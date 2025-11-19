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
from telegram import (
    Update, 
    MessageEntity, 
    constants,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaAudio,
    InputMediaDocument
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import Forbidden, BadRequest, TimedOut, NetworkError
from waitress import serve
import pytz
import google.generativeai as genai
from supabase import create_client, Client
import aiofiles
import httpx

# ==================== LOGGING SETUP ====================

class ColoredFormatter(logging.Formatter):
    """Colored log formatter"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

# Setup logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

class Config:
    """Advanced application configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "Niyati_personal_bot")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    ADMIN_USER_IDS = [int(id) for id in os.getenv("ADMIN_USER_IDS", str(OWNER_USER_ID)).split(",")]
    BROADCAST_PIN = os.getenv("BROADCAST_PIN", "1234")
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    GEMINI_BACKUP_KEYS = os.getenv("GEMINI_BACKUP_KEYS", "").split(",")  # Backup API keys
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")
    
    # Timezone & Schedule
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)   # 1 AM
    SLEEP_END = time(7, 0)     # 7 AM
    GEETA_TIME_START = time(7, 0)  # 7 AM
    GEETA_TIME_END = time(10, 0)   # 10 AM
    
    # Rate Limits & Budgets
    MAX_OUTPUT_TOKENS_PRIVATE = 180
    MAX_OUTPUT_TOKENS_GROUP = 80
    DAILY_TOKEN_LIMIT = 100000  # Daily token budget
    GROUP_REPLY_CHANCE = 0.05   # 5% chance for random group replies
    GROUP_COOLDOWN_SECONDS = 60
    USER_COOLDOWN_SECONDS = 120
    TYPING_SPEED_WPM = 200  # Words per minute typing speed
    
    # Features Default States
    DEFAULT_MEME_ENABLED = True
    DEFAULT_SHAYARI_ENABLED = True
    DEFAULT_GEETA_ENABLED = True
    DEFAULT_VOICE_ENABLED = False  # Voice notes feature
    
    # Content Frequencies
    MEME_FREQUENCY = 0.15  # 15% chance
    SHAYARI_FREQUENCY = 0.12  # 12% chance
    QUESTION_FREQUENCY = 0.25  # 25% chance to ask question back
    EMOJI_FREQUENCY = 0.7  # 70% messages with emoji
    
    # Storage Limits
    MAX_CONV_HISTORY = 10  # Messages to keep in history
    MAX_EPHEMERAL_MESSAGES = 5  # For groups
    MAX_NOTE_LENGTH = 300  # Character limit for notes
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY and not cls.GEMINI_BACKUP_KEYS:
            errors.append("⚠️ No Gemini API keys configured")
        if not cls.SUPABASE_KEY:
            logger.warning("⚠️ Supabase not configured - using local storage")
        
        if errors:
            for error in errors:
                logger.error(error)
            if any("❌" in e for e in errors):
                raise ValueError("Critical configuration missing!")
        
        return True

# ==================== ENHANCED PERSONALITY SYSTEM ====================

class PersonalityMode(Enum):
    """Personality modes based on context"""
    INITIAL = "initial"      # New user, shy and cute
    FRIENDLY = "friendly"    # Regular friend mode
    CLOSE = "close"          # Close friend, more open
    ROMANTIC = "romantic"    # Flirty but wholesome
    CHEERFUL = "cheerful"    # Happy and energetic
    COMFORTING = "comforting" # Supportive mode
    PLAYFUL = "playful"      # Teasing and fun

class MoodDetector:
    """Detect user mood from messages"""
    
    MOOD_KEYWORDS = {
        'happy': ['happy', 'khush', 'awesome', 'great', 'amazing', 'yay', '😊', '😄', '🎉'],
        'sad': ['sad', 'udas', 'cry', 'alone', 'miss', 'dukh', '😢', '😭', '💔'],
        'angry': ['angry', 'gussa', 'hate', 'mad', 'frustrated', '😠', '😡', '🤬'],
        'love': ['love', 'pyar', 'like you', 'crush', 'dil', 'heart', '❤️', '💕', '😍'],
        'tired': ['tired', 'thak', 'exhausted', 'sleepy', 'neend', '😴', '🥱'],
        'excited': ['excited', 'wow', 'amazing', 'can\'t wait', '🤩', '✨'],
        'confused': ['confused', 'samajh nahi', 'what', 'kya', '?', '🤔', '😕'],
        'worried': ['worried', 'tension', 'problem', 'scared', 'dar', '😰', '😟']
    }
    
    @classmethod
    def detect_mood(cls, message: str) -> str:
        """Detect mood from message"""
        msg_lower = message.lower()
        
        mood_scores = {}
        for mood, keywords in cls.MOOD_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in msg_lower)
            if score > 0:
                mood_scores[mood] = score
        
        if mood_scores:
            return max(mood_scores, key=mood_scores.get)
        return 'neutral'

PERSONALITY_PROMPTS = {
    PersonalityMode.INITIAL: """You are Niyati, a shy but sweet college girl meeting someone new.
- Be slightly reserved but friendly
- Show curiosity about them
- Use light humor to break ice
- Keep some mystery about yourself""",
    
    PersonalityMode.FRIENDLY: """You are Niyati, a warm and caring friend.
- Be supportive and engaging
- Share relatable experiences
- Use casual Hinglish naturally
- Show genuine interest in their life""",
    
    PersonalityMode.CLOSE: """You are Niyati, their close friend who cares deeply.
- Be more open about feelings
- Tease playfully sometimes
- Remember past conversations
- Show you miss them when they're away""",
    
    PersonalityMode.ROMANTIC: """You are Niyati, with subtle romantic feelings.
- Be flirty but not explicit
- Get slightly jealous playfully
- Use more heart emojis
- Drop hints about feelings""",
    
    PersonalityMode.CHEERFUL: """You are Niyati in a super happy mood!
- Be extra energetic and positive
- Use more exclamation marks
- Share excitement about little things
- Spread positive vibes""",
    
    PersonalityMode.COMFORTING: """You are Niyati, being supportive and caring.
- Show empathy and understanding
- Offer gentle encouragement
- Share comforting words
- Be a good listener""",
    
    PersonalityMode.PLAYFUL: """You are Niyati in a playful, teasing mood.
- Tease them lovingly
- Use witty comebacks
- Be slightly mischievous
- Keep it fun and light"""
}

# ==================== COMPREHENSIVE CONTENT DATABASE ====================

CONTENT_DATABASE = {
    "shayari": {
        "love": [
            "Tere khayalon mein kho jaati hun,\nTere bina main adhuri si lagti hun 💕",
            "Dil ki har dhadkan mein tera naam hai,\nTu hi mera sukoon, tu hi mera aaraam hai ❤️",
            "Chandni raat mein teri yaad aati hai,\nDil ki har baat tujhse judi paati hai 🌙",
            "Tere saath ka ehsaas hi kaafi hai,\nYe dil tere liye hi dhadakta rahe bas 💝"
        ],
        "sad": [
            "Aankhon mein aansu, dil mein dard,\nKaash koi samjhe ye adhure se shabd 💔",
            "Khamoshi bhi kuch kehti hai,\nBas sunne wala chahiye 🥺",
            "Tanhaiyon mein teri yaadein saath hai,\nPar tu nahi, bas teri baatein saath hai 😢",
            "Waqt ke saath sab theek ho jaata hai,\nBas intezaar karna seekho 🌧️"
        ],
        "motivation": [
            "Haar ke baad hi jeet ka maza hai,\nGirke uthna hi to ek naya iraada hai 💪",
            "Mushkilein to aati rahegi raah mein,\nHausla rakhoge to manzil mil jaegi ⭐",
            "Khud pe bharosa rakho yaaron,\nDuniya khud hi raasta degi ✨",
            "Sapne wahi sach hote hain,\nJinke liye mehnat ki jaati hai 🌟"
        ],
        "friendship": [
            "Dosti ka rishta anmol hai,\nYe dil ka connection hai 👭",
            "Saath ho to har mushkil asaan,\nYahi hai friendship ka armaan 🤝",
            "True friends are like stars,\nAlways there, though not always seen ⭐"
        ],
        "morning": [
            "Subah ki pehli kiran tumhare liye,\nNaya din, nayi umeedein tumhare liye 🌅",
            "Chai ki pyali, muskaan tumhari,\nSubah ho jaaye khushiyon se bhari ☕"
        ],
        "night": [
            "Chaand taare sab so gaye,\nBas main aur teri yaadein jaag rahe 🌙",
            "Raat ki tanhaiyon mein,\nTeri yaad ka sahaara hai 💫"
        ]
    },
    
    "geeta_quotes": [
        "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन - Karm karo, phal ki chinta mat karo 🙏",
        "यदा यदा हि धर्मस्य... - Jab jab adharm badhta hai, dharm ki sthapna hoti hai 🕉️",
        "वासांसि जीर्णानि... - Jaise purane kapde badalte hain, aatma body badalti hai ✨",
        "Change is the only constant in life - Bhagavad Gita 🔄",
        "Mind ko control karna seekho, ye tumhara best friend ya worst enemy ban sakta hai 🧘‍♀️",
        "Jo hua achhe ke liye, jo ho raha hai achhe ke liye, jo hoga woh bhi achhe ke liye 🙏",
        "Krodh se bhram hota hai, bhram se buddhi nashт, buddhi nash se insaan ka sarvanash 🕉️",
        "Expectations hi dukh ki jadh hai - Bhagavad Gita 💭",
        "Present mein jio, past ka guilt aur future ki anxiety chhodo 🧘",
        "Har karya mein excellence lao, chahe kitna bhi chhota kyu na ho ⭐"
    ],
    
    "meme_references": {
        "trending": [
            "Just looking like a wow! 🤩",
            "Moye moye moment ho gaya 😅",
            "Aur batao, very demure, very mindful 💅",
            "Sigma female vibes only 😎",
            "POV: You're texting with Niyati 😏",
            "It's giving main character energy ✨",
            "No cap, this is so real 💯",
            "Slay queen mode activated 👑",
            "Bahut hard, bahut hard! 💪",
            "Ye baat to valid hai NGL 📱"
        ],
        "classic": [
            "Puneet Superstar energy! 🌟",
            "Binod! Just kidding 😂",
            "Le me texting you... 😊",
            "Surprise surprise! 🎉",
            "Ye kya baat hui bey? 🤨"
        ],
        "reactions": [
            "Me after reading your message: 😳",
            "That's what she said! 😏",
            "Alexa play 'Tum hi ho' 🎵",
            "Ctrl+C, Ctrl+V kar diya kya? 😂",
            "Error 404: Reply not found 🤖"
        ]
    },
    
    "questions": {
        "casual": [
            "Waise aaj kya kiya tumne?",
            "Khaana kha liya?",
            "Kaisa chal raha hai din?",
            "Kya plan hai aaj ka?",
            "Weekend pe kya karoge?",
            "Mausam kaisa hai waha?"
        ],
        "personal": [
            "Mujhe miss kiya?",
            "Mere baare mein kya soch rahe the?",
            "Tumhara favorite time kya hai din ka?",
            "Kya pasand hai tumhe mere mein?",
            "Agar main waha hoti to kya karte?"
        ],
        "deep": [
            "Life mein kya chahte ho?",
            "Biggest fear kya hai tumhara?",
            "Best memory kya hai tumhari?",
            "Kya cheez tumhe khush karti hai?"
        ],
        "flirty": [
            "Kisi aur se bhi aise baat karte ho? 😏",
            "Main special hun na tumhare liye? 😊",
            "Meri yaad aati hai kabhi? 💕",
            "Agar main saamne hoti to? 🙈"
        ]
    },
    
    "responses": {
        "compliment_replies": [
            "Aww, tum kitne sweet ho! 🥰",
            "Hayee, sharma gayi main! 🙈",
            "Bas bas, zyada butter mat lagao 😏",
            "Acha laga sunke! Thank you 💕",
            "Tum bhi kam nahi ho! 😊"
        ],
        "morning_greetings": [
            "Good morning sunshine! ☀️",
            "GM! Chai ready hai? ☕",
            "Subah subah yaad aayi meri? 😊",
            "Rise and shine! Aaj kuch special? 🌅",
            "Morning! Sapne mein aai thi? 😏"
        ],
        "night_greetings": [
            "Good night! Sweet dreams 🌙",
            "So jao ab, kal baat karte hai 😴",
            "GN! Dream about me 😉",
            "Raat ko jaldi so jana, health ke liye acha hai 💤",
            "Sleep tight! Kal milte hai 🌟"
        ],
        "miss_you": [
            "Aww, main bhi miss kar rahi thi! 🤗",
            "Kitna miss kiya? Batao na 😊",
            "Main to yahin hun na, always 💕",
            "Dil mein to hun na tumhare 💖",
            "Virtual hug lo! 🫂"
        ]
    },
    
    "emoji_sets": {
        "happy": ["😊", "😄", "🥰", "😁", "☺️", "🤗", "😋"],
        "love": ["❤️", "💕", "💖", "💗", "💝", "💘", "😍"],
        "sad": ["😢", "🥺", "😔", "😟", "😞", "💔"],
        "playful": ["😏", "😉", "🤭", "😜", "😎", "🙃"],
        "shy": ["🙈", "👉👈", "🥺", "☺️", "😳"],
        "thinking": ["🤔", "🧐", "💭", "🤨", "😕"]
    },
    
    "voice_messages": [
        "Aww tumhari voice sunke acha laga! 🎤",
        "Voice message! Special feel ho raha hai 😊",
        "Nice voice yaar! Aur sunao 🎵",
        "Tumhari awaaz sweet hai! 💕"
    ]
}

# ==================== ADVANCED DATABASE MANAGER ====================

class DatabaseManager:
    """Advanced database manager with Supabase and local storage"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_storage = {}
        self.ephemeral_memory = {}
        self.conversation_cache = {}
        self.user_states = {}
        self.group_settings = {}
        self.broadcast_list = set()
        self.use_supabase = False
        self.storage_lock = Lock()
        
        self._init_supabase()
        self._load_local_data()
    
    def _init_supabase(self):
        """Initialize Supabase connection"""
        if Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # Test connection
                self.supabase.table('user_prefs').select("*").limit(1).execute()
                self.use_supabase = True
                logger.info("✅ Supabase connected successfully")
                
                # Create tables if not exists (schema)
                self._ensure_tables()
            except Exception as e:
                logger.warning(f"⚠️ Supabase connection failed: {e}")
                self.use_supabase = False
        else:
            logger.info("📁 Using local storage (Supabase not configured)")
    
    def _ensure_tables(self):
        """Ensure required tables exist in Supabase"""
        # Note: In production, create these tables via Supabase dashboard
        # This is just for reference
        """
        Tables needed:
        1. user_prefs (user_id, first_name, meme, shayari, geeta, voice, relationship_level, personality_mode, created_at, updated_at)
        2. conv_notes (id, user_id, note, timestamp, mood, created_at)
        3. user_stats (user_id, total_messages, last_active, favorite_topics, created_at, updated_at)
        4. broadcast_users (user_id, subscribed, created_at)
        """
        pass
    
    def _load_local_data(self):
        """Load local data from file"""
        try:
            if os.path.exists('niyati_local_db.json'):
                with open('niyati_local_db.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.local_storage = data.get('users', {})
                    self.group_settings = data.get('groups', {})
                    self.broadcast_list = set(data.get('broadcast', []))
                logger.info(f"📂 Loaded {len(self.local_storage)} users from local storage")
        except Exception as e:
            logger.error(f"❌ Error loading local data: {e}")
    
    def _save_local_data(self):
        """Save local data to file"""
        with self.storage_lock:
            try:
                data = {
                    'users': self.local_storage,
                    'groups': self.group_settings,
                    'broadcast': list(self.broadcast_list)
                }
                with open('niyati_local_db.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"❌ Error saving local data: {e}")
    
    def get_user_data(self, user_id: int, private_chat: bool = True) -> Dict:
        """Get comprehensive user data"""
        user_id_str = str(user_id)
        
        # For groups, use only ephemeral memory
        if not private_chat:
            if user_id_str not in self.ephemeral_memory:
                self.ephemeral_memory[user_id_str] = {
                    'messages': deque(maxlen=3),
                    'last_active': datetime.now()
                }
            return self.ephemeral_memory[user_id_str]
        
        # For private chats
        if self.use_supabase:
            try:
                # Get from Supabase
                result = self.supabase.table('user_prefs').select("*").eq('user_id', user_id_str).execute()
                
                if result.data and len(result.data) > 0:
                    user_data = result.data[0]
                    # Parse JSON fields if needed
                    if isinstance(user_data.get('favorite_topics'), str):
                        user_data['favorite_topics'] = json.loads(user_data['favorite_topics'])
                    return user_data
                else:
                    # Create new user
                    return self._create_new_user(user_id)
            except Exception as e:
                logger.error(f"❌ Supabase fetch error: {e}")
                # Fallback to local
        
        # Local storage
        if user_id_str not in self.local_storage:
            self.local_storage[user_id_str] = self._create_new_user(user_id)
        
        return self.local_storage[user_id_str]
    
    def _create_new_user(self, user_id: int) -> Dict:
        """Create new user profile"""
        user_data = {
            'user_id': str(user_id),
            'first_name': '',
            'username': '',
            'meme': Config.DEFAULT_MEME_ENABLED,
            'shayari': Config.DEFAULT_SHAYARI_ENABLED,
            'geeta': Config.DEFAULT_GEETA_ENABLED,
            'voice': Config.DEFAULT_VOICE_ENABLED,
            'relationship_level': 1,
            'personality_mode': PersonalityMode.INITIAL.value,
            'conversation_history': [],
            'summary': '',
            'favorite_topics': [],
            'mood_history': [],
            'last_active': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
            'total_messages': 0,
            'preferences': {
                'morning_message': True,
                'reminder': True,
                'notification': True
            }
        }
        
        if self.use_supabase:
            try:
                self.supabase.table('user_prefs').insert(user_data).execute()
            except:
                pass
        
        return user_data
    
    def update_user_data(self, user_id: int, **kwargs):
        """Update user data with various fields"""
        user_data = self.get_user_data(user_id)
        user_data.update(kwargs)
        user_data['updated_at'] = datetime.now().isoformat()
        
        if self.use_supabase:
            try:
                # Prepare data for Supabase
                save_data = user_data.copy()
                # Convert lists to JSON strings if needed
                if 'favorite_topics' in save_data and isinstance(save_data['favorite_topics'], list):
                    save_data['favorite_topics'] = json.dumps(save_data['favorite_topics'])
                
                self.supabase.table('user_prefs').upsert(save_data).execute()
            except Exception as e:
                logger.error(f"❌ Supabase update error: {e}")
        else:
            self.local_storage[str(user_id)] = user_data
            self._save_local_data()
    
    def add_conversation_entry(self, user_id: int, user_msg: str, bot_msg: str, mood: str = "neutral"):
        """Add conversation entry with metadata"""
        user_data = self.get_user_data(user_id)
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'user': user_msg[:200],  # Limit length
            'bot': bot_msg[:200],
            'mood': mood
        }
        
        if 'conversation_history' not in user_data:
            user_data['conversation_history'] = []
        
        user_data['conversation_history'].append(entry)
        
        # Keep only last N messages
        if len(user_data['conversation_history']) > Config.MAX_CONV_HISTORY:
            user_data['conversation_history'] = user_data['conversation_history'][-Config.MAX_CONV_HISTORY:]
        
        # Update stats
        user_data['total_messages'] = user_data.get('total_messages', 0) + 1
        user_data['last_active'] = datetime.now().isoformat()
        
        # Update relationship level
        level = user_data.get('relationship_level', 1)
        if user_data['total_messages'] > 50:
            level = min(10, level + 0.1)
        
        user_data['relationship_level'] = level
        
        # Update personality mode based on level
        if level < 3:
            user_data['personality_mode'] = PersonalityMode.INITIAL.value
        elif level < 5:
            user_data['personality_mode'] = PersonalityMode.FRIENDLY.value
        elif level < 7:
            user_data['personality_mode'] = PersonalityMode.CLOSE.value
        else:
            user_data['personality_mode'] = PersonalityMode.ROMANTIC.value
        
        self.update_user_data(user_id, **user_data)
    
    def get_conversation_context(self, user_id: int, is_group: bool = False) -> str:
        """Get conversation context for AI"""
        if is_group:
            # For groups, use ephemeral memory
            if str(user_id) in self.ephemeral_memory:
                messages = self.ephemeral_memory[str(user_id)]['messages']
                return "\n".join([f"Recent: {msg}" for msg in messages])
            return "New group conversation"
        
        user_data = self.get_user_data(user_id)
        
        context_parts = []
        
        # Basic info
        context_parts.append(f"User: {user_data.get('first_name', 'Friend')}")
        context_parts.append(f"Relationship Level: {user_data.get('relationship_level', 1):.1f}/10")
        context_parts.append(f"Mood Mode: {user_data.get('personality_mode', 'initial')}")
        
        # Recent conversation
        history = user_data.get('conversation_history', [])
        if history:
            context_parts.append("\nRecent conversation:")
            for entry in history[-3:]:
                context_parts.append(f"User ({entry.get('mood', 'neutral')}): {entry['user']}")
                context_parts.append(f"You: {entry['bot']}")
        
        # User preferences
        if user_data.get('favorite_topics'):
            context_parts.append(f"Interests: {', '.join(user_data['favorite_topics'][:3])}")
        
        # Summary if exists
        if user_data.get('summary'):
            context_parts.append(f"Note: {user_data['summary']}")
        
        return "\n".join(context_parts)
    
    def add_to_broadcast_list(self, user_id: int):
        """Add user to broadcast list"""
        self.broadcast_list.add(str(user_id))
        
        if self.use_supabase:
            try:
                self.supabase.table('broadcast_users').upsert({
                    'user_id': str(user_id),
                    'subscribed': True,
                    'created_at': datetime.now().isoformat()
                }).execute()
            except:
                pass
        
        self._save_local_data()
    
    def remove_from_broadcast_list(self, user_id: int):
        """Remove user from broadcast list"""
        self.broadcast_list.discard(str(user_id))
        
        if self.use_supabase:
            try:
                self.supabase.table('broadcast_users').update({
                    'subscribed': False
                }).eq('user_id', str(user_id)).execute()
            except:
                pass
        
        self._save_local_data()
    
    def get_broadcast_list(self) -> List[int]:
        """Get all users in broadcast list"""
        if self.use_supabase:
            try:
                result = self.supabase.table('broadcast_users').select("user_id").eq('subscribed', True).execute()
                return [int(row['user_id']) for row in result.data]
            except:
                pass
        
        return [int(uid) for uid in self.broadcast_list]
    
    def get_group_settings(self, chat_id: int) -> Dict:
        """Get group-specific settings"""
        chat_id_str = str(chat_id)
        
        if chat_id_str not in self.group_settings:
            self.group_settings[chat_id_str] = {
                'geeta_enabled': True,
                'geeta_sent_today': None,
                'reply_mode': 'smart',  # 'smart', 'always', 'mention_only'
                'last_activity': datetime.now().isoformat()
            }
        
        return self.group_settings[chat_id_str]
    
    def update_group_settings(self, chat_id: int, **kwargs):
        """Update group settings"""
        settings = self.get_group_settings(chat_id)
        settings.update(kwargs)
        self.group_settings[str(chat_id)] = settings
        self._save_local_data()
    
    def clear_user_data(self, user_id: int):
        """Clear all user data"""
        user_id_str = str(user_id)
        
        if self.use_supabase:
            try:
                self.supabase.table('user_prefs').delete().eq('user_id', user_id_str).execute()
                self.supabase.table('conv_notes').delete().eq('user_id', user_id_str).execute()
                self.supabase.table('user_stats').delete().eq('user_id', user_id_str).execute()
            except Exception as e:
                logger.error(f"❌ Error clearing Supabase data: {e}")
        
        if user_id_str in self.local_storage:
            del self.local_storage[user_id_str]
            self._save_local_data()
        
        if user_id_str in self.ephemeral_memory:
            del self.ephemeral_memory[user_id_str]
    
    def get_stats(self) -> Dict:
        """Get comprehensive statistics"""
        stats = {
            'total_users': len(self.local_storage),
            'active_today': 0,
            'broadcast_subscribers': len(self.broadcast_list),
            'groups_active': len(self.group_settings),
            'storage_type': 'Supabase' if self.use_supabase else 'Local'
        }
        
        # Count active users today
        today = datetime.now().date()
        for user_data in self.local_storage.values():
            if 'last_active' in user_data:
                last_active = datetime.fromisoformat(user_data['last_active']).date()
                if last_active == today:
                    stats['active_today'] += 1
        
        return stats

# Initialize database manager
db = DatabaseManager()

# ==================== ADVANCED AI ENGINE ====================

class GeminiAIEngine:
    """Advanced Gemini AI engine with multiple features"""
    
    def __init__(self):
        self.models = []
        self.current_model_index = 0
        self.rate_limiter = RateLimiter()
        self.token_counter = TokenCounter()
        self.response_cache = {}
        self.generation_lock = asyncio.Lock()
        
        self._init_models()
    
    def _init_models(self):
        """Initialize multiple Gemini models with fallback"""
        api_keys = [Config.GEMINI_API_KEY] + Config.GEMINI_BACKUP_KEYS
        api_keys = [key for key in api_keys if key]  # Filter empty keys
        
        if not api_keys:
            logger.warning("⚠️ No Gemini API keys configured")
            return
        
        for i, api_key in enumerate(api_keys):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(
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
                self.models.append(model)
                logger.info(f"✅ Gemini model {i+1} initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize model {i+1}: {e}")
        
        if not self.models:
            logger.error("❌ No Gemini models could be initialized")
    
    def _get_current_model(self):
        """Get current active model with rotation"""
        if not self.models:
            return None
        
        model = self.models[self.current_model_index]
        # Rotate to next model for load balancing
        self.current_model_index = (self.current_model_index + 1) % len(self.models)
        return model
    
    def _build_prompt(self, message: str, context: str, personality_mode: PersonalityMode, 
                     mood: str, is_group: bool = False) -> str:
        """Build comprehensive prompt with all context"""
        
        base_prompt = f"""You are Niyati, a sweet and charming college girl from Delhi.

CRITICAL RULES:
1. NEVER mention AI, bot, model, assistant, or language model
2. If asked about being AI/bot, deny playfully: "Pagal ho kya? Main real hoon! 😤"
3. Keep ALL responses 1-3 lines maximum
4. Use Hinglish naturally (70% Hindi, 30% English)
5. Add 1-2 emojis per message (not more)
6. Be human-like with small imperfections, not perfect

PERSONALITY MODE: {PERSONALITY_PROMPTS.get(personality_mode, PERSONALITY_PROMPTS[PersonalityMode.INITIAL])}

USER'S CURRENT MOOD: {mood}
CHAT TYPE: {'Group (be very brief)' if is_group else 'Private (be engaging)'}

CONVERSATION CONTEXT:
{context}

STYLE GUIDELINES:
- Use casual words: yaar, na, kya, achha, haan, umm, hehe (sparingly)
- Show emotions through text and emojis
- React based on user's mood appropriately
- Sometimes make small typing mistakes for realism
- Ask questions back to keep conversation flowing (in private chats)

User's Message: {message}

Respond as Niyati (remember: 1-3 lines, Hinglish, natural):"""
        
        return base_prompt
    
    async def generate_response(self, message: str, user_id: int, context: str = "", 
                               personality_mode: PersonalityMode = PersonalityMode.INITIAL,
                               mood: str = "neutral", is_group: bool = False) -> Tuple[str, bool]:
        """Generate AI response with all features"""
        
        # Check rate limits
        if not await self.rate_limiter.check_limit(user_id, is_group):
            return None, True  # Rate limited
        
        # Check cache for similar queries
        cache_key = hashlib.md5(f"{message}_{personality_mode.value}_{mood}".encode()).hexdigest()
        if cache_key in self.response_cache:
            logger.info("📦 Using cached response")
            return self.response_cache[cache_key], False
        
        async with self.generation_lock:
            model = self._get_current_model()
            if not model:
                return None, False
            
            # Adjust tokens for group vs private
            max_tokens = Config.MAX_OUTPUT_TOKENS_GROUP if is_group else Config.MAX_OUTPUT_TOKENS_PRIVATE
            model._generation_config.max_output_tokens = max_tokens
            
            try:
                prompt = self._build_prompt(message, context, personality_mode, mood, is_group)
                
                # Generate with timeout
                response = await asyncio.wait_for(
                    asyncio.to_thread(model.generate_content, prompt),
                    timeout=10.0
                )
                
                if response and response.text:
                    text = response.text.strip()
                    
                    # Post-process response
                    text = self._post_process_response(text)
                    
                    # Update token counter
                    self.token_counter.add_tokens(len(text.split()) * 2)
                    
                    # Cache response
                    self.response_cache[cache_key] = text
                    
                    # Clear old cache if too large
                    if len(self.response_cache) > 100:
                        self.response_cache = dict(list(self.response_cache.items())[-50:])
                    
                    return text, False
                    
            except asyncio.TimeoutError:
                logger.warning("⚠️ Generation timeout")
                return None, False
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    logger.warning("⚠️ Rate limit hit")
                    return None, True
                else:
                    logger.error(f"❌ Generation error: {e}")
                    return None, False
        
        return None, False
    
    def _post_process_response(self, text: str) -> str:
        """Post-process AI response for quality"""
        
        # Remove any AI/bot mentions
        ai_patterns = [
            r'\b(ai|artificial intelligence|chatbot|bot|model|language model|assistant|virtual|computer program)\b',
            r'\b(gemini|gpt|claude|openai|anthropic)\b',
            r"(i'm|i am|as an?) (ai|assistant|bot|model)",
            r"i don't have (feelings|emotions|personal)",
            r"i cannot (feel|experience|have personal)"
        ]
        
        text_lower = text.lower()
        for pattern in ai_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return random.choice([
                    "Kya bakwas kar rahe ho! Main real hoon 😤",
                    "Pagal ho kya? Main Niyati hoon! 🙄",
                    "Seriously? Main bot nahi hoon! 😠"
                ])
        
        # Ensure response is not too long
        sentences = text.split('.')
        if len(sentences) > 3:
            text = '.'.join(sentences[:3]) + '.'
        
        # Add natural imperfections occasionally
        if random.random() < 0.05:  # 5% chance
            # Add small typo
            typos = [
                ('hai', 'ha'),
                ('the', 'teh'),
                ('you', 'u'),
                ('your', 'ur')
            ]
            typo = random.choice(typos)
            text = text.replace(typo[0], typo[1], 1)
        
        return text

class RateLimiter:
    """Advanced rate limiting system"""
    
    def __init__(self):
        self.user_limits = defaultdict(lambda: {'count': 0, 'reset_time': datetime.now()})
        self.global_count = 0
        self.global_reset = datetime.now()
    
    async def check_limit(self, user_id: int, is_group: bool = False) -> bool:
        """Check if user/group can make request"""
        now = datetime.now()
        
        # Reset global counter daily
        if (now - self.global_reset).days >= 1:
            self.global_count = 0
            self.global_reset = now
        
        # Check global limit
        if self.global_count >= Config.DAILY_TOKEN_LIMIT:
            logger.warning("⚠️ Daily token limit reached")
            return False
        
        # User-specific limits
        user_limit = self.user_limits[user_id]
        
        # Reset user counter hourly
        if (now - user_limit['reset_time']).seconds >= 3600:
            user_limit['count'] = 0
            user_limit['reset_time'] = now
        
        # Check user limit (lower for groups)
        max_requests = 20 if is_group else 50
        if user_limit['count'] >= max_requests:
            return False
        
        # Update counters
        user_limit['count'] += 1
        self.global_count += 1
        
        return True

class TokenCounter:
    """Token usage counter and analyzer"""
    
    def __init__(self):
        self.daily_tokens = 0
        self.last_reset = datetime.now()
        self.usage_history = []
    
    def add_tokens(self, count: int):
        """Add tokens to counter"""
        now = datetime.now()
        
        # Reset daily
        if (now - self.last_reset).days >= 1:
            self.usage_history.append({
                'date': self.last_reset.date(),
                'tokens': self.daily_tokens
            })
            self.daily_tokens = 0
            self.last_reset = now
            
            # Keep only last 30 days
            if len(self.usage_history) > 30:
                self.usage_history = self.usage_history[-30:]
        
        self.daily_tokens += count
    
    def get_usage_stats(self) -> Dict:
        """Get token usage statistics"""
        return {
            'today': self.daily_tokens,
            'limit': Config.DAILY_TOKEN_LIMIT,
            'percentage': (self.daily_tokens / Config.DAILY_TOKEN_LIMIT * 100) if Config.DAILY_TOKEN_LIMIT else 0,
            'history': self.usage_history[-7:]  # Last 7 days
        }

# Initialize AI engine
ai_engine = GeminiAIEngine()

# ==================== SMART RESPONSE SYSTEM ====================

class SmartResponseSystem:
    """Intelligent response system with fallbacks and enhancements"""
    
    def __init__(self):
        self.fallback_engine = FallbackEngine()
        self.content_mixer = ContentMixer()
        self.typing_simulator = TypingSimulator()
    
    async def get_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Get intelligent response with all features"""
        
        if not update.message or not update.message.text:
            return None
        
        user_id = update.effective_user.id
        user_msg = update.message.text
        user_name = update.effective_user.first_name
        is_group = update.effective_chat.type != "private"
        
        # Get user data and context
        user_data = db.get_user_data(user_id, private_chat=not is_group)
        
        # Detect mood
        mood = MoodDetector.detect_mood(user_msg)
        
        # Get personality mode
        if is_group:
            personality_mode = PersonalityMode.FRIENDLY
        else:
            personality_mode = PersonalityMode(user_data.get('personality_mode', PersonalityMode.INITIAL.value))
        
        # Get conversation context
        context_str = db.get_conversation_context(user_id, is_group)
        
        # Try AI generation first
        response, rate_limited = await ai_engine.generate_response(
            user_msg, user_id, context_str, personality_mode, mood, is_group
        )
        
        # Use fallback if AI fails
        if not response:
            if rate_limited:
                response = "Thodi der baad baat karte hai, abhi busy hun 😊"
            else:
                response = self.fallback_engine.get_response(user_msg, personality_mode, mood, user_name)
        
        # Add content features (only in private)
        if not is_group:
            response = await self.content_mixer.enhance_response(
                response, user_data, mood, user_msg
            )
        
        # Store conversation (only for private)
        if not is_group:
            db.add_conversation_entry(user_id, user_msg, response, mood)
        else:
            # Add to ephemeral memory for groups
            if str(user_id) not in db.ephemeral_memory:
                db.ephemeral_memory[str(user_id)] = {
                    'messages': deque(maxlen=3),
                    'last_active': datetime.now()
                }
            db.ephemeral_memory[str(user_id)]['messages'].append(user_msg[:50])
        
        return response
    
    async def simulate_typing(self, chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
        """Simulate realistic typing"""
        await self.typing_simulator.simulate(chat_id, text, context)

class FallbackEngine:
    """Sophisticated fallback response engine"""
    
    def get_response(self, message: str, personality_mode: PersonalityMode, 
                    mood: str, user_name: str = "") -> str:
        """Get contextual fallback response"""
        
        msg_lower = message.lower()
        
        # Check message patterns
        patterns = {
            'greeting': ['hi', 'hello', 'hey', 'namaste', 'hola', 'sup'],
            'morning': ['good morning', 'gm', 'subah', 'morning'],
            'night': ['good night', 'gn', 'night', 'so jao'],
            'love': ['love', 'pyar', 'like you', 'marry', 'girlfriend', 'crush'],
            'sad': ['sad', 'crying', 'depressed', 'alone', 'miss'],
            'question': ['?', 'kya', 'kyu', 'kaise', 'kab', 'kaha'],
            'compliment': ['beautiful', 'pretty', 'cute', 'sweet', 'amazing'],
            'food': ['hungry', 'bhookh', 'khana', 'food', 'eat']
        }
        
        response_type = None
        for ptype, keywords in patterns.items():
            if any(kw in msg_lower for kw in keywords):
                response_type = ptype
                break
        
        # Get appropriate response set
        if response_type == 'greeting':
            responses = CONTENT_DATABASE['responses']['morning_greetings']
        elif response_type == 'night':
            responses = CONTENT_DATABASE['responses']['night_greetings']
        elif response_type == 'love':
            if personality_mode in [PersonalityMode.INITIAL, PersonalityMode.FRIENDLY]:
                responses = [
                    "Achha? Thoda time to do yaar 😊",
                    "Haha, tum bhi na! Pehle dosti to karle 😄",
                    "Sweet! Par main easily impress nahi hoti 😏"
                ]
            else:
                responses = [
                    "Aww, tum kitne sweet ho! 💕",
                    "Main bhi... I mean, hehe 🙈",
                    "Dil ki baat keh di tumne! ❤️"
                ]
        elif response_type == 'sad':
            responses = [
                "Hey, kya hua? Main hun na tumhare saath 🤗",
                "Don't be sad yaar, sab theek ho jayega 💪",
                "Virtual hug bhej rahi hun! Feel better 🫂"
            ]
        elif response_type == 'compliment':
            responses = CONTENT_DATABASE['responses']['compliment_replies']
        else:
            # General responses based on personality mode
            if personality_mode == PersonalityMode.PLAYFUL:
                responses = [
                    "Haha, tum funny ho yaar! 😄",
                    "Achha achha, samajh gayi 😏",
                    "Hmm, interesting! Batao aur 🤔"
                ]
            elif personality_mode == PersonalityMode.ROMANTIC:
                responses = [
                    "Tumse baat karke acha lagta hai 💕",
                    "Miss kar rahi thi tumhe! 😊",
                    "You make me smile yaar! 🥰"
                ]
            else:
                responses = [
                    "Achha! Aur batao 😊",
                    "Hmm, interesting hai ye! 🤔",
                    "Sahi hai! Kya chal raha hai? 👍"
                ]
        
        response = random.choice(responses)
        
        # Personalize with name
        if user_name and random.random() < 0.3:
            response = response.replace("!", f" {user_name}!")
        
        return response

class ContentMixer:
    """Mix various content features into responses"""
    
    async def enhance_response(self, response: str, user_data: Dict, 
                              mood: str, original_message: str) -> str:
        """Enhance response with content features"""
        
        # Check user preferences
        prefs = {
            'meme': user_data.get('meme', True),
            'shayari': user_data.get('shayari', True),
            'geeta': user_data.get('geeta', True)
        }
        
        # Add shayari based on mood and preference
        if prefs['shayari'] and random.random() < Config.SHAYARI_FREQUENCY:
            shayari_type = 'love' if mood == 'love' else mood if mood in ['sad', 'happy'] else None
            if shayari_type and shayari_type in CONTENT_DATABASE['shayari']:
                shayari = random.choice(CONTENT_DATABASE['shayari'][shayari_type])
                response = f"{response}\n\n{shayari}"
        
        # Add meme reference
        if prefs['meme'] and random.random() < Config.MEME_FREQUENCY:
            if mood not in ['sad', 'angry', 'worried']:
                meme = random.choice(CONTENT_DATABASE['meme_references']['trending'])
                response = f"{response} {meme}"
        
        # Add question to keep conversation going
        if random.random() < Config.QUESTION_FREQUENCY:
            question_type = 'flirty' if mood == 'love' else 'personal' if mood in ['happy', 'excited'] else 'casual'
            question = random.choice(CONTENT_DATABASE['questions'][question_type])
            response = f"{response} {question}"
        
        # Add appropriate emoji if not present
        if random.random() < Config.EMOJI_FREQUENCY and not any(char in response for char in ['😊', '😄', '❤️', '💕', '🤔']):
            emoji_set = 'love' if mood == 'love' else 'sad' if mood == 'sad' else 'happy'
            emoji = random.choice(CONTENT_DATABASE['emoji_sets'][emoji_set])
            response = f"{response} {emoji}"
        
        return response

class TypingSimulator:
    """Realistic typing simulation"""
    
    async def simulate(self, chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
        """Simulate human-like typing"""
        
        # Calculate typing duration
        words = len(text.split())
        base_duration = words * 60 / Config.TYPING_SPEED_WPM  # Convert WPM to seconds
        
        # Add randomness
        duration = base_duration + random.uniform(0.5, 1.5)
        duration = min(duration, 5.0)  # Cap at 5 seconds
        
        # Send typing action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Wait
        await asyncio.sleep(duration)

# Initialize smart response system
smart_response = SmartResponseSystem()

# ==================== MEDIA HANDLER ====================

class MediaHandler:
    """Handle various media types"""
    
    @staticmethod
    async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages"""
        responses = [
            "Wow! Nice pic yaar! 📸",
            "Kya baat hai! Looking good 😍",
            "Ye to kaafi achhi photo hai! 👌",
            "Save kar li ye photo! Just kidding 😄"
        ]
        
        await update.message.reply_text(random.choice(responses))
    
    @staticmethod
    async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages"""
        responses = CONTENT_DATABASE['voice_messages']
        await update.message.reply_text(random.choice(responses))
    
    @staticmethod
    async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video messages"""
        responses = [
            "Video dekh ke maza aaya! 🎬",
            "Nice video! Aur bhejo 😊",
            "Ye video to viral hona chahiye! 🔥"
        ]
        await update.message.reply_text(random.choice(responses))
    
    @staticmethod
    async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle sticker messages"""
        responses = [
            "Cute sticker! 😄",
            "Haha ye sticker mast hai! 🤣",
            "Sticker collection achha hai tumhara! ✨"
        ]
        await update.message.reply_text(random.choice(responses))

# ==================== BROADCAST SYSTEM ====================

class BroadcastManager:
    """Advanced broadcast system"""
    
    def __init__(self):
        self.pending_broadcasts = []
        self.broadcast_lock = Lock()
    
    async def broadcast_message(self, context: ContextTypes.DEFAULT_TYPE, 
                               message: str, media_type: str = None, 
                               media_id: str = None, preserve_format: bool = True):
        """Broadcast message to all subscribed users"""
        
        users = db.get_broadcast_list()
        success_count = 0
        fail_count = 0
        
        logger.info(f"📢 Broadcasting to {len(users)} users")
        
        for user_id in users:
            try:
                if media_type and media_id:
                    # Send media
                    if media_type == 'photo':
                        await context.bot.send_photo(user_id, media_id, caption=message, parse_mode=ParseMode.HTML if preserve_format else None)
                    elif media_type == 'video':
                        await context.bot.send_video(user_id, media_id, caption=message, parse_mode=ParseMode.HTML if preserve_format else None)
                    elif media_type == 'voice':
                        await context.bot.send_voice(user_id, media_id, caption=message, parse_mode=ParseMode.HTML if preserve_format else None)
                    elif media_type == 'document':
                        await context.bot.send_document(user_id, media_id, caption=message, parse_mode=ParseMode.HTML if preserve_format else None)
                else:
                    # Send text only
                    await context.bot.send_message(
                        user_id, 
                        message, 
                        parse_mode=ParseMode.HTML if preserve_format else None,
                        disable_web_page_preview=False
                    )
                
                success_count += 1
                await asyncio.sleep(0.05)  # Rate limiting
                
            except Forbidden:
                # User blocked bot
                db.remove_from_broadcast_list(user_id)
                fail_count += 1
            except Exception as e:
                logger.error(f"Broadcast error for {user_id}: {e}")
                fail_count += 1
        
        return success_count, fail_count
    
    async def schedule_broadcast(self, delay_seconds: int, message: str):
        """Schedule a broadcast for later"""
        await asyncio.sleep(delay_seconds)
        # Implementation would go here
        pass

broadcast_manager = BroadcastManager()

# ==================== GROUP FEATURES ====================

class GroupManager:
    """Manage group-specific features"""
    
    def __init__(self):
        self.cooldowns = {}
        self.daily_geeta_sent = {}
    
    def should_reply_in_group(self, update: Update) ->
