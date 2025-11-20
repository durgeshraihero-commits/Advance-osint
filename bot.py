# bot.py
import os
import logging
import json
import html
from urllib.parse import quote_plus

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== CONFIG =====================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ================== HELPERS =====================

def fetch_url(url: str) -> str:
    """
    Generic helper to GET a URL and return a nicely formatted string.
    Tries JSON first, falls back to plain text.
    """
    try:
        resp = requests.get(url, timeout=15)
    except Exception as e:
        return f"❌ Error while calling API:\n{e}"

    if resp.status_code != 200:
        return f"❌ API returned HTTP {resp.status_code}"

    text = resp.text.strip()

    # Try JSON pretty print
    try:
        data = resp.json()
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        pretty = text

    # Limit length for Telegram
    max_len = 3500
    if len(pretty) > max_len:
        pretty = pretty[:max_len] + "\n\n[⛔ Output truncated]"

    return pretty


# ================== COMMAND HANDLERS =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *OSINT Utility Bot*\n\n"
        "Available commands:\n"
        "1️⃣ `/phone <number>` – Phone / Email search\n"
        "2️⃣ `/family <id>` – Family info\n"
        "3️⃣ `/vehicle <reg_no>` – Vehicle info (RC)\n"
        "4️⃣ `/insta <username>` – Instagram info\n"
        "5️⃣ `/gst <gstin>` – GST info\n"
        "6️⃣ `/ip <ip_or_domain>` – IP info\n\n"
        "_Example:_\n"
        "`/phone 9006895231`\n"
        "`/vehicle BR01AB1234`\n"
        "`/insta instagram`\n"
        "`/gst 22AAAAA0000A1Z5`\n"
        "`/ip 8.8.8.8`"
    )
    await update.message.reply_markdown(msg)


async def phone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📱 Use like:\n`/phone 9006895231`", parse_mode="Markdown")
        return

    number = " ".join(context.args).strip()
    url = f"https://meowmeow.rf.gd/gand/mobile.php?num={quote_plus(number)}"
    result = fetch_url(url)

    await update.message.reply_text(
        f"🔍 Phone / Email info for: {number}\n\n<pre>{html.escape(result)}</pre>",
        parse_mode="HTML",
    )


async def family_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("👨‍👩‍👧 Use like:\n`/family 1234567890`", parse_mode="Markdown")
        return

    value = " ".join(context.args).strip()
    url = f"https://encore.toxictanji0503.workers.dev/family?id={quote_plus(value)}"
    result = fetch_url(url)

    await update.message.reply_text(
        f"👨‍👩‍👧 Family info for: {value}\n\n<pre>{html.escape(result)}</pre>",
        parse_mode="HTML",
    )


async def vehicle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🚗 Use like:\n`/vehicle BR01AB1234`", parse_mode="Markdown")
        return

    vehicle_number = " ".join(context.args).strip().upper()
    url = f"https://encore.toxictanji0503.workers.dev/rcfuck?vehicle_number={quote_plus(vehicle_number)}"
    result = fetch_url(url)

    await update.message.reply_text(
        f"🚗 Vehicle info for: {vehicle_number}\n\n<pre>{html.escape(result)}</pre>",
        parse_mode="HTML",
    )


async def insta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📸 Use like:\n`/insta username`", parse_mode="Markdown")
        return

    username = " ".join(context.args).strip()
    url = f"https://insta-profile-info-api.vercel.app/api/instagram.php?username={quote_plus(username)}"
    result = fetch_url(url)

    await update.message.reply_text(
        f"📸 Instagram info for: {username}\n\n<pre>{html.escape(result)}</pre>",
        parse_mode="HTML",
    )


async def gst_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🧾 Use like:\n`/gst 22AAAAA0000A1Z5`", parse_mode="Markdown")
        return

    gst_number = " ".join(context.args).strip().upper()
    url = f"https://gstlookup.hideme.eu.org/?gstNumber={quote_plus(gst_number)}"
    result = fetch_url(url)

    await update.message.reply_text(
        f"🧾 GST info for: {gst_number}\n\n<pre>{html.escape(result)}</pre>",
        parse_mode="HTML",
    )


async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🌐 Use like:\n`/ip 8.8.8.8` or `/ip google.com`", parse_mode="Markdown")
        return

    query = " ".join(context.args).strip()
    # ip-api format: http://ip-api.com/json/{query}
    url = f"http://ip-api.com/json/{quote_plus(query)}"
    result = fetch_url(url)

    await update.message.reply_text(
        f"🌐 IP info for: {query}\n\n<pre>{html.escape(result)}</pre>",
        parse_mode="HTML",
    )


# ================== MAIN =====================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("⚠️ An error occurred. Please try again.")
    except Exception:
        pass


def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Please set BOT_TOKEN env variable or edit bot.py with your token.")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))

    application.add_handler(CommandHandler("phone", phone_cmd))
    application.add_handler(CommandHandler("family", family_cmd))
    application.add_handler(CommandHandler("vehicle", vehicle_cmd))
    application.add_handler(CommandHandler("insta", insta_cmd))
    application.add_handler(CommandHandler("gst", gst_cmd))
    application.add_handler(CommandHandler("ip", ip_cmd))

    application.add_error_handler(error_handler)

    print("Bot is running with polling...")
    application.run_polling()


if __name__ == "__main__":
    main()
