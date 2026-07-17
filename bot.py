import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from downloader import download_media

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "স্বাগতম! Pinterest, TikTok, Instagram থেকে ভিডিও/ছবির লিংক পাঠান, আমি ডাউনলোড করে দেব।"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("দয়া করে একটা সঠিক লিংক পাঠান।")
        return

    msg = await update.message.reply_text("ডাউনলোড হচ্ছে... ⏳")
    try:
        filepath, media_type = download_media(url)
        if media_type == "video":
            await update.message.reply_video(video=open(filepath, 'rb'))
        else:
            await update.message.reply_photo(photo=open(filepath, 'rb'))
        os.remove(filepath)
    except Exception as e:
        await update.message.reply_text(f"দুঃখিত, ডাউনলোড করা যায়নি।\nকারণ: {str(e)}")
    finally:
        await msg.delete()

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
