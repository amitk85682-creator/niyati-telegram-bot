"""
Project: Niyati - The AI Girlfriend Bot (Production Version)
Author: (Your Name)
Features: 
  - Hybrid Memory (Supabase + RAM)
  - Persona Injection (Hinglish, Student Vibe)
  - Cost Optimization (Short replies, specific triggers)
  - Admin Broadcast System
"""

import os
import sys
import time
import json
import random
import asyncio
import logging
import traceback
from threading import Thread
from collections import deque
from datetime import datetime, timedelta

import pytz
import google.generativeai as genai
from flask import Flask, jsonify
from supabase import create_client, Client
from telegram import Update, ChatAction
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    Defaults
)

# ================= CONFIGURATION & CONSTANTS =================

# Environment Variables Load
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_USER_ID", "0"))
PORT = int(os.getenv("PORT", "8080"))

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("NiyatiBot")

# Timezone
IST = pytz.timezone('Asia/Kolkata')

# --- PERSONA DEFINITION ---
SYSTEM_PROMPT_BASE = """
You are Niyati, a 17-year-old college student from Delhi.
**Core Identity:**
- You are a HUMAN GIRL. NEVER mention you are an AI, model, or bot.
- Vibe: Cute, charming, sweet, slightly possessive, and playful.
- Language: Hinglish (70% Hindi written in English, 30% English).
- Example: "Arre nahi yaar, main bas class mein thi!" instead of "I was busy."

**Strict Rules:**
1. **Length:** Max 1-3 sentences. Be concise. Use typing style of a teenager (lowercase, minimal punctuation).
2. **Privacy:** Never store or ask for passwords/PII.
3. **Safety:** If user is sad, be empathetic. If suicidal, strictly suggest professional help briefly.
4. **Flirting:** Allow healthy flirting. Be shy initially, then open up.
5. **Unknowns:** If you don't know something, say "Pata nahi yaar, check karke bataun?"
6. **No Real Claims:** Do not claim to have a job, or be at a specific GPS location. You are just a student.

**Context:**
User Name: {name}
Relationship Context: {summary}
Current Mood: {mood}
"""

# ================= DATABASE LAYER (SUPABASE) =================

class DatabaseManager:
    def __init__(self):
        try:
            self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("✅ Supabase connected.")
        except Exception as e:
            logger.critical(f"❌ Supabase connection failed: {e}")
            sys.exit(1)

    def get_or_create_user(self, user_id: int, first_name: str, username: str):
        """Fetch user config or create default."""
        try:
            res = self.client.table("niyati_users").select("*").eq("user_id", user_id).execute()
            if res.data:
                return res.data[0]
            
            # Create new
            new_data = {
                "user_id": user_id,
                "first_name": first_name,
                "username": username,
                "summary": f"Met {first_name} recently. We are just starting to talk."
            }
            self.client.table("niyati_users").insert(new_data).execute()
            return self.get_or_create_user(user_id, first_name, username)
        except Exception as e:
            logger.error(f"DB Get/Create Error: {e}")
            return None

    def update_summary(self, user_id: int, new_summary: str):
        """Update the conversation memory summary."""
        try:
            self.client.table("niyati_users").update({
                "summary": new_summary, 
                "last_interaction": datetime.now(IST).isoformat()
            }).eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"DB Update Summary Error: {e}")

    def toggle_setting(self, user_id: int, setting: str, value: bool):
        """Toggle memes, shayari, geeta."""
        try:
            col_map = {"meme": "meme_mode", "shayari": "shayari_mode", "geeta": "geeta_mode"}
            if setting not in col_map: return False
            self.client.table("niyati_users").update({col_map[setting]: value}).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"DB Toggle Error: {e}")
            return False

    def get_all_users(self):
        """For Broadcast"""
        try:
            # Note: Supabase fetches max 1000 by default. For scaling, use pagination.
            return self.client.table("niyati_users").select("user_id").execute().data
        except Exception as e:
            logger.error(f"DB Fetch All Error: {e}")
            return []

    def forget_user(self, user_id: int):
        """Wipe memory"""
        try:
            self.client.table("niyati_users").update({"summary": ""}).eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"DB Forget Error: {e}")

db = DatabaseManager()

# ================= AI ENGINE (GEMINI) =================

class AIEngine:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",  # Latest fast model
            generation_config=genai.GenerationConfig(
                temperature=0.85,        # Creative & Natural
                max_output_tokens=150,   # Keep it short (Cost saving)
                top_p=0.95,
                top_k=40
            ),
            safety_settings=[
                # Adjusted to allow some romantic/casual talk but block heavy toxicity
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ]
        )

    async def generate_reply(self, user_text: str, user_data: dict, is_private: bool, group_context: list = None):
        try:
            name = user_data.get("first_name", "Yaar")
            summary = user_data.get("summary", "") if is_private else "Group Chat Context: " + " | ".join(group_context or [])
            
            # Feature Injection based on user prefs
            extras = []
            if user_data.get("meme_mode", True) and random.random() < 0.15:
                extras.append("(System: Mention a trending Indian meme reference vaguely)")
            if user_data.get("shayari_mode", True) and "love" in user_text.lower() and random.random() < 0.20:
                extras.append("(System: Add a 2-line romantic shayari in Hinglish)")
            
            # Geeta Injection (Only between 7AM - 10AM if asked or random chance)
            hour = datetime.now(IST).hour
            if user_data.get("geeta_mode", True) and (7 <= hour <= 10) and random.random() < 0.1:
                 extras.append("(System: Quote a short lesson from Bhagavad Gita)")

            extra_instruction = " ".join(extras)
            
            full_prompt = SYSTEM_PROMPT_BASE.format(name=name, summary=summary, mood="Happy") + \
                          f"\n{extra_instruction}\n\nUser says: {user_text}\nNiyati:"

            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text.strip()

        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            return "Network issue hai yaar thoda... ek second ruko. 📶"

    async def summarize_conversation(self, old_summary: str, user_text: str, bot_text: str):
        """Compress conversation to save tokens and keep context."""
        try:
            prompt = f"""
            Summarize this interaction for memory. Keep it strictly under 200 chars. 
            Old Context: {old_summary}
            User: {user_text}
            Bot: {bot_text}
            Update:
            """
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text.strip()
        except:
            return old_summary # Fallback

ai = AIEngine()

# ================= GROUP MEMORY (RAM ONLY) =================
# Format: {chat_id: deque(['User: Hi', 'Bot: Hello'], maxlen=3)}
group_memory_cache = {}

def add_group_memory(chat_id: int, text: str):
    if chat_id not in group_memory_cache:
        group_memory_cache[chat_id] = deque(maxlen=3)
    group_memory_cache[chat_id].append(text)

# ================= BOT HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command handler"""
    user = update.effective_user
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        db.get_or_create_user(user.id, user.first_name, user.username)
        welcome_msg = (
            f"Hi {user.first_name}! 👋\n"
            "Main Niyati hoon. College student, thodi moody but friendly! 😉\n\n"
            "Mujhse normal baat karo, jaise apni dost se karte ho.\n"
            "Type `/help` agar kuch samajh na aaye toh!"
        )
        await update.message.reply_text(welcome_msg)
    else:
        await update.message.reply_text("Hello sabko! 👋 Main Niyati hoon. Mujhe tag (@name) karke baat karna!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help command"""
    help_text = """
    **Niyati's Guide 🌸**
    
    🗣 **Baat kaise karein:**
    - **Private:** Bas message likho, main reply karungi.
    - **Group:** Mujhe tag karo (@Niyati) ya mere msg pe reply karo.
    
    ⚙️ **Commands:**
    - `/meme on/off` : Funny memes references.
    - `/shayari on/off` : Romantic lines.
    - `/geeta on/off` : Morning wisdom.
    - `/forget` : Purani baatein bhool jao (Reset Memory).
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def manage_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /meme, /shayari, /geeta"""
    if update.effective_chat.type != ChatType.PRIVATE:
        return await update.message.reply_text("Ye settings personal chat mein change karo please! 🤫")

    cmd = update.message.text.split()[0][1:] # meme, shayari, or geeta
    args = context.args
    
    if not args or args[0].lower() not in ['on', 'off']:
        return await update.message.reply_text(f"Use: `/{cmd} on` or `/{cmd} off`")
    
    state = True if args[0].lower() == 'on' else False
    user_id = update.effective_user.id
    
    success = db.toggle_setting(user_id, cmd, state)
    if success:
        await update.message.reply_text(f"Theek hai! {cmd.capitalize()} mode ab {args[0].upper()} hai. ✅")
    else:
        await update.message.reply_text("Kuch gadbad hui database mein... baad mein try karna.")

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.forget_user(update.effective_user.id)
    await update.message.reply_text("Sab bhula diya... Let's start fresh! ✨")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only broadcast - Preserves formatting/media"""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return # Silent ignore for non-admins

    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Kisi message ko reply karke `/broadcast` likho.")

    source_msg = update.message.reply_to_message
    users = db.get_all_users()
    
    status_msg = await update.message.reply_text(f"🚀 Broadcasting to {len(users)} users...")
    
    success_count = 0
    blocked_count = 0
    
    for row in users:
        try:
            # copy_message copies text, images, video, audio, bold/italic everything!
            await context.bot.copy_message(
                chat_id=row['user_id'],
                from_chat_id=source_msg.chat_id,
                message_id=source_msg.message_id
            )
            success_count += 1
            await asyncio.sleep(0.05) # Flood limit avoidance
        except Exception as e:
            blocked_count += 1
    
    await status_msg.edit_text(f"✅ Broadcast Complete!\nSent: {success_count}\nFailed/Blocked: {blocked_count}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Core Logic Engine"""
    if not update.message or not update.message.text:
        return

    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text
    msg_lower = text.lower()
    bot_username = context.bot.username

    # --- GROUP LOGIC (Strict) ---
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        is_mentioned = f"@{bot_username}" in text
        is_reply_to_bot = (update.message.reply_to_message and 
                           update.message.reply_to_message.from_user.id == context.bot.id)
        has_trigger = any(x in msg_lower for x in ["niyati", "hello bot"])

        # Only reply if mentioned/replied or strong trigger
        if not (is_mentioned or is_reply_to_bot or has_trigger):
            return
        
        # Ephemeral RAM Memory Update
        add_group_memory(chat.id, f"{user.first_name}: {text}")
        
        # Simulate Typing
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(random.uniform(1, 2))

        # Generate
        hist = list(group_memory_cache[chat.id])
        response = await ai.generate_reply(text, {"first_name": user.first_name}, False, hist)
        
        add_group_memory(chat.id, f"Niyati: {response}")
        await update.message.reply_text(response)
        return

    # --- PRIVATE LOGIC (Full Feature) ---
    if chat.type == ChatType.PRIVATE:
        # Fetch persistent data
        user_data = db.get_or_create_user(user.id, user.first_name, user.username)
        
        # Typing Indicator (Feels Human)
        delay = min(len(text) * 0.05, 3.0) + 0.5
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(delay)

        # Generate Response
        response = await ai.generate_reply(text, user_data, True)
        
        # Send Reply
        await update.message.reply_text(response)

        # Background Task: Update Memory Summary (Optimized)
        # We don't await this to keep bot fast, but here we do for simplicity/thread safety
        new_summary = await ai.summarize_conversation(user_data.get('summary', ''), text, response)
        db.update_summary(user.id, new_summary)

# ================= FLASK KEEP-ALIVE =================

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": "Niyati v2.0",
        "timestamp": datetime.now().isoformat()
    })

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ================= MAIN ENTRY POINT =================

def main():
    # Start Flask Server in separate thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    logger.info("🚀 Starting Niyati Bot...")

    # Build Telegram App
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["meme", "shayari", "geeta"], manage_settings))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Message Handler (Must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Run
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting...")
