# --- main.py (Fully Corrected & Stable) ---

import logging
import random
from datetime import time
import pytz

from telegram import Update, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
import database as db
import persona

# --- Flags ---
GEETA_WINDOW_OPEN = False

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Scheduled Tasks ---
def open_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    global GEETA_WINDOW_OPEN
    GEETA_WINDOW_OPEN = True
    logger.info("Geeta window OPEN ho gaya.")

def close_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    global GEETA_WINDOW_OPEN
    GEETA_WINDOW_OPEN = False
    logger.info("Geeta window CLOSED ho gaya.")

# --- Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type == Chat.PRIVATE:
        db.get_or_create_user(user.id, user.first_name)
        await update.message.reply_text(
            persona.get_welcome_message(user.first_name)
        )
    else:
        await update.message.reply_text(
            "Hii! Main Niyati hu 💖 Group me baat karne ke liye @mention karo!"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(persona.get_help_message())

async def toggle_feature_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type != Chat.PRIVATE:
        await update.message.reply_text("Yeh command sirf private me chalega 😅")
        return

    try:
        command = update.message.text.split()[0].lstrip('/').split('@')[0]
        state = context.args[0].lower()

        if state not in ["on", "off"]:
            raise ValueError

        is_on = (state == "on")
        db.update_user_pref(user_id, command, is_on)

        await update.message.reply_text(
            persona.get_toggle_confirmation(command, state)
        )

    except Exception:
        await update.message.reply_text("Use like: `/meme on` or `/shayari off`")

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type != Chat.PRIVATE:
        await update.message.reply_text("Yeh command sirf private me chalega.")
        return

    db.delete_user_data(user_id)
    await update.message.reply_text(persona.get_forget_confirmation())

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text("Hehe, admin wale kaam mat chhedo 😌")
        return

    try:
        _, pin, content = update.message.text.split(maxsplit=2)

        if pin != config.BROADCAST_PIN:
            await update.message.reply_text("Galat PIN daal diya 😭")
            return

        user_ids = db.get_all_user_ids()
        count = 0

        for uid in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=content,
                    parse_mode=ParseMode.HTML
                )
                count += 1
            except TelegramError as e:
                logger.error(f"Broadcast failed for {uid}: {e}")

        await update.message.reply_text(
            f"Broadcast done! {count}/{len(user_ids)} users ko bhej diya ✔️"
        )

    except:
        await update.message.reply_text("Use like: `/broadcast PIN message`")

# --- Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    text = message.text

    mode = "private" if chat.type == Chat.PRIVATE else "group"

    if mode == "group" and f"@{config.BOT_USERNAME}" not in text:
        return

    prefs = {}
    if mode == "private":
        db.get_or_create_user(user.id, user.first_name)
        prefs = db.get_user_prefs(user.id) or {
            "meme": True,
            "shayari": True,
            "geeta": True
        }

    reply_text = persona.get_reply(text, mode, prefs, GEETA_WINDOW_OPEN)
    await message.reply_text(reply_text)

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(
        f"Error while handling update: {context.error}",
        exc_info=context.error
    )

    try:
        if update and hasattr(update, "effective_chat"):
            await context.bot.send_message(
                update.effective_chat.id,
                "Oops... kuch galti ho gayi 😖"
            )
    except:
        pass

# --- Main Function ---
def main():
    db.init_db()

    builder = Application.builder().token(config.TELEGRAM_TOKEN)

    job_queue = JobQueue()
    builder.job_queue(job_queue)

    application = builder.build()

    # Schedule jobs
    tz = pytz.timezone(config.GEETA_TIMEZONE)
    job_queue.run_daily(open_geeta_window, time(7, 0, 0, tzinfo=tz))
    job_queue.run_daily(close_geeta_window, time(10, 0, 0, tzinfo=tz))

    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["meme", "shayari", "geeta"], toggle_feature_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    logger.info("Niyati is starting... 💖✨")
    application.run_polling()

if __name__ == "__main__":
    main()
