import logging
import os
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
WAITING_DATE = 2

user_sessions = {}

def get_sheet_rows():
    try:
        resp = requests.get(SHEET_CSV_URL, timeout=10)
        resp.encoding = 'utf-8'
        reader = csv.reader(io.StringIO(resp.text))
        return list(reader)
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return []

def find_user_data(username, rows, headers_idx):
    nick_idx = headers_idx['nick']
    date_idx = headers_idx['date']
    ino_idx = headers_idx['ino']
    iss_idx = headers_idx['iss']
    cno_idx = headers_idx['cno']
    css_idx = headers_idx['css']
    final_idx = headers_idx['final']
    source_idx = headers_idx['source']

    results = {}
    for row in rows:
        if len(row) <= nick_idx:
            continue
        if row[nick_idx].strip().lower() == username.strip().lower():
            date = row[date_idx].strip() if len(row) > date_idx else 'Unknown'
            if not date:
                date = 'Unknown'
            results[date] = {
                'date': date,
                'nick': row[nick_idx].strip(),
                'ino': row[ino_idx].strip() if len(row) > ino_idx else '—',
                'iss': row[iss_idx].strip() if len(row) > iss_idx else '—',
                'cno': row[cno_idx].strip() if len(row) > cno_idx else '—',
                'css': row[css_idx].strip() if len(row) > css_idx else '—',
                'final': row[final_idx].strip() if len(row) > final_idx else '—',
                'source': row[source_idx].strip() if len(row) > source_idx else '—',
            }
    return results if results else None

def get_headers_idx(headers):
    h = [x.strip().lower() for x in headers]
    return {
        'nick': next((i for i, x in enumerate(h) if 'nick' in x), 1),
        'date': next((i for i, x in enumerate(h) if 'date' in x), 0),
        'iss': next((i for i, x in enumerate(h) if 'initial' in x and 'ss' in x), 2),
        'ino': next((i for i, x in enumerate(h) if 'initial' in x and 'no' in x), 3),
        'css': next((i for i, x in enumerate(h) if 'closing' in x and 'ss' in x), 4),
        'cno': next((i for i, x in enumerate(h) if 'closing' in x and 'no' in x), 5),
        'final': next((i for i, x in enumerate(h) if 'final' in x), 6),
        'source': next((i for i, x in enumerate(h) if 'source' in x), 7),
    }

def format_row(row):
    source_line = f"🌐 Source: *{row['source']}*\n" if row['source'] and row['source'] != '—' else ""
    return (
        f"👤 *{row['nick']}* | 📅 *{row['date']}*\n"
        f"▶️ Initial: *{row['ino']}* | 🔄 Closing: *{row['cno']}*\n"
        f"⚡ Final Adds: *{row['final']}*\n"
        f"{source_line}"
        f"━━━━━━━━━━━━━━━\n"
    )

def make_date_keyboard(all_data):
    # Collect all dates across all users
    all_dates = set()
    for udata in all_data.values():
        all_dates.update(udata.keys())
    
    dates = sorted(all_dates, reverse=True)[:30]
    
    keyboard = [['📋 All Data']]
    row = []
    for date in dates:
        row.append(date)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(['🔄 নতুন Username', '❌ বাতিল'])
    return keyboard, dates

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Adds Tracker Bot*\n\n"
        "Username লিখো!\n"
        "একাধিক username এর জন্য space দিয়ে লিখো:\n"
        "_(যেমন: DANIELghjo ESMEExvbw JORYYYrty)_",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_USERNAME

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    # Handle special commands
    if text == '🔄 নতুন Username':
        await update.message.reply_text(
            "👤 Username লিখো:\n_(একাধিকের জন্য space দিয়ে লিখো)_",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return WAITING_USERNAME

    await update.message.reply_text("🔍 খুঁজছি...", reply_markup=ReplyKeyboardRemove())

    # Split multiple usernames
    usernames = text.split()

    rows = get_sheet_rows()
    if not rows or len(rows) < 2:
        await update.message.reply_text("❌ Sheet থেকে data আনতে পারছি না!")
        return WAITING_USERNAME

    headers_idx = get_headers_idx(rows[0])
    data_rows = rows[1:]

    all_data = {}
    not_found = []

    for username in usernames:
        udata = find_user_data(username, data_rows, headers_idx)
        if udata:
            all_data[username] = udata
        else:
            not_found.append(username)

    if not all_data:
        msg = "❌ কোনো user পাওয়া যায়নি!\n"
        if not_found:
            msg += f"পাওয়া যায়নি: {', '.join(not_found)}"
        await update.message.reply_text(msg)
        return WAITING_USERNAME

    # Save session
    user_sessions[user_id] = {
        'usernames': list(all_data.keys()),
        'all_data': all_data
    }

    # Not found message
    extra = ""
    if not_found:
        extra = f"\n⚠️ পাওয়া যায়নি: {', '.join(not_found)}"

    found_names = ', '.join(all_data.keys())
    keyboard, dates = make_date_keyboard(all_data)
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

    await update.message.reply_text(
        f"✅ পেয়েছি: *{found_names}*{extra}\n\n"
        f"📅 কোন date এর data দেখতে চাও?\n"
        f"_(All Data = সব দিনের data একসাথে)_",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return WAITING_DATE

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    selected = update.message.text.strip()

    if selected == '❌ বাতিল':
        await update.message.reply_text("❌ বাতিল।", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    if selected == '🔄 নতুন Username':
        await update.message.reply_text(
            "👤 Username লিখো:\n_(একাধিকের জন্য space দিয়ে লিখো)_",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return WAITING_USERNAME

    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ আবার username লিখো:", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    session = user_sessions[user_id]
    all_data = session['all_data']
    keyboard, dates = make_date_keyboard(all_data)
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

    if selected == '📋 All Data':
        # Show all data for all users
        msg = "📊 *সব Data*\n━━━━━━━━━━━━━━━\n"
        for username, udata in all_data.items():
            sorted_dates = sorted(udata.keys(), reverse=True)[:30]
            for date in sorted_dates:
                msg += format_row(udata[date])
        
        # Split if too long
        if len(msg) > 4000:
            chunks = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            for chunk in chunks:
                await update.message.reply_text(chunk, parse_mode='Markdown')
        else:
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
        return WAITING_DATE

    # Specific date selected
    msg = f"📊 *{selected}* এর Data\n━━━━━━━━━━━━━━━\n"
    found = False
    for username, udata in all_data.items():
        if selected in udata:
            msg += format_row(udata[selected])
            found = True

    if not found:
        await update.message.reply_text(
            f"❌ *{selected}* তারিখে কোনো data নেই!",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return WAITING_DATE

    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
    return WAITING_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ বাতিল।", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)
        ],
        states={
            WAITING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)],
            WAITING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv)
    print("✅ Bot চালু!")
    app.run_polling()

if __name__ == '__main__':
    main()
