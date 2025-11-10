"""
Niyati - Gen-Z AI Girlfriend Telegram Bot v7.0 (VAPI Integration - Fixed)

Fixed async initialization issues that were causing runtime errors.
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
from typing import Optional, List, Dict, Any
from io import BytesIO
from collections import defaultdict

from flask import Flask, jsonify
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.error import Forbidden, BadRequest
from waitress import serve
import pytz
from gtts import gTTS

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

    # VAPI Configuration
    VAPI_API_KEY = os.getenv("VAPI_API_KEY", "eb7b4acb-6997-4e42-a3c2-04b66ff2a44c")  # Private Key
    VAPI_PUBLIC_KEY = os.getenv("VAPI_PUBLIC_KEY", "b702dff1-4ce9-4fa9-8003-1d7448620a69")  # Public Key
    VAPI_BASE_URL = "https://api.vapi.ai"
    
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "DpnM70iDHNHZ0Mguv6GJ")

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Kolkata"))
    SLEEP_START = time(1, 0)
    SLEEP_END = time(7, 0)

    VOICE_MESSAGE_CHANCE = float(os.getenv("VOICE_MESSAGE_CHANCE", "0.28"))
    MAX_VOICE_LENGTH = int(os.getenv("MAX_VOICE_LENGTH", "250"))

    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not cls.VAPI_API_KEY:
            logger.warning("VAPI_API_KEY not set — bot will use local fallbacks for AI replies")
        if not cls.SUPABASE_KEY or not cls.SUPABASE_URL:
            logger.info("Supabase not configured — using local JSON storage")
        if not cls.ELEVENLABS_API_KEY:
            logger.info("ElevenLabs not configured — gTTS fallback will be used")

# ==================== PERSONALITY & CONTENT ====================

PERSONALITY = """You are Niyati, a 17-year-old Gen-Z college girl from Delhi.
Keep responses short (1-3 lines), in Hinglish (mix Hindi/English), use Gen-Z slang and emojis.
Never admit you are an AI. Be sassy, caring, sometimes jealous, and playful.
Prefer short sentences and lots of emoji. If user flirts, react shyly then playfully.
Respond as Niyati directly (no system commentary)."""

GENZ_GREETINGS = [
    "heyy bestie! kya chal raha hai? ✨",
    "yoo wassup! missed u fr 💖",
    "omg finally! kaha the tum? 😤",
    "arey hello! abo batao 😏",
]
GENZ_FLIRT = ["oop- thoda slow down 😳", "arey arey… blush ho rhi hu 🙈", "ngl, like ur vibes 💕"]
JEALOUS = ["kon hai wo? 😤 naam do", "ur talking to other girls?? 😒", "blocked. bye. 😤"]
AI_DENIAL = [
    "excuse me? AI? seriously? main real hu okay! 😤",
    "bro what?? main koi bot nahi hu! so rude 😡",
    "AI? no no, wrong number 😒",
]

# ==================== VOICE ENGINE (async ElevenLabs with gTTS fallback) ====================

class VoiceEngine:
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1"
        self.enabled = bool(self.api_key)
        self.working = False
        self._initialized = False

    async def initialize(self):
        """Initialize the voice engine - call this from async context"""
        if self._initialized:
            return
        self._initialized = True
        
        if self.enabled:
            try:
                await self._test_connection()
            except Exception as e:
                logger.warning("ElevenLabs initialization failed: %s", e)

    async def _test_connection(self):
        try:
            async with aiohttp.ClientSession() as sess:
                headers = {"xi-api-key": self.api_key}
                async with sess.get(f"{self.base_url}/voices", headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        self.working = True
                        logger.info("ElevenLabs reachable and configured")
                    else:
                        self.working = False
                        logger.warning("ElevenLabs test request failed: %s", resp.status)
        except Exception as e:
            logger.warning("ElevenLabs test failed: %s", e)
            self.working = False

    async def text_to_speech(self, text: str, voice_id: Optional[str] = None) -> Optional[BytesIO]:
        if not text:
            return None
        if len(text) > Config.MAX_VOICE_LENGTH:
            logger.debug("Text too long for voice: %d chars", len(text))
            return None
        if self.enabled and self.working:
            vid = voice_id or self.voice_id
            url = f"{self.base_url}/text-to-speech/{vid}"
            payload = {
                "text": self._prepare_text(text),
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.6, "similarity_boost": 0.6},
            }
            headers = {"xi-api-key": self.api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"}
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.post(url, json=payload, headers=headers, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            bio = BytesIO(data)
                            bio.seek(0)
                            logger.debug("ElevenLabs TTS success")
                            return bio
                        else:
                            txt = await resp.text()
                            logger.warning("ElevenLabs response %s: %s", resp.status, txt[:200])
            except Exception as e:
                logger.warning("ElevenLabs request failed: %s", e)

        try:
            logger.debug("Using gTTS fallback")
            tts = gTTS(text=self._prepare_text(text, for_tts=True), lang="hi", slow=False)
            bio = BytesIO()
            tts.write_to_fp(bio)
            bio.seek(0)
            return bio
        except Exception as e:
            logger.error("gTTS fallback failed: %s", e)
            return None

    def _prepare_text(self, text: str, for_tts: bool = False) -> str:
        repl = {
            "u": "you", "ur": "your", "r": "are", "pls": "please", "omg": "oh my god",
            "fr": "for real", "ngl": "not gonna lie", "lol": "haha"
        }
        words = text.split()
        for i, w in enumerate(words):
            lw = w.lower().strip(".,!?")
            if lw in repl:
                words[i] = repl[lw]
        out = " ".join(words)
        if for_tts:
            out = out.replace("...", ". ")
        return out

    def should_send_voice(self, message: str, stage: str = "initial") -> bool:
        if not self.enabled:
            return False
        if not self.working:
            return False
        if not message:
            return False
        if len(message) > Config.MAX_VOICE_LENGTH:
            return False

        emotional_markers = ["miss", "love", "yaad", "baby", "jaan", "❤", "💕", "😘", "cry", "sad"]
        if any(m in message.lower() for m in emotional_markers):
            return random.random() < 0.85

        stage_map = {"initial": 0.12, "middle": 0.22, "advanced": 0.35}
        base = stage_map.get(stage, Config.VOICE_MESSAGE_CHANCE)
        return random.random() < base

voice_engine = VoiceEngine()

# ==================== DATABASE (Supabase optional / local fallback) ====================

class Database:
    def __init__(self):
        # type of supabase client is dynamic; avoid importing Client at module level
        self.supabase: Optional[Any] = None
        self.create_client = None  # function reference if available
        self.local_db_path = "local_db.json"
        self.groups_path = "groups_data.json"
        self.local_db: Dict[str, Dict] = {}
        self.groups_data: Dict[int, Dict] = {}
        self.use_local = True
        self._init_supabase()
        self._load_local()

    def _init_supabase(self):
        """
        Try to import create_client lazily. If import fails (ModuleNotFoundError or other),
        keep using local JSON storage and log a helpful message. This prevents deployment
        crashes when the environment does not have matching supabase dependencies.
        """
        if not (Config.SUPABASE_KEY and Config.SUPABASE_URL):
            self.use_local = True
            return

        try:
            # lazy import to avoid module-level import errors like missing sub-deps
            from supabase import create_client  # type: ignore
            self.create_client = create_client
            try:
                self.supabase = self.create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # quick health check: do not crash if table missing
                try:
                    self.supabase.table("user_chats").select("*").limit(1).execute()
                    self.use_local = False
                    logger.info("Supabase connected")
                except Exception:
                    logger.warning("Supabase reachable but failed read (table might not exist). Using local fallback.")
                    self.use_local = True
            except Exception as e:
                logger.warning("Supabase client initialization failed: %s", e)
                self.supabase = None
                self.use_local = True
        except ModuleNotFoundError as e:
            # Common in minimal deployment where supabase_auth or other deps missing
            logger.warning("Supabase library not available: %s. Falling back to local JSON DB.", e)
            self.use_local = True
            self.supabase = None
        except Exception as e:
            logger.warning("Unexpected error importing supabase: %s. Falling back to local JSON DB.", e)
            self.use_local = True
            self.supabase = None

    def _load_local(self):
        try:
            if os.path.exists(self.local_db_path):
                with open(self.local_db_path, "r", encoding="utf-8") as f:
                    self.local_db = json.load(f)
            if os.path.exists(self.groups_path):
                with open(self.groups_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.groups_data = {int(k): v for k, v in raw.items()}
        except Exception as e:
            logger.warning("Failed to load local DB: %s", e)
            self.local_db = {}
            self.groups_data = {}

    def _save_local(self):
        try:
            with open(self.local_db_path, "w", encoding="utf-8") as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=2)
            with open(self.groups_path, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in self.groups_data.items()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Saving local DB failed: %s", e)

    def add_group(self, group_id: int, title: str = "", username: str = ""):
        now = datetime.utcnow().isoformat()
        g = self.groups_data.get(group_id, {})
        g.update({
            "id": group_id,
            "title": title or g.get("title", ""),
            "username": username or g.get("username", ""),
            "joined_at": g.get("joined_at", now),
            "last_activity": now,
            "messages_count": g.get("messages_count", 0) + 1,
            "is_active": True,
        })
        self.groups_data[group_id] = g
        self._save_local()

    def remove_group(self, group_id: int):
        if group_id in self.groups_data:
            self.groups_data[group_id]["is_active"] = False
            self._save_local()

    def get_active_groups(self) -> List[int]:
        return [gid for gid, v in self.groups_data.items() if v.get("is_active", True)]

    def get_all_groups_info(self) -> List[Dict]:
        return list(self.groups_data.values())

    def _default_user(self, uid: int) -> Dict:
        return {
            "user_id": uid,
            "name": "",
            "username": "",
            "chats": [],
            "relationship_level": 1,
            "stage": "initial",
            "last_interaction": datetime.utcnow().isoformat(),
            "voice_messages_sent": 0,
            "total_messages": 0,
            "mood": "happy",
            "nickname": "",
        }

    def get_user(self, user_id: int) -> Dict:
        uid = str(user_id)
        if self.use_local:
            if uid not in self.local_db:
                self.local_db[uid] = self._default_user(user_id)
                self._save_local()
            return self.local_db[uid]
        else:
            try:
                res = self.supabase.table("user_chats").select("*").eq("user_id", user_id).execute()
                data = getattr(res, "data", None) or (res.get("data") if isinstance(res, dict) else None)
                if data:
                    item = data[0] if isinstance(data, list) else data
                    if isinstance(item.get("chats"), str):
                        try:
                            item["chats"] = json.loads(item["chats"])
                        except:
                            item["chats"] = []
                    return item
                else:
                    new = self._default_user(user_id)
                    try:
                        to_insert = new.copy()
                        to_insert["chats"] = json.dumps(to_insert["chats"])
                        self.supabase.table("user_chats").insert(to_insert).execute()
                    except Exception:
                        pass
                    return new
            except Exception as e:
                logger.warning("Supabase get_user failed: %s, falling back to local", e)
                self.use_local = True
                return self.get_user(user_id)

    def save_user(self, user_id: int, user_data: Dict):
        uid = str(user_id)
        user_data["last_interaction"] = datetime.utcnow().isoformat()
        if self.use_local:
            self.local_db[uid] = user_data
            self._save_local()
        else:
            try:
                to_save = user_data.copy()
                if isinstance(to_save.get("chats"), list):
                    to_save["chats"] = json.dumps(to_save["chats"])
                # Upsert; on_conflict param may vary by client version
                try:
                    self.supabase.table("user_chats").upsert(to_save, on_conflict="user_id").execute()
                except TypeError:
                    # older/newer clients may not accept on_conflict kwarg
                    self.supabase.table("user_chats").upsert(to_save).execute()
            except Exception as e:
                logger.warning("Supabase save failed: %s — saving locally", e)
                self.use_local = True
                self.save_user(user_id, user_data)

    def add_message(self, user_id: int, user_msg: str, bot_msg: str, is_voice: bool = False):
        user = self.get_user(user_id)
        chats = user.get("chats") or []
        if not isinstance(chats, list):
            chats = []
        chats.append({
            "user": user_msg,
            "bot": bot_msg,
            "timestamp": datetime.utcnow().isoformat(),
            "is_voice": bool(is_voice),
        })
        user["chats"] = chats[-12:]
        user["total_messages"] = user.get("total_messages", 0) + 1
        if is_voice:
            user["voice_messages_sent"] = user.get("voice_messages_sent", 0) + 1
        user["relationship_level"] = min(10, user.get("relationship_level", 1) + 1)
        level = user["relationship_level"]
        user["stage"] = "initial" if level <= 3 else ("middle" if level <= 7 else "advanced")
        self.save_user(user_id, user)

    def update_user_info(self, user_id: int, name: str, username: str = ""):
        user = self.get_user(user_id)
        user["name"] = name or user.get("name", "")
        user["username"] = username or user.get("username", "")
        self.save_user(user_id, user)

    def get_context(self, user_id: int) -> str:
        user = self.get_user(user_id)
        nickname = user.get("nickname") or user.get("name") or "baby"
        ctx = [
            f"User's name: {user.get('name', 'Unknown')}",
            f"Nickname: {nickname}",
            f"Stage: {user.get('stage', 'initial')}",
            f"Level: {user.get('relationship_level', 1)}/10",
            f"Mood: {user.get('mood', 'happy')}",
        ]
        chats = user.get("chats", [])[-6:]
        if chats:
            ctx.append("Recent conv (last):")
            for c in chats[-3:]:
                ctx.append(f"User: {c.get('user','')}")
                ctx.append(f"You: {c.get('bot','')}")
        return "\n".join(ctx)

    def get_stats(self) -> Dict:
        active_groups = self.get_active_groups()
        if self.use_local:
            total_users = len(self.local_db)
            total_messages = sum(u.get("total_messages", 0) for u in self.local_db.values())
            total_voice = sum(u.get("voice_messages_sent", 0) for u in self.local_db.values())
            return {
                "total_users": total_users,
                "total_groups": len(active_groups),
                "total_messages": total_messages,
                "total_voice_messages": total_voice,
                "storage": "local",
            }
        else:
            try:
                res = self.supabase.table("user_chats").select("user_id", count="exact").execute()
                cnt = getattr(res, "count", 0) or 0
                return {"total_users": cnt, "total_groups": len(active_groups), "storage": "supabase"}
            except Exception:
                return {"total_users": 0, "total_groups": len(active_groups), "storage": "error"}

db = Database()

# ==================== AI ENGINE (VAPI Integration) ====================

class VapiAI:
    def __init__(self):
        self.api_key = Config.VAPI_API_KEY
        self.base_url = Config.VAPI_BASE_URL
        self.assistant_id = None
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.initialized = False
        
    async def initialize(self):
        """Initialize VAPI assistant - call this from async context"""
        if not self.api_key:
            logger.info("VAPI API key not provided — will use fallback responses")
            return
            
        try:
            # First try to list existing assistants
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/assistant",
                    headers=self.headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Check if we already have a Niyati assistant
                        assistants = data if isinstance(data, list) else data.get("assistants", [])
                        for assistant in assistants:
                            if assistant.get("name") == "Niyati":
                                self.assistant_id = assistant.get("id")
                                logger.info(f"Found existing VAPI assistant: {self.assistant_id}")
                                self.initialized = True
                                return
                
                # Create new assistant if not found
                await self._create_assistant()
                
        except Exception as e:
            logger.warning(f"VAPI initialization failed: {e}")
            self.initialized = False

    async def _create_assistant(self):
        """Create a new VAPI assistant with Niyati's personality"""
        try:
            assistant_config = {
                "name": "Niyati",
                "model": {
                    "provider": "openai",
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": PERSONALITY
                        }
                    ],
                    "temperature": 0.8,
                    "maxTokens": 250
                },
                "voice": {
                    "provider": "elevenlabs",
                    "voiceId": Config.ELEVENLABS_VOICE_ID if Config.ELEVENLABS_VOICE_ID else "21m00Tcm4TlvDq8ikWAM"
                },
                "firstMessage": "Heyy! I'm Niyati, kya chal raha hai? 💕",
                "firstMessageMode": "assistant-speaks-first"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/assistant",
                    headers=self.headers,
                    json=assistant_config,
                    timeout=30
                ) as resp:
                    if resp.status in [200, 201]:
                        data = await resp.json()
                        self.assistant_id = data.get("id")
                        self.initialized = True
                        logger.info(f"Created VAPI assistant: {self.assistant_id}")
                    else:
                        text = await resp.text()
                        logger.warning(f"Failed to create VAPI assistant: {resp.status} - {text}")
                        self.initialized = False
                        
        except Exception as e:
            logger.warning(f"Failed to create VAPI assistant: {e}")
            self.initialized = False

    async def generate(self, message: str, context: str = "", for_voice: bool = False) -> Optional[str]:
        """Generate response using VAPI assistant"""
        # VAPI is primarily for voice calls, not text chat
        # Using fallback responses instead
        return None

    def fallback_response(self, message: str, stage: str = "initial", name: str = "") -> str:
        """Fallback responses when VAPI is not available"""
        m = message.lower()
        
        # Extended fallback responses for better interaction
        if any(x in m for x in ["hi", "hello", "hey", "hii", "heyy"]):
            return random.choice(GENZ_GREETINGS)
        
        if any(x in m for x in ["love", "pyaar", "gf", "girlfriend", "cute", "beautiful", "pretty", "hot"]):
            return random.choice(GENZ_FLIRT)
        
        if any(x in m for x in ["she", "her", "girl", "ladki", "female", "woman"]):
            return random.choice(JEALOUS)
        
        if any(x in m for x in ["bot", "ai", "chatgpt", "gemini", "robot", "fake", "machine"]):
            return random.choice(AI_DENIAL)
        
        if any(x in m for x in ["miss", "yaad"]):
            return random.choice(["aww miss u too baby 🥺💕", "mujhe bhi tumhari yaad aa rhi thi 💖", "same yaar, kaha the tum? 😭"])
        
        if any(x in m for x in ["sad", "cry", "upset", "tension"]):
            return random.choice(["kya hua baby? tell me na 🥺", "don't be sad yaar, I'm here na 💕", "aww mere paas aao, sab theek ho jayega 🤗"])
        
        if any(x in m for x in ["good morning", "gm", "subah"]):
            return random.choice(["good morning sunshine! ☀️💕", "gm baby! aaj ka plan kya hai? ✨", "uth gaye finally? 😂 good morning!"])
        
        if any(x in m for x in ["good night", "gn", "sleep", "sone"]):
            return random.choice(["good night baby, sweet dreams 💕😴", "gn! kal baat karte hai 🌙", "soja abhi, health important hai! gn 💤"])
        
        if any(x in m for x in ["how are you", "kaise ho", "kaisi ho", "what's up", "wassup", "sup"]):
            moods = ["I'm good baby! tum batao? 💕", "theek hu yaar, missing u tho 🥺", "mast! aaj mood ekdum accha hai ✨"]
            return random.choice(moods)
        
        if any(x in m for x in ["bored", "bore"]):
            return random.choice(["same yaar! kuch fun karte hai? 🎮", "netflix and chill? 😏", "chalo kahi ghoomne chalte hai! 🚗"])
            
        if any(x in m for x in ["food", "khana", "hungry", "bhukh"]):
            return random.choice(["mujhe bhi bhook lagi hai! pizza order kare? 🍕", "momos khane chale? 😋", "ghar ka khana is the best tho 🍛"])
        
        if "?" in message:
            return random.choice([
                "umm lemme think... 🤔",
                "good question ngl 💭",
                "bruh idk... tumhe kya lagta hai? 😅",
                "yaar ye toh tough hai... 🙃",
                "arre confuse mat karo na 😵‍💫"
            ])
        
        # Stage-based responses
        if stage == "advanced":
            return random.choice([
                "baby tum kitne sweet ho yaar 💕",
                "accha suno na, something important batana hai...",
                "you know what? ur special fr 🥺",
                "bas karo, sharma rahi hu 🙈",
                "tumhare saath time spend karna best hai 💖"
            ])
        elif stage == "middle":
            return random.choice([
                "haan haan, aur batao 😊",
                "interesting... phir? 👀",
                "oh accha, nice nice 💫",
                "sahi hai yaar! 🙌",
                "tumhari baatein sunna accha lagta hai ✨"
            ])
        else:
            return random.choice([
                "hmm interesting... tell me more 👀",
                "achha? continue na 🙂",
                "okayy... and? 🤷‍♀️",
                "oh wow, sahi hai! ✨",
                "nice nice, aur batao na 😄"
            ])

ai = VapiAI()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    words = max(1, len(text.split()))
    base = min(4.0, 0.2 * words + 0.4)
    return base + random.uniform(0.2, 0.8)

def has_user_mention(message) -> bool:
    if not message or not hasattr(message, "entities"):
        return False
    for e in message.entities or []:
        if e.type in ["mention", "text_mention"]:
            return True
    return False

def should_reply_in_group() -> bool:
    return random.random() < 0.35

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    db.update_user_info(user.id, user.first_name or "", user.username or "")
    msg = (f"<b>heyy {user.first_name or 'baby'}! 👋✨</b>\n\n"
           "I'm <b>Niyati</b> - 17 y/o college girl from delhi 💅\n"
           "text me like a normal person yaar! i love making friends 🥰\n\n"
           "<i>lessgo bestie! 🚀</i>")
    await update.message.reply_text(msg, parse_mode="HTML")
    logger.info("User %s started the bot", user.id)

async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = None
    if context.args:
        text = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text
    if not text:
        await update.message.reply_text("Usage: /tts <text> or reply to a message with /tts")
        return
    if len(text) > 800:
        await update.message.reply_text("Text too long. Please keep under 800 chars.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)
    audio = await voice_engine.text_to_speech(text)
    if audio:
        await update.message.reply_voice(voice=audio, caption=(text[:120] + "...") if len(text) > 120 else text)
    else:
        await update.message.reply_text("TTS failed. Try again later.")

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        status = "Enabled" if (voice_engine.enabled and voice_engine.working) else ("Enabled (gTTS fallback)" if voice_engine.enabled else "Disabled (gTTS only)")
        await update.message.reply_text(f"Voice status: {status}\nUsage: /voice <text>")
        return
    text = " ".join(context.args)
    if len(text) > 400:
        await update.message.reply_text("Thoda short karo yaar — max 400 chars.")
        return
    endings = [" na", " yaar", " 💕", " hehe", " 😊", " ...", " hai na?"]
    final_text = text + random.choice(endings)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)
    audio = await voice_engine.text_to_speech(final_text)
    if audio:
        await update.message.reply_voice(voice=audio, caption="Niyati speaking ✨")
    else:
        await update.message.reply_text("Voice generation failed — try /tts or later.")

async def voice_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only command")
        return
    status = "Working" if voice_engine.working else ("Configured (not verified)" if voice_engine.enabled else "Disabled")
    vapi_status = "Initialized" if ai.initialized else "Not initialized"
    await update.message.reply_text(f"ElevenLabs: {status}\nVoice ID: {Config.ELEVENLABS_VOICE_ID}\nVAPI: {vapi_status}")

async def scan_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only")
        return
    await update.message.reply_text("Scanning recent updates to discover groups...")
    bot = context.bot
    discovered = 0
    errors = 0
    try:
        updates = await bot.get_updates(limit=200)
        seen = set()
        for u in updates:
            chat = getattr(u, "message", None) or getattr(u, "edited_message", None) or getattr(u, "channel_post", None)
            if not chat:
                continue
            c = chat.chat
            if c and c.type in ["group", "supergroup"] and c.id not in seen:
                seen.add(c.id)
                try:
                    info = await bot.get_chat(c.id)
                    db.add_group(c.id, info.title or "", info.username or "")
                    discovered += 1
                except (Forbidden, BadRequest):
                    db.remove_group(c.id)
                    errors += 1
                except Exception as e:
                    logger.debug("Group get_chat failed: %s", e)
                    errors += 1
        await update.message.reply_text(f"Scan complete. Discovered: {discovered}. Errors/removed: {errors}. Total groups: {len(db.get_active_groups())}")
    except Exception as e:
        logger.error("Scan groups failed: %s", e)
        await update.message.reply_text("Scan failed. Check logs.")

async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only")
        return
    groups = db.get_all_groups_info()
    active = [g for g in groups if g.get("is_active", True)]
    if not active:
        await update.message.reply_text("No active groups found.")
        return
    active.sort(key=lambda x: x.get("last_activity", ""), reverse=True)
    lines = [f"{i+1}. {g.get('title','Unknown')} (@{g.get('username','')}) [{g.get('messages_count',0)} msgs]" for i, g in enumerate(active[:50])]
    text = "<b>Active Groups</b>\n\n" + "\n".join(lines) + f"\n\nTotal: {len(active)}"
    await update.message.reply_text(text, parse_mode="HTML")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only")
        return
    groups = db.get_active_groups()
    if not groups:
        await update.message.reply_text("No groups to broadcast to. Run /scan first.")
        return
    src = update.message.reply_to_message
    text = " ".join(context.args) if context.args else (src.text if src and src.text else "")
    if not text and not src:
        await update.message.reply_text("Usage: /broadcast <text> OR reply to a message with /broadcast")
        return
    await update.message.reply_text(f"Broadcasting to {len(groups)} groups...")
    success = 0
    failed = 0
    for gid in groups:
        try:
            if src and src.photo:
                await context.bot.send_photo(gid, src.photo[-1].file_id, caption=src.caption)
            elif src and src.voice:
                await context.bot.send_voice(gid, src.voice.file_id, caption=src.caption)
            else:
                await context.bot.send_message(gid, text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.4)
        except (Forbidden, BadRequest):
            db.remove_group(gid)
            failed += 1
        except Exception as e:
            logger.debug("Broadcast to %s failed: %s", gid, e)
            failed += 1
    await update.message.reply_text(f"Broadcast complete. Success: {success}. Failed: {failed}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Only owner can see full stats")
        return
    stats = db.get_stats()
    user = db.get_user(user_id)
    msg = (f"<b>Bot Stats</b>\n\n"
           f"Users: {stats.get('total_users',0)}\n"
           f"Active Groups: {stats.get('total_groups',0)}\n"
           f"Total Messages: {stats.get('total_messages', stats.get('total_messages','N/A'))}\n"
           f"Voice Messages: {stats.get('total_voice_messages',0)}\n"
           f"Storage: {stats.get('storage','local')}\n"
           f"AI: {'VAPI' if ai.initialized else 'Fallback'}\n\n"
           f"<b>Your Stats</b>\n"
           f"Messages: {len(user.get('chats',[]))}\n"
           f"Relationship Level: {user.get('relationship_level',1)}/10\n"
           f"Stage: {user.get('stage','initial')}\n"
           f"Voice Sent: {user.get('voice_messages_sent',0)}")
    await update.message.reply_text(msg, parse_mode="HTML")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = datetime.utcnow()
    m = await update.message.reply_text("🏓 Pong!")
    end = datetime.utcnow()
    ms = (end - start).total_seconds() * 1000
    await m.edit_text(f"🏓 Pong! `{ms:.2f}ms`", parse_mode="Markdown")

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = db.get_user(uid)
    if not context.args:
        await update.message.reply_text(f"my current mood: {user.get('mood','happy')}\nChange: /mood [happy/sad/angry/flirty/excited]")
        return
    mood = context.args[0].lower()
    if mood not in ["happy", "sad", "angry", "flirty", "excited"]:
        await update.message.reply_text("Valid: happy, sad, angry, flirty, excited")
        return
    user["mood"] = mood
    db.save_user(uid, user)
    await update.message.reply_text(f"mood changed to {mood} ✅")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    is_owner = uid == Config.OWNER_USER_ID
    text = (
        "<b>Niyati Bot Commands</b>\n\n"
        "/start - start\n"
        "/help - this\n"
        "/ping - latency\n"
        "/mood - view/change mood\n"
        "/tts <text> - text to speech\n"
        "/voice <text> - voice from Niyati\n"
    )
    if is_owner:
        text += "/scan - discover groups\n/groups - list groups\n/broadcast - broadcast to groups\n/stats - stats\n"
    await update.message.reply_text(text, parse_mode="HTML")

# cooldowns
last_group_reply = defaultdict(lambda: datetime.min)
last_user_interaction = defaultdict(lambda: datetime.min)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text:
            return
        is_private = update.message.chat.type == "private"
        chat_id = update.effective_chat.id
        user = update.effective_user
        if not user:
            return
        user_id = user.id
        user_msg = update.message.text.strip()
        now = datetime.utcnow()

        if not is_private:
            chat = update.effective_chat
            db.add_group(chat_id, chat.title or "", chat.username or "")
            bot_username = (context.bot.username or "niyati").lower()
            is_mentioned = bot_username in user_msg.lower() or "niyati" in user_msg.lower()
            is_reply_to_bot = update.message.reply_to_message and (update.message.reply_to_message.from_user.id == context.bot.id)
            if not (is_mentioned or is_reply_to_bot):
                if (now - last_group_reply[chat_id]).total_seconds() < 25:
                    return
                if (now - last_user_interaction[f"{chat_id}_{user_id}"]).total_seconds() < 100:
                    return
                if has_user_mention(update.message):
                    return
                if not should_reply_in_group():
                    return
            last_group_reply[chat_id] = now
            last_user_interaction[f"{chat_id}_{user_id}"] = now

        if is_sleeping_time():
            await update.message.reply_text("yaar abhi so rahi hu... kal baat karte hai 😴")
            return

        if any(k in user_msg.lower() for k in ["bot", "ai", "chatgpt", "gemini", "robot"]):
            denial = random.choice(AI_DENIAL)
            await asyncio.sleep(calculate_typing_delay(denial))
            await update.message.reply_text(denial)
            db.add_message(user_id, user_msg, denial)
            return

        user_data = db.get_user(user_id)
        stage = user_data.get("stage", "initial")
        wants_voice = voice_engine.should_send_voice(user_msg, stage) and is_private

        ctx = db.get_context(user_id)
        ai_response = await ai.generate(user_msg, ctx, for_voice=wants_voice)

        if not ai_response:
            ai_response = ai.fallback_response(user_msg, stage, user_data.get("name", ""))

        if wants_voice:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio = await voice_engine.text_to_speech(ai_response)
            if audio:
                await update.message.reply_voice(voice=audio, caption=(ai_response[:120] + "...") if len(ai_response) > 120 else ai_response)
                db.add_message(user_id, user_msg, ai_response, is_voice=True)
            else:
                await asyncio.sleep(calculate_typing_delay(ai_response))
                await update.message.reply_text(ai_response)
                db.add_message(user_id, user_msg, ai_response)
        else:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(calculate_typing_delay(ai_response))
            await update.message.reply_text(ai_response)
            db.add_message(user_id, user_msg, ai_response)

        logger.info("Replied to %s (%s)", user_id, "private" if is_private else f"group {chat_id}")
    except Exception as e:
        logger.exception("Message handler error: %s", e)
        try:
            await update.message.reply_text("oop something went wrong... try again? 😅")
        except:
            pass

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    stats = db.get_stats()
    return jsonify({
        "bot": "Niyati",
        "version": "7.0",
        "status": "vibing",
        "users": stats.get("total_users", 0),
        "groups": stats.get("total_groups", 0),
        "storage": stats.get("storage", "local"),
        "ai": "VAPI" if ai.initialized else "Fallback"
    })

@flask_app.route("/health")
def health():
    return jsonify({"status": "healthy", "mood": "happy", "sleeping": is_sleeping_time()})

def run_flask():
    logger.info("Starting Flask server")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN BOT ====================

async def main():
    Config.validate()
    logger.info("Starting Niyati Bot v7.0 with VAPI")
    
    # Initialize async components
    await voice_engine.initialize()
    await ai.initialize()
    
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("scan", scan_groups_command))
    app.add_handler(CommandHandler("groups", groups_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("tts", tts_command))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("voicestatus", voice_status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.start()
    bot_info = await app.bot.get_me()
    logger.info("Bot started: @%s", bot_info.username or "unknown")

    try:
        updates = await app.bot.get_updates(limit=150)
        found = set()
        for u in updates:
            msg = getattr(u, "message", None) or getattr(u, "edited_message", None) or getattr(u, "channel_post", None)
            if not msg:
                continue
            chat = msg.chat
            if chat and chat.type in ("group", "supergroup") and chat.id not in found:
                found.add(chat.id)
                try:
                    info = await app.bot.get_chat(chat.id)
                    db.add_group(chat.id, info.title or "", info.username or "")
                except Exception:
                    pass
        logger.info("Initial group scan done: %d groups", len(db.get_active_groups()))
    except Exception as e:
        logger.debug("Initial scan failed: %s", e)

    logger.info("Polling for updates...")
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down (KeyboardInterrupt)")
    except Exception as e:
        logger.critical("Fatal error: %s", e)
        sys.exit(1)
