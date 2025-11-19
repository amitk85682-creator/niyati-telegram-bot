import logging
import asyncio
from datetime import time
import pytz

from telegram import Update, Chat
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
import database as db
import persona

# --- Global Flags & Setup ---
GEETA_WINDOW_OPEN = False

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Scheduled Tasks ---
async def open_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    global GEETA_WINDOW_OPEN
    GEETA_WINDOW_OPEN = True
    logger.info("Geeta window is now OPEN.")

async def close_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    global GEETA_WINDOW_OPEN
    GEETA_WINDOW_OPEN = False
    logger.info("Geeta window is now CLOSED.")

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type == Chat.PRIVATE:
        db.get_or_create_user(user.id, user.first_name or "User")
        welcome_message = persona.get_welcome_message(user.first_name or "User")
        await update.message.reply_text(welcome_message)
    else:
        await update.message.reply_text("Hiii! Main Niyati. 😊 Group me mujhse baat karne ke liye @mention karo!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(persona.get_help_message())

async def toggle_feature_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type != Chat.PRIVATE:
        await update.message.reply_text("Yeh settings sirf private chat me change kar sakte ho, sorry! 😅")
        return

    try:
        full_text = update.message.text.split()
        if len(full_text) < 2:
            raise ValueError("Insufficient command arguments")
        command = full_text[0].lstrip('/').split('@')[0].lower()
        state = full_text[1].lower()

        if state not in ("on", "off"):
            raise ValueError("State must be 'on' or 'off'")

        is_on = (state == "on")
        db.update_user_pref(user_id, command, is_on)

        confirmation_message = persona.get_toggle_confirmation(command, state)
        await update.message.reply_text(confirmation_message)

    except Exception:
        await update.message.reply_text("Aise use karo: `/meme on` ya `/shayari off`")

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type != Chat.PRIVATE:
        await update.message.reply_text("Yeh command sirf private chat me kaam karta hai.")
        return

    db.delete_user_data(user_id)
    await update.message.reply_text(persona.get_forget_confirmation())

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text("Hehe, yeh sirf admins ke liye hai! 😉")
        return

    try:
        parts = update.message.text.split(maxsplit=2)
        if len(parts) < 3:
            raise ValueError("Not enough arguments for broadcast")

        pin = parts[1]
        content = parts[2]

        if pin != config.BROADCAST_PIN:
            await update.message.reply_text("Sorry, PIN galat hai. 🤫")
            return

        all_user_ids = db.get_all_user_ids()
        sent_count = 0
        status_msg = await update.message.reply_text(f"Broadcast starting for {len(all_user_ids)} users...")

        for uid in all_user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=content, parse_mode=ParseMode.HTML)
                sent_count += 1
                await asyncio.sleep(0.05)
            except TelegramError as e:
                logger.error(f"Broadcast failed for user {uid}: {e}")

        await context.bot.edit_message_text(chat_id=user_id, message_id=status_msg.message_id,
                                            text=f"Done! Message {sent_count}/{len(all_user_ids)} users ko bhej diya hai. ✅")

    except Exception:
        await update.message.reply_text("Aise use karo: `/broadcast <PIN> <Your Message>`")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat = update.effective_chat
    user = update.effective_user
    text = message.text

    mode = "private" if chat.type == Chat.PRIVATE else "group"

    if mode == 'group':
        if f"@{config.BOT_USERNAME.lower()}" not in text.lower():
            return

    prefs = {}
    if mode == 'private':
        db.get_or_create_user(user.id, user.first_name or "User")
        prefs = db.get_user_prefs(user.id) or {"memes": True, "shayari": True, "geeta": True}

    reply_text = persona.get_reply(text, mode, prefs, GEETA_WINDOW_OPEN)
    await message.reply_text(reply_text)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, TelegramError) and update and hasattr(update, 'effective_chat') and update.effective_chat:
        try:
            chat_id = update.effective_chat.id
            await context.bot.send_message(chat_id, "Sorry yaar, meri galti... kuch toh gadbad ho gayi. 🫶")
        except Exception as e:
            logger.error(f"Failed to send error acknowledgement: {e}")

def main():
    db.init_db()

    builder = Application.builder().token(config.TELEGRAM_TOKEN)
    application = builder.build()

    job_queue = application.job_queue
    if job_queue:
        tz = pytz.timezone(config.GEETA_TIMEZONE)
        job_queue.run_daily(open_geeta_window, time(hour=7, minute=0, second=0, tzinfo=tz))
        job_queue.run_daily(close_geeta_window, time(hour=10, minute=0, second=0, tzinfo=tz))
    else:
        logger.error("JobQueue failed to initialize. Make sure 'python-telegram-bot[job-queue]' is installed.")

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["meme", "shayari", "geeta"], toggle_feature_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    logger.info("Niyati is starting... ✨")
    application.run_polling()

if __name__ == "__main__":
    main()
