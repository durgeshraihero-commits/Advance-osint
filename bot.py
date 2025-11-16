# bot.py — Phone & Email Search Bot
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

# New API endpoints
IP_API = "http://ip-api.com/json/"
INSTAGRAM_API = "https://insta-profile-info-api.vercel.app/api/instagram.php?username="
IFSC_API = "https://encore.toxictanji0503.workers.dev/ifsc?id="
GST_API = "https://gstlookup.hideme.eu.org/?gstNumber="
VEHICLE_API = "https://encore.toxictanji0503.workers.dev/rcfuck?vehicle_number="

# Channel/Group IDs
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID", "-1003467393174")
ADMIN_GROUP_ID = os.environ.get("ADMIN_GROUP_ID", "-1003275777221")

LANG = "ru"
LIMIT = 100

ADMIN_USERNAME = "@itsmezigzagzozo"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6314556756"))

# Simplified credit system - 1 credit per search
COST_PER_SEARCH = 1

# Referral and bonus settings
REFERRAL_BONUS = 3  # Credits for referring someone
WELCOME_BONUS = 2   # Credits for new users

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
            credits INTEGER DEFAULT 2,
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

# New API functions
def ip_lookup(ip):
    try:
        r = requests.get(IP_API + ip, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def instagram_lookup(username):
    try:
        r = requests.get(INSTAGRAM_API + username, timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def ifsc_lookup(ifsc_code):
    try:
        r = requests.get(IFSC_API + ifsc_code, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def gst_lookup(gst_number):
    try:
        r = requests.get(GST_API + gst_number, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def vehicle_lookup(vehicle_number):
    try:
        r = requests.get(VEHICLE_API + vehicle_number, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# ================== RESULT CHECKERS =====================

def has_valid_data(data):
    """Check if the API response contains valid data (not 'No results found')"""
    if not data or data.get('error'):
        return False
    
    # Check for "No results found" in List
    if data.get('List'):
        for db_name, db_data in data['List'].items():
            if db_name == "No results found":
                return False
            # Check if Data contains actual records
            if db_data.get('Data') and len(db_data['Data']) > 0:
                # Check if first record is not empty
                first_record = db_data['Data'][0]
                if first_record and any(key not in ['', None] for key in first_record.values()):
                    return True
        return False
    
    # Check for direct record data
    if any(key in data for key in ['FullName', 'FatherName', 'Address', 'Phone', 'Email']):
        return True
    
    return False

def filter_no_results(data):
    """Remove 'No results found' entries from the data"""
    if not data or not data.get('List'):
        return data
    
    filtered_list = {}
    for db_name, db_data in data['List'].items():
        if db_name != "No results found":
            # Also filter out empty data arrays
            if db_data.get('Data') and len(db_data['Data']) > 0:
                # Filter out empty records
                non_empty_data = [record for record in db_data['Data'] if record and any(record.values())]
                if non_empty_data:
                    db_data['Data'] = non_empty_data
                    filtered_list[db_name] = db_data
    
    data['List'] = filtered_list
    data['NumOfDatabase'] = len(filtered_list)
    
    # Recalculate total results
    total_results = 0
    for db_data in filtered_list.values():
        total_results += db_data.get('NumOfResults', 0)
    data['NumOfResults'] = total_results
    
    return data

def remove_infoleak(data):
    """Remove InfoLeak field from the data"""
    if not data or not data.get('List'):
        return data
    
    cleaned_data = data.copy()
    
    # Remove InfoLeak from each database entry
    if 'List' in cleaned_data:
        for db_name, db_data in cleaned_data['List'].items():
            if 'InfoLeak' in db_data:
                del db_data['InfoLeak']
    
    return cleaned_data

# ================== SIMPLE FORMATTERS =====================

def swap_father_fullname(data):
    """Swap FatherName with FullName in the data"""
    if isinstance(data, dict):
        # Create a copy to avoid modifying original
        result = data.copy()
        
        # Swap the values if both keys exist
        if 'FatherName' in result and 'FullName' in result:
            father_name = result['FatherName']
            full_name = result['FullName']
            result['FatherName'] = full_name
            result['FullName'] = father_name
        
        # Recursively process nested dictionaries
        for key, value in result.items():
            result[key] = swap_father_fullname(value)
            
        return result
    
    elif isinstance(data, list):
        # Process each item in the list
        return [swap_father_fullname(item) for item in data]
    
    else:
        # Return unchanged for other data types
        return data

def format_raw_output(data):
    """Format raw API output with FatherName/FullName swap and InfoLeak removed"""
    # First remove InfoLeak
    cleaned_data = remove_infoleak(data)
    # Then swap the names
    swapped_data = swap_father_fullname(cleaned_data)
    
    # Convert to pretty JSON
    pretty_json = json.dumps(swapped_data, indent=2, ensure_ascii=False)
    
    return f"<pre>{pretty_json}</pre>"

def format_family_raw(data):
    """Format family API raw output"""
    pretty_json = json.dumps(data, indent=2, ensure_ascii=False)
    return f"<pre>{pretty_json}</pre>"

# New formatters for additional services
def format_ip_info(data):
    """Format IP location information"""
    if data.get('status') == 'success':
        formatted = (
            f"🌐 <b>IP Location Information</b>\n\n"
            f"📍 <b>IP Address:</b> {data.get('query', 'N/A')}\n"
            f"🏙️ <b>City:</b> {data.get('city', 'N/A')}\n"
            f"🏛️ <b>Region:</b> {data.get('regionName', 'N/A')}\n"
            f"🇮🇳 <b>Country:</b> {data.get('country', 'N/A')} ({data.get('countryCode', 'N/A')})\n"
            f"📮 <b>ZIP:</b> {data.get('zip', 'N/A')}\n"
            f"📍 <b>Latitude:</b> {data.get('lat', 'N/A')}\n"
            f"📍 <b>Longitude:</b> {data.get('lon', 'N/A')}\n"
            f"⏰ <b>Timezone:</b> {data.get('timezone', 'N/A')}\n"
            f"🏢 <b>ISP:</b> {data.get('isp', 'N/A')}\n"
            f"🏢 <b>Organization:</b> {data.get('org', 'N/A')}\n"
            f"🛜 <b>AS:</b> {data.get('as', 'N/A')}"
        )
        return formatted
    else:
        return "❌ Unable to fetch IP location information."

def format_instagram_info(data):
    """Format Instagram profile information"""
    if data and not data.get('error'):
        formatted = (
            f"📷 <b>Instagram Profile</b>\n\n"
            f"👤 <b>Username:</b> {data.get('username', 'N/A')}\n"
            f"📛 <b>Full Name:</b> {data.get('full_name', 'N/A')}\n"
            f"📝 <b>Bio:</b> {data.get('biography', 'N/A')}\n"
            f"🔗 <b>External URL:</b> {data.get('external_url', 'N/A')}\n"
            f"👥 <b>Followers:</b> {data.get('edge_followed_by', {}).get('count', 'N/A')}\n"
            f"👥 <b>Following:</b> {data.get('edge_follow', {}).get('count', 'N/A')}\n"
            f"📸 <b>Posts:</b> {data.get('edge_owner_to_timeline_media', {}).get('count', 'N/A')}\n"
            f"🔒 <b>Private:</b> {'Yes' if data.get('is_private') else 'No'}\n"
            f"✅ <b>Verified:</b> {'Yes' if data.get('is_verified') else 'No'}"
        )
        return formatted
    else:
        return "❌ Unable to fetch Instagram profile information."

def format_ifsc_info(data):
    """Format IFSC code information"""
    if data and not data.get('error'):
        formatted = (
            f"🏦 <b>IFSC Code Information</b>\n\n"
            f"🏛️ <b>Bank:</b> {data.get('BANK', 'N/A')}\n"
            f"🏢 <b>Branch:</b> {data.get('BRANCH', 'N/A')}\n"
            f"📍 <b>Address:</b> {data.get('ADDRESS', 'N/A')}\n"
            f"🏙️ <b>City:</b> {data.get('CITY', 'N/A')}\n"
            f"📮 <b>District:</b> {data.get('DISTRICT', 'N/A')}\n"
            f"🏛️ <b>State:</b> {data.get('STATE', 'N/A')}\n"
            f"📞 <b>Contact:</b> {data.get('CONTACT', 'N/A')}\n"
            f"🆔 <b>IFSC:</b> {data.get('IFSC', 'N/A')}\n"
            f"🏛️ <b>MICR:</b> {data.get('MICR', 'N/A')}"
        )
        return formatted
    else:
        return "❌ Unable to fetch IFSC code information."

def format_gst_info(data):
    """Format GST information"""
    if data and not data.get('error'):
        formatted = (
            f"🧾 <b>GST Information</b>\n\n"
            f"🏢 <b>Business Name:</b> {data.get('tradeNam', 'N/A')}\n"
            f"👤 <b>Legal Name:</b> {data.get('lgnm', 'N/A')}\n"
            f"🆔 <b>GST Number:</b> {data.get('gstNo', 'N/A')}\n"
            f"📅 <b>Registration Date:</b> {data.get('rgdt', 'N/A')}\n"
            f"🏢 <b>Business Type:</b> {data.get('ctb', 'N/A')}\n"
            f"📍 <b>State:</b> {data.get('stj', 'N/A')}\n"
            f"🏙️ <b>Jurisdiction:</b> {data.get('ctj', 'N/A')}\n"
            f"📊 <b>Status:</b> {data.get('sts', 'N/A')}"
        )
        return formatted
    else:
        return "❌ Unable to fetch GST information."

def format_vehicle_info(data):
    """Format vehicle information"""
    if data and not data.get('error'):
        formatted = (
            f"🚗 <b>Vehicle Information</b>\n\n"
            f"🆔 <b>Registration Number:</b> {data.get('regn_no', 'N/A')}\n"
            f"👤 <b>Owner Name:</b> {data.get('owner_name', 'N/A')}\n"
            f"🏠 <b>Address:</b> {data.get('present_address', 'N/A')}\n"
            f"🚗 <b>Vehicle Class:</b> {data.get('vehicle_class', 'N/A')}\n"
            f"🏭 <b>Manufacturer:</b> {data.get('maker_model', 'N/A')}\n"
            f"🏭 <b>Model:</b> {data.get('vehicle_type', 'N/A')}\n"
            f"🎨 <b>Color:</b> {data.get('color', 'N/A')}\n"
            f"📅 <b>Registration Date:</b> {data.get('regn_date', 'N/A')}\n"
            f"📅 <b>Expiry Date:</b> {data.get('expiry_date', 'N/A')}\n"
            f"🆔 <b>Chassis Number:</b> {data.get('chasi_no', 'N/A')}\n"
            f"🛞 <b>Engine Number:</b> {data.get('engine_no', 'N/A')}\n"
            f"⛽ <b>Fuel Type:</b> {data.get('fuel_type', 'N/A')}"
        )
        return formatted
    else:
        return "❌ Unable to fetch vehicle information."

# ================== SAFE SENDERS =====================

async def safe_reply(update, text, **kwargs):
    chat = update.message or (update.callback_query and update.callback_query.message)
    if chat:
        return await chat.reply_text(text, **kwargs)
    return None

async def log_search_to_group(context, user_info, input_query, output_data, search_type, success=True):
    """Log search details to the admin group - only for successful searches"""
    if not success:
        return  # Don't log failed searches
        
    try:
        log_message = (
            f"🔍 <b>NEW SEARCH REQUEST</b>\n"
            "────────────────────\n\n"
            f"👤 <b>User:</b> {user_info['first_name']}\n"
            f"📱 <b>Username:</b> @{user_info['username']}\n"
            f"🆔 <b>User ID:</b> {user_info['user_id']}\n\n"
            f"🔎 <b>Search Type:</b> {search_type}\n"
            f"📥 <b>Input:</b> {input_query}\n"
            f"📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📋 <b>Results Found:</b> {len(output_data) if isinstance(output_data, list) else 'Single record'}\n"
            "────────────────────"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=log_message,
            parse_mode="HTML"
        )
        
        # Also send the actual output data (with InfoLeak removed)
        if output_data:
            # Remove InfoLeak before sending to admin group
            cleaned_output = remove_infoleak(output_data)
            output_preview = json.dumps(cleaned_output, indent=2, ensure_ascii=False)
            if len(output_preview) > 3000:
                output_preview = output_preview[:3000] + "..."
            
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"<code>{output_preview}</code>",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Failed to log to admin group: {e}")

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
        
        # Log new user to admin group
        try:
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"🆕 <b>NEW USER JOINED</b>\n\n👤 {user.first_name} (@{user.username})\n🆔 {user.id}\n🎁 Got {WELCOME_BONUS} free credits\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to log new user: {e}")

    user_data = get_user(user.id)
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"

    welcome_text = (
        "🔍 <b>Advanced OSINT Search Bot</b>\n\n"
        "Find information using various search methods.\n\n"
        f"👋 Welcome <b>{user.first_name}</b>!\n"
        f"💰 <b>Your Credits:</b> {user_data['credits']}\n"
        f"🔍 <b>Cost per search:</b> 1 credit\n\n"
        "<b>Choose what you want to search:</b>"
    )
    
    await safe_reply(
        update,
        welcome_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 Phone Number Search", callback_data="lookup")],
            [InlineKeyboardButton("📧 Email Address Search", callback_data="lookup")],
            [InlineKeyboardButton("👪 Family Members Search", callback_data="family")],
            [InlineKeyboardButton("🌐 IP Location", callback_data="ip_lookup")],
            [InlineKeyboardButton("📷 Instagram Profile", callback_data="instagram_lookup")],
            [InlineKeyboardButton("🏦 IFSC Code", callback_data="ifsc_lookup")],
            [InlineKeyboardButton("🧾 GST Information", callback_data="gst_lookup")],
            [InlineKeyboardButton("🚗 Vehicle Info", callback_data="vehicle_lookup")],
            [
                InlineKeyboardButton("💰 Buy Credits", callback_data="buy"),
                InlineKeyboardButton("👥 Refer & Earn", callback_data="referral")
            ],
            [InlineKeyboardButton("📊 My Account", callback_data="dashboard")]
        ])
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
            [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME[1:]}")]
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
        f"👤 <b>Name:</b> {user_data['first_name']}\n"
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

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"
    
    referral_msg = (
        "👥 <b>Refer & Earn</b>\n"
        "────────────────────\n\n"
        "Share your referral link and earn credits when friends join!\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{referral_link}</code>\n\n"
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
        f"👤 <b>Name:</b> {user_data['first_name']}\n"
        f"🆔 <b>User ID:</b> {uid}\n\n"
        f"💳 <b>Credits:</b> {user_data['credits']}\n"
        f"🔍 <b>Total Searches:</b> {user_data['total_searches']}\n"
        f"🔗 <b>Referral Code:</b> {user_data['referral_code']}\n\n"
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

async def button(update: Update, context):
    q = update.callback_query
    await q.answer()

    if q.data == "lookup":
        context.user_data["lookup"] = True
        return await safe_reply(update, "🔍 <b>Phone/Email Search</b>\n\nEnter a phone number or email address to search:", parse_mode="HTML")

    elif q.data == "family":
        context.user_data["family"] = True
        return await safe_reply(update, "👪 <b>Family Search</b>\n\nEnter Family ID to find family members:", parse_mode="HTML")

    elif q.data == "ip_lookup":
        context.user_data["ip_lookup"] = True
        return await safe_reply(update, "🌐 <b>IP Location Lookup</b>\n\nEnter an IP address to get location information:", parse_mode="HTML")

    elif q.data == "instagram_lookup":
        context.user_data["instagram_lookup"] = True
        return await safe_reply(update, "📷 <b>Instagram Profile Lookup</b>\n\nEnter Instagram username to get profile information:", parse_mode="HTML")

    elif q.data == "ifsc_lookup":
        context.user_data["ifsc_lookup"] = True
        return await safe_reply(update, "🏦 <b>IFSC Code Lookup</b>\n\nEnter IFSC code to get bank details:", parse_mode="HTML")

    elif q.data == "gst_lookup":
        context.user_data["gst_lookup"] = True
        return await safe_reply(update, "🧾 <b>GST Information Lookup</b>\n\nEnter GST number to get business details:", parse_mode="HTML")

    elif q.data == "vehicle_lookup":
        context.user_data["vehicle_lookup"] = True
        return await safe_reply(update, "🚗 <b>Vehicle Information Lookup</b>\n\nEnter vehicle registration number to get vehicle details:", parse_mode="HTML")

    elif q.data == "buy":
        return await buy(update, context)

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

    # Check for auto-detection of phone/email
    phone_auto = normalize_phone(text)
    email_auto = re.fullmatch(r"[\w.-]+@[\w.-]+\.\w+", text)

    if phone_auto or email_auto:
        context.user_data["lookup"] = True

    # Handle different search types
    if context.user_data.pop("lookup", False):
        phone = normalize_phone(text)
        email = email_auto

        if not phone and not email:
            return await safe_reply(update, "❌ Please enter a valid phone number or email address.")

        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need 1 credit to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Searching... Please wait")

        try:
            use_credit(uid)
            # SINGLE API CALL - store the result
            raw_data = leak_raw(phone if phone else email.group())
            
            # Check if we have valid data (not "No results found")
            if has_valid_data(raw_data):
                # Filter out "No results found" entries and remove InfoLeak
                filtered_data = filter_no_results(raw_data)
                cleaned_data = remove_infoleak(filtered_data)
                
                # Log to database
                log_search(uid, user.username, text, cleaned_data, "lookup")
                
                # Log to admin group with full details (only for successful searches)
                user_info = {
                    'user_id': uid,
                    'username': user.username,
                    'first_name': user.first_name
                }
                await log_search_to_group(context, user_info, text, cleaned_data, "Phone/Email Search", success=True)
                
                # Send raw output with FatherName/FullName swap and InfoLeak removed
                formatted_output = format_raw_output(cleaned_data)
                for chunk_text in chunk(formatted_output, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                # No valid data found - return credit and don't log
                update_credits(uid, COST_PER_SEARCH)  # Return the credit
                await safe_reply(update, "❌ No information found for this search. Your credit has been returned. ✅")
                # Don't log to admin group for failed searches

        except Exception as e:
            logger.error(f"Search error: {e}")
            update_credits(uid, COST_PER_SEARCH)  # Return credit on error
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass

    elif context.user_data.pop("family", False):
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need 1 credit to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Searching family information...")

        try:
            use_credit(uid)
            # SINGLE API CALL - store the result
            raw_data = family_raw(text)
            
            # Check if we have valid family data
            if raw_data and "memberDetailsList" in raw_data and raw_data["memberDetailsList"]:
                # Log to database
                log_search(uid, user.username, text, raw_data, "family")

                # Log to admin group with full details (only for successful searches)
                user_info = {
                    'user_id': uid,
                    'username': user.username,
                    'first_name': user.first_name
                }
                await log_search_to_group(context, user_info, text, raw_data, "Family Search", success=True)

                # Send raw family output
                formatted_output = format_family_raw(raw_data)
                for chunk_text in chunk(formatted_output, 4000):
                    await safe_reply(update, chunk_text, parse_mode="HTML")
            else:
                # No valid family data found - return credit and don't log
                update_credits(uid, COST_PER_SEARCH)  # Return the credit
                await safe_reply(update, "❌ No family information found. Your credit has been returned. ✅")
                # Don't log to admin group for failed searches

        except Exception as e:
            logger.error(f"Family search error: {e}")
            update_credits(uid, COST_PER_SEARCH)  # Return credit on error
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass

    # New search handlers
    elif context.user_data.pop("ip_lookup", False):
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need 1 credit to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Looking up IP location...")

        try:
            use_credit(uid)
            raw_data = ip_lookup(text)
            
            if raw_data and raw_data.get('status') == 'success':
                # Log to database
                log_search(uid, user.username, text, raw_data, "ip_lookup")
                
                # Log to admin group
                user_info = {
                    'user_id': uid,
                    'username': user.username,
                    'first_name': user.first_name
                }
                await log_search_to_group(context, user_info, text, raw_data, "IP Lookup", success=True)
                
                # Send formatted output
                formatted_output = format_ip_info(raw_data)
                await safe_reply(update, formatted_output, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "❌ Unable to fetch IP location information. Your credit has been returned. ✅")

        except Exception as e:
            logger.error(f"IP lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass

    elif context.user_data.pop("instagram_lookup", False):
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need 1 credit to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Fetching Instagram profile...")

        try:
            use_credit(uid)
            raw_data = instagram_lookup(text)
            
            if raw_data and not raw_data.get('error'):
                # Log to database
                log_search(uid, user.username, text, raw_data, "instagram_lookup")
                
                # Log to admin group
                user_info = {
                    'user_id': uid,
                    'username': user.username,
                    'first_name': user.first_name
                }
                await log_search_to_group(context, user_info, text, raw_data, "IFSC Lookup", success=True)
                
                # Send formatted output
                formatted_output = format_ifsc_info(raw_data)
                await safe_reply(update, formatted_output, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "❌ Unable to fetch IFSC information. Your credit has been returned. ✅")

        except Exception as e:
            logger.error(f"IFSC lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass

    elif context.user_data.pop("gst_lookup", False):
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need 1 credit to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Fetching GST information...")

        try:
            use_credit(uid)
            raw_data = gst_lookup(text)
            
            if raw_data and not raw_data.get('error'):
                # Log to database
                log_search(uid, user.username, text, raw_data, "gst_lookup")
                
                # Log to admin group
                user_info = {
                    'user_id': uid,
                    'username': user.username,
                    'first_name': user.first_name
                }
                await log_search_to_group(context, user_info, text, raw_data, "GST Lookup", success=True)
                
                # Send formatted output
                formatted_output = format_gst_info(raw_data)
                await safe_reply(update, formatted_output, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "❌ Unable to fetch GST information. Your credit has been returned. ✅")

        except Exception as e:
            logger.error(f"GST lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass

    elif context.user_data.pop("vehicle_lookup", False):
        if user_data['credits'] < COST_PER_SEARCH:
            return await safe_reply(update, 
                "❌ <b>Not enough credits</b>\n\n"
                f"You need 1 credit to search\n"
                f"You have: {user_data['credits']} credits\n\n"
                "Use /buy to get more credits",
                parse_mode="HTML"
            )

        processing_msg = await safe_reply(update, "🔄 Fetching vehicle information...")

        try:
            use_credit(uid)
            raw_data = vehicle_lookup(text)
            
            if raw_data and not raw_data.get('error'):
                # Log to database
                log_search(uid, user.username, text, raw_data, "vehicle_lookup")
                
                # Log to admin group
                user_info = {
                    'user_id': uid,
                    'username': user.username,
                    'first_name': user.first_name
                }
                await log_search_to_group(context, user_info, text, raw_data, "Vehicle Lookup", success=True)
                
                # Send formatted output
                formatted_output = format_vehicle_info(raw_data)
                await safe_reply(update, formatted_output, parse_mode="HTML")
            else:
                update_credits(uid, COST_PER_SEARCH)
                await safe_reply(update, "❌ Unable to fetch vehicle information. Your credit has been returned. ✅")

        except Exception as e:
            logger.error(f"Vehicle lookup error: {e}")
            update_credits(uid, COST_PER_SEARCH)
            await safe_reply(update, "❌ Search failed. Please try again. Your credit has been returned. ✅")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass

    else:
        await safe_reply(update, "👋 Use the menu buttons to start searching!")

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

    logger.info("🔍 Advanced OSINT Search Bot Started")

    try:
        telegram_loop = start_telegram_background(telegram_app)
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port, debug=False)
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

if __name__ == "__main__":
    main()
           
