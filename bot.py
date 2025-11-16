# bot.py — Phone, Email, Family + Vehicle, GST, IFSC, Instagram, IP lookup
# Updated: integrated Vehicle, GST, IFSC, Instagram, IP into main menu
# Notes: Uses emoji-based "colored" formatting because Telegram HTML doesn't support CSS colors.

import os
import re
import json
import logging
import urllib.parse
import requests
import asyncio
import threading
import time
import sqlite3
import uuid
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, request

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ================== CONFIG =====================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8285505523:AAEoJgpBpVeUEErcseSSeCIEb0MwNAZ_5qM")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://advance-osint-zii6.onrender.com")

API_KEY = os.environ.get("API_KEY", "5785818477:QqPj82nd")
LEAK_API = os.environ.get("LEAK_API", "https://leakosintapi.com/")
FAMILY_API = os.environ.get("FAMILY_API", "https://encore.toxictanji0503.workers.dev/family?id=")

# Extra APIs
VEHICLE_API_BASE = os.environ.get("VEHICLE_API", "https://encore.toxictanji0503.workers.dev/rcfuck?vehicle_number=")
GST_API_BASE = os.environ.get("GST_API", "https://gstlookup.hideme.eu.org/?gstNumber=")
IFSC_API_BASE = os.environ.get("IFSC_API", "https://encore.toxictanji0503.workers.dev/ifsc?id=")
INSTA_API_BASE = os.environ.get("INSTA_API", "https://insta-profile-info-api.vercel.app/api/instagram.php?username=")
IP_API_BASE = os.environ.get("IP_API", "http://ip-api.com/json/")

# Channel/Group IDs
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID", "-1003467393174")
ADMIN_GROUP_ID = os.environ.get("ADMIN_GROUP_ID", "-1003275777221")

LANG = "ru"
LIMIT = 100

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@itsmezigzagzozo")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6314556756"))

# Simplified credit system - 1 credit per search
COST_PER_SEARCH = int(os.environ.get("COST_PER_SEARCH", "1"))

# Referral and bonus settings
REFERRAL_BONUS = int(os.environ.get("REFERRAL_BONUS", "3"))  # Credits for referring someone
WELCOME_BONUS = int(os.environ.get("WELCOME_BONUS", "2"))   # Credits for new users

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== DATABASE SETUP =====================

def init_db():
    conn = sqlite3.connect('user_data.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # The above parameterized create is fine; if the sqlite driver rejects param in DDL, fallback:
    try:
        conn.commit()
    except Exception:
        # recreate without param (fallback)
        cursor.execute('DROP TABLE IF EXISTS users_temp_for_init')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                credits INTEGER DEFAULT 2,
                referral_code TEXT UNIQUE,cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        credits INTEGER DEFAULT {WELCOME_BONUS},
        referral_code TEXT UNIQUE,
        referred_by INTEGER,
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_searches INTEGER DEFAULT 0
    )
''')
                referred_by INTEGER,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_searches INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            input_query TEXT,
            output_data TEXT,
            search_type TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_claimed BOOLEAN DEFAULT FALSE,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users (user_id),
            FOREIGN KEY (referred_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    return conn

db_conn = init_db()

# ================== DATABASE FUNCTIONS =====================

def get_user(user_id):
    cursor = db_conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'credits': user[3],
            'referral_code': user[4],
            'referred_by': user[5],
            'join_date': user[6],
            'total_searches': user[7]
        }
    return None

def create_user(user_id, username, first_name, referral_code=None, referred_by=None):
    cursor = db_conn.cursor()
    if not referral_code:
        referral_code = str(uuid.uuid4())[:8].upper()
    
    # Try insert; if exists, replace
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, first_name, credits, referral_code, referred_by)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, WELCOME_BONUS, referral_code, referred_by))
    db_conn.commit()
    
    if referred_by:
        cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', 
                     (REFERRAL_BONUS, referred_by))
        db_conn.commit()

def update_credits(user_id, amount):
    cursor = db_conn.cursor()
    cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', 
                  (amount, user_id))
    db_conn.commit()

def use_credit(user_id):
    cursor = db_conn.cursor()
    cursor.execute('UPDATE users SET credits = credits - ?, total_searches = total_searches + 1 WHERE user_id = ?', 
                  (COST_PER_SEARCH, user_id))
    db_conn.commit()

def log_search(user_id, username, input_query, output_data, search_type):
    cursor = db_conn.cursor()
    cursor.execute('''
        INSERT INTO search_logs (user_id, username, input_query, output_data, search_type)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, input_query, json.dumps(output_data), search_type))
    db_conn.commit()

def get_all_users():
    cursor = db_conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, credits FROM users')
    return cursor.fetchall()

def get_user_by_referral(referral_code):
    cursor = db_conn.cursor()
    cursor.execute('SELECT * FROM users WHERE referral_code = ?', (referral_code,))
    user = cursor.fetchone()
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'credits': user[3],
            'referral_code': user[4],
            'referred_by': user[5],
            'join_date': user[6],
            'total_searches': user[7]
        }
    return None

# ================== FLASK APP =====================

app = Flask(__name__)
telegram_app = None
telegram_loop = None

@app.route("/")
def home():
    return "🔍 Phone & Email Search Bot - Active"

@app.route("/health")
def health():
    return json.dumps({"status": "active", "timestamp": datetime.now().isoformat()})

@app.route("/webhook", methods=["POST"])
def webhook():
    global telegram_app, telegram_loop
    if telegram_app is None or telegram_loop is None:
        return "Bot starting...", 503

    try:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        future = asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), telegram_loop)
        return "OK"
    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        return "OK", 200

# ================== HELPERS =====================

def chunk(text, size=3500):
    return [text[i:i + size] for i in range(0, len(text), size)]

def normalize_phone(txt):
    s = re.sub(r"[^0-9]", "", txt)
    if len(s) == 10:
        return "+91" + s
    if len(s) == 11 and s.startswith("0"):
        return "+91" + s[1:]
    if len(s) == 12 and s.startswith("91"):
        return "+" + s
    if len(s) == 13 and s.startswith("+91"):
        return s
    return None

# ================== API CALLS =====================

def leak_raw(query):
    try:
        r = requests.post(
            LEAK_API,
            json={
                "token": API_KEY,
                "request": query,
                "limit": LIMIT,
                "lang": LANG
            },
            timeout=20
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def family_raw(fid):
    try:
        r = requests.get(FAMILY_API + fid, timeout=20)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# Extra APIs
def vehicle_info_api(vnum):
    try:
        url = VEHICLE_API_BASE + urllib.parse.quote_plus(vnum)
        r = requests.get(url, timeout=20)
        try:
            return r.json()
        except:
            return {"raw": r.text}
    except Exception as e:
        return {"error": str(e)}

def gst_lookup_api(gst):
    try:
        url = GST_API_BASE + urllib.parse.quote_plus(gst)
        r = requests.get(url, timeout=20)
        try:
            return r.json()
        except:
            return {"raw": r.text}
    except Exception as e:
        return {"error": str(e)}

def ifsc_lookup_api(ifsc):
    try:
        url = IFSC_API_BASE + urllib.parse.quote_plus(ifsc)
        r = requests.get(url, timeout=20)
        try:
            return r.json()
        except:
            return {"raw": r.text}
    except Exception as e:
        return {"error": str(e)}

def insta_lookup_api(username):
    try:
        # strip @ if present
        username = username.lstrip("@")
        url = INSTA_API_BASE + urllib.parse.quote_plus(username)
        r = requests.get(url, timeout=20)
        try:
            return r.json()
        except:
            return {"raw": r.text}
    except Exception as e:
        return {"error": str(e)}

def ip_lookup_api(ip):
    try:
        url = IP_API_BASE + urllib.parse.quote_plus(ip)
        r = requests.get(url, timeout=20)
        try:
            return r.json()
        except:
            return {"raw": r.text}
    except Exception as e:
        return {"error": str(e)}

# ================== RESULT CHECKERS =====================

def has_valid_data(data):
    """Generic check for result existence."""
    if not data:
        return False
    if isinstance(data, dict):
        if data.get('error') or data.get('status') == 'fail' or data.get('message') == 'No results found':
            return False
        # any non-empty key suggests results
        if any(v not in [None, "", [], {}] for v in data.values()):
            return True
    if isinstance(data, list) and len(data) > 0:
        return True
    return False

# ================== FORMATTING (emoji "colors") =====================

def heading(title):
    return f"🟦 <b><u>{title}</u></b>\n\n"

def success_field(k, v):
    return f"🟢 <b>{k}:</b> <code>{escape_html(str(v))}</code>\n"

def error_line(msg):
    return f"🔴 <b>{escape_html(msg)}</b>\n"

def note_line(msg):
    return f"🟡 <b>{escape_html(msg)}</b>\n"

def json_block(data):
    pretty = json.dumps(data, indent=2, ensure_ascii=False)
    # wrap in <pre> to preserve formatting
    return f"<pre>{escape_html(pretty)}</pre>"

def escape_html(s):
    # basic escape for <>&
    return (s.replace('&', '&amp;')
              .replace('<', '&lt;')
              .replace('>', '&gt;'))

# ================== SAFE SENDERS =====================

async def safe_reply(update, text, **kwargs):
    chat = update.message or (update.callback_query and update.callback_query.message)
    if chat:
        try:
            return await chat.reply_text(text, **kwargs)
        except Exception as e:
            logger.warning(f"reply_text failed, trying send_message: {e}")
            try:
                return await chat.reply_markdown_v2(text, **kwargs)
            except Exception:
                return None
    return None

async def log_search_to_group(context, user_info, input_query, output_data, search_type, success=True):
    """Log search details to the admin group - only for successful searches"""
    if not success:
        return  # Don't log failed searches
        
    try:
        log_message = (
            f"🔍 <b>NEW SEARCH REQUEST</b>\n"
            "────────────────────\n\n"
            f"👤 <b>User:</b> {escape_html(user_info['first_name'])}\n"
            f"📱 <b>Username:</b> @{escape_html(user_info.get('username') or '')}\n"
            f"🆔 <b>User ID:</b> {user_info['user_id']}\n\n"
            f"🔎 <b>Search Type:</b> {escape_html(search_type)}\n"
            f"📥 <b>Input:</b> {escape_html(input_query)}\n"
            f"📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"────────────────────"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=log_message,
            parse_mode="HTML"
        )
        
        # Also send a preview of the actual output data (limited)
        if output_data:
            preview = json.dumps(remove_infoleak(output_data), indent=2, ensure_ascii=False)
            if len(preview) > 3000:
                preview = preview[:3000] + "..."
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"<pre>{escape_html(preview)}</pre>",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Failed to log to admin group: {e}")

# ================== RESULT FILTERS (reuse existing utilities) =====================

def filter_no_results(data):
    if not data or not isinstance(data, dict):
        return data
    # if provider uses specific "No results" patterns, try to clean minimal
    if 'message' in data and data['message'].lower().startswith("no"):
        return {}
    return data

def remove_infoleak(data):
    if not data or not isinstance(data, dict):
        return data
    cleaned = dict(data)
    # remove any InfoLeak keys broadly
    if 'InfoLeak' in cleaned:
        del cleaned['InfoLeak']
    return cleaned

# ================== COMMANDS & MENU =====================

async def start(update: Update, context):
    user = update.effective_user
    user_data = get_user(user.id)
    
    if not user_data:
        referral_code = None
        referred_by = None
        if context.args and len(context.args) > 0:
            referral_code = context.args[0]
            referred_by_user = get_user_by_referral(referral_code)
            if referred_by_user:
                referred_by = referred_by_user['user_id']
                create_user(user.id, user.username, user.first_name, referred_by=referred_by)
            else:
                create_user(user.id, user.username, user.first_name)
        else:
            create_user(user.id, user.username, user.first_name)
        
        user_data = get_user(user.id)
        
        # Log new user to admin group
        try:
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"🆕 <b>NEW USER JOINED</b>\n\n👤 {escape_html(user.first_name)} (@{escape_html(user.username or '')})\n🆔 {user.id}\n🎁 Got {WELCOME_BONUS} free credits\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to log new user: {e}")

    user_data = get_user(user.id)
    try:
        bot_username = (await context.bot.get_me()).username
    except:
        bot_username = "bot"
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"

    welcome_text = (
        "🔍 <b>Phone & Email Search Bot</b>\n\n"
        "Find information using phone numbers, email addresses, family IDs, or the tools below.\n\n"
        f"👋 Welcome <b>{escape_html(user.first_name)}</b>!\n"
        f"💰 <b>Your Credits:</b> {user_data['credits']}\n"
        f"🔍 <b>Cost per search:</b> {COST_PER_SEARCH} credit(s)\n\n"
        "<b>Choose what you want to search:</b>"
    )
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Phone Number Search", callback_data="lookup_phone"),
         InlineKeyboardButton("📧 Email Address Search", callback_data="lookup_email")],
        [InlineKeyboardButton("👪 Family Members Search", callback_data="family")],
        [InlineKeyboardButton("🚘 Vehicle Info (RC)", callback_data="vehicle")],
        [InlineKeyboardButton("🧾 GST Lookup", callback_data="gst"),
         InlineKeyboardButton("🏦 IFSC Lookup", callback_data="ifsc")],
        [InlineKeyboardButton("📷 Instagram Lookup", callback_data="instagram"),
         InlineKeyboardButton("🌐 IP Lookup", callback_data="ip")],
        [
            InlineKeyboardButton("💰 Buy Credits", callback_data="buy"),
            InlineKeyboardButton("👥 Refer & Earn", callback_data="referral")
        ],
        [InlineKeyboardButton("📊 My Account", callback_data="dashboard")]
    ])

    await safe_reply(
        update,
        welcome_text,
        parse_mode="HTML",
        reply_markup=markup
    )

async def buy(update, context):
    contact_text = (
        "💰 <b>Buy Credits</b>\n\n"
        "Need more credits to search?\n\n"
        "🔍 <b>Cost:</b> 1 credit per search\n"
        f"💬 <b>Contact Admin:</b> {ADMIN_USERNAME}\n\n"
        "Click the button below to message the admin directly:"
    )
    
    await safe_reply(
        update,
        contact_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME.lstrip('@')}")]
        ])
    )

async def balance(update, context):
    uid = update.effective_user.id
    user_data = get_user(uid)
    
    if not user_data:
        create_user(uid, update.effective_user.username, update.effective_user.first_name)
        user_data = get_user(uid)

    status_msg = (
        "💰 <b>Your Account</b>\n"
        "────────────────────\n\n"
        f"👤 <b>Name:</b> {escape_html(user_data['first_name'])}\n"
        f"🆔 <b>User ID:</b> {uid}\n\n"
        f"💳 <b>Available Credits:</b> {user_data['credits']}\n"
        f"🔍 <b>Total Searches:</b> {user_data['total_searches']}\n\n"
        "<i>Each search costs 1 credit</i>"
    )
    await safe_reply(update, status_msg, parse_mode="HTML")

async def referral(update, context):
    uid = update.effective_user.id
    user_data = get_user(uid)
    
    if not user_data:
        create_user(uid, update.effective_user.username, update.effective_user.first_name)
        user_data = get_user(uid)

    try:
        bot_username = (await context.bot.get_me()).username
    except:
        bot_username = "bot"
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"
    
    referral_msg = (
        "👥 <b>Refer & Earn</b>\n"
        "────────────────────\n\n"
        "Share your referral link and earn credits when friends join!\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{escape_html(referral_link)}</code>\n\n"
        f"🎁 <b>You get:</b> {REFERRAL_BONUS} credits per referral\n"
        f"🎁 <b>Friend gets:</b> {WELCOME_BONUS} free credits\n\n"
        "<i>Share your link and both of you get bonus credits!</i>"
    )
    await safe_reply(update, referral_msg, parse_mode="HTML")

async def dashboard(update, context):
    uid = update.effective_user.id
    user_data = get_user(uid)
    
    dashboard_msg = (
        "📊 <b>My Account</b>\n"
        "────────────────────\n\n"
        f"👤 <b>Name:</b> {escape_html(user_data['first_name'])}\n"
        f"🆔 <b>User ID:</b> {uid}\n\n"
        f"💳 <b>Credits:</b> {user_data['credits']}\n"
        f"🔍 <b>Total Searches:</b> {user_data['total_searches']}\n"
        f"🔗 <b>Referral Code:</b> {escape_html(user_data['referral_code'])}\n\n"
        "<i>Need more credits? Use /buy</i>"
    )
    await safe_reply(update, dashboard_msg, parse_mode="HTML")

async def approve(update, context):
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ Admin only command.")
    
    try:
        args = context.args or []
        if len(args) != 2:
            return await safe_reply(update, "Usage: /approve USER_ID CREDITS")
        
        uid = int(args[0])
        amt = int(args[1])
        
        user_data = get_user(uid)
        if not user_data:
            return await safe_reply(update, "❌ User not found.")
        
        update_credits(uid, amt)
        
        try:
            await context.bot.send_message(
                uid, 
                f"🎉 <b>Credits Added</b>\n\n"
                f"You received <b>{amt}</b> credits!\n"
                f"New balance: <b>{user_data['credits'] + amt}</b> credits",
                parse_mode="HTML"
            )
        except:
            pass
        
        await safe_reply(update, f"✅ Added {amt} credits to user {uid}")
        
    except Exception as e:
        await safe_reply(update, f"❌ Error: {e}")

async def free_credits(update, context):
    """Give free credits to ALL users"""
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ Admin only command.")
    
    try:
        args = context.args or []
        if not args:
            return await safe_reply(update, "Usage: /freecredits AMOUNT\nExample: /freecredits 5")
        
        amt = int(args[0])
        users = get_all_users()
        successful = 0
        failed = 0
        
        processing_msg = await safe_reply(update, f"🔄 Giving {amt} free credits to all users...")
        
        for user in users:
            try:
                update_credits(user[0], amt)
                await context.bot.send_message(
                    user[0],
                    f"🎉 <b>Free Credits!</b>\n\n"
                    f"You received <b>{amt}</b> free credits from admin!\n"
                    f"Enjoy your searches! 🔍",
                    parse_mode="HTML"
                )
                successful += 1
                await asyncio.sleep(0.1)  # Rate limiting
            except Exception as e:
                failed += 1
                logger.error(f"Failed to send to user {user[0]}: {e}")
        
        # Log this action to admin group
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"🎁 <b>MASS CREDIT DISTRIBUTION</b>\n\n"
                 f"📤 Sent by: Admin\n"
                 f"💰 Amount: {amt} credits each\n"
                 f"✅ Successful: {successful} users\n"
                 f"❌ Failed: {failed} users\n"
                 f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="HTML"
        )
        
        await processing_msg.edit_text(
            f"✅ <b>Free Credits Distributed!</b>\n\n"
            f"💰 <b>Amount:</b> {amt} credits each\n"
            f"👥 <b>Successful:</b> {successful} users\n"
            f"❌ <b>Failed:</b> {failed} users\n"
            f"💎 <b>Total Credits Given:</b> {successful * amt}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await safe_reply(update, f"❌ Error: {e}")

async def stats(update, context):
    """Show bot statistics (Admin only)"""
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ Admin only command.")
    
    try:
        users = get_all_users()
        total_users = len(users)
        total_credits = sum(user[3] for user in users)
        total_searches = sum(get_user(user[0])['total_searches'] for user in users)
        
        stats_msg = (
            "📊 <b>Bot Statistics</b>\n"
            "────────────────────\n\n"
            f"👥 <b>Total Users:</b> {total_users}\n"
            f"💎 <b>Total Credits in System:</b> {total_credits}\n"
            f"🔍 <b>Total Searches Made:</b> {total_searches}\n"
            f"📅 <b>Last Updated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "<i>Use /freecredits AMOUNT to give credits to all users</i>"
        )
        
        await safe_reply(update, stats_msg, parse_mode="HTML")
        
    except Exception as e:
        await safe_reply(update, f"❌ Error: {e}")

# ================== CALLBACK BUTTONS =====================

async def button(update: Update, context):
    q = update.callback_query
    await q.answer()

    if q.data == "lookup_phone":
        context.user_data["lookup_mode"] = "phone"
        return await safe_reply(update, "🔍 <b>Phone Search</b>\n\nSend a phone number (e.g. 9876543210):", parse_mode="HTML")

    elif q.data == "lookup_email":
        context.user_data["lookup_mode"] = "email"
        return await safe_reply(update, "🔍 <b>Email Search</b>\n\nSend an email address:", parse_mode="HTML")

    elif q.data == "family":
        context.user_data["family"] = True
        return await safe_reply(update, "👪 <b>Family Search</b>\n\nEnter Family ID to find family members:", parse_mode="HTML")

    elif q.data == "vehicle":
        context.user_data["vehicle"] = True
        return await safe_reply(update, "🚘 <b>Vehicle (RC) Lookup</b>\n\nSend vehicle number (e.g. MH12DE1433):", parse_mode="HTML")

    elif q.data == "gst":
        context.user_data["gst"] = True
        return await safe_reply(update, "🧾 <b>GST Lookup</b>\n\nSend GST number (15 chars):", parse_mode="HTML")

    elif q.data == "ifsc":
        context.user_data["ifsc"] = True
        return await safe_reply(update, "🏦 <b>IFSC Lookup</b>\n\nSend IFSC code (e.g. HDFC0001234):", parse_mode="HTML")

    elif q.data == "instagram":
        context.user_data["instagram"] = True
        return await safe_reply(update, "📷 <b>Instagram Lookup</b>\n\nSend Instagram username (with or without @):", parse_mode="HTML")

    elif q.data == "ip":
        context.user_data["ip"] = True
        return await safe_reply(update, "🌐 <b>IP Lookup</b>\n\nSend IPv4 address (e.g. 8.8.8.8):", parse_mode="HTML")

    elif q.data == "buy":
        return await buy(update, context)

    elif q.data == "referral":
        return await referral(update, context)

    elif q.data == "dashboard":
        return await dashboard(update, context)

# ================== MESSAGE HANDLER =====================

# Regex patterns for auto-detect
IFSC_REGEX = re.compile(r'^[A-Za-z]{4}0[A-Za-z0-9]{6}$')
GST_REGEX = re.compile(r'^[0-9A-Z]{15}$', re.I)
IPV4_REGEX = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')
IF_VEHICLE_SIMPLE = re.compile(r'^[A-Z]{2}\d{1,2}[A-Z]{0,2}\d{1,4}$', re.I)

async def handle_message(update: Update, context):
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    user = update.effective_user

    user_data = get_user(uid)
    if not user_data:
        create_user(uid, user.username, user.first_name)
        user_data = get_user(uid)

    phone_auto = normalize_phone(text)
    email_auto = re.fullmatch(r"[\w.-]+@[\w.-]+\.\w+", text)

    # determine mode from button state
    mode = context.user_data.pop("lookup_mode", None)
    family_mode = context.user_data.pop("family", False)
    vehicle_mode = context.user_data.pop("vehicle", False)
    gst_mode = context.user_data.pop("gst", False)
    ifsc_mode = context.user_data.pop("ifsc", False)
    insta_mode = context.user_data.pop("instagram", False)
    ip_mode = context.user_data.pop("ip", False)

    # If phone or email was entered, treat as lookup
    if phone_auto or email_auto or mode:
        context.user_data["lookup"] = True

    # ---------------- PHONE / EMAIL / LEAKS ----------------
    if context.user_data.pop("lookup", False):
        phone = normalize_phone(text)
        email = email_auto

        if not phone and not email:
            return await safe_reply(update, "❌ Please enter a valid phone number or email address.")

        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need {COST_PER_SEARCH} credit(s) to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Searching... Please wait")

        try:
            use_credit(uid)
            # SINGLE API CALL - store the result
            raw_data = leak_raw(phone if phone else email.group())
            
            if has_valid_data(raw_data):
                cleaned_data = filter_no_results(raw_data)
                cleaned_data = remove_infoleak(cleaned_data)
                log_search(uid, user.username, text, cleaned_data, "lookup")
                
                user_info = {'user_id': uid, 'username': user.username, 'first_name': user.first_name}
                await log_search_to_group(context, user_info, text, cleaned_data, "Phone/Email Search", success=True)
                
                formatted_output = format_raw_output(cleaned_data)
                for chunk_text in chunk(formatted_output, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)  # Return the credit
                await safe_reply(update, "❌ No information found for this search. Your credit has been returned. ✅")
        except Exception as e:
            logger.error(f"Search error: {e}")
            update_credits(uid, COST_PER_SEARCH)  # Return the credit on error
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
        return

    # ---------------- FAMILY ----------------
    if family_mode:
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need {COST_PER_SEARCH} credit(s) to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Searching family information...")

        try:
            use_credit(uid)
            raw_data = family_raw(text)
            if raw_data and "memberDetailsList" in raw_data and raw_data["memberDetailsList"]:
                log_search(uid, user.username, text, raw_data, "family")
                user_info = {'user_id': uid, 'username': user.username, 'first_name': user.first_name}
                await log_search_to_group(context, user_info, text, raw_data, "Family Search", success=True)
                formatted_output = format_family_raw(raw_data)
                for chunk_text in chunk(formatted_output, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "❌ No family information found. Your credit has been returned. ✅")
        except Exception as e:
            logger.error(f"Family search error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
        return

    # ---------------- VEHICLE ----------------
    if vehicle_mode:
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need {COST_PER_SEARCH} credit(s) to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        vnum = text.strip()
        processing_msg = await safe_reply(update, "🔄 Looking up vehicle...")

        try:
            use_credit(uid)
            data = vehicle_info_api(vnum)
            if has_valid_data(data):
                cleaned = remove_infoleak(data)
                log_search(uid, user.username, text, cleaned, "vehicle")
                user_info = {'user_id': uid, 'username': user.username, 'first_name': user.first_name}
                await log_search_to_group(context, user_info, text, cleaned, "Vehicle Lookup", success=True)

                out = heading("Vehicle Information")
                # try to produce friendly fields if present
                if isinstance(cleaned, dict):
                    for k, v in cleaned.items():
                        out += success_field(k, v)
                    out += "\n" + json_block(cleaned)
                else:
                    out += json_block(cleaned)
                for chunk_text in chunk(out, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "🔎 No vehicle information found. Your credit has been returned. ✅")
        except Exception as e:
            logger.error(f"Vehicle lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, f"❌ Vehicle lookup failed: {e}\nYour credit has been returned.")
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
        return

    # ---------------- GST ----------------
    if gst_mode:
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need {COST_PER_SEARCH} credit(s) to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        gst = text.strip()
        processing_msg = await safe_reply(update, "🔄 Looking up GST...")

        try:
            use_credit(uid)
            data = gst_lookup_api(gst)
            if has_valid_data(data):
                cleaned = remove_infoleak(data)
                log_search(uid, user.username, text, cleaned, "gst")
                user_info = {'user_id': uid, 'username': user.username, 'first_name': user.first_name}
                await log_search_to_group(context, user_info, text, cleaned, "GST Lookup", success=True)

                out = heading("GST Information")
                if isinstance(cleaned, dict):
                    for k, v in cleaned.items():
                        out += success_field(k, v)
                    out += "\n" + json_block(cleaned)
                else:
                    out += json_block(cleaned)
                for chunk_text in chunk(out, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "🔎 No GST information found. Your credit has been returned. ✅")
        except Exception as e:
            logger.error(f"GST lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, f"❌ GST lookup failed: {e}\nYour credit has been returned.")
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
        return

    # ---------------- IFSC ----------------
    if ifsc_mode:
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need {COST_PER_SEARCH} credit(s) to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        ifsc = text.strip().upper()
        processing_msg = await safe_reply(update, "🔄 Looking up IFSC...")

        try:
            use_credit(uid)
            data = ifsc_lookup_api(ifsc)
            if has_valid_data(data):
                cleaned = remove_infoleak(data)
                log_search(uid, user.username, text, cleaned, "ifsc")
                user_info = {'user_id': uid, 'username': user.username, 'first_name': user.first_name}
                await log_search_to_group(context, user_info, text, cleaned, "IFSC Lookup", success=True)

                out = heading("IFSC Information")
                if isinstance(cleaned, dict):
                    for k, v in cleaned.items():
                        out += success_field(k, v)
                    out += "\n" + json_block(cleaned)
                else:
                    out += json_block(cleaned)
                for chunk_text in chunk(out, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "🔎 No IFSC information found. Your credit has been returned. ✅")
        except Exception as e:
            logger.error(f"IFSC lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, f"❌ IFSC lookup failed: {e}\nYour credit has been returned.")
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
        return

    # ---------------- INSTAGRAM ----------------
    if insta_mode:
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need {COST_PER_SEARCH} credit(s) to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        usern = text.strip().lstrip("@")
        processing_msg = await safe_reply(update, "🔄 Looking up Instagram profile...")

        try:
            use_credit(uid)
            data = insta_lookup_api(usern)
            if has_valid_data(data):
                cleaned = remove_infoleak(data)
                log_search(uid, user.username, text, cleaned, "instagram")
                user_info = {'user_id': uid, 'username': user.username, 'first_name': user.first_name}
                await log_search_to_group(context, user_info, text, cleaned, "Instagram Lookup", success=True)

                out = heading("Instagram Profile")
                if isinstance(cleaned, dict):
                    for k, v in cleaned.items():
                        out += success_field(k, v)
                    out += "\n" + json_block(cleaned)
                else:
                    out += json_block(cleaned)
                for chunk_text in chunk(out, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "🔎 No Instagram information found. Your credit has been returned. ✅")
        except Exception as e:
            logger.error(f"Instagram lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, f"❌ Instagram lookup failed: {e}\nYour credit has been returned.")
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
        return

    # ---------------- IP ----------------
    if ip_mode:
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need {COST_PER_SEARCH} credit(s) to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        ipaddr = text.strip()
        processing_msg = await safe_reply(update, "🔄 Looking up IP address...")

        try:
            use_credit(uid)
            data = ip_lookup_api(ipaddr)
            if has_valid_data(data):
                cleaned = remove_infoleak(data)
                log_search(uid, user.username, text, cleaned, "ip")
                user_info = {'user_id': uid, 'username': user.username, 'first_name': user.first_name}
                await log_search_to_group(context, user_info, text, cleaned, "IP Lookup", success=True)

                out = heading("IP Address Lookup")
                if isinstance(cleaned, dict):
                    for k, v in cleaned.items():
                        out += success_field(k, v)
                    out += "\n" + json_block(cleaned)
                else:
                    out += json_block(cleaned)
                for chunk_text in chunk(out, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "🔎 No IP information found. Your credit has been returned. ✅")
        except Exception as e:
            logger.error(f"IP lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, f"❌ IP lookup failed: {e}\nYour credit has been returned.")
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
        return

    # ---------------- AUTO-DETECT (no explicit mode) ----------------
    # If user typed a single token that looks like IFSC / GST / IPv4 / vehicle / insta, try to detect and run (auto-detect enabled)
    txt_u = text.strip()
    if txt_u:
        token = txt_u.split()[0]
        # IFSC
        if IFSC_REGEX.match(token):
            context.user_data["ifsc"] = True
            return await handle_message(update, context)
        # GST (15 chars)
        if GST_REGEX.match(token) and len(token) == 15:
            context.user_data["gst"] = True
            return await handle_message(update, context)
        # IPv4
        if IPV4_REGEX.match(token):
            context.user_data["ip"] = True
            return await handle_message(update, context)
        # Vehicle (simple heuristic)
        if IF_VEHICLE_SIMPLE.match(token) and 6 <= len(token) <= 12:
            context.user_data["vehicle"] = True
            return await handle_message(update, context)
        # Instagram heuristic: starts with @ or only letters/digits and length <=30
        if token.startswith("@") or (re.match(r'^[A-Za-z0-9._]{1,30}$', token) and '.' not in token and '@' not in token and len(token) <= 30):
            # prefer instagram only if other patterns not matched
            # If it's clear phone/email skip
            if not normalize_phone(token) and not re.fullmatch(r"[\w.-]+@[\w.-]+\.\w+", token):
                context.user_data["instagram"] = True
                return await handle_message(update, context)

    # Default fallback
    await safe_reply(update, "👋 Use the menu buttons to start searching! (You can also paste IFSC/GST/RC/username/IP directly.)")

# ------------------ UTIL: format_raw_output & format_family_raw (kept from previous) ----------------

def swap_father_fullname(data):
    if isinstance(data, dict):
        result = data.copy()
        if 'FatherName' in result and 'FullName' in result:
            father_name = result['FatherName']
            full_name = result['FullName']
            result['FatherName'] = full_name
            result['FullName'] = father_name
        for key, value in result.items():
            result[key] = swap_father_fullname(value)
        return result
    elif isinstance(data, list):
        return [swap_father_fullname(item) for item in data]
    else:
        return data

def format_raw_output(data):
    cleaned_data = remove_infoleak(data)
    swapped = swap_father_fullname(cleaned_data)
    pretty_json = json.dumps(swapped, indent=2, ensure_ascii=False)
    # Use emoji "colors" and heading
    out = heading("Search Results")
    out += "<pre>" + escape_html(pretty_json) + "</pre>"
    return out

def format_family_raw(data):
    pretty_json = json.dumps(data, indent=2, ensure_ascii=False)
    return f"<pre>{escape_html(pretty_json)}</pre>"

# ================== BACKGROUND LOOP =====================

def start_telegram_background(app_obj):
    loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(app_obj.initialize())
            webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
            loop.run_until_complete(app_obj.bot.delete_webhook(drop_pending_updates=True))
            loop.run_until_complete(app_obj.bot.set_webhook(webhook_url))
            logger.info(f"Webhook: {webhook_url}")
            loop.create_task(app_obj.start())
            loop.run_forever()
        except Exception:
            logger.exception("Background loop error")
        finally:
            try:
                loop.run_until_complete(app_obj.stop())
                loop.run_until_complete(app_obj.shutdown())
            except:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return loop

# ================== MAIN =====================

def main():
    global telegram_app, telegram_loop

    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("buy", buy))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("referral", referral))
    telegram_app.add_handler(CommandHandler("dashboard", dashboard))
    telegram_app.add_handler(CommandHandler("approve", approve))
    telegram_app.add_handler(CommandHandler("freecredits", free_credits))
    telegram_app.add_handler(CommandHandler("stats", stats))
    telegram_app.add_handler(CallbackQueryHandler(button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    admin_user = get_user(ADMIN_ID)
    if not admin_user:
        create_user(ADMIN_ID, "admin", "Admin")
        update_credits(ADMIN_ID, 100)

    logger.info("🔍 Phone & Email Search Bot Started")

    try:
        telegram_loop = start_telegram_background(telegram_app)
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port, debug=False)
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

if __name__ == "__main__":
    main()
