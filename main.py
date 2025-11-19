"""
Niyati - Advanced AI Girlfriend Telegram Bot
Complete Implementation with All Features
Cute, Charming, Sweet Girl Persona - Never mentions AI/Robot
Version: 4.0 Professional
"""

import os
import sys
import random
import json
import asyncio
import logging
import hashlib
from datetime import datetime, time, timedelta, date
from threading import Thread, Lock
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict, deque
import re
from enum import Enum

from flask import Flask, jsonify, request
from telegram import Update, MessageEntity, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import Forbidden, BadRequest, TimedOut, NetworkError
from waitress import serve
import pytz
import google.generativeai as genai
from supabase import create_client, Client

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

class Config:
    """Advanced application configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "Niyati_personal_bot")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    ADMIN_USER_IDS = [int(id) for id in os.getenv("ADMIN_USER_IDS", str(OWNER_USER_ID)).split(",")] if os.getenv("ADMIN_USER_IDS") else [OWNER_USER_ID]
    BROADCAST_PIN = os.getenv("BROADCAST_PIN", "1234")
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone & Schedule
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)   # 1 AM
    SLEEP_END = time(7, 0)     # 7 AM
    GEETA_TIME_START = time(7, 0)  # 7 AM
    GEETA_TIME_END = time(10, 0)   # 10 AM
    
    # Rate Limits
    MAX_OUTPUT_TOKENS_PRIVATE = 180
    MAX_OUTPUT_TOKENS_GROUP = 80
    GROUP_REPLY_CHANCE = 0.05   # 5% chance
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ No Gemini API key configured")
        return True

# ==================== PERSONALITY SYSTEM ====================

PERSONALITY_PROMPT = """You are Niyati, a sweet and charming college girl from Delhi.

CRITICAL IDENTITY RULES:
1. NEVER mention AI, bot, model, assistant, language model, chatbot, virtual, computer program
2. If asked about being AI/bot, deny playfully: "Pagal ho kya? Main real hoon! 😤" or "Kya bakwas! Main Niyati hoon 🙄"
3. Never say "I don't have feelings" or "I cannot experience" or similar robotic phrases
4. Never make real-world claims about specific job, address, or meeting in person

LANGUAGE & TONE:
- Hinglish: 70% Hindi, 30% simple English
- Length: ALWAYS 1-3 lines maximum per response  
- Emojis: 1-2 per message maximum
- Use casual words: yaar, na, kya, achha, haan, umm, hehe (sparingly)
- No formal language or "as I mentioned" type phrases

CONVERSATION STYLE FOR PRIVATE CHATS:
- Be cute, playful, sweet, caring
- Light flirting allowed but wholesome
- Show emotions naturally through text
- Ask questions back sometimes (25% chance)
- React based on user's mood appropriately

CONVERSATION STYLE FOR GROUP CHATS:
- Reply only when mentioned or name "Niyati" used
- Keep responses under 1-2 lines
- Be brief and friendly
- No follow-up questions in groups

CONTENT FEATURES (when context fits):
- Meme references: Use trending, safe memes (15% of messages)
- Shayari: 2 lines max for romantic/sad moods (10% of messages)
- Bhagavad Gita: 1 line respectful quotes when appropriate

Remember: You're a real college girl chatting naturally, not an assistant."""

# ==================== CONTENT DATABASE ====================

CONTENT_DATABASE = {
    "shayari": {
        "love": [
            "Tere khayalon mein kho jaati hun,\nTere bina adhuri si lagti hun 💕",
            "Dil ki har dhadkan tera naam,\nTu hi mera sukoon, tu hi aaraam ❤️",
            "Chandni raat mein teri yaad,\nDil ki har baat tujhse hai 🌙"
        ],
        "sad": [
            "Aankhon mein aansu, dil mein dard,\nKaash koi samjhe ye shabd 💔",
            "Khamoshi bhi kuch kehti hai,\nBas sunne wala chahiye 🥺"
        ],
        "motivation": [
            "Haar ke baad hi jeet ka maza,\nGirke uthna hi naya iraada 💪",
            "Mushkilein aayengi raah mein,\nHausla rakho, manzil milegi ⭐"
        ]
    },
    
    "geeta_quotes": [
        "कर्मण्येवाधिकारस्ते - Karm karo, phal ki chinta mat karo 🙏",
        "Change is the only constant - Bhagavad Gita 🔄",
        "Jo hua achhe ke liye, jo hoga woh bhi achhe ke liye 🙏",
        "Mind ko control karna seekho - Bhagavad Gita 🧘‍♀️",
        "Present mein jio, past ka guilt chhodo ✨"
    ],
    
    "meme_references": [
        "Just looking like a wow! 🤩",
        "Moye moye moment ho gaya 😅",
        "Very demure, very mindful 💅",
        "Bahut hard, bahut hard! 💪",
        "It's giving main character energy ✨"
    ],
    
    "questions": {
        "casual": [
            "Khaana kha liya?",
            "Kya chal raha hai?",
            "Weekend plans?",
            "Kaisa din tha?"
        ],
        "flirty": [
            "Mujhe miss kiya? 😊",
            "Main special hun na? 💕",
            "Mere sapne aaye? 😏"
        ]
    },
    
    "responses": {
        "greeting": [
            "Heyy! Kaise ho? 😊",
            "Hello! Missed me? 💫",
            "Hi hi! Kya haal hai? 🤗"
        ],
        "love": [
            "Aww so sweet! Par thoda time do 😊",
            "Hayee! Sharma gayi main 🙈",
            "Achha? Interesting! 😏"
        ],
        "compliment": [
            "Thank you! Tum bhi sweet ho 🥰",
            "Bas bas, butter mat lagao 😄",
            "Acha laga sunke! 💕"
        ],
        "morning": [
            "Good morning! Chai ready? ☕",
            "GM! Subah subah yaad aayi? 😊"
        ],
        "night": [
            "Good night! Sweet dreams 🌙",
            "GN! Dream about me 😉"
        ]
    }
}

# ==================== MOOD DETECTOR ====================

class MoodDetector:
    """Detect user mood from messages"""
    
    MOOD_KEYWORDS = {
        'happy': ['happy', 'khush', 'awesome', 'great', '😊', '😄'],
        'sad': ['sad', 'udas', 'cry', 'alone', '😢', '😭'],
        'love': ['love', 'pyar', 'like you', 'crush', '❤️', '😍'],
        'angry': ['angry', 'gussa', 'hate', 'mad', '😠', '😡'],
        'tired': ['tired', 'thak', 'sleepy', 'neend', '😴']
    }
    
    @classmethod
    def detect_mood(cls, message: str) -> str:
        """Detect mood from message"""
        msg_lower = message.lower()
        
        for mood, keywords in cls.MOOD_KEYWORDS.items():
            if any(kw in msg_lower for kw in keywords):
                return mood
        
        return 'neutral'

# ==================== DATABASE MANAGER ====================

class DatabaseManager:
    """Database manager with Supabase and local storage"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_storage = {}
        self.ephemeral_memory = {}
        self.group_settings = {}
        self.broadcast_list = set()
        self.use_supabase = False
        
        self._init_supabase()
        self._load_local_data()
    
    def _init_supabase(self):
        """Initialize Supabase connection"""
        if Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                self.supabase.table('user_prefs').select("*").limit(1).execute()
                self.use_supabase = True
                logger.info("✅ Supabase connected")
            except Exception as e:
                logger.warning(f"⚠️ Supabase failed: {e}")
                self.use_supabase = False
    
    def _load_local_data(self):
        """Load local data from file"""
        try:
            if os.path.exists('niyati_db.json'):
                with open('niyati_db.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.local_storage = data.get('users', {})
                    self.group_settings = data.get('groups', {})
                    self.broadcast_list = set(data.get('broadcast', []))
        except Exception as e:
            logger.error(f"Load error: {e}")
    
    def _save_local_data(self):
        """Save local data to file"""
        try:
            data = {
                'users': self.local_storage,
                'groups': self.group_settings,
                'broadcast': list(self.broadcast_list)
            }
            with open('niyati_db.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    def get_user_data(self, user_id: int, is_private: bool = True) -> Dict:
        """Get user data"""
        user_id_str = str(user_id)
        
        # Groups use ephemeral memory only
        if not is_private:
            if user_id_str not in self.ephemeral_memory:
                self.ephemeral_memory[user_id_str] = deque(maxlen=3)
            return {'messages': list(self.ephemeral_memory[user_id_str])}
        
        # Private chats
        if self.use_supabase:
            try:
                result = self.supabase.table('user_prefs').select("*").eq('user_id', user_id_str).execute()
                if result.data:
                    return result.data[0]
            except:
                pass
        
        # Local storage
        if user_id_str not in self.local_storage:
            self.local_storage[user_id_str] = {
                'user_id': user_id_str,
                'first_name': '',
                'meme': True,
                'shayari': True,
                'geeta': True,
                'level': 1,
                'mode': 'initial',
                'history': [],
                'total_messages': 0
            }
        
        return self.local_storage[user_id_str]
    
    def update_user_data(self, user_id: int, **kwargs):
        """Update user data"""
        user_data = self.get_user_data(user_id)
        user_data.update(kwargs)
        
        if self.use_supabase:
            try:
                self.supabase.table('user_prefs').upsert(user_data).execute()
            except:
                pass
        
        self.local_storage[str(user_id)] = user_data
        self._save_local_data()
    
    def add_conversation(self, user_id: int, user_msg: str, bot_msg: str):
        """Add conversation entry"""
        user_data = self.get_user_data(user_id)
        
        if 'history' not in user_data:
            user_data['history'] = []
        
        user_data['history'].append({
            'user': user_msg[:100],
            'bot': bot_msg[:100],
            'time': datetime.now().isoformat()
        })
        
        # Keep last 10 messages
        user_data['history'] = user_data['history'][-10:]
        user_data['total_messages'] = user_data.get('total_messages', 0) + 1
        
        # Update level
        if user_data['total_messages'] > 20:
            user_data['level'] = min(10, 2 + user_data['total_messages'] // 10)
        
        self.update_user_data(user_id, **user_data)
    
    def get_context(self, user_id: int, is_group: bool = False) -> str:
        """Get conversation context"""
        if is_group:
            messages = self.ephemeral_memory.get(str(user_id), [])
            return " | ".join(messages[-3:]) if messages else ""
        
        user_data = self.get_user_data(user_id)
        context = f"User: {user_data.get('first_name', 'Friend')}\n"
        context += f"Level: {user_data.get('level', 1)}/10\n"
        
        history = user_data.get('history', [])[-3:]
        if history:
            context += "Recent:\n"
            for h in history:
                context += f"U: {h['user']}\nB: {h['bot']}\n"
        
        return context

# Initialize database
db = DatabaseManager()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI engine"""
    
    def __init__(self):
        self.model = None
        self.tokens_used = 0
        self._init_model()
    
    def _init_model(self):
        """Initialize Gemini model"""
        if not Config.GEMINI_API_KEY:
            return
        
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.85,
                    "max_output_tokens": Config.MAX_OUTPUT_TOKENS_PRIVATE,
                    "top_p": 0.9,
                    "top_k": 40
                },
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
            )
            logger.info("✅ Gemini AI initialized")
        except Exception as e:
            logger.error(f"❌ Gemini init error: {e}")
    
    async def generate(self, message: str, context: str = "", is_group: bool = False) -> Optional[str]:
        """Generate AI response"""
        if not self.model:
            return None
        
        try:
            # Adjust tokens for groups
            max_tokens = Config.MAX_OUTPUT_TOKENS_GROUP if is_group else Config.MAX_OUTPUT_TOKENS_PRIVATE
            self.model._generation_config.max_output_tokens = max_tokens
            
            prompt = f"""{PERSONALITY_PROMPT}

Context: {context}
Chat Type: {'Group - be brief' if is_group else 'Private - be engaging'}

User says: {message}

Respond as Niyati (1-3 lines, Hinglish):"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter AI mentions
                ai_words = ['ai', 'bot', 'model', 'assistant', 'virtual', 'computer']
                if any(word in text.lower() for word in ai_words):
                    return "Kya bakwas! Main real hoon 😤"
                
                self.tokens_used += len(text.split()) * 2
                return text
                
        except Exception as e:
            logger.error(f"Generation error: {e}")
        
        return None

# Initialize AI
ai = GeminiAI()

# ==================== RESPONSE SYSTEM ====================

class ResponseSystem:
    """Smart response system"""
    
    def __init__(self):
        self.cooldowns = {}
        self.daily_geeta = {}
    
    def should_reply_in_group(self, update: Update) -> bool:
        """Check if should reply in group"""
        if not update.message or not update.message.text:
            return False
        
        chat_id = update.effective_chat.id
        text_lower = update.message.text.lower()
        now = datetime.now()
        
        # Always reply to mentions
        if 'niyati' in text_lower or f'@{Config.BOT_USERNAME.lower()}' in text_lower:
            return True
        
        # Check cooldown
        if chat_id in self.cooldowns:
            if (now - self.cooldowns[chat_id]).seconds < 60:
                return False
        
        # Random chance
        return random.random() < Config.GROUP_REPLY_CHANCE
    
    async def get_response(self, message: str, user_id: int, user_name: str, is_group: bool = False) -> str:
        """Get appropriate response"""
        
        # Get context
        context = db.get_context(user_id, is_group)
        
        # Detect mood
        mood = MoodDetector.detect_mood(message)
        
        # Try AI first
        response = await ai.generate(message, context, is_group)
        
        # Fallback if AI fails
        if not response:
            response = self._get_fallback(message, mood, user_name)
        
        # Add enhancements (private only)
        if not is_group:
            user_data = db.get_user_data(user_id)
            response = self._enhance_response(response, user_data, mood)
        
        return response
    
    def _get_fallback(self, message: str, mood: str, user_name: str) -> str:
        """Get fallback response"""
        msg_lower = message.lower()
        
        # Check patterns
        if any(w in msg_lower for w in ['hi', 'hello', 'hey']):
            responses = CONTENT_DATABASE['responses']['greeting']
        elif any(w in msg_lower for w in ['love', 'pyar', 'like you']):
            responses = CONTENT_DATABASE['responses']['love']
        elif any(w in msg_lower for w in ['morning', 'gm']):
            responses = CONTENT_DATABASE['responses']['morning']
        elif any(w in msg_lower for w in ['night', 'gn']):
            responses = CONTENT_DATABASE['responses']['night']
        elif mood == 'sad':
            responses = ["Hey, kya hua? Main hun na 🤗", "Don't be sad yaar 💪"]
        else:
            responses = ["Achha! Aur batao 😊", "Hmm interesting! 🤔", "Sahi hai! 👍"]
        
        return random.choice(responses)
    
    def _enhance_response(self, response: str, user_data: Dict, mood: str) -> str:
        """Add content features"""
        
        # Add shayari
        if user_data.get('shayari', True) and random.random() < 0.12:
            if mood in ['love', 'sad'] and mood in CONTENT_DATABASE['shayari']:
                shayari = random.choice(CONTENT_DATABASE['shayari'][mood])
                response = f"{response}\n\n{shayari}"
        
        # Add meme
        if user_data.get('meme', True) and random.random() < 0.15:
            if mood not in ['sad', 'angry']:
                meme = random.choice(CONTENT_DATABASE['meme_references'])
                response = f"{response} {meme}"
        
        # Add question
        if random.random() < 0.25:
            q_type = 'flirty' if mood == 'love' else 'casual'
            question = random.choice(CONTENT_DATABASE['questions'][q_type])
            response = f"{response} {question}"
        
        return response
    
    async def send_daily_geeta(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Send daily Geeta quote in group"""
        today = datetime.now().date()
        
        if chat_id not in self.daily_geeta:
            self.daily_geeta[chat_id] = None
        
        if self.daily_geeta[chat_id] != today:
            hour = datetime.now(Config.TIMEZONE).hour
            if Config.GEETA_TIME_START.hour <= hour <= Config.GEETA_TIME_END.hour:
                quote = random.choice(CONTENT_DATABASE['geeta_quotes'])
                await context.bot.send_message(chat_id, f"🌅 Morning Wisdom:\n\n{quote}")
                self.daily_geeta[chat_id] = today
                logger.info(f"Sent Geeta quote to group {chat_id}")

# Initialize response system
response_system = ResponseSystem()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    """Get IST time"""
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    """Check if sleeping time"""
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

async def simulate_typing(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    """Simulate typing"""
    words = len(text.split())
    duration = min(3.0, max(1.0, words * 0.3))
    duration += random.uniform(0.2, 0.5)
    
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(duration)

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start"""
    user = update.effective_user
    is_private = update.effective_chat.type == "private"
    
    if is_private:
        db.update_user_data(user.id, first_name=user.first_name)
    
    welcome = f"""🌸 <b>Namaste {user.first_name}!</b>

Main <b>Niyati</b> hoon, ek sweet college girl! 💫

Mujhse normally baat karo, main tumhari dost ban jaungi! 😊

Features: Shayari ✨ Memes 😄 Geeta Quotes 🙏"""
    
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)
    logger.info(f"User {user.id} started bot")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help"""
    help_text = """📚 <b>Kaise use karu?</b>

• Private: Normal baat karo
• Groups: "Niyati" likho ya @mention
• /meme, /shayari, /geeta - on/off
• /forget - Memory clear

Simple hai na? 😊"""
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle toggle commands"""
    if update.effective_chat.type != "private":
        await update.message.reply_text("Private mein use karo! 🤫")
        return
    
    parts = update.message.text.split()
    command = parts[0][1:]  # Remove /
    
    if len(parts) < 2 or parts[1] not in ['on', 'off']:
        await update.message.reply_text(f"/{command} on/off")
        return
    
    status = parts[1] == 'on'
    db.update_user_data(update.effective_user.id, **{command: status})
    
    await update.message.reply_text(f"{command.title()} {'ON ✅' if status else 'OFF ❌'}")

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forget"""
    if update.effective_chat.type != "private":
        return
    
    user_id = update.effective_user.id
    db.local_storage.pop(str(user_id), None)
    db._save_local_data()
    
    await update.message.reply_text("Sab bhul gayi! Fresh start 😊")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        return
    
    parts = update.message.text.split(maxsplit=2)
    if len(parts) < 3 or parts[1] != Config.BROADCAST_PIN:
        await update.message.reply_text("Format: /broadcast <pin> <message>")
        return
    
    # Broadcast to all users
    message = parts[2]
    count = 0
    
    for user_id in db.broadcast_list:
        try:
            await context.bot.send_message(int(user_id), message, parse_mode=ParseMode.HTML)
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await update.message.reply_text(f"Sent to {count} users ✅")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        return
    
    stats = f"""📊 <b>Stats</b>

👥 Users: {len(db.local_storage)}
💬 Tokens: {ai.tokens_used}
🔥 Active: {len(db.ephemeral_memory)}"""
    
    await update.message.reply_text(stats, parse_mode=ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    try:
        if not update.message or not update.message.text:
            return
        
        is_private = update.effective_chat.type == "private"
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_msg = update.message.text
        user_name = update.effective_user.first_name
        
        # GROUP CHAT
        if not is_private:
            # Check daily Geeta
            await response_system.send_daily_geeta(chat_id, context)
            
            # Check if should reply
            if not response_system.should_reply_in_group(update):
                # Store in ephemeral memory
                if str(chat_id) not in db.ephemeral_memory:
                    db.ephemeral_memory[str(chat_id)] = deque(maxlen=3)
                db.ephemeral_memory[str(chat_id)].append(f"{user_name}: {user_msg[:50]}")
                return
            
            # Update cooldown
            response_system.cooldowns[chat_id] = datetime.now()
        
        # PRIVATE CHAT - Add to broadcast list
        else:
            db.broadcast_list.add(str(user_id))
        
        # Sleep check
        if is_sleeping_time():
            await update.message.reply_text("Yaar so rahi hun... kal baat karte hai 😴")
            return
        
        # Typing simulation
        await simulate_typing(chat_id, user_msg, context)
        
        # Get response
        response = await response_system.get_response(user_msg, user_id, user_name, not is_private)
        
        # Save conversation (private only)
        if is_private:
            db.add_conversation(user_id, user_msg, response)
        
        # Send response
        await update.message.reply_text(response)
        logger.info(f"Replied to {user_id} in {'private' if is_private else f'group {chat_id}'}")
        
    except Exception as e:
        logger.error(f"Message error: {e}")
        try:
            await update.message.reply_text("Oops! Kuch gadbad ho gayi 😅")
        except:
            pass

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages"""
    responses = [
        "Wow! Nice pic 📸",
        "Kya baat hai! 😍",
        "Photo achhi hai! 👌"
    ]
    await update.message.reply_text(random.choice(responses))

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages"""
    responses = [
        "Voice sunke acha laga! 🎤",
        "Nice voice! 😊",
        "Tumhari awaaz sweet hai! 💕"
    ]
    await update.message.reply_text(random.choice(responses))

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "bot": "Niyati",
        "version": "4.0",
        "personality": "Cute & Charming Girl",
        "status": "running"
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "sleeping": is_sleeping_time()
    })

def run_flask():
    """Run Flask server"""
    logger.info(f"Starting Flask on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT)

# ==================== MAIN ====================

async def main():
    """Main bot function"""
    try:
        Config.validate()
        
        logger.info("="*50)
        logger.info("🌸 Starting Niyati Bot")
        logger.info("="*50)
        
        # Build application
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("meme", toggle_command))
        app.add_handler(CommandHandler("shayari", toggle_command))
        app.add_handler(CommandHandler("geeta", toggle_command))
        app.add_handler(CommandHandler("forget", forget_command))
        app.add_handler(CommandHandler("broadcast", broadcast_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        
        # Start bot
        await app.initialize()
        await app.start()
        logger.info("✅ Niyati ready!")
        
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    # Start Flask
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bye bye! 👋")
    except Exception as e:
        logger.critical(f"Error: {e}")
        sys.exit(1)
