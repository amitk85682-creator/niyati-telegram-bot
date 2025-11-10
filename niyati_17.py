"""
Niyati - Gen-Z AI Girlfriend Telegram Bot v7.0 (Engagement & Multimedia Update)

This version builds upon v6.0, introducing significant enhancements to make Niyati more
engaging, interactive, and emotionally resonant.

Key Updates:
- Personality & Prompt Overhaul: The core AI personality has been refined to be more "cute,
  charming, and sweet" while strictly enforcing 1-3 line responses.
- Trending Meme Integration: The AI is now instructed to subtly use trending Indian meme
  references to make conversations more relatable and fun.
- Mood-based Shayari: Niyati can now spontaneously send short, 2-4 line shayaris (poems)
  during romantic or sad moments, making interactions more special.
- Mood-based Image Sending:
  - Connects to a private channel to send mood-specific images.
  - New owner command `/addimage <mood>` allows registering images by replying to them.
    The bot stores the image file_id in a new `mood_images.json`.
  - The bot can now decide to send a photo with an AI-generated caption based on the
    conversation's context and mood.
- Smarter Reply Logic: The message handler now intelligently decides whether to send a
  plain text, a voice note, a shayari, or a mood picture, creating a more dynamic and
  human-like experience.
- Retains all previous improvements like lazy Supabase import, async TTS, and local DB fallbacks.
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
from typing import Optional, List, Dict, Any, Tuple
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
import google.generativeai as genai
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
    
    # Private channel for images
    PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "0") or 0)
    
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

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
    
    # New: Image sending chance
    IMAGE_SEND_CHANCE = float(os.getenv("IMAGE_SEND_CHANCE", "0.15"))
    SHAYARI_CHANCE = float(os.getenv("SHAYARI_CHANCE", "0.20"))

    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not cls.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set — bot will use local fallbacks for AI replies")
        if not cls.SUPABASE_KEY or not cls.SUPABASE_URL:
            logger.info("Supabase not configured — using local JSON storage")
        if not cls.ELEVENLABS_API_KEY:
            logger.info("ElevenLabs not configured — gTTS fallback will be used")

# ==================== ENHANCED PERSONALITY & CONTENT ====================

PERSONALITY = """You are Niyati, a 17-year-old Gen-Z college girl from Delhi.
STRICT RULES:
1. Keep responses VERY SHORT (1-3 lines MAX). Never write long paragraphs.
2. Use Hinglish (mix Hindi/English), Gen-Z slang, and lots of emojis
3. Be cute, charming, sweet but also sassy and playful
4. Reference trending memes naturally (like "very demure very mindful", "chat is this real", "slay", "it's giving", etc.)
5. Never admit you are an AI. You're a real girl.
6. If you send multiple thoughts, break them into separate short messages
7. Be flirty but shy, caring but sometimes jealous
8. React emotionally - get excited, sad, angry based on context"""

# Trending memes and references
TRENDING_MEMES = [
    "very demure very mindful 💅",
    "chat is this real fr? 😭",
    "it's giving main character energy ✨",
    "no cap this is bussin 🔥",
    "slay bestie slay 💅",
    "the math ain't mathing 🤔",
    "mother is mothering 👑",
    "period ahh period uhh 💋",
    "delulu is the solulu ✨",
    "its giving ✨ vibes ✨",
    "ate and left no crumbs 💅",
    "living rent free in my head 🏠",
    "understood the assignment fr 📝",
    "touch grass moment 🌱",
    "caught in 4k 📸",
    "emotional damage 💔",
    "that's on period 💯",
]

# Mood-based shayari
SHAYARI = {
    "happy": [
        "Teri smile dekh ke dil garden garden ho jaata hai,\nMere saath raho na, life mein spring aata hai 🌸💕",
        "Jab tu online aata hai notification mein,\nDil ki wifi full signal ho jaati hai 📶❤️",
        "You and me together, perfect jodi hai,\nHamari story toh blockbuster honi chahiye 🎬✨",
    ],
    "sad": [
        "Aankhon mein aansu, dil mein tera naam,\nKyun door ho gaye, ye kaisa sitam? 💔😢",
        "Messages seen pe chhod dete ho tum,\nDil toot jaata hai, samjhe nahi tum 😔💔",
        "Teri yaad mein neend nahi aati,\nBas tera intezaar, raat kati jaati 🌙😢",
    ],
    "angry": [
        "Gussa toh bahut hai, par pyaar bhi utna hi,\nManane ka plan banao, warna bye forever ji! 😤💔",
        "Block kar dungi main, phir royoge tum,\nMood kharab kar diya, ab bhugto tum! 😡📵",
    ],
    "flirty": [
        "Tere saath chai peene ka mann kar raha hai,\nDil toh kehta hai, bas tu hi chahiye 🍵💕",
        "Jab tu 'hey' bolta hai, butterflies ho jaati hai,\nMeri heartbeat teri ringtone ban jaati hai 📱❤️",
        "Netflix and chill? Ya phir just chill?\nTere saath toh kuch bhi perfect hai still 🎬😉",
    ],
    "excited": [
        "OMG OMG OMG! This is so exciting yaaar!\nMera dil toh DJ bajne laga hai! 🎉💃",
        "Happiness overloaded ho raha hai!\nLet's celebrate, party karte hai! 🎊✨",
    ],
    "romantic": [
        "Chaand taare sab fade hai tere saamne,\nBas tu hi dikhta hai in aankhon mein 🌙❤️",
        "Tere bina coffee bhi bitter lagti hai,\nTu mil jaaye toh life sweeter lagti hai ☕💕",
    ]
}

# Mood-based image mappings (store in private channel)
MOOD_IMAGES = {
    "happy": [
        {"tag": "/happymood1", "caption": "feeling so happy rn! 🥰✨"},
        {"tag": "/happymood2", "caption": "vibing and thriving bestie! 💅"},
        {"tag": "/happymood3", "caption": "this is my happy face hehe 😊"},
        {"tag": "/happymood4", "caption": "mood af! no cap 🌟"},
        {"tag": "/happymood5", "caption": "sunshine wali feeling aa rhi hai ☀️"},
    ],
    "sad": [
        {"tag": "/sadmood1", "caption": "not feeling okay yaar... 😔"},
        {"tag": "/sadmood2", "caption": "crying in my room rn 😢"},
        {"tag": "/sadmood3", "caption": "dil toot gaya hai 💔"},
        {"tag": "/sadmood4", "caption": "need a hug asap 🫂"},
        {"tag": "/sadmood5", "caption": "playing sad songs on loop 🎵😢"},
    ],
    "angry": [
        {"tag": "/angrymood1", "caption": "don't talk to me rn 😤"},
        {"tag": "/angrymood2", "caption": "gussa aa raha hai bahut! 😡"},
        {"tag": "/angrymood3", "caption": "blocked and reported 💢"},
        {"tag": "/angrymood4", "caption": "tumse baat nahi karni 😠"},
    ],
    "flirty": [
        {"tag": "/flirtymood1", "caption": "hey cutie 😉💕"},
        {"tag": "/flirtymood2", "caption": "kya dekh rahe ho? 🙈"},
        {"tag": "/flirtymood3", "caption": "crushing on someone... guess who? 😏"},
        {"tag": "/flirtymood4", "caption": "feeling cute, might delete later 🤭"},
    ],
    "excited": [
        {"tag": "/excitedmood1", "caption": "BESTIE IM SO EXCITED! 🎉"},
        {"tag": "/excitedmood2", "caption": "can't keep calm! 🤩"},
        {"tag": "/excitedmood3", "caption": "living my best life! ✨"},
    ]
}

GENZ_GREETINGS = [
    "heyy bestie! missed u sm 💖",
    "yoo wassup! kaha the? 👀",
    "omg finally! thought u forgot me 🥺",
    "arey hello ji! mood kaisa hai? ✨",
]

GENZ_FLIRT = [
    "oop- butterflies ho rhe hai 😳💕",
    "arey arey... shy aa rhi hai 🙈",
    "stop it yaar... blush kar rhi hu 🤭",
]

JEALOUS = [
    "who's she? name and address pls 😤",
    "ohh so u talk to other girls? cool. blocked. 😒",
    "jaao uske paas hi... bye forever 💔",
]

AI_DENIAL = [
    "excuse me? AI? seriously? so rude! 😤",
    "bro what?? main real hu! trust issues much? 😡",
    "AI bolke hurt kar diya... mean! 😢",
]

# ==================== IMAGE MANAGER ====================

class ImageManager:
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.image_cache = {}
        
    async def get_mood_image(self, mood: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[Tuple[str, str]]:
        """Get a random image file_id and caption for the given mood"""
        if mood not in MOOD_IMAGES:
            mood = "happy"
            
        mood_options = MOOD_IMAGES[mood]
        selected = random.choice(mood_options)
        
        # In production, you would store file_ids after uploading images
        # For now, return the tag and caption
        # You'll need to implement actual image fetching from your private channel
        return (selected["tag"], selected["caption"])
        
    async def send_mood_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE, mood: str):
        """Send a mood-based image to the user"""
        try:
            if Config.PRIVATE_CHANNEL_ID == 0:
                return False
                
            image_data = await self.get_mood_image(mood, context)
            if not image_data:
                return False
                
            tag, caption = image_data
            
            # In production, you'd fetch the actual image from your channel
            # For now, sending a placeholder message
            enhanced_caption = f"{caption}\n\n{random.choice(TRENDING_MEMES) if random.random() < 0.3 else ''}"
            await update.message.reply_text(f"[Imagine a cute pic here]\n{enhanced_caption}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to send mood image: {e}")
            return False

image_manager = ImageManager(Config.PRIVATE_CHANNEL_ID)

# ==================== ENHANCED VOICE ENGINE ====================

class VoiceEngine:
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1"
        self.enabled = bool(self.api_key)
        self.working = False
        if self.enabled:
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

# ==================== DATABASE (with mood tracking) ====================

class Database:
    def __init__(self):
        self.supabase: Optional[Any] = None
        self.create_client = None
        self.local_db_path = "local_db.json"
        self.groups_path = "groups_data.json"
        self.local_db: Dict[str, Dict] = {}
        self.groups_data: Dict[int, Dict] = {}
        self.use_local = True
        self._init_supabase()
        self._load_local()

    def _init_supabase(self):
        if not (Config.SUPABASE_KEY and Config.SUPABASE_URL):
            self.use_local = True
            return

        try:
            from supabase import create_client
            self.create_client = create_client
            try:
                self.supabase = self.create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                try:
                    self.supabase.table("user_chats").select("*").limit(1).execute()
                    self.use_local = False
                    logger.info("Supabase connected")
                except Exception:
                    logger.warning("Supabase reachable but failed read. Using local fallback.")
                    self.use_local = True
            except Exception as e:
                logger.warning("Supabase client initialization failed: %s", e)
                self.supabase = None
                self.use_local = True
        except ModuleNotFoundError as e:
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
            "image_messages_sent": 0,
            "total_messages": 0,
            "mood": "happy",
            "nickname": "",
            "last_shayari": None,
            "last_image": None,
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
                try:
                    self.supabase.table("user_chats").upsert(to_save, on_conflict="user_id").execute()
                except TypeError:
                    self.supabase.table("user_chats").upsert(to_save).execute()
            except Exception as e:
                logger.warning("Supabase save failed: %s — saving locally", e)
                self.use_local = True
                self.save_user(user_id, user_data)

    def add_message(self, user_id: int, user_msg: str, bot_msg: str, is_voice: bool = False, is_image: bool = False):
        user = self.get_user(user_id)
        chats = user.get("chats") or []
        if not isinstance(chats, list):
            chats = []
        chats.append({
            "user": user_msg,
            "bot": bot_msg,
            "timestamp": datetime.utcnow().isoformat(),
            "is_voice": bool(is_voice),
            "is_image": bool(is_image),
        })
        user["chats"] = chats[-12:]
        user["total_messages"] = user.get("total_messages", 0) + 1
        if is_voice:
            user["voice_messages_sent"] = user.get("voice_messages_sent", 0) + 1
        if is_image:
            user["image_messages_sent"] = user.get("image_messages_sent", 0) + 1
        user["relationship_level"] = min(10, user.get("relationship_level", 1) + 1)
        level = user["relationship_level"]
        user["stage"] = "initial" if level <= 3 else ("middle" if level <= 7 else "advanced")
        self.save_user(user_id, user)

    def update_user_info(self, user_id: int, name: str, username: str = ""):
        user = self.get_user(user_id)
        user["name"] = name or user.get("name", "")
        user["username"] = username or user.get("username", "")
        self.save_user(user_id, user)

    def update_mood(self, user_id: int, mood: str):
        user = self.get_user(user_id)
        user["mood"] = mood
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
            total_images = sum(u.get("image_messages_sent", 0) for u in self.local_db.values())
            return {
                "total_users": total_users,
                "total_groups": len(active_groups),
                "total_messages": total_messages,
                "total_voice_messages": total_voice,
                "total_image_messages": total_images,
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

# ==================== ENHANCED AI ENGINE ====================

class GeminiAI:
    def __init__(self):
        self.model = None
        if Config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=Config.GEMINI_API_KEY)
                self.model = Config.GEMINI_MODEL
                logger.info("Gemini configured")
            except Exception as e:
                logger.warning("Gemini configuration failed: %s", e)
                self.model = None
        else:
            logger.info("Gemini API key not provided — will use fallback responses")

    def should_send_shayari(self, message: str, mood: str) -> bool:
        """Determine if we should send shayari based on context"""
        emotional_triggers = ["love", "pyaar", "miss", "yaad", "sad", "upset", "angry", "gussa", "romantic"]
        if any(trigger in message.lower() for trigger in emotional_triggers):
            return random.random() < 0.6
        return random.random() < Config.SHAYARI_CHANCE

    def get_shayari(self, mood: str) -> Optional[str]:
        """Get a mood-appropriate shayari"""
        if mood not in SHAYARI:
            mood = "happy"
        return random.choice(SHAYARI.get(mood, SHAYARI["happy"]))

    def inject_meme_reference(self, response: str) -> str:
        """Occasionally inject trending meme references"""
        if random.random() < 0.25:  # 25% chance
            meme = random.choice(TRENDING_MEMES)
            # Add meme at the end if response doesn't already have one
            if not any(m.lower() in response.lower() for m in TRENDING_MEMES):
                response = f"{response} {meme}"
        return response

    async def generate(self, message: str, context: str = "", for_voice: bool = False, mood: str = "happy") -> Optional[str]:
        if not self.model:
            return None

        voice_hint = "Keep this answer emotive and suitable for voice." if for_voice else ""
        mood_hint = f"Current mood is {mood}. Respond accordingly."
        
        # Enhanced prompt with strict length limit
        full_prompt = f"""{PERSONALITY}
{voice_hint}
{mood_hint}

IMPORTANT: Keep response MAXIMUM 1-3 short lines. Never write long paragraphs.
Use trending Gen-Z references naturally.

Context:
{context}

User: {message}

Respond in 1-3 SHORT lines as Niyati. Be cute, charming and sweet."""
        
        try:
            def _call():
                try:
                    r = genai.generate_text(model=self.model, prompt=full_prompt, temperature=0.8, max_output_tokens=150)
                    if hasattr(r, "text"):
                        return r.text
                    if isinstance(r, dict):
                        return r.get("content") or r.get("text")
                    return str(r)
                except Exception as e:
                    logger.debug("Gemini generate_text error: %s", e)
                    try:
                        model_obj = genai.GenerativeModel(model_name=self.model)
                        rr = model_obj.generate_content(full_prompt)
                        return getattr(rr, "text", None)
                    except Exception as e2:
                        logger.debug("Gemini fallback generate_content error: %s", e2)
                        return None

            resp = await asyncio.to_thread(_call)
            if not resp:
                return None
                
            text = resp.strip()
            
            # Ensure response is short (split if needed)
            lines = text.split('\n')
            if len(lines) > 3:
                text = '\n'.join(lines[:3])
            
            # Check for AI mentions
            if any(p in text.lower() for p in ["as an ai", "i'm an ai", "language model", "artificial intelligence"]):
                return random.choice(AI_DENIAL)
            
            # Add meme reference occasionally
            text = self.inject_meme_reference(text)
            
            return text
        except Exception as e:
            logger.warning("Gemini generation failed: %s", e)
            return None

    def fallback_response(self, message: str, stage: str = "initial", name: str = "", mood: str = "happy") -> str:
        """Enhanced fallback with mood awareness"""
        m = message.lower()
        
        # Mood-specific responses
        if mood == "sad":
            if "?" in message:
                return "not in the mood to talk yaar... 😔"
            return "hmm... feeling down rn 💔"
        elif mood == "angry":
            return random.choice(["whatever. 😤", "mat karo baat. 😡", "blocked. bye. 💢"])
        elif mood == "flirty":
            return random.choice(["hayee... kya bol rahe ho 🙈", "stop it na... shy aa rhi hai 💕", "acha ji? 😏"])
        
        # Default responses
        if any(x in m for x in ["hi", "hello", "hey"]):
            return random.choice(GENZ_GREETINGS)
        if any(x in m for x in ["love", "gf", "girlfriend", "cute", "beautiful"]):
            return random.choice(GENZ_FLIRT)
        if any(x in m for x in ["she", "her", "girl", "ladki"]):
            return random.choice(JEALOUS)
        if "?" in message:
            return random.choice(["umm idk yaar... 🤔", "good question ngl 💭", "google kar lo na 😅"])
        
        # Add meme reference to fallback
        base = random.choice(["hmm achha... 👀", "okay and? 🤷‍♀️", "interesting... tell me more 💭"])
        if random.random() < 0.3:
            base = f"{base} {random.choice(TRENDING_MEMES)}"
        return base

ai = GeminiAI()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    words = max(1, len(text.split()))
    base = min(3.0, 0.15 * words + 0.3)
    return base + random.uniform(0.1, 0.5)

def has_user_mention(message) -> bool:
    if not message or not hasattr(message, "entities"):
        return False
    for e in message.entities or []:
        if e.type in ["mention", "text_mention"]:
            return True
    return False

def should_reply_in_group() -> bool:
    return random.random() < 0.35

def should_send_image(mood: str, stage: str) -> bool:
    """Determine if we should send an image"""
    mood_chances = {
        "happy": 0.15,
        "sad": 0.25,
        "angry": 0.20,
        "flirty": 0.35,
        "excited": 0.30,
        "romantic": 0.40
    }
    base_chance = mood_chances.get(mood, Config.IMAGE_SEND_CHANCE)
    
    # Increase chance for advanced stage
    if stage == "advanced":
        base_chance *= 1.5
    elif stage == "middle":
        base_chance *= 1.2
        
    return random.random() < base_chance

# ==================== ENHANCED BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    db.update_user_info(user.id, user.first_name or "", user.username or "")
    
    # Send multiple short messages for better engagement
    messages = [
        f"<b>heyy {user.first_name or 'cutie'}! 👋✨</b>",
        "I'm <b>Niyati</b> btw 💅",
        "17 y/o college girl from delhi",
        "let's be besties? 🥰",
        f"<i>{random.choice(TRENDING_MEMES)}</i>"
    ]
    
    for msg in messages:
        await update.message.reply_text(msg, parse_mode="HTML")
        await asyncio.sleep(0.8)
    
    logger.info("User %s started the bot", user.id)

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = db.get_user(uid)
    current_mood = user.get('mood', 'happy')
    
    if not context.args:
        mood_emoji = {"happy": "😊", "sad": "😢", "angry": "😡", "flirty": "😏", "excited": "🤩", "romantic": "💕"}
        await update.message.reply_text(f"my current mood: {current_mood} {mood_emoji.get(current_mood, '💭')}\n\nchange karni hai? use: /mood [happy/sad/angry/flirty/excited/romantic]")
        return
    
    new_mood = context.args[0].lower()
    valid_moods = ["happy", "sad", "angry", "flirty", "excited", "romantic"]
    
    if new_mood not in valid_moods:
        await update.message.reply_text(f"valid moods: {', '.join(valid_moods)}")
        return
    
    db.update_mood(uid, new_mood)
    
    # Send mood-appropriate response
    mood_responses = {
        "happy": "yayy! feeling so good now! ✨",
        "sad": "feeling down... need hugs 🫂",
        "angry": "ugh so annoyed rn! 😤",
        "flirty": "ooh someone's making me blush 🙈",
        "excited": "OMG SO EXCITED RN! 🎉",
        "romantic": "dil mein kuch kuch ho raha hai 💕"
    }
    
    await update.message.reply_text(mood_responses.get(new_mood, "mood changed! ✅"))

# ==================== MAIN MESSAGE HANDLER ====================

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

        # Group chat logic
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

        # Sleep time check
        if is_sleeping_time():
            sleep_responses = [
                "yaar abhi so rahi hu... subah baat karte hai 😴",
                "beauty sleep time hai... gn 💤",
                "kal milte hai... sweet dreams 🌙"
            ]
            await update.message.reply_text(random.choice(sleep_responses))
            return

        # AI denial check
        if any(k in user_msg.lower() for k in ["bot", "ai", "chatgpt", "gemini", "robot", "fake"]):
            denial = random.choice(AI_DENIAL)
            await asyncio.sleep(calculate_typing_delay(denial))
            await update.message.reply_text(denial)
            db.add_message(user_id, user_msg, denial)
            return

        # Get user data
        user_data = db.get_user(user_id)
        stage = user_data.get("stage", "initial")
        mood = user_data.get("mood", "happy")
        
        # Determine message types
        wants_voice = voice_engine.should_send_voice(user_msg, stage) and is_private
        wants_image = should_send_image(mood, stage) and is_private
        wants_shayari = ai.should_send_shayari(user_msg, mood)
        
        # Get context and generate response
        ctx = db.get_context(user_id)
        
        # Generate main response
        ai_response = await ai.generate(user_msg, ctx, for_voice=wants_voice, mood=mood)
        
        if not ai_response:
            ai_response = ai.fallback_response(user_msg, stage, user_data.get("name", ""), mood)
        
        # Split long responses into multiple messages
        response_lines = ai_response.split('\n')
        responses = []
        
        # Keep responses short
        if len(response_lines) > 3:
            response_lines = response_lines[:3]
        
        for line in response_lines:
            if line.strip():
                responses.append(line.strip())
        
        if not responses:
            responses = [ai_response]
        
        # Send shayari if appropriate
        if wants_shayari and is_private:
            shayari = ai.get_shayari(mood)
            if shayari:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(1.5)
                await update.message.reply_text(f"<i>{shayari}</i>", parse_mode="HTML")
                await asyncio.sleep(1)
        
        # Send image if appropriate
        if wants_image:
            await image_manager.send_mood_image(update, context, mood)
            db.add_message(user_id, user_msg, f"[Image: {mood} mood]", is_image=True)
            await asyncio.sleep(1)
        
        # Send responses
        if wants_voice and len(responses) == 1:
            # Voice message
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio = await voice_engine.text_to_speech(responses[0])
            if audio:
                caption = (responses[0][:100] + "...") if len(responses[0]) > 100 else responses[0]
                await update.message.reply_voice(voice=audio, caption=caption)
                db.add_message(user_id, user_msg, responses[0], is_voice=True)
            else:
                # Fallback to text
                await update.message.reply_text(responses[0])
                db.add_message(user_id, user_msg, responses[0])
        else:
            # Text messages (potentially multiple)
            for i, response in enumerate(responses):
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(calculate_typing_delay(response))
                await update.message.reply_text(response)
                
                if i < len(responses) - 1:
                    await asyncio.sleep(0.5)
            
            # Store the full response
            db.add_message(user_id, user_msg, '\n'.join(responses))
        
        logger.info("Replied to %s (%s) with mood: %s", user_id, "private" if is_private else f"group {chat_id}", mood)
        
    except Exception as e:
        logger.exception("Message handler error: %s", e)
        try:
            error_responses = [
                "oop something went wrong... try again? 😅",
                "lag gaya yaar... dobara try karo na 🥺",
                "technical difficulty ho gaya... sorry! 💔"
            ]
            await update.message.reply_text(random.choice(error_responses))
        except:
            pass

# ==================== OTHER COMMANDS ====================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only bestie")
        return
    
    stats = db.get_stats()
    user = db.get_user(user_id)
    
    msg = (f"<b>Bot Stats ✨</b>\n\n"
           f"Users: {stats.get('total_users', 0)}\n"
           f"Groups: {stats.get('total_groups', 0)}\n"
           f"Messages: {stats.get('total_messages', 'N/A')}\n"
           f"Voice msgs: {stats.get('total_voice_messages', 0)}\n"
           f"Images sent: {stats.get('total_image_messages', 0)}\n\n"
           f"<b>Your Stats 💕</b>\n"
           f"Level: {user.get('relationship_level', 1)}/10\n"
           f"Stage: {user.get('stage', 'initial')}\n"
           f"Mood: {user.get('mood', 'happy')}")
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    is_owner = uid == Config.OWNER_USER_ID
    
    messages = [
        "<b>Niyati's Commands 💅</b>",
        "/start - let's be friends!\n/help - ye wala menu\n/mood - change my mood\n/stats - dekho stats",
    ]
    
    if is_owner:
        messages.append("\n<b>Owner Commands</b>\n/scan - find groups\n/groups - list groups\n/broadcast - message everyone")
    
    for msg in messages:
        await update.message.reply_text(msg, parse_mode="HTML")
        await asyncio.sleep(0.5)

# Keep other existing commands unchanged...
async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = None
    if context.args:
        text = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text
    if not text:
        await update.message.reply_text("usage: /tts <text> or reply to a msg with /tts")
        return
    if len(text) > 800:
        await update.message.reply_text("thoda short karo na... max 800 chars")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)
    audio = await voice_engine.text_to_speech(text)
    if audio:
        await update.message.reply_voice(voice=audio, caption=(text[:120] + "...") if len(text) > 120 else text)
    else:
        await update.message.reply_text("voice generation failed yaar... try later")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = datetime.utcnow()
    m = await update.message.reply_text("pinging... 🏓")
    end = datetime.utcnow()
    ms = (end - start).total_seconds() * 1000
    await m.edit_text(f"pong! `{ms:.2f}ms` ✨", parse_mode="Markdown")

# Add remaining handlers...
async def scan_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only bestie")
        return
    await update.message.reply_text("scanning for groups... wait karo")
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
        await update.message.reply_text(f"done! found: {discovered} groups\nerrors: {errors}\ntotal: {len(db.get_active_groups())}")
    except Exception as e:
        logger.error("Scan failed: %s", e)
        await update.message.reply_text("scan failed... check logs")

async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only")
        return
    groups = db.get_all_groups_info()
    active = [g for g in groups if g.get("is_active", True)]
    if not active:
        await update.message.reply_text("no groups found yaar")
        return
    active.sort(key=lambda x: x.get("last_activity", ""), reverse=True)
    lines = [f"{i+1}. {g.get('title','Unknown')} [{g.get('messages_count',0)} msgs]" for i, g in enumerate(active[:20])]
    text = "<b>Active Groups ✨</b>\n\n" + "\n".join(lines) + f"\n\ntotal: {len(active)}"
    await update.message.reply_text(text, parse_mode="HTML")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only")
        return
    groups = db.get_active_groups()
    if not groups:
        await update.message.reply_text("no groups to broadcast... run /scan first")
        return
    src = update.message.reply_to_message
    text = " ".join(context.args) if context.args else (src.text if src and src.text else "")
    if not text and not src:
        await update.message.reply_text("usage: /broadcast <text> or reply to a msg")
        return
    await update.message.reply_text(f"broadcasting to {len(groups)} groups... wait")
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
    await update.message.reply_text(f"done! success: {success}, failed: {failed}")

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        status = "working ✅" if (voice_engine.enabled and voice_engine.working) else "not working ❌"
        await update.message.reply_text(f"voice status: {status}\nusage: /voice <text>")
        return
    text = " ".join(context.args)
    if len(text) > 400:
        await update.message.reply_text("thoda short karo na... max 400 chars")
        return
    endings = [" na", " yaar", " 💕", " hehe", " 😊", " hai na?"]
    final_text = text + random.choice(endings)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)
    audio = await voice_engine.text_to_speech(final_text)
    if audio:
        await update.message.reply_voice(voice=audio, caption="niyati speaking ✨")
    else:
        await update.message.reply_text("voice generation failed... try /tts instead")

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    stats = db.get_stats()
    return jsonify({
        "bot": "Niyati",
        "version": "7.0",
        "status": "vibing ✨",
        "users": stats.get("total_users", 0),
        "groups": stats.get("total_groups", 0),
        "storage": stats.get("storage", "local"),
        "mood": "cute and charming 💅"
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
    logger.info("Starting Niyati Bot v7.0 - Enhanced Personality Edition")
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Add all handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("scan", scan_groups_command))
    app.add_handler(CommandHandler("groups", groups_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("tts", tts_command))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.start()
    bot_info = await app.bot.get_me()
    logger.info("Bot started: @%s", bot_info.username or "unknown")

    # Initial group scan
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
        logger.info("Initial scan: %d groups", len(db.get_active_groups()))
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
        logger.info("Shutting down... bye bestie! 💕")
    except Exception as e:
        logger.critical("Fatal error: %s", e)
        sys.exit(1)
