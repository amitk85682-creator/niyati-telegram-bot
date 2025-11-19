# --- main.py (Corrected) ---

import logging
import random
from datetime import time
import pytz

from telegram import Update, Chat
# JobQueue is now imported directly
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue 
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
        # User creation/check should ideally be done in private chats
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
        # Extract command name (e.g., 'meme', 'shayari')
        # This handles /meme@bot_username, extracting just 'meme'
        command = update.message.text.split()[0].lstrip('/').split('@')[0]
        
        # Check for arguments (e.g., 'on' or 'off')
        if not context.args or len(context.args) != 1:
            raise IndexError("Missing argument")
            
        state = context.args[0].lower()
        if state not in ["on", "off"]:
            raise ValueError("Invalid state")
            
        is_on = (state == "on")
        # Assuming db.update_user_pref takes the command name directly
        db.update_user_pref(user_id, command, is_on)
        
        confirmation_message = persona.get_toggle_confirmation(command, state)
        await update.message.reply_text(confirmation_message)

    except (IndexError, ValueError):
        # Index error is now explicitly raised if args are missing/incorrect
        # ValueError is for invalid 'on'/'off' state
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
        # Split into max 3 parts: /broadcast, <PIN>, <Your Message>
        parts = update.message.text.split(maxsplit=2) 
        
        # Check if both PIN and Content are present
        if len(parts) < 3:
             await update.message.reply_text("Aise use karo: `/broadcast <PIN> <Your Message>`")
             return

        pin = parts[1]
        content = parts[2]

        if pin != config.BROADCAST_PIN:
            await update.message.reply_text("Sorry, PIN galat hai. 🤫")
            return

        all_user_ids = db.get_all_user_ids()
        sent_count = 0
        for uid in all_user_ids:
            try:
                # Use context.bot.send_message
                await context.bot.send_message(chat_id=uid, text=content, parse_mode=ParseMode.HTML)
                sent_count += 1
            except TelegramError as e:
                # Log error and continue to the next user
                logger.error(f"Broadcast failed for user {uid}: {e}")
        
        await update.message.reply_text(f"Done! Message {sent_count}/{len(all_user_ids)} users ko bhej diya hai. ✅")

    except Exception: # Catch any other unexpected error
        # This catch-all is just a safety net, primary check is for len(parts)
        await update.message.reply_text("Aise use karo: `/broadcast <PIN> <Your Message>`")

# --- Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    text = message.text

    # Ignore if no text is present (e.g., a sticker, photo without caption)
    if not text:
        return

    mode = "private" if chat.type == Chat.PRIVATE else "group"
    
    # In group, only reply if the bot is explicitly mentioned
    if mode == 'group' and f"@{config.BOT_USERNAME}" not in text:
        return

    prefs = {}
    if mode == 'private':
        # Ensure user exists and fetch preferences
        db.get_or_create_user(user.id, user.first_name) 
        # Default prefs if none are found in DB (though get_user_prefs should handle this)
        prefs = db.get_user_prefs(user.id) or {"memes": True, "shayari": True, "geeta": True} 

    # The actual reply logic relies on the external persona module
    reply_text = persona.get_reply(text, mode, prefs, GEETA_WINDOW_OPEN)
    
    await message.reply_text(reply_text)

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Ensure update has effective_chat before trying to access its ID
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id = update.effective_chat.id
    else:
        chat_id = None

    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Try to send an error message back to the user/chat if we have the chat_id
    if chat_id and isinstance(context.error, TelegramError):
        try:
            await context.bot.send_message(chat_id, "Sorry yaar, meri galti... kuch toh gadbad ho gayi. 🫶")
        except Exception as e:
            logger.error(f"Failed to send error acknowledgement: {e}")

# --- Main Function ---
def main():
    """Start the bot."""
    # Ensure DB is initialized before starting the bot
    db.init_db()

    # Create the Application builder with the token
    builder = Application.builder().token(config.TELEGRAM_TOKEN)

    # Create and attach the JobQueue
    job_queue = JobQueue() 
    builder.job_queue(job_queue) 

    # Build the application
    application = builder.build() 

    # Schedule the daily jobs
    # The time objects need to be timezone aware
    try:
        tz = pytz.timezone(config.GEETA_TIMEZONE)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Unknown timezone: {config.GEETA_TIMEZONE}. Using UTC.")
        tz = pytz.utc
        
    # The run_daily method is correct here
    # 7 AM to 10 AM (local time, based on GEETA_TIMEZONE)
    job_queue.run_daily(open_geeta_window, time(hour=7, minute=0, second=0, tzinfo=tz))
    job_queue.run_daily(close_geeta_window, time(hour=10, minute=0, second=0, tzinfo=tz))

    # --- Register Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    # Combined handler for feature toggling
    application.add_handler(CommandHandler(["meme", "shayari", "geeta"], toggle_feature_command)) 
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    # Message handler for all text that is NOT a command
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)) 
    application.add_error_handler(error_handler)

    # Run the bot
    logger.info("Niyati is starting... ✨")
    # Start the bot, which automatically starts the job_queue
    application.run_polling()

if __name__ == "__main__":
    main()
