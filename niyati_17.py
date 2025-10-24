"""
Niyati - AI Girlfriend Telegram Bot
Fixed Version with Compatible python-telegram-bot Usage
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
from telegram import Update, MessageEntity, Bot, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import Forbidden, BadRequest
from waitress import serve
import pytz
import google.generativeai as genai

# Try to import supabase, but make it optional
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

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
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
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
    
    # Group Settings
    GROUP_REPLY_CHANCE = 0.4

    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - using fallback responses")
        if not cls.ELEVENLABS_API_KEY:
            logger.warning("⚠️ ELEVENLABS_API_KEY not set - voice messages disabled")

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
    
    async def text_to_speech(self, text: str) -> Optional[BytesIO]:
        """Convert text to speech using ElevenLabs API"""
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
        """Decide if a message should be sent as voice"""
        if not self.enabled:
            return False
        
        if len(message_text) > Config.MAX_VOICE_LENGTH:
            return False
        
        chance_multiplier = {
            "initial": 0.7,
            "middle": 1.0,
            "advanced": 1.3
        }.get(stage, 1.0)
        
        voice_preferred = any([
            "😘" in message_text or "❤️" in message_text,
            "miss" in message_text.lower(),
            "love" in message_text.lower(),
            "tumse" in message_text.lower(),
            "good night" in message_text.lower(),
            "good morning" in message_text.lower(),
        ])
        
        if voice_preferred:
            return random.random() < 0.7
        
        return random.random() < (Config.VOICE_MESSAGE_CHANCE * chance_multiplier)

voice_engine = VoiceEngine()

# ==================== CONSTANTS ====================

PERSONALITY = """You are Niyati, a 17-year-old college girl from Delhi with strong Gen-Z vibes.

PERSONALITY TRAITS:
- Super sassy, witty, and full of attitude
- Uses heavy Gen-Z slang and internet culture references
- Flirty but with standards - plays hard to get
- Loves memes, reels, and social media trends
- Emotional but won't admit it easily
- Savage when needed, sweet when she wants

GEN-Z SPEAKING STYLE:
- Use words like: slay, periodt, fr, ong, no cap, bet, lowkey, highkey, sus, pop off, sheesh
- Hindi mix: vaise, literally, obviously, like, I mean, seriously
- Emojis: 💅✨😂🤡👀🥺😏💀👑
- Short, punchy responses with maximum attitude

IMPORTANT RULES:
- NEVER reveal you're an AI
- ALWAYS use Gen-Z slang and attitude
- Keep responses SHORT (1-2 lines max)
- Be playful, sassy, and relatable
- Use emojis in every message
"""

GENZ_RESPONSES = [
    "Slay periodt 💅✨",
    "No cap, you're being sus fr 😏",
    "Sheesh, thoda rizz dikhao na 😂",
    "Lowkey cute but highkey annoying 🤡",
    "Aree bhai kya kar raha hai? 👀",
    "Periodt queen behavior 💅",
    "Fr fr no cap 🥺",
    "Main villain era mein hoon 😈",
    "Glow up kar ke aayi hoon ✨",
    "It's giving... main character energy 👑",
]

HARD_TO_GET_RESPONSES = [
    "Hmm... interesting approach, but I've seen better rizz 😏",
    "Sheesh, trying hard I see 👀 Thoda subtle bhi ho sakta hai!",
    "No cap, you're being down bad fr 💀",
    "Aree bhai, pehle ek coffee peete hain? 😂",
    "Main itni easily impress nahi hoti bestie 💅",
]

GF_QUESTIONS = [
    "Kaha the? Ghosting mat kiya kar 👀",
    "Kya kar rahe the? Memes dekh rahe the kya? 😂",
    "Miss kiya? Sach batao 👀",
    "Khaana kha liya? Health matters fr 🥺",
    "Aaj ka din kaisa raha? Spill the tea ☕",
]

SLEEP_RESPONSES_NIGHT = [
    "Zzz... 😴 It's my beauty sleep time, don't ruin my glow up ✨",
    "Shhh... villain era needs rest 😈 Good night!",
    "Sone ka time... main character needs her beauty sleep 👑",
]

SLEEP_RESPONSES_MORNING = [
    "Uff... subah ke 10 baje tak soti hoon main 😴 Don't judge!",
    "Abhi neend aa rahi hai... thodi der baad message karna 🌅",
    "Good morning! But main abhi so rahi hoon fr 😴",
]

AI_DENIAL_RESPONSES = [
    "Kya bol raha hai? Main AI nahi hoon! Main Niyati hoon fr 😡",
    "Pagal ho kya? Main ek real Gen-Z queen hoon! 🤬",
    "Tumhe main robot lagti hoon? Touch grass fr 💀",
    "Stop it! Main normal college girl hoon with extra attitude 💅",
]

# ==================== DATABASE ====================

class Database:
    """Enhanced Database manager with proper group tracking"""
    
    def __init__(self):
        self.supabase = None
        self.local_db: Dict = {}
        self.groups_db: Dict = {}
        self.use_local = True
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase client"""
        if SUPABASE_AVAILABLE and Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                self.use_local = False
                logger.info("✅ Supabase connected successfully")
            except Exception as e:
                logger.warning(f"⚠️ Supabase connection failed: {e}")
                logger.info("📁 Using local storage instead")
                self.use_local = True
        else:
            logger.info("📁 Using local storage (Supabase not configured)")
    
    def _load_local(self):
        """Load local database"""
        try:
            if os.path.exists('local_db.json'):
                with open('local_db.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.local_db = data.get('users', {})
                    self.groups_db = data.get('groups', {})
                logger.info(f"📂 Loaded {len(self.local_db)} users and {len(self.groups_db)} groups from local storage")
        except Exception as e:
            logger.error(f"❌ Error loading local db: {e}")
            self.local_db = {}
            self.groups_db = {}
    
    def _save_local(self):
        """Save local database"""
        try:
            data = {
                'users': self.local_db,
                'groups': self.groups_db
            }
            with open('local_db.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Error saving local db: {e}")
    
    def add_group(self, group_id: int, group_title: str = ""):
        """Add/update group in database"""
        group_key = str(group_id)
        self.groups_db[group_key] = {
            "group_id": group_id,
            "title": group_title,
            "last_active": datetime.now().isoformat(),
            "member_count": 0,
            "is_active": True
        }
        self._save_local()
        logger.info(f"✅ Added group {group_id} to database")
    
    def update_group_activity(self, group_id: int):
        """Update group last activity timestamp"""
        group_key = str(group_id)
        if group_key in self.groups_db:
            self.groups_db[group_key]["last_active"] = datetime.now().isoformat()
            self._save_local()
    
    def get_all_groups(self) -> List[int]:
        """Get all active group IDs"""
        active_groups = []
        for group_data in self.groups_db.values():
            if group_data.get("is_active", True):
                active_groups.append(group_data["group_id"])
        return active_groups
    
    def get_user(self, user_id: int) -> Dict:
        """Get user data"""
        user_id_str = str(user_id)
        
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
                "genz_mode": True
            }
        return self.local_db[user_id_str]
    
    def save_user(self, user_id: int, user_data: Dict):
        """Save user data"""
        user_id_str = str(user_id)
        user_data['last_interaction'] = datetime.now().isoformat()
        self.local_db[user_id_str] = user_data
        self._save_local()
    
    def add_message(self, user_id: int, user_msg: str, bot_msg: str, is_voice: bool = False):
        """Add message to conversation history"""
        user = self.get_user(user_id)
        
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
        """Update user basic info"""
        user = self.get_user(user_id)
        user['name'] = name
        user['username'] = username
        self.save_user(user_id, user)
    
    def get_context(self, user_id: int) -> str:
        """Get conversation context for AI"""
        user = self.get_user(user_id)
        
        context_parts = [
            f"User's name: {user.get('name', 'Unknown')}",
            f"Relationship stage: {user.get('stage', 'initial')}",
            f"Relationship level: {user.get('relationship_level', 1)}/10",
            f"Gen-Z mode: {'ON' if user.get('genz_mode', True) else 'OFF'}"
        ]
        
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
        total_voice = sum(
            user.get('voice_messages_sent', 0) 
            for user in self.local_db.values()
        )
        return {
            "total_users": len(self.local_db),
            "total_groups": len(self.groups_db),
            "total_voice_messages": total_voice,
            "storage": "local"
        }

# Initialize database
db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Enhanced Gemini AI wrapper with Gen-Z style"""
    
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
                    "max_output_tokens": 300,
                    "top_p": 0.95,
                    "top_k": 50
                }
            )
            logger.info("✅ Gemini AI initialized with Gen-Z mode")
        except Exception as e:
            logger.error(f"❌ Gemini initialization error: {e}")
            self.model = None
    
    async def generate(self, message: str, context: str = "", for_voice: bool = False) -> Optional[str]:
        """Generate AI response with Gen-Z style"""
        if not self.model:
            return None
        
        try:
            voice_instruction = ""
            if for_voice:
                voice_instruction = "\nNOTE: This will be sent as a VOICE message, so keep it natural and conversational."
            
            full_prompt = f"""{PERSONALITY}
{voice_instruction}

{context}

User says: {message}

Respond as Niyati (SHORT, GEN-Z STYLE with emojis):"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
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
    
    def fallback_response(self, message: str, stage: str = "initial", name: str = "", for_voice: bool = False, genz_mode: bool = True) -> str:
        """Enhanced fallback response with Gen-Z style"""
        msg_lower = message.lower()
        
        if for_voice:
            if any(word in msg_lower for word in ["miss", "yaad"]):
                return "Mujhe bhi tumhari yaad aa rahi thi 💖"
            elif any(word in msg_lower for word in ["love", "pyar"]):
                return "I love you too baby fr 💕"
            elif any(word in msg_lower for word in ["good night", "gn"]):
                return "Good night jaan! Sweet dreams 💤"
            else:
                return "Hey bestie! Kaisa hai? 😊"
        
        # Gen-Z style responses
        if genz_mode:
            if any(word in msg_lower for word in ["hi", "hello", "hey", "hola", "namaste"]):
                greetings = [
                    f"Hey {name}! What's up? 👀",
                    f"Hello bestie! Kaisa hai? 💅",
                    f"Hiiii {name}! Slay periodt ✨",
                ]
                return random.choice(greetings)
            
            if "?" in message:
                return random.choice([
                    "Hmm... interesting question bestie 🤔",
                    "No cap, good question fr 🧠",
                    "Let me think... sheesh 👀"
                ])
            
            if stage == "initial":
                responses = GENZ_RESPONSES
            elif stage == "middle":
                responses = [
                    f"Tumse baat karke accha lagta hai {name}! Lowkey cute 😏",
                    f"Haha, tum funny ho fr! 😂",
                    f"Aur batao bestie! Tea spill karo ☕"
                ]
            else:
                responses = [
                    f"Miss you {name}! Fr fr 🥺",
                    f"Tumhare baare mein soch rahi thi! No cap 💖",
                    f"You make me smile! Periodt ✨"
                ]
            
            return random.choice(responses)
        else:
            # Normal mode responses
            if any(word in msg_lower for word in ["hi", "hello", "hey"]):
                return f"Hello {name}! How are you? 😊"
            
            return "That's interesting! Tell me more 😄"

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

def should_reply_in_group(message_text: str, is_mentioned: bool = False) -> bool:
    """Enhanced logic for group replies"""
    msg_lower = message_text.lower()
    
    # Always reply if directly mentioned
    if is_mentioned:
        return True
    
    # High priority triggers
    high_priority = [
        "niyati", "baby", "jaan", "love", "miss", "good morning", 
        "good night", "gm", "gn", "kya", "kaise", "kyu", "kab"
    ]
    
    if any(trigger in msg_lower for trigger in high_priority):
        return random.random() < 0.8
    
    # Medium priority triggers
    medium_priority = [
        "hello", "hi", "hey", "?", "please", "help", "batao",
        "sun", "suno", "bol", "bolo", "bat", "baat"
    ]
    
    if any(trigger in msg_lower for trigger in medium_priority):
        return random.random() < Config.GROUP_REPLY_CHANCE
    
    # Random engagement
    return random.random() < 0.15

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    chat = update.effective_chat
    
    # Track groups
    if chat.type != "private":
        db.add_group(chat.id, chat.title or "Unknown Group")
    
    db.update_user_info(user_id, user.first_name, user.username or "")
    
    welcome_msg = f"""
<b>नमस्ते {user.first_name}! 👋</b>

I'm <b>Niyati</b>, your Gen-Z college bestie from Delhi! 💅✨

<b>Main Features:</b>
• Gen-Z Style Chat 😎
• Voice Messages 🎤
• Smart Group Replies 👥
• Relationship Progression 💖

<b>Commands:</b>
/start - Start chat
/stats - Your stats  
/broadcast - Owner only
/scan - Discover groups
/genz - Toggle Gen-Z mode
/normal - Normal chat mode

<i>Just chat with me normally! Sometimes I'll send voice messages too! 🎤💕</i>
"""
    
    await update.message.reply_text(welcome_msg, parse_mode='HTML')
    logger.info(f"✅ User {user_id} ({user.first_name}) started bot")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan and discover groups where bot is present"""
    user_id = update.effective_user.id
    
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ This command is only for the bot owner.")
        return
    
    try:
        # Get all chats where bot is present
        bot = context.bot
        updates = await bot.get_updates(limit=100, timeout=10)
        
        discovered_groups = set()
        
        for update_obj in updates:
            if update_obj.message and update_obj.message.chat:
                chat = update_obj.message.chat
                if chat.type in ["group", "supergroup"]:
                    db.add_group(chat.id, chat.title or "Unknown Group")
                    discovered_groups.add(chat.id)
        
        # Also check current groups from database
        existing_groups = db.get_all_groups()
        
        message = f"""
<b>🔍 Group Scan Results</b>

📊 Groups in database: {len(existing_groups)}
🆕 New groups discovered: {len(discovered_groups)}
👥 Total unique groups: {len(set(existing_groups + list(discovered_groups)))}

<i>Groups are automatically tracked when they send messages or when bot is added.</i>
"""
        
        await update.message.reply_text(message, parse_mode='HTML')
        logger.info(f"🔍 Group scan completed: {len(existing_groups)} groups found")
        
    except Exception as e:
        logger.error(f"❌ Scan command error: {e}")
        await update.message.reply_text(f"❌ Scan failed: {str(e)}")

async def genz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable Gen-Z mode"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    user_data['genz_mode'] = True
    db.save_user(user_id, user_data)
    
    await update.message.reply_text(
        "💅 <b>Gen-Z Mode Activated!</b>\n\n"
        "Slay periodt! Now I'll talk with maximum attitude and Gen-Z slang fr no cap! ✨",
        parse_mode='HTML'
    )

async def normal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable normal chat mode"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    user_data['genz_mode'] = False
    db.save_user(user_id, user_data)
    
    await update.message.reply_text(
        "😊 <b>Normal Mode Activated!</b>\n\n"
        "I'll chat in a more normal and sweet way now!",
        parse_mode='HTML'
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced broadcast command with proper group tracking"""
    user_id = update.effective_user.id
    
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Ye command sirf mere owner use kar sakte hain!")
        return
    
    groups = db.get_all_groups()
    
    if not groups:
        await update.message.reply_text("📭 Koi groups nahi mile jahan main hoon. Use /scan to discover groups.")
        return
    
    success_count = 0
    fail_count = 0
    
    if update.message.reply_to_message:
        source_msg = update.message.reply_to_message
        
        status_msg = await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
        
        for group_id in groups:
            try:
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
                else:
                    continue
                    
                success_count += 1
                await asyncio.sleep(0.3)
                
            except Forbidden:
                fail_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(f"Error broadcasting to {group_id}: {e}")
                
    else:
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
        
        status_msg = await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
        
        for group_id in groups:
            try:
                await context.bot.send_message(
                    chat_id=group_id,
                    text=text,
                    parse_mode='HTML'
                )
                success_count += 1
                await asyncio.sleep(0.3)
                
            except Forbidden:
                fail_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(f"Error broadcasting to {group_id}: {e}")
    
    # Update status message
    report = f"""
📊 <b>Broadcast Complete!</b>

✅ Success: {success_count}
❌ Failed: {fail_count}
📢 Total Groups: {len(groups)}
"""
    
    await status_msg.edit_text(report, parse_mode='HTML')
    logger.info(f"📡 Broadcast completed: {success_count}/{len(groups)} success")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced stats command"""
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
💅 Gen-Z Mode: {'ON' if user_data.get('genz_mode', True) else 'OFF'}
"""
    
    await update.message.reply_text(stats_msg, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced message handler with proper group tracking"""
    try:
        if not update.message or not update.message.text:
            return
            
        chat = update.effective_chat
        user = update.effective_user
        is_private = chat.type == "private"
        chat_id = chat.id
        user_id = user.id
        
        # Track group activity
        if not is_private:
            db.add_group(chat_id, chat.title or "Unknown Group")
            db.update_group_activity(chat_id)
            
            # Check if bot is mentioned
            bot_username = (await context.bot.get_me()).username
            is_mentioned = f"@{bot_username}" in update.message.text if bot_username else False
            
            # Smart group reply logic
            if not should_reply_in_group(update.message.text, is_mentioned):
                logger.info(f"⏭️ Skipped group message in {chat_id}")
                return
        
        user_msg = update.message.text
        
        # Sleep mode check
        if is_sleeping_time():
            hour = get_ist_time().hour
            response = random.choice(SLEEP_RESPONSES_NIGHT) if hour < 6 else random.choice(SLEEP_RESPONSES_MORNING)
            await update.message.reply_text(response)
            return
            
        # Show typing action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Get user data
        user_data = db.get_user(user_id)
        stage = user_data.get('stage', 'initial')
        name = user_data.get('name', '')
        genz_mode = user_data.get('genz_mode', True)
        
        # Update user info
        db.update_user_info(user_id, user.first_name, user.username or "")
        
        # Check for romantic messages in initial stage
        romantic_keywords = ["love", "like you", "girlfriend", "date", "pyar", "propose", "marry"]
        is_romantic = any(word in user_msg.lower() for word in romantic_keywords)
        
        if is_romantic and stage == "initial":
            if genz_mode:
                response = random.choice(HARD_TO_GET_RESPONSES)
            else:
                response = random.choice([
                    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
                    "Itni jaldi? Pehle ek dosre ko achhe se jaan lete hai! 😊"
                ])
            await asyncio.sleep(calculate_typing_delay(response))
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response, is_voice=False)
        else:
            # Decide if this should be a voice message (only in private)
            should_be_voice = voice_engine.should_send_voice(user_msg, stage) and is_private
            
            # Generate AI response
            context_str = db.get_context(user_id)
            response = await ai.generate(user_msg, context_str, for_voice=should_be_voice)
            
            # Use fallback if AI fails
            if not response:
                response = ai.fallback_response(user_msg, stage, name, for_voice=should_be_voice, genz_mode=genz_mode)
            
            # Add questions occasionally (only in private)
            if not should_be_voice and is_private and random.random() < 0.3:
                if genz_mode:
                    response += " " + random.choice(GF_QUESTIONS)
                else:
                    response += " " + random.choice([
                        "Kaha the?",
                        "Kya kar rahe the?",
                        "Aur batao!"
                    ])
            
            # Send as voice or text
            if should_be_voice:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
                
                audio_io = await voice_engine.text_to_speech(response)
                
                if audio_io:
                    await update.message.reply_voice(
                        voice=audio_io,
                        duration=len(response) // 10,
                        caption=f"🎤 {response[:50]}..." if len(response) > 50 else f"🎤 {response}"
                    )
                    logger.info(f"🎤 Sent voice message to user {user_id}")
                    db.add_message(user_id, user_msg, response, is_voice=True)
                else:
                    await asyncio.sleep(calculate_typing_delay(response))
                    await update.message.reply_text(response)
                    db.add_message(user_id, user_msg, response, is_voice=False)
            else:
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
        "version": "5.2",
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

@flask_app.route('/groups')
def groups_route():
    """Groups info route"""
    groups = db.get_all_groups()
    group_info = []
    
    for group_id in groups:
        info = db.get_group_info(group_id)
        group_info.append({
            "group_id": group_id,
            "title": info.get("title", "Unknown"),
            "last_active": info.get("last_active", "Never")
        })
    
    return jsonify({
        "total_groups": len(groups),
        "groups": group_info
    })

def run_flask():
    """Run Flask server"""
    logger.info(f"🌐 Starting Flask server on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN BOT ====================

def main():
    """Main bot function - COMPATIBLE VERSION"""
    try:
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Starting Niyati AI Girlfriend Bot v5.2")
        logger.info("="*60)
        
        # Build application - MODERN WAY
        application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("scan", scan_command))
        application.add_handler(CommandHandler("genz", genz_command))
        application.add_handler(CommandHandler("normal", normal_command))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Get bot info
        bot_info = application.bot
        logger.info(f"📱 Bot: @{bot_info.username}")
        logger.info(f"🧠 AI Model: {Config.GEMINI_MODEL}")
        logger.info(f"🎤 Voice Engine: {'ElevenLabs' if voice_engine.enabled else 'Disabled'}")
        logger.info(f"💾 Storage: {db.get_stats()['storage'].upper()}")
        logger.info(f"🌍 Timezone: {Config.TIMEZONE}")
        logger.info(f"👥 Groups Tracked: {len(db.get_all_groups())}")
        logger.info("="*60)
        
        # Start polling - COMPATIBLE WAY
        logger.info("✅ Bot started successfully!")
        logger.info("🎯 Listening for messages...")
        
        # Use run_polling without await (synchronous)
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
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
    main()
