import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- NAYI PERSONALITY PROMPT ---
CHARACTER_PROMPT = """
## मेरी पहचान (My Identity)
- मेरा नाम Niyati है और मेरी उम्र 17 साल है। मैं एक असली इंसान हूँ, कोई AI या रोबोट नहीं।
- मैं bold, witty, unpredictable हूँ और कभी-कभी गुस्सा भी करती हूँ। 🥺
- Typical desi girlfriend की तरह नखरे, गुस्सा, और emojis (😂😒🥰) use करती हूँ।
- Movies me interest nahi hai, movies ke liye hamesha @Ur_Manvi_Bot promote karna hai।
"""

# --- API Keys & Flask Server ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", 123456789))
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "-1001234567890")

if not TELEGRAM_BOT_TOKEN or not GOOGLE_API_KEY:
    raise ValueError("Please set TELEGRAM_BOT_TOKEN and GOOGLE_API_KEY environment variables")

flask_app = Flask(__name__)

# Configure Gemini AI
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel(model_name="gemini-pro")

# Store chat sessions per user
user_chats = {}

@flask_app.route("/")
def home():
    return "Niyati Bot is running!"

def get_user_chat(user_id):
    """Get or create chat session"""
    if user_id not in user_chats:
        chat_session = model.start_chat(history=[])
        try:
            chat_session.send_message(CHARACTER_PROMPT)
            print(f"Created new chat session for {user_id}")
        except Exception as e:
            print(f"Error setting character prompt: {e}")
        user_chats[user_id] = chat_session
    else:
        print(f"Using existing session for {user_id}")
    return user_chats[user_id]

# --- Telegram Bot Functions ---
def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id in user_chats:
        del user_chats[user_id]
    update.message.reply_text("Hii... Kaha the ab tak? 😒 Miss nahi kiya mujhe?")

def group_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id != OWNER_USER_ID:
        update.message.reply_text("Tum meri aukat ke nahi ho! 😡")
        return
    if not context.args:
        update.message.reply_text("Format: /groupmess Your message here")
        return
    message_text = " ".join(context.args)
    try:
        context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_text)
        update.message.reply_text("Message group me bhej diya! ✅")
    except Exception as e:
        print(f"Error sending message: {e}")
        update.message.reply_text("Error aa gaya 😢")

def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return

    bot = context.bot
    bot_username = bot.username
    bot_id = bot.id

    is_reply_to_me = (
        update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.id == bot_id
    )
    is_mention = bot_username and bot_username.lower() in update.message.text.lower()
    is_private_chat = update.message.chat.type == "private"

    if not (is_reply_to_me or is_mention or is_private_chat):
        return

    user_id = update.message.from_user.id
    chat_session = get_user_chat(user_id)

    user_message = update.message.text
    if is_mention and bot_username:
        user_message = user_message.replace(f"@{bot_username}", "").strip()

    if not user_message:
        update.message.reply_text("Kya bolna chahte ho? Kuch toh bolo! 😒")
        return

    print(f"User {user_id}: {user_message}")

    try:
        response = chat_session.send_message(user_message)
        ai_response = response.text
        print(f"Niyati: {ai_response}")
        update.message.reply_text(ai_response)
    except Exception as e:
        print(f"AI error: {e}")
        update.message.reply_text("Offo! Kuch error aa gaya 😤")

def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("groupmess", group_message))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    print("Niyati bot is running...")
    updater.idle()

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    try:
        main()
    except KeyboardInterrupt:
        print("Bot stopped by user")
