# bot.py — Premium OSINT Intelligence Bot v2.0
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

# Channel/Group IDs
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID", "-1003467393174")
ADMIN_GROUP_ID = os.environ.get("ADMIN_GROUP_ID", "-1003275777221")

LANG = "ru"
LIMIT = 100

UPI_ID = "durgeshraihero@oksbi"
QR_IMAGE = "https://i.ibb.co/S6nfK15/upi.jpg"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6314556756"))

COST_LOOKUP = 50
COST_FAMILY = 20
COST_TRACK = 10

RENDER_LINK = os.environ.get("RENDER_LINK", "https://jsjs-kzua.onrender.com")

# Referral and trial settings
REFERRAL_BONUS = 3
TRIAL_SEARCHES = 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== DATABASE SETUP =====================

def init_db():
    conn = sqlite3.connect('user_data.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            free_searches INTEGER DEFAULT 2,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_searches INTEGER DEFAULT 0
        )
    ''')
    
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
            'balance': user[3],
            'free_searches': user[4],
            'referral_code': user[5],
            'referred_by': user[6],
            'join_date': user[7],
            'total_searches': user[8]
        }
    return None

def create_user(user_id, username, first_name, referral_code=None, referred_by=None):
    cursor = db_conn.cursor()
    if not referral_code:
        referral_code = str(uuid.uuid4())[:8].upper()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, first_name, balance, free_searches, referral_code, referred_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, 0, TRIAL_SEARCHES, referral_code, referred_by))
    db_conn.commit()
    
    if referred_by:
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', 
                     (REFERRAL_BONUS, referred_by))
        db_conn.commit()

def update_balance(user_id, amount):
    cursor = db_conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', 
                  (amount, user_id))
    db_conn.commit()

def use_free_search(user_id):
    cursor = db_conn.cursor()
    cursor.execute('UPDATE users SET free_searches = free_searches - 1, total_searches = total_searches + 1 WHERE user_id = ?', 
                  (user_id,))
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
    cursor.execute('SELECT user_id, username, first_name, balance, free_searches FROM users')
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
            'balance': user[3],
            'free_searches': user[4],
            'referral_code': user[5],
            'referred_by': user[6],
            'join_date': user[7],
            'total_searches': user[8]
        }
    return None

# ================== FLASK APP =====================

app = Flask(__name__)
telegram_app = None
telegram_loop = None

@app.route("/")
def home():
    return "🔍 Premium OSINT Intelligence Platform - Operational"

@app.route("/health")
def health():
    return json.dumps({"status": "optimal", "timestamp": datetime.now().isoformat()})

@app.route("/webhook", methods=["POST"])
def webhook():
    global telegram_app, telegram_loop
    if telegram_app is None or telegram_loop is None:
        return "System Initializing", 503

    try:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        future = asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), telegram_loop)
        return "✅"
    except Exception as e:
        logger.exception(f"Webhook Processing Error: {e}")
        return "✅", 200

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

def google_maps_link(address):
    return "https://www.google.com/maps/search/" + urllib.parse.quote(address or "")

def whatsapp_check(number):
    return f"https://wa.me/{number.replace('+','')}" if number else ""

def make_tracking_link(uid, site):
    return f"{RENDER_LINK}/?chat_id={uid}&site={urllib.parse.quote(site)}"

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

# ================== FORMATTERS =====================

def format_lookup(entry):
    name = (entry.get("FatherName") or "N/A").title()
    father = (entry.get("FullName") or "N/A").title()

    address = entry.get("Address", "")
    maps = google_maps_link(address)
    region = (entry.get("Region", "")).replace(";", " / ")
    doc = entry.get("DocNumber", "N/A")

    phones = []
    for k, v in entry.items():
        if "phone" in k.lower() and v:
            p = str(v)
            if len(p) == 10:
                p = "+91" + p
            phones.append(p)

    phone_block = "\n".join([f"• {p}" for p in phones]) or "Not Available"
    wa = whatsapp_check(phones[0]) if phones else ""

    return (
        "🔍 <b>Digital Footprint Analysis Report</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Primary Identity:</b> {name}\n"
        f"👨‍👦 <b>Lineage Reference:</b> {father}\n\n"
        f"🏠 <b>Geolocation Data:</b>\n{address}\n\n"
        f"🗺 <b>Geospatial Mapping:</b> <a href='{maps}'>Access Coordinates</a>\n\n"
        f"🌐 <b>Regional Jurisdiction:</b> {region}\n\n"
        f"📞 <b>Telecom Footprint:</b>\n{phone_block}\n\n"
        f"💬 <b>Communication Channel:</b> <a href='{wa}'>WhatsApp Verification</a>\n\n"
        f"🧾 <b>Identity Document:</b> {doc}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
    )

def format_list(raw):
    out = "🔍 <b>Comprehensive Digital Intelligence Report</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for db_name, block in raw.get("List", {}).items():
        out += f"🗃 <b>Data Repository:</b> {db_name}\n"
        for i, entry in enumerate(block.get("Data", []), 1):
            name = (entry.get("FatherName") or "N/A").title()
            father = (entry.get("FullName") or "N/A").title()
            address = entry.get("Address", "")
            region = (entry.get("Region", "")).replace(";", " / ")
            maps = google_maps_link(address)
            doc = entry.get("DocNumber", "N/A")

            phones = []
            for k, v in entry.items():
                if "phone" in k.lower() and v:
                    p = str(v)
                    if len(p) == 10:
                        p = "+91" + p
                    phones.append(p)

            phone_block = "\n".join([f"• {p}" for p in phones]) or "Not Available"
            wa = whatsapp_check(phones[0]) if phones else ""

            out += (
                f"\n<b>📊 Record #{i}</b>\n"
                f"👤 <b>Subject:</b> {name}\n"
                f"👨‍👦 <b>Lineage:</b> {father}\n\n"
                f"🏠 <b>Geolocation:</b>\n{address}\n\n"
                f"🗺 <b>Mapping:</b> <a href='{maps}'>Access</a>\n\n"
                f"🌐 <b>Region:</b> {region}\n\n"
                f"📞 <b>Telecom:</b>\n{phone_block}\n\n"
                f"💬 <b>WhatsApp:</b> <a href='{wa}'>Verify</a>\n\n"
                f"🧾 <b>Document:</b> {doc}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
    return out

def format_family(data):
    head = (
        "👨‍👩‍👧‍👦 <b>Family Network Intelligence Report</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏛️ <b>State Jurisdiction:</b> {data.get('homeStateName','N/A')}\n"
        f"📍 <b>Administrative District:</b> {data.get('homeDistName','N/A')}\n"
        f"🆔 <b>Family Registry ID:</b> {data.get('rcId','N/A')}\n"
        f"📦 <b>Government Scheme:</b> {data.get('schemeName','N/A')}\n\n"
    )

    body = ""
    for i, m in enumerate(data.get("memberDetailsList", []), 1):
        body += (
            f"{i}) 👤 <b>{m.get('memberName','N/A').title()}</b>\n"
            f"   ┗ 🔗 Kinship Relation: {m.get('releationship_name','N/A')}\n"
            f"   ┗ 🆔 Aadhaar Linked: {m.get('uid','N/A')}\n\n"
        )

    return head + body + "━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ================== SAFE SENDERS =====================

async def safe_reply(update, text, **kwargs):
    chat = update.message or (update.callback_query and update.callback_query.message)
    if chat:
        return await chat.reply_text(text, **kwargs)
    return None

async def safe_photo(update, photo, **kwargs):
    chat = update.message or (update.callback_query and update.callback_query.message)
    if chat:
        return await chat.reply_photo(photo, **kwargs)
    return None

async def log_to_channel(context, message):
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to log to channel: {e}")

# ================== COMMANDS =====================

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
        
        log_msg = (
            f"🆕 <b>New User Registration</b>\n\n"
            f"👤 User: {user.first_name} (@{user.username})\n"
            f"🆔 ID: {user.id}\n"
            f"📅 Joined: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🎁 Free Searches: {TRIAL_SEARCHES}"
        )
        if referral_code and referred_by:
            log_msg += f"\n🔗 Referred by: {referred_by_user['first_name']} (@{referred_by_user['username']})"
        
        await log_to_channel(context, log_msg)

    user_data = get_user(user.id)
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"

    welcome_text = (
        "🛡️ <b>PREMIUM OSINT INTELLIGENCE PLATFORM</b>\n\n"
        "Welcome to the most advanced digital intelligence gathering system. "
        "Our platform provides comprehensive data analysis and digital footprint mapping.\n\n"
        f"👤 <b>Welcome Agent:</b> {user.first_name}\n"
        f"🆔 <b>Clearance Level:</b> {user.id}\n"
        f"💳 <b>Operational Credits:</b> {user_data['balance']}\n"
        f"🎯 <b>Trial Operations:</b> {user_data['free_searches']} remaining\n\n"
        "<b>Select your intelligence operation:</b>"
    )
    
    await safe_reply(
        update,
        welcome_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Digital Footprint Analysis", callback_data="lookup")],
            [InlineKeyboardButton("👨‍👩‍👧‍👦 Family Network Mapping", callback_data="family")],
            [InlineKeyboardButton("🌐 Digital Surveillance", callback_data="track")],
            [
                InlineKeyboardButton("💳 Acquire Credits", callback_data="buy"),
                InlineKeyboardButton("💰 Credit Status", callback_data="balance")
            ],
            [
                InlineKeyboardButton("👥 Recruit Agent", callback_data="referral"),
                InlineKeyboardButton("📊 Operations Dashboard", callback_data="dashboard")
            ]
        ])
    )

async def getid(update: Update, context):
    chat = update.effective_chat
    user = update.effective_user
    
    message = (
        f"🆔 <b>CHAT ID INFORMATION</b>\n\n"
        f"👤 <b>Your User ID:</b> <code>{user.id}</code>\n"
        f"💬 <b>This Chat ID:</b> <code>{chat.id}</code>\n"
        f"📝 <b>Chat Type:</b> {chat.type}\n"
    )
    
    if chat.title:
        message += f"🏷️ <b>Chat Title:</b> {chat.title}\n"
    
    if str(chat.id).startswith('-100'):
        message += "\n🔹 <b>This is a Channel</b> (use for LOG_CHANNEL_ID)"
    elif str(chat.id).startswith('-'):
        message += "\n🔹 <b>This is a Group</b> (use for ADMIN_GROUP_ID)"
    else:
        message += "\n🔹 <b>This is a Private Chat</b>"
    
    await update.message.reply_text(message, parse_mode="HTML")

async def test_setup(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ Admin access required.")
    
    results = []
    
    try:
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text="🔧 <b>Test Message</b>\n\nLog channel configuration verified successfully! ✅",
            parse_mode="HTML"
        )
        results.append("📊 Log Channel: ✅ Working")
    except Exception as e:
        results.append(f"📊 Log Channel: ❌ Failed - {str(e)}")
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID, 
            text="🔧 <b>Test Message</b>\n\nAdmin group configuration verified successfully! ✅",
            parse_mode="HTML"
        )
        results.append("👥 Admin Group: ✅ Working")
    except Exception as e:
        results.append(f"👥 Admin Group: ❌ Failed - {str(e)}")
    
    result_msg = "🔧 <b>SETUP TEST RESULTS</b>\n\n" + "\n".join(results)
    
    if "❌" in result_msg:
        result_msg += "\n\n⚠️ <b>Check:</b>\n• Correct Chat IDs\n• Bot admin permissions\n• Environment variables"
    else:
        result_msg += "\n\n🎉 <b>All systems operational!</b>"
    
    await safe_reply(update, result_msg, parse_mode="HTML")

async def buy(update, context):
    await safe_photo(
        update,
        QR_IMAGE,
        caption=(
            "💳 <b>CREDIT ACQUISITION PORTAL</b>\n\n"
            "Upgrade your operational capacity with additional intelligence credits:\n\n"
            f"🔍 <b>Digital Footprint Scan:</b> ₹{COST_LOOKUP}\n"
            f"👪 <b>Family Network Analysis:</b> ₹{COST_FAMILY}\n"
            f"🌐 <b>Surveillance Operation:</b> ₹{COST_TRACK}\n\n"
            f"<b>Payment Gateway:</b>\n<code>{UPI_ID}</code>\n\n"
            "<i>Forward payment confirmation to command for credit activation.</i>"
        ),
        parse_mode="HTML"
    )

async def balance(update, context):
    uid = update.effective_user.id
    user_data = get_user(uid)
    
    if not user_data:
        create_user(uid, update.effective_user.username, update.effective_user.first_name)
        user_data = get_user(uid)

    status_msg = (
        "💰 <b>OPERATIONAL CREDIT STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Agent:</b> {user_data['first_name']}\n"
        f"🆔 <b>Clearance ID:</b> {uid}\n\n"
        f"💳 <b>Available Credits:</b> {user_data['balance']}\n"
        f"🎯 <b>Trial Operations:</b> {user_data['free_searches']}\n"
        f"📊 <b>Total Missions:</b> {user_data['total_searches']}\n\n"
        "<i>Maintain sufficient credits for uninterrupted operations.</i>"
    )
    await safe_reply(update, status_msg, parse_mode="HTML")

async def referral(update, context):
    uid = update.effective_user.id
    user_data = get_user(uid)
    
    if not user_data:
        create_user(uid, update.effective_user.username, update.effective_user.first_name)
        user_data = get_user(uid)

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"
    
    referral_msg = (
        "👥 <b>AGENT RECRUITMENT PROGRAM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Recruit new operatives and earn intelligence credits for each successful recruitment.\n\n"
        f"🔗 <b>Your Recruitment Link:</b>\n<code>{referral_link}</code>\n\n"
        f"🎁 <b>Recruitment Bonus:</b> {REFERRAL_BONUS} credits per agent\n\n"
        "<i>Share your recruitment link. When new agents join using your link, "
        "you'll receive bonus credits for enhancing our intelligence network.</i>"
    )
    await safe_reply(update, referral_msg, parse_mode="HTML")

async def dashboard(update, context):
    uid = update.effective_user.id
    user_data = get_user(uid)
    
    dashboard_msg = (
        "📊 <b>OPERATIONS DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Operative:</b> {user_data['first_name']}\n"
        f"🆔 <b>Agent ID:</b> {uid}\n\n"
        f"💳 <b>Credit Balance:</b> {user_data['balance']}\n"
        f"🎯 <b>Remaining Trials:</b> {user_data['free_searches']}\n"
        f"📈 <b>Total Missions:</b> {user_data['total_searches']}\n"
        f"🔗 <b>Recruitment Code:</b> {user_data['referral_code']}\n\n"
        "<i>Maintain operational readiness with adequate credits.</i>"
    )
    await safe_reply(update, dashboard_msg, parse_mode="HTML")

async def approve(update, context):
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ <b>Access Denied:</b> Insufficient clearance level.", parse_mode="HTML")
    
    try:
        args = context.args or []
        if len(args) != 2:
            return await safe_reply(update, "🛠 <b>Usage:</b> /approve [agent_id] [credit_amount]", parse_mode="HTML")
        
        uid = int(args[0])
        amt = int(args[1])
        
        user_data = get_user(uid)
        if not user_data:
            return await safe_reply(update, "❌ <b>Target Not Found:</b> Agent ID not registered.", parse_mode="HTML")
        
        update_balance(uid, amt)
        
        try:
            await context.bot.send_message(
                uid, 
                f"🎉 <b>CREDIT DEPOSIT CONFIRMED</b>\n\n"
                f"Your operational account has been credited with <b>{amt}</b> intelligence credits.\n"
                f"New balance: <b>{user_data['balance'] + amt}</b> credits.\n\n"
                f"<i>Proceed with your intelligence operations.</i>",
                parse_mode="HTML"
            )
        except:
            pass
        
        await safe_reply(update, f"✅ <b>Credit Transfer Complete:</b> {amt} credits added to agent {uid}.", parse_mode="HTML")
        
    except Exception as e:
        await safe_reply(update, f"❌ <b>System Error:</b> {e}\nUsage: /approve [agent_id] [credit_amount]", parse_mode="HTML")

async def broadcast_credits(update, context):
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ <b>Access Denied:</b> Command clearance required.", parse_mode="HTML")
    
    try:
        args = context.args or []
        if not args:
            return await safe_reply(update, "🛠 <b>Usage:</b> /broadcast [credit_amount]", parse_mode="HTML")
        
        amt = int(args[0])
        users = get_all_users()
        successful = 0
        failed = 0
        
        processing_msg = await safe_reply(update, f"🔄 <b>Initiating mass credit distribution...</b>", parse_mode="HTML")
        
        for user in users:
            try:
                update_balance(user[0], amt)
                await context.bot.send_message(
                    user[0],
                    f"🎉 <b>SYSTEM-WIDE CREDIT BONUS</b>\n\n"
                    f"You have received <b>+{amt}</b> intelligence credits as a system bonus.\n"
                    f"Continue your intelligence operations with enhanced capacity.",
                    parse_mode="HTML"
                )
                successful += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                failed += 1
                logger.error(f"Failed to send to user {user[0]}: {e}")
        
        await processing_msg.edit_text(
            f"✅ <b>Credit Distribution Complete</b>\n\n"
            f"📊 <b>Results:</b>\n"
            f"• Successful: {successful} agents\n"
            f"• Failed: {failed} agents\n"
            f"• Total Credits Distributed: {successful * amt}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await safe_reply(update, f"❌ <b>Distribution Error:</b> {e}", parse_mode="HTML")

async def button(update: Update, context):
    q = update.callback_query
    await q.answer()

    if q.data == "lookup":
        context.user_data["lookup"] = True
        return await safe_reply(update, "🔍 <b>DIGITAL FOOTPRINT ANALYSIS</b>\n\nEnter target phone number or email address for comprehensive scanning:", parse_mode="HTML")

    elif q.data == "family":
        context.user_data["family"] = True
        return await safe_reply(update, "👨‍👩‍👧‍👦 <b>FAMILY NETWORK MAPPING</b>\n\nEnter Family Registry ID for kinship analysis:", parse_mode="HTML")

    elif q.data == "track":
        context.user_data["track"] = True
        return await safe_reply(update, "🌐 <b>DIGITAL SURVEILLANCE</b>\n\nEnter target URL for tracking operation:", parse_mode="HTML")

    elif q.data == "buy":
        return await buy(update, context)

    elif q.data == "balance":
        return await balance(update, context)

    elif q.data == "referral":
        return await referral(update, context)

    elif q.data == "dashboard":
        return await dashboard(update, context)

# ================== MESSAGE HANDLER =====================

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

    if phone_auto or email_auto:
        context.user_data["lookup"] = True

    if context.user_data.pop("lookup", False):
        phone = normalize_phone(text)
        email = email_auto

        if not phone and not email:
            return await safe_reply(update, "❌ <b>Invalid Input:</b> Provide valid phone number or email address.", parse_mode="HTML")

        if user_data['balance'] <= 0 and user_data['free_searches'] <= 0:
            return await safe_reply(update, 
                "❌ <b>Insufficient Resources</b>\n\n"
                f"Required: {COST_LOOKUP} credits\n"
                f"Available: {user_data['balance']} credits, {user_data['free_searches']} trials\n\n"
                "Use /buy to acquire additional operational credits.",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 <b>Initiating Digital Footprint Analysis...</b>", parse_mode="HTML")

        try:
            if user_data['free_searches'] > 0:
                use_free_search(uid)
                cost_type = "Trial Operation"
            else:
                update_balance(uid, -COST_LOOKUP)
                cost_type = "Credit Operation"

            raw = leak_raw(phone if phone else email.group())
            
            log_search(uid, user.username, text, raw, "lookup")
            
            log_msg = (
                f"🔍 <b>Search Operation Logged</b>\n\n"
                f"👤 <b>Agent:</b> {user.first_name} (@{user.username})\n"
                f"🆔 <b>ID:</b> {uid}\n"
                f"🎯 <b>Target:</b> {text}\n"
                f"💳 <b>Operation Type:</b> {cost_type}\n"
                f"📅 <b>Timestamp:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"<code>Raw data logged to database</code>"
            )
            await log_to_channel(context, log_msg)

            if isinstance(raw, dict) and any(k in raw for k in ["FullName", "FatherName", "Address"]):
                msg = format_lookup(raw)
                for c in chunk(msg):
                    await safe_reply(update, c, parse_mode="HTML", disable_web_page_preview=True)
                return

            if "List" in raw:
                msg = format_list(raw)
                for c in chunk(msg):
                    await safe_reply(update, c, parse_mode="HTML", disable_web_page_preview=True)
                return

            pretty = "<pre>" + json.dumps(raw, indent=2, ensure_ascii=False) + "</pre>"
            for c in chunk(pretty):
                await safe_reply(update, c, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Lookup error for user {uid}: {e}")
            await safe_reply(update, f"❌ <b>Operation Failed:</b> {str(e)}", parse_mode="HTML")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass

    elif context.user_data.pop("family", False):
        if user_data['balance'] < COST_FAMILY:
            return await safe_reply(update, 
                f"❌ <b>Insufficient Credits:</b> {COST_FAMILY} required, {user_data['balance']} available.",
                parse_mode="HTML"
            )

        update_balance(uid, -COST_FAMILY)
        await safe_reply(update, "🔄 <b>Initiating Family Network Analysis...</b>", parse_mode="HTML")

        raw = family_raw(text)
        log_search(uid, user.username, text, raw, "family")

        if "memberDetailsList" in raw:
            msg = format_family(raw)
            for c in chunk(msg):
                await safe_reply(update, c, parse_mode="HTML")
        else:
            update_balance(uid, COST_FAMILY)
            await safe_reply(update, f"❌ <b>Analysis Failed:</b> {raw.get('error', 'No family data found')}", parse_mode="HTML")

    elif context.user_data.pop("track", False):
        if user_data['balance'] < COST_TRACK:
            return await safe_reply(update, 
                f"❌ <b>Insufficient Credits:</b> {COST_TRACK} required, {user_data['balance']} available.",
                parse_mode="HTML"
            )

        update_balance(uid, -COST_TRACK)
        link = make_tracking_link(uid, text)

        return await safe_reply(
            update,
            f"🌐 <b>SURVEILLANCE OPERATION INITIATED</b>\n\n"
            f"<b>Tracking Link Generated:</b>\n<code>{link}</code>\n\n"
            f"<i>Deploy this link to monitor target interactions. "
            f"You will receive intelligence reports on all engagements.</i>",
            parse_mode="HTML"
        )

    else:
        await safe_reply(update, "🛡️ <b>Access the command interface via /start</b>", parse_mode="HTML")

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
            logger.info(f"Webhook configured: {webhook_url}")
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
    telegram_app.add_handler(CommandHandler("getid", getid))
    telegram_app.add_handler(CommandHandler("testsetup", test_setup))
    telegram_app.add_handler(CommandHandler("buy", buy))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("referral", referral))
    telegram_app.add_handler(CommandHandler("dashboard", dashboard))
    telegram_app.add_handler(CommandHandler("approve", approve))
    telegram_app.add_handler(CommandHandler("broadcast", broadcast_credits))
    telegram_app.add_handler(CallbackQueryHandler(button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    admin_user = get_user(ADMIN_ID)
    if not admin_user:
        create_user(ADMIN_ID, "admin", "System Administrator")
        update_balance(ADMIN_ID, 1000)

    logger.info("🛡️ Premium OSINT Intelligence Platform Initialized")

    try:
        telegram_loop = start_telegram_background(telegram_app)
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port, debug=False)
    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        raise

if __name__ == "__main__":
    main()
