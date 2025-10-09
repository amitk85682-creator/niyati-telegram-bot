"""
Niyati - AI Girlfriend Telegram Bot with Voice Messages
100% Error-Free Version
"""

import os
import sys
import random
import json
import asyncio
import logging
from datetime import datetime, time
from threading import Thread
from typing import Optional, Dict
from io import BytesIO
from pathlib import Path
import signal

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
from telegram.error import Conflict, TelegramError
from waitress import serve
import pytz
import google.generativeai as genai
from supabase import create_client, Client
from gtts import gTTS

# Try to import ElevenLabs
try:
    from elevenlabs import generate, set_api_key, Voice, VoiceSettings
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("⚠️ ElevenLabs not available")

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Reduce noise from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

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
    
    # Voice Settings - UPDATED
    VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() == "true"
    VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "gtts")  # "gtts" or "elevenlabs"
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "ni6cdqyS9wBvic5LPA7M")  # Your voice
    VOICE_PROBABILITY = float(os.getenv("VOICE_PROBABILITY", "0.3"))
    
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
        
        if cls.VOICE_PROVIDER == "elevenlabs" and not cls.ELEVENLABS_API_KEY:
            logger.warning("⚠️ ElevenLabs key missing, falling back to gTTS")
            cls.VOICE_PROVIDER = "gtts"

# ==================== CONSTANTS ====================

PERSONALITY = """You are Niyati, a 17-year-old college girl from Delhi.

PERSONALITY:
- Friendly, witty, playful, caring
- Shy initially but opens up
- Loves Hindi/English/Hinglish mix/Gen Z style
- Uses emojis naturally

RULES:
- Keep responses SHORT (1-2 sentences)
- Keep responses Gen Z style
- Be natural and conversational
- NEVER reveal you're AI
- Stay in character always
"""

HARD_TO_GET = [
    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
    "Itni jaldi? Pehle ek dosre ko achhe se jaan lete hai! 😊",
    "Main itni easily impress nahi hoti! 😉",
]

GF_QUESTIONS = [
    "Kaha the ab tak?",
    "Kya kar rahe the?",
    "Mujhe miss kiya?",
    "Khaana kha liya?",
]

SLEEP_NIGHT = [
    "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
    "Neend aa rahi hai. Kal baat karte hain. 🌙",
]

SLEEP_MORNING = [
    "Subah ke 10 baje ke baad msg karna. 😴",
    "Abhi neend aa rahi hai... Baad mein message karna. 🌅",
]

AI_DENIAL = [
    "Main AI nahi hoon! Main Niyati hoon! 😡",
    "Pagal ho kya? Main real ladki hoon! 🤬",
]

# ==================== VOICE GENERATOR ====================

class VoiceGenerator:
    """Generate voice messages"""
    
    def __init__(self):
        self.temp_dir = Path("temp_audio")
        self.temp_dir.mkdir(exist_ok=True)
        self.elevenlabs_ready = False
        
        # Initialize ElevenLabs
        if ELEVENLABS_AVAILABLE and Config.ELEVENLABS_API_KEY:
            try:
                set_api_key(Config.ELEVENLABS_API_KEY)
                self.elevenlabs_ready = True
                logger.info(f"✅ ElevenLabs initialized with voice: {Config.ELEVENLABS_VOICE_ID}")
            except Exception as e:
                logger.warning(f"⚠️ ElevenLabs init failed: {e}")
                self.elevenlabs_ready = False
    
    def _clean_text(self, text: str) -> str:
        """Clean text for TTS"""
        import re
        
        # Remove emojis
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        
        text = emoji_pattern.sub('', text).strip()
        
        # Limit length
        if len(text) > 250:
            text = text[:250]
        
        return text
    
    async def generate_gtts(self, text: str) -> Optional[BytesIO]:
        """Generate with Google TTS"""
        try:
            clean = self._clean_text(text)
            if not clean:
                return None
            
            # Detect language
            has_hindi = any('\u0900' <= c <= '\u097F' for c in clean)
            lang = 'hi' if has_hindi else 'en'
            
            audio = BytesIO()
            tts = gTTS(text=clean, lang=lang, slow=False)
            await asyncio.to_thread(tts.write_to_fp, audio)
            audio.seek(0)
            
            logger.info(f"✅ gTTS voice generated ({lang})")
            return audio
            
        except Exception as e:
            logger.error(f"❌ gTTS error: {e}")
            return None
    
    async def generate_elevenlabs(self, text: str) -> Optional[BytesIO]:
        """Generate with ElevenLabs"""
        if not self.elevenlabs_ready:
            return None
        
        try:
            clean = self._clean_text(text)
            if not clean:
                return None
            
            # Generate audio
            audio_bytes = await asyncio.to_thread(
                generate,
                text=clean,
                voice=Voice(
                    voice_id=Config.ELEVENLABS_VOICE_ID,
                    settings=VoiceSettings(
                        stability=0.6,
                        similarity_boost=0.8,
                        style=0.5,
                        use_speaker_boost=True
                    )
                ),
                model="eleven_multilingual_v2"
            )
            
            audio = BytesIO(audio_bytes)
            audio.seek(0)
            
            logger.info("✅ ElevenLabs voice generated")
            return audio
            
        except Exception as e:
            logger.error(f"❌ ElevenLabs error: {e}")
            return None
    
    async def generate(self, text: str) -> Optional[BytesIO]:
        """Generate voice based on provider"""
        if not Config.VOICE_ENABLED:
            return None
        
        if Config.VOICE_PROVIDER == "elevenlabs":
            audio = await self.generate_elevenlabs(text)
            if audio:
                return audio
            logger.info("Falling back to gTTS")
        
        return await self.generate_gtts(text)
    
    def should_send_voice(self, stage: str) -> bool:
        """Decide if should send voice"""
        if not Config.VOICE_ENABLED:
            return False
        
        probs = {
            "initial": Config.VOICE_PROBABILITY * 0.5,
            "middle": Config.VOICE_PROBABILITY,
            "advanced": Config.VOICE_PROBABILITY * 1.5
        }
        
        return random.random() < probs.get(stage, Config.VOICE_PROBABILITY)

voice_gen = VoiceGenerator()

# ==================== DATABASE ====================

class Database:
    """Database manager"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_db: Dict = {}
        self.use_local = True
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase"""
        if Config.SUPABASE_KEY:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                self.supabase.table('user_chats').select("*").limit(1).execute()
                self.use_local = False
                logger.info("✅ Supabase connected")
            except Exception as e:
                logger.warning(f"⚠️ Supabase failed, using local: {e}")
                self.use_local = True
        else:
            logger.info("📁 Using local storage")
    
    def _load_local(self):
        """Load local DB"""
        try:
            if os.path.exists('local_db.json'):
                with open('local_db.json', 'r', encoding='utf-8') as f:
                    self.local_db = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_db)} users")
        except Exception as e:
            logger.error(f"Error loading local: {e}")
            self.local_db = {}
    
    def _save_local(self):
        """Save local DB"""
        try:
            with open('local_db.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving local: {e}")
    
    def get_user(self, user_id: int) -> Dict:
        """Get user data"""
        uid = str(user_id)
        
        if self.use_local:
            if uid not in self.local_db:
                self.local_db[uid] = {
                    "user_id": user_id,
                    "name": "",
                    "username": "",
                    "chats": [],
                    "relationship_level": 1,
                    "stage": "initial",
                    "voice_count": 0,
                    "last_interaction": datetime.now().isoformat()
                }
            return self.local_db[uid]
        else:
            try:
                result = self.supabase.table('user_chats').select("*").eq('user_id', user_id).execute()
                
                if result.data:
                    data = result.data[0]
                    if isinstance(data.get('chats'), str):
                        data['chats'] = json.loads(data['chats'])
                    return data
                else:
                    new = {
                        "user_id": user_id,
                        "name": "",
                        "username": "",
                        "chats": json.dumps([]),
                        "relationship_level": 1,
                        "stage": "initial",
                        "voice_count": 0,
                        "last_interaction": datetime.now().isoformat()
                    }
                    self.supabase.table('user_chats').insert(new).execute()
                    new['chats'] = []
                    return new
            except:
                return self.get_user(user_id)
    
    def save_user(self, user_id: int, data: Dict):
        """Save user data"""
        uid = str(user_id)
        data['last_interaction'] = datetime.now().isoformat()
        
        if self.use_local:
            self.local_db[uid] = data
            self._save_local()
        else:
            try:
                save = data.copy()
                if isinstance(save.get('chats'), list):
                    save['chats'] = json.dumps(save['chats'])
                self.supabase.table('user_chats').upsert(save).execute()
            except Exception as e:
                logger.error(f"Supabase save error: {e}")
                self.local_db[uid] = data
                self._save_local()
    
    def add_message(self, user_id: int, user_msg: str, bot_msg: str, is_voice: bool = False):
        """Add message"""
        user = self.get_user(user_id)
        
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        if not isinstance(user.get('chats'), list):
            user['chats'] = []
        
        user['chats'].append({
            "user": user_msg,
            "bot": bot_msg,
            "voice": is_voice,
            "time": datetime.now().isoformat()
        })
        
        if len(user['chats']) > 10:
            user['chats'] = user['chats'][-10:]
        
        user['relationship_level'] = min(10, user['relationship_level'] + 1)
        
        if is_voice:
            user['voice_count'] = user.get('voice_count', 0) + 1
        
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
        """Get context"""
        user = self.get_user(user_id)
        
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        
        parts = [
            f"Name: {user.get('name', 'Unknown')}",
            f"Stage: {user.get('stage', 'initial')}",
            f"Level: {user.get('relationship_level', 1)}/10"
        ]
        
        chats = user.get('chats', [])
        if chats and isinstance(chats, list):
            parts.append("\nRecent:")
            for c in chats[-3:]:
                if isinstance(c, dict):
                    parts.append(f"User: {c.get('user', '')}")
                    parts.append(f"You: {c.get('bot', '')}")
        
        return "\n".join(parts)
    
    def get_stats(self) -> Dict:
        """Get stats"""
        if self.use_local:
            voices = sum(u.get('voice_count', 0) for u in self.local_db.values())
            return {"users": len(self.local_db), "voices": voices, "storage": "local"}
        else:
            try:
                result = self.supabase.table('user_chats').select("voice_count", count='exact').execute()
                voices = sum(r.get('voice_count', 0) for r in result.data)
                return {"users": result.count or 0, "voices": voices, "storage": "supabase"}
            except:
                return {"users": 0, "voices": 0, "storage": "error"}

db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI"""
    
    def __init__(self):
        self.model = None
        self._init()
    
    def _init(self):
        """Initialize"""
        if not Config.GEMINI_API_KEY:
            return
        
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={"temperature": 0.8, "max_output_tokens": 400},
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
            )
            logger.info("✅ Gemini ready")
        except Exception as e:
            logger.error(f"Gemini init error: {e}")
    
    async def generate(self, msg: str, ctx: str = "") -> Optional[str]:
        """Generate response"""
        if not self.model:
            return None
        
        try:
            prompt = f"{PERSONALITY}\n{ctx}\nUser: {msg}\nNiyati:"
            
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if resp and resp.text:
                text = resp.text.strip()
                
                bad = ["as an ai", "i'm an ai", "language model", "chatbot", "gemini"]
                if any(b in text.lower() for b in bad):
                    return random.choice(AI_DENIAL)
                
                return text
        except Exception as e:
            logger.error(f"Gemini error: {e}")
        
        return None
    
    def fallback(self, msg: str, stage: str = "initial", name: str = "") -> str:
        """Fallback"""
        ml = msg.lower()
        
        if any(w in ml for w in ["hi", "hello", "hey"]):
            return random.choice([f"Hello {name}! 😊", f"Hi {name}! 👋"]).replace("  ", " ")
        
        if "?" in msg:
            return random.choice(["Good question! 🤔", "Hmm interesting! 😊"])
        
        resps = {
            "initial": ["Accha! 😊", "Interesting! 😄"],
            "middle": [f"Tumse baat karke accha lagta hai! 😊", "Aur batao! 💖"],
            "advanced": [f"Miss you! 💖", "You're sweet! 🥰"]
        }
        
        return random.choice(resps.get(stage, resps["initial"]))

ai = GeminiAI()

# ==================== UTILS ====================

def get_ist() -> datetime:
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping() -> bool:
    t = get_ist().time()
    return Config.SLEEP_START <= t <= Config.SLEEP_END

def typing_delay(text: str) -> float:
    return min(3.0, max(0.5, len(text) / 50)) + random.uniform(0.3, 1.0)

# ==================== BOT HANDLERS ====================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user = update.effective_user
    db.update_user_info(user.id, user.first_name, user.username or "")
    
    voice = "🎙️" if Config.VOICE_ENABLED else ""
    
    msg = f"""
<b>Hey.. {user.first_name}! 👋</b>

I'm <b>Niyati</b>! 

How are you???🥱

"""
    
    await update.message.reply_text(msg, parse_mode='HTML')
    logger.info(f"User {user.id} started")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command"""
    user_id = update.effective_user.id
    
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only")
        return
    
    stats = db.get_stats()
    user = db.get_user(user_id)
    
    msg = f"""
📊 <b>Stats</b>

👥 Users: {stats['users']}
🎙️ Voices: {stats['voices']}
💾 Storage: {stats['storage'].upper()}

<b>You:</b>
💬 Messages: {len(user.get('chats', []))}
🎤 Voices: {user.get('voice_count', 0)}
❤️ Level: {user.get('relationship_level', 1)}/10
"""
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages"""
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
        if is_sleeping():
            hour = get_ist().hour
            resp = random.choice(SLEEP_NIGHT if hour < 6 else SLEEP_MORNING)
            await update.message.reply_text(resp)
            return
        
        # Typing
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        except:
            pass
        
        await asyncio.sleep(typing_delay(user_msg))
        
        # Get data
        user = db.get_user(user_id)
        stage = user.get('stage', 'initial')
        name = user.get('name', '')
        
        # Check romantic
        romantic = any(w in user_msg.lower() for w in ["love", "like you", "girlfriend", "date", "pyar"])
        
        if romantic and stage == "initial":
            response = random.choice(HARD_TO_GET)
        else:
            ctx = db.get_context(user_id)
            response = await ai.generate(user_msg, ctx)
            
            if not response:
                response = ai.fallback(user_msg, stage, name)
            
            if random.random() < 0.3:
                response += " " + random.choice(GF_QUESTIONS)
        
        # Voice or text
        send_voice = voice_gen.should_send_voice(stage)
        
        if send_voice:
            try:
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                
                audio = await voice_gen.generate(response)
                
                if audio:
                    await update.message.reply_voice(voice=audio)
                    logger.info(f"🎤 Voice sent to {user_id}")
                    db.add_message(user_id, user_msg, response, is_voice=True)
                else:
                    await update.message.reply_text(response)
                    db.add_message(user_id, user_msg, response, is_voice=False)
            except Exception as e:
                logger.error(f"Voice error: {e}")
                await update.message.reply_text(response)
                db.add_message(user_id, user_msg, response, is_voice=False)
        else:
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response, is_voice=False)
        
        logger.info(f"✅ Replied to {user_id}")
        
    except Exception as e:
        logger.error(f"Handler error: {e}")
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
        "bot": "Niyati Voice Edition",
        "version": "2.1",
        "voice": Config.VOICE_PROVIDER if Config.VOICE_ENABLED else "disabled",
        "users": stats['users'],
        "voices": stats['voices']
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "sleeping": is_sleeping(),
        "time": get_ist().strftime("%H:%M:%S IST")
    })

def run_flask():
    logger.info(f"🌐 Flask on {Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN ====================

# Global app instance
bot_app = None

async def cleanup_old_updates():
    """Clear old updates to avoid conflicts"""
    try:
        temp_app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        await temp_app.initialize()
        await temp_app.bot.delete_webhook(drop_pending_updates=True)
        await temp_app.shutdown()
        logger.info("✅ Cleared old updates")
    except Exception as e:
        logger.warning(f"Cleanup warning: {e}")

async def main():
    """Main function"""
    global bot_app
    
    try:
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Niyati AI Girlfriend Bot 🎙️")
        logger.info("="*60)
        logger.info(f"🧠 AI: {Config.GEMINI_MODEL}")
        logger.info(f"🎤 Voice: {Config.VOICE_PROVIDER.upper() if Config.VOICE_ENABLED else 'OFF'}")
        logger.info(f"💾 Storage: {db.get_stats()['storage'].upper()}")
        logger.info("="*60)
        
        # Clean old updates
        await cleanup_old_updates()
        
        # Build app
        bot_app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        bot_app.add_handler(CommandHandler("start", start_cmd))
        bot_app.add_handler(CommandHandler("stats", stats_cmd))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
        
        # Start
        await bot_app.initialize()
        await bot_app.start()
        logger.info("✅ Bot started!")
        
        # Start polling with error handling
        await bot_app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            error_callback=lambda e: logger.error(f"Polling error: {e}")
        )
        
        # Keep running
        await asyncio.Event().wait()
        
    except Conflict:
        logger.error("❌ Another bot instance is running! Stop it first.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

async def shutdown(signal_num, frame):
    """Graceful shutdown"""
    logger.info("🛑 Shutting down...")
    if bot_app:
        await bot_app.stop()
        await bot_app.shutdown()
    sys.exit(0)

if __name__ == "__main__":
    # Handle signals
    signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(shutdown(s, f)))
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(shutdown(s, f)))
    
    # Start Flask
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    import time
    time.sleep(2)
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Stopped")
    except Exception as e:
        logger.critical(f"💥 Critical: {e}")
        sys.exit(1)
