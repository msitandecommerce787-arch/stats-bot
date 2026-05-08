import logging, os, requests, csv, io, json, threading, time, asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SHEET_ID = "18de83dHTjl1azVEcvep8heLjLOYWGCKcNh4vxepA85o"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
USERS_FILE = "users.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_USERNAME, WAITING_FILTER, WAITING_FROM, WAITING_TO = 1, 2, 3, 4

sessions = {}
last_count = [0]
app_ref = [None]

DATE_COL, NICK_COL, INO_COL, CNO_COL, FINAL_COL, SOURCE_COL = 0, 1, 3, 5, 6, 7

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE) as f:
                return json.load(f)
    except: pass
    return {}

def save_users(u):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(u, f)
    except: pass

def register_user(user):
    users = load_users()
    uid = str(user.id)
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    users[uid] = {
        'id': user.id,
        'name': user.full_name,
        'username': f"@{user.username}" if user.username else "—",
        'first_seen': users.get(uid, {}).get('first_seen', now),
        'last_seen': now,
        'searches': users.get(uid, {}).get('searches', 0) + 1
    }
    save_users(users)

def get_rows():
    try:
        r = requests.get(SHEET_URL, timeout=10)
        r.encoding = 'utf-8'
        return list(csv.reader(io.StringIO(r.text)))
    except Exception as e:
        logger.error(e)
        return []

def parse_date(s):
    s = s.strip()
    for fmt in ['%d.%m.%Y', '%d.%m.%y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m']:
        try:
            d = datetime.strptime(s, fmt)
            if fmt == '%d.%m':
                d = d.replace(year=datetime.now().year)
            return d
        except: pass
    return None

def find_user(username, rows):
    res = {}
    ul = username.strip().lower()
    for row in rows:
        if len(row) < 2: continue
        if row[NICK_COL].strip().lower() == ul:
            ds = row[DATE_COL].strip()
            if not ds: continue
            res[ds] = {
                'date_str': ds,
                'date_obj': parse_date(ds),
                'nick': row[NICK_COL].strip(),
                'ino': row[INO_COL].strip() if len(row) > INO_COL else '—',
                'cno': row[CNO_COL].strip() if len(row) > CNO_COL else '—',
                'final': row[FINAL_COL].strip() if len(row) > FINAL_COL else '—',
                'source': row[SOURCE_COL].strip() if len(row) > SOURCE_COL else '—',
            }
    return res or None

def fmt_row(row):
    try:
        f = int(row['final'])
        m = "🥇" if f>=50 else "🥈" if f>=30 else "🥉" if f>=10 else "✅" if f>0 else "❌"
    except: m = "⚡"
    src = f"║   🌐 _{row['source']}_\n" if row['source'] not in ['—',''] else ""
    return (
        f"╔══════════════════════\n"
        f"║ 👤 *{row['nick']}*\n"
        f"║ 📅 *{row['date_str']}*\n"
        f"╠══════════════════════\n"
        f"║ ▶️  Initial:  *{row['ino']}*\n"
        f"║ 🔄 Closing:  *{row['cno']}*\n"
        f"║ {m} Final:    *{row['final']}*\n"
        f"{src}"
        f"╚══════════════════════\n\n"
    )

def filter_data(all_data, mode, **kw):
    today = datetime.now().date()
    res = {}
    for uname, udata in all_data.items():
        filtered = {}
        for ds, row in udata.items():
            d = row['date_obj']
            ok = False
            if mode == 'today': ok = bool(d and d.date() == today)
            elif mode == 'last_n': ok = bool(d and d.date() >= today - timedelta(days=kw.get('n',7)-1))
            elif mode == 'range':
                df, dt = kw.get('df'), kw.get('dt')
                ok = bool(d and df and dt and df <= d.date() <= dt)
            elif mode == 'specific':
                tgt = kw.get('tgt')
                ok = bool(d and tgt and d.date() == tgt)
            elif mode == 'all': ok = True
            if ok: filtered[ds] = row
        if filtered: res[uname] = filtered
    return res

def build_report(fdata, title):
    if not fdata: return None
    msg = f"📊 *{title}*\n{'━'*22}\n\n"
    total, count = 0, 0
    for udata in fdata.values():
        for row in sorted(udata.values(), key=lambda x: x['date_obj'] or datetime.min, reverse=True):
            msg += fmt_row(row)
            try: total += int(row['final']); count += 1
            except: pass
    if count > 1:
        msg += f"{'━'*22}\n📈 *Total Final Adds: {total}*\n👥 *Entries: {count}*"
    return msg

def main_kb():
    today = datetime.now().strftime('%d.%m.%Y')
    return ReplyKeyboardMarkup([
        [f'🌅 Today  ({today})'],
        ['📋 All Data'],
        ['1️⃣ Last 1', '2️⃣ Last 2', '3️⃣ Last 3'],
        ['4️⃣ Last 4', '5️⃣ Last 5', '6️⃣ Last 6'],
        ['7️⃣ Last 7', '🔟 Last 10', '📆 Last 14'],
        ['📆 Last 15', '📆 Last 20', '📆 Last 25'],
        ['📆 Last 30'],
        ['📆 Custom Range', '🗓 Specific Date'],
        ['🔄 New Search', '❌ Exit']
    ], resize_keyboard=True)

def date_kb(all_data):
    dates = sorted({ds for udata in all_data.values() for ds in udata}, reverse=True)[:30]
    rows, r = [], []
    for d in dates:
        r.append(d)
        if len(r)==3: rows.append(r); r=[]
    if r: rows.append(r)
    rows.append(['⬅️ Back', '❌ Exit'])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.message.from_user)
    await update.message.reply_text(
        "🤖 *ADDS TRACKER BOT*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 Username লিখো!\n\n"
        "💡 _একাধিক username:_\n_space দিয়ে লিখো_",
        parse_mode='Markdown', reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_USERNAME

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    register_user(update.message.from_user)
    text = update.message.text.strip()

    if text in ['🔄 New Search', '❌ Exit']:
        await update.message.reply_text("👤 Username লিখো:", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    await update.message.reply_text("⏳ _Searching..._", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())

    rows = get_rows()
    if not rows or len(rows) < 2:
        await update.message.reply_text("❌ Sheet connect হচ্ছে না!")
        return WAITING_USERNAME

    all_data, not_found = {}, []
    for uname in text.split():
        d = find_user(uname, rows[1:])
        if d: all_data[uname] = d
        else: not_found.append(uname)

    if not all_data:
        await update.message.reply_text(f"❌ পাওয়া যায়নি: *{', '.join(not_found)}*", parse_mode='Markdown')
        return WAITING_USERNAME

    sessions[uid] = {'all_data': all_data, 'mode': 'filter'}
    extra = f"\n⚠️ _পাওয়া যায়নি: {', '.join(not_found)}_" if not_found else ""
    found = ' | '.join(all_data.keys())

    await update.message.reply_text(
        f"✅ *Found:* {found}{extra}\n\n📊 কোন period এর data দেখতে চাও?",
        parse_mode='Markdown', reply_markup=main_kb()
    )
    return WAITING_FILTER

async def handle_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    sel = update.message.text.strip()

    if sel == '❌ Exit':
        await update.message.reply_text("👋 _Bye!_", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME
    if sel == '🔄 New Search':
        await update.message.reply_text("👤 Username লিখো:", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME
    if uid not in sessions:
        await update.message.reply_text("⚠️ আবার username লিখো:", reply_markup=ReplyKeyboardRemove())
        return WAITING_USERNAME

    all_data = sessions[uid]['all_data']

    if sel == '🗓 Specific Date':
        sessions[uid]['mode'] = 'date'
        await update.message.reply_text("📅 Date select করো:", reply_markup=date_kb(all_data))
        return WAITING_FILTER

    if sel == '⬅️ Back':
        sessions[uid]['mode'] = 'filter'
        await update.message.reply_text("📊 Period select করো:", reply_markup=main_kb())
        return WAITING_FILTER

    if sel == '📆 Custom Range':
        await update.message.reply_text(
            "📆 *Custom Date Range*\n\nFrom date লিখো:\n_(যেমন: 01.05.2026)_",
            parse_mode='Markdown', reply_markup=ReplyKeyboardRemove()
        )
        return WAITING_FROM

    if sessions[uid].get('mode') == 'date':
        d = parse_date(sel)
        if not d:
            await update.message.reply_text("❌ Date ঠিকমতো select করো!", reply_markup=date_kb(all_data))
            return WAITING_FILTER
        fdata = filter_data(all_data, 'specific', tgt=d.date())
        msg = build_report(fdata, f"📅 {sel}") or f"❌ *{sel}* তারিখে data নেই!"
        chunks = [msg[i:i+4000] for i in range(0,len(msg),4000)]
        for i, chunk in enumerate(chunks):
            rm = date_kb(all_data) if i==len(chunks)-1 else None
            await update.message.reply_text(chunk, parse_mode='Markdown', reply_markup=rm)
        return WAITING_FILTER

    today_str = datetime.now().strftime('%d.%m.%Y')
    if sel.startswith('🌅 Today'):
        fdata = filter_data(all_data, 'today')
        title = f"🌅 Today  {today_str}"
    elif sel == '📋 All Data':
        fdata = filter_data(all_data, 'all')
        title = "📋 All Data"
    elif 'Last' in sel:
        try: n = int(''.join(filter(str.isdigit, sel)))
        except: n = 7
        fdata = filter_data(all_data, 'last_n', n=n)
        title = f"📆 {sel}"
    else:
        fdata = filter_data(all_data, 'all')
        title = "📋 All Data"

    msg = build_report(fdata, title) or "❌ এই period এ কোনো data নেই!"
    chunks = [msg[i:i+4000] for i in range(0,len(msg),4000)]
    for i, chunk in enumerate(chunks):
        rm = main_kb() if i==len(chunks)-1 else None
        await update.message.reply_text(chunk, parse_mode='Markdown', reply_markup=rm)
    return WAITING_FILTER

async def handle_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    d = parse_date(update.message.text.strip())
    if not d:
        await update.message.reply_text("❌ Format ঠিক করো! _(যেমন: 01.05.2026)_", parse_mode='Markdown')
        return WAITING_FROM
    sessions[uid]['custom_from'] = d.date()
    await update.message.reply_text(
        f"✅ From: *{update.message.text.strip()}*\n\nTo date লিখো:\n_(যেমন: 07.05.2026)_",
        parse_mode='Markdown'
    )
    return WAITING_TO

async def handle_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    d = parse_date(update.message.text.strip())
    if not d:
        await update.message.reply_text("❌ Format ঠিক করো! _(যেমন: 07.05.2026)_", parse_mode='Markdown')
        return WAITING_TO
    df = sessions[uid].get('custom_from')
    dt = d.date()
    all_data = sessions[uid]['all_data']
    fdata = filter_data(all_data, 'range', df=df, dt=dt)
    from_str = df.strftime('%d.%m.%Y')
    to_str = dt.strftime('%d.%m.%Y')
    msg = build_report(fdata, f"📆 {from_str} → {to_str}") or "❌ এই range এ কোনো data নেই!"
    chunks = [msg[i:i+4000] for i in range(0,len(msg),4000)]
    for i, chunk in enumerate(chunks):
        rm = main_kb() if i==len(chunks)-1 else None
        await update.message.reply_text(chunk, parse_mode='Markdown', reply_markup=rm)
    return WAITING_FILTER

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ তুমি admin না!")
        return
    users = load_users()
    if not users:
        await update.message.reply_text("কেউ এখনো bot use করেনি!")
        return
    msg = f"👥 *Bot Users ({len(users)} জন)*\n{'━'*22}\n\n"
    for u in users.values():
        msg += f"👤 *{u['name']}* {u['username']}\n🔍 Searches: *{u['searches']}* | Last: _{u['last_seen']}_\n\n"
    chunks = [msg[i:i+4000] for i in range(0,len(msg),4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ বাতিল।", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def notification_thread(loop):
    """Background thread to check sheet updates every 5 minutes"""
    while True:
        try:
            time.sleep(300)  # 5 minutes
            rows = get_rows()
            current_count = len(rows)
            if last_count[0] > 0 and current_count > last_count[0]:
                users = load_users()
                today_str = datetime.now().strftime('%d.%m.%Y')
                new_rows = current_count - last_count[0]
                notif_msg = (
                    f"🔔 *নতুন Report এসেছে!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📅 আজকের Date: *{today_str}*\n"
                    f"📊 নতুন entries: *{new_rows}টি*\n\n"
                    f"👉 Username লিখে এখনই দেখো!"
                )
                app = app_ref[0]
                if app:
                    for u in users.values():
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                app.bot.send_message(chat_id=u['id'], text=notif_msg, parse_mode='Markdown'),
                                loop
                            )
                            future.result(timeout=10)
                        except Exception as e:
                            logger.error(f"Notify error: {e}")
            last_count[0] = current_count
        except Exception as e:
            logger.error(f"Thread error: {e}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    app_ref[0] = application

    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)
        ],
        states={
            WAITING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)],
            WAITING_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filter)],
            WAITING_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_from)],
            WAITING_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_to)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv)
    application.add_handler(CommandHandler('admin', admin_cmd))

    # Initialize sheet count
    rows = get_rows()
    last_count[0] = len(rows)

    # Start notification thread
    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()

    notif_thread = threading.Thread(target=notification_thread, args=(loop,), daemon=True)
    notif_thread.start()

    print("✅ Bot চালু!")
    application.run_polling()

if __name__ == '__main__':
    main()
