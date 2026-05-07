import logging
import os
import requests
import csv
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SHEET_ID = "18de83dHTjl1azVEcvep8heLjLOYWGCKcNh4vxepA85o"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_USERNAME = 1

def get_sheet_data():
    try:
        resp = requests.get(SHEET_CSV_URL, timeout=10)
        resp.encoding = 'utf-8'
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        return rows
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return []

def find_user_rows(username):
    rows = get_sheet_data()
    if not rows or len(rows) < 2:
        return None

    # Find header row
    headers = [h.strip().lower() for h in rows[0]]
    
    # Find column indexes
    try:
        nick_idx = next(i for i, h in enumerate(headers) if 'nick' in h)
        date_idx = next((i for i, h in enumerate(headers) if 'date' in h), 0)
        ino_idx = next((i for i, h in enumerate(headers) if 'initial' in h and 'no' in h), None)
        iss_idx = next((i for i, h in enumerate(headers) if 'initial' in h and 'ss' in h), None)
        cno_idx = next((i for i, h in enumerate(headers) if 'closing' in h and 'no' in h), None)
        css_idx = next((i for i, h in enumerate(headers) if 'closing' in h and 'ss' in h), None)
        final_idx = next((i for i, h in enumerate(headers) if 'final' in h), None)
        source_idx = next((i for i, h in enumerate(headers) if 'source' in h), None)
    except StopIteration:
        # fallback: assume fixed columns A,B,C,D,E,F,G,H
        nick_idx = 1
        date_idx = 0
        iss_idx = 2
        ino_idx = 3
        css_idx = 4
        cno_idx = 5
        final_idx = 6
        source_idx = 7

    results = []
    for row in rows[1:]:
        if len(row) <= nick_idx:
            continue
        if row[nick_idx].strip().lower() == username.strip().lower():
            results.append({
                'date': row[date_idx].strip() if date_idx is not None and len(row) > date_idx else '—',
                'nick': row[nick_idx].strip(),
                'iss': row[iss_idx].strip() if iss_idx is not None and len(row) > iss_idx else '—',
                'ino': row[ino_idx].strip() if ino_idx is not None and len(row) > ino_idx else '—',
                'css': row[css_idx].strip() if css_idx is not None and len(row) > css_idx else '—',
                'cno': row[cno_idx].strip() if cno_idx is not None and len(row) > cno_idx else '—',
                'final': row[final_idx].strip() if final_idx is not None and len(row) > final_idx else '—',
                'source': row[source_idx].strip() if source_idx is not None and len(row) > source_idx else '—',
            })

    return results if results else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Adds Tracker Bot*\n\n"
        "তোমার username লিখো — আমি তোমার সব data দেখাব! ✅",
        parse_mode='Markdown'
    )
    return WAITING_USERNAME

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    await update.message.reply_text("🔍 খুঁজছি...")

    results = find_user_rows(username)

    if not results:
        await update.message.reply_text(
            f"❌ *'{username}'* পাওয়া যায়নি!\n\nUsername ঠিকমতো লিখো।",
            parse_mode='Markdown'
        )
        return WAITING_USERNAME

    for row in results:
        source_line = f"🌐 Source: *{row['source']}*\n" if row['source'] and row['source'] != '—' else ""
        
        msg = (
            f"📊 *{row['nick']}* এর Report\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 Date: *{row['date']}*\n"
            f"▶️ Initial Adds: *{row['ino']}*\n"
            f"🔄 Closing Adds: *{row['cno']}*\n"
            f"⚡ Final Adds: *{row['final']}*\n"
            f"{source_line}"
            f"━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

    return WAITING_USERNAME

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ বাতিল।")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)
        ],
        states={
            WAITING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv)
    print("✅ Bot চালু!")
    app.run_polling()

if __name__ == '__main__':
    main()
