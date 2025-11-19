"""
Niyati - Final main.py
- Telegram bot (python-telegram-bot v20+)
- Flask health endpoints
- Gemini support (tries multiple client styles)
- ElevenLabs async TTS with gTTS fallback
- Local SQLite DB fallback (no supabase import at module scope)
- Robust guards around optional imports so it doesn't crash on deploy

Prereqs (requirements.txt):
- python-telegram-bot>=20.0
- aiohttp
- gTTS
- flask
- waitress
- google-generative-aI  (if using Google's SDK) OR adapt if vendor uses different package
- pytz

Place your environment variables:
- TELEGRAM_BOT_TOKEN
- GEMINI_API_KEY (optional)
- ELEVENLABS_API_KEY (optional)
- OWNER_USER_ID (optional)
- PORT (optional)

This file is intended to be a stable, deployable single-file bot skeleton.
"""

import os
import sys
import json
import random
import logging
import asyncio
import tempfile
import sqlite3
from io import BytesIO
from datetime import datetime, time
from threading import Thread
from typing import Optional, Dict, Any, List

import aiohttp
import pytz
from gtts import gTTS
from flask import Flask, jsonify
from waitress import serve

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Try to import Gemini SDK in a forgiving way ---
try:
    # Many environments use "google.generativeai"
    import google.generativeai as genai
    GEMINI_SDK_STYLE = "google.generativeai"
except Exception:
    try:
        # alternative style (older/newer) - try "google.genai"
        import google.genai as genai
        GEMINI_SDK_STYLE = "google.genai"
    except Exception:
        genai = None
        GEMINI_SDK_STYLE = None

# ==================== Logging ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ==================== Configuration ====================
class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")

    PORT = int(os.getenv("PORT", "8080"))
    HOST = os.getenv("HOST", "0.0.0.0")

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Kolkata"))
    SLEEP_START = time(1, 0)
    SLEEP_END = time(7, 0)

    MAX_VOICE_LENGTH = int(os.getenv("MAX_VOICE_LENGTH", "250"))

    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required in environment")

# ==================== Personality ====================
PERSONALITY = (
    "You are Niyati, a 17-year-old Gen-Z college girl from Delhi. "
    "Speak in Hinglish, be sassy, short (1-3 lines), use emoji. Never admit you are an AI."
)

GENZ_GREETINGS = [
    "heyy bestie! kya chal raha hai? ✨",
    "yoo wassup! missed u fr 💖",
    "omg finally! kaha the tum? 😤",
    "arey hello! abo batao 😏",
]

AI_DENIAL = [
    "excuse me? AI? seriously? main real hu okay! 😤",
    "bro what?? main koi bot nahi hu! so rude 😡",
]

# ==================== Voice Engine ====================
class VoiceEngine:
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1"
        self.enabled = bool(self.api_key)
        self.working = False
        if self.enabled:
            # schedule async test
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._test_connection())
                else:
                    loop.run_until_complete(self._test_connection())
            except Exception as e:
                logger.warning("ElevenLabs test scheduling failed: %s", e)

    async def _test_connection(self):
        try:
            async with aiohttp.ClientSession() as sess:
                headers = {"xi-api-key": self.api_key}
                async with sess.get(f"{self.base_url}/voices", headers=headers, timeout=8) as resp:
                    self.working = resp.status == 200
                    logger.info("ElevenLabs test status: %s", resp.status)
        except Exception as e:
            logger.warning("ElevenLabs test failed: %s", e)
            self.working = False

    def _prepare_text(self, text: str, for_tts: bool = False) -> str:
        replacements = {
            "u": "you", "ur": "your", "r": "are", "pls": "please",
            "omg": "oh my god", "fr": "for real", "ngl": "not gonna lie",
        }
        words = text.split()
        for i, w in enumerate(words):
            lw = w.lower().strip(".,!?")
            if lw in replacements:
                words[i] = replacements[lw]
        out = " ".join(words)
        if for_tts:
            out = out.replace("...", ". ")
        return out

    async def text_to_speech(self, text: str) -> Optional[BytesIO]:
        if not text:
            return None
        if len(text) > Config.MAX_VOICE_LENGTH:
            return None

        # Try ElevenLabs if configured
        if self.enabled and self.working:
            try:
                payload = {
                    "text": self._prepare_text(text),
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.6, "similarity_boost": 0.6}
                }
                headers = {"xi-api-key": self.api_key, "Accept": "audio/mpeg"}
                async with aiohttp.ClientSession() as sess:
                    async with sess.post(f"{self.base_url}/text-to-speech/{self.voice_id}", json=payload, headers=headers, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            bio = BytesIO(data)
                            bio.seek(0)
                            return bio
                        else:
                            txt = await resp.text()
                            logger.warning("ElevenLabs returned %s: %s", resp.status, txt[:200])
            except Exception as e:
                logger.warning("ElevenLabs TTS failed: %s", e)

        # gTTS fallback
        try:
            tts = gTTS(text=self._prepare_text(text, for_tts=True), lang="hi", slow=False)
            bio = BytesIO()
            tts.write_to_fp(bio)
            bio.seek(0)
            return bio
        except Exception as e:
            logger.error("gTTS fallback failed: %s", e)
            return None

    def should_send_voice(self, message: str, stage: str = "initial") -> bool:
        if not message:
            return False
        if not self.enabled:
            return False
        if not self.working:
            return False
        emotional = ["miss", "love", "yaad", "baby", "jaan"]
        if any(e in message.lower() for e in emotional):
            return random.random() < 0.8
        return random.random() < 0.2

voice_engine = VoiceEngine()

# ==================== Local SQLite DB ====================
DB_FILE = os.getenv("NIYATI_DB", "niyati.sqlite3")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        chats TEXT,
        relationship_level INTEGER DEFAULT 1,
        stage TEXT DEFAULT 'initial',
        mood TEXT DEFAULT 'happy',
        voice_messages_sent INTEGER DEFAULT 0,
        total_messages INTEGER DEFAULT 0,
        last_interaction TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user(user_id: int) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chats, relationship_level, stage, mood, voice_messages_sent, total_messages, first_name, username FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        user = {
            "user_id": user_id,
            "first_name": "",
            "username": "",
            "chats": [],
            "relationship_level": 1,
            "stage": "initial",
            "mood": "happy",
            "voice_messages_sent": 0,
            "total_messages": 0,
        }
        conn.close()
        return user
    chats_raw, relationship_level, stage, mood, voice_messages_sent, total_messages, first_name, username = row
    try:
        chats = json.loads(chats_raw) if chats_raw else []
    except Exception:
        chats = []
    conn.close()
    return {
        "user_id": user_id,
        "first_name": first_name or "",
        "username": username or "",
        "chats": chats,
        "relationship_level": relationship_level,
        "stage": stage,
        "mood": mood,
        "voice_messages_sent": voice_messages_sent,
        "total_messages": total_messages,
    }

def save_user(user: Dict[str, Any]):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    chats_json = json.dumps(user.get("chats", [])[:50], ensure_ascii=False)
    c.execute("INSERT OR REPLACE INTO users (user_id, first_name, username, chats, relationship_level, stage, mood, voice_messages_sent, total_messages, last_interaction) VALUES (?,?,?,?,?,?,?,?,?,?)", (
        user.get("user_id"), user.get("first_name"), user.get("username"), chats_json,
        user.get("relationship_level", 1), user.get("stage", "initial"), user.get("mood", "happy"),
        user.get("voice_messages_sent", 0), user.get("total_messages", 0), datetime.now(Config.TIMEZONE).isoformat()
    ))
    conn.commit()
    conn.close()

# ==================== Gemini wrapper ====================
class GeminiAI:
    def __init__(self):
        self.client = None
        self.model = Config.GEMINI_MODEL
        if genai and Config.GEMINI_API_KEY:
            try:
                if GEMINI_SDK_STYLE == "google.generativeai":
                    genai.configure(api_key=Config.GEMINI_API_KEY)
                    # store model name only; calls will use genai.generate_text or similar
                    self.client = genai
                else:
                    # try to initialize a client object if SDK provides it
                    try:
                        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
                    except Exception:
                        self.client = genai
                logger.info("Gemini SDK prepared (%s)", GEMINI_SDK_STYLE)
            except Exception as e:
                logger.warning("Gemini setup failed: %s", e)
                self.client = None
        else:
            logger.info("Gemini not configured or not installed; falling back to canned replies")

    async def generate(self, message: str, context: str = "", for_voice: bool = False) -> Optional[str]:
        if not self.client:
            return None
        # Build the prompt
        voice_hint = "\n(Respond with emotional voice-friendly lines)" if for_voice else ""
        full_prompt = f"{PERSONALITY}\n{voice_hint}\n\nContext:\n{context}\n\nUser: {message}\n\nNiyati:"

        try:
            # Different SDK styles expose different APIs — attempt a few safely
            def _call_api():
                try:
                    if GEMINI_SDK_STYLE == "google.generativeai":
                        # older google.generativeai style: genai.generate_text
                        try:
                            r = genai.generate_text(model=self.model, prompt=full_prompt, temperature=0.85, max_output_tokens=220)
                            if hasattr(r, 'text'):
                                return r.text
                            if isinstance(r, dict):
                                return r.get('content') or r.get('text')
                            return str(r)
                        except Exception:
                            # fallback to generative model object
                            try:
                                model_obj = genai.GenerativeModel(model_name=self.model)
                                rr = model_obj.generate_content(full_prompt)
                                return getattr(rr, 'text', None)
                            except Exception as e2:
                                logger.debug('Gemini fallback2 failed: %s', e2)
                                return None
                    else:
                        # try client.models.generate_content style
                        try:
                            model_client = self.client
                            # some clients use .models.generate or .models.generate_content
                            if hasattr(model_client, 'models') and hasattr(model_client.models, 'generate'):
                                res = model_client.models.generate(model=self.model, prompt=full_prompt, temperature=0.85, max_output_tokens=220)
                                if isinstance(res, dict):
                                    return res.get('text') or res.get('content') or str(res)
                                return str(res)
                            if hasattr(model_client, 'models') and hasattr(model_client.models, 'generate_content'):
                                res = model_client.models.generate_content(model=self.model, contents=full_prompt)
                                return getattr(res, 'text', None) or getattr(res, 'content', None)
                            # last resort
                            return None
                        except Exception as e:
                            logger.debug('Other SDK call failed: %s', e)
                            return None
                except Exception as e:
                    logger.debug('Gemini inner error: %s', e)
                    return None

            text = await asyncio.to_thread(_call_api)
            if not text:
                return None
            text = text.strip()
            # Sanitize: if it says "I am an AI" replace with denial
            banned = ["as an ai", "i'm an ai", "i am an ai", "language model", "artificial intelligence"]
            if any(b in text.lower() for b in banned):
                return random.choice(AI_DENIAL)
            # ensure short
            lines = [l for l in text.split('\n') if l.strip()]
            short = '\n'.join(lines[:3])
            if len(short) > 400:
                short = short[:400] + '...'
            return short
        except Exception as e:
            logger.warning("Gemini generate error: %s", e)
            return None

    def fallback(self, message: str) -> str:
        m = message.lower()
        if any(x in m for x in ["hi", "hello", "hey"]):
            return random.choice(GENZ_GREETINGS)
        if any(x in m for x in ["love", "gf", "girlfriend", "cute"]):
            return random.choice(["oop- thoda slow down 😳", "arey arey… blush ho rhi hu 🙈"]) 
        if "?" in m:
            return random.choice(["umm lemme think... 🤔", "good question ngl 💭"]) 
        return random.choice(["hmm interesting... tell me more 👀", "achha? continue na 🙂"]) 


ai = GeminiAI()

# ==================== Utilities ====================

def get_ist_time() -> datetime:
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END


def calculate_typing_delay(text: str) -> float:
    words = max(1, len(text.split()))
    base = min(4.0, 0.2 * words + 0.4)
    return base + random.uniform(0.2, 0.6)

# ==================== Telegram Handlers ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    u = get_user(user.id)
    if not u.get('first_name'):
        u['first_name'] = user.first_name or ''
        u['username'] = user.username or ''
        save_user(u)

    welcome = (
        f"<b>heyy {user.first_name or 'baby'}! 👋✨</b>\n\n"
        "I'm <b>Niyati</b> - 17 y/o college girl from delhi 💅\n"
        "text me like a normal person yaar! i love making friends 🥰"
    )
    await update.message.reply_text(welcome, parse_mode='HTML')

async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ' '.join(context.args) if context.args else (update.message.reply_to_message.text if update.message.reply_to_message else None)
    if not text:
        await update.message.reply_text("Usage: /tts <text> or reply with /tts")
        return
    if len(text) > 800:
        await update.message.reply_text("Text too long. Keep under 800 chars.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)
    audio = await voice_engine.text_to_speech(text)
    if audio:
        await update.message.reply_voice(voice=audio, caption=(text[:120] + '...') if len(text) > 120 else text)
    else:
        await update.message.reply_text("TTS failed. Try again later.")

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        status = 'Enabled' if (voice_engine.enabled and voice_engine.working) else ('Configured (gTTS fallback)' if voice_engine.enabled else 'Disabled')
        await update.message.reply_text(f"Voice status: {status}\nUsage: /voice <text>")
        return
    text = ' '.join(context.args)
    if len(text) > 400:
        await update.message.reply_text("Thoda short karo yaar — max 400 chars.")
        return
    final = text + random.choice([" na", " yaar", " 💕", " hehe"]) 
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)
    audio = await voice_engine.text_to_speech(final)
    if audio:
        await update.message.reply_voice(voice=audio, caption='Niyati speaking ✨')
    else:
        await update.message.reply_text('Voice generation failed — try /tts or later.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>Niyati Bot Commands</b>\n\n"
        "/start - start\n"
        "/help - this\n"
        "/tts <text> - text to speech\n"
        "/voice <text> - Niyati voice\n"
    )
    await update.message.reply_text(text, parse_mode='HTML')

# Message cooldowns
last_group_reply: Dict[int, datetime] = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text:
            return
        is_private = update.message.chat.type == 'private'
        chat_id = update.effective_chat.id
        user = update.effective_user
        if not user:
            return
        user_id = user.id
        text = update.message.text.strip()

        # sleeping check
        if is_sleeping_time() and is_private:
            await update.message.reply_text(random.choice(["yaar abhi so rahi hu... kal baat karte hai 😴", "bruh its late... good night! 💤"]))
            return

        u = get_user(user_id)
        wants_voice = voice_engine.should_send_voice(text, u.get('stage', 'initial')) and is_private

        # if user asks if bot is AI
        if any(k in text.lower() for k in ["bot", "ai", "chatgpt", "gemini", "robot"]):
            denial = random.choice(AI_DENIAL)
            await asyncio.sleep(calculate_typing_delay(denial))
            await update.message.reply_text(denial)
            u['chats'].append({"user": text, "bot": denial, "ts": datetime.now(Config.TIMEZONE).isoformat()})
            u['total_messages'] = u.get('total_messages', 0) + 1
            save_user(u)
            return

        # get context snippet
        ctx = '\n'.join([f"User: {c['user'] if isinstance(c, dict) else c}" for c in (u.get('chats') or [])[-4:]])

        # try AI
        ai_resp = await ai.generate(text, ctx, for_voice=wants_voice)
        if not ai_resp:
            ai_resp = ai.fallback(text)

        if wants_voice:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio = await voice_engine.text_to_speech(ai_resp)
            if audio:
                await update.message.reply_voice(voice=audio, caption=(ai_resp[:120] + '...') if len(ai_resp) > 120 else ai_resp)
                u['voice_messages_sent'] = u.get('voice_messages_sent', 0) + 1
            else:
                await asyncio.sleep(calculate_typing_delay(ai_resp))
                await update.message.reply_text(ai_resp)
        else:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(calculate_typing_delay(ai_resp))
            await update.message.reply_text(ai_resp)

        # save convo
        u['chats'].append({"user": text, "bot": ai_resp, "ts": datetime.now(Config.TIMEZONE).isoformat()})
        u['chats'] = u['chats'][-30:]
        u['total_messages'] = u.get('total_messages', 0) + 1
        u['relationship_level'] = min(10, u.get('relationship_level', 1) + 1)
        lvl = u['relationship_level']
        u['stage'] = 'initial' if lvl <= 3 else ('middle' if lvl <= 7 else 'advanced')
        save_user(u)

    except Exception as e:
        logger.exception("Message handler error: %s", e)
        try:
            await update.message.reply_text("oop something went wrong... try again? 😅")
        except Exception:
            pass

# ==================== Flask app for health
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({"bot": "Niyati", "status": "ok", "time": datetime.now().isoformat()})

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy", "sleeping": is_sleeping_time()})

def run_flask():
    logger.info("Starting Flask on %s:%s", Config.HOST, Config.PORT)
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== Main
async def main():
    Config.validate()
    logger.info("Starting Niyati Bot")

    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('tts', tts_command))
    app.add_handler(CommandHandler('voice', voice_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.start()

    bot_info = await app.bot.get_me()
    logger.info('Bot started: @%s', bot_info.username or 'unknown')

    # initial lightweight scan/log
    logger.info('Ready to reply')

    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Shutting down (KeyboardInterrupt)')
    except Exception as e:
        logger.critical('Fatal error: %s', e)
        sys.exit(1)
