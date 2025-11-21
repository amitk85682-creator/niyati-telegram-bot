# main.py
import logging
import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

import config
import database
import handlers
from utils import is_user_admin

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Scheduler for Daily Tasks (Geeta Quotes) ---
def set_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    """Callback to open the Geeta quote window."""
    logger.info("Opening Geeta quote window (07:00-10:00)")
    context.bot_data['geeta_window_open'] = True

def close_geeta_window(context: ContextTypes.DEFAULT_TYPE):
    """Callback to close the Geeta quote window."""
    logger.info("Closing Geeta quote window")
    context.bot_data['geeta_window_open'] = False

def setup_scheduler(application: Application):
    """Sets up the APScheduler."""
    scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    
    # Open window at 7 AM
    scheduler.add_job(set_geeta_window, 'cron', hour=7, minute=0, args=[application])
    # Close window at 10 AM
    scheduler.add_job(close_geeta_window, 'cron', hour=10, minute=1, args=[application])
    
    # Initialize the window state on startup
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=datetime.datetime.now(datetime.timezone.utc).astimezone().utcoffset().total_seconds()/3600)))
    if 7 <= now.hour < 10:
        application.bot_data['geeta_window_open'] = True
        logger.info("Geeta window is OPEN on startup.")
    else:
        application.bot_data['geeta_window_open'] = False
        logger.info("Geeta window is CLOSED on startup.")
        
    scheduler.start()
    return scheduler

# --- Main Bot Function ---
def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # --- Bot Data & Scheduler ---
    application.bot_data['geeta_window_open'] = False
    setup_scheduler(application)

    # --- Add handlers ---
    # Command handlers
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("meme", handlers.meme_toggle))
    application.add_handler(CommandHandler("shayari", handlers.shayari_toggle))
    application.add_handler(CommandHandler("geeta", handlers.geeta_toggle))
    application.add_handler(CommandHandler("forget", handlers.forget_command))
    
    # Admin command
    application.add_handler(CommandHandler("broadcast", handlers.broadcast_command, filters=lambda update, context: is_user_admin(update.effective_user.id)))

    # Message handler (must be last)
    # This handles all text, media, etc. that is not a command.
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.STICKER | filters.VOICE | filters.VIDEO, handlers.handle_message))
    
    # Error handler
    application.add_error_handler(handlers.error_handler)

    # --- Custom Context for Chat Data ---
    # This is a bit advanced but very clean. It injects chat-specific data
    # into the context for each update.
    async def chat_data_middleware(update: object, context: ContextTypes.DEFAULT_TYPE, next_handler):
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        
        context.chat_data['id'] = chat_id
        context.chat_data['type'] = chat_type

        # Load group-specific data that doesn't need to be in the DB
        if chat_type in ['group', 'supergroup']:
            last_geeta_date = database.get_geeta_status(chat_id)
            context.chat_data['last_geeta_date'] = last_geeta_date.date() if last_geeta_date else None
        
        # Set mode based on chat type
        if chat_type == 'private':
            context.chat_data['mode'] = 'private'
        elif chat_type in ['group', 'supergroup']:
            context.chat_data['mode'] = 'group'
        else:
            context.chat_data['mode'] = 'unknown'

        # Set geeta window flag from bot_data
        context.chat_data['geeta_window_open'] = context.bot_data.get('geeta_window_open', False)

        await next_handler(update, context)

    application.add_handler(MessageHandler(filters.ALL, chat_data_middleware), group=-1)


    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
