# --- main.py (Corrected) ---

import logging
import random
from datetime import time
import pytz

from telegram import Update, Chat
# JobQueue is now imported directly
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue # <-- CHANGE HERE
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
def open_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    """Sets the Geeta window flag to True."""
    global GEETA_WINDOW_OPEN
    GEETA_WINDOW_OPEN = True
    logger.info("Geeta window is now OPEN.")

def close_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    """Sets the Geeta window flag to False."""
    global GEETA_WINDOW_OPEN
    GEETA_WINDOW_OPEN = False
    logger.info("Geeta window is now CLOSED.")

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    if chat.type == Chat.PRIVATE:
        db.get_or_create_user(user.id, user.first_name)
        welcome_message = persona.get_welcome_message(user.first_name)
        await update.message.reply_text(welcome_message)
    else: # Group chat
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
        command = update.message.text.split()[0].lstrip('/').split('@')[0]
        state = context.args[0].lower()
        if state not in ["on", "off"]:
            raise ValueError
        
        is_on = (state == "on")
        db.update_user_pref(user_id, command, is_on)
        
        confirmation_message = persona.get_toggle_confirmation(command, state)
        await update.message.reply_text(confirmation_message)

    except (IndexError, ValueError):
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
        pin = parts[1]
        content = parts[2]

        if pin != config.BROADCAST_PIN:
            await update.message.reply_text("Sorry, PIN galat hai. 🤫")
            return

        all_user_ids = db.get_all_user_ids()
        sent_count = 0
        for uid in all_user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=content, parse_mode=ParseMode.HTML)
                sent_count += 1
            except TelegramError as e:
                logger.error(f"Broadcast failed for user {uid}: {e}")
        
        await update.message.reply_text(f"Done! Message {sent_count}/{len(all_user_ids)} users ko bhej diya hai. ✅")

    except (IndexError, ValueError):
        await update.message.reply_text("Aise use karo: `/broadcast <PIN> <Your Message>`")

# --- Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    text = message.text

    mode = "private" if chat.type == Chat.PRIVATE else "group"
    
    if mode == 'group' and f"@{config.BOT_USERNAME}" not in text:
        return

    prefs = {}
    if mode == 'private':
        db.get_or_create_user(user.id, user.first_name) # Ensure user exists
        prefs = db.get_user_prefs(user.id) or {"memes": True, "shayari": True, "geeta": True}

    reply_text = persona.get_reply(text, mode, prefs, GEETA_WINDOW_OPEN)
    
    await message.reply_text(reply_text)

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if isinstance(context.error, TelegramError):
        try:
            chat_id = update.effective_chat.id
            await context.bot.send_message(chat_id, "Sorry yaar, meri galti... kuch toh gadbad ho gayi. 🫶")
        except Exception as e:
            logger.error(f"Failed to send error acknowledgement: {e}")

# --- Main Function ---
def main():
    """Start the bot."""
    db.init_db()

    # Create the Application builder
    builder = Application.builder().token(config.TELEGRAM_TOKEN)

    # Create and attach the JobQueue
    job_queue = JobQueue() # <-- CHANGE HERE
    builder.job_queue(job_queue) # <-- CHANGE HERE

    # Build the application
    application = builder.build() # <-- CHANGE HERE

    # Schedule the daily jobs
    tz = pytz.timezone(config.GEETA_TIMEZONE)
    job_queue.run_daily(open_geeta_window, time(hour=7, minute=0, second=0, tzinfo=tz))
    job_queue.run_daily(close_geeta_window, time(hour=10, minute=0, second=0, tzinfo=tz))

    # --- Register Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["meme", "shayari", "geeta"], toggle_feature_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    # Run the bot
    logger.info("Niyati is starting... ✨")
    application.run_polling()

if __name__ == "__main__":
    main()
