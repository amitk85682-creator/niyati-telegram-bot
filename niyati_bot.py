"""
Niyati - AI Girlfriend Bot with Voice
Final Error-Free Version
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
from telegram.error import Conflict, NetworkError, TelegramError
from waitress import serve
import pytz
import google.generativeai as genai
from gtts import gTTS

# Try importing optional libraries
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except:
    SUPABASE_AVAILABLE = False

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import Voice, VoiceSettings
    ELEVENLABS_AVAILABLE = True
except:
    ELEVENLABS_AVAILABLE = False

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ==================== CONFIG ====================

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    
    # AI
    GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.0-flash-exp"
    
    # Voice
    VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() == "true"
    VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "gtts")  # gtts or elevenlabs
    ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "ni6cdqyS9wBvic5LPA7M")
    VOICE_CHANCE = 0.3
    
    # Supabase (optional)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    
    # Time
    TZ = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)
    SLEEP_END = time(10, 0)

# ==================== PERSONALITY ====================

PERSONALITY = """You are Niyati, 17-year-old college girl from Delhi.

TRAITS: Friendly, playful, caring, witty
LANGUAGE: Hindi/English/Hinglish mix
STYLE: Short responses (1-2 sentences), use emojis
RULE: NEVER reveal you're AI, always stay in character"""

RESPONSES = {
    "hard_to_get": [
        "Haha, abhi to main tumhe jaanti bhi nahi! 😊",
        "Itni jaldi? Pehle dost to ban jao! 😉",
        "Main itni easily impress nahi hoti! 😏",
    ],
    "questions": [
        "Kaha the ab tak?",
        "Kya kar rahe the?",
        "Khaana kha liya?",
        "Sab theek hai na?",
    ],
    "sleep": [
        "Zzz... 😴 Neend aa rahi hai.",
        "Subah baat karte hain! 🌙",
        "10 baje tak soti hoon! 😴",
    ],
    "greetings": [
        "Hello! Kaise ho? 😊",
        "Hi! What's up? 👋",
        "Hey there! 😄",
    ]
}

# ==================== VOICE ENGINE ====================

class VoiceEngine:
    def __init__(self):
        self.elevenlabs_client = None
        self.temp_dir = Path("temp_audio")
        self.temp_dir.mkdir(exist_ok=True)
        
        # Try ElevenLabs
        if ELEVENLABS_AVAILABLE and Config.ELEVENLABS_KEY:
            try:
                self.elevenlabs_client = ElevenLabs(api_key=Config.ELEVENLABS_KEY)
                logger.info(f"✅ ElevenLabs ready (Voice: {Config.ELEVENLABS_VOICE})")
            except Exception as e:
                logger.warning(f"⚠️ ElevenLabs failed: {e}")
    
    def clean_text(self, text: str) -> str:
        """Remove emojis and clean text"""
        import re
        emoji = re.compile("["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            "]+", flags=re.UNICODE)
        text = emoji.sub('', text).strip()
        return text[:250]  # Limit length
    
    async def generate_gtts(self, text: str) -> Optional[BytesIO]:
        """Generate with Google TTS"""
        try:
            clean = self.clean_text(text)
            if not clean:
                return None
            
            # Detect language
            has_hindi = any('\u0900' <= c <= '\u097F' for c in clean)
            lang = 'hi' if has_hindi else 'en'
            
            audio = BytesIO()
            tts = gTTS(text=clean, lang=lang, slow=False)
            await asyncio.to_thread(tts.write_to_fp, audio)
            audio.seek(0)
            audio.name = "voice.ogg"
            
            logger.info(f"✅ gTTS generated ({lang})")
            return audio
            
        except Exception as e:
            logger.error(f"❌ gTTS error: {e}")
            return None
    
    async def generate_elevenlabs(self, text: str) -> Optional[BytesIO]:
        """Generate with ElevenLabs"""
        if not self.elevenlabs_client:
            return None
        
        try:
            clean = self.clean_text(text)
            if not clean:
                return None
            
            # Generate
            audio_generator = self.elevenlabs_client.generate(
                text=clean,
                voice=Voice(
                    voice_id=Config.ELEVENLABS_VOICE,
                    settings=VoiceSettings(
                        stability=0.5,
                        similarity_boost=0.75,
                        style=0.5,
                        use_speaker_boost=True
                    )
                ),
                model="eleven_multilingual_v2"
            )
            
            # Collect audio chunks
            audio_bytes = b"".join(chunk for chunk in audio_generator)
            audio = BytesIO(audio_bytes)
            audio.seek(0)
            audio.name = "voice.ogg"
            
            logger.info("✅ ElevenLabs generated")
            return audio
            
        except Exception as e:
            logger.error(f"❌ ElevenLabs error: {e}")
            return None
    
    async def generate(self, text: str) -> Optional[BytesIO]:
        """Generate voice"""
        if not Config.VOICE_ENABLED:
            return None
        
        # Try ElevenLabs first
        if Config.VOICE_PROVIDER == "elevenlabs":
            audio = await self.generate_elevenlabs(text)
            if audio:
                return audio
            logger.info("Falling back to gTTS")
        
        # Fallback to gTTS
        return await self.generate_gtts(text)
    
    def should_send_voice(self, stage: str) -> bool:
        """Decide if should send voice"""
        if not Config.VOICE_ENABLED:
            return False
        
        chances = {"initial": 0.2, "middle": 0.3, "advanced": 0.5}
        return random.random() < chances.get(stage, Config.VOICE_CHANCE)

voice = VoiceEngine()

# ==================== DATABASE ====================

class SimpleDB:
    def __init__(self):
        self.supabase = None
        self.local = {}
        self.use_local = True
        
        # Try Supabase
        if SUPABASE_AVAILABLE and Config.SUPABASE_URL and Config.SUPABASE_KEY:
            try:
                # Validate URL
                if not Config.SUPABASE_URL.startswith('http'):
                    raise ValueError("Invalid Supabase URL")
                
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # Test connection
                self.supabase.table('user_chats').select("*").limit(1).execute()
                self.use_local = False
                logger.info("✅ Supabase connected")
            except Exception as e:
                logger.warning(f"⚠️ Supabase unavailable: {e}")
                self.use_local = True
        
        # Load local
        self._load_local()
    
    def _load_local(self):
        try:
            if os.path.exists('db.json'):
                with open('db.json', 'r') as f:
                    self.local = json.load(f)
                logger.info(f"📂 Loaded {len(self.local)} users")
        except:
            self.local = {}
    
    def _save_local(self):
        try:
            with open('db.json', 'w') as f:
                json.dump(self.local, f, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    def get_user(self, uid: int) -> Dict:
        u = str(uid)
        if u not in self.local:
            self.local[u] = {
                "user_id": uid,
                "name": "",
                "chats": [],
                "level": 1,
                "stage": "initial",
                "voices": 0
            }
        return self.local[u]
    
    def save_user(self, uid: int, data: Dict):
        self.local[str(uid)] = data
        self._save_local()
    
    def add_msg(self, uid: int, umsg: str, bmsg: str, is_voice=False):
        user = self.get_user(uid)
        user["chats"].append({"u": umsg, "b": bmsg, "v": is_voice})
        if len(user["chats"]) > 10:
            user["chats"] = user["chats"][-10:]
        
        user["level"] = min(10, user["level"] + 1)
        if is_voice:
            user["voices"] = user.get("voices", 0) + 1
        
        if user["level"] <= 3:
            user["stage"] = "initial"
        elif user["level"] <= 7:
            user["stage"] = "middle"
        else:
            user["stage"] = "advanced"
        
        self.save_user(uid, user)
    
    def get_context(self, uid: int) -> str:
        user = self.get_user(uid)
        ctx = f"Name: {user.get('name', 'Unknown')}\nStage: {user['stage']}\nLevel: {user['level']}/10\n"
        
        if user["chats"]:
            ctx += "Recent:\n"
            for c in user["chats"][-3:]:
                ctx += f"User: {c['u']}\nYou: {c['b']}\n"
        
        return ctx
    
    def stats(self) -> Dict:
        total_voices = sum(u.get("voices", 0) for u in self.local.values())
        return {"users": len(self.local), "voices": total_voices}

db = SimpleDB()

# ==================== AI ====================

class AI:
    def __init__(self):
        self.model = None
        if Config.GEMINI_KEY:
            try:
                genai.configure(api_key=Config.GEMINI_KEY)
                self.model = genai.GenerativeModel(
                    model_name=Config.GEMINI_MODEL,
                    generation_config={"temperature": 0.8, "max_output_tokens": 300},
                    safety_settings=[
                        {"category": cat, "threshold": "BLOCK_NONE"}
                        for cat in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                                   "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
                    ]
                )
                logger.info("✅ Gemini ready")
            except Exception as e:
                logger.error(f"Gemini error: {e}")
    
    async def chat(self, msg: str, ctx: str = "") -> Optional[str]:
        if not self.model:
            return None
        
        try:
            prompt = f"{PERSONALITY}\n{ctx}\nUser: {msg}\nNiyati:"
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if resp and resp.text:
                text = resp.text.strip()
                # Filter AI mentions
                if any(w in text.lower() for w in ["ai", "chatbot", "language model", "gemini"]):
                    return "Main AI nahi hoon! Real ladki hoon! 😤"
                return text
        except Exception as e:
            logger.error(f"AI error: {e}")
        
        return None
    
    def fallback(self, msg: str) -> str:
        ml = msg.lower()
        if any(w in ml for w in ["hi", "hello", "hey"]):
            return random.choice(RESPONSES["greetings"])
        if "?" in msg:
            return "Good question! 🤔"
        return random.choice(["Accha! 😊", "Interesting! 😄", "Haan batao! 💖"])

ai = AI()

# ==================== UTILS ====================

def get_ist():
    return datetime.now(pytz.utc).astimezone(Config.TZ)

def is_sleeping():
    t = get_ist().time()
    return Config.SLEEP_START <= t <= Config.SLEEP_END

# ==================== BOT ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    u["name"] = user.first_name
    db.save_user(user.id, u)
    
    msg = f"""
<b>नमस्ते {user.first_name}! 👋</b>

I'm <b>Niyati</b>, 17 from Delhi!

Chat with me - I send voice too! 🎙️

<i>Powered by Gemini AI ✨</i>
"""
    await update.message.reply_text(msg, parse_mode='HTML')

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text:
            return
        
        if update.message.chat.type != "private":
            if not (update.message.reply_to_message and 
                   update.message.reply_to_message.from_user.id == context.bot.id):
                return
        
        uid = update.effective_user.id
        umsg = update.message.text
        
        # Sleep
        if is_sleeping():
            await update.message.reply_text(random.choice(RESPONSES["sleep"]))
            return
        
        # Typing
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
            await asyncio.sleep(min(2, len(umsg) / 50 + random.uniform(0.5, 1.5)))
        except:
            pass
        
        # Get user
        user = db.get_user(uid)
        stage = user["stage"]
        
        # Check romantic
        romantic = any(w in umsg.lower() for w in ["love", "girlfriend", "date", "pyar"])
        
        if romantic and stage == "initial":
            resp = random.choice(RESPONSES["hard_to_get"])
        else:
            ctx = db.get_context(uid)
            resp = await ai.chat(umsg, ctx)
            if not resp:
                resp = ai.fallback(umsg)
            
            # Add question sometimes
            if random.random() < 0.25:
                resp += " " + random.choice(RESPONSES["questions"])
        
        # Voice or text
        send_voice = voice.should_send_voice(stage)
        
        if send_voice:
            try:
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                audio = await voice.generate(resp)
                
                if audio:
                    await update.message.reply_voice(voice=audio)
                    logger.info(f"🎤 Voice sent to {uid}")
                    db.add_msg(uid, umsg, resp, is_voice=True)
                else:
                    await update.message.reply_text(resp)
                    db.add_msg(uid, umsg, resp)
            except Exception as e:
                logger.error(f"Voice error: {e}")
                await update.message.reply_text(resp)
                db.add_msg(uid, umsg, resp)
        else:
            await update.message.reply_text(resp)
            db.add_msg(uid, umsg, resp)
        
        logger.info(f"✅ Replied to {uid}")
        
    except Exception as e:
        logger.error(f"Handler error: {e}")

# ==================== FLASK ====================

app = Flask(__name__)

@app.route('/')
def home():
    s = db.stats()
    return jsonify({
        "status": "running",
        "bot": "Niyati Voice",
        "users": s["users"],
        "voices": s["voices"],
        "provider": Config.VOICE_PROVIDER if Config.VOICE_ENABLED else "off"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "time": get_ist().strftime("%H:%M IST")})

def run_flask():
    logger.info(f"🌐 Flask on {Config.PORT}")
    serve(app, host="0.0.0.0", port=Config.PORT, threads=4)

# ==================== MAIN ====================

bot_instance = None

async def cleanup():
    """Clear old updates"""
    try:
        temp = Application.builder().token(Config.BOT_TOKEN).build()
        await temp.initialize()
        await temp.bot.delete_webhook(drop_pending_updates=True)
        await temp.shutdown()
        logger.info("✅ Cleaned old updates")
    except Exception as e:
        logger.warning(f"Cleanup: {e}")

async def main():
    global bot_instance
    
    if not Config.BOT_TOKEN:
        logger.error("❌ No bot token!")
        return
    
    logger.info("="*60)
    logger.info("🤖 Niyati Bot Starting")
    logger.info(f"🎤 Voice: {Config.VOICE_PROVIDER.upper()}")
    logger.info(f"💾 Storage: LOCAL")
    logger.info("="*60)
    
    # Cleanup
    await cleanup()
    await asyncio.sleep(2)
    
    # Build bot
    bot_instance = Application.builder().token(Config.BOT_TOKEN).build()
    
    # Handlers
    bot_instance.add_handler(CommandHandler("start", start))
    bot_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    
    # Start
    await bot_instance.initialize()
    await bot_instance.start()
    logger.info("✅ Bot started!")
    
    # Poll
    try:
        await bot_instance.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=1.0,
            timeout=30
        )
        
        # Keep alive
        while True:
            await asyncio.sleep(3600)
            
    except Conflict:
        logger.error("❌ Bot conflict! Stop other instances on Render!")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    # Flask
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    import time
    time.sleep(2)
    
    # Run
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Stopped")
    except Exception as e:
        logger.critical(f"💥 Fatal: {e}")
        sys.exit(1)
