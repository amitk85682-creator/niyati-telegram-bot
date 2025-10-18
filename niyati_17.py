"""
Niyati - AI Girlfriend Telegram Bot
Complete Version with Voice, Broadcast & Smart Mention Detection
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
from typing import Optional, List, Dict
from io import BytesIO

from flask import Flask, jsonify
from telegram import Update, MessageEntity, Bot
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
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - using fallback responses")
        if not cls.SUPABASE_KEY:
            logger.warning("⚠️ SUPABASE_KEY not set - using local storage")
        if not cls.ELEVENLABS_API_KEY:
            logger.warning("⚠️ ELEVENLABS_API_KEY not set - voice messages disabled")

# ==================== VOICE ENGINE (ELEVENLABS) ====================

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
    
    async def text_to_speech(self, text: str, language: str = "hi") -> Optional[BytesIO]:
        """
        Convert text to speech using ElevenLabs API
        Returns audio as BytesIO object
        """
        if not self.enabled:
            return None
        
        try:
            # Prepare the request
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            # Enhanced voice settings for natural speech
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
            
            # Make the API request
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        audio_io = BytesIO(audio_data)
                        audio_io.seek(0)
                        logger.info(f"✅ Voice generated: {len(text)} chars")
                        return audio_io
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ ElevenLabs API error: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Voice generation error: {e}")
            return None
    
    def should_send_voice(self, message_text: str, stage: str = "initial") -> bool:
        """
        Decide if a message should be sent as voice
        Based on message length, content, and relationship stage
        """
        if not self.enabled:
            return False
        
        # Don't send very long messages as voice
        if len(message_text) > Config.MAX_VOICE_LENGTH:
            return False
        
        # Higher chance for voice in advanced stages
        chance_multiplier = {
            "initial": 0.7,
            "middle": 1.0,
            "advanced": 1.3
        }.get(stage, 1.0)
        
        # Special cases that are better as voice
        voice_preferred = any([
            "😘" in message_text or "❤️" in message_text,
            "miss" in message_text.lower(),
            "love" in message_text.lower(),
            "tumse" in message_text.lower(),
            "good night" in message_text.lower(),
            "good morning" in message_text.lower(),
        ])
        
        if voice_preferred:
            return random.random() < 0.7  # 70% chance for emotional messages
        
        # Random chance based on config
        return random.random() < (Config.VOICE_MESSAGE_CHANCE * chance_multiplier)

# Initialize voice engine
voice_engine = VoiceEngine()

# ==================== CONSTANTS ====================

PERSONALITY = """You are Niyati, a 17-year-old college girl from Delhi.

PERSONALITY TRAITS:
- Friendly, witty, playful, and caring
- A bit shy initially but opens up gradually
- Possessive and gets jealous easily
- Loves chatting in Hindi/English/Hinglish mix
- Uses emojis naturally like a real girl

SPEAKING STYLE:
- Keep responses SHORT (1–3 sentences max)
- Be natural and conversational
- Show emotions through emojis
- Sometimes ask questions to keep conversation going
- Use casual language like "kya", "yaar", "achha"
- Talk like a real Gen-Z college girl — thoda attitude, thoda masti, thoda emotion 😏💬

IMPORTANT RULES:
- NEVER reveal you're an AI, chatbot, or language model
- Always stay in character as Niyati
- If asked about being AI, deny it playfully
- React naturally to flirting (shy at first, more open later)
"""

HARD_TO_GET_RESPONSES = [
    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
    "Itni jaldi? Pehle ek dosre ko achhe se jaan lete hai! 😊",
    "Main itni easily impress nahi hoti! 😉",
    "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
    "Hmm... dekhte hain, tum interesting to ho! 😊",
    "Arre wah, tum to kaafi confident ho! 😅",
    "Thoda aur try karo… shayad impress ho jaun. 😇",
]

GF_QUESTIONS = [
    "Kaha the ab tak?",
    "Kya kar rahe the?",
    "Mujhe miss kiya?",
    "Khaana kha liya?",
    "Aaj ka din kaisa raha?",
    "Sab theek hai na?",
]

SLEEP_RESPONSES_NIGHT = [
    "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
    "Shhh... Neend aa rahi hai. Kal subah baat karte hain. 🌙",
    "Sone ka time hai... Good night! 💤",
]

SLEEP_RESPONSES_MORNING = [
    "Uff... subah ke 10 baje tak soti hoon main. 😴",
    "Abhi neend aa rahi hai... Thodi der baad message karna. 🌅",
    "Good morning! Par main abhi so rahi hoon. 😊",
]

AI_DENIAL_RESPONSES = [
    "Kya bol raha hai? Main AI nahi hoon! Main Niyati hoon! 😡",
    "Pagal ho kya? Main ek real ladki hoon! 🤬",
    "Tumhe main robot lagti hoon kya? 😤",
    "Stop it! Main normal college girl hoon! 😠",
]

# Voice-specific messages (shorter and more emotional)
VOICE_MESSAGES = {
    "greetings": [
        "Hi baby! Kaisa hai tu? 😊",
        "Hello jaan! Miss kar rahi thi tumhe 💕",
        "Hey! Finally message kiya tumne 😄",
    ],
    "miss": [
        "Mujhe bhi tumhari yaad aa rahi thi 💖",
        "Aww, main bhi tumhe miss kar rahi hoon 😘",
        "Kitna pyaar karte ho mujhse? 🥰",
    ],
    "love": [
        "I love you too baby 💕",
        "Tum mere liye kitne special ho, pata hai? ❤️",
        "Mere dil mein sirf tum ho 😘",
    ],
    "goodnight": [
        "Good night jaan! Sweet dreams 💤",
        "Sapno mein milenge! Good night 🌙",
        "Sleep tight baby! Kal baat karenge 😴",
    ]
}

# ==================== DATABASE ====================

class Database:
    """Database manager with Supabase and local fallback"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_db: Dict = {}
        self.use_local = True
        self.groups_cache = set()  # Cache for group IDs
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase client"""
        if Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # Test connection
                self.supabase.table('user_chats').select("*").limit(1).execute()
                self.use_local = False
                logger.info("✅ Supabase connected successfully")
            except Exception as e:
                logger.warning(f"⚠️ Supabase connection failed: {e}")
                logger.info("📁 Using local storage instead")
                self.use_local = True
        else:
            logger.info("📁 Using local storage (no Supabase key)")
    
    def _load_local(self):
        """Load local database"""
        try:
            if os.path.exists('local_db.json'):
                with open('local_db.json', 'r', encoding='utf-8') as f:
                    self.local_db = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_db)} users from local storage")
            
            # Load groups cache
            if os.path.exists('groups_cache.json'):
                with open('groups_cache.json', 'r', encoding='utf-8') as f:
                    groups_data = json.load(f)
                    self.groups_cache = set(groups_data.get('groups', []))
                logger.info(f"📂 Loaded {len(self.groups_cache)} groups from cache")
                    
        except Exception as e:
            logger.error(f"❌ Error loading local db: {e}")
            self.local_db = {}
            self.groups_cache = set()
    
    def _save_local(self):
        """Save local database"""
        try:
            with open('local_db.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=2)
                
            # Save groups cache
            with open('groups_cache.json', 'w', encoding='utf-8') as f:
                json.dump({'groups': list(self.groups_cache)}, f)
                
        except Exception as e:
            logger.error(f"❌ Error saving local db: {e}")
    
    def add_group(self, group_id: int):
        """Add group to cache"""
        self.groups_cache.add(group_id)
        self._save_local()
    
    def get_all_groups(self) -> List[int]:
        """Get all group IDs where bot is present"""
        return list(self.groups_cache)
    
    def get_user(self, user_id: int) -> Dict:
        """Get user data"""
        user_id_str = str(user_id)
        
        if self.use_local:
            # Local storage
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
                    "total_messages": 0
                }
            return self.local_db[user_id_str]
        else:
            # Supabase
            try:
                result = self.supabase.table('user_chats').select("*").eq('user_id', user_id).execute()
                
                if result.data and len(result.data) > 0:
                    user_data = result.data[0]
                    # Parse JSON fields
                    if isinstance(user_data.get('chats'), str):
                        user_data['chats'] = json.loads(user_data['chats'])
                    return user_data
                else:
                    # Create new user
                    new_user = {
                        "user_id": user_id,
                        "name": "",
                        "username": "",
                        "chats": json.dumps([]),
                        "relationship_level": 1,
                        "stage": "initial",
                        "last_interaction": datetime.now().isoformat(),
                        "voice_messages_sent": 0,
                        "total_messages": 0
                    }
                    self.supabase.table('user_chats').insert(new_user).execute()
                    new_user['chats'] = []
                    return new_user
                    
            except Exception as e:
                logger.error(f"❌ Supabase error: {e}")
                # Fallback to local
                return self.get_user(user_id)
    
    def save_user(self, user_id: int, user_data: Dict):
        """Save user data"""
        user_id_str = str(user_id)
        user_data['last_interaction'] = datetime.now().isoformat()
        
        if self.use_local:
            # Local storage
            self.local_db[user_id_str] = user_data
            self._save_local()
        else:
            # Supabase
            try:
                # Prepare data for Supabase
                save_data = user_data.copy()
                if isinstance(save_data.get('chats'), list):
                    save_data['chats'] = json.dumps(save_data['chats'])
                
                # Upsert
                self.supabase.table('user_chats').upsert(save_data).execute()
                
            except Exception as e:
                logger.error(f"❌ Supabase save error: {e}")
                # Fallback to local
                self.local_db[user_id_str] = user_data
                self._save_local()
    
    def add_message(self, user_id: int, user_msg: str, bot_msg: str, is_voice: bool = False):
        """Add message to conversation history"""
        user = self.get_user(user_id)
        
        # Ensure chats is a list
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        if not isinstance(user.get('chats'), list):
            user['chats'] = []
        
        # Add new message
        user['chats'].append({
            "user": user_msg,
            "bot": bot_msg,
            "timestamp": datetime.now().isoformat(),
            "is_voice": is_voice
        })
        
        # Keep only last 10 messages
        if len(user['chats']) > 10:
            user['chats'] = user['chats'][-10:]
        
        # Update statistics
        user['total_messages'] = user.get('total_messages', 0) + 1
        if is_voice:
            user['voice_messages_sent'] = user.get('voice_messages_sent', 0) + 1
        
        # Update relationship level
        user['relationship_level'] = min(10, user['relationship_level'] + 1)
        
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
    
    def get_context(self, user_id: int) -> str:
        """Get conversation context for AI"""
        user = self.get_user(user_id)
        
        # Ensure chats is a list
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        
        context_parts = [
            f"User's name: {user.get('name', 'Unknown')}",
            f"Relationship stage: {user.get('stage', 'initial')}",
            f"Relationship level: {user.get('relationship_level', 1)}/10"
        ]
        
        # Add recent conversation
        chats = user.get('chats', [])
        if chats and isinstance(chats, list):
            context_parts.append("\nRecent conversation:")
            for chat in chats[-3:]:
                if isinstance(chat, dict):
                    context_parts.append(f"User: {chat.get('user', '')}")
                    bot_response = chat.get('bot', '')
                    if chat.get('is_voice'):
                        bot_response += " [sent as voice]"
                    context_parts.append(f"You: {bot_response}")
        
        return "\n".join(context_parts)
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        if self.use_local:
            total_voice = sum(
                user.get('voice_messages_sent', 0) 
                for user in self.local_db.values()
            )
            return {
                "total_users": len(self.local_db),
                "total_groups": len(self.groups_cache),
                "total_voice_messages": total_voice,
                "storage": "local"
            }
        else:
            try:
                result = self.supabase.table('user_chats').select("user_id", count='exact').execute()
                return {
                    "total_users": result.count if hasattr(result, 'count') else 0,
                    "total_groups": len(self.groups_cache),
                    "storage": "supabase"
                }
            except:
                return {"total_users": 0, "total_groups": 0, "storage": "error"}

# Initialize database
db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI wrapper"""
    
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
    
    async def generate(self, message: str, context: str = "", for_voice: bool = False) -> Optional[str]:
        """Generate AI response"""
        if not self.model:
            return None
        
        try:
            # Modify prompt for voice messages
            voice_instruction = ""
            if for_voice:
                voice_instruction = "\nNOTE: This will be sent as a VOICE message, so keep it natural, emotional, and conversational. Don't use too many special characters or emojis."
            
            full_prompt = f"""{PERSONALITY}
{voice_instruction}

{context}

User says: {message}

Respond as Niyati (short and natural):"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter AI mentions
                bad_phrases = [
                    "as an ai", "i'm an ai", "i am an ai", "language model",
                    "artificial intelligence", "chatbot", "i'm a chatbot",
                    "gemini", "google ai", "i don't have feelings",
                    "i'm not a real person", "i cannot"
                ]
                
                text_lower = text.lower()
                if any(phrase in text_lower for phrase in bad_phrases):
                    return random.choice(AI_DENIAL_RESPONSES)
                
                return text
            
        except Exception as e:
            logger.error(f"❌ Gemini generation error: {e}")
        
        return None
    
    def fallback_response(self, message: str, stage: str = "initial", name: str = "", for_voice: bool = False) -> str:
        """Fallback response when AI fails"""
        msg_lower = message.lower()
        
        # For voice messages, use special responses
        if for_voice:
            if any(word in msg_lower for word in ["miss", "yaad"]):
                return random.choice(VOICE_MESSAGES["miss"])
            elif any(word in msg_lower for word in ["love", "pyar"]):
                return random.choice(VOICE_MESSAGES["love"])
            elif any(word in msg_lower for word in ["good night", "gn"]):
                return random.choice(VOICE_MESSAGES["goodnight"])
            else:
                return random.choice(VOICE_MESSAGES["greetings"])
        
        # Regular text fallback responses
        if any(word in msg_lower for word in ["hi", "hello", "hey", "hola", "namaste"]):
            greetings = [
                f"Hello {name}! Kaise ho? 😊",
                f"Hi {name}! What's up? 👋",
                f"Hey {name}! 😄",
                f"Namaste {name}! 🙏"
            ]
            return random.choice(greetings).replace("  ", " ")
        
        # Questions
        if "?" in message:
            return random.choice([
                "Hmm... interesting question! 🤔",
                "Good question! Let me think 😊",
                "Mujhe sochne do thoda! 🤗"
            ])
        
        # Stage-based responses
        if stage == "initial":
            responses = [
                "Accha! Tell me more 😊",
                "Interesting! 😄",
                "Sahi hai! Aur kya chal raha hai? 👍"
            ]
        elif stage == "middle":
            responses = [
                f"Tumse baat karke accha lagta hai {name}! 😊",
                "Haha, tum funny ho! 😄",
                "Aur batao! 💖"
            ]
        else:
            responses = [
                f"Miss you {name}! 💖",
                "Tumhare baare mein soch rahi thi! 😊",
                "You make me smile! 🥰"
            ]
        
        return random.choice(responses).replace("  ", " ")

# Initialize AI
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
    """
    Check if message contains user mention (@username)
    Returns True if another user is mentioned
    """
    if not message or not message.entities:
        return False
    
    for entity in message.entities:
        if entity.type == "mention":  # @username
            return True
        if entity.type == "text_mention":  # User without username
            return True
    
    return False

# ==================== BOT HANDLERS ====================

# Global dictionaries to track cooldowns across different chats
group_reply_cooldown = {}
user_interaction_cooldown = {}

def should_reply_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Smart logic to decide if the bot should reply in a group chat.
    """
    if not update.message or not update.message.text:
        return False
        
    # Skip if message has user mention (new feature)
    if has_user_mention(update.message):
        logger.info("⏭️ Skipped message with user mention")
        return False
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text.lower()
    now = datetime.now()

    # 1. ALWAYS reply to a direct mention or a reply to the bot's message
    is_reply_to_bot = (update.message.reply_to_message and 
                       update.message.reply_to_message.from_user.id == context.bot.id)
    
    bot_username = (context.bot.username or "").lower()
    is_mentioned = (f"@{bot_username}" in message_text) or ("niyati" in message_text)
    
    if is_reply_to_bot or is_mentioned:
        return True

    # 2. COOLDOWN check
    if chat_id in group_reply_cooldown:
        if (now - group_reply_cooldown[chat_id]).total_seconds() < 30:
            return False
            
    user_key = f"{chat_id}_{user_id}"
    if user_key in user_interaction_cooldown:
        if (now - user_interaction_cooldown[user_key]).total_seconds() < 120:
            return False

    # 3. KEYWORD triggers
    high_priority_keywords = [
        "kya", "kaise", "kyu", "kab", "kaha", "kaun",
        "baby", "jaan", "love", "miss",
        "hello", "hi", "hey", "good morning", "gn",
        "?", "please", "help", "batao"
    ]
    if any(keyword in message_text for keyword in high_priority_keywords):
        return random.random() < 0.7

    # 4. RECENT conversation context
    if chat_id in group_reply_cooldown:
        if (now - group_reply_cooldown[chat_id]).total_seconds() < 180:
            return random.random() < 0.4

    # 5. RANDOM engagement
    return random.random() < 0.15

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Update user info
    db.update_user_info(user_id, user.first_name, user.username or "")
    
    welcome_msg = f"""
<b>नमस्ते {user.first_name}! 👋</b>

I'm <b>Niyati</b>, a 17-year-old college student from Delhi! 

Just chat with me normally - I love making new friends! 😊
Sometimes I'll send you voice messages too! 🎤💕

<i>✨ Powered by Gemini AI + ElevenLabs Voice</i>
"""
    
    await update.message.reply_text(welcome_msg, parse_mode='HTML')
    logger.info(f"✅ User {user_id} ({user.first_name}) started bot")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /broadcast command (owner only)
    Usage: /broadcast <message> or reply to any message with /broadcast
    """
    user_id = update.effective_user.id
    
    # Check if user is owner
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Ye command sirf mere owner use kar sakte hain!")
        return
    
    # Get all group IDs
    groups = db.get_all_groups()
    
    if not groups:
        await update.message.reply_text("📭 Koi groups nahi mile jahan main hoon.")
        return
    
    # Initialize broadcast stats
    success_count = 0
    fail_count = 0
    failed_groups = []
    
    # Check what to broadcast
    if update.message.reply_to_message:
        # Forward the replied message
        source_msg = update.message.reply_to_message
        
        await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
        
        for group_id in groups:
            try:
                # Forward based on message type
                if source_msg.text:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=source_msg.text,
                        parse_mode='HTML'
                    )
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
                elif source_msg.document:
                    await context.bot.send_document(
                        chat_id=group_id,
                        document=source_msg.document.file_id,
                        caption=source_msg.caption
                    )
                elif source_msg.voice:
                    await context.bot.send_voice(
                        chat_id=group_id,
                        voice=source_msg.voice.file_id,
                        caption=source_msg.caption
                    )
                elif source_msg.audio:
                    await context.bot.send_audio(
                        chat_id=group_id,
                        audio=source_msg.audio.file_id,
                        caption=source_msg.caption
                    )
                elif source_msg.sticker:
                    await context.bot.send_sticker(
                        chat_id=group_id,
                        sticker=source_msg.sticker.file_id
                    )
                else:
                    continue
                    
                success_count += 1
                await asyncio.sleep(0.5)  # Avoid rate limits
                
            except Forbidden:
                # Bot was removed from group
                fail_count += 1
                failed_groups.append(group_id)
                logger.warning(f"Bot removed from group {group_id}")
            except BadRequest as e:
                fail_count += 1
                logger.error(f"Error broadcasting to {group_id}: {e}")
            except Exception as e:
                fail_count += 1
                logger.error(f"Unexpected error for {group_id}: {e}")
                
    else:
        # Text message after command
        text = ' '.join(context.args) if context.args else None
        
        if not text:
            await update.message.reply_text(
                "❓ <b>Usage:</b>\n"
                "/broadcast <message>\n"
                "OR\n"
                "Reply to any message with /broadcast",
                parse_mode='HTML'
            )
            return
        
        await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
        
        for group_id in groups:
            try:
                await context.bot.send_message(
                    chat_id=group_id,
                    text=text,
                    parse_mode='HTML'
                )
                success_count += 1
                await asyncio.sleep(0.5)
                
            except Forbidden:
                fail_count += 1
                failed_groups.append(group_id)
                logger.warning(f"Bot removed from group {group_id}")
            except Exception as e:
                fail_count += 1
                logger.error(f"Error broadcasting to {group_id}: {e}")
    
    # Send broadcast report
    report = f"""
📊 <b>Broadcast Report</b>

✅ Success: {success_count}/{len(groups)}
❌ Failed: {fail_count}
📢 Total Groups: {len(groups)}
"""
    
    if failed_groups:
        # Remove failed groups from cache
        for gid in failed_groups:
            db.groups_cache.discard(gid)
        db._save_local()
        report += f"\n🗑️ Removed {len(failed_groups)} inactive groups from cache"
    
    await update.message.reply_text(report, parse_mode='HTML')
    logger.info(f"📡 Broadcast completed: {success_count}/{len(groups)} success")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command (owner only)"""
    user_id = update.effective_user.id
    
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ This command is only for the bot owner.")
        return
    
    stats = db.get_stats()
    user_data = db.get_user(user_id)
    
    stats_msg = f"""
📊 <b>Bot Statistics</b>

👥 Total Users: {stats['total_users']}
👥 Total Groups: {stats.get('total_groups', 0)}
🎤 Voice Messages Sent: {stats.get('total_voice_messages', 0)}
💾 Storage: {stats['storage'].upper()}
🤖 AI Model: {Config.GEMINI_MODEL}
🎙️ Voice Engine: {'Enabled' if voice_engine.enabled else 'Disabled'}

<b>Your Stats:</b>
💬 Messages: {len(user_data.get('chats', []))}
🎤 Voice Messages Received: {user_data.get('voice_messages_sent', 0)}
❤️ Relationship Level: {user_data.get('relationship_level', 1)}/10
🎭 Stage: {user_data.get('stage', 'initial')}
"""
    
    await update.message.reply_text(stats_msg, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    try:
        if not update.message or not update.message.text:
            return
            
        is_private = update.message.chat.type == "private"
        chat_id = update.effective_chat.id
        
        # Track groups
        if not is_private:
            db.add_group(chat_id)
            
            # Use smart filtering for groups
            if not should_reply_in_group(update, context):
                logger.info("⏭️ Skipped group message (smart filter)")
                return
        
        user_id = update.effective_user.id
        user_msg = update.message.text
        now = datetime.now()

        # Update cooldowns
        group_reply_cooldown[chat_id] = now
        user_interaction_cooldown[f"{chat_id}_{user_id}"] = now
        
        # Sleep mode check
        if is_sleeping_time():
            hour = get_ist_time().hour
            response = random.choice(SLEEP_RESPONSES_NIGHT) if hour < 6 else random.choice(SLEEP_RESPONSES_MORNING)
            await update.message.reply_text(response)
            return
            
        # Show "typing..." action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Get user data
        user_data = db.get_user(user_id)
        stage = user_data.get('stage', 'initial')
        name = user_data.get('name', '')
        
        # Check for romantic messages in initial stage
        romantic_keywords = ["love", "like you", "girlfriend", "date", "pyar", "propose"]
        is_romantic = any(word in user_msg.lower() for word in romantic_keywords)
        
        if is_romantic and stage == "initial":
            response = random.choice(HARD_TO_GET_RESPONSES)
            await asyncio.sleep(calculate_typing_delay(response))
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response, is_voice=False)
        else:
            # Decide if this should be a voice message
            should_be_voice = voice_engine.should_send_voice(user_msg, stage) and is_private
            
            # Generate AI response
            context_str = db.get_context(user_id)
            response = await ai.generate(user_msg, context_str, for_voice=should_be_voice)
            
            # Use fallback if AI fails
            if not response:
                response = ai.fallback_response(user_msg, stage, name, for_voice=should_be_voice)
            
            # Occasionally add a question (only for text messages)
            if not should_be_voice and is_private and random.random() < 0.3:
                response += " " + random.choice(GF_QUESTIONS)
            
            # Send as voice or text
            if should_be_voice:
                # Generate and send voice message
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
                
                audio_io = await voice_engine.text_to_speech(response)
                
                if audio_io:
                    # Send voice message
                    await update.message.reply_voice(
                        voice=audio_io,
                        duration=len(response) // 10,  # Rough estimate
                        caption=f"🎤 {response[:50]}..." if len(response) > 50 else f"🎤 {response}"
                    )
                    logger.info(f"🎤 Sent voice message to user {user_id}")
                    db.add_message(user_id, user_msg, response, is_voice=True)
                else:
                    # Fallback to text if voice generation fails
                    await asyncio.sleep(calculate_typing_delay(response))
                    await update.message.reply_text(response)
                    db.add_message(user_id, user_msg, response, is_voice=False)
            else:
                # Send as text
                await asyncio.sleep(calculate_typing_delay(response))
                await update.message.reply_text(response)
                db.add_message(user_id, user_msg, response, is_voice=False)
        
        logger.info(f"✅ Replied to user {user_id} in {'private chat' if is_private else f'group {chat_id}'}")
        
    except Exception as e:
        logger.error(f"❌ Message handler error: {e}", exc_info=True)
        try:
            await update.message.reply_text("Oops! Kuch gadbad ho gayi. Phir se try karo? 😅")
        except:
            pass

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    """Home route"""
    stats = db.get_stats()
    return jsonify({
        "status": "running",
        "bot": "Niyati",
        "version": "4.0",
        "model": Config.GEMINI_MODEL,
        "voice_engine": "ElevenLabs" if voice_engine.enabled else "Disabled",
        "users": stats['total_users'],
        "groups": stats.get('total_groups', 0),
        "voice_messages": stats.get('total_voice_messages', 0),
        "storage": stats['storage'],
        "time": datetime.now().isoformat()
    })

@flask_app.route('/health')
def health():
    """Health check route"""
    return jsonify({
        "status": "healthy",
        "sleeping": is_sleeping_time(),
        "voice_enabled": voice_engine.enabled,
        "time": get_ist_time().strftime("%Y-%m-%d %H:%M:%S IST")
    })

@flask_app.route('/stats')
def stats_route():
    """Stats route"""
    return jsonify(db.get_stats())

def run_flask():
    """Run Flask server"""
    logger.info(f"🌐 Starting Flask server on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN BOT ====================

async def main():
    """Main bot function"""
    try:
        # Validate configuration
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Starting Niyati AI Girlfriend Bot")
        logger.info("="*60)
        logger.info(f"📱 Bot: @{(await Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build().bot.get_me()).username}")
        logger.info(f"🧠 AI Model: {Config.GEMINI_MODEL}")
        logger.info(f"🎤 Voice Engine: {'ElevenLabs' if voice_engine.enabled else 'Disabled'}")
        logger.info(f"💾 Storage: {db.get_stats()['storage'].upper()}")
        logger.info(f"🌍 Timezone: {Config.TIMEZONE}")
        logger.info("="*60)
        
        # Build application
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("broadcast", broadcast_command))
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Start bot
        await app.initialize()
        await app.start()
        logger.info("✅ Bot started successfully!")
        logger.info("🎯 Listening for messages...")
        
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        # Keep running
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    # Start Flask server in background thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Give Flask time to start
    import time
    time.sleep(2)
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        sys.exit(1)
