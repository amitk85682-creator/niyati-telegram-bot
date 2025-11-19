import logging
import asyncio # Added for sleep in broadcast
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
    """Sets the Geeta window flag to True."""
    global GEETA_WINDOW_OPEN
    GEETA_WINDOW_OPEN = True
    logger.info("Geeta window is now OPEN.")

async def close_geeta_window(context: ContextTypes.DEFAULT_TYPE):
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
        # Example: /meme on -> command="meme", state="on"
        # Ensure your command string parsing matches what user types
        full_text = update.message.text.split()
        if len(full_text) < 2:
             raise ValueError
             
        command = full_text[0].lstrip('/').split('@')[0] # e.g., 'meme'
        state = full_text[1].lower() # e.g., 'on'
        
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
    
    # Config me ADMIN_IDS list of integers honi chahiye
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
        
        status_msg = await update.message.reply_text(f"Broadcast starting for {len(all_user_ids)} users...")

        for uid in all_user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=content, parse_mode=ParseMode.HTML)
                sent_count += 1
                # Thoda wait karo taki telegram block na kare (FloodWait prevention)
                await asyncio.sleep(0.05) 
            except TelegramError as e:
                logger.error(f"Broadcast failed for user {uid}: {e}")
        
        await context.bot.edit_message_text(chat_id=user_id, message_id=status_msg.message_id, text=f"Done! Message {sent_count}/{len(all_user_ids)} users ko bhej diya hai. ✅")

    except (IndexError, ValueError):
        await update.message.reply_text("Aise use karo: `/broadcast <PIN> <Your Message>`")

# --- Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return 

    chat = update.effective_chat
    user = update.effective_user
    text = message.text

    mode = "private" if chat.type == Chat.PRIVATE else "group"
    
    # Case insensitive check for bot username
    if mode == 'group':
        if f"@{config.BOT_USERNAME.lower()}" not in text.lower():
            return

    prefs = {}
    if mode == 'private':
        db.get_or_create_user(user.id, user.first_name)
        # Prefs handle karo agar None return ho toh default set karo
        prefs = db.get_user_prefs(user.id) 
        if not prefs:
            prefs = {"memes": True, "shayari": True, "geeta": True}

    reply_text = persona.get_reply(text, mode, prefs, GEETA_WINDOW_OPEN)
    
    await message.reply_text(reply_text)

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(context.error, TelegramError) and update and hasattr(update, 'effective_chat') and update.effective_chat:
        try:
            chat_id = update.effective_chat.id
            await context.bot.send_message(chat_id, "Sorry yaar, meri galti... kuch toh gadbad ho gayi. 🫶")
        except Exception as e:
            logger.error(f"Failed to send error acknowledgement: {e}")

# --- Main Function ---
def main():
    """Start the bot."""
    # Database initialize
    db.init_db()

    # Application Builder
    builder = Application.builder().token(config.TELEGRAM_TOKEN)
    application = builder.build()

    # Job Queue Setup (Correct way for v20+)
    job_queue = application.job_queue

    if job_queue:
        tz = pytz.timezone(config.GEETA_TIMEZONE)
        # Tasks ko async def banana zaroori hai upar
        job_queue.run_daily(open_geeta_window, time(hour=7, minute=0, second=0, tzinfo=tz))
        job_queue.run_daily(close_geeta_window, time(hour=10, minute=0, second=0, tzinfo=tz))
    else:
        logger.error("JobQueue failed to initialize. Make sure 'python-telegram-bot[job-queue]' is installed.")

    # Handlers Add karo
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["meme", "shayari", "geeta"], toggle_feature_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Message handler LAST me hona chahiye
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.add_error_handler(error_handler)

    logger.info("Niyati is starting... ✨")
    
    # Run polling
    application.run_polling()

if __name__ == "__main__":
    main()
