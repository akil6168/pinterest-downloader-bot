import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from downloader import download_media
from pymongo import MongoClient
import certifi

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 5724602667
MONGO_URI = os.environ.get("MONGO_URI")

# ---------- MongoDB setup ----------
mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = mongo_client["allsaverbot"]
channels_col = db["channels"]
users_col = db["users"]


def load_channels():
    return list(channels_col.find({}, {"_id": 0}))


def save_channel(channel):
    channels_col.insert_one(channel)


def delete_channel(channel_id):
    channels_col.delete_one({"id": channel_id})


def track_user(user_id):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id})


def get_all_users():
    return [u["user_id"] for u in users_col.find({}, {"user_id": 1})]


# ---------- Force-join logic ----------
async def check_membership(user_id, context):
    channels = load_channels()
    not_joined = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined


async def send_force_join(update, not_joined):
    buttons = []
    for ch in not_joined:
        buttons.append([InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch["link"])])
    buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
    await update.message.reply_text(
        "🚫 To use this bot, please join our channel(s) first.\n\n"
        "After joining, tap the button below.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ---------- User commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user.id)
    not_joined = await check_membership(update.effective_user.id, context)
    if not_joined:
        await send_force_join(update, not_joined)
        return
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Send me a link from Pinterest, TikTok, Instagram, Facebook or YouTube "
        "and I'll download it for you. 🚀"
    )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    not_joined = await check_membership(query.from_user.id, context)
    if not_joined:
        await query.answer("❌ You haven't joined all channels yet.", show_alert=True)
    else:
        await query.answer("✅ Verified!")
        await query.message.edit_text("✅ Thanks for joining! Now send me a link to download.")


# ---------- Admin panel ----------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    buttons = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="admin_add")],
        [InlineKeyboardButton("➖ Remove Channel", callback_data="admin_remove")],
        [InlineKeyboardButton("📋 List Channels", callback_data="admin_list")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")],
    ]
    await update.message.reply_text(
        "🛠 Admin Panel\n\nChoose an action:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Not authorized.", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "admin_close":
        await query.message.delete()
        return

    if data == "admin_add":
        context.user_data["awaiting"] = "add_channel"
        await query.message.reply_text(
            "Send the channel details in this format (one line):\n\n"
            "@channelusername | https://t.me/channelusername | Channel Display Name\n\n"
            "Example:\n@mychannel | https://t.me/mychannel | My Awesome Channel",
            reply_markup=ForceReply(selective=True)
        )

    elif data == "admin_remove":
        channels = load_channels()
        if not channels:
            await query.message.reply_text("No channels to remove.")
            return
        buttons = [[InlineKeyboardButton(f"🗑 {c['name']}", callback_data=f"rm_{c['id']}")] for c in channels]
        await query.message.reply_text("Select a channel to remove:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "admin_list":
        channels = load_channels()
        if not channels:
            await query.message.reply_text("No force-join channels set.")
            return
        text = "📋 Force-join channels:\n\n"
        for c in channels:
            text += f"• {c['name']} ({c['id']})\n"
        await query.message.reply_text(text)

    elif data == "admin_broadcast":
        context.user_data["awaiting"] = "broadcast"
        await query.message.reply_text(
            "Send the message you want to broadcast to all users:",
            reply_markup=ForceReply(selective=True)
        )

    elif data.startswith("rm_"):
        channel_id = data[3:]
        delete_channel(channel_id)
        await query.message.edit_text(f"✅ Channel removed: {channel_id}")


# ---------- Message handler ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id == ADMIN_ID and context.user_data.get("awaiting"):
        awaiting = context.user_data.pop("awaiting")

        if awaiting == "add_channel":
            try:
                channel_id, link, name = [p.strip() for p in text.split("|")]
                save_channel({"id": channel_id, "link": link, "name": name})
                await update.message.reply_text(f"✅ Channel added: {name}")
            except ValueError:
                await update.message.reply_text("❌ Wrong format. Use: @channel | link | Name")
            return

        if awaiting == "broadcast":
            users = get_all_users()
            sent, failed = 0, 0
            for uid in users:
                try:
                    await context.bot.send_message(chat_id=uid, text=text)
                    sent += 1
                except Exception:
                    failed += 1
            await update.message.reply_text(f"📢 Broadcast done.\nSent: {sent} | Failed: {failed}")
            return

    track_user(user_id)
    not_joined = await check_membership(user_id, context)
    if not_joined:
        await send_force_join(update, not_joined)
        return

    if not text.startswith("http"):
        await update.message.reply_text("Please send a valid link.")
        return

    msg = await update.message.reply_text("⏳ Downloading...")
    try:
        filepath, media_type, original_caption = download_media(text)

        bot_tag = "\n\n🤖 @AllSaverPinDownloader_bot"
        max_caption_len = 1024 - len(bot_tag)
        if original_caption and len(original_caption) > max_caption_len:
            original_caption = original_caption[:max_caption_len - 3] + "..."

        caption = (original_caption + bot_tag) if original_caption else f"✅ Downloaded successfully!{bot_tag}"

        if media_type == "video":
            await update.message.reply_video(
                video=open(filepath, 'rb'),
                caption=caption,
                write_timeout=120,
                read_timeout=120,
                connect_timeout=60,
                pool_timeout=60,
            )
        else:
            await update.message.reply_photo(
                photo=open(filepath, 'rb'),
                caption=caption,
                write_timeout=120,
                read_timeout=120,
                connect_timeout=60,
                pool_timeout=60,
            )
        os.remove(filepath)
    except Exception as e:
        await update.message.reply_text(f"❌ Sorry, download failed.\nReason: {str(e)}")
    finally:
        await msg.delete()


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(120)
        .write_timeout(120)
        .connect_timeout(60)
        .pool_timeout(60)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_|^rm_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
