import logging
import base64
import json
import re
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

TELEGRAM_TOKEN = "7824261761:AAFtcGQPMNNeBeqVd8zwqzXkq_QSauXH5MQ"
GEMINI_API_KEY = "AIzaSyA118Lc9tg1AgYf_quIDYkQNil3xSb-ick"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_FOR_USERNAME = 1
user_images = {}

async def start(update, context):
    await update.message.reply_text("👋 Stats Bot এ স্বাগতম!\n\n📊 Screenshot পাঠাও\nতারপর username লিখো\n✅ Final Adds বলে দেব!")

async def handle_photo(update, context):
    user_id = update.message.from_user.id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    img_bytes = await file.download_as_bytearray()
    user_images[user_id] = bytes(img_bytes)
    await update.message.reply_text("✅ Screenshot পেয়েছি!\n\nএখন username লিখো 👇")
    return WAITING_FOR_USERNAME

async def handle_username(update, context):
    user_id = update.message.from_user.id
    username = update.message.text.strip()
    if user_id not in user_images:
        await update.message.reply_text("❌ আগে screenshot পাঠাও!")
        return ConversationHandler.END
    await update.message.reply_text("🔍 খুঁজছি...")
    try:
        img_base64 = base64.b64encode(user_images[user_id]).decode()
        prompt = f'Find row where nick="{username}". Return ONLY JSON: {{"found":true,"mir_id":"MIR99","username":"{username}","date":"06.05","initial_adds":50,"closing_adds":163,"final_adds":113,"source":"Reddit"}} or {{"found":false}}'
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
            json={"contents":[{"parts":[{"inline_data":{"mime_type":"image/jpeg","data":img_base64}},{"text":prompt}]}]}
        )
        raw = response.json()['candidates'][0]['content']['parts'][0]['text']
        parsed = json.loads(re.search(r'\{[\s\S]*?\}', raw).group())
        if not parsed.get('found'):
            await update.message.reply_text(f"❌ '{username}' পাওয়া যায়নি!")
            return ConversationHandler.END
        msg = f"📊 *{parsed.get('username')}* — `{parsed.get('mir_id')}`\n📅 {parsed.get('date')}\n━━━━━━━━━━━━\n▶️ Initial: *{parsed.get('initial_adds')}*\n🔄 Closing: *{parsed.get('closing_adds')}*\n🌐 Source: *{parsed.get('source')}*\n━━━━━━━━━━━━\n⚡ *Final Adds: {parsed.get('final_adds')}*"
        await update.message.reply_text(msg, parse_mode='Markdown')
        del user_images[user_id]
    except Exception as e:
        await update.message.reply_text("❌ সমস্যা হয়েছে। আবার try করো।")
    return ConversationHandler.END

async def cancel(update, context):
    await update.message.reply_text("❌ বাতিল।")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, handle_photo)],
        states={WAITING_FOR_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username)]},
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv)
    print("✅ Bot চালু!")
    app.run_polling()

if __name__ == '__main__':
    main()
