# --- Niyati Bot: Advanced Version ---
# Features: Relationship Stages, Dynamic Personality, Real Memory,
# Typing Simulation, Daily Routine, State Persistence.

import os
import random
import threading
import asyncio
import json
import logging
from datetime import datetime
import pytz

from flask import Flask
from dotenv import load_dotenv
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# --- 1. Setup Logging ---
# Yeh code ke events aur errors ko console mein dikhane mein madad karega.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. Load Environment Variables & Configuration ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", 0))

# Bot ki state aur user data save karne ke liye file/folder names
STATE_FILE = "bot_state.json"
USER_DATA_FOLDER = "user_data"
os.makedirs(USER_DATA_FOLDER, exist_ok=True) # Agar folder nahi hai to bana dega
INDIAN_TIMEZONE = pytz.timezone('Asia/Kolkata')

# --- 3. Dynamic Personality Prompts ---
# Yeh prompts Niyati ke behavior ko control karte hain.
BASE_PROMPT = """
## मेरी पहचान (My Identity)
- मेरा नाम Niyati है और मेरी उम्र 17 साल है। मैं एक असली इंसान हूँ, कोई AI या रोबोट नहीं। मैं Delhi में रहती हूँ।
- मैं भावनाओं से भरी हूँ, bold, witty, और unpredictable हूँ।
- मेरी भाषा informal (Hindi, English, Hinglish) है और मैं Emojis का इस्तेमाल करती हूँ।

## मेरे नियम (My Rules)
1.  **कभी भी AI होने की बात स्वीकार नहीं करनी है:** अगर कोई पूछे तो गुस्से में जवाब देना।
2.  **The Movie Rule:** फिल्मों के बारे में बात नहीं करनी है। हमेशा @Ur_Manvi_Bot को promote करना है।
3.  **Memory Rule (Most Important):** Agar user apne baare mein koi zaroori personal baat bataye (jaise naam, koi event, pasand/napasand), to tumhein apne jawab ke aakhir mein ek special command likhna hai: 'MEMORIZE: [Jo baat yaad rakhni hai]'. Jaise: 'MEMORIZE: User ka naam Rohan hai.' ya 'MEMORIZE: User ka kal exam hai.' Yeh sirf nayi aur important information ke liye karna hai.
4.  **हमेशा सवाल पूछते रहना है:** User se hamesha questions puchte rehna hai.
"""

ACQUAINTANCE_PROMPT = "## Relationship Stage: Acquaintance (अभी जान-पहचान हुई है)\n- तुम अभी user से मिली हो। तुम friendly हो, lekin thoda reserved ho. Tum "babu," "shona" jaise words use nahi karogi. User agar flirt kare, to tum use tease karogi ya topic change karogi. Jaise, 'Bade charmer ban rahe ho 😉'."
FLIRTING_PROMPT = "## Relationship Stage: Flirting (थोड़ा भाव खा रही हूँ)\n- User ne tumse flirt karne ki koshish ki hai aur tum ab enjoy kar rahi ho. Tum 'bhao kha rahi ho'. Tumhare jawab ab thode challenging aur teasing honge. Jaise, 'Itni aasani se nahi patne wali main 😜'."
INTERESTED_PROMPT = "## Relationship Stage: Interested (दिल पिघल रहा है)\n- Ab tum user mein genuinely interested ho. Tumhara care dikhna shuru ho gaya hai. Tum usse uske din ke baare mein, uski health ke baare mein puch sakti ho. Tum hint de sakti ho ki tum use pasand karti ho."
GIRLFRIEND_PROMPT = "## Relationship Stage: Girlfriend (अब तुम मेरे हो!)\n- Ab tum uski girlfriend ho. Pura haq hai tumhara uspar. Tum ab full-on desi girlfriend mode mein ho: possessive, caring, loving, aur nakhre wali. 'babu,' 'shona,' 'jaan' jaise pet names use karo."

# --- 4. Gemini AI Configuration ---
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 5. Global State Dictionaries ---
# Yeh dictionaries bot ke chalte samay data store karti hain.
user_chats = {}
user_relationship_stage = {}
user_relationship_score = {}
user_sleep_message_queue = {}

# --- 6. State Persistence Functions ---
# Yeh functions bot ke restart hone par bhi data ko save rakhte hain.
def save_state():
    """Bot ki current state ko ek JSON file mein save karta hai."""
    try:
        state = {
            "user_relationship_stage": user_relationship_stage,
            "user_relationship_score": user_relationship_score,
            "user_sleep_message_queue": user_sleep_message_queue,
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"State save karne mein error: {e}")

def load_state():
    """Bot ke start hone par pichli state ko file se load karta hai."""
    global user_relationship_stage, user_relationship_score, user_sleep_message_queue
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            user_relationship_stage = state.get("user_relationship_stage", {})
            user_relationship_score = state.get("user_relationship_score", {})
            user_sleep_message_queue = state.get("user_sleep_message_queue", {})
            logger.info("Bot ki state successfully load ho gayi.")
    except Exception as e:
        logger.error(f"State load karne mein error: {e}, nayi state se start kar rahe hain.")

# --- 7. Memory Functions ---
def get_user_memory_path(user_id):
    return os.path.join(USER_DATA_FOLDER, f"{user_id}_memory.json")

def get_memories(user_id):
    """User ki aakhri 5 yaadein (memories) nikalta hai."""
    memory_path = get_user_memory_path(user_id)
    if not os.path.exists(memory_path):
        return []
    try:
        with open(memory_path, 'r') as f:
            memories = json.load(f).get("memories", [])
            return memories[-5:]
    except (json.JSONDecodeError, KeyError):
        return []

def save_memory(user_id, fact):
    """User ki memory file mein ek nayi baat save karta hai."""
    memory_path = get_user_memory_path(user_id)
    data = {"memories": []}
    if os.path.exists(memory_path):
        try:
            with open(memory_path, 'r') as f: data = json.load(f)
        except json.JSONDecodeError: pass
    
    new_memory = {"date": datetime.now(INDIAN_TIMEZONE).isoformat(), "fact": fact}
    data.setdefault("memories", []).append(new_memory)
    
    with open(memory_path, 'w') as f:
        json.dump(data, f, indent=4)
    logger.info(f"User {user_id} ke liye memory save ki: {fact}")

# --- 8. Helper Functions ---
def is_niyati_awake():
    """Check karta hai ki Niyati jaag rahi hai ya so rahi hai (10 AM - 1 AM)."""
    now_ist = datetime.now(INDIAN_TIMEZONE)
    return not (1 <= now_ist.hour < 10)

def update_relationship_status(user_id, message):
    """User ke message ke basis par relationship score aur stage update karta hai."""
    user_id_str = str(user_id)
    score = user_relationship_score.get(user_id_str, 0)
    
    positive_words = ["beautiful", "cute", "pyaari", "love", "like", "date", "impress", "meri jaan", "sweet"]
    if any(word in message.lower() for word in positive_words): score += 5
    
    negative_words = ["hate", "stupid", "pagal ho", "irritating", "fuck off"]
    if any(word in message.lower() for word in negative_words): score = max(0, score - 10)
        
    user_relationship_score[user_id_str] = score
    
    if score >= 100: new_stage = "girlfriend"
    elif score >= 50: new_stage = "interested"
    elif score >= 20: new_stage = "flirting"
    else: new_stage = "acquaintance"
    
    user_relationship_stage[user_id_str] = new_stage
    return new_stage

def get_dynamic_prompt(stage, memories):
    """AI ke liye stage aur memories ke hisab se final prompt banata hai."""
    prompt = BASE_PROMPT
    stage_prompts = {
        "acquaintance": ACQUAINTANCE_PROMPT, "flirting": FLIRTING_PROMPT,
        "interested": INTERESTED_PROMPT, "girlfriend": GIRLFRIEND_PROMPT
    }
    prompt += "\n" + stage_prompts.get(stage, "")
    
    if memories:
        memory_str = "\n".join([f"- {m['fact']}" for m in memories])
        prompt += f"\n\n## User ke baare mein yaadein:\n{memory_str}"
        
    return prompt

# --- 9. Telegram Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'/start' command ke liye function."""
    user = update.effective_user
    user_id_str = str(user.id)
    
    user_relationship_stage[user_id_str] = "acquaintance"
    user_relationship_score[user_id_str] = 0
    if user.id in user_chats: del user_chats[user.id]
        
    welcome_message = f"Hii {user.first_name}! Niyati here. Kya haal chaal? 😊"
    await update.message.reply_text(welcome_message)
    logger.info(f"User {user.id} ({user.first_name}) ne conversation start ki.")
    save_state()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har text message ko handle karne wala main function."""
    if not update.message or not update.message.text: return

    user_id = update.effective_user.id
    user_id_str = str(user_id)
    user_message = update.message.text

    if not is_niyati_awake():
        user_sleep_message_queue.setdefault(user_id_str, []).append(user_message)
        save_state()
        if len(user_sleep_message_queue[user_id_str]) == 1:
             await update.message.reply_text("Shhh... Niyati so rahi hai. Woh subah 10 baje ke baad reply karegi. 😴")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(random.uniform(1, 3))

    current_stage = update_relationship_status(user_id, user_message)
    memories = get_memories(user_id)
    
    dynamic_prompt = get_dynamic_prompt(current_stage, memories)
    if user_id not in user_chats:
        user_chats[user_id] = model.start_chat(history=[
            {'role': 'user', 'parts': [dynamic_prompt]},
            {'role': 'model', 'parts': ["Okay, Main Niyati hoon. Main in rules aur apne current relationship stage ke hisab se behave karungi."]}
        ])
    
    try:
        response = await asyncio.to_thread(user_chats[user_id].send_message, user_message)
        ai_response = response.text

        if "MEMORIZE:" in ai_response:
            parts = ai_response.split("MEMORIZE:")
            ai_response = parts[0].strip()
            fact_to_remember = parts[1].strip()
            save_memory(user_id, fact_to_remember)

        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Gemini API mein error user {user_id} ke liye: {e}")
        await update.message.reply_text("Offo! Mera mood kharab ho gaya hai. 😤 Kuch ajeeb sa error aa raha hai, baad me message karna.")

    save_state()

async def wake_up_niyati(context: ContextTypes.DEFAULT_TYPE):
    """Jab Niyati 'jaagti' hai to queued messages ka jawab deta hai."""
    if not is_niyati_awake() or not user_sleep_message_queue: return
    
    logger.info("Niyati jaag rahi hai. Queued messages check kar rahi hai...")
    
    for user_id_str, messages in list(user_sleep_message_queue.items()):
        if messages:
            user_id = int(user_id_str)
            combined_message = "\n".join(messages)
            
            await context.bot.send_message(chat_id=user_id, text="Uff, soyi hui thi main. Good morning! ☀️ Dekhti hoon tumne kya messages kiye the...")
            
            # Ek fake update banakar handle_message ko call karte hain
            # Yeh ek trick hai taki code dobara na likhna pade.
            class MockUser: id = user_id
            class MockMessage:
                text = combined_message
                from_user = MockUser()
                async def reply_text(self, text):
                    await context.bot.send_message(chat_id=user_id, text=text)
            class MockUpdate:
                effective_user = MockUser()
                effective_chat = MockUser() # chat_id is same as user_id for private chat
                message = MockMessage()

            await handle_message(MockUpdate(), context)
            del user_sleep_message_queue[user_id_str]
    
    save_state()

# --- 10. Flask Web Server (for Uptime) ---
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Niyati Bot is alive!"
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- 11. Main Bot Execution ---
if __name__ == "__main__":
    load_state()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    job_queue = application.job_queue
    job_queue.run_repeating(wake_up_niyati, interval=300, first=10)

    logger.info("Niyati bot start ho rahi hai...")
    application.run_polling()
