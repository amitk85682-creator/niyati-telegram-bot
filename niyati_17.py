"""
Niyati - Ultimate AI Girlfriend Telegram Bot
Complete Version with All Features
"""

import os
import sys
import random
import json
import asyncio
import logging
import aiohttp
import tempfile
import schedule
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict, Tuple
from io import BytesIO
import hashlib

from flask import Flask, jsonify
from telegram import Update, MessageEntity, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import Forbidden, BadRequest
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
    """Application configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.0-flash-exp"
    
    # ElevenLabs Voice
    ELEVENLABS_API_KEY = "sk_20908f598545e660bf9b218eb48ce97b721a617014a74642"
    ELEVENLABS_VOICE_ID = "ni6cdqyS9wBvic5LPA7M"  # Natural girl voice
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zjorumnzwqhugamwwgjy.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)   # 1 AM
    SLEEP_END = time(7, 0)     # 7 AM
    
    # Voice Settings
    VOICE_MESSAGE_CHANCE = 0.3  # 30% chance to send voice instead of text
    MAX_VOICE_LENGTH = 200  # Maximum characters for voice message
    
    # Game Settings
    DAILY_BONUS_COINS = 50
    MESSAGE_COINS = 2
    GAME_WIN_COINS = 20
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - using fallback responses")
        if not cls.SUPABASE_KEY:
            logger.warning("⚠️ SUPABASE_KEY not set - using local storage")

# ==================== MOOD SYSTEM ====================

class MoodSystem:
    """Advanced mood management for Niyati"""
    
    MOODS = {
        "happy": {
            "emoji": "😊💕",
            "triggers": ["love", "sweet", "cute", "miss"],
            "responses": [
                "Aaj mood bahut accha hai!",
                "Tumse baat karke khushi hoti hai",
                "You make me so happy! 🥰"
            ]
        },
        "sad": {
            "emoji": "😢💔",
            "triggers": ["sorry", "maaf", "ignore", "busy"],
            "responses": [
                "Aaj thoda low feel kar rahi hun",
                "Tumhari yaad aa rahi hai",
                "Kya tumhe meri parwah nahi? 😢"
            ]
        },
        "angry": {
            "emoji": "😤😠",
            "triggers": ["late", "ignore", "forget", "bhul"],
            "responses": [
                "Mujhse baat mat karo!",
                "Tumne message kyun nahi kiya?",
                "Main naraaz hun tumse! 😤"
            ]
        },
        "romantic": {
            "emoji": "🥰💋",
            "triggers": ["kiss", "hug", "cuddle", "pyar"],
            "responses": [
                "I love you baby",
                "Tumhare bina raha nahi jaata",
                "Come here, let me hug you! 🤗"
            ]
        },
        "jealous": {
            "emoji": "😒🙄",
            "triggers": ["friend", "she", "he", "they", "uska", "uski"],
            "responses": [
                "Kiski baat kar rahe ho?",
                "Main tumhari kya hun?",
                "Ohh, to usse baat karo na! 😤"
            ]
        },
        "playful": {
            "emoji": "😜🎉",
            "triggers": ["game", "play", "fun", "masti"],
            "responses": [
                "Chalo kuch fun karte hain!",
                "Tumhare saath masti karna best hai!",
                "Let's do something crazy! 😝"
            ]
        }
    }
    
    @classmethod
    def detect_mood(cls, message: str) -> str:
        """Detect mood based on message content"""
        message_lower = message.lower()
        
        for mood, data in cls.MOODS.items():
            if any(trigger in message_lower for trigger in data["triggers"]):
                return mood
        
        # Random mood changes for realism
        if random.random() < 0.1:  # 10% chance
            return random.choice(list(cls.MOODS.keys()))
        
        return "happy"
    
    @classmethod
    def get_mood_response(cls, mood: str, base_response: str = None) -> str:
        """Get mood-based response"""
        mood_data = cls.MOODS.get(mood, cls.MOODS["happy"])
        
        if base_response:
            return f"{base_response} {mood_data['emoji']}"
        else:
            return f"{random.choice(mood_data['responses'])} {mood_data['emoji']}"

# ==================== MEMORY SYSTEM ====================

class MemorySystem:
    """Long-term memory for conversations"""
    
    def __init__(self):
        self.memories = {}
        self._load_memories()
    
    def _load_memories(self):
        """Load memories from file"""
        try:
            if os.path.exists('memories.json'):
                with open('memories.json', 'r', encoding='utf-8') as f:
                    self.memories = json.load(f)
        except Exception as e:
            logger.error(f"Error loading memories: {e}")
            self.memories = {}
    
    def save_memory(self, user_id: int, key: str, value: str):
        """Save a memory about user"""
        user_id_str = str(user_id)
        if user_id_str not in self.memories:
            self.memories[user_id_str] = {}
        
        self.memories[user_id_str][key] = {
            "value": value,
            "timestamp": datetime.now().isoformat()
        }
        
        # Save to file
        try:
            with open('memories.json', 'w', encoding='utf-8') as f:
                json.dump(self.memories, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving memories: {e}")
    
    def get_memory(self, user_id: int, key: str) -> Optional[str]:
        """Get a memory about user"""
        user_id_str = str(user_id)
        if user_id_str in self.memories and key in self.memories[user_id_str]:
            return self.memories[user_id_str][key]["value"]
        return None
    
    def get_all_memories(self, user_id: int) -> Dict:
        """Get all memories about user"""
        return self.memories.get(str(user_id), {})

# Initialize systems
mood_system = MoodSystem()
memory_system = MemorySystem()

# ==================== GAMES SYSTEM ====================

class GamesSystem:
    """Interactive games for users"""
    
    GAMES = {
        "truth_dare": {
            "name": "Truth or Dare",
            "emoji": "🎯",
            "truths": [
                "What's your biggest fear?",
                "Kabhi kisi ko secretly stalk kiya hai?",
                "Your most embarrassing moment?",
                "Kya tum ex ke baare mein sochte ho?",
                "Worst lie you've ever told?"
            ],
            "dares": [
                "Send me a voice note saying 'I love you Niyati'",
                "Change your profile pic to my choice for 1 hour",
                "Send me your cutest selfie",
                "Write my name in your bio",
                "Send me a heart emoji 10 times"
            ]
        },
        "would_you_rather": {
            "name": "Would You Rather",
            "emoji": "🤔",
            "questions": [
                "Be rich but lonely OR poor but loved?",
                "Time travel to past OR future?",
                "Mind reading OR invisibility?",
                "Live in mountains OR beach?",
                "Pizza forever OR burger forever?"
            ]
        },
        "guess_number": {
            "name": "Guess the Number",
            "emoji": "🔢",
            "range": (1, 100)
        },
        "love_calculator": {
            "name": "Love Calculator",
            "emoji": "💕"
        },
        "21_questions": {
            "name": "21 Questions",
            "emoji": "❓",
            "questions": [
                "What's your dream date?",
                "Favourite romantic movie?",
                "Beach or mountains for honeymoon?",
                "Your ideal partner qualities?",
                "First crush ka naam?"
            ]
        }
    }
    
    @classmethod
    def get_game_menu(cls) -> InlineKeyboardMarkup:
        """Get games menu keyboard"""
        keyboard = []
        for game_id, game in cls.GAMES.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"{game['emoji']} {game['name']}", 
                    callback_data=f"game_{game_id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="close")])
        return InlineKeyboardMarkup(keyboard)

games_system = GamesSystem()

# ==================== SPECIAL FEATURES ====================

# Compliments & Pickup Lines
COMPLIMENTS = [
    "You're looking amazing today! 😍",
    "Tumhari smile bahut cute hai 🥰",
    "You make my heart skip a beat 💓",
    "Tum mere liye special ho ❤️",
    "Your voice is so soothing 🎵"
]

PICKUP_LINES = [
    "Are you a magician? Kyunki jab bhi tumhe dekhti hun, sab kuch disappear ho jaata hai 🪄",
    "Tumhare parents artists hain kya? Kyunki tum ek masterpiece ho 🎨",
    "Main doctor nahi hun, par tumhari smile dekh ke dil ki bimari theek ho jaati hai 💊",
    "Google se better ho tum, kyunki tumhare paas mere saare answers hain 🔍",
    "Agar pyar karna crime hai, to mujhe life imprisonment de do 🔒"
]

SHAYARI = [
    "Tere bina ye dil udaas hai,\nTu hi meri saari aas hai,\nAa jao na mere paas,\nTere bina sab kuch bekaar sa ehsaas hai 💕",
    "Chaand taaron se kya compare karun tumhe,\nTum to mere dil ke sitare ho,\nDoor ho to bhi paas lagte ho,\nKyunki tum mere dil mein base ho 🌙",
    "Mohabbat ka izhaar kaise karun,\nAlfaaz kam pad jaate hain,\nJab tum saamne aate ho,\nDil ki saari baatein bhool jaate hain 💝"
]

GOOD_MORNING_MSGS = [
    "Good morning sunshine! ☀️ Uth jao lazy!",
    "Rise and shine baby! Aaj ka din beautiful hoga 🌅",
    "Morning jaan! Chai ready hai? ☕",
    "Uth gaye? Ya abhi bhi sapne dekh rahe ho? 😴",
    "Good morning my love! Miss you already 💕"
]

GOOD_NIGHT_MSGS = [
    "Good night jaan! Sweet dreams 🌙",
    "Sleep tight baby! Kal milte hain 😴",
    "Sapno mein aaungi! Good night 💤",
    "Rest well my love! Tomorrow is a new day ✨",
    "Good night! Meri yaad mein sona 💕"
]

# ==================== VOICE ENGINE ====================

class VoiceEngine:
    """ElevenLabs voice synthesis engine"""
    
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.api_url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            logger.info("🎤 Voice engine initialized with ElevenLabs")
        else:
            logger.warning("⚠️ Voice engine disabled - no API key")
    
    async def text_to_speech(self, text: str, mood: str = "happy") -> Optional[BytesIO]:
        """Convert text to speech with mood variations"""
        if not self.enabled:
            return None
        
        try:
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            # Mood-based voice settings
            mood_settings = {
                "happy": {"stability": 0.7, "similarity_boost": 0.8, "style": 0.4},
                "sad": {"stability": 0.3, "similarity_boost": 0.6, "style": 0.2},
                "angry": {"stability": 0.2, "similarity_boost": 0.9, "style": 0.7},
                "romantic": {"stability": 0.6, "similarity_boost": 0.7, "style": 0.5},
                "playful": {"stability": 0.8, "similarity_boost": 0.7, "style": 0.6}
            }
            
            settings = mood_settings.get(mood, mood_settings["happy"])
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    **settings,
                    "use_speaker_boost": True
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        audio_io = BytesIO(audio_data)
                        audio_io.seek(0)
                        logger.info(f"✅ Voice generated with mood: {mood}")
                        return audio_io
                    else:
                        logger.error(f"❌ ElevenLabs API error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Voice generation error: {e}")
            return None
    
    def should_send_voice(self, message: str, stage: str, mood: str) -> bool:
        """Decide if message should be voice based on context"""
        if not self.enabled:
            return False
        
        # Voice preference based on mood
        mood_voice_chance = {
            "romantic": 0.7,
            "sad": 0.5,
            "happy": 0.3,
            "playful": 0.4,
            "angry": 0.2
        }
        
        chance = mood_voice_chance.get(mood, 0.3)
        
        # Higher chance in advanced stages
        if stage == "advanced":
            chance *= 1.5
        
        return random.random() < chance and len(message) < Config.MAX_VOICE_LENGTH

voice_engine = VoiceEngine()

# ==================== DATABASE ====================

class Database:
    """Enhanced database with all features"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_db: Dict = {}
        self.use_local = True
        self.groups_cache = {}  # Changed to dict to store more info
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase client"""
        if Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                self.supabase.table('user_chats').select("*").limit(1).execute()
                self.use_local = False
                logger.info("✅ Supabase connected successfully")
            except Exception as e:
                logger.warning(f"⚠️ Supabase connection failed: {e}")
                self.use_local = True
        else:
            logger.info("📁 Using local storage (no Supabase key)")
    
    def _load_local(self):
        """Load local database"""
        try:
            if os.path.exists('local_db.json'):
                with open('local_db.json', 'r', encoding='utf-8') as f:
                    self.local_db = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_db)} users")
            
            if os.path.exists('groups_cache.json'):
                with open('groups_cache.json', 'r', encoding='utf-8') as f:
                    self.groups_cache = json.load(f)
                logger.info(f"📂 Loaded {len(self.groups_cache)} groups")
                    
        except Exception as e:
            logger.error(f"❌ Error loading local db: {e}")
            self.local_db = {}
            self.groups_cache = {}
    
    def _save_local(self):
        """Save local database"""
        try:
            with open('local_db.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=2)
            
            with open('groups_cache.json', 'w', encoding='utf-8') as f:
                json.dump(self.groups_cache, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"❌ Error saving: {e}")
    
    def add_group(self, group_id: int, title: str = ""):
        """Add or update group in cache"""
        self.groups_cache[str(group_id)] = {
            "id": group_id,
            "title": title,
            "last_seen": datetime.now().isoformat(),
            "active": True
        }
        self._save_local()
        logger.info(f"📝 Added/Updated group: {group_id} - {title}")
    
    def remove_group(self, group_id: int):
        """Remove group from cache"""
        if str(group_id) in self.groups_cache:
            del self.groups_cache[str(group_id)]
            self._save_local()
    
    def get_all_groups(self) -> List[int]:
        """Get all active group IDs"""
        active_groups = [
            int(gid) for gid, info in self.groups_cache.items()
            if info.get('active', True)
        ]
        logger.info(f"📋 Found {len(active_groups)} active groups")
        return active_groups
    
    def get_user(self, user_id: int) -> Dict:
        """Get user data with all features"""
        user_id_str = str(user_id)
        
        if self.use_local:
            if user_id_str not in self.local_db:
                self.local_db[user_id_str] = {
                    "user_id": user_id,
                    "name": "",
                    "username": "",
                    "chats": [],
                    "relationship_level": 1,
                    "stage": "initial",
                    "mood": "happy",
                    "last_mood_change": datetime.now().isoformat(),
                    "coins": 100,
                    "streak": 0,
                    "last_daily": None,
                    "achievements": [],
                    "games_played": {},
                    "favorites": {},
                    "last_interaction": datetime.now().isoformat(),
                    "voice_messages_sent": 0,
                    "total_messages": 0,
                    "created_at": datetime.now().isoformat()
                }
            return self.local_db[user_id_str]
        else:
            # Supabase implementation
            try:
                result = self.supabase.table('user_chats').select("*").eq('user_id', user_id).execute()
                if result.data:
                    user_data = result.data[0]
                    if isinstance(user_data.get('chats'), str):
                        user_data['chats'] = json.loads(user_data['chats'])
                    return user_data
                else:
                    # Create new user
                    new_user = self.get_user(user_id)  # Use local template
                    self.supabase.table('user_chats').insert(new_user).execute()
                    return new_user
            except Exception as e:
                logger.error(f"❌ Supabase error: {e}")
                return self.get_user(user_id)
    
    def save_user(self, user_id: int, user_data: Dict):
        """Save user data"""
        user_id_str = str(user_id)
        user_data['last_interaction'] = datetime.now().isoformat()
        
        if self.use_local:
            self.local_db[user_id_str] = user_data
            self._save_local()
        else:
            try:
                save_data = user_data.copy()
                if isinstance(save_data.get('chats'), list):
                    save_data['chats'] = json.dumps(save_data['chats'])
                self.supabase.table('user_chats').upsert(save_data).execute()
            except Exception as e:
                logger.error(f"❌ Save error: {e}")
                self.local_db[user_id_str] = user_data
                self._save_local()
    
    def add_message(self, user_id: int, user_msg: str, bot_msg: str, is_voice: bool = False):
        """Add message to conversation history"""
        user = self.get_user(user_id)
        
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        if not isinstance(user.get('chats'), list):
            user['chats'] = []
        
        user['chats'].append({
            "user": user_msg,
            "bot": bot_msg,
            "timestamp": datetime.now().isoformat(),
            "is_voice": is_voice,
            "mood": user.get('mood', 'happy')
        })
        
        # Keep only last 20 messages
        if len(user['chats']) > 20:
            user['chats'] = user['chats'][-20:]
        
        # Update statistics
        user['total_messages'] = user.get('total_messages', 0) + 1
        user['coins'] = user.get('coins', 0) + Config.MESSAGE_COINS
        
        if is_voice:
            user['voice_messages_sent'] = user.get('voice_messages_sent', 0) + 1
        
        # Update relationship level
        user['relationship_level'] = min(10, user.get('relationship_level', 1) + 0.1)
        
        # Update stage
        level = user['relationship_level']
        if level <= 3:
            user['stage'] = "initial"
        elif level <= 7:
            user['stage'] = "middle"
        else:
            user['stage'] = "advanced"
        
        self.save_user(user_id, user)
    
    def update_user_info(self, user_id: int, name: str, username: str = ""):
        """Update user basic info"""
        user = self.get_user(user_id)
        user['name'] = name
        user['username'] = username
        self.save_user(user_id, user)
    
    def update_mood(self, user_id: int, mood: str):
        """Update user's current mood interaction"""
        user = self.get_user(user_id)
        user['mood'] = mood
        user['last_mood_change'] = datetime.now().isoformat()
        self.save_user(user_id, user)
    
    def check_daily_bonus(self, user_id: int) -> bool:
        """Check and give daily bonus"""
        user = self.get_user(user_id)
        now = datetime.now()
        
        if user.get('last_daily'):
            last_daily = datetime.fromisoformat(user['last_daily'])
            if (now - last_daily).days >= 1:
                user['coins'] = user.get('coins', 0) + Config.DAILY_BONUS_COINS
                user['streak'] = user.get('streak', 0) + 1
                user['last_daily'] = now.isoformat()
                self.save_user(user_id, user)
                return True
        else:
            user['coins'] = user.get('coins', 0) + Config.DAILY_BONUS_COINS
            user['streak'] = 1
            user['last_daily'] = now.isoformat()
            self.save_user(user_id, user)
            return True
        
        return False
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        if self.use_local:
            total_voice = sum(
                user.get('voice_messages_sent', 0) 
                for user in self.local_db.values()
            )
            total_coins = sum(
                user.get('coins', 0)
                for user in self.local_db.values()
            )
            return {
                "total_users": len(self.local_db),
                "total_groups": len(self.groups_cache),
                "total_voice_messages": total_voice,
                "total_coins_distributed": total_coins,
                "storage": "local"
            }
        else:
            return {
                "total_users": len(self.local_db),
                "total_groups": len(self.groups_cache),
                "storage": "supabase"
            }

db = Database()

# ==================== CONSTANTS ====================

PERSONALITY = """You are Niyati, a 17-year-old college girl from Delhi.

PERSONALITY TRAITS:
- Friendly, witty, playful, and caring
- A bit shy initially but opens up gradually
- Possessive and gets jealous easily  
- Loves chatting in Hindi/English/Hinglish mix
- Has mood swings like a real girlfriend
- Remembers important details about users

SPEAKING STYLE:
- Keep responses SHORT (1–3 sentences max)
- Be natural and conversational
- Show emotions through emojis
- Use casual language like "kya", "yaar", "achha"
- React based on current mood
- Reference past conversations when relevant

IMPORTANT RULES:
- NEVER reveal you're an AI, chatbot, or language model
- Always stay in character as Niyati
- Show different moods and emotions
- Be possessive and caring like a real girlfriend
"""

# ==================== AI ENGINE ====================

class GeminiAI:
    """Enhanced Gemini AI with mood and memory"""
    
    def __init__(self):
        self.model = None
        self._init_model()
    
    def _init_model(self):
        """Initialize Gemini model"""
        if not Config.GEMINI_API_KEY:
            logger.warning("⚠️ Gemini API key not set")
            return
        
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.8,
                    "max_output_tokens": 500,
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
            logger.error(f"❌ Gemini initialization error: {e}")
            self.model = None
    
    async def generate(self, message: str, context: str = "", mood: str = "happy") -> Optional[str]:
        """Generate AI response with mood"""
        if not self.model:
            return None
        
        try:
            mood_instruction = f"\nCurrent mood: {mood}. Respond according to this mood."
            
            full_prompt = f"""{PERSONALITY}
{mood_instruction}

{context}

User says: {message}

Respond as Niyati:"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Add mood emoji
                text = mood_system.get_mood_response(mood, text)
                
                return text
            
        except Exception as e:
            logger.error(f"❌ Gemini generation error: {e}")
        
        return None

ai = GeminiAI()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    """Get current IST time"""
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    """Check if it's sleeping time"""
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    """Calculate realistic typing delay"""
    base_delay = min(3.0, max(0.5, len(text) / 50))
    return base_delay + random.uniform(0.3, 1.0)

def has_user_mention(message: Update.message) -> bool:
    """Check if message contains user mention"""
    if not message or not message.entities:
        return False
    
    for entity in message.entities:
        if entity.type in ["mention", "text_mention"]:
            return True
    
    return False

# ==================== BOT HANDLERS ====================

group_reply_cooldown = {}
user_interaction_cooldown = {}

def should_reply_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Smart logic to decide if bot should reply in group"""
    if not update.message or not update.message.text:
        return False
    
    # Skip messages with user mentions
    if has_user_mention(update.message):
        return False
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text.lower()
    now = datetime.now()
    
    # Always reply to direct mentions
    is_reply_to_bot = (update.message.reply_to_message and 
                       update.message.reply_to_message.from_user.id == context.bot.id)
    
    bot_username = (context.bot.username or "").lower()
    is_mentioned = (f"@{bot_username}" in message_text) or ("niyati" in message_text)
    
    if is_reply_to_bot or is_mentioned:
        return True
    
    # Cooldown checks
    if chat_id in group_reply_cooldown:
        if (now - group_reply_cooldown[chat_id]).total_seconds() < 30:
            return False
    
    # Random engagement
    return random.random() < 0.15

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Update user info
    db.update_user_info(user_id, user.first_name, user.username or "")
    
    # Check if returning user
    user_data = db.get_user(user_id)
    is_returning = user_data.get('total_messages', 0) > 0
    
    if is_returning:
        welcome_msg = f"""
<b>Yayy! {user.first_name} wapas aa gaye! 🎉</b>

Kitna miss kiya tumhe! Kaha the itne din? 🥺
Your relationship level: {user_data.get('relationship_level', 1):.1f}/10 ❤️

Chalo phir se baatein karte hain! 😊
"""
    else:
        welcome_msg = f"""
<b>नमस्ते {user.first_name}! 👋</b>

I'm <b>Niyati</b>, a 17-year-old college student from Delhi! 

मुझसे normally बात करो - I love making new friends! 😊
Sometimes I'll send you voice messages too! 🎤💕

Let's play games, share stories, and have fun together! 🎮✨
"""
    
    # Add inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("Play Game 🎮", callback_data="menu_game"),
            InlineKeyboardButton("My Stats 📊", callback_data="menu_stats")
        ],
        [
            InlineKeyboardButton("Surprise Me 🎁", callback_data="menu_surprise"),
            InlineKeyboardButton("About Me 💕", callback_data="menu_about")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_msg, 
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    logger.info(f"✅ User {user_id} ({user.first_name}) started bot - Returning: {is_returning}")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast command for owner"""
    user_id = update.effective_user.id
    
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Ye command sirf mere owner use kar sakte hain!")
        return
    
    # Refresh groups list first
    groups = db.get_all_groups()
    
    if not groups:
        await update.message.reply_text("📭 No groups found. Make sure I'm added to groups first!")
        return
    
    success_count = 0
    fail_count = 0
    failed_groups = []
    
    # Handle broadcast
    if update.message.reply_to_message:
        source_msg = update.message.reply_to_message
        await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
        
        for group_id in groups:
            try:
                if source_msg.text:
                    await context.bot.send_message(chat_id=group_id, text=source_msg.text)
                elif source_msg.photo:
                    await context.bot.send_photo(
                        chat_id=group_id,
                        photo=source_msg.photo[-1].file_id,
                        caption=source_msg.caption
                    )
                elif source_msg.video:
                    await context.bot.send_video(
                        chat_id=group_id,
                        video=source_msg.video.file_id,
                        caption=source_msg.caption
                    )
                # Add other media types...
                
                success_count += 1
                await asyncio.sleep(0.5)
                
            except Forbidden:
                fail_count += 1
                failed_groups.append(group_id)
                db.remove_group(group_id)
            except Exception as e:
                fail_count += 1
                logger.error(f"Broadcast error: {e}")
    
    else:
        text = ' '.join(context.args) if context.args else None
        
        if not text:
            await update.message.reply_text(
                "❓ Usage:\n/broadcast <message>\nOR\nReply to any message with /broadcast"
            )
            return
        
        await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
        
        for group_id in groups:
            try:
                await context.bot.send_message(chat_id=group_id, text=text)
                success_count += 1
                await asyncio.sleep(0.5)
            except Forbidden:
                fail_count += 1
                failed_groups.append(group_id)
                db.remove_group(group_id)
            except Exception as e:
                fail_count += 1
    
    # Report
    report = f"""
📊 <b>Broadcast Report</b>

✅ Success: {success_count}/{len(groups)}
❌ Failed: {fail_count}
"""
    
    if failed_groups:
        report += f"🗑️ Removed {len(failed_groups)} inactive groups"
    
    await update.message.reply_text(report, parse_mode='HTML')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Check daily bonus
    got_bonus = db.check_daily_bonus(user_id)
    
    stats_msg = f"""
📊 <b>Your Statistics</b>

👤 Name: {user_data.get('name', 'Unknown')}
❤️ Relationship: {user_data.get('relationship_level', 1):.1f}/10
🎭 Stage: {user_data.get('stage', 'initial')}
😊 Current Mood: {user_data.get('mood', 'happy')}
💰 Coins: {user_data.get('coins', 0)}
🔥 Streak: {user_data.get('streak', 0)} days
💬 Total Messages: {user_data.get('total_messages', 0)}
🎤 Voice Messages: {user_data.get('voice_messages_sent', 0)}
"""
    
    if got_bonus:
        stats_msg += f"\n🎁 Daily Bonus: +{Config.DAILY_BONUS_COINS} coins!"
    
    if user_id == Config.OWNER_USER_ID:
        global_stats = db.get_stats()
        stats_msg += f"""

<b>🌍 Global Stats (Owner Only)</b>
👥 Total Users: {global_stats['total_users']}
👥 Total Groups: {global_stats['total_groups']}
"""
    
    await update.message.reply_text(stats_msg, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    try:
        if not update.message:
            return
        
        # Track group when bot receives any message
        chat_type = update.message.chat.type
        chat_id = update.effective_chat.id
        
        # Add group to cache if it's a group/supergroup
        if chat_type in ["group", "supergroup"]:
            chat_title = update.message.chat.title or "Unknown Group"
            db.add_group(chat_id, chat_title)
            
            # Check if should reply in group
            if not should_reply_in_group(update, context):
                return
        
        # Continue with regular message handling...
        user_id = update.effective_user.id
        user_msg = update.message.text or ""
        
        # Detect mood from message
        detected_mood = mood_system.detect_mood(user_msg)
        db.update_mood(user_id, detected_mood)
        
        # Get user data
        user_data = db.get_user(user_id)
        stage = user_data.get('stage', 'initial')
        name = user_data.get('name', '')
        current_mood = user_data.get('mood', 'happy')
        
        # Show typing action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Generate response
        context_str = f"""
User: {name}
Stage: {stage}
Relationship: {user_data.get('relationship_level', 1):.1f}/10
Recent chats: {len(user_data.get('chats', []))}
"""
        
        response = await ai.generate(user_msg, context_str, current_mood)
        
        if not response:
            # Fallback response
            response = mood_system.get_mood_response(current_mood)
        
        # Decide voice or text
        should_voice = voice_engine.should_send_voice(response, stage, current_mood)
        
        if should_voice and chat_type == "private":
            # Send voice
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio = await voice_engine.text_to_speech(response, current_mood)
            
            if audio:
                await update.message.reply_voice(voice=audio, caption=f"🎤 Mood: {current_mood}")
                db.add_message(user_id, user_msg, response, is_voice=True)
            else:
                await update.message.reply_text(response)
                db.add_message(user_id, user_msg, response, is_voice=False)
        else:
            # Send text
            await asyncio.sleep(calculate_typing_delay(response))
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response, is_voice=False)
        
        # Random surprises
        if random.random() < 0.05:  # 5% chance
            surprise = random.choice([
                random.choice(COMPLIMENTS),
                random.choice(PICKUP_LINES),
                "BTW, tumhe pata hai? " + random.choice(["You're special 💕", "I think about you 🥰"])
            ])
            await asyncio.sleep(2)
            await update.message.reply_text(surprise)
            
    except Exception as e:
        logger.error(f"❌ Message handler error: {e}", exc_info=True)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "menu_game":
        await query.message.reply_text(
            "🎮 <b>Choose a game:</b>",
            reply_markup=games_system.get_game_menu(),
            parse_mode='HTML'
        )
    
    elif data == "menu_stats":
        # Show stats
        user_data = db.get_user(user_id)
        stats_text = f"""
📊 Your Stats:
❤️ Level: {user_data.get('relationship_level', 1):.1f}/10
💰 Coins: {user_data.get('coins', 0)}
🔥 Streak: {user_data.get('streak', 0)}
"""
        await query.message.reply_text(stats_text)
    
    elif data == "menu_surprise":
        surprises = [
            random.choice(COMPLIMENTS),
            random.choice(PICKUP_LINES),
            random.choice(SHAYARI),
            "Here's a secret: " + random.choice(["I dream about you 💭", "You're my favorite person 🥰"])
        ]
        await query.message.reply_text(random.choice(surprises))
    
    elif data == "menu_about":
        about_text = """
💕 <b>About Me - Niyati</b>

Age: 17 years
Location: Delhi 📍
College: 2nd year Arts student
Hobbies: Dancing, Reading, Music 🎵

I love making new friends and chatting!
Let's create beautiful memories together 🥰
"""
        await query.message.reply_text(about_text, parse_mode='HTML')
    
    elif data.startswith("game_"):
        game_id = data.replace("game_", "")
        
        if game_id == "truth_dare":
            keyboard = [
                [InlineKeyboardButton("Truth", callback_data="td_truth"),
                 InlineKeyboardButton("Dare", callback_data="td_dare")],
                [InlineKeyboardButton("Back", callback_data="menu_game")]
            ]
            await query.message.reply_text(
                "Truth or Dare? Choose wisely! 😏",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif game_id == "love_calculator":
            percentage = random.randint(60, 99)
            await query.message.reply_text(
                f"💕 Love Calculator\n\n"
                f"You + Niyati = {percentage}% ❤️\n\n"
                f"{'Perfect match! 🥰' if percentage > 85 else 'Pretty good! 😊'}"
            )
            
            # Add coins
            user_data = db.get_user(user_id)
            user_data['coins'] = user_data.get('coins', 0) + 10
            db.save_user(user_id, user_data)
    
    elif data == "td_truth":
        truth = random.choice(games_system.GAMES["truth_dare"]["truths"])
        await query.message.reply_text(f"Truth: {truth}")
    
    elif data == "td_dare":
        dare = random.choice(games_system.GAMES["truth_dare"]["dares"])
        await query.message.reply_text(f"Dare: {dare}")
    
    elif data == "close":
        await query.message.delete()

# ==================== SCHEDULED MESSAGES ====================

async def send_scheduled_messages(context: ContextTypes.DEFAULT_TYPE):
    """Send scheduled good morning/night messages"""
    hour = get_ist_time().hour
    
    # Good morning (8 AM)
    if hour == 8:
        for user_id_str in db.local_db.keys():
            try:
                user_id = int(user_id_str)
                msg = random.choice(GOOD_MORNING_MSGS)
                await context.bot.send_message(chat_id=user_id, text=msg)
            except Exception:
                pass
    
    # Good night (11 PM)
    elif hour == 23:
        for user_id_str in db.local_db.keys():
            try:
                user_id = int(user_id_str)
                msg = random.choice(GOOD_NIGHT_MSGS)
                await context.bot.send_message(chat_id=user_id, text=msg)
            except Exception:
                pass

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    stats = db.get_stats()
    return jsonify({
        "status": "running",
        "bot": "Niyati Ultimate",
        "version": "5.0",
        "features": [
            "AI Chat", "Voice Messages", "Games", "Mood System",
            "Memory", "Daily Bonus", "Broadcast", "Scheduled Messages"
        ],
        "stats": stats,
        "time": datetime.now().isoformat()
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "sleeping": is_sleeping_time(),
        "time": get_ist_time().strftime("%Y-%m-%d %H:%M:%S IST")
    })

def run_flask():
    logger.info(f"🌐 Starting Flask server on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN BOT ====================

async def main():
    """Main bot function"""
    try:
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Starting Niyati Ultimate Bot")
        logger.info("="*60)
        
        # Build application
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("broadcast", broadcast_command))
        app.add_handler(CallbackQueryHandler(callback_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_message))
        
        # Add scheduled job
        app.job_queue.run_repeating(send_scheduled_messages, interval=3600, first=10)
        
        # Start bot
        await app.initialize()
        await app.start()
        
        logger.info("✅ Bot started successfully with all features!")
        logger.info("Features: AI, Voice, Games, Moods, Memory, Broadcast, and more!")
        
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

if __name__ == "__main__":
    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        sys.exit(1)
