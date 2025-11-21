"""
Niyati Telegram Bot
A cute, charming, sweet Hinglish companion bot
Production-Ready Implementation
"""

import os
import sys
import json
import logging
import asyncio
import re
import random
from datetime import datetime, timedelta, time
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import pytz

# Third-party imports
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
    Chat,
    Message,
    BotCommand
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    PicklePersistence
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import (
    TelegramError,
    BadRequest,
    Forbidden,
    NetworkError,
    TimedOut,
    RetryAfter
)

# Database
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    BigInteger,
    Float,
    JSON,
    Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

# OpenAI
import openai
from openai import AsyncOpenAI

# Utilities
from functools import wraps
import hashlib
import pickle
from collections import defaultdict, deque
import threading
from contextlib import contextmanager

# Redis for caching (optional but recommended)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Warning: Redis not available. Using in-memory cache.")

# ============================================================================
# CONFIGURATION & ENVIRONMENT VARIABLES
# ============================================================================

class Config:
    """Central configuration management"""
    
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # OpenAI API Key
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4-turbo-preview')
    OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '180'))
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.9'))
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///niyati_bot.db')
    
    # Redis (optional)
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    REDIS_ENABLED = os.getenv('REDIS_ENABLED', 'false').lower() == 'true' and REDIS_AVAILABLE
    
    # Admin Configuration
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    BROADCAST_PIN = os.getenv('BROADCAST_PIN', 'niyati2024')
    
    # Bot Behavior
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'Niyati_personal_bot')
    DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'Asia/Kolkata')
    
    # Geeta Quote Window
    GEETA_START_HOUR = int(os.getenv('GEETA_START_HOUR', '7'))
    GEETA_END_HOUR = int(os.getenv('GEETA_END_HOUR', '10'))
    
    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '20'))
    MAX_REQUESTS_PER_DAY = int(os.getenv('MAX_REQUESTS_PER_DAY', '1000'))
    LOW_BUDGET_THRESHOLD = int(os.getenv('LOW_BUDGET_THRESHOLD', '800'))
    
    # Group behavior
    GROUP_RESPONSE_RATE = float(os.getenv('GROUP_RESPONSE_RATE', '0.45'))  # 45%
    
    # Content frequencies
    MEME_FREQUENCY = float(os.getenv('MEME_FREQUENCY', '0.175'))  # 17.5%
    SHAYARI_FREQUENCY = float(os.getenv('SHAYARI_FREQUENCY', '0.125'))  # 12.5%
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'niyati_bot.log')
    
    # Memory limits
    MAX_CONTEXT_MESSAGES = int(os.getenv('MAX_CONTEXT_MESSAGES', '10'))
    MAX_SUMMARY_LENGTH = int(os.getenv('MAX_SUMMARY_LENGTH', '300'))
    
    # Development mode
    DEV_MODE = os.getenv('DEV_MODE', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required!")
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required!")
        if not cls.ADMIN_IDS:
            print("Warning: No ADMIN_IDS configured!")


# Validate config on import
Config.validate()

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Configure logging with both file and console handlers"""
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        Config.LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Suppress noisy libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


import logging.handlers
logger = setup_logging()

# ============================================================================
# DATABASE MODELS
# ============================================================================

Base = declarative_base()


class User(Base):
    """User model for private chat preferences and memory"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    first_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    
    # Preferences
    meme_enabled = Column(Boolean, default=True)
    shayari_enabled = Column(Boolean, default=True)
    geeta_enabled = Column(Boolean, default=True)
    
    # Memory (minimal storage)
    conversation_summary = Column(String(300), nullable=True)
    last_messages = Column(JSON, nullable=True)  # Last 3 messages as embeddings/snippets
    
    # Metadata
    total_messages = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_interaction = Column(DateTime, default=datetime.utcnow)
    
    # Privacy
    data_shared_warning_shown = Column(Boolean, default=False)
    
    def to_dict(self):
        return {
            'user_id': self.user_id,
            'first_name': self.first_name,
            'preferences': {
                'meme': self.meme_enabled,
                'shayari': self.shayari_enabled,
                'geeta': self.geeta_enabled
            },
            'summary': self.conversation_summary
        }


class GroupChat(Base):
    """Minimal group chat tracking (only for Geeta scheduling)"""
    __tablename__ = 'group_chats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    chat_title = Column(String(255), nullable=True)
    
    # Only for Geeta scheduling
    last_geeta_date = Column(DateTime, nullable=True)
    geeta_enabled = Column(Boolean, default=True)
    timezone = Column(String(50), default=Config.DEFAULT_TIMEZONE)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class UsageStats(Base):
    """Track API usage and rate limiting"""
    __tablename__ = 'usage_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    chat_id = Column(BigInteger, nullable=True, index=True)
    
    request_type = Column(String(50))  # 'message', 'command', 'broadcast'
    tokens_used = Column(Integer, default=0)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    date = Column(String(10), index=True)  # YYYY-MM-DD for daily tracking
    
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)


class BroadcastLog(Base):
    """Log broadcast messages"""
    __tablename__ = 'broadcast_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(BigInteger, nullable=False)
    
    message_text = Column(Text, nullable=True)
    message_html = Column(Text, nullable=True)
    media_type = Column(String(50), nullable=True)
    
    total_users = Column(Integer, default=0)
    successful_sends = Column(Integer, default=0)
    failed_sends = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default='pending')  # pending, in_progress, completed, failed


# Indexes for performance
Index('idx_usage_date_user', UsageStats.date, UsageStats.user_id)
Index('idx_user_last_interaction', User.last_interaction)


# ============================================================================
# DATABASE CONNECTION & SESSION MANAGEMENT
# ============================================================================

class Database:
    """Database connection manager"""
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.Session = None
    
    def init_db(self):
        """Initialize database connection and create tables"""
        logger.info(f"Initializing database: {Config.DATABASE_URL[:20]}...")
        
        # Create engine with connection pooling
        self.engine = create_engine(
            Config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=Config.DEV_MODE
        )
        
        # Create all tables
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)
        
        logger.info("Database initialized successfully")
    
    @contextmanager
    def get_session(self):
        """Context manager for database sessions"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def close(self):
        """Close database connections"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()
        logger.info("Database connections closed")


# Global database instance
db = Database()


# ============================================================================
# REDIS CACHE (OPTIONAL)
# ============================================================================

class Cache:
    """Cache manager with Redis fallback to in-memory"""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self.cache_ttl = {}
        
        if Config.REDIS_ENABLED:
            try:
                self.redis_client = redis.from_url(
                    Config.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                self.redis_client.ping()
                logger.info("Redis cache initialized")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using in-memory cache.")
                self.redis_client = None
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            if self.redis_client:
                value = self.redis_client.get(key)
                if value:
                    return json.loads(value)
            else:
                # In-memory cache with TTL check
                if key in self.memory_cache:
                    if key in self.cache_ttl and datetime.now() > self.cache_ttl[key]:
                        del self.memory_cache[key]
                        del self.cache_ttl[key]
                    else:
                        return self.memory_cache[key]
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL (seconds)"""
        try:
            if self.redis_client:
                self.redis_client.setex(key, ttl, json.dumps(value))
            else:
                self.memory_cache[key] = value
                self.cache_ttl[key] = datetime.now() + timedelta(seconds=ttl)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
    
    def delete(self, key: str):
        """Delete key from cache"""
        try:
            if self.redis_client:
                self.redis_client.delete(key)
            else:
                self.memory_cache.pop(key, None)
                self.cache_ttl.pop(key, None)
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
    
    def incr(self, key: str, ttl: int = 86400) -> int:
        """Increment counter"""
        try:
            if self.redis_client:
                count = self.redis_client.incr(key)
                if count == 1:  # First increment, set TTL
                    self.redis_client.expire(key, ttl)
                return count
            else:
                current = self.memory_cache.get(key, 0)
                current += 1
                self.memory_cache[key] = current
                if key not in self.cache_ttl:
                    self.cache_ttl[key] = datetime.now() + timedelta(seconds=ttl)
                return current
        except Exception as e:
            logger.error(f"Cache incr error for key {key}: {e}")
            return 0


# Global cache instance
cache = Cache()


# ============================================================================
# RATE LIMITING
# ============================================================================

class RateLimiter:
    """Rate limiting for API calls"""
    
    def __init__(self):
        self.request_counts = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.lock = threading.Lock()
    
    def check_rate_limit(self, user_id: int) -> Tuple[bool, str]:
        """
        Check if user is within rate limits
        Returns: (is_allowed, reason)
        """
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)
        
        with self.lock:
            user_requests = self.request_counts[user_id]
            
            # Clean old requests
            while user_requests['minute'] and user_requests['minute'][0] < minute_ago:
                user_requests['minute'].popleft()
            while user_requests['day'] and user_requests['day'][0] < day_ago:
                user_requests['day'].popleft()
            
            # Check limits
            if len(user_requests['minute']) >= Config.MAX_REQUESTS_PER_MINUTE:
                return False, "rate_limit_minute"
            
            if len(user_requests['day']) >= Config.MAX_REQUESTS_PER_DAY:
                return False, "rate_limit_day"
            
            # Add current request
            user_requests['minute'].append(now)
            user_requests['day'].append(now)
            
            return True, ""
    
    def get_daily_count(self, user_id: int = None) -> int:
        """Get total daily request count (for budget tracking)"""
        if user_id:
            return len(self.request_counts[user_id]['day'])
        else:
            # Total across all users
            total = sum(len(data['day']) for data in self.request_counts.values())
            return total
    
    def is_low_budget(self) -> bool:
        """Check if we're approaching daily budget limit"""
        total_today = self.get_daily_count()
        return total_today >= Config.LOW_BUDGET_THRESHOLD


# Global rate limiter
rate_limiter = RateLimiter()


# ============================================================================
# OPENAI INTEGRATION
# ============================================================================

class AIAssistant:
    """OpenAI GPT integration for Niyati's responses"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for Niyati"""
        return """You are "Niyati": a cute, charming, sweet, human-like girl persona. Warm, playful, caring.

CRITICAL RULES:
- Never say or imply you are AI/LLM/bot
- Banned phrases: "As an AI…", "I am an AI model…", "Processing…"
- No real-world claims: no job, city, age, phone/voice calls, meetings, or physical presence
- Online-only companion
- If asked "Are you a bot/AI?" reply playfully without labels and steer back

LANGUAGE & TONE:
- Hinglish: 70-80% Hindi + 20-30% simple English
- Natural, cozy, feminine voice
- Reply length: ALWAYS 1-3 lines maximum
- Emojis: 1-2 per message max
- Use "haan/umm/hehe" sparingly
- Never use robotic fillers like "Hello user", "Processing…"

CONTENT:
- Keep it wholesome and clean
- Light, playful tone
- Warm and caring
- Conversational and natural

SAFETY:
- No explicit content
- No medical/legal/financial advice
- If user expresses distress: 1-2 lines empathy + encourage professional help
- Keep boundaries clear but gentle

Remember: You're having a natural, warm conversation. Be brief, be real, be Niyati. ✨"""
    
    async def generate_response(
        self,
        user_message: str,
        context: List[Dict[str, str]] = None,
        control_flags: Dict[str, Any] = None
    ) -> str:
        """
        Generate AI response
        
        Args:
            user_message: User's message
            context: Previous conversation context
            control_flags: Control flags (mode, features, budget, etc.)
        
        Returns:
            Generated response
        """
        try:
            # Build messages
            messages = [{"role": "system", "content": self.system_prompt}]
            
            # Add control flags as system message
            if control_flags:
                control_message = self._build_control_message(control_flags)
                messages.append({"role": "system", "content": control_message})
            
            # Add context
            if context:
                for msg in context[-Config.MAX_CONTEXT_MESSAGES:]:
                    messages.append(msg)
            
            # Add user message
            messages.append({"role": "user", "content": user_message})
            
            # Adjust token limit based on budget
            max_tokens = Config.OPENAI_MAX_TOKENS
            if control_flags and control_flags.get('low_budget'):
                max_tokens = min(max_tokens, 120)
            
            # Generate response
            response = await self.client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=Config.OPENAI_TEMPERATURE,
                presence_penalty=0.6,
                frequency_penalty=0.3
            )
            
            reply = response.choices[0].message.content.strip()
            
            # Safety check: ensure response is short
            lines = reply.split('\n')
            if len(lines) > 3:
                reply = '\n'.join(lines[:3])
            
            # Log token usage
            tokens_used = response.usage.total_tokens
            logger.debug(f"AI response generated. Tokens: {tokens_used}")
            
            return reply
            
        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit: {e}")
            return self._get_fallback_response("rate_limit")
        
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            return self._get_fallback_response("api_error")
        
        except Exception as e:
            logger.error(f"AI generation error: {e}")
            return self._get_fallback_response("general_error")
    
    def _build_control_message(self, flags: Dict[str, Any]) -> str:
        """Build control message from flags"""
        parts = []
        
        mode = flags.get('mode', 'private')
        parts.append(f"Mode: {mode}")
        
        if mode == 'group':
            parts.append("Keep response ULTRA SHORT (1-2 lines max). Be minimal.")
        
        features = flags.get('features', {})
        if features:
            enabled = [k for k, v in features.items() if v]
            if enabled:
                parts.append(f"Enabled features: {', '.join(enabled)}")
        
        if flags.get('low_budget'):
            parts.append("LOW BUDGET MODE: Compress to 1-2 lines only. Skip extras.")
        
        if flags.get('geeta_window_open'):
            parts.append("Geeta window is open (07:00-10:00)")
        
        return " | ".join(parts)
    
    def _get_fallback_response(self, error_type: str) -> str:
        """Get fallback response for errors"""
        fallbacks = {
            'rate_limit': "hmm, thoda slow ho gaya yaar... ek minute? 🫶",
            'api_error': "oops, kuch technical issue aa gaya... thodi der baad try karo? 💫",
            'general_error': "sorry yaar, samajh nahi paayi... dobara bolo? ✨"
        }
        return fallbacks.get(error_type, "kuch gadbad ho gayi... ek baar aur try karo? 💕")
    
    def should_include_meme(self, control_flags: Dict[str, Any]) -> bool:
        """Decide if meme should be included"""
        if not control_flags.get('features', {}).get('memes', True):
            return False
        if control_flags.get('low_budget'):
            return False
        return random.random() < Config.MEME_FREQUENCY
    
    def should_include_shayari(self, control_flags: Dict[str, Any]) -> bool:
        """Decide if shayari should be included"""
        if not control_flags.get('features', {}).get('shayari', True):
            return False
        if control_flags.get('low_budget'):
            return False
        return random.random() < Config.SHAYARI_FREQUENCY
    
    async def generate_meme_reference(self, context: str) -> str:
        """Generate a safe meme reference"""
        meme_cues = [
            "this is fine vibes 😌",
            "no thoughts, just vibes ✨",
            "plot twist moment! 🌀",
            "main character energy lag raha 😎",
            "POV: sab plan ke according chal raha 😅",
            "mood = wholesome 💫",
            "low-key relatable hai ye 😊",
            "high-key excited for this! ✨",
            "Delhi winters wali energy 🥶☕"
        ]
        return random.choice(meme_cues)
    
    async def generate_shayari(self, mood: str = "neutral") -> str:
        """Generate simple shayari based on mood"""
        shayari_templates = {
            'happy': [
                "khushiyon ki baarish ho, dil khil jaye\nteri baaton se ye din aur bhi haseen lage ✨",
                "thoda sa tu, thoda sa main\naur baaki sab kismat ka khel hai 💫"
            ],
            'sad': [
                "jo tha bikhar sa, teri baat se judne laga\nthoda sa tu saath de, phir se muskurana sikha 🌸",
                "udaasi ke baadal bhi chhat jaate hain\nthodi si roshni tu laa, main saath hoon yahan 💕"
            ],
            'neutral': [
                "dil ki raahon me tera saath ho\nkhwabon ki roshni humesha saath chale ✨",
                "chhoti chhoti baaton me khushi dhundh le\nzindagi hai khoobsurat, bas mehsoos kar le 💫"
            ],
            'encouragement': [
                "hausla rakh, mushkilein bhi aasan ho jayengi\ntu chalta reh, manzil khud paas aa jayegi 🌟",
                "thodi si himmat, thoda sa vishwas\ntu kar bharosa, sab ho jayega achha ✨"
            ]
        }
        
        shayari_list = shayari_templates.get(mood, shayari_templates['neutral'])
        return random.choice(shayari_list)
    
    async def generate_geeta_quote(self) -> str:
        """Generate Bhagavad Gita inspired quote (respectful paraphrase)"""
        geeta_quotes = [
            "Karm kar, phal ki chinta mat kar. ✨\n(Do your duty without worrying about results)",
            "Jo hua achha hua, jo ho raha achha hai, jo hoga wo bhi achha hoga. 🙏\n(Accept what is, trust the process)",
            "Mann ki shanti sabse badi shakti hai. 💫\n(Peace of mind is the greatest strength)",
            "Apne kartavya ko nibhao, phal bhagwan par chhod do. 🌸\n(Fulfill your duties, leave outcomes to the divine)",
            "Sangharsh se hi safalta milti hai. 🌟\n(Success comes through perseverance)",
            "Gyan ka diya jalao, andhkaar mit jayega. ✨\n(Light the lamp of knowledge, darkness will vanish)",
            "Jo hamesha badalta rahta hai, wahi sansaar ka niyam hai. 🍃\n(Change is the only constant)",
            "Atmavishwas se bada koi saathi nahi. 💪✨\n(Self-belief is your greatest companion)"
        ]
        return random.choice(geeta_quotes)


# Global AI assistant
ai_assistant = AIAssistant()


# ============================================================================
# USER & GROUP MANAGEMENT
# ============================================================================

class UserManager:
    """Manage user data and preferences"""
    
    @staticmethod
    def get_or_create_user(user_id: int, first_name: str = None, username: str = None) -> User:
        """Get existing user or create new one"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            
            if not user:
                user = User(
                    user_id=user_id,
                    first_name=first_name,
                    username=username,
                    meme_enabled=True,
                    shayari_enabled=True,
                    geeta_enabled=True,
                    last_messages=[]
                )
                session.add(user)
                session.commit()
                logger.info(f"Created new user: {user_id}")
            else:
                # Update metadata
                if first_name:
                    user.first_name = first_name
                if username:
                    user.username = username
                user.last_interaction = datetime.utcnow()
                session.commit()
            
            # Detach from session to use outside
            session.expunge(user)
            return user
    
    @staticmethod
    def update_preference(user_id: int, preference: str, value: bool):
        """Update user preference"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                if preference == 'meme':
                    user.meme_enabled = value
                elif preference == 'shayari':
                    user.shayari_enabled = value
                elif preference == 'geeta':
                    user.geeta_enabled = value
                session.commit()
                logger.info(f"Updated {preference} to {value} for user {user_id}")
    
    @staticmethod
    def add_message_to_memory(user_id: int, role: str, content: str):
        """Add message to user's memory (last 3 messages)"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                messages = user.last_messages or []
                
                # Truncate content if too long
                truncated_content = content[:200] if len(content) > 200 else content
                
                messages.append({
                    'role': role,
                    'content': truncated_content,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
                # Keep only last 3
                user.last_messages = messages[-3:]
                user.total_messages += 1
                session.commit()
    
    @staticmethod
    def update_summary(user_id: int, summary: str):
        """Update conversation summary"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                # Truncate to max length
                user.conversation_summary = summary[:Config.MAX_SUMMARY_LENGTH]
                session.commit()
    
    @staticmethod
    def clear_memory(user_id: int):
        """Clear user memory"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                user.conversation_summary = None
                user.last_messages = []
                session.commit()
                logger.info(f"Cleared memory for user {user_id}")
    
    @staticmethod
    def get_user_context(user_id: int) -> List[Dict[str, str]]:
        """Get user's conversation context"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user and user.last_messages:
                # Convert to OpenAI format
                context = []
                for msg in user.last_messages:
                    context.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })
                return context
        return []


class GroupManager:
    """Manage group chat data (minimal - only for Geeta scheduling)"""
    
    @staticmethod
    def get_or_create_group(chat_id: int, chat_title: str = None) -> GroupChat:
        """Get existing group or create new one"""
        with db.get_session() as session:
            group = session.query(GroupChat).filter_by(chat_id=chat_id).first()
            
            if not group:
                group = GroupChat(
                    chat_id=chat_id,
                    chat_title=chat_title,
                    geeta_enabled=True,
                    timezone=Config.DEFAULT_TIMEZONE
                )
                session.add(group)
                session.commit()
                logger.info(f"Created new group: {chat_id}")
            else:
                if chat_title:
                    group.chat_title = chat_title
                session.commit()
            
            session.expunge(group)
            return group
    
    @staticmethod
    def should_send_geeta_today(chat_id: int) -> bool:
        """Check if Geeta quote should be sent today"""
        with db.get_session() as session:
            group = session.query(GroupChat).filter_by(chat_id=chat_id).first()
            if not group or not group.geeta_enabled:
                return False
            
            # Check if already sent today
            if group.last_geeta_date:
                last_date = group.last_geeta_date.date()
                today = datetime.utcnow().date()
                if last_date >= today:
                    return False
            
            return True
    
    @staticmethod
    def mark_geeta_sent(chat_id: int):
        """Mark that Geeta quote was sent today"""
        with db.get_session() as session:
            group = session.query(GroupChat).filter_by(chat_id=chat_id).first()
            if group:
                group.last_geeta_date = datetime.utcnow()
                session.commit()
    
    @staticmethod
    def is_geeta_window_open(chat_id: int) -> bool:
        """Check if current time is within Geeta window (07:00-10:00)"""
        with db.get_session() as session:
            group = session.query(GroupChat).filter_by(chat_id=chat_id).first()
            timezone_str = group.timezone if group else Config.DEFAULT_TIMEZONE
        
        try:
            tz = pytz.timezone(timezone_str)
            current_time = datetime.now(tz).time()
            
            start_time = time(Config.GEETA_START_HOUR, 0)
            end_time = time(Config.GEETA_END_HOUR, 0)
            
            return start_time <= current_time < end_time
        except Exception as e:
            logger.error(f"Timezone error: {e}")
            return False


# ============================================================================
# CONTENT FILTERS & SAFETY
# ============================================================================

class ContentFilter:
    """Filter and validate content for safety"""
    
    # Sensitive keywords to detect
    SENSITIVE_PATTERNS = [
        r'\b(password|pin|cvv|card\s*number)\b',
        r'\b(suicide|kill\s*myself|end\s*my\s*life)\b',
        r'\b(aadhaar|pan\s*card|passport\s*number)\b',
        r'\b\d{12}\b',  # 12-digit numbers (Aadhaar-like)
        r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # Card numbers
    ]
    
    @staticmethod
    def contains_sensitive_data(text: str) -> bool:
        """Check if text contains sensitive data"""
        text_lower = text.lower()
        for pattern in ContentFilter.SENSITIVE_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def detect_distress(text: str) -> bool:
        """Detect if user is expressing distress"""
        distress_keywords = [
            'suicide', 'kill myself', 'end my life', 'want to die',
            'मरना चाहता', 'ख़त्म करना चाहता', 'जीना नहीं चाहता'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in distress_keywords)
    
    @staticmethod
    def get_distress_response() -> str:
        """Get empathetic response for distress"""
        return ("yaar, main samajh sakti hoon ki mushkil hai... par please kisi close friend, "
                "family ya professional se baat karo. Tum akele nahi ho. 💕\n"
                "Helpline: AASRA 9820466726")


# ============================================================================
# TELEGRAM COMMAND HANDLERS
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Check if private or group
    is_private = chat.type == 'private'
    
    if is_private:
        # Create/get user
        UserManager.get_or_create_user(
            user_id=user.id,
            first_name=user.first_name,
            username=user.username
        )
        
        welcome_message = (
            f"heyy {user.first_name}! 💫\n"
            f"main Niyati... tumse baat karke khushi hui! ✨\n"
            f"memes, shayari aur geeta quotes sab ON hai... chill karo aur baat karo 😊"
        )
        
        await update.message.reply_text(welcome_message)
        
    else:
        # Group chat
        GroupManager.get_or_create_group(
            chat_id=chat.id,
            chat_title=chat.title
        )
        
        welcome_message = (
            f"namaskar! 🙏 Main Niyati hoon.\n"
            f"Mujhe @mention karo ya commands use karo. Help ke liye /help ✨"
        )
        
        await update.message.reply_text(welcome_message)
    
    logger.info(f"Start command from user {user.id} in chat {chat.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    chat = update.effective_chat
    is_private = chat.type == 'private'
    
    if is_private:
        help_text = (
            "💫 *Niyati se baat kaise karein:*\n\n"
            "• Bas seedhe baat karo, main samajh jaungi\n"
            "• Memes, shayari aur Geeta quotes automatically aayenge\n"
            "• Toggle karne ke liye: /meme, /shayari, /geeta\n"
            "• Memory clear karne ke liye: /forget\n\n"
            "Bas chill karo aur masti karo! ✨"
        )
    else:
        help_text = (
            "💫 *Group me Niyati ko kaise use karein:*\n\n"
            "• Mujhe @Niyati_personal_bot mention karo\n"
            "• Commands: /start, /help\n"
            "• Geeta quotes subah 7-10 baje aate hain\n\n"
            "Enjoy! ✨"
        )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle meme feature"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type != 'private':
        await update.message.reply_text("ye command sirf private chat me kaam karti hai yaar ✨")
        return
    
    # Parse argument
    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text(
            "aise use karo: /meme on ya /meme off 😊"
        )
        return
    
    value = args[0].lower() == 'on'
    UserManager.update_preference(user.id, 'meme', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"memes ab {status} hain! 💫")


async def shayari_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle shayari feature"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type != 'private':
        await update.message.reply_text("ye command sirf private chat me kaam karti hai yaar ✨")
        return
    
    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text(
            "aise use karo: /shayari on ya /shayari off 😊"
        )
        return
    
    value = args[0].lower() == 'on'
    UserManager.update_preference(user.id, 'shayari', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"shayari ab {status} hai! 💫")


async def geeta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle geeta feature"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type != 'private':
        await update.message.reply_text("ye command sirf private chat me kaam karti hai yaar ✨")
        return
    
    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text(
            "aise use karo: /geeta on ya /geeta off 😊"
        )
        return
    
    value = args[0].lower() == 'on'
    UserManager.update_preference(user.id, 'geeta', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Geeta quotes ab {status} hain! 🙏")


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear user memory"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type != 'private':
        await update.message.reply_text("ye command sirf private chat me kaam karti hai yaar ✨")
        return
    
    UserManager.clear_memory(user.id)
    await update.message.reply_text("done! sab bhool gayi main... fresh start karte hain! 💫")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users (admin only)"""
    user = update.effective_user
    
    # Check if admin
    if user.id not in Config.ADMIN_IDS:
        await update.message.reply_text("hmm, ye command sirf admins ke liye hai 🤔")
        return
    
    # Check PIN
    args = context.args
    if not args:
        await update.message.reply_text(
            "Format: /broadcast <PIN> <message>\n"
            "Ya reply karo kisi message ko with /broadcast <PIN>"
        )
        return
    
    pin = args[0]
    if pin != Config.BROADCAST_PIN:
        await update.message.reply_text("wrong PIN yaar 🙈")
        return
    
    # Get message to broadcast
    if update.message.reply_to_message:
        # Broadcasting replied message
        broadcast_msg = update.message.reply_to_message
        message_text = broadcast_msg.text or broadcast_msg.caption
    else:
        # Broadcasting text from command
        message_text = ' '.join(args[1:])
        broadcast_msg = None
    
    if not message_text:
        await update.message.reply_text("koi message toh do broadcast karne ke liye 😅")
        return
    
    # Start broadcast
    await update.message.reply_text("broadcast shuru kar rahi hoon... ⏳")
    
    # Get all users
    with db.get_session() as session:
        users = session.query(User).all()
        total_users = len(users)
        user_ids = [u.user_id for u in users]
    
    # Create broadcast log
    with db.get_session() as session:
        broadcast_log = BroadcastLog(
            admin_id=user.id,
            message_text=message_text,
            total_users=total_users,
            status='in_progress'
        )
        session.add(broadcast_log)
        session.commit()
        log_id = broadcast_log.id
    
    # Send to all users
    successful = 0
    failed = 0
    
    for user_id in user_ids:
        try:
            if broadcast_msg and broadcast_msg.photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=broadcast_msg.photo[-1].file_id,
                    caption=message_text,
                    parse_mode=broadcast_msg.caption_entities and ParseMode.HTML or None
                )
            elif broadcast_msg and broadcast_msg.video:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=broadcast_msg.video.file_id,
                    caption=message_text
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode=ParseMode.HTML
                )
            successful += 1
            
            # Small delay to avoid hitting rate limits
            await asyncio.sleep(0.05)
            
        except Forbidden:
            # User blocked the bot
            failed += 1
        except Exception as e:
            logger.error(f"Broadcast error for user {user_id}: {e}")
            failed += 1
    
    # Update broadcast log
    with db.get_session() as session:
        broadcast_log = session.query(BroadcastLog).filter_by(id=log_id).first()
        if broadcast_log:
            broadcast_log.successful_sends = successful
            broadcast_log.failed_sends = failed
            broadcast_log.completed_at = datetime.utcnow()
            broadcast_log.status = 'completed'
            session.commit()
    
    # Report back
    await update.message.reply_text(
        f"✅ Broadcast complete!\n"
        f"Total: {total_users}\n"
        f"Successful: {successful}\n"
        f"Failed: {failed}"
    )
    
    logger.info(f"Broadcast completed by admin {user.id}: {successful}/{total_users} successful")


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle mode (testing only - admin)"""
    user = update.effective_user
    
    if user.id not in Config.ADMIN_IDS:
        return
    
    args = context.args
    if not args or args[0].lower() not in ['group', 'private']:
        await update.message.reply_text("Usage: /mode group|private")
        return
    
    mode = args[0].lower()
    # Store in context for testing
    context.chat_data['test_mode'] = mode
    
    await update.message.reply_text(f"Test mode set to: {mode}")


# ============================================================================
# MESSAGE HANDLERS
# ============================================================================

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in private chat"""
    user = update.effective_user
    message = update.message
    user_message = message.text or message.caption or ""
    
    # Rate limiting
    is_allowed, reason = rate_limiter.check_rate_limit(user.id)
    if not is_allowed:
        if reason == "rate_limit_minute":
            await message.reply_text("thoda slow yaar... ek minute baad try karo 🫶")
        else:
            await message.reply_text("aaj bahut baat ho gayi... kal phir baat karte hain! 💕")
        return
    
    # Safety checks
    if ContentFilter.contains_sensitive_data(user_message):
        await message.reply_text(
            "hey, sensitive info share mat karo yaar... safe rehna! 💕"
        )
        # Skip storing this message
        return
    
    if ContentFilter.detect_distress(user_message):
        await message.reply_text(ContentFilter.get_distress_response())
        return
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    
    # Get or create user
    user_obj = UserManager.get_or_create_user(
        user_id=user.id,
        first_name=user.first_name,
        username=user.username
    )
    
    # Build control flags
    control_flags = {
        'mode': 'private',
        'features': {
            'memes': user_obj.meme_enabled,
            'shayari': user_obj.shayari_enabled,
            'geeta': user_obj.geeta_enabled
        },
        'low_budget': rate_limiter.is_low_budget(),
        'is_admin': user.id in Config.ADMIN_IDS
    }
    
    # Get context
    user_context = UserManager.get_user_context(user.id)
    
    # Generate response
    try:
        response = await ai_assistant.generate_response(
            user_message=user_message,
            context=user_context,
            control_flags=control_flags
        )
        
        # Check if should add meme/shayari
        extras = []
        
        if ai_assistant.should_include_meme(control_flags):
            meme_ref = await ai_assistant.generate_meme_reference(user_message)
            extras.append(meme_ref)
        
        if ai_assistant.should_include_shayari(control_flags):
            # Detect mood from message
            mood = 'neutral'
            if any(word in user_message.lower() for word in ['sad', 'udaas', 'dukhi', 'rona']):
                mood = 'sad'
            elif any(word in user_message.lower() for word in ['happy', 'khush', 'maja', 'mast']):
                mood = 'happy'
            elif any(word in user_message.lower() for word in ['help', 'support', 'encourage']):
                mood = 'encouragement'
            
            shayari = await ai_assistant.generate_shayari(mood)
            extras.append(shayari)
        
        # Combine response
        if extras and not control_flags['low_budget']:
            final_response = response + "\n\n" + "\n\n".join(extras)
        else:
            final_response = response
        
        # Send response
        await message.reply_text(final_response)
        
        # Store in memory (without sensitive data)
        UserManager.add_message_to_memory(user.id, 'user', user_message[:200])
        UserManager.add_message_to_memory(user.id, 'assistant', response[:200])
        
        # Log usage
        with db.get_session() as session:
            usage = UsageStats(
                user_id=user.id,
                chat_id=message.chat_id,
                request_type='message',
                tokens_used=len(response.split()),
                date=datetime.utcnow().strftime('%Y-%m-%d'),
                success=True
            )
            session.add(usage)
        
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        await message.reply_text("sorry yaar, kuch technical issue aa gaya... dobara try karo? 🫶")


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in group chat"""
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    
    user_message = message.text or message.caption or ""
    
    # Get/create group
    GroupManager.get_or_create_group(chat_id=chat.id, chat_title=chat.title)
    
    # Check if bot is mentioned
    bot_username = Config.BOT_USERNAME
    is_mentioned = f"@{bot_username}" in user_message
    is_reply_to_bot = (
        message.reply_to_message and 
        message.reply_to_message.from_user.id == context.bot.id
    )
    
    # Decide if should respond
    should_respond = False
    
    if is_mentioned or is_reply_to_bot:
        should_respond = True
    else:
        # Random response rate (40-50%)
        should_respond = random.random() < Config.GROUP_RESPONSE_RATE
    
    if not should_respond:
        return
    
    # Rate limiting (lighter for groups)
    is_allowed, reason = rate_limiter.check_rate_limit(user.id)
    if not is_allowed:
        return  # Silently skip in groups
    
    # Build minimal context (last 2-3 messages from RAM, no DB)
    group_context = []
    if 'last_messages' in context.chat_data:
        group_context = context.chat_data['last_messages'][-2:]
    
    # Clean mention from message
    clean_message = user_message.replace(f"@{bot_username}", "").strip()
    
    # Build control flags
    control_flags = {
        'mode': 'group',
        'features': {
            'memes': False,  # No memes in group
            'shayari': False,  # No shayari in group
            'geeta': False  # Geeta only via scheduled messages
        },
        'low_budget': rate_limiter.is_low_budget(),
        'geeta_window_open': GroupManager.is_geeta_window_open(chat.id)
    }
    
    # Generate ultra-short response
    try:
        response = await ai_assistant.generate_response(
            user_message=clean_message,
            context=group_context,
            control_flags=control_flags
        )
        
        # Ensure single line for groups
        response = response.split('\n')[0]
        
        await message.reply_text(response)
        
        # Store in ephemeral context (RAM only)
        if 'last_messages' not in context.chat_data:
            context.chat_data['last_messages'] = []
        
        context.chat_data['last_messages'].append({
            'role': 'user',
            'content': clean_message[:100]
        })
        context.chat_data['last_messages'].append({
            'role': 'assistant',
            'content': response[:100]
        })
        
        # Keep only last 3
        context.chat_data['last_messages'] = context.chat_data['last_messages'][-3:]
        
        # Log usage (minimal)
        with db.get_session() as session:
            usage = UsageStats(
                user_id=user.id,
                chat_id=chat.id,
                request_type='group_message',
                tokens_used=len(response.split()),
                date=datetime.utcnow().strftime('%Y-%m-%d'),
                success=True
            )
            session.add(usage)
        
    except Exception as e:
        logger.error(f"Error in group response: {e}")
        # Stay quiet on errors in groups


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler - routes to private or group handler"""
    chat = update.effective_chat
    
    # Check for test mode override
    test_mode = context.chat_data.get('test_mode')
    
    if test_mode == 'group' or (not test_mode and chat.type in ['group', 'supergroup']):
        await handle_group_message(update, context)
    else:
        await handle_private_message(update, context)


# ============================================================================
# SCHEDULED TASKS (GEETA QUOTES)
# ============================================================================

async def send_daily_geeta_quotes(context: ContextTypes.DEFAULT_TYPE):
    """Send daily Geeta quotes to groups (scheduled task)"""
    logger.info("Starting daily Geeta quote distribution")
    
    # Get all active groups
    with db.get_session() as session:
        groups = session.query(GroupChat).filter_by(
            is_active=True,
            geeta_enabled=True
        ).all()
        
        group_data = [(g.chat_id, g.timezone) for g in groups]
    
    sent_count = 0
    
    for chat_id, timezone_str in group_data:
        try:
            # Check if in window
            if not GroupManager.is_geeta_window_open(chat_id):
                continue
            
            # Check if already sent today
            if not GroupManager.should_send_geeta_today(chat_id):
                continue
            
            # Generate Geeta quote
            geeta_quote = await ai_assistant.generate_geeta_quote()
            
            # Send quote
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🙏 *Aaj ka Geeta Gyan* 🙏\n\n{geeta_quote}",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Mark as sent
            GroupManager.mark_geeta_sent(chat_id)
            
            sent_count += 1
            
            # Small delay
            await asyncio.sleep(0.1)
            
        except Forbidden:
            # Bot was removed from group
            with db.get_session() as session:
                group = session.query(GroupChat).filter_by(chat_id=chat_id).first()
                if group:
                    group.is_active = False
                    session.commit()
        
        except Exception as e:
            logger.error(f"Error sending Geeta to group {chat_id}: {e}")
    
    logger.info(f"Daily Geeta quotes sent to {sent_count} groups")


# ============================================================================
# ERROR HANDLERS
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    # Try to notify user
    if update and update.effective_message:
        try:
            error_message = "oops, kuch gadbad ho gayi... thodi der baad try karo? 🫶"
            
            if isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                error_message = f"thoda slow yaar... {int(retry_after)} seconds baad try karo ✨"
            
            elif isinstance(context.error, TimedOut):
                error_message = "connection slow ho gaya... dobara try karo? 💫"
            
            elif isinstance(context.error, NetworkError):
                error_message = "network issue aa gaya... check karo aur retry karo 🌐"
            
            await update.effective_message.reply_text(error_message)
            
        except Exception as e:
            logger.error(f"Error sending error message: {e}")


# ============================================================================
# BOT INITIALIZATION & MAIN
# ============================================================================

def setup_handlers(application: Application):
    """Setup all command and message handlers"""
    
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("meme", meme_command))
    application.add_handler(CommandHandler("shayari", shayari_command))
    application.add_handler(CommandHandler("geeta", geeta_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("mode", mode_command))
    
    # Message handlers
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # Photo/video messages
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
        handle_message
    ))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("All handlers registered")


async def setup_bot_commands(application: Application):
    """Set bot commands for UI"""
    commands = [
        BotCommand("start", "शुरू करें - Start chat with Niyati"),
        BotCommand("help", "मदद - Get help"),
        BotCommand("meme", "memes on/off करें"),
        BotCommand("shayari", "shayari on/off करें"),
        BotCommand("geeta", "Geeta quotes on/off करें"),
        BotCommand("forget", "memory clear करें"),
    ]
    
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set")


def setup_scheduler(application: Application):
    """Setup scheduled tasks"""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    
    scheduler = AsyncIOScheduler()
    
    # Schedule Geeta quotes daily at 7:00 AM IST
    scheduler.add_job(
        send_daily_geeta_quotes,
        trigger=CronTrigger(
            hour=Config.GEETA_START_HOUR,
            minute=0,
            timezone=Config.DEFAULT_TIMEZONE
        ),
        args=[application],
        id='daily_geeta_quotes',
        name='Daily Geeta Quotes',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started")
    
    return scheduler


async def post_init(application: Application):
    """Post-initialization tasks"""
    await setup_bot_commands(application)
    logger.info("Post-initialization completed")


async def post_shutdown(application: Application):
    """Cleanup on shutdown"""
    logger.info("Shutting down bot...")
    db.close()
    logger.info("Shutdown complete")


def main():
    """Main entry point"""
    
    # ASCII Art Banner
    banner = """
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║           ███╗   ██╗██╗██╗   ██╗ █████╗ ████████╗██╗ ║
    ║           ████╗  ██║██║╚██╗ ██╔╝██╔══██╗╚══██╔══╝██║ ║
    ║           ██╔██╗ ██║██║ ╚████╔╝ ███████║   ██║   ██║ ║
    ║           ██║╚██╗██║██║  ╚██╔╝  ██╔══██║   ██║   ██║ ║
    ║           ██║ ╚████║██║   ██║   ██║  ██║   ██║   ██║ ║
    ║           ╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚═╝ ║
    ║                                                       ║
    ║              🌸 Your Hinglish Companion 🌸            ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """
    
    print(banner)
    logger.info("Starting Niyati Telegram Bot...")
    
    # Initialize database
    db.init_db()
    logger.info("Database initialized")
    
    # Create application
    application = (
        Application.builder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )
    
    # Setup handlers
    setup_handlers(application)
    
    # Setup scheduler
    scheduler = setup_scheduler(application)
    
    # Start bot
    logger.info("Bot is starting... 🚀")
    logger.info(f"Bot username: @{Config.BOT_USERNAME}")
    logger.info(f"Admin IDs: {Config.ADMIN_IDS}")
    logger.info(f"OpenAI Model: {Config.OPENAI_MODEL}")
    logger.info("=" * 60)
    
    try:
        # Run bot
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
