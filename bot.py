# bot.py — PTB v20.3 + Flask + Render (Improved Version)
import os
import re
import json
import logging
import urllib.parse
import requests
import asyncio
import threading
import time
import random
from collections import defaultdict
from flask import Flask, request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

# Multiple API endpoints for fallback
API_KEYS = os.environ.get("API_KEYS", "5785818477:QqPj82nd").split(",")
LEAK_APIS = [
    "https://leakosintapi.com/",
    "https://api.leakcheck.io/",
    "https://leakcheck.net/api/",
]

FAMILY_API = os.environ.get("FAMILY_API", "https://encore.toxictanji0503.workers.dev/family?id=")

# Proxy configuration (optional)
PROXY_URL = os.environ.get("PROXY_URL")  # e.g., "http://user:pass@proxy:port"

LANG = "ru"
LIMIT = 300

UPI_ID = "durgeshraihero@oksbi"
QR_IMAGE = "https://i.ibb.co/S6nfK15/upi.jpg"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6314556756"))

COST_LOOKUP = 50
COST_FAMILY = 20
COST_TRACK = 10

RENDER_LINK = os.environ.get("RENDER_LINK", "https://jsjs-kzua.onrender.com")

# User management
user_balances = {}
last_request_time = defaultdict(float)
user_request_count = defaultdict(int)
REQUEST_COOLDOWN = 15  # seconds between requests
DAILY_LIMIT = 50  # max requests per user per day

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================== FLASK APP =====================

app = Flask(__name__)
telegram_app = None
telegram_loop = None

@app.route("/")
def home():
    return "🚀 Advanced OSINT Bot - Running Smoothly"

@app.route("/health")
def health():
    return json.dumps({"status": "healthy", "timestamp": time.time()})

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive Telegram update from webhook and forward to PTB loop."""
    global telegram_app, telegram_loop
    if telegram_app is None or telegram_loop is None:
        return "Bot not ready", 503

    try:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        future = asyncio.run_coroutine_threadsafe(
            telegram_app.process_update(update), telegram_loop
        )
        future.result(timeout=10)  # Wait for processing
        return "OK"
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "OK", 200

# ================== ENHANCED HELPERS =====================

def create_session_with_retries():
    """Create requests session with retry strategy."""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=100, pool_maxsize=100)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set headers to mimic browser
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })
    
    # Add proxy if configured
    if PROXY_URL:
        session.proxies = {
            "http": PROXY_URL,
            "https": PROXY_URL,
        }
    
    return session

def chunk(text, size=3500):
    """Split long messages into chunks."""
    return [text[i:i + size] for i in range(0, len(text), size)]

def normalize_phone(txt):
    """Normalize phone number to international format."""
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
    """Generate Google Maps link."""
    return "https://www.google.com/maps/search/" + urllib.parse.quote(address or "")

def whatsapp_check(number):
    """Generate WhatsApp link."""
    return f"https://wa.me/{number.replace('+','')}" if number else ""

def make_tracking_link(uid, site):
    """Generate tracking link."""
    return f"{RENDER_LINK}/?chat_id={uid}&site={urllib.parse.quote(site)}"

def can_make_request(user_id):
    """Check if user can make request (rate limiting)."""
    current_time = time.time()
    
    # Reset daily counter if new day
    if current_time - last_request_time.get(user_id, 0) > 86400:
        user_request_count[user_id] = 0
    
    # Check cooldown
    if current_time - last_request_time.get(user_id, 0) < REQUEST_COOLDOWN:
        return False, f"⏳ Please wait {int(REQUEST_COOLDOWN - (current_time - last_request_time[user_id]))} seconds before next request."
    
    # Check daily limit
    if user_request_count.get(user_id, 0) >= DAILY_LIMIT:
        return False, "❌ Daily request limit reached. Try again tomorrow."
    
    # Update counters
    last_request_time[user_id] = current_time
    user_request_count[user_id] = user_request_count.get(user_id, 0) + 1
    
    return True, ""

# ================== ENHANCED API CALLS =====================

def leak_raw(query):
    """Make API request with fallback and retry logic."""
    session = create_session_with_retries()
    
    # Rotate APIs for load balancing
    apis = LEAK_APIS.copy()
    random.shuffle(apis)
    
    for api_url in apis:
        for api_key in API_KEYS:
            try:
                logger.info(f"Trying API: {api_url} with key: {api_key[:10]}...")
                
                payload = {
                    "token": api_key.strip(),
                    "request": query,
                    "limit": LIMIT,
                    "lang": LANG
                }
                
                response = session.post(
                    api_url,
                    json=payload,
                    timeout=25,
                    verify=True  # SSL verification
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Check if API returned valid data (not blocked)
                    if isinstance(result, dict) and not result.get('error'):
                        logger.info(f"API success from {api_url}")
                        return result
                    elif 'blocked' not in str(result.get('error', '')).lower():
                        logger.info(f"API returned data from {api_url}")
                        return result
                    else:
                        logger.warning(f"API blocked from {api_url}: {result.get('error')}")
                        continue
                
                elif response.status_code == 429:  # Rate limited
                    logger.warning(f"Rate limited by {api_url}")
                    time.sleep(2)  # Brief pause before next try
                    continue
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout with {api_url}")
                continue
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error with {api_url}")
                continue
            except Exception as e:
                logger.error(f"Error with {api_url}: {e}")
                continue
    
    return {"error": "All API endpoints failed or are temporarily unavailable. Please try again in a few minutes."}

def family_raw(fid):
    """Fetch family information with enhanced error handling."""
    try:
        session = create_session_with_retries()
        response = session.get(FAMILY_API + fid, timeout=20)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned status code: {response.status_code}"}
    except Exception as e:
        return {"error": f"Family API error: {str(e)}"}

# ================== IMPROVED FORMATTERS =====================

def format_lookup(entry):
    """Format single lookup result."""
    name = (entry.get("FatherName") or entry.get("FullName") or "N/A").title()
    father = (entry.get("FullName") or entry.get("FatherName") or "N/A").title()

    address = entry.get("Address", "") or entry.get("address", "")
    maps = google_maps_link(address)
    region = (entry.get("Region", "") or entry.get("region", "")).replace(";", " / ")
    doc = entry.get("DocNumber", "N/A")

    phones = []
    for k, v in entry.items():
        if "phone" in k.lower() and v and str(v).strip():
            p = str(v).strip()
            if len(p) == 10 and p.isdigit():
                p = "+91" + p
            phones.append(p)

    phone_block = "\n".join([f"• {p}" for p in phones[:5]]) or "Not Available"
    wa = whatsapp_check(phones[0]) if phones else ""

    return (
        "📱 <b>Phone Intelligence Report</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Name:</b> {name}\n"
        f"👨‍👦 <b>Father's Name:</b> {father}\n\n"
        f"🏠 <b>Address:</b>\n{address[:200]}{'...' if len(address) > 200 else ''}\n\n"
        f"🗺 <b>Maps:</b> <a href='{maps}'>Open Location</a>\n\n"
        f"🌐 <b>Region:</b> {region}\n\n"
        f"📞 <b>Linked Numbers:</b>\n{phone_block}\n\n"
        f"💬 <b>WhatsApp:</b> <a href='{wa}'>Check WhatsApp</a>\n\n"
        f"🧾 <b>Document:</b> {doc}\n"
        "━━━━━━━━━━━━━━━━━━"
    )

def format_list(raw):
    """Format multiple results."""
    if not raw.get("List"):
        return "❌ No data found in the response."
    
    out = "📱 <b>Phone Intelligence Report</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    
    for db_name, block in raw.get("List", {}).items():
        out += f"🗂 <b>Database:</b> {db_name}\n"
        
        for i, entry in enumerate(block.get("Data", [])[:10], 1):  # Limit to 10 records
            name = (entry.get("FatherName") or entry.get("FullName") or "N/A").title()
            father = (entry.get("FullName") or entry.get("FatherName") or "N/A").title()
            address = entry.get("Address", "")
            region = (entry.get("Region", "") or "").replace(";", " / ")
            maps = google_maps_link(address)
            doc = entry.get("DocNumber", "N/A")

            phones = []
            for k, v in entry.items():
                if "phone" in k.lower() and v and str(v).strip():
                    p = str(v).strip()
                    if len(p) == 10 and p.isdigit():
                        p = "+91" + p
                    phones.append(p)

            phone_block = "\n".join([f"• {p}" for p in phones[:3]]) or "Not Available"
            wa = whatsapp_check(phones[0]) if phones else ""

            out += (
                f"\n<b>{i}) Record</b>\n"
                f"👤 <b>Name:</b> {name}\n"
                f"👨‍👦 <b>Father:</b> {father}\n\n"
                f"🏠 <b>Address:</b>\n{address[:150]}{'...' if len(address) > 150 else ''}\n\n"
                f"🗺 <b>Maps:</b> <a href='{maps}'>Open</a>\n\n"
                f"🌐 <b>Region:</b> {region}\n\n"
                f"📞 <b>Phones:</b>\n{phone_block}\n\n"
                f"💬 <b>WhatsApp:</b> <a href='{wa}'>Check</a>\n\n"
                f"🧾 <b>Document:</b> {doc}\n"
                "━━━━━━━━━━━━━━━━━━\n"
            )
    
    if len(block.get("Data", [])) > 10:
        out += f"\n📋 ... and {len(block.get('Data', [])) - 10} more records\n"
    
    return out

def format_family(data):
    """Format family information."""
    if "error" in data:
        return f"❌ Error fetching family data: {data['error']}"
    
    if not data.get("memberDetailsList"):
        return "❌ No family data found for the provided ID."
    
    head = (
        "👨‍👩‍👧‍👦 <b>Family Intelligence Report</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🏠 <b>State:</b> {data.get('homeStateName','N/A')}\n"
        f"📍 <b>District:</b> {data.get('homeDistName','N/A')}\n"
        f"🆔 <b>Ration Card:</b> {data.get('rcId','N/A')}\n"
        f"📦 <b>Scheme:</b> {data.get('schemeName','N/A')}\n\n"
    )

    body = ""
    for i, m in enumerate(data.get("memberDetailsList", []), 1):
        body += (
            f"{i}) 👤 <b>{m.get('memberName','N/A').title()}</b>\n"
            f"   ┗ 🔗 Relation: {m.get('releationship_name','N/A')}\n"
            f"   ┗ 🆔 UID Linked: {m.get('uid','N/A')}\n\n"
        )

    return head + body + "━━━━━━━━━━━━━━━━━━"

# ================== SAFE SENDERS =====================

async def safe_reply(update, text, **kwargs):
    """Safely send reply with error handling."""
    try:
        chat = update.message or (update.callback_query and update.callback_query.message)
        if chat:
            return await chat.reply_text(text, **kwargs)
        else:
            logger.warning("safe_reply: no chat found for update")
            return None
    except Exception as e:
        logger.error(f"Error in safe_reply: {e}")
        return None

async def safe_photo(update, photo, **kwargs):
    """Safely send photo with error handling."""
    try:
        chat = update.message or (update.callback_query and update.callback_query.message)
        if chat:
            return await chat.reply_photo(photo, **kwargs)
        else:
            logger.warning("safe_photo: no chat found for update")
            return None
    except Exception as e:
        logger.error(f"Error in safe_photo: {e}")
        return None

# ================== ENHANCED COMMANDS =====================

async def start(update: Update, context):
    """Enhanced start command with user info."""
    user = update.effective_user
    welcome_text = (
        f"👋 <b>Welcome {user.first_name}!</b>\n\n"
        "🔍 <i>Premium OSINT Intelligence Bot</i>\n\n"
        "Choose an option below:"
    )
    
    await safe_reply(
        update,
        welcome_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Phone/Email Lookup", callback_data="lookup")],
            [InlineKeyboardButton("👪 Family Info", callback_data="family")],
            [InlineKeyboardButton("🌍 Track Website", callback_data="track")],
            [
                InlineKeyboardButton("💳 Add Balance", callback_data="buy"),
                InlineKeyboardButton("💰 Check Balance", callback_data="balance")
            ],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        ])
    )

async def buy(update, context):
    """Buy credits command."""
    await safe_photo(
        update,
        QR_IMAGE,
        caption=(
            "💳 <b>Recharge Credits</b>\n\n"
            f"🔍 Lookup: ₹{COST_LOOKUP}\n"
            f"👪 Family: ₹{COST_FAMILY}\n" 
            f"🌍 Track: ₹{COST_TRACK}\n\n"
            f"<b>UPI ID:</b> <code>{UPI_ID}</code>\n\n"
            "After payment, send screenshot to admin for approval."
        ),
        parse_mode="HTML"
    )

async def balance(update, context):
    """Check balance with request stats."""
    uid = update.effective_user.id
    bal = user_balances.get(uid, 0)
    requests_today = user_request_count.get(uid, 0)
    
    message = (
        f"💰 <b>Balance:</b> {bal} credits\n"
        f"📊 <b>Requests today:</b> {requests_today}/{DAILY_LIMIT}\n"
        f"⏰ <b>Cooldown:</b> {REQUEST_COOLDOWN}s\n\n"
        "Use /buy to add more credits."
    )
    await safe_reply(update, message, parse_mode="HTML")

async def stats(update, context):
    """Show user statistics."""
    uid = update.effective_user.id
    requests_today = user_request_count.get(uid, 0)
    last_request = last_request_time.get(uid, 0)
    time_since_last = time.time() - last_request if last_request else None
    
    stats_text = (
        "📊 <b>Your Statistics</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>User ID:</b> {uid}\n"
        f"💰 <b>Balance:</b> {user_balances.get(uid, 0)} credits\n"
        f"📨 <b>Requests Today:</b> {requests_today}/{DAILY_LIMIT}\n"
        f"⏰ <b>Cooldown:</b> {REQUEST_COOLDOWN} seconds\n"
    )
    
    if time_since_last:
        if time_since_last < REQUEST_COOLDOWN:
            stats_text += f"🕒 <b>Next Request In:</b> {int(REQUEST_COOLDOWN - time_since_last)}s\n"
        else:
            stats_text += "✅ <b>Ready for next request</b>\n"
    
    await safe_reply(update, stats_text, parse_mode="HTML")

async def approve(update, context):
    """Admin command to approve payments."""
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ Unauthorized.")
    
    try:
        args = context.args
        if len(args) != 2:
            return await safe_reply(update, "Usage: /approve <user_id> <amount>")
        
        uid = int(args[0])
        amt = int(args[1])
        
        user_balances[uid] = user_balances.get(uid, 0) + amt
        
        # Notify user if possible
        try:
            await context.bot.send_message(
                uid, 
                f"✅ Payment approved! {amt} credits added to your account.\n"
                f"New balance: {user_balances[uid]} credits."
            )
        except:
            pass  # User might have blocked the bot
        
        await safe_reply(update, f"✅ Added {amt} credits to user {uid}")
        
    except Exception as e:
        await safe_reply(update, f"❌ Error: {e}\nUsage: /approve <user_id> <amount>")

async def apistatus(update, context):
    """Check API status (admin only)."""
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ Unauthorized.")
    
    test_queries = ["+911234567890", "test@example.com"]
    status_results = []
    
    for query in test_queries:
        result = leak_raw(query)
        status = "✅ Working" if not result.get('error') else f"❌ {result.get('error')}"
        status_results.append(f"Query '{query}': {status}")
    
    status_msg = "🔍 <b>API Status Check</b>\n\n" + "\n".join(status_results)
    status_msg += f"\n\n📊 Active users: {len(last_request_time)}"
    status_msg += f"\n💰 Total balance in system: {sum(user_balances.values())}"
    
    await safe_reply(update, status_msg, parse_mode="HTML")

async def button(update: Update, context):
    """Handle button callbacks."""
    q = update.callback_query
    await q.answer()
    
    if q.data == "lookup":
        context.user_data["lookup"] = True
        return await safe_reply(update, "📥 Send phone number or email address:")
    
    elif q.data == "family":
        context.user_data["family"] = True
        return await safe_reply(update, "👪 Send Family ID (ration card number):")
    
    elif q.data == "track":
        context.user_data["track"] = True
        return await safe_reply(update, "🌍 Send website URL to track:")
    
    elif q.data == "buy":
        return await buy(update, context)
    
    elif q.data == "balance":
        return await balance(update, context)
    
    elif q.data == "stats":
        return await stats(update, context)

# ================== ENHANCED MESSAGE HANDLER =====================

async def handle_message(update: Update, context):
    """Enhanced message handler with better error handling."""
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    
    if not text:
        return await safe_reply(update, "❌ Please provide valid input.")
    
    # Check rate limiting
    can_request, error_msg = can_make_request(uid)
    if not can_request:
        return await safe_reply(update, error_msg)
    
    # Auto-detect phone numbers
    phone_auto = normalize_phone(text)
    email_auto = re.fullmatch(r"[\w.-]+@[\w.-]+\.\w+", text)
    
    if phone_auto or email_auto:
        context.user_data["lookup"] = True
    
    # Handle lookup requests
    if context.user_data.pop("lookup", False):
        phone = normalize_phone(text)
        email = text if email_auto else None
        
        if not phone and not email:
            return await safe_reply(update, "❌ Invalid phone number or email address.")
        
        if user_balances.get(uid, 0) < COST_LOOKUP:
            return await safe_reply(update, 
                f"❌ Insufficient balance. You need {COST_LOOKUP} credits.\n"
                f"Current balance: {user_balances.get(uid, 0)} credits.\n"
                "Use /buy to add credits."
            )
        
        # Deduct credits
        user_balances[uid] -= COST_LOOKUP
        processing_msg = await safe_reply(update, "⏳ Fetching OSINT data... This may take a few seconds.")
        
        try:
            # Make API call
            raw = leak_raw(phone if phone else email)
            
            # Handle API errors
            if isinstance(raw, dict) and raw.get('error'):
                # Refund credits on error
                user_balances[uid] += COST_LOOKUP
                
                error_msg = raw['error']
                if any(word in error_msg.lower() for word in ['blocked', 'ip blocked', 'rate limit', 'limit exceeded']):
                    return await safe_reply(update,
                        "❌ API providers are temporarily rate-limiting requests.\n"
                        "Please try again in 10-15 minutes.\n"
                        "Your credits have been refunded."
                    )
                else:
                    return await safe_reply(update, f"❌ API Error: {error_msg}\nCredits refunded.")
            
            # Format and send response
            if isinstance(raw, dict) and any(k in raw for k in ["FullName", "FatherName", "Address", "phone"]):
                msg = format_lookup(raw)
                for c in chunk(msg):
                    await safe_reply(update, c, parse_mode="HTML", disable_web_page_preview=True)
                return
            
            elif "List" in raw:
                msg = format_list(raw)
                for c in chunk(msg):
                    await safe_reply(update, c, parse_mode="HTML", disable_web_page_preview=True)
                return
            
            else:
                # Raw JSON response for debugging
                pretty = "<pre>" + json.dumps(raw, indent=2, ensure_ascii=False) + "</pre>"
                for c in chunk(pretty):
                    await safe_reply(update, c, parse_mode="HTML")
                    
        except Exception as e:
            # Refund on unexpected error
            user_balances[uid] += COST_LOOKUP
            logger.error(f"Lookup error for user {uid}: {e}")
            return await safe_reply(update, f"❌ Unexpected error: {str(e)}\nCredits refunded.")
        
        finally:
            # Delete processing message
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
    
    # Handle family lookup
    elif context.user_data.pop("family", False):
        if user_balances.get(uid, 0) < COST_FAMILY:
            return await safe_reply(update, 
                f"❌ Insufficient balance. You need {COST_FAMILY} credits.\n"
                f"Current balance: {user_balances.get(uid, 0)} credits."
            )
        
        user_balances[uid] -= COST_FAMILY
        processing_msg = await safe_reply(update, "⏳ Fetching family information...")
        
        try:
            raw = family_raw(text)
            
            if "error" in raw:
                user_balances[uid] += COST_FAMILY
                return await safe_reply(update, f"❌ Error: {raw['error']}\nCredits refunded.")
            
            msg = format_family(raw)
            for c in chunk(msg):
                await safe_reply(update, c, parse_mode="HTML")
                
        except Exception as e:
            user_balances[uid] += COST_FAMILY
            logger.error(f"Family lookup error for user {uid}: {e}")
            return await safe_reply(update, f"❌ Unexpected error: {str(e)}\nCredits refunded.")
        
        finally:
            try:
                if processing_msg:
                    await processing_msg.delete()
            except:
                pass
    
    # Handle website tracking
    elif context.user_data.pop("track", False):
        if user_balances.get(uid, 0) < COST_TRACK:
            return await safe_reply(update, 
                f"❌ Insufficient balance. You need {COST_TRACK} credits.\n"
                f"Current balance: {user_balances.get(uid, 0)} credits."
            )
        
        user_balances[uid] -= COST_TRACK
        link = make_tracking_link(uid, text)
        
        return await safe_reply(
            update,
            f"🔗 <b>Your Tracking Link</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"Share this link and get notified when someone clicks it.",
            parse_mode="HTML"
        )
    
    else:
        await safe_reply(update, "🤔 Use /start to access the main menu and choose an option.")

# ================== BACKGROUND LOOP MANAGEMENT =====================

def start_telegram_background(app_obj):
    """
    Create dedicated asyncio loop in background thread for PTB.
    """
    loop = asyncio.new_event_loop()
    
    def _run():
        asyncio.set_event_loop(loop)
        try:
            # Initialize application
            loop.run_until_complete(app_obj.initialize())
            
            # Set webhook
            webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
            loop.run_until_complete(app_obj.bot.delete_webhook(drop_pending_updates=True))
            loop.run_until_complete(app_obj.bot.set_webhook(webhook_url))
            logger.info(f"Webhook configured: {webhook_url}")
            
            # Start application
            loop.create_task(app_obj.start())
            logger.info("PTB application started in background loop")
            
            # Keep loop running
            loop.run_forever()
            
        except Exception as e:
            logger.error(f"Background loop error: {e}")
        finally:
            try:
                loop.run_until_complete(app_obj.stop())
                loop.run_until_complete(app_obj.shutdown())
            except:
                pass
    
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return loop

# ================== MAIN EXECUTION =====================

def main():
    global telegram_app, telegram_loop
    
    # Initialize Telegram application
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("buy", buy))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("stats", stats))
    telegram_app.add_handler(CommandHandler("approve", approve))
    telegram_app.add_handler(CommandHandler("apistatus", apistatus))
    telegram_app.add_handler(CallbackQueryHandler(button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Initialize some demo balances for testing
    user_balances[ADMIN_ID] = 1000  # Admin gets some credits
    
    logger.info("Starting bot with enhanced features...")
    
    try:
        # Start Telegram in background loop
        telegram_loop = start_telegram_background(telegram_app)
        logger.info("Background Telegram loop started")
        
        # Start Flask app
        port = int(os.environ.get("PORT", 10000))
        logger.info(f"Starting Flask app on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False)
        
    except Exception as e:
        logger.error(f"Failed to start: {e}")
        raise

if __name__ == "__main__":
    main()
