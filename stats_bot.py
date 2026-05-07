import logging
import os
import re
import requests
import csv
import io
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
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

def find_user_data(username):
    rows = get_sheet_data()
    if not rows:
        return None
    
    results = []
    for row in rows:
        if len(row) < 2:
            continue
        # Check if any cell contains the username (case insensitive)
        for i, cell in enumerate(row):
            if cell.strip().lower() == username.strip().lower():
                results.append(row)
                break
    
    return results if results else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Adds Tracker Bot*\n\n"
        "তোমার username লিখো — আমি তোমার সব data দেখাব! ✅\n\n"
        "অথবা /check লিখো",
        parse_mode='Markdown'
    )
    return WAITING_USERNAME

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 তোমার username লিখো:",
        parse_mode='Markdown'
    )
    return WAITING_USERNAME

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    
    await update.message.reply_text("🔍 খুঁজছি...")
    
    results = find_user_data(username)
    
    if not results:
        await update.message.reply_text(
            f"❌ *'{username}'* পাওয়া যায়নি!\n\nUsername ঠিকমতো লিখো।",
            parse_mode='Markdown'
        )
        return WAITING_USERNAME
    
    msg = f"📊 *{username}* এর Report\n"
    msg += "━━━━━━━━━━━━━━━\n"
    
    for row in results:
        # Try to extract data based on column positions
        # Row format: date/MIR_ID, nick, initial_ss, initial_no, closing_ss, closing_no, final_adds, ...
        try:
            # Find the username column index
            nick_idx = None
            for i, cell in enumerate(row):
                if cell.strip().lower() == username.strip().lower():
                    nick_idx = i
                    break
            
            if nick_idx is not None:
                # Extract surrounding data
                date = row[0] if len(row) > 0 else "—"
                initial_no = row[nick_idx + 2] if len(row) > nick_idx + 2 else "—"
                closing_no = row[nick_idx + 4] if len(row) > nick_idx + 4 else "—"
                final = row[nick_idx + 5] if len(row) > nick_idx + 5 else "—"
                
                # Clean up values
                initial_no = initial_no.strip() or "0"
                closing_no = closing_no.strip() or "0"
                final = final.strip() or "0"
                
                msg += f"📅 Date: *{date}*\n"
                msg += f"▶️ Initial Adds: *{initial_no}*\n"
                msg += f"🔄 Closing Adds: *{closing_no}*\n"
                msg += f"⚡ Final Adds: *{final}*\n"
                msg += "━━━━━━━━━━━━━━━\n"
        except Exception as e:
            logger.error(f"Row parse error: {e}")
            continue
    
    await update.message.reply_text(msg, parse_mode='Markdown')
    return WAITING_USERNAME

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ বাতিল।", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('check', check),
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
