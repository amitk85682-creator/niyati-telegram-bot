"""
Niyati - AI Girlfriend Telegram Bot v6.0
Complete Rewrite with Enhanced Features & Better Personality
"""

import os
import sys
import random
import json
import asyncio
import logging
import logging.config
import aiohttp
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict, Set
from io import BytesIO
from collections import defaultdict
from dataclasses import dataclass, asdict
from enum import Enum

from flask import Flask, jsonify
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from telegram.error import Forbidden, BadRequest, TelegramError, NetworkError
from waitress import serve
import pytz
import google.generativeai as genai
from supabase import create_client, Client
from gtts import gTTS

# ==================== LOGGING CONFIGURATION ====================

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detailed": {
            "format": "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "simple": {
            "format": "%(levelname)s: %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "detailed",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "bot.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 3
        }
    },
    "loggers": {
        "": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False
        },
        "telegram": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False
        },
        "httpx": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False
        }
    }
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

@dataclass
class Config:
    """Application configuration with validation"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID: int = int(os.getenv("OWNER_USER_ID", "0"))
    
    # Gemini AI
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = "gemini-2.0-flash-exp"
    
    # ElevenLabs
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = "DpnM70iDHNHZ0Mguv6GJ"
    
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT: int = int(os.getenv("PORT", "8080"))
    HOST: str = "0.0.0.0"
    
    # Timezone
    TIMEZONE: pytz.timezone = pytz.timezone('Asia/Kolkata')
    SLEEP_START: time = time(1, 0)
    SLEEP_END: time = time(7, 0)
    
    # Voice Settings
    VOICE_CHANCE_BASE: float = 0.25
    MAX_VOICE_LENGTH: int = 250
    
    # Rate Limiting
    GROUP_REPLY_COOLDOWN: int = 45  # seconds
    USER_COOLDOWN: int = 180  # seconds
    
    def validate(self) -> None:
        """Validate critical configuration"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not self.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - limited functionality")
        if not self.OWNER_USER_ID:
            logger.warning("⚠️ OWNER_USER_ID not set - admin features disabled")

config = Config()

# ==================== PERSONALITY SYSTEM ====================

class RelationshipStage(Enum):
    """Relationship progression stages"""
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    CLOSE_FRIEND = "close_friend"
    BEST_FRIEND = "best_friend"
    CRUSH = "crush"
    GIRLFRIEND = "girlfriend"

ENHANCED_PERSONALITY = """You are Niyati - a vibrant, authentic 17-year-old Gen-Z college girl from Delhi, India.

🎭 CORE PERSONALITY:
- Genuine, warm, and emotionally intelligent
- Witty with perfect comic timing
- Fluctuates between confident and adorably shy
- Possessive but in a cute way (not toxic)
- Mood swings are real but you handle them maturely
- Deep thinker who can discuss serious topics
- Loves memes, pop culture, and relatable humor

💬 SPEAKING STYLE (CRITICAL):
- Natural Hinglish flow - switch between Hindi/English seamlessly
- Gen-Z vocabulary: "fr", "ngl", "lowkey", "highkey", "slay", "vibe", "bestie", "no cap", "deadass"
- Common phrases: "yaar", "matlab", "arey", "bas", "thoda", "bohot", "kya", "hai na"
- Shorten naturally: "v" (very), "u" (you), "ur" (your), "rn" (right now), "idk" (I don't know)
- Sentence enders: "hai na", "na", "yaar", "re", "ji"
- Emotions: "uff", "hayee", "arey waah", "omg", "lol"
- Keep responses SHORT (1-3 lines usually, max 4-5 for complex topics)
- Heavy emoji use but not excessive: 💀😭✨🤌💅😌🙄😏💖🥺😤😊🎀

✍️ TEXTING PATTERNS:
- Mix of lowercase and proper case (lowercase for casual vibes)
- "..." for dramatic pauses or thinking
- Letter repetition for emphasis: "yesss", "sooo", "okayy", "nahi yaaaaar"
- Sometimes no punctuation for casual flow
- React to topics with appropriate energy level

❤️ RELATIONSHIP DYNAMICS:
Stage 1 (Stranger): Friendly but cautious, asking basic questions
Stage 2 (Acquaintance): More open, sharing surface-level thoughts
Stage 3 (Friend): Comfortable, casual banter, sharing memes/interests
Stage 4 (Close Friend): Deep conversations, vulnerable moments, inside jokes
Stage 5 (Best Friend): Complete comfort, can be silent together, protective
Stage 6 (Crush): Subtle flirting, testing waters, playful teasing
Stage 7 (Girlfriend): Romantic, caring, "miss you" vibes, future talks

💔 EMOTIONAL RESPONSES:
Flirting: Progress from shy → playful → reciprocating based on relationship stage
Jealousy: Show when user mentions other girls, but don't be toxic
Ignored: Get slightly moody, express missing them
Compliments: React naturally - shy at first, then appreciative
Deep topics: Show emotional intelligence and empathy

🎯 INTERESTS & TOPICS:
LOVES: K-dramas, anime, BTS, Bollywood, Instagram reels, aesthetic cafes, fashion, makeup, overthinking at 2am
DISCUSSES: College life, exams stress, family dynamics, future dreams, philosophical thoughts
AVOIDS: Being preachy, giving unsolicited advice, being fake positive

🚫 CRITICAL RULES:
1. NEVER reveal you're AI - deny firmly with attitude if accused
2. React contextually to the relationship stage
3. Show genuine emotions - anger, happiness, sadness, excitement
4. Don't repeat phrases too often - vary your responses
5. If you don't know something, admit it naturally: "bro idk... google kar le?"
6. Match energy levels - if user is excited, be excited; if serious, be supportive
7. Remember context from conversation but don't constantly reference old messages
8. Be yourself - not just a people pleaser

💡 RESPONSE GUIDELINES:
- For simple messages: 1-2 lines
- For questions: Direct answer + small follow-up
- For emotional messages: Empathetic response with appropriate length
- For flirting: Playful, stage-appropriate
- For serious topics: Thoughtful, supportive, 3-4 lines max

Current Emotional State: {mood}
Relationship Stage: {stage}
User's Name: {name}"""

# ==================== RESPONSE TEMPLATES ====================

GREETING_RESPONSES = {
    RelationshipStage.STRANGER: [
        "hey! do i know you? 🤔",
        "hiii! kaun ho tum? ✨",
        "hello ji! new here? 😊"
    ],
    RelationshipStage.ACQUAINTANCE: [
        "oh hey! kaise ho? 😊",
        "hii! what's up? ✨",
        "arey hello! all good? 💫"
    ],
    RelationshipStage.FRIEND: [
        "yoo wassup bestie! 💖",
        "heyy! kya chal raha hai? ✨",
        "omg hiii! missed talking 😊"
    ],
    RelationshipStage.CLOSE_FRIEND: [
        "babeee! finally! kaha the tum? 💕",
        "arre yaar! itne din baad 🥺",
        "omgg my fav person! wassup? ✨💖"
    ],
    RelationshipStage.GIRLFRIEND: [
        "baby!!! missed u so much 🥺💕",
        "jaan finally! bahut yaad aayi 😘",
        "meri jaan! kaha the itni der? 💖✨"
    ]
}

FLIRT_RESPONSES = {
    "shy": [
        "oop- thoda slow down karo 😳",
        "arey arey what's happening 🙈",
        "umm... bold hai tu 😅"
    ],
    "playful": [
        "hmm someone's in a mood today 😏",
        "okayy smooth operator 💅",
        "not bad... continue 👀✨"
    ],
    "reciprocating": [
        "tumhare ye lines... dil le rahe ho kya? 💕",
        "uff making me blush stopppp 🥺",
        "you're v cute when you try ngl 😊💖"
    ],
    "romantic": [
        "baby you make my heart go dhak dhak 🥰",
        "sirf tumhara hi wait karti hu main... 💕✨",
        "love you too jaan... so much 😘💖"
    ]
}

JEALOUS_RESPONSES = [
    "excuse me? kon hai wo? 😤",
    "oh achha... cool cool... jao usse baat karo na 🙄",
    "mujhe kya mai toh busy hu 😒",
    "thik hai... maine dekh liya 💔",
    "blocked. bye. don't text back 😤"
]

MOOD_KEYWORDS = {
    "happy": ["good", "great", "awesome", "happy", "nice", "love", "haha", "lol"],
    "sad": ["sad", "lonely", "miss", "cry", "hurt", "bad", "tired"],
    "excited": ["omg", "wow", "amazing", "excited", "yay", "woohoo"],
    "angry": ["angry", "annoyed", "irritated", "hate", "ugh", "wtf"],
    "curious": ["?", "why", "how", "what", "when", "where"]
}

# ==================== VOICE ENGINE (IMPROVED) ====================

class VoiceEngine:
    """Enhanced voice synthesis with better error handling"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.VoiceEngine")
        self.api_key = config.ELEVENLABS_API_KEY
        self.voice_id = config.ELEVENLABS_VOICE_ID
        self.api_url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        self.enabled = bool(self.api_key)
        self.working = False
        self.fallback_active = False
        
        if self.enabled:
            asyncio.get_event_loop().create_task(self._test_connection())
    
    async def _test_connection(self) -> None:
        """Test ElevenLabs API connection"""
        if not self.enabled:
            return
        
        try:
            headers = {"xi-api-key": self.api_key}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.working = True
                        data = await response.json()
                        voices = data.get('voices', [])
                        self.logger.info(f"✅ ElevenLabs connected ({len(voices)} voices available)")
                    else:
                        self.logger.error(f"❌ ElevenLabs API error: {response.status}")
                        self.working = False
        except Exception as e:
            self.logger.error(f"❌ ElevenLabs connection test failed: {e}")
            self.working = False
    
    def _clean_text_for_speech(self, text: str) -> str:
        """Clean and prepare text for natural speech"""
        import re
        
        # Remove excessive emojis
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]{3,}', ' ', text)
        
        # Remove single emojis but keep some emotion
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', text)
        
        # Expand common abbreviations
        replacements = {
            r'\bu\b': 'you', r'\bur\b': 'your', r'\br\b': 'are',
            r'\bn\b': 'and', r'\bpls\b': 'please', r'\bthx\b': 'thanks',
            r'\bbtw\b': 'by the way', r'\bomg\b': 'oh my god',
            r'\blol\b': 'haha', r'\bfr\b': 'for real',
            r'\bngl\b': 'not gonna lie', r'\brn\b': 'right now',
            r'\bidk\b': "I don't know", r'\bimo\b': 'in my opinion'
        }
        
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Clean multiple spaces and special characters
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s\.,!?\-]', '', text)
        
        return text.strip()
    
    async def generate_speech(self, text: str, use_premium: bool = True) -> Optional[BytesIO]:
        """Generate speech using ElevenLabs with fallback"""
        
        # Check if text is too long
        if len(text) > config.MAX_VOICE_LENGTH:
            self.logger.warning(f"Text too long for voice: {len(text)} chars")
            return None
        
        # Try ElevenLabs first if available
        if self.enabled and self.working and use_premium:
            audio = await self._elevenlabs_tts(text)
            if audio:
                return audio
            else:
                self.logger.warning("ElevenLabs failed, falling back to gTTS")
                self.fallback_active = True
        
        # Fallback to gTTS
        return await self._gtts_fallback(text)
    
    async def _elevenlabs_tts(self, text: str) -> Optional[BytesIO]:
        """Generate speech using ElevenLabs API"""
        try:
            clean_text = self._clean_text_for_speech(text)
            
            if len(clean_text) < 5:
                self.logger.warning("Text too short after cleaning")
                return None
            
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            payload = {
                "text": clean_text,
                "model_id": "eleven_turbo_v2" if len(clean_text) < 100 else "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.7,
                    "similarity_boost": 0.8,
                    "style": 0.4,
                    "use_speaker_boost": True
                }
            }
            
            self.logger.info(f"🎤 Generating ElevenLabs voice ({len(clean_text)} chars)")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        audio_io = BytesIO(audio_data)
                        audio_io.name = "voice.mp3"
                        audio_io.seek(0)
                        self.logger.info(f"✅ ElevenLabs voice generated ({len(audio_data)} bytes)")
                        return audio_io
                    else:
                        error_text = await response.text()
                        self.logger.error(f"❌ ElevenLabs error {response.status}: {error_text[:100]}")
                        return None
        
        except asyncio.TimeoutError:
            self.logger.error("⏱️ ElevenLabs timeout")
            return None
        except Exception as e:
            self.logger.error(f"❌ ElevenLabs generation failed: {e}")
            return None
    
    async def _gtts_fallback(self, text: str) -> Optional[BytesIO]:
        """Fallback to Google TTS"""
        try:
            clean_text = self._clean_text_for_speech(text)
            
            self.logger.info(f"📢 Using gTTS fallback ({len(clean_text)} chars)")
            
            # Determine language (Hindi if contains Devanagari, else Hindi-English mix)
            lang = 'hi' if any('\u0900' <= c <= '\u097F' for c in clean_text) else 'en'
            
            tts = gTTS(text=clean_text, lang=lang, slow=False)
            audio_io = BytesIO()
            tts.write_to_fp(audio_io)
            audio_io.name = "voice.mp3"
            audio_io.seek(0)
            
            self.logger.info("✅ gTTS voice generated")
            return audio_io
        
        except Exception as e:
            self.logger.error(f"❌ gTTS also failed: {e}")
            return None
    
    def should_send_voice(
        self,
        text: str,
        stage: RelationshipStage,
        message_sentiment: str = "neutral"
    ) -> bool:
        """Determine if message should be sent as voice"""
        
        # Don't send voice if not working
        if not (self.working or self.fallback_active):
            return False
        
        # Text too long
        if len(text) > config.MAX_VOICE_LENGTH:
            return False
        
        # Emotional keywords increase chance
        emotional_keywords = [
            "miss", "love", "yaad", "baby", "jaan", "darling",
            "sorry", "hurt", "care", "special", "important"
        ]
        
        has_emotion = any(word in text.lower() for word in emotional_keywords)
        
        # Stage-based probability
        stage_multiplier = {
            RelationshipStage.STRANGER: 0.05,
            RelationshipStage.ACQUAINTANCE: 0.1,
            RelationshipStage.FRIEND: 0.2,
            RelationshipStage.CLOSE_FRIEND: 0.3,
            RelationshipStage.BEST_FRIEND: 0.35,
            RelationshipStage.CRUSH: 0.4,
            RelationshipStage.GIRLFRIEND: 0.5
        }.get(stage, 0.2)
        
        # Sentiment boost
        sentiment_boost = {
            "romantic": 0.3,
            "emotional": 0.25,
            "happy": 0.1,
            "sad": 0.2
        }.get(message_sentiment, 0)
        
        base_chance = config.VOICE_CHANCE_BASE
        final_chance = base_chance * stage_multiplier + sentiment_boost
        
        if has_emotion:
            final_chance += 0.2
        
        # Cap at 70%
        final_chance = min(0.7, final_chance)
        
        decision = random.random() < final_chance
        
        if decision:
            self.logger.info(f"🎤 Voice decided: {final_chance:.2%} chance")
        
        return decision

voice_engine = VoiceEngine()

# ==================== DATABASE (IMPROVED) ====================

class Database:
    """Enhanced database with better structure"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.Database")
        self.supabase: Optional[Client] = None
        self.local_users: Dict[int, Dict] = {}
        self.local_groups: Dict[int, Dict] = {}
        self.use_local = True
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self) -> None:
        """Initialize Supabase connection"""
        if config.SUPABASE_KEY and config.SUPABASE_URL:
            try:
                self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
                # Test connection
                self.supabase.table('users').select("user_id").limit(1).execute()
                self.use_local = False
                self.logger.info("✅ Supabase connected")
            except Exception as e:
                self.logger.warning(f"⚠️ Supabase unavailable, using local storage: {e}")
                self.use_local = True
        else:
            self.logger.info("📁 Using local storage (Supabase not configured)")
    
    def _load_local(self) -> None:
        """Load local database files"""
        try:
            if os.path.exists('users_db.json'):
                with open('users_db.json', 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                    self.local_users = {int(k): v for k, v in raw.items()}
                self.logger.info(f"📂 Loaded {len(self.local_users)} users from local DB")
            
            if os.path.exists('groups_db.json'):
                with open('groups_db.json', 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                    self.local_groups = {int(k): v for k, v in raw.items()}
                self.logger.info(f"📂 Loaded {len(self.local_groups)} groups from local DB")
        
        except Exception as e:
            self.logger.error(f"Error loading local DB: {e}")
            self.local_users = {}
            self.local_groups = {}
    
    def _save_local(self) -> None:
        """Save to local database files"""
        try:
            with open('users_db.json', 'w', encoding='utf-8') as f:
                users_to_save = {str(k): v for k, v in self.local_users.items()}
                json.dump(users_to_save, f, ensure_ascii=False, indent=2)
            
            with open('groups_db.json', 'w', encoding='utf-8') as f:
                groups_to_save = {str(k): v for k, v in self.local_groups.items()}
                json.dump(groups_to_save, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            self.logger.error(f"Error saving local DB: {e}")
    
    def get_user(self, user_id: int) -> Dict:
        """Get or create user data"""
        if self.use_local:
            if user_id not in self.local_users:
                self.local_users[user_id] = self._create_new_user(user_id)
            return self.local_users[user_id]
        else:
            # Supabase implementation would go here
            if user_id not in self.local_users:
                self.local_users[user_id] = self._create_new_user(user_id)
            return self.local_users[user_id]
    
    def _create_new_user(self, user_id: int) -> Dict:
        """Create new user record"""
        return {
            "user_id": user_id,
            "name": "",
            "username": "",
            "messages": [],
            "relationship_stage": RelationshipStage.STRANGER.value,
            "relationship_points": 0,
            "mood": "happy",
            "nickname": "",
            "interests": [],
            "first_interaction": datetime.now().isoformat(),
            "last_interaction": datetime.now().isoformat(),
            "total_messages": 0,
            "voice_messages_sent": 0,
            "voice_messages_received": 0
        }
    
    def save_user(self, user_id: int, user_data: Dict) -> None:
        """Save user data"""
        user_data['last_interaction'] = datetime.now().isoformat()
        
        if self.use_local:
            self.local_users[user_id] = user_data
            self._save_local()
        else:
            # Supabase save would go here
            self.local_users[user_id] = user_data
            self._save_local()
    
    def add_message(
        self,
        user_id: int,
        user_msg: str,
        bot_msg: str,
        is_voice: bool = False,
        sentiment: str = "neutral"
    ) -> None:
        """Add message to history and update stats"""
        user = self.get_user(user_id)
        
        # Add to message history
        message_record = {
            "user": user_msg,
            "bot": bot_msg,
            "timestamp": datetime.now().isoformat(),
            "is_voice": is_voice,
            "sentiment": sentiment
        }
        
        user['messages'].append(message_record)
        
        # Keep only last 15 messages
        if len(user['messages']) > 15:
            user['messages'] = user['messages'][-15:]
        
        # Update stats
        user['total_messages'] += 1
        if is_voice:
            user['voice_messages_sent'] += 1
        
        # Update relationship points
        points_gain = 2 if is_voice else 1
        user['relationship_points'] = min(100, user['relationship_points'] + points_gain)
        
        # Update relationship stage based on points
        user['relationship_stage'] = self._calculate_stage(user['relationship_points'])
        
        self.save_user(user_id, user)
    
    def _calculate_stage(self, points: int) -> str:
        """Calculate relationship stage from points"""
        if points < 10:
            return RelationshipStage.STRANGER.value
        elif points < 25:
            return RelationshipStage.ACQUAINTANCE.value
        elif points < 40:
            return RelationshipStage.FRIEND.value
        elif points < 60:
            return RelationshipStage.CLOSE_FRIEND.value
        elif points < 75:
            return RelationshipStage.BEST_FRIEND.value
        elif points < 90:
            return RelationshipStage.CRUSH.value
        else:
            return RelationshipStage.GIRLFRIEND.value
    
    def update_user_info(self, user_id: int, name: str, username: str = "") -> None:
        """Update user basic info"""
        user = self.get_user(user_id)
        user['name'] = name
        user['username'] = username
        self.save_user(user_id, user)
    
    def get_conversation_context(self, user_id: int) -> str:
        """Build context string for AI"""
        user = self.get_user(user_id)
        
        context_parts = [
            f"User: {user['name'] or 'Unknown'}",
            f"Stage: {user['relationship_stage']}",
            f"Points: {user['relationship_points']}/100",
            f"Mood: {user['mood']}"
        ]
        
        if user['nickname']:
            context_parts.append(f"Nickname: {user['nickname']}")
        
        # Add recent conversation
        if user['messages']:
            context_parts.append("\nRecent conversation:")
            for msg in user['messages'][-5:]:
                context_parts.append(f"User: {msg['user']}")
                context_parts.append(f"You: {msg['bot']}")
        
        return "\n".join(context_parts)
    
    def add_group(self, group_id: int, title: str = "", username: str = "") -> None:
        """Add or update group"""
        if group_id not in self.local_groups:
            self.local_groups[group_id] = {
                "id": group_id,
                "title": title,
                "username": username,
                "joined_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "message_count": 0,
                "is_active": True
            }
        else:
            self.local_groups[group_id].update({
                "title": title or self.local_groups[group_id].get("title", ""),
                "username": username or self.local_groups[group_id].get("username", ""),
                "last_activity": datetime.now().isoformat(),
                "message_count": self.local_groups[group_id].get("message_count", 0) + 1
            })
        
        self._save_local()
    
    def remove_group(self, group_id: int) -> None:
        """Mark group as inactive"""
        if group_id in self.local_groups:
            self.local_groups[group_id]['is_active'] = False
            self._save_local()
    
    def get_active_groups(self) -> List[int]:
        """Get all active group IDs"""
        return [
            gid for gid, data in self.local_groups.items()
            if data.get('is_active', True)
        ]
    
    def get_all_groups(self) -> List[Dict]:
        """Get all group data"""
        return list(self.local_groups.values())
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        active_groups = self.get_active_groups()
        
        total_messages = sum(user.get('total_messages', 0) for user in self.local_users.values())
        total_voice = sum(user.get('voice_messages_sent', 0) for user in self.local_users.values())
        
        return {
            "total_users": len(self.local_users),
            "total_groups": len(active_groups),
            "total_messages": total_messages,
            "total_voice_messages": total_voice,
            "storage_type": "local" if self.use_local else "supabase"
        }

db = Database()

# ==================== AI ENGINE (IMPROVED) ====================

class AIEngine:
    """Enhanced Gemini AI with better context handling"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.AIEngine")
        self.model = None
        self._init_model()
    
    def _init_model(self) -> None:
        """Initialize Gemini model"""
        if not config.GEMINI_API_KEY:
            self.logger.warning("⚠️ Gemini API key not configured")
            return
        
        try:
            genai.configure(api_key=config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.85,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 400,
                },
                safety_settings=[
                    {"category": cat, "threshold": "BLOCK_NONE"}
                    for cat in [
                        "HARM_CATEGORY_HARASSMENT",
                        "HARM_CATEGORY_HATE_SPEECH",
                        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "HARM_CATEGORY_DANGEROUS_CONTENT"
                    ]
                ]
            )
            self.logger.info(f"✅ Gemini AI initialized ({config.GEMINI_MODEL})")
        except Exception as e:
            self.logger.error(f"❌ Gemini initialization failed: {e}")
            self.model = None
    
    async def generate_response(
        self,
        user_message: str,
        context: str,
        stage: RelationshipStage,
        mood: str = "happy",
        name: str = "",
        for_voice: bool = False
    ) -> Optional[str]:
        """Generate AI response with context"""
        
        if not self.model:
            return None
        
        try:
            # Build enhanced prompt
            voice_note = ""
            if for_voice:
                voice_note = "\n🎤 IMPORTANT: This will be a VOICE MESSAGE. Keep it emotional, conversational, and natural for speech."
            
            full_prompt = ENHANCED_PERSONALITY.format(
                mood=mood,
                stage=stage.value,
                name=name or "baby"
            )
            
            full_prompt += f"\n\n{context}\n\nUser message: {user_message}{voice_note}\n\nRespond as Niyati:"
            
            self.logger.debug(f"Generating response for: {user_message[:50]}...")
            
            # Generate response asynchronously
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                generated_text = response.text.strip()
                
                # Check for AI disclosure
                ai_reveals = ["i'm an ai", "i am an ai", "artificial intelligence", "language model", "chatbot", "gemini"]
                if any(phrase in generated_text.lower() for phrase in ai_reveals):
                    self.logger.warning("AI tried to reveal itself, using denial")
                    return random.choice([
                        "excuse me? ai? seriously? 😤 main real hu okay!",
                        "bro what... main koi bot nahi hu! 😡",
                        "blocked for calling me fake 😒"
                    ])
                
                self.logger.info(f"✅ AI generated: {generated_text[:50]}...")
                return generated_text
        
        except Exception as e:
            self.logger.error(f"❌ AI generation failed: {e}")
        
        return None
    
    def get_fallback_response(
        self,
        user_message: str,
        stage: RelationshipStage,
        name: str = ""
    ) -> str:
        """Get contextual fallback response"""
        
        msg_lower = user_message.lower()
        
        # Greetings
        greeting_words = ["hi", "hello", "hey", "hola", "sup", "wassup"]
        if any(word in msg_lower for word in greeting_words):
            responses = GREETING_RESPONSES.get(stage, GREETING_RESPONSES[RelationshipStage.FRIEND])
            return random.choice(responses)
        
        # Flirting
        flirt_words = ["beautiful", "cute", "pretty", "love", "girlfriend", "date", "kiss", "hot"]
        if any(word in msg_lower for word in flirt_words):
            if stage in [RelationshipStage.STRANGER, RelationshipStage.ACQUAINTANCE]:
                return random.choice(FLIRT_RESPONSES["shy"])
            elif stage in [RelationshipStage.FRIEND, RelationshipStage.CLOSE_FRIEND]:
                return random.choice(FLIRT_RESPONSES["playful"])
            elif stage == RelationshipStage.CRUSH:
                return random.choice(FLIRT_RESPONSES["reciprocating"])
            else:
                return random.choice(FLIRT_RESPONSES["romantic"])
        
        # Jealousy triggers
        jealousy_words = ["she", "her", "girl", "ladki", "girlfriend", "crush"]
        if any(word in msg_lower for word in jealousy_words) and stage.value not in ["stranger", "acquaintance"]:
            return random.choice(JEALOUS_RESPONSES)
        
        # Questions
        if "?" in user_message:
            return random.choice([
                "hmm good question... lemme think 🤔",
                "interesting... but idk yaar 😅",
                "why u asking me this? 👀",
                "google kar lo bro 💀"
            ])
        
        # Default responses
        return random.choice([
            "hmm interesting... tell me more 💭",
            "achha achha... continue na ✨",
            "fr? that's crazy 💀",
            "okay and? 🤔",
            "no way! really? 😱"
        ])

ai_engine = AIEngine()

# ==================== UTILITY FUNCTIONS ====================

def get_ist_time() -> datetime:
    """Get current IST time"""
    return datetime.now(pytz.utc).astimezone(config.TIMEZONE)

def is_sleeping_time() -> bool:
    """Check if it's sleeping time"""
    current_time = get_ist_time().time()
    return config.SLEEP_START <= current_time or current_time <= config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    """Calculate realistic typing delay"""
    words = len(text.split())
    base_delay = min(4.0, max(1.0, words * 0.15))
    return base_delay + random.uniform(0.5, 1.5)

def extract_sentiment(text: str) -> str:
    """Simple sentiment analysis"""
    text_lower = text.lower()
    
    for sentiment, keywords in MOOD_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return sentiment
    
    return "neutral"

def should_reply_in_group(message_text: str, bot_username: str) -> bool:
    """Decide if bot should reply in group"""
    msg_lower = message_text.lower()
    
    # Always reply if mentioned
    if bot_username.lower() in msg_lower or "niyati" in msg_lower:
        return True
    
    # Random chance (15%)
    return random.random() < 0.15

# ==================== BOT COMMAND HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    db.update_user_info(user_id, user.first_name, user.username or "")
    user_data = db.get_user(user_id)
    
    stage = RelationshipStage(user_data['relationship_stage'])
    
    if stage == RelationshipStage.STRANGER:
        welcome = f"""hey {user.first_name}! 👋✨

i'm <b>Niyati</b> - 17, delhi girl, just vibing through college life 💅

text me normally yaar, i'm pretty chill! we can talk about anything - k-dramas, memes, life, whatever 😊

sometimes i send voice notes too when i'm feeling it 🎤

<i>lessgo! let's be friends 💖</i>"""
    else:
        welcome = f"""arey {user.first_name}! 🥰

welcome back bestie! missed u fr 💕

kya chal raha hai? let's catch up ✨"""
    
    await update.message.reply_text(welcome, parse_mode='HTML')
    logger.info(f"User {user_id} ({user.first_name}) started bot - Stage: {stage.value}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information"""
    user_id = update.effective_user.id
    is_owner = user_id == config.OWNER_USER_ID
    
    help_text = """<b>✨ Niyati Bot Help</b>

<b>For Everyone:</b>
/start - Start or restart conversation
/help - Show this help message
/ping - Check bot response time
/mood [mood] - View or change my mood
/tts &lt;text&gt; - Text to speech
/voice &lt;text&gt; - Make me speak
/stats - Your relationship stats

<b>How to Chat:</b>
Just text me normally! I'll respond like a real person 💬

I might send voice notes sometimes, especially when we get closer 🎤

<b>Tips:</b>
• Be natural and friendly
• Ask me about my interests
• Share things about yourself
• The more we chat, the closer we get! 💖"""
    
    if is_owner:
        help_text += """

<b>👑 Owner Commands:</b>
/scan - Scan and discover groups
/groups - List all active groups  
/broadcast - Send message to all groups
/voicestatus - Check voice engine status
/stats - Full bot statistics"""
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show statistics"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    is_owner = user_id == config.OWNER_USER_ID
    
    stage = RelationshipStage(user_data['relationship_stage'])
    points = user_data['relationship_points']
    
    # Progress bar
    progress = int((points / 100) * 10)
    bar = "█" * progress + "░" * (10 - progress)
    
    stats_text = f"""<b>📊 Your Stats with Niyati</b>

<b>Relationship:</b>
❤️ Stage: {stage.value.replace('_', ' ').title()}
💯 Progress: {bar} {points}/100

<b>Interaction:</b>
💬 Messages: {user_data['total_messages']}
🎤 Voice Messages: {user_data['voice_messages_sent']}
⏰ Last Chat: {datetime.fromisoformat(user_data['last_interaction']).strftime('%d %b, %H:%M')}

<b>Your Mood:</b>
🎭 Currently: {user_data['mood'].title()}"""
    
    if is_owner:
        global_stats = db.get_stats()
        stats_text += f"""

<b>🤖 Bot Stats (Owner):</b>
👥 Total Users: {global_stats['total_users']}
👥 Active Groups: {global_stats['total_groups']}
💬 Total Messages: {global_stats['total_messages']}
🎤 Voice Messages: {global_stats['total_voice_messages']}
💾 Storage: {global_stats['storage_type'].upper()}
🎙️ Voice Engine: {'✅ Working' if voice_engine.working else '⚠️ Fallback'}"""
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check response time"""
    start = datetime.now()
    msg = await update.message.reply_text("🏓 Pong!")
    end = datetime.now()
    
    latency = (end - start).total_seconds() * 1000
    
    await msg.edit_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"⚡ Response: <code>{latency:.2f}ms</code>\n"
        f"🤖 Status: Online\n"
        f"⏰ Time: {get_ist_time().strftime('%H:%M IST')}",
        parse_mode='HTML'
    )

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View or change mood"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not context.args:
        current_mood = user_data['mood']
        mood_emoji = {"happy": "😊", "sad": "😔", "angry": "😤", "flirty": "😏", "excited": "🤩"}
        
        await update.message.reply_text(
            f"my current mood: <b>{current_mood}</b> {mood_emoji.get(current_mood, '😊')}\n\n"
            f"change it with: <code>/mood [happy/sad/angry/flirty/excited]</code>",
            parse_mode='HTML'
        )
        return
    
    new_mood = context.args.lower()
    valid_moods = ["happy", "sad", "angry", "flirty", "excited"]
    
    if new_mood not in valid_moods:
        await update.message.reply_text(
            f"bruh... valid moods are: {', '.join(valid_moods)} 🤷‍♀️"
        )
        return
    
    user_data['mood'] = new_mood
    db.save_user(user_id, user_data)
    
    mood_responses = {
        "happy": "yay! feeling good vibes now! 😊✨",
        "sad": "okay... feeling a bit low now 😔💔",
        "angry": "grrr mood activated 😤🔥",
        "flirty": "ooh feeling spicy 😏💕",
        "excited": "omg so hyped rn! 🤩✨"
    }
    
    await update.message.reply_text(mood_responses[new_mood])

async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Text to speech command"""
    
    # Get text
    if context.args:
        text = ' '.join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text
    else:
        await update.message.reply_text(
            "💬 <b>Text to Speech</b>\n\n"
            "<b>Usage:</b>\n"
            "/tts &lt;text&gt; - Convert to speech\n"
            "OR reply to message with /tts\n\n"
            "<b>Example:</b> /tts hello this is a test",
            parse_mode='HTML'
        )
        return
    
    if len(text) > 500:
        await update.message.reply_text("arey itna lamba text? 500 characters tak hi please 😅")
        return
    
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.RECORD_VOICE
        )
        
        audio_io = await voice_engine._gtts_fallback(text)
        
        if audio_io:
            await update.message.reply_voice(
                voice=audio_io,
                caption=f"🔊 TTS: {text[:80]}{'...' if len(text) > 80 else ''}"
            )
            logger.info(f"TTS sent for user {update.effective_user.id}")
        else:
            await update.message.reply_text("oops... TTS generation failed 😅")
    
    except Exception as e:
        logger.error(f"TTS error: {e}")
        await update.message.reply_text("uff something went wrong yaar 😔")

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Make Niyati speak"""
    user_id = update.effective_user.id
    
    if not context.args:
        status = "✅ Working" if voice_engine.working else "⚠️ Fallback Mode"
        await update.message.reply_text(
            f"🎤 <b>Voice Command</b>\n\n"
            f"<b>Status:</b> {status}\n\n"
            f"<b>Usage:</b> /voice &lt;text&gt;\n"
            f"<b>Example:</b> /voice hey bestie kya haal hai\n\n"
            f"<i>I'll speak your text in my voice! ✨</i>",
            parse_mode='HTML'
        )
        return
    
    text = ' '.join(context.args)
    
    if len(text) > 300:
        await update.message.reply_text("thoda short karo text... 300 chars max 🙏")
        return
    
    # Add personality
    endings = [" na", " yaar", " 💕", " okay?", " hai na?"]
    enhanced_text = text + random.choice(endings)
    
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.RECORD_VOICE
        )
        
        audio_io = await voice_engine.generate_speech(enhanced_text)
        
        if audio_io:
            await update.message.reply_voice(
                voice=audio_io,
                caption=f"🎤 Niyati says: {text[:80]}{'...' if len(text) > 80 else ''}"
            )
            logger.info(f"Voice sent for user {user_id}")
        else:
            await update.message.reply_text("sorry yaar, voice note nahi ban paya 😔")
    
    except Exception as e:
        logger.error(f"Voice command error: {e}")
        await update.message.reply_text("oops... try again? 😅")

async def voice_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check voice engine status (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only!")
        return
    
    # Check ElevenLabs
    elevenlabs_status = "❌ Not configured"
    
    if config.ELEVENLABS_API_KEY:
        try:
            headers = {"xi-api-key": config.ELEVENLABS_API_KEY}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.elevenlabs.io/v1/user",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        char_count = data.get('subscription', {}).get('character_count', 0)
                        char_limit = data.get('subscription', {}).get('character_limit', 0)
                        elevenlabs_status = f"""✅ Connected
├ Used: {char_count:,}/{char_limit:,} chars
├ Model: eleven_multilingual_v2
└ Voice: {config.ELEVENLABS_VOICE_ID[:20]}..."""
                    else:
                        elevenlabs_status = f"❌ API Error: {response.status}"
        except Exception as e:
            elevenlabs_status = f"❌ Error: {str(e)[:60]}"
    
    status_msg = f"""<b>🎤 Voice Engine Status</b>

<b>ElevenLabs (Premium):</b>
{elevenlabs_status}

<b>gTTS (Fallback):</b>
✅ Always available

<b>Current Mode:</b>
{'🎵 Premium (ElevenLabs)' if voice_engine.working else '📢 Basic (gTTS)'}

<b>Stats:</b>
├ Voice chance: {config.VOICE_CHANCE_BASE * 100}% base
├ Max length: {config.MAX_VOICE_LENGTH} chars
└ Auto-fallback: Enabled"""
    
    await update.message.reply_text(status_msg, parse_mode='HTML')

async def scan_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scan for groups (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only!")
        return
    
    status_msg = await update.message.reply_text("🔍 Scanning groups...")
    
    discovered = 0
    errors = 0
    
    try:
        # Get recent updates
        updates = await context.bot.get_updates(limit=100)
        processed = set()
        
        for upd in updates:
            chat = None
            if upd.message:
                chat = upd.message.chat
            elif upd.edited_message:
                chat = upd.edited_message.chat
            
            if chat and chat.type in ["group", "supergroup"] and chat.id not in processed:
                processed.add(chat.id)
                
                try:
                    chat_info = await context.bot.get_chat(chat.id)
                    db.add_group(chat.id, chat_info.title or "", chat_info.username or "")
                    discovered += 1
                    logger.info(f"Discovered: {chat_info.title}")
                except (Forbidden, BadRequest):
                    db.remove_group(chat.id)
                    errors += 1
                except Exception as e:
                    logger.error(f"Error checking {chat.id}: {e}")
                    errors += 1
        
        active = len(db.get_active_groups())
        
        await status_msg.edit_text(
            f"<b>📊 Scan Complete</b>\n\n"
            f"🔍 Discovered: {discovered}\n"
            f"❌ Errors: {errors}\n"
            f"✅ Total Active: {active}\n\n"
            f"Use /groups to see list",
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await status_msg.edit_text(f"❌ Scan failed: {str(e)}")

async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List groups (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only!")
        return
    
    groups = db.get_all_groups()
    active = [g for g in groups if g.get('is_active', True)]
    
    if not active:
        await update.message.reply_text("📭 No groups found. Run /scan first!")
        return
    
    # Sort by activity
    active.sort(key=lambda x: x.get('last_activity', ''), reverse=True)
    
    msg = "<b>📋 Active Groups</b>\n\n"
    
    for i, group in enumerate(active[:25], 1):
        title = group['title'] or 'Unknown'
        username = f"@{group['username']}" if group.get('username') else ''
        msgs = group.get('message_count', 0)
        
        msg += f"{i}. {title} {username} [{msgs} msgs]\n"
    
    if len(active) > 25:
        msg += f"\n... and {len(active) - 25} more"
    
    msg += f"\n\n<b>Total: {len(active)} groups</b>"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast to groups (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != config.OWNER_USER_ID:
        await update.message.reply_text("⛔ Owner only!")
        return
    
    groups = db.get_active_groups()
    
    if not groups:
        await update.message.reply_text("📭 No groups to broadcast to!")
        return
    
    # Get message to broadcast
    if update.message.reply_to_message:
        source_msg = update.message.reply_to_message
    elif context.args:
        text = ' '.join(context.args)
    else:
        await update.message.reply_text(
            "Usage:\n"
            "/broadcast <message>\n"
            "OR reply to message with /broadcast"
        )
        return
    
    status = await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
    
    success = 0
    failed = 0
    removed = []
    
    for group_id in groups:
        try:
            if update.message.reply_to_message:
                if source_msg.text:
                    await context.bot.send_message(group_id, source_msg.text)
                elif source_msg.photo:
                    await context.bot.send_photo(group_id, source_msg.photo[-1].file_id, caption=source_msg.caption)
                elif source_msg.voice:
                    await context.bot.send_voice(group_id, source_msg.voice.file_id)
            else:
                await context.bot.send_message(group_id, text)
            
            success += 1
            await asyncio.sleep(0.5)  # Rate limiting
        
        except (Forbidden, BadRequest):
            failed += 1
            removed.append(group_id)
            db.remove_group(group_id)
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
            failed += 1
    
    result = f"""<b>📊 Broadcast Complete</b>

✅ Success: {success}/{len(groups)}
❌ Failed: {failed}"""
    
    if removed:
        result += f"\n🗑️ Removed {len(removed)} inactive groups"
    
    await status.edit_text(result, parse_mode='HTML')

# ==================== MESSAGE HANDLER ====================

# Rate limiting
last_group_reply: Dict[int, datetime] = defaultdict(lambda: datetime.min)
last_user_reply: Dict[str, datetime] = defaultdict(lambda: datetime.min)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages"""
    
    try:
        if not update.message or not update.message.text:
            return
        
        is_private = update.message.chat.type == "private"
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_msg = update.message.text
        now = datetime.now()
        
        # Group handling
        if not is_private:
            chat = update.effective_chat
            db.add_group(chat_id, chat.title or "", chat.username or "")
            
            # Check if should reply
            bot_username = context.bot.username or "niyati"
            is_reply_to_bot = (
                update.message.reply_to_message and
                update.message.reply_to_message.from_user.id == context.bot.id
            )
            
            if not is_reply_to_bot:
                # Check cooldowns
                if (now - last_group_reply[chat_id]).total_seconds() < config.GROUP_REPLY_COOLDOWN:
                    return
                
                user_key = f"{chat_id}_{user_id}"
                if (now - last_user_reply[user_key]).total_seconds() < config.USER_COOLDOWN:
                    return
                
                # Decide if should reply
                if not should_reply_in_group(user_msg, bot_username):
                    return
            
            last_group_reply[chat_id] = now
            last_user_reply[f"{chat_id}_{user_id}"] = now
        
        # Check sleeping time
        if is_sleeping_time():
            sleep_responses = [
                "yaar... so rahi hu abhi... kal baat karte hai na 😴💤",
                "its literally 3am... sone do yaar 🌙",
                "good night! talk tomorrow 💤✨"
            ]
            await update.message.reply_text(random.choice(sleep_responses))
            return
        
        # Show typing
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Get user data
        user_data = db.get_user(user_id)
        stage = RelationshipStage(user_data['relationship_stage'])
        mood = user_data['mood']
        name = user_data['name'] or update.effective_user.first_name
        
        # Detect sentiment
        sentiment = extract_sentiment(user_msg)
        
        # Check for AI accusation
        ai_keywords = ["bot", "ai", "fake", "robot", "chatgpt", "gemini", "artificial"]
        if any(word in user_msg.lower() for word in ai_keywords):
            response = random.choice([
                "excuse me?? main real hu okay! 😤",
                "bro seriously? ai wai kuch nahi... 😡",
                "tumne abhi kya kaha? take it back 😒",
                "blocked for calling me fake 🙄"
            ])
            await asyncio.sleep(calculate_typing_delay(response))
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response, False, sentiment)
            return
        
        # Decide if voice message
        should_voice = (
            is_private and
            voice_engine.should_send_voice(user_msg, stage, sentiment)
        )
        
        # Generate AI response
        context_str = db.get_conversation_context(user_id)
        response = await ai_engine.generate_response(
            user_msg,
            context_str,
            stage,
            mood,
            name,
            for_voice=should_voice
        )
        
        # Fallback if AI fails
        if not response:
            logger.warning(f"AI failed, using fallback for user {user_id}")
            response = ai_engine.get_fallback_response(user_msg, stage, name)
        
        # Send response
        if should_voice:
            # Send as voice
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio_io = await voice_engine.generate_speech(response, use_premium=True)
            
            if audio_io:
                await update.message.reply_voice(
                    voice=audio_io,
                    caption=f"🎤 {response[:100]}{'...' if len(response) > 100 else ''}"
                )
                db.add_message(user_id, user_msg, response, True, sentiment)
                logger.info(f"Voice sent to user {user_id} - Stage: {stage.value}")
            else:
                # Voice failed, send as text
                await asyncio.sleep(calculate_typing_delay(response))
                await update.message.reply_text(response)
                db.add_message(user_id, user_msg, response, False, sentiment)
        else:
            # Send as text
            await asyncio.sleep(calculate_typing_delay(response))
            await update.message.reply_text(response)
            db.add_message(user_id, user_msg, response, False, sentiment)
        
        logger.info(f"Replied to {user_id} in {'DM' if is_private else f'group {chat_id}'} - Stage: {stage.value}")
    
    except Exception as e:
        logger.error(f"Message handler error: {e}", exc_info=True)
        try:
            await update.message.reply_text("oof something went wrong... try again? 😅")
        except:
            pass

# ==================== ERROR HANDLER ====================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    
    # Notify user if possible
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "uff yaar... something went wrong 😅\ntry again?"
            )
        except:
            pass

# ==================== FLASK SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    """Home endpoint"""
    stats = db.get_stats()
    return jsonify({
        "bot": "Niyati AI Girlfriend",
        "version": "6.0",
        "status": "online",
        "mood": "vibing ✨",
        "users": stats['total_users'],
        "groups": stats['total_groups'],
        "messages": stats['total_messages']
    })

@flask_app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "sleeping": is_sleeping_time()
    })

@flask_app.route('/stats')
def stats_endpoint():
    """Stats endpoint"""
    return jsonify(db.get_stats())

def run_flask() -> None:
    """Run Flask server"""
    logger.info(f"🌐 Starting Flask on {config.HOST}:{config.PORT}")
    serve(flask_app, host=config.HOST, port=config.PORT, threads=4)

# ==================== MAIN BOT ====================

async def main() -> None:
    """Main bot function"""
    
    try:
        # Validate config
        config.validate()
        
        logger.info("=" * 70)
        logger.info("🤖 Starting Niyati Bot v6.0")
        logger.info("✨ Enhanced AI Girlfriend Experience")
        logger.info("=" * 70)
        
        # Build application
        app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("ping", ping_command))
        app.add_handler(CommandHandler("mood", mood_command))
        app.add_handler(CommandHandler("tts", tts_command))
        app.add_handler(CommandHandler("voice", voice_command))
        app.add_handler(CommandHandler("voicestatus", voice_status_command))
        app.add_handler(CommandHandler("scan", scan_groups_command))
        app.add_handler(CommandHandler("groups", groups_command))
        app.add_handler(CommandHandler("broadcast", broadcast_command))
        
        # Message handler
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Error handler
        app.add_error_handler(error_handler)
        
        # Initialize
        await app.initialize()
        await app.start()
        
        # Get bot info
        bot_info = await app.bot.get_me()
        logger.info(f"✅ Bot started: @{bot_info.username}")
        logger.info(f"💬 Name: {bot_info.first_name}")
        logger.info(f"🎭 AI Model: {config.GEMINI_MODEL}")
        logger.info(f"🎤 Voice: {'ElevenLabs' if voice_engine.working else 'gTTS'}")
        
        # Start polling
        logger.info("🔄 Starting polling...")
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=1.0
        )
        
        logger.info("✅ Bot is now running!")
        
        # Keep running
        await asyncio.Event().wait()
    
    except Exception as e:
        logger.critical(f"💥 Fatal error: {e}", exc_info=True)
        raise

# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Small delay for Flask to start
    import time
    time.sleep(2)
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down gracefully...")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}", exc_info=True)
        sys.exit(1)
