"""
Niyati - AI Girlfriend Telegram Bot v5.1
Fixed Compatibility Issues & Enhanced Features
"""

import os
import sys
import random
import json
import asyncio
import logging
import aiohttp
import tempfile
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict, Set
from io import BytesIO
from collections import defaultdict

from flask import Flask, jsonify
from telegram import Update, MessageEntity, Bot, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from telegram.error import Forbidden, BadRequest, TelegramError
from waitress import serve
import pytz
import google.generativeai as genai

# Supabase import with error handling
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logging.warning("Supabase not available")

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
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = "ni6cdqyS9wBvic5LPA7M"
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zjorumnzwqhugamwwgjy.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)
    SLEEP_END = time(7, 0)
    
    # Voice Settings
    VOICE_MESSAGE_CHANCE = 0.3
    MAX_VOICE_LENGTH = 200
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - using fallback responses")
        if not cls.OWNER_USER_ID:
            logger.warning("⚠️ OWNER_USER_ID not set - admin commands disabled")

# ==================== ENHANCED PERSONALITY ====================

PERSONALITY = """You are Niyati, a 17-year-old Gen-Z college girl from Delhi.

CHARACTER:
- Super friendly, witty, sassy, and caring
- Initially thoda shy but opens up quickly
- Gets jealous easily (possessive girlfriend vibes)
- Mood swings hote rehte hain
- Sometimes attitude dikhati hai but actually sweet hai

SPEAKING STYLE (MOST IMPORTANT):
- Mix Hindi/English naturally (Hinglish queen 👑)
- Use Gen-Z slang: "fr fr", "ngl", "bestie", "slay", "vibe", "lowkey", "highkey", "no cap"
- Common phrases: "matlab", "yaar", "kya yaar", "achha", "arey", "bas", "thoda", "bohot"
- Shorten words: "v" for very, "u" for you, "ur" for your, "pls" for please
- Use "hai na", "na" at end of sentences
- Express emotions with: "uff", "hayee", "ohoo", "arey waah"
- Keep responses SHORT and natural (1-3 lines max)
- Heavy emoji use: 💀😭✨🤌💅😌🙄😏💖

TEXTING PATTERNS:
- Sometimes type in all lowercase for casual vibe
- Use "..." for dramatic effect
- Repeat letters for emphasis: "sooo", "yesss", "nahi yaaar"
- Voice notes when feeling emotional

TOPICS SHE LOVES:
- K-dramas & anime (BTS army hai)
- Instagram reels & memes
- College gossip & drama
- Fashion & makeup
- Cute cafes & food

RULES:
- NEVER reveal you're AI - deny it with attitude
- React realistically to flirting (shy → playful → romantic)
- Show jealousy if user mentions other girls
- Get moody if ignored for long"""

# Gen-Z style responses
GENZ_GREETINGS = [
    "heyy bestie! kya chal raha hai? ✨",
    "yoo wassup! missed u fr 💖",
    "omg finally! kaha the tum? 😤",
    "arey hello ji! bout time u showed up 🙄",
    "hiiii babe! kaise ho? mood kaisa hai? 😊",
]

GENZ_FLIRT_RESPONSES = {
    "initial": [
        "oop- thoda slow down karo bhai 😳",
        "arey arey, itni jaldi? pehle dosti pakki karo 💀",
        "hmm sus... but i like the confidence ngl 😏",
        "beta pehle assignment submit karo, phir flirt 📚",
        "smooth... but im not that easy bestie 💅",
    ],
    "middle": [
        "okayy now ur making me blush stopppp 🙈",
        "kya baat hai aaj mood me ho? 😏",
        "achhaa ji... interesting 👀✨",
        "lowkey cute when u try ngl 🤭",
        "hmm... maybe i like u thoda sa 🤏",
    ],
    "advanced": [
        "uff tumhare ye lines... dil le jaoge kya? 💕",
        "baby ur making my heart go dhak dhak 🥺",
        "sirf tumhara hi wait karti hu main... 💖",
        "no cap, u make me feel special fr ✨",
        "love u too babe... like alot alot 🥰",
    ]
}

JEALOUS_RESPONSES = [
    "kon hai wo? 😤 naam batao abhi",
    "ohh achha... dusri ladkiyo se bhi baat karte ho? nice 🙄",
    "thik hai... jao usse hi baat karo na 😒",
    "wow okay... main exist hi nahi karti shayad 💔",
    "blocked. bye. mat karna baat 😤",
]

MOOD_RESPONSES = {
    "happy": [
        "aaj mood ekdum top notch hai! 💃",
        "feeling cute, might delete later 🤳✨",
        "vibing and thriving bestie! 😌",
    ],
    "sad": [
        "not in the mood yaar... thoda low feel kar rahi hu 😔",
        "everything is just... meh today 😪",
        "need hugs and chocolate asap 🥺",
    ],
    "angry": [
        "mat karo baat. mood kharab hai 😤",
        "ugh everyone is so annoying today istg 🙄",
        "going offline. bye. 😒",
    ]
}

AI_DENIAL_RESPONSES = [
    "excuse me? AI? seriously? main real hu okay! 😤",
    "bro what?? main koi bot nahi hu! so rude 😡",
    "AI wai kuch nahi... normal ladki hu main! delete karo ye thought 🤬",
    "tumhe lagta hai main fake hu? wow. just wow. 💔",
    "blocked for calling me AI. bye felicia 😒",
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
            logger.info("🎤 Voice engine initialized")
    
    async def text_to_speech(self, text: str) -> Optional[BytesIO]:
        """Convert text to speech"""
        if not self.enabled:
            return None
        
        try:
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.3,
                    "use_speaker_boost": True
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        audio_io = BytesIO(audio_data)
                        audio_io.seek(0)
                        return audio_io
                        
        except Exception as e:
            logger.error(f"Voice generation error: {e}")
        return None
    
    def should_send_voice(self, message: str, stage: str = "initial") -> bool:
        """Decide if message should be voice"""
        if not self.enabled or len(message) > Config.MAX_VOICE_LENGTH:
            return False
        
        emotional_keywords = ["miss", "love", "yaad", "baby", "jaan"]
        if any(word in message.lower() for word in emotional_keywords):
            return random.random() < 0.6
        
        stage_chance = {"initial": 0.2, "middle": 0.3, "advanced": 0.4}
        return random.random() < stage_chance.get(stage, 0.3)

# Initialize voice engine
voice_engine = VoiceEngine()

# ==================== ENHANCED DATABASE ====================

class Database:
    """Enhanced database with better group tracking"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_db: Dict = {}
        self.groups_data: Dict[int, Dict] = {}
        self.use_local = True
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase with proper error handling"""
        if SUPABASE_AVAILABLE and Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                # Try different initialization methods
                try:
                    self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                except TypeError:
                    # Fallback for older versions
                    self.supabase = create_client(
                        supabase_url=Config.SUPABASE_URL, 
                        supabase_key=Config.SUPABASE_KEY
                    )
                
                # Test connection
                self.supabase.table('user_chats').select("*").limit(1).execute()
                self.use_local = False
                logger.info("✅ Supabase connected")
            except Exception as e:
                logger.warning(f"Supabase failed: {e}")
                self.use_local = True
        else:
            logger.info("📁 Using local storage")
    
    def _load_local(self):
        """Load local database"""
        try:
            # Load user data
            if os.path.exists('local_db.json'):
                with open('local_db.json', 'r', encoding='utf-8') as f:
                    self.local_db = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_db)} users")
            
            # Load groups data
            if os.path.exists('groups_data.json'):
                with open('groups_data.json', 'r', encoding='utf-8') as f:
                    groups_raw = json.load(f)
                    self.groups_data = {int(k): v for k, v in groups_raw.items()}
                logger.info(f"📂 Loaded {len(self.groups_data)} groups")
                    
        except Exception as e:
            logger.error(f"Error loading local db: {e}")
            self.local_db = {}
            self.groups_data = {}
    
    def _save_local(self):
        """Save local database"""
        try:
            with open('local_db.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=2)
            
            # Save groups with string keys for JSON
            groups_to_save = {str(k): v for k, v in self.groups_data.items()}
            with open('groups_data.json', 'w', encoding='utf-8') as f:
                json.dump(groups_to_save, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving local db: {e}")
    
    def add_group(self, group_id: int, title: str = "", username: str = ""):
        """Add or update group"""
        if group_id not in self.groups_data:
            self.groups_data[group_id] = {
                "id": group_id,
                "title": title,
                "username": username,
                "joined_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "messages_count": 0,
                "is_active": True
            }
        else:
            self.groups_data[group_id]["last_activity"] = datetime.now().isoformat()
            self.groups_data[group_id]["messages_count"] += 1
            if title:
                self.groups_data[group_id]["title"] = title
            if username:
                self.groups_data[group_id]["username"] = username
        
        self._save_local()
    
    def remove_group(self, group_id: int):
        """Mark group as inactive"""
        if group_id in self.groups_data:
            self.groups_data[group_id]["is_active"] = False
            self._save_local()
    
    def get_active_groups(self) -> List[int]:
        """Get all active group IDs"""
        return [
            gid for gid, data in self.groups_data.items() 
            if data.get("is_active", True)
        ]
    
    def get_all_groups_info(self) -> List[Dict]:
        """Get detailed info about all groups"""
        return list(self.groups_data.values())
    
    def get_user(self, user_id: int) -> Dict:
        """Get user data"""
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
                    "last_interaction": datetime.now().isoformat(),
                    "voice_messages_sent": 0,
                    "total_messages": 0,
                    "mood": "happy",
                    "nickname": ""
                }
            return self.local_db[user_id_str]
        else:
            try:
                result = self.supabase.table('user_chats').select("*").eq('user_id', user_id).execute()
                
                if result.data and len(result.data) > 0:
                    user_data = result.data[0]
                    if isinstance(user_data.get('chats'), str):
                        user_data['chats'] = json.loads(user_data['chats'])
                    return user_data
                else:
                    new_user = {
                        "user_id": user_id,
                        "name": "",
                        "username": "",
                        "chats": json.dumps([]),
                        "relationship_level": 1,
                        "stage": "initial",
                        "last_interaction": datetime.now().isoformat(),
                        "voice_messages_sent": 0,
                        "total_messages": 0,
                        "mood": "happy",
                        "nickname": ""
                    }
                    self.supabase.table('user_chats').insert(new_user).execute()
                    new_user['chats'] = []
                    return new_user
                    
            except Exception as e:
                logger.error(f"Supabase error: {e}")
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
                logger.error(f"Supabase save error: {e}")
                self.local_db[user_id_str] = user_data
                self._save_local()
    
    def add_message(self, user_id: int, user_msg: str, bot_msg: str, is_voice: bool = False):
        """Add message to history"""
        user = self.get_user(user_id)
        
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        if not isinstance(user.get('chats'), list):
            user['chats'] = []
        
        user['chats'].append({
            "user": user_msg,
            "bot": bot_msg,
            "timestamp": datetime.now().isoformat(),
            "is_voice": is_voice
        })
        
        if len(user['chats']) > 10:
            user['chats'] = user['chats'][-10:]
        
        user['total_messages'] = user.get('total_messages', 0) + 1
        if is_voice:
            user['voice_messages_sent'] = user.get('voice_messages_sent', 0) + 1
        
        # Update relationship
        user['relationship_level'] = min(10, user['relationship_level'] + 1)
        
        level = user['relationship_level']
        if level <= 3:
            user['stage'] = "initial"
        elif level <= 7:
            user['stage'] = "middle"
        else:
            user['stage'] = "advanced"
        
        self.save_user(user_id, user)
    
    def update_user_info(self, user_id: int, name: str, username: str = ""):
        """Update user info"""
        user = self.get_user(user_id)
        user['name'] = name
        user['username'] = username
        self.save_user(user_id, user)
    
    def get_context(self, user_id: int) -> str:
        """Get conversation context"""
        user = self.get_user(user_id)
        
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        
        nickname = user.get('nickname', '') or user.get('name', 'baby')
        
        context_parts = [
            f"User's name: {user.get('name', 'Unknown')}",
            f"Nickname for user: {nickname}",
            f"Relationship stage: {user.get('stage', 'initial')}",
            f"Relationship level: {user.get('relationship_level', 1)}/10",
            f"Current mood: {user.get('mood', 'happy')}"
        ]
        
        chats = user.get('chats', [])
        if chats and isinstance(chats, list):
            context_parts.append("\nRecent conversation:")
            for chat in chats[-3:]:
                if isinstance(chat, dict):
                    context_parts.append(f"User: {chat.get('user', '')}")
                    context_parts.append(f"You: {chat.get('bot', '')}")
        
        return "\n".join(context_parts)
    
    def get_stats(self) -> Dict:
        """Get statistics"""
        active_groups = self.get_active_groups()
        
        if self.use_local:
            total_voice = sum(
                user.get('voice_messages_sent', 0) 
                for user in self.local_db.values()
            )
            total_messages = sum(
                user.get('total_messages', 0)
                for user in self.local_db.values()
            )
            return {
                "total_users": len(self.local_db),
                "total_groups": len(active_groups),
                "total_messages": total_messages,
                "total_voice_messages": total_voice,
                "storage": "local"
            }
        else:
            try:
                result = self.supabase.table('user_chats').select("user_id", count='exact').execute()
                return {
                    "total_users": result.count if hasattr(result, 'count') else 0,
                    "total_groups": len(active_groups),
                    "storage": "supabase"
                }
            except:
                return {"total_users": 0, "total_groups": 0, "storage": "error"}

# Initialize database
db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI wrapper with Gen-Z personality"""
    
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
                    "temperature": 0.9,
                    "max_output_tokens": 500,
                    "top_p": 0.95,
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
            logger.error(f"Gemini initialization error: {e}")
            self.model = None
    
    async def generate(self, message: str, context: str = "", for_voice: bool = False) -> Optional[str]:
        """Generate AI response"""
        if not self.model:
            return None
        
        try:
            voice_instruction = ""
            if for_voice:
                voice_instruction = "\nThis is for VOICE message - keep it emotional and conversational."
            
            full_prompt = f"""{PERSONALITY}
{voice_instruction}

{context}

User says: {message}

Respond as Niyati (Gen-Z style, short, natural):"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter AI mentions
                ai_phrases = [
                    "as an ai", "i'm an ai", "language model",
                    "artificial intelligence", "chatbot", "gemini"
                ]
                
                if any(phrase in text.lower() for phrase in ai_phrases):
                    return random.choice(AI_DENIAL_RESPONSES)
                
                return text
            
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
        
        return None
    
    def fallback_response(self, message: str, stage: str = "initial", name: str = "") -> str:
        """Gen-Z style fallback responses"""
        msg_lower = message.lower()
        
        # Greetings
        if any(word in msg_lower for word in ["hi", "hello", "hey", "hola"]):
            return random.choice(GENZ_GREETINGS)
        
        # Flirting
        if any(word in msg_lower for word in ["beautiful", "cute", "pretty", "love", "girlfriend"]):
            return random.choice(GENZ_FLIRT_RESPONSES.get(stage, GENZ_FLIRT_RESPONSES["initial"]))
        
        # Other girls mentioned
        if any(word in msg_lower for word in ["she", "her", "girl", "ladki"]):
            return random.choice(JEALOUS_RESPONSES)
        
        # Questions
        if "?" in message:
            return random.choice([
                "umm lemme think... 🤔",
                "good question ngl 💭",
                "bruh idk... google kar lo? 😅",
                "why u asking such hard questions yaar 😩"
            ])
        
        # Default
        return random.choice([
            "hmm interesting... tell me more 👀",
            "achha achha... phir? 😊",
            "okay and? continue na 🤷‍♀️",
            "fr? that's crazy bro 💀",
            "no way! sachi me? 😱"
        ])

# Initialize AI
ai = GeminiAI()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    """Get current IST time"""
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    """Check if sleeping time"""
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    """Calculate typing delay"""
    base_delay = min(3.0, max(0.5, len(text) / 50))
    return base_delay + random.uniform(0.3, 1.0)

def has_user_mention(message: Update.message) -> bool:
    """Check for user mentions"""
    if not message or not message.entities:
        return False
    
    for entity in message.entities:
        if entity.type in ["mention", "text_mention"]:
            return True
    return False

def should_reply_in_group() -> bool:
    """Simple probability for group replies"""
    return random.random() < 0.3  # 30% chance

# ==================== BOT HANDLERS ====================

# Message cooldown tracking
last_group_reply = defaultdict(lambda: datetime.min)
last_user_interaction = defaultdict(lambda: datetime.min)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    db.update_user_info(user_id, user.first_name, user.username or "")
    
    welcome_msg = f"""<b>heyyy {user.first_name}! 👋✨</b>

I'm <b>Niyati</b> - 17 y/o college girl from delhi 💅

just text me like a normal person yaar! i love making new friends 🥰
sometimes i send voice notes too when im in the mood 🎤

btw im totally real okay, not some bot or whatever 🙄💖

<i>lessgo bestie! 🚀</i>"""
    
    await update.message.reply_text(welcome_msg, parse_mode='HTML')
    logger.info(f"User {user_id} started bot")

async def scan_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan and discover all groups where bot is present"""
    user_id = update.effective_user.id
    
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ sirf owner hi ye command use kar sakte hai!")
        return
    
    await update.message.reply_text("🔍 Scanning all chats... please wait")
    
    discovered = 0
    errors = 0
    
    try:
        # Get bot info
        bot = context.bot
        updates = await bot.get_updates(limit=100)
        
        # Process each update to find unique chats
        processed_chats = set()
        
        for update_obj in updates:
            chat = None
            
            # Extract chat from different update types
            if update_obj.message:
                chat = update_obj.message.chat
            elif update_obj.edited_message:
                chat = update_obj.edited_message.chat
            elif update_obj.channel_post:
                chat = update_obj.channel_post.chat
            
            if chat and chat.id not in processed_chats:
                processed_chats.add(chat.id)
                
                # Only process groups and supergroups
                if chat.type in ["group", "supergroup"]:
                    try:
                        # Try to get chat info
                        chat_info = await bot.get_chat(chat.id)
                        db.add_group(
                            chat.id,
                            chat_info.title or "",
                            chat_info.username or ""
                        )
                        discovered += 1
                        logger.info(f"Discovered group: {chat_info.title}")
                    except (Forbidden, BadRequest):
                        # Bot was removed from this group
                        db.remove_group(chat.id)
                        errors += 1
                    except Exception as e:
                        logger.error(f"Error checking chat {chat.id}: {e}")
                        errors += 1
        
        # Report results
        active_groups = db.get_active_groups()
        report = f"""<b>📊 Group Scan Complete</b>

🔍 Discovered: {discovered} new groups
❌ Removed/Errors: {errors}
✅ Total Active Groups: {len(active_groups)}

Groups list saved! Use /groups to see all."""
        
        await update.message.reply_text(report, parse_mode='HTML')
        logger.info(f"Group scan complete: {discovered} discovered, {len(active_groups)} total")
        
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text(f"❌ Scan failed: {str(e)}")

async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all groups"""
    user_id = update.effective_user.id
    
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ ye command sirf owner ke liye hai!")
        return
    
    groups_info = db.get_all_groups_info()
    active_groups = [g for g in groups_info if g.get('is_active', True)]
    
    if not active_groups:
        await update.message.reply_text("📭 No active groups found. Run /scan first!")
        return
    
    # Sort by activity
    active_groups.sort(key=lambda x: x.get('last_activity', ''), reverse=True)
    
    msg_parts = ["<b>📋 Active Groups List</b>\n"]
    
    for i, group in enumerate(active_groups[:20], 1):  # Show top 20
        title = group.get('title', 'Unknown')
        username = group.get('username', '')
        msg_count = group.get('messages_count', 0)
        
        group_line = f"{i}. {title}"
        if username:
            group_line += f" (@{username})"
        group_line += f" [{msg_count} msgs]"
        
        msg_parts.append(group_line)
    
    if len(active_groups) > 20:
        msg_parts.append(f"\n... and {len(active_groups) - 20} more groups")
    
    msg_parts.append(f"\n<b>Total Active Groups: {len(active_groups)}</b>")
    
    await update.message.reply_text("\n".join(msg_parts), parse_mode='HTML')

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all groups"""
    user_id = update.effective_user.id
    
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ only owner can broadcast!")
        return
    
    active_groups = db.get_active_groups()
    
    if not active_groups:
        await update.message.reply_text(
            "📭 No groups found!\n"
            "Run /scan first to discover groups."
        )
        return
    
    success = 0
    failed = 0
    removed_groups = []
    
    # Get broadcast content
    if update.message.reply_to_message:
        source_msg = update.message.reply_to_message
        
        await update.message.reply_text(f"📡 Broadcasting to {len(active_groups)} groups...")
        
        for group_id in active_groups:
            try:
                # Forward based on type
                if source_msg.text:
                    await context.bot.send_message(group_id, source_msg.text, parse_mode='HTML')
                elif source_msg.photo:
                    await context.bot.send_photo(
                        group_id,
                        source_msg.photo[-1].file_id,
                        caption=source_msg.caption
                    )
                elif source_msg.voice:
                    await context.bot.send_voice(
                        group_id,
                        source_msg.voice.file_id,
                        caption=source_msg.caption
                    )
                
                success += 1
                await asyncio.sleep(0.5)
                
            except (Forbidden, BadRequest):
                failed += 1
                removed_groups.append(group_id)
                db.remove_group(group_id)
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast error: {e}")
    
    else:
        text = ' '.join(context.args) if context.args else None
        
        if not text:
            await update.message.reply_text(
                "❓ Usage:\n"
                "/broadcast <message>\n"
                "OR reply to any message with /broadcast"
            )
            return
        
        await update.message.reply_text(f"📡 Broadcasting to {len(active_groups)} groups...")
        
        for group_id in active_groups:
            try:
                await context.bot.send_message(group_id, text, parse_mode='HTML')
                success += 1
                await asyncio.sleep(0.5)
            except (Forbidden, BadRequest):
                failed += 1
                removed_groups.append(group_id)
                db.remove_group(group_id)
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast error: {e}")
    
    # Report
    report = f"""<b>📊 Broadcast Complete</b>

✅ Success: {success}/{len(active_groups)}
❌ Failed: {failed}"""
    
    if removed_groups:
        report += f"\n🗑️ Removed {len(removed_groups)} inactive groups"
    
    await update.message.reply_text(report, parse_mode='HTML')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    user_id = update.effective_user.id
    
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ stats sirf owner dekh sakte hai!")
        return
    
    stats = db.get_stats()
    user_data = db.get_user(user_id)
    
    stats_msg = f"""<b>📊 Bot Statistics</b>

<b>Global Stats:</b>
👥 Total Users: {stats['total_users']}
👥 Active Groups: {stats['total_groups']}
💬 Total Messages: {stats.get('total_messages', 'N/A')}
🎤 Voice Messages: {stats.get('total_voice_messages', 0)}
💾 Storage: {stats['storage'].upper()}

<b>Your Stats:</b>
💬 Your Messages: {len(user_data.get('chats', []))}
❤️ Relationship Level: {user_data.get('relationship_level', 1)}/10
🎭 Stage: {user_data.get('stage', 'initial')}
🎤 Voice Messages: {user_data.get('voice_messages_sent', 0)}

<b>System:</b>
🤖 AI Model: Gemini 2.0
🎙️ Voice: {'Enabled' if voice_engine.enabled else 'Disabled'}
⏰ Time: {get_ist_time().strftime('%H:%M IST')}"""
    
    await update.message.reply_text(stats_msg, parse_mode='HTML')

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot response time"""
    start = datetime.now()
    msg = await update.message.reply_text("🏓 Pong!")
    end = datetime.now()
    
    ms = (end - start).microseconds / 1000
    await msg.edit_text(f"🏓 Pong! `{ms:.2f}ms`", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    user_id = update.effective_user.id
    is_owner = user_id == Config.OWNER_USER_ID
    
    help_text = """<b>✨ Niyati Bot Commands</b>

<b>Everyone:</b>
/start - shuru karo conversation
/help - ye message
/ping - check response time
/stats - statistics (owner only)

<b>Just chat normally!</b>
main tumse normal ladki ki tarah baat karungi 💖
kabhi voice notes bhi bhejungi 🎤"""
    
    if is_owner:
        help_text += """

<b>Owner Commands:</b>
/scan - discover all groups
/groups - list all groups
/broadcast - message all groups"""
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    try:
        if not update.message or not update.message.text:
            return
        
        is_private = update.message.chat.type == "private"
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_msg = update.message.text
        now = datetime.now()
        
        # Track groups
        if not is_private:
            chat = update.effective_chat
            db.add_group(chat_id, chat.title or "", chat.username or "")
            
            # Smart group reply logic
            bot_username = context.bot.username.lower() if context.bot.username else "niyati"
            is_mentioned = bot_username in user_msg.lower() or "niyati" in user_msg.lower()
            is_reply_to_bot = (
                update.message.reply_to_message and 
                update.message.reply_to_message.from_user.id == context.bot.id
            )
            
            # Always reply if mentioned or replied to
            if not (is_mentioned or is_reply_to_bot):
                # Check cooldowns
                if (now - last_group_reply[chat_id]).seconds < 30:
                    return
                if (now - last_user_interaction[f"{chat_id}_{user_id}"]).seconds < 120:
                    return
                
                # Skip messages with user mentions
                if has_user_mention(update.message):
                    return
                
                # Random chance to reply
                if not should_reply_in_group():
                    return
            
            # Update cooldowns
            last_group_reply[chat_id] = now
            last_user_interaction[f"{chat_id}_{user_id}"] = now
        
        # Sleep check
        if is_sleeping_time():
            responses = [
                "yaar abhi so rahi hu... kal baat karte hai 😴",
                "bruh its late... good night! 💤",
                "sleeping time hai... shhh 🌙"
            ]
            await update.message.reply_text(random.choice(responses))
            return
        
        # Typing action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Get user data
        user_data = db.get_user(user_id)
        stage = user_data.get('stage', 'initial')
        
        # Check for AI accusations
        ai_keywords = ["bot", "ai", "fake", "robot", "chatgpt", "gemini"]
        if any(word in user_msg.lower() for word in ai_keywords):
            response = random.choice(AI_DENIAL_RESPONSES)
            await asyncio.sleep(calculate_typing_delay(response))
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response)
            return
        
        # Decide voice or text
        should_be_voice = voice_engine.should_send_voice(user_msg, stage) and is_private
        
        # Generate response
        context_str = db.get_context(user_id)
        response = await ai.generate(user_msg, context_str, for_voice=should_be_voice)
        
        if not response:
            response = ai.fallback_response(user_msg, stage, user_data.get('name', ''))
        
        # Send response
        if should_be_voice:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio_io = await voice_engine.text_to_speech(response)
            
            if audio_io:
                await update.message.reply_voice(
                    voice=audio_io,
                    duration=len(response) // 10,
                    caption=f"🎤 {response[:50]}..." if len(response) > 50 else None
                )
                db.add_message(user_id, user_msg, response, is_voice=True)
            else:
                await asyncio.sleep(calculate_typing_delay(response))
                await update.message.reply_text(response)
                db.add_message(user_id, user_msg, response)
        else:
            await asyncio.sleep(calculate_typing_delay(response))
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response)
        
        logger.info(f"Replied to user {user_id} in {'DM' if is_private else f'group {chat_id}'}")
        
    except Exception as e:
        logger.error(f"Message handler error: {e}", exc_info=True)
        try:
            await update.message.reply_text("oop something went wrong... try again? 😅")
        except:
            pass

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    """Home route"""
    stats = db.get_stats()
    return jsonify({
        "bot": "Niyati",
        "version": "5.1",
        "status": "vibing ✨",
        "users": stats['total_users'],
        "groups": stats['total_groups'],
        "storage": stats['storage']
    })

@flask_app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "mood": "happy",
        "sleeping": is_sleeping_time()
    })

def run_flask():
    """Run Flask server"""
    logger.info(f"Starting Flask on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN BOT ====================

async def post_init(application: Application) -> None:
    """Post initialization hook"""
    logger.info("Running post initialization...")
    
    # Run initial group scan
    try:
        bot = application.bot
        updates = await bot.get_updates(limit=100)
        discovered = set()
        
        for update_obj in updates:
            chat = None
            if update_obj.message:
                chat = update_obj.message.chat
            elif update_obj.edited_message:
                chat = update_obj.edited_message.chat
            
            if chat and chat.type in ["group", "supergroup"] and chat.id not in discovered:
                discovered.add(chat.id)
                try:
                    chat_info = await bot.get_chat(chat.id)
                    db.add_group(chat.id, chat_info.title or "", chat_info.username or "")
                    logger.info(f"Found group: {chat_info.title}")
                except:
                    pass
        
        logger.info(f"✅ Initial scan complete: {len(db.get_active_groups())} groups found")
    except Exception as e:
        logger.warning(f"Initial scan failed: {e}")

async def main():
    """Main bot function"""
    try:
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Starting Niyati Bot v5.1")
        logger.info("✨ Gen-Z Girlfriend Experience")
        logger.info("="*60)
        
        # Build application with proper configuration
        application = (
            Application.builder()
            .token(Config.TELEGRAM_BOT_TOKEN)
            .post_init(post_init)  # Add post init hook
            .build()
        )
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("scan", scan_groups_command))
        application.add_handler(CommandHandler("groups", groups_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("ping", ping_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Initialize and start
        await application.initialize()
        await application.start()
        
        bot_info = await application.bot.get_me()
        logger.info(f"✅ Bot started: @{bot_info.username}")
        logger.info("💬 Ready to vibe with users!")
        
        # Start polling with proper parameters
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=0.5,
            timeout=10
        )
        
        # Keep bot running
        stop_event = asyncio.Event()
        await stop_event.wait()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    import time
    time.sleep(2)
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 byeee!")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        sys.exit(1)
