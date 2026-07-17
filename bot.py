import logging
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from downloader import download_media

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 5724602667
CHANNELS_FILE = "channels.json"
USERS_FILE = "users.json"


# ---------- Storage helpers ----------
def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def load_channels():
    return load_json(CHANNELS_FILE)


def save_channels(channels):
    save_json(CHANNELS_FILE, channels)


def track_user(user_id):
    users = load_json(USERS_FILE)
    if user_id not in users:
        users.append(user_id)
        save_json(USERS_FILE, users)


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
        channels = load_channels()
        channels = [c for c in channels if c["id"] != channel_id]
        save_channels(channels)
        await query.message.edit_text(f"✅ Channel removed: {channel_id}")


# ---------- Message handler (handles admin replies + normal links) ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Handle admin awaiting input
    if user_id == ADMIN_ID and context.user_data.get("awaiting"):
        awaiting = context.user_data.pop("awaiting")

        if awaiting == "add_channel":
            try:
                channel_id, link, name = [p.strip() for p in text.split("|")]
                channels = load_channels()
                channels.append({"id": channel_id, "link": link, "name": name})
                save_channels(channels)
                await update.message.reply_text(f"✅ Channel added: {name}")
            except ValueError:
                await update.message.reply_text("❌ Wrong format. Use: @channel | link | Name")
            return

        if awaiting == "broadcast":
            users = load_json(USERS_FILE)
            sent, failed = 0, 0
            for uid in users:
                try:
                    await context.bot.send_message(chat_id=uid, text=text)
                    sent += 1
                except Exception:
                    failed += 1
            await update.message.reply_text(f"📢 Broadcast done.\nSent: {sent} | Failed: {failed}")
            return

    # Normal user flow
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
        filepath, media_type = download_media(text)
        caption = "✅ Downloaded successfully!\n\n🤖 @AllSaverPinDownloader_bot"
        if media_type == "video":
            await update.message.reply_video(video=open(filepath, 'rb'), caption=caption)
        else:
            await update.message.reply_photo(photo=open(filepath, 'rb'), caption=caption)
        os.remove(filepath)
    except Exception as e:
        await update.message.reply_text(f"❌ Sorry, download failed.\nReason: {str(e)}")
    finally:
        await msg.delete()


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_|^rm_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
