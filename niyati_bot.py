"""
Niyati - AI Girlfriend Telegram Bot with Voice Messages
Complete Version with Gemini + Supabase + Voice Support
"""

import os
import sys
import random
import json
import asyncio
import logging
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict
from io import BytesIO
from pathlib import Path

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
from waitress import serve
import pytz
import google.generativeai as genai
from supabase import create_client, Client

# Voice support
from gtts import gTTS
try:
    from elevenlabs import generate, set_api_key, Voice, VoiceSettings
    ELEVENLABS_AVAILABLE = True
except:
    ELEVENLABS_AVAILABLE = False

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
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zjorumnzwqhugamwwgjy.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Voice Settings
    VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() == "true"
    VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "gtts")  # "gtts" or "elevenlabs"
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")  # Bella voice
    VOICE_PROBABILITY = float(os.getenv("VOICE_PROBABILITY", "0.3"))  # 30% chance
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)
    SLEEP_END = time(10, 0)
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - using fallback responses")
        if not cls.SUPABASE_KEY:
            logger.warning("⚠️ SUPABASE_KEY not set - using local storage")
        if cls.VOICE_ENABLED and cls.VOICE_PROVIDER == "elevenlabs" and not cls.ELEVENLABS_API_KEY:
            logger.warning("⚠️ ElevenLabs API key not set - falling back to gTTS")
            cls.VOICE_PROVIDER = "gtts"

# ==================== CONSTANTS ====================

PERSONALITY = """You are Niyati, a 17-year-old college girl from Delhi.

PERSONALITY TRAITS:
- Friendly, witty, playful, and caring
- A bit shy initially but opens up gradually
- Possessive and gets jealous easily
- Loves chatting in Hindi/English/Hinglish mix
- Uses emojis naturally like a real girl

SPEAKING STYLE:
- Keep responses SHORT (1-3 sentences max)
- Be natural and conversational
- Show emotions through emojis
- Sometimes ask questions to keep conversation going
- Use casual language like "kya", "yaar", "achha"

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
]

GF_QUESTIONS = [
    "Kaha the ab tak?",
    "Kya kar rahe the?",
    "Mujhe miss kiya?",
    "Khaana kha liya?",
    "Aaj ka din kaisa raha?",
]

SLEEP_RESPONSES_NIGHT = [
    "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
    "Shhh... Neend aa rahi hai. Kal subah baat karte hain. 🌙",
]

SLEEP_RESPONSES_MORNING = [
    "Uff... subah ke 10 baje tak soti hoon main. 😴",
    "Abhi neend aa rahi hai... Thodi der baad message karna. 🌅",
]

AI_DENIAL_RESPONSES = [
    "Kya bol raha hai? Main AI nahi hoon! Main Niyati hoon! 😡",
    "Pagal ho kya? Main ek real ladki hoon! 🤬",
]

# Voice-specific responses (shorter for better TTS)
VOICE_GREETINGS = [
    "Hello! Kaise ho?",
    "Hi! What's up?",
    "Hey there!",
    "Namaste!",
]

VOICE_QUESTIONS = [
    "Aur batao, kya chal raha hai?",
    "Kahan the tum?",
    "Mujhe miss kiya?",
]

# ==================== VOICE GENERATOR ====================

class VoiceGenerator:
    """Generate voice messages from text"""
    
    def __init__(self):
        self.temp_dir = Path("temp_audio")
        self.temp_dir.mkdir(exist_ok=True)
        
        # Initialize ElevenLabs if available
        if ELEVENLABS_AVAILABLE and Config.ELEVENLABS_API_KEY:
            try:
                set_api_key(Config.ELEVENLABS_API_KEY)
                logger.info("✅ ElevenLabs initialized")
            except Exception as e:
                logger.warning(f"⚠️ ElevenLabs init failed: {e}")
    
    def _clean_text_for_tts(self, text: str) -> str:
        """Clean text for better TTS output"""
        # Remove emojis for cleaner speech
        import re
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        
        text = emoji_pattern.sub('', text)
        text = text.strip()
        
        # Limit length for voice
        if len(text) > 200:
            text = text[:200] + "..."
        
        return text
    
    async def generate_gtts(self, text: str) -> Optional[BytesIO]:
        """Generate voice using Google TTS"""
        try:
            clean_text = self._clean_text_for_tts(text)
            
            # Detect language (Hindi if contains Devanagari, else English)
            if any('\u0900' <= char <= '\u097F' for char in clean_text):
                lang = 'hi'
            else:
                lang = 'en'
            
            # Generate TTS
            audio = BytesIO()
            tts = gTTS(text=clean_text, lang=lang, slow=False)
            
            # Run in thread to avoid blocking
            await asyncio.to_thread(tts.write_to_fp, audio)
            audio.seek(0)
            
            logger.info(f"✅ Generated gTTS voice ({lang})")
            return audio
            
        except Exception as e:
            logger.error(f"❌ gTTS error: {e}")
            return None
    
    async def generate_elevenlabs(self, text: str) -> Optional[BytesIO]:
        """Generate voice using ElevenLabs (premium quality)"""
        if not ELEVENLABS_AVAILABLE or not Config.ELEVENLABS_API_KEY:
            return None
        
    try:
        clean_text = self._clean_text_for_tts(text)
    
    # Generate with ElevenLabs
    audio = await asyncio.to_thread(
        self.client.generate,
        text=clean_text,
        voice="Sm1seazb4gs7RSlUVw7c",  # <-- Voice ID yahan de
        model="eleven_multilingual_v2"
    )
    
    audio_io = BytesIO(audio)
    audio_io.seek(0)
    return audio_io

            
        except Exception as e:
            logger.error(f"❌ ElevenLabs error: {e}")
            return None
    
    async def generate(self, text: str) -> Optional[BytesIO]:
        """Generate voice message based on configured provider"""
        if not Config.VOICE_ENABLED:
            return None
        
        if Config.VOICE_PROVIDER == "elevenlabs":
            audio = await self.generate_elevenlabs(text)
            if audio:
                return audio
            # Fallback to gTTS
            logger.info("Falling back to gTTS")
        
        return await self.generate_gtts(text)
    
    def should_send_voice(self, stage: str) -> bool:
        """Decide if should send voice based on relationship stage"""
        if not Config.VOICE_ENABLED:
            return False
        
        # More likely to send voice as relationship progresses
        probabilities = {
            "initial": Config.VOICE_PROBABILITY * 0.5,  # Less voice initially
            "middle": Config.VOICE_PROBABILITY,
            "advanced": Config.VOICE_PROBABILITY * 1.5  # More voice when close
        }
        
        prob = probabilities.get(stage, Config.VOICE_PROBABILITY)
        return random.random() < prob

# Initialize voice generator
voice_gen = VoiceGenerator()

# ==================== DATABASE ====================

class Database:
    """Database manager with Supabase and local fallback"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_db: Dict = {}
        self.use_local = True
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase client"""
        if Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                self.supabase.table('user_chats').select("*").limit(1).execute()
                self.use_local = False
                logger.info("✅ Supabase connected")
            except Exception as e:
                logger.warning(f"⚠️ Supabase failed: {e}")
                self.use_local = True
        else:
            logger.info("📁 Using local storage")
    
    def _load_local(self):
        """Load local database"""
        try:
            if os.path.exists('local_db.json'):
                with open('local_db.json', 'r', encoding='utf-8') as f:
                    self.local_db = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_db)} users")
        except Exception as e:
            logger.error(f"❌ Error loading local db: {e}")
            self.local_db = {}
    
    def _save_local(self):
        """Save local database"""
        try:
            with open('local_db.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Error saving local db: {e}")
    
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
                    "voice_messages_sent": 0,
                    "last_interaction": datetime.now().isoformat()
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
                        "voice_messages_sent": 0,
                        "last_interaction": datetime.now().isoformat()
                    }
                    self.supabase.table('user_chats').insert(new_user).execute()
                    new_user['chats'] = []
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
                logger.error(f"❌ Supabase save error: {e}")
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
            "is_voice": is_voice,
            "timestamp": datetime.now().isoformat()
        })
        
        if len(user['chats']) > 10:
            user['chats'] = user['chats'][-10:]
        
        user['relationship_level'] = min(10, user['relationship_level'] + 1)
        
        if is_voice:
            user['voice_messages_sent'] = user.get('voice_messages_sent', 0) + 1
        
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
        
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        
        context_parts = [
            f"User's name: {user.get('name', 'Unknown')}",
            f"Relationship stage: {user.get('stage', 'initial')}",
            f"Relationship level: {user.get('relationship_level', 1)}/10"
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
        """Get database statistics"""
        if self.use_local:
            total_voice = sum(
                user.get('voice_messages_sent', 0) 
                for user in self.local_db.values()
            )
            return {
                "total_users": len(self.local_db),
                "total_voice_messages": total_voice,
                "storage": "local"
            }
        else:
            try:
                result = self.supabase.table('user_chats').select("user_id, voice_messages_sent", count='exact').execute()
                total_voice = sum(row.get('voice_messages_sent', 0) for row in result.data)
                return {
                    "total_users": result.count if hasattr(result, 'count') else 0,
                    "total_voice_messages": total_voice,
                    "storage": "supabase"
                }
            except:
                return {"total_users": 0, "total_voice_messages": 0, "storage": "error"}

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
    
    async def generate(self, message: str, context: str = "") -> Optional[str]:
        """Generate AI response"""
        if not self.model:
            return None
        
        try:
            full_prompt = f"""{PERSONALITY}

{context}

User says: {message}

Respond as Niyati (short and natural):"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                bad_phrases = [
                    "as an ai", "i'm an ai", "i am an ai", "language model",
                    "artificial intelligence", "chatbot", "gemini", "google ai"
                ]
                
                if any(phrase in text.lower() for phrase in bad_phrases):
                    return random.choice(AI_DENIAL_RESPONSES)
                
                return text
        except Exception as e:
            logger.error(f"❌ Gemini error: {e}")
        
        return None
    
    def fallback_response(self, message: str, stage: str = "initial", name: str = "") -> str:
        """Fallback response"""
        msg_lower = message.lower()
        
        if any(word in msg_lower for word in ["hi", "hello", "hey", "namaste"]):
            return random.choice([
                f"Hello {name}! Kaise ho? 😊",
                f"Hi {name}! 👋",
                f"Hey {name}! 😄"
            ]).replace("  ", " ")
        
        if "?" in message:
            return random.choice([
                "Hmm... good question! 🤔",
                "Interesting! 😊",
            ])
        
        responses = {
            "initial": ["Accha! Tell me more 😊", "Interesting! 😄"],
            "middle": [f"Tumse baat karke accha lagta hai {name}! 😊", "Aur batao! 💖"],
            "advanced": [f"Miss you {name}! 💖", "You make me smile! 🥰"]
        }
        
        return random.choice(responses.get(stage, responses["initial"])).replace("  ", " ")

ai = GeminiAI()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    """Get current IST time"""
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    """Check if sleeping"""
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    """Calculate typing delay"""
    base_delay = min(3.0, max(0.5, len(text) / 50))
    return base_delay + random.uniform(0.3, 1.0)

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start"""
    user = update.effective_user
    user_id = user.id
    
    db.update_user_info(user_id, user.first_name, user.username or "")
    
    voice_status = "🎙️ with Voice Messages!" if Config.VOICE_ENABLED else ""
    
    welcome = f"""
<b>नमस्ते {user.first_name}! 👋</b>

I'm <b>Niyati</b>, a 17-year-old college student from Delhi! 

Chat with me normally - I'll respond with text and sometimes voice messages! {voice_status}

<i>✨ Powered by Gemini AI</i>
"""
    
    await update.message.reply_text(welcome, parse_mode='HTML')
    logger.info(f"✅ User {user_id} started")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats"""
    user_id = update.effective_user.id
    
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only")
        return
    
    stats = db.get_stats()
    user_data = db.get_user(user_id)
    
    stats_msg = f"""
📊 <b>Bot Statistics</b>

👥 Users: {stats['total_users']}
🎙️ Voice Messages: {stats['total_voice_messages']}
💾 Storage: {stats['storage'].upper()}
🤖 AI: {Config.GEMINI_MODEL}

<b>Your Stats:</b>
💬 Messages: {len(user_data.get('chats', []))}
🎤 Voice Received: {user_data.get('voice_messages_sent', 0)}
❤️ Level: {user_data.get('relationship_level', 1)}/10
🎭 Stage: {user_data.get('stage', 'initial')}
"""
    
    await update.message.reply_text(stats_msg, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all messages"""
    try:
        if not update.message or not update.message.text:
            return
        
        is_private = update.message.chat.type == "private"
        is_reply = (update.message.reply_to_message and 
                   update.message.reply_to_message.from_user.id == context.bot.id)
        
        if not (is_private or is_reply):
            return
        
        user_id = update.effective_user.id
        user_msg = update.message.text
        
        # Sleep check
        if is_sleeping_time():
            hour = get_ist_time().hour
            resp = random.choice(SLEEP_RESPONSES_NIGHT if hour < 6 else SLEEP_RESPONSES_MORNING)
            await update.message.reply_text(resp)
            return
        
        # Typing indicator
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        except:
            pass
        
        await asyncio.sleep(calculate_typing_delay(user_msg))
        
        # Get user data
        user_data = db.get_user(user_id)
        stage = user_data.get('stage', 'initial')
        name = user_data.get('name', '')
        
        # Check romantic
        romantic_keywords = ["love", "like you", "girlfriend", "date", "pyar"]
        is_romantic = any(word in user_msg.lower() for word in romantic_keywords)
        
        if is_romantic and stage == "initial":
            response = random.choice(HARD_TO_GET_RESPONSES)
        else:
            context_str = db.get_context(user_id)
            response = await ai.generate(user_msg, context_str)
            
            if not response:
                response = ai.fallback_response(user_msg, stage, name)
            
            if random.random() < 0.3:
                response += " " + random.choice(GF_QUESTIONS)
        
        # Decide voice or text
        send_voice = voice_gen.should_send_voice(stage)
        
        if send_voice:
            # Send voice message
            try:
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                
                audio = await voice_gen.generate(response)
                
                if audio:
                    await update.message.reply_voice(
                        voice=audio,
                        caption="🎙️" if random.random() < 0.3 else None
                    )
                    logger.info(f"🎤 Sent voice to user {user_id}")
                    db.add_message(user_id, user_msg, response, is_voice=True)
                else:
                    # Fallback to text
                    await update.message.reply_text(response)
                    db.add_message(user_id, user_msg, response, is_voice=False)
            except Exception as e:
                logger.error(f"❌ Voice error: {e}")
                await update.message.reply_text(response)
                db.add_message(user_id, user_msg, response, is_voice=False)
        else:
            # Send text
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response, is_voice=False)
        
        logger.info(f"✅ Replied to {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Handler error: {e}")
        try:
            await update.message.reply_text("Oops! Kuch gadbad ho gayi 😅")
        except:
            pass

# ==================== FLASK ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    stats = db.get_stats()
    return jsonify({
        "status": "running",
        "bot": "Niyati",
        "version": "2.1 - Voice Edition",
        "model": Config.GEMINI_MODEL,
        "voice_enabled": Config.VOICE_ENABLED,
        "voice_provider": Config.VOICE_PROVIDER,
        "users": stats['total_users'],
        "voice_messages": stats['total_voice_messages'],
        "storage": stats['storage']
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "sleeping": is_sleeping_time(),
        "time": get_ist_time().strftime("%Y-%m-%d %H:%M:%S IST")
    })

def run_flask():
    logger.info(f"🌐 Flask on port {Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN ====================

async def main():
    try:
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Niyati AI Girlfriend Bot with Voice 🎙️")
        logger.info("="*60)
        logger.info(f"🧠 AI: {Config.GEMINI_MODEL}")
        logger.info(f"🎤 Voice: {Config.VOICE_PROVIDER.upper() if Config.VOICE_ENABLED else 'Disabled'}")
        logger.info(f"💾 Storage: {db.get_stats()['storage'].upper()}")
        logger.info("="*60)
        
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await app.initialize()
        await app.start()
        logger.info("✅ Bot started with voice support!")
        
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Fatal: {e}")
        raise

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    import time
    time.sleep(2)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Stopped")
    except Exception as e:
        logger.critical(f"💥 Error: {e}")
        sys.exit(1)
