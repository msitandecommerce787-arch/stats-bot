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
WAITING_FILTER = 2

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

def find_user_data(username, rows, hidx):
    results = {}
    for row in rows:
        if len(row) <= hidx['nick']:
            continue
        if row[hidx['nick']].strip().lower() == username.strip().lower():
            date = row[hidx['date']].strip() if len(row) > hidx['date'] else 'Unknown'
            if not date:
                date = 'Unknown'
            results[date] = {
                'date': date,
                'nick': row[hidx['nick']].strip(),
                'ino': row[hidx['ino']].strip() if len(row) > hidx['ino'] else '—',
                'cno': row[hidx['cno']].strip() if len(row) > hidx['cno'] else '—',
                'final': row[hidx['final']].strip() if len(row) > hidx['final'] else '—',
                'source': row[hidx['source']].strip() if len(row) > hidx['source'] else '—',
            }
    return results if results else None

def format_row(row):
    source_line = f"🌐 *{row['source']}*\n" if row['source'] and row['source'] != '—' else ""
    return (
        f"👤 *{row['nick']}* | 📅 *{row['date']}*\n"
        f"▶️ Initial: *{row['ino']}* | 🔄 Closing: *{row['cno']}*\n"
        f"⚡ Final Adds: *{row['final']}*\n"
        f"{source_line}"
        f"━━━━━━━━━━━━━━━\n"
    )

def make_filter_keyboard():
    return [
        ['📋 All Data'],
        ['1️⃣ Last 1', '2️⃣ Last 2', '3️⃣ Last 3'],
        ['4️⃣ Last 4', '5️⃣ Last 5', '6️⃣ Last 6'],
        ['7️⃣ Last 7', '🔟 Last 10', '📅 Last 14'],
        ['📅 Last 15', '📅 Last 20', '📅 Last 25'],
        ['📅 Last 30'],
        ['🗓 Specific Date'],
        ['🔄 নতুন Username', '❌ বাতিল']
    ]

def make_date_keyboard(all_data):
    all_dates = set()
    for udata in all_data.values():
        all_dates.update(udata.keys())
    dates = sorted(all_dates, reverse=True)[:30]
    keyboard = []
    row = []
    for date in dates:
        row.append(date)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(['⬅️ Back', '❌ বাতিল'])
    return keyboard, dates

def get_last_n_dates(all_data, n):
    all_dates = set()
    for udata in all_data.values():
        all_dates.update(udata.keys())
    return sorted(all_dates, reverse=True)[:n]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Adds Tracker Bot*\n\n"
        "Username লিখো!\n"
        "_(একাধিক: space দিয়ে লিখো)_",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_USERNAME

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if text in ['🔄 নতুন Username', '❌ বাতিল']:
        await update.message.reply_text("👤 Username লিখো:", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    await update.message.reply_text("🔍 খুঁজছি...", reply_markup=ReplyKeyboardRemove())

    usernames = text.split()
    rows = get_sheet_rows()
    if not rows or len(rows) < 2:
        await update.message.reply_text("❌ Sheet থেকে data আনতে পারছি না!")
        return WAITING_USERNAME

    hidx = get_headers_idx(rows[0])
    all_data = {}
    not_found = []

    for username in usernames:
        udata = find_user_data(username, rows[1:], hidx)
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

    user_sessions[user_id] = {'all_data': all_data, 'mode': 'filter'}

    extra = f"\n⚠️ পাওয়া যায়নি: {', '.join(not_found)}" if not_found else ""
    found_names = ', '.join(all_data.keys())

    reply_markup = ReplyKeyboardMarkup(make_filter_keyboard(), resize_keyboard=True)
    await update.message.reply_text(
        f"✅ *{found_names}*{extra}\n\n📊 কত দিনের data দেখতে চাও?",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return WAITING_FILTER

async def handle_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    selected = update.message.text.strip()

    if selected == '❌ বাতিল':
        await update.message.reply_text("❌ বাতিল।", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    if selected == '🔄 নতুন Username':
        await update.message.reply_text("👤 Username লিখো:", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ আবার username লিখো:", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    session = user_sessions[user_id]
    all_data = session['all_data']

    # Specific Date mode
    if selected == '🗓 Specific Date':
        keyboard, dates = make_date_keyboard(all_data)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("📅 কোন date?", reply_markup=reply_markup)
        user_sessions[user_id]['mode'] = 'date'
        return WAITING_FILTER

    if selected == '⬅️ Back':
        reply_markup = ReplyKeyboardMarkup(make_filter_keyboard(), resize_keyboard=True)
        await update.message.reply_text("📊 কত দিনের data?", reply_markup=reply_markup)
        user_sessions[user_id]['mode'] = 'filter'
        return WAITING_FILTER

    # Specific date selected
    if session.get('mode') == 'date':
        msg = f"📊 *{selected}*\n━━━━━━━━━━━━━━━\n"
        found = False
        for username, udata in all_data.items():
            if selected in udata:
                msg += format_row(udata[selected])
                found = True
        if not found:
            keyboard, _ = make_date_keyboard(all_data)
            await update.message.reply_text(
                f"❌ *{selected}* তারিখে data নেই!",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return WAITING_FILTER
        keyboard, _ = make_date_keyboard(all_data)
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        if len(msg) > 4000:
            for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
                await update.message.reply_text(chunk, parse_mode='Markdown')
            await update.message.reply_text("👆", reply_markup=reply_markup)
        else:
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
        return WAITING_FILTER

    # Last N days
    n = 30
    if selected == '📋 All Data':
        n = 30
    elif 'Last' in selected:
        try:
            n = int(''.join(filter(str.isdigit, selected)))
        except:
            n = 7

    dates_to_show = get_last_n_dates(all_data, n)

    if not dates_to_show:
        await update.message.reply_text("❌ কোনো data নেই!")
        return WAITING_FILTER

    label = "All Data (Last 30)" if selected == '📋 All Data' else selected
    msg = f"📊 *{label}*\n━━━━━━━━━━━━━━━\n"
    for date in dates_to_show:
        for username, udata in all_data.items():
            if date in udata:
                msg += format_row(udata[date])

    reply_markup = ReplyKeyboardMarkup(make_filter_keyboard(), resize_keyboard=True)
    if len(msg) > 4000:
        for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
            await update.message.reply_text(chunk, parse_mode='Markdown')
        await update.message.reply_text("👆", reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
    return WAITING_FILTER

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
            WAITING_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filter)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv)
    print("✅ Bot চালু!")
    app.run_polling()

if __name__ == '__main__':
    main()
