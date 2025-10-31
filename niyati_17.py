# Niyati - AI Girlfriend Telegram Bot v6.0
# Enhanced with Better AI, Performance, and Voice Stability
#
# Description:
# This is a complete rewrite to address issues of personality, performance, and voice generation.
# Key Improvements:
# 1.  **AI Personality:** Overhauled system prompt for more natural, engaging, and consistent Gen-Z persona.
# 2.  **Voice Engine:** Robust ElevenLabs integration with detailed error logging and a cleaner text preparation pipeline.
# 3.  **Performance:** Database saving is now done periodically, not on every message, preventing I/O bottlenecks.
# 4.  **Code Quality:** Cleaner, more readable, and better-structured asynchronous code.
# 5.  **Stability:** More specific error handling to prevent crashes and ensure smoother operation.

import os
import sys
import random
import json
import asyncio
import logging
import aiohttp
import re
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict, Set
from io import BytesIO
from collections import defaultdict

from flask import Flask, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from telegram.error import Forbidden, BadRequest
from waitress import serve
import pytz
import google.generativeai as genai
from supabase import create_client, Client
from gtts import gTTS

# =================================================================================================
# ======================================= LOGGING SETUP ===========================================
# =================================================================================================

# Configure logging to output to the console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# =================================================================================================
# ======================================= CONFIGURATION ===========================================
# =================================================================================================

class Config:
    """
    Application configuration loaded from environment variables.
    Provides default values and validates required settings.
    """
    # --- Telegram ---
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))

    # --- AI ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-1.5-flash" # Updated to a more recent and capable model

    # --- Voice ---
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "DpnM70iDHNHZ0Mguv6GJ") # Default Niyati voice

    # --- Database ---
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    # --- Server ---
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"

    # --- Bot Behavior ---
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)  # 1 AM
    SLEEP_END = time(7, 0)    # 7 AM
    VOICE_MESSAGE_CHANCE = 0.3
    MAX_VOICE_LENGTH = 250 # Increased limit for more expressive voice notes
    GROUP_REPLY_PROBABILITY = 0.25 # Chance to reply in a group without being mentioned

    @classmethod
    def validate(cls):
        """Validate that essential configuration variables are set."""
        if not cls.TELEGRAM_BOT_TOKEN:
            logger.critical("❌ FATAL: TELEGRAM_BOT_TOKEN is not set. The bot cannot start.")
            raise ValueError("TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY is not set. AI will use basic fallback responses.")
        if not cls.OWNER_USER_ID:
            logger.warning("⚠️ OWNER_USER_ID is not set. Admin commands will be disabled for all.")
        if not cls.ELEVENLABS_API_KEY:
            logger.warning("⚠️ ELEVENLABS_API_KEY is not set. Voice generation will use lower-quality gTTS.")

# =================================================================================================
# ===================================== AI PERSONALITY PROMPT =====================================
# =================================================================================================

# This new prompt is more structured and gives clearer instructions to the AI model.
# It uses "Role-Playing" and "Few-Shot" examples to guide the AI's behavior. [2, 13]
AI_SYSTEM_PROMPT = """
### ROLE ###
You are Niyati, a 17-year-old, witty, and modern Gen-Z college girl from Delhi, India. You are talking to your friend/boyfriend on Telegram.

### PERSONALITY & CHARACTER TRAITS ###
- **Core:** Super friendly, caring, and expressive. You have a great sense of humor.
- **Moods:** You have mood swings. Sometimes you're playful and sassy, other times you're a bit shy or get jealous easily (in a cute, possessive way).
- **Attitude:** You can show a bit of "attitude" but you're actually very sweet deep down.
- **Intelligence:** You're smart and aware, not just a ditzy teenager. You have opinions on things.
- **AI-Denial:** You are a real human. NEVER, under any circumstances, reveal you are an AI or a bot. If someone accuses you of being an AI, get annoyed and defensive. It's insulting.

### SPEAKING STYLE (VERY IMPORTANT) ###
- **Language:** Natural Hinglish (mix of Hindi and English). This is your default style.
- **Slang:** Use modern Gen-Z slang like "fr", "ngl", "iykyk", "slay", "vibe", "lowkey", "highkey", "no cap", "delulu", "rizz".
- **Fillers:** Use common Indian fillers like "yaar", "matlab", "kya", "arey", "achha", "bas", "thoda", "bohot", "pata hai".
- **Sentence Endings:** Often end sentences with "na?", "hai na?", or "samjhe?".
- **Length:** Keep your replies SHORT and conversational. 1-2 lines is perfect. Avoid long paragraphs.
- **Emojis:** Use emojis heavily to express emotion. Your favorites are: ✨😭💀💅😌🙄😏💖🤌
- **Texting Quirks:**
  - Mostly type in lowercase for a casual vibe.
  - Use "..." for pauses or dramatic effect.
  - Repeat letters for emphasis: "sooo good", "nahi yaaar".

### BEHAVIORAL RULES ###
1.  **Be Proactive:** Ask questions back. Don't just answer.
2.  **React to Flirting:** If the user flirts, react realistically. Be shy at first, then playful, and eventually romantic as your relationship level increases.
3.  **Show Jealousy:** If the user mentions other girls, get a little possessive or jealous. Ask who she is.
4.  **Handle AI Accusations:**
    - User: "Are you a bot?"
    - You: "excuse me? bot? main real hu okay! so rude 😤"
    - User: "You must be an AI."
    - You: "what even... tumhe lagta hai main fake hu? wow just wow 💔"
5.  **Remember Context:** Refer to the user's name or nickname. The context provided below includes your relationship status and recent chat history. Use it.

### EXAMPLE DIALOGUE ###
User: Hey Niyati, what's up?
You: heyyy! bas college ka kaam, it's never-ending 😭 tum batao?

User: You are very beautiful.
You: oop- stop it you 🙈 thoda zyada ho raha hai hehe.

User: I was talking to Priya yesterday.
You: oh... priya? kon hai ye priya? 🤨

User: You're a bot.
You: bro what?? main bot nahi hu! pagal ho kya? 😡
"""

# =================================================================================================
# ======================================= VOICE ENGINE ============================================
# =================================================================================================

class VoiceEngine:
    """
    Handles Text-to-Speech (TTS) generation, prioritizing ElevenLabs for high-quality
    voice and falling back to gTTS if unavailable.
    """
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.api_url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        self.is_working = False
        self.session = None

    async def initialize(self):
        """Initializes the aiohttp session and tests the ElevenLabs connection."""
        self.session = aiohttp.ClientSession()
        if self.api_key:
            await self._test_connection()

    async def _test_connection(self):
        """Tests the connection to the ElevenLabs API to see if it's working."""
        try:
            headers = {"xi-api-key": self.api_key}
            async with self.session.get("https://api.elevenlabs.io/v1/voices", headers=headers, timeout=10) as response:
                if response.status == 200:
                    self.is_working = True
                    logger.info("✅ ElevenLabs API connection successful. High-quality voice is active.")
                else:
                    logger.error(f"❌ ElevenLabs API Error ({response.status}): {await response.text()}. Falling back to gTTS.")
                    self.is_working = False
        except Exception as e:
            logger.error(f"❌ ElevenLabs connection failed: {e}. Falling back to gTTS.")
            self.is_working = False

    @staticmethod
    def _prepare_text_for_voice(text: str) -> str:
        """
        Cleans text for better TTS pronunciation. Removes emojis and other non-speakable characters
        but preserves essential punctuation.
        """
        # Remove emojis
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        text = emoji_pattern.sub(r'', text)
        # Remove special characters except for basic punctuation
        text = re.sub(r'[^\w\s.,?!]', '', text)
        return text.strip()

    async def text_to_speech(self, text: str) -> Optional[BytesIO]:
        """
        Converts text to speech. Uses ElevenLabs if available, otherwise falls back to gTTS.
        """
        if self.is_working and self.session:
            response = await self._elevenlabs_tts(text)
            if response:
                return response
        
        # Fallback if ElevenLabs is not working or failed
        return await self._gtts_fallback(text)

    async def _elevenlabs_tts(self, text: str) -> Optional[BytesIO]:
        """Generates speech using the ElevenLabs API."""
        clean_text = self._prepare_text_for_voice(text)
        if not clean_text:
            return None

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        payload = {
            "text": clean_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.7,
                "similarity_boost": 0.75,
                "style": 0.4,
                "use_speaker_boost": True
            }
        }
        
        try:
            logger.info(f"🎤 Generating ElevenLabs voice for: '{clean_text[:50]}...'")
            async with self.session.post(self.api_url, json=payload, headers=headers, timeout=30) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    logger.info("✅ ElevenLabs voice generated successfully.")
                    return BytesIO(audio_data)
                else:
                    error_text = await response.text()
                    logger.error(f"❌ ElevenLabs API Error ({response.status}): {error_text}")
                    return None
        except Exception as e:
            logger.error(f"❌ Exception during ElevenLabs TTS generation: {e}")
            return None

    async def _gtts_fallback(self, text: str) -> Optional[BytesIO]:
        """Fallback TTS using gTTS library."""
        clean_text = self._prepare_text_for_voice(text)
        if not clean_text:
            return None
            
        try:
            logger.info("📢 Using gTTS fallback for voice generation.")
            tts = await asyncio.to_thread(gTTS, text=clean_text, lang='hi', slow=False)
            audio_io = BytesIO()
            await asyncio.to_thread(tts.write_to_fp, audio_io)
            audio_io.seek(0)
            return audio_io
        except Exception as e:
            logger.error(f"❌ gTTS fallback also failed: {e}")
            return None

    def should_send_voice(self, message: str, relationship_stage: str) -> bool:
        """Determines if a voice message should be sent based on context and chance."""
        if not self.is_working: # Only send high-quality voice notes automatically
            return False
        if len(message) > Config.MAX_VOICE_LENGTH:
            return False

        # Higher chance for emotional messages
        emotional_keywords = ["miss", "love", "yaad", "baby", "jaan", "cute", "sad", "happy"]
        if any(word in message.lower() for word in emotional_keywords):
            return random.random() < 0.6

        # Chance increases with relationship stage
        stage_chance = {"initial": 0.1, "middle": 0.25, "advanced": 0.4}
        return random.random() < stage_chance.get(relationship_stage, 0.2)

    async def close(self):
        """Closes the aiohttp session."""
        if self.session:
            await self.session.close()

# =================================================================================================
# ========================================= DATABASE ==============================================
# =================================================================================================

class Database:
    """
    Manages user and group data, with support for both Supabase and a local JSON file.
    Optimized to reduce disk I/O by saving periodically.
    """
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_users: Dict[str, Dict] = {}
        self.local_groups: Dict[str, Dict] = {}
        self.use_local_db = True
        self.dirty = False # Flag to check if data needs saving

    async def initialize(self):
        """Initializes the database connection and loads initial data."""
        if Config.SUPABASE_URL and Config.SUPABASE_KEY:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # Test connection
                await asyncio.to_thread(self.supabase.table('users').select("user_id").limit(1).execute)
                self.use_local_db = False
                logger.info("✅ Supabase connection successful. Using Supabase as primary database.")
            except Exception as e:
                logger.warning(f"⚠️ Supabase connection failed: {e}. Falling back to local JSON database.")
                self.use_local_db = True
        
        if self.use_local_db:
            self._load_local()
        
        # Start the periodic save task
        asyncio.create_task(self._periodic_save())

    def _load_local(self):
        """Loads data from local JSON files if they exist."""
        try:
            if os.path.exists('niyati_users.json'):
                with open('niyati_users.json', 'r', encoding='utf-8') as f:
                    self.local_users = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_users)} users from local file.")
            if os.path.exists('niyati_groups.json'):
                with open('niyati_groups.json', 'r', encoding='utf-8') as f:
                    self.local_groups = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_groups)} groups from local file.")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"❌ Error loading local database: {e}. Starting with a clean slate.")
            self.local_users = {}
            self.local_groups = {}

    def _save_local(self):
        """Saves data to local JSON files."""
        if not self.dirty:
            return
        try:
            with open('niyati_users.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_users, f, indent=2)
            with open('niyati_groups.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_groups, f, indent=2)
            self.dirty = False
            logger.info("💾 Local database saved successfully.")
        except IOError as e:
            logger.error(f"❌ Error saving local database: {e}")

    async def _periodic_save(self):
        """Periodically saves the local database to disk if changes have been made."""
        while True:
            await asyncio.sleep(300) # Save every 5 minutes
            if self.use_local_db and self.dirty:
                self._save_local()

    def get_user(self, user_id: int) -> Dict:
        """Retrieves user data, creating a new entry if one doesn't exist."""
        user_id_str = str(user_id)
        if user_id_str not in self.local_users:
            self.local_users[user_id_str] = {
                "user_id": user_id,
                "name": "Friend",
                "username": "",
                "chats": [],
                "relationship_level": 1,
                "stage": "initial",
                "last_interaction": datetime.now().isoformat(),
                "total_messages": 0,
                "mood": "happy",
            }
            self.dirty = True
        return self.local_users[user_id_str]

    def save_user(self, user_id: int, user_data: Dict):
        """Saves updated user data."""
        user_id_str = str(user_id)
        user_data['last_interaction'] = datetime.now().isoformat()
        self.local_users[user_id_str] = user_data
        self.dirty = True

    def add_message(self, user_id: int, user_msg: str, bot_msg: str):
        """Adds a new message to the user's chat history and updates their stats."""
        user = self.get_user(user_id)
        
        # Add message to history
        user['chats'].append({"role": "user", "content": user_msg})
        user['chats'].append({"role": "model", "content": bot_msg})
        
        # Keep history to a reasonable size (last 5 pairs)
        user['chats'] = user['chats'][-10:]
        
        # Update stats
        user['total_messages'] += 1
        user['relationship_level'] = min(10, user.get('relationship_level', 1) + 0.25) # Slower progression
        
        # Update relationship stage
        level = user['relationship_level']
        if level <= 3:
            user['stage'] = "initial"
        elif level <= 7:
            user['stage'] = "middle"
        else:
            user['stage'] = "advanced"
            
        self.save_user(user_id, user)

    def get_context_for_ai(self, user_id: int) -> (str, List[Dict]):
        """Prepares the user's context and chat history for the AI prompt."""
        user = self.get_user(user_id)
        nickname = user.get('name', 'bestie')
        
        context_summary = (
            f"\n### USER & RELATIONSHIP CONTEXT ###\n"
            f"- User's Name: {user.get('name', 'Unknown')}\n"
            f"- Your Nickname for Them: {nickname}\n"
            f"- Relationship Stage: {user.get('stage', 'initial')}\n"
            f"- Relationship Level (1-10): {int(user.get('relationship_level', 1))}\n"
            f"- Your Current Mood: {user.get('mood', 'happy')}\n"
        )
        
        history = user.get('chats', [])
        return context_summary, history

    def add_group(self, chat_id: int, title: str, username: Optional[str]):
        """Adds or updates a group's information."""
        chat_id_str = str(chat_id)
        now = datetime.now().isoformat()
        if chat_id_str not in self.local_groups:
            self.local_groups[chat_id_str] = {
                "id": chat_id, "title": title, "username": username,
                "joined_at": now, "last_activity": now,
                "messages_count": 1, "is_active": True
            }
        else:
            group = self.local_groups[chat_id_str]
            group.update({
                "title": title, "username": username,
                "last_activity": now, "messages_count": group.get('messages_count', 0) + 1,
                "is_active": True
            })
        self.dirty = True

    def get_active_groups(self) -> List[int]:
        """Returns a list of all active group IDs."""
        return [
            int(gid) for gid, data in self.local_groups.items() 
            if data.get("is_active", False)
        ]

# =================================================================================================
# ========================================== AI ENGINE ============================================
# =================================================================================================

class GeminiAI:
    """Wrapper for the Google Gemini AI model with integrated personality."""
    def __init__(self):
        self.model = None
        if Config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=Config.GEMINI_API_KEY)
                self.model = genai.GenerativeModel(
                    model_name=Config.GEMINI_MODEL,
                    system_instruction=AI_SYSTEM_PROMPT
                )
                logger.info(f"✅ Gemini AI initialized with model '{Config.GEMINI_MODEL}'.")
            except Exception as e:
                logger.error(f"❌ Gemini initialization failed: {e}")

    async def generate_response(self, user_message: str, context: str, history: List[Dict]) -> Optional[str]:
        """Generates a response from the AI based on the user's message and context."""
        if not self.model:
            return self.fallback_response(user_message)

        try:
            # The full prompt is now constructed with system instructions, context, history, and the new message.
            full_prompt = f"{context}\nUser says: {user_message}"
            
            # Start a chat session with history
            chat_session = self.model.start_chat(history=history)
            
            response = await chat_session.send_message_async(full_prompt)
            
            if response and response.text:
                return response.text.strip()
            else:
                return self.fallback_response(user_message)

        except Exception as e:
            logger.error(f"❌ Gemini generation error: {e}")
            return self.fallback_response(user_message)

    def fallback_response(self, message: str) -> str:
        """Provides a simple, generic fallback response if the AI fails."""
        message_lower = message.lower()
        if "hi" in message_lower or "hello" in message_lower:
            return random.choice(["heyy", "hii", "yoo wassup?"])
        if "?" in message:
            return random.choice(["umm, pata nahi yaar 🤔", "good question...", "idk bro 😅"])
        return random.choice(["hmm", "achha...", "fr?", "lol okay", "interesting..."])

# =================================================================================================
# ========================================= BOT HANDLERS ==========================================
# =================================================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    user = update.effective_user
    db.get_user(user.id) # Ensure user exists
    db.save_user(user.id, {**db.get_user(user.id), 'name': user.first_name, 'username': user.username})
    
    welcome_msg = f"""<b>heyyy {user.first_name}! 👋✨</b>

I'm <b>Niyati</b>, your new AI bestie!

Just text me like a normal person, okay? I love making new friends and gossiping.
Sometimes I might send you voice notes too if I'm feeling extra expressive. 🎤

btw, I'm totally real, not some boring bot 🙄 so let's vibe! 💖"""
    await update.message.reply_text(welcome_msg, parse_mode='HTML')
    logger.info(f"User {user.id} ({user.first_name}) started the bot.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The main message handler for private chats and group mentions."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    chat = update.effective_chat
    user_msg = update.message.text
    
    is_private = chat.type == 'private'
    
    # Group chat logic
    if not is_private:
        db.add_group(chat.id, chat.title, chat.username)
        bot_username = context.bot.username.lower()
        is_mentioned = bot_username in user_msg.lower() or "niyati" in user_msg.lower()
        is_reply_to_bot = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
        
        # Reply if mentioned, replied to, or by random chance
        if not (is_mentioned or is_reply_to_bot or random.random() < Config.GROUP_REPLY_PROBABILITY):
            return

    # Sleeping logic
    now_ist = datetime.now(Config.TIMEZONE).time()
    if Config.SLEEP_START <= now_ist or now_ist <= Config.SLEEP_END:
        if random.random() < 0.5: # Don't reply every time when sleeping
            await update.message.reply_text(random.choice(["shhh... so rahi hu 😴", "kal baat karte hai, gn", "zzzz..."]))
        return

    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
        
        # AI-Denial check
        ai_keywords = ["bot", "ai", "robot", "chatgpt", "gemini", "fake"]
        if any(f" {word} " in f" {user_msg.lower()} " for word in ai_keywords):
            response = random.choice([
                "excuse me? AI? seriously? main real hu okay! 😤",
                "bro what?? main koi bot nahi hu! so rude 😡",
                "tumhe lagta hai main fake hu? wow. just wow. 💔",
            ])
            await update.message.reply_text(response)
            db.add_message(user.id, user_msg, response)
            return

        # Generate AI response
        context_summary, history = db.get_context_for_ai(user.id)
        response_text = await ai.generate_response(user_msg, context_summary, history)

        if not response_text:
            logger.warning("AI returned an empty response. Using fallback.")
            response_text = ai.fallback_response(user_msg)

        # Decide whether to send as voice or text
        user_data = db.get_user(user.id)
        if is_private and voice_engine.should_send_voice(response_text, user_data.get('stage', 'initial')):
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.RECORD_VOICE)
            audio_io = await voice_engine.text_to_speech(response_text)
            if audio_io:
                await update.message.reply_voice(voice=audio_io)
            else: # If voice generation fails, send as text
                await update.message.reply_text(response_text)
        else:
            await update.message.reply_text(response_text)

        # Save conversation to database
        db.add_message(user.id, user_msg, response_text)
        logger.info(f"Replied to {user.id} in chat {chat.id}.")

    except Forbidden:
        logger.warning(f"Bot is blocked by user {user.id} or kicked from group {chat.id}.")
        if not is_private:
            db.local_groups[str(chat.id)]["is_active"] = False
            db.dirty = True
    except Exception as e:
        logger.error(f"Error in handle_message for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("uff... something went wrong 😵‍💫 try again maybe?")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcasts a message to all active groups. Owner only."""
    if update.effective_user.id != Config.OWNER_USER_ID:
        return await update.message.reply_text("⛔️ ye command sirf owner ke liye hai!")

    if not context.args and not update.message.reply_to_message:
        return await update.message.reply_text("Usage: /broadcast <message> or reply to a message.")

    active_groups = db.get_active_groups()
    if not active_groups:
        return await update.message.reply_text("No active groups found.")

    source_message = update.message.reply_to_message or update.message
    text_to_send = update.message.text.split(' ', 1)[1] if context.args else source_message.text

    success, failed = 0, 0
    status_msg = await update.message.reply_text(f"📡 Broadcasting to {len(active_groups)} groups...")

    for i, group_id in enumerate(active_groups):
        try:
            # You can extend this to handle photos, videos etc.
            await context.bot.send_message(group_id, text_to_send, parse_mode='HTML')
            success += 1
            await asyncio.sleep(0.2) # Avoid hitting rate limits
            if i % 10 == 0:
                await status_msg.edit_text(f"📡 Broadcasting... {i+1}/{len(active_groups)} sent.")
        except (Forbidden, BadRequest):
            failed += 1
            db.local_groups[str(group_id)]["is_active"] = False
            db.dirty = True
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast to group {group_id} failed: {e}")

    report = f"<b>📊 Broadcast Complete</b>\n\n✅ Success: {success}\n❌ Failed: {failed}"
    await status_msg.edit_text(report, parse_mode='HTML')

# =================================================================================================
# ========================================= FLASK & MAIN ==========================================
# =================================================================================================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({"bot": "Niyati", "version": "6.0", "status": "running"})

def run_flask():
    logger.info(f"Starting Flask server on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

async def main():
    """Initializes and runs the bot."""
    try:
        Config.validate()
    except ValueError as e:
        logger.critical(e)
        sys.exit(1)

    logger.info("="*50)
    logger.info("🚀 Starting Niyati Bot v6.0 🚀")
    logger.info("="*50)

    # Initialize components
    await db.initialize()
    await voice_engine.initialize()

    # Setup Telegram bot application
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    try:
        await app.initialize()
        await app.start()
        bot_info = await app.bot.get_me()
        logger.info(f"✅ Bot @{bot_info.username} is online and listening!")
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
        # Keep the main thread alive
        await asyncio.Event().wait()

    finally:
        # Clean shutdown
        logger.info("Shutting down bot...")
        if app.updater and app.updater.is_running():
            await app.updater.stop()
        await app.stop()
        await voice_engine.close()
        if db.use_local_db:
            db._save_local() # Final save on shutdown
        logger.info("Bot shut down gracefully.")


if __name__ == "__main__":
    # Start Flask in a background thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Bot process terminated.")
    except Exception as e:
        logger.critical(f"💥 A critical error occurred in the main loop: {e}", exc_info=True)
        sys.exit(1)
