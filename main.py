"""
Niyati Telegram Bot - FIXED VERSION
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
from sqlalchemy. pool import QueuePool

# OpenAI - FIXED IMPORT
from openai import AsyncOpenAI, RateLimitError, APIError

# Utilities
from functools import wraps
import hashlib
import pickle
from collections import defaultdict, deque
import threading
from contextlib import contextmanager

# Redis for caching (optional)
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
    
    # OpenAI API Key - FIXED
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')  # Changed to more reliable model
    OPENAI_MAX_TOKENS = int(os. getenv('OPENAI_MAX_TOKENS', '150'))
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.8'))
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///niyati_bot.db')
    
    # Redis (optional)
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    REDIS_ENABLED = os.getenv('REDIS_ENABLED', 'false').lower() == 'true' and REDIS_AVAILABLE
    
    # Admin Configuration
    ADMIN_IDS = [int(x. strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    BROADCAST_PIN = os.getenv('BROADCAST_PIN', 'niyati2024')
    
    # Bot Behavior
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'Niyati_personal_bot')
    DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'Asia/Kolkata')
    
    # Geeta Quote Window
    GEETA_START_HOUR = int(os.getenv('GEETA_START_HOUR', '7'))
    GEETA_END_HOUR = int(os. getenv('GEETA_END_HOUR', '10'))
    
    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '20'))
    MAX_REQUESTS_PER_DAY = int(os.getenv('MAX_REQUESTS_PER_DAY', '1000'))
    LOW_BUDGET_THRESHOLD = int(os.getenv('LOW_BUDGET_THRESHOLD', '800'))
    
    # Group behavior
    GROUP_RESPONSE_RATE = float(os.getenv('GROUP_RESPONSE_RATE', '0.45'))
    
    # Content frequencies
    MEME_FREQUENCY = float(os.getenv('MEME_FREQUENCY', '0.175'))
    SHAYARI_FREQUENCY = float(os. getenv('SHAYARI_FREQUENCY', '0.125'))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'niyati_bot. log')
    
    # Memory limits
    MAX_CONTEXT_MESSAGES = int(os.getenv('MAX_CONTEXT_MESSAGES', '5'))
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
        if not cls. ADMIN_IDS:
            print("Warning: No ADMIN_IDS configured!")


Config.validate()

# ============================================================================
# LOGGING SETUP
# ============================================================================

import logging. handlers

def setup_logging():
    """Configure logging with both file and console handlers"""
    
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    file_handler = logging.handlers.RotatingFileHandler(
        Config. LOG_FILE,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


logger = setup_logging()

# ============================================================================
# DATABASE MODELS
# ============================================================================

Base = declarative_base()


class User(Base):
    """User model"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    first_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    
    meme_enabled = Column(Boolean, default=True)
    shayari_enabled = Column(Boolean, default=True)
    geeta_enabled = Column(Boolean, default=True)
    
    conversation_summary = Column(String(300), nullable=True)
    last_messages = Column(JSON, nullable=True)
    
    total_messages = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_interaction = Column(DateTime, default=datetime.utcnow)
    
    data_shared_warning_shown = Column(Boolean, default=False)


class GroupChat(Base):
    """Group chat model"""
    __tablename__ = 'group_chats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    chat_title = Column(String(255), nullable=True)
    
    last_geeta_date = Column(DateTime, nullable=True)
    geeta_enabled = Column(Boolean, default=True)
    timezone = Column(String(50), default=Config.DEFAULT_TIMEZONE)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class UsageStats(Base):
    """Usage tracking"""
    __tablename__ = 'usage_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    chat_id = Column(BigInteger, nullable=True, index=True)
    
    request_type = Column(String(50))
    tokens_used = Column(Integer, default=0)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    date = Column(String(10), index=True)
    
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)


class BroadcastLog(Base):
    """Broadcast logs"""
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
    status = Column(String(20), default='pending')


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
        """Initialize database"""
        logger.info(f"Initializing database:  {Config.DATABASE_URL[: 20]}...")
        
        self.engine = create_engine(
            Config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=Config.DEV_MODE
        )
        
        Base.metadata.create_all(self.engine)
        
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
            session. close()
    
    def close(self):
        """Close database"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()
        logger.info("Database closed")


db = Database()


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

class Cache:
    """Cache manager"""
    
    def __init__(self):
        self.redis_client = None
        self. memory_cache = {}
        self. cache_ttl = {}
        
        if Config.REDIS_ENABLED: 
            try:
                self.redis_client = redis.from_url(
                    Config.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                self.redis_client.ping()
                logger.info("Redis initialized")
            except Exception as e: 
                logger.warning(f"Redis failed:  {e}. Using in-memory cache.")
                self.redis_client = None
    
    def get(self, key:  str) -> Optional[Any]:
        """Get from cache"""
        try:
            if self.redis_client:
                value = self.redis_client.get(key)
                if value: 
                    return json.loads(value)
            else:
                if key in self.memory_cache:
                    if key in self.cache_ttl and datetime.now() > self.cache_ttl[key]:
                        del self.memory_cache[key]
                        del self.cache_ttl[key]
                    else:
                        return self.memory_cache[key]
        except Exception as e:
            logger. error(f"Cache get error: {e}")
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set in cache"""
        try:
            if self.redis_client:
                self.redis_client.setex(key, ttl, json. dumps(value))
            else:
                self.memory_cache[key] = value
                self. cache_ttl[key] = datetime.now() + timedelta(seconds=ttl)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    def delete(self, key: str):
        """Delete from cache"""
        try:
            if self.redis_client:
                self.redis_client.delete(key)
            else:
                self.memory_cache.pop(key, None)
                self.cache_ttl.pop(key, None)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")


cache = Cache()


# ============================================================================
# RATE LIMITING
# ============================================================================

class RateLimiter: 
    """Rate limiting"""
    
    def __init__(self):
        self.request_counts = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.lock = threading.Lock()
    
    def check_rate_limit(self, user_id: int) -> Tuple[bool, str]:
        """Check rate limits"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)
        
        with self.lock:
            user_requests = self.request_counts[user_id]
            
            while user_requests['minute'] and user_requests['minute'][0] < minute_ago:
                user_requests['minute'].popleft()
            while user_requests['day'] and user_requests['day'][0] < day_ago:
                user_requests['day'].popleft()
            
            if len(user_requests['minute']) >= Config.MAX_REQUESTS_PER_MINUTE:
                return False, "rate_limit_minute"
            
            if len(user_requests['day']) >= Config.MAX_REQUESTS_PER_DAY: 
                return False, "rate_limit_day"
            
            user_requests['minute'].append(now)
            user_requests['day'].append(now)
            
            return True, ""
    
    def get_daily_count(self, user_id: int = None) -> int:
        """Get daily count"""
        if user_id: 
            return len(self.request_counts[user_id]['day'])
        else:
            total = sum(len(data['day']) for data in self.request_counts.values())
            return total
    
    def is_low_budget(self) -> bool:
        """Check budget"""
        total_today = self.get_daily_count()
        return total_today >= Config.LOW_BUDGET_THRESHOLD


rate_limiter = RateLimiter()


# ============================================================================
# OPENAI INTEGRATION - FIXED
# ============================================================================

class AIAssistant:
    """OpenAI GPT integration - FIXED"""
    
    def __init__(self):
        # FIXED:  Proper AsyncOpenAI initialization
        self. client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        self.system_prompt = self._build_system_prompt()
        logger.info(f"AIAssistant initialized with model: {Config.OPENAI_MODEL}")
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for Niyati"""
        return """You are "Niyati":  a cute, charming, sweet girl companion bot.  Warm, playful, caring. 

CRITICAL RULES:
- Never say you are AI/LLM/bot - be natural and human-like
- Banned phrases: "As an AI", "I am a bot", "Processing"
- No fake claims about real world (job, age, city, calls, meetings)
- You're an online-only text companion
- If asked "are you a bot?" - reply playfully without labels

LANGUAGE & TONE:
- Hinglish:  70% Hindi + 30% English mix
- Natural, cozy, feminine voice
- Reply length: 1-3 lines ONLY
- 1-2 emojis max per message
- Use casual phrases like "haan", "hehe", "umm" sparingly
- NEVER say "Hello user" or "Processing"

CONTENT: 
- Keep wholesome and clean
- Light and playful tone
- Warm and caring
- Natural conversation

SAFETY: 
- No explicit content
- No medical/legal/financial advice
- If distressed:  short empathy + suggest professional help

BE BRIEF, BE REAL, BE NIYATI.  ✨"""
    
    async def generate_response(
        self,
        user_message: str,
        context: List[Dict[str, str]] = None,
        control_flags: Dict[str, Any] = None
    ) -> str:
        """
        Generate AI response using OpenAI API - FIXED
        """
        try:
            # Build messages list
            messages = [{"role": "system", "content":  self.system_prompt}]
            
            # Add control flags
            if control_flags:
                control_msg = self._build_control_message(control_flags)
                if control_msg:
                    messages.append({"role": "system", "content": control_msg})
            
            # Add conversation context
            if context:
                # Take last N messages
                for msg in context[-Config.MAX_CONTEXT_MESSAGES:]:
                    messages.append({
                        "role": msg. get('role', 'user'),
                        "content": msg.get('content', '')
                    })
            
            # Add current user message
            messages.append({"role": "user", "content": user_message})
            
            # Determine max tokens
            max_tokens = Config.OPENAI_MAX_TOKENS
            if control_flags and control_flags.get('low_budget'):
                max_tokens = min(max_tokens, 100)
            
            # FIXED:  Proper async API call
            logger.debug(f"Calling OpenAI with {len(messages)} messages")
            
            response = await self.client. chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=Config.OPENAI_TEMPERATURE,
                presence_penalty=0.6,
                frequency_penalty=0.3,
                top_p=0.9
            )
            
            # Extract response
            reply = response.choices[0].message.content. strip()
            
            # Enforce length limit
            lines = reply.split('\n')
            if len(lines) > 4: 
                reply = '\n'.join(lines[: 4])
            
            logger. info(f"✅ AI Response generated: {len(reply)} chars")
            return reply
            
        except RateLimitError as e:
            logger.error(f"❌ OpenAI Rate Limit:  {e}")
            return await self._get_fallback_response("rate_limit")
        
        except APIError as e: 
            logger.error(f"❌ OpenAI API Error:  {e}")
            return await self._get_fallback_response("api_error")
        
        except Exception as e:
            logger.error(f"❌ AI Generation Error: {type(e).__name__}: {e}")
            return await self._get_fallback_response("general_error")
    
    def _build_control_message(self, flags: Dict[str, Any]) -> str:
        """Build control message from flags"""
        parts = []
        
        mode = flags.get('mode', 'private')
        if mode == 'group':
            parts.append("📱 GROUP MODE:  Keep response ULTRA SHORT (1 line max).")
        
        features = flags.get('features', {})
        if features: 
            enabled = [k for k, v in features.items() if v]
            if enabled:
                parts.append(f"Features: {', '.join(enabled)}")
        
        if flags.get('low_budget'):
            parts.append("⚠️ LOW BUDGET:  1-2 lines only, skip extras.")
        
        return " | ".join(parts)
    
    async def _get_fallback_response(self, error_type: str) -> str:
        """Get fallback response"""
        fallbacks = {
            'rate_limit': "hmm, thoda slow ho gaya yaar...  ek minute?  🫶",
            'api_error': "oops, kuch technical issue... thodi der baad try karo?  💫",
            'general_error':  "sorry, samajh nahi paayi... dobara bolo?  ✨"
        }
        return fallbacks.get(error_type, "kuch gadbad...  retry karo? 💕")
    
    def should_include_meme(self, control_flags: Dict[str, Any]) -> bool:
        """Decide if meme should be included"""
        if not control_flags. get('features', {}).get('memes', True):
            return False
        if control_flags.get('low_budget') or control_flags.get('mode') == 'group':
            return False
        return random.random() < Config.MEME_FREQUENCY
    
    def should_include_shayari(self, control_flags: Dict[str, Any]) -> bool:
        """Decide if shayari should be included"""
        if not control_flags.get('features', {}).get('shayari', True):
            return False
        if control_flags.get('low_budget') or control_flags.get('mode') == 'group':
            return False
        return random.random() < Config.SHAYARI_FREQUENCY
    
    async def generate_meme_reference(self, context: str = "") -> str:
        """Generate meme reference"""
        meme_cues = [
            "this is fine vibes 😌",
            "no thoughts, just vibes ✨",
            "plot twist!  🌀",
            "main character energy 😎",
            "POV: sab theek chal raha ✨",
            "mood = wholesome 💫",
            "low-key relatable 😊",
        ]
        return random.choice(meme_cues)
    
    async def generate_shayari(self, mood: str = "neutral") -> str:
        """Generate shayari"""
        shayari_templates = {
            'happy': [
                "khushiyon ki baarish ho, dil khil jaye\nteri baat se ye din aur bhi haseen lage ✨",
                "thoda sa tu, thoda sa main\naur baaki sab kismat hai 💫"
            ],
            'sad': [
                "jo tha bikhar sa, teri baat se judne laga\nthoda sa tu, phir se muskurana sikha 🌸",
                "udaasi bhi chhat jayegi\nthodi si roshni tu laa 💕"
            ],
            'neutral': [
                "dil ki raahon me tera saath ho\nkhwabon ki roshni hamesha chale ✨",
                "chhoti baaton me khushi dhundh le\nzindagi hai khoobsurat 💫"
            ]
        }
        
        shayari_list = shayari_templates.get(mood, shayari_templates['neutral'])
        return random.choice(shayari_list)
    
    async def generate_geeta_quote(self) -> str:
        """Generate Geeta quote"""
        geeta_quotes = [
            "Karm kar, phal ki chinta mat kar 🙏\n(Do your duty without worrying about results)",
            "Mann ki shanti sabse badi shakti hai 💫\n(Peace of mind is greatest strength)",
            "Apne kartavya ko nibhao, phal bhagwan par 🌸\n(Do your duty, leave outcomes to divine)",
            "Gyan ka diya jalao, andhkaar mit jayega ✨\n(Light of knowledge vanishes darkness)"
        ]
        return random. choice(geeta_quotes)


# Global AI assistant
ai_assistant = AIAssistant()


# ============================================================================
# USER & GROUP MANAGEMENT
# ============================================================================

class UserManager:
    """Manage user data"""
    
    @staticmethod
    def get_or_create_user(user_id: int, first_name: str = None, username: str = None) -> User:
        """Get or create user"""
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
                session. add(user)
                session. commit()
                logger.info(f"✅ New user created: {user_id}")
            else:
                if first_name:
                    user.first_name = first_name
                if username:
                    user.username = username
                user.last_interaction = datetime.utcnow()
                session. commit()
            
            session.expunge(user)
            return user
    
    @staticmethod
    def update_preference(user_id: int, preference: str, value: bool):
        """Update preference"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                setattr(user, f'{preference}_enabled', value)
                session.commit()
                logger. info(f"Preference {preference} = {value} for user {user_id}")
    
    @staticmethod
    def add_message_to_memory(user_id: int, role: str, content: str):
        """Add message to memory"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                messages = user.last_messages or []
                
                # Truncate long content
                truncated = content[:200] if len(content) > 200 else content
                
                messages.append({
                    'role': role,
                    'content': truncated,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
                # Keep only last 5
                user.last_messages = messages[-5:]
                user.total_messages += 1
                user.updated_at = datetime.utcnow()
                session.commit()
    
    @staticmethod
    def get_user_context(user_id: int) -> List[Dict[str, str]]:
        """Get user context for AI"""
        with db.get_session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user and user.last_messages:
                context = []
                for msg in user.last_messages:
                    context. append({
                        'role':  msg. get('role', 'user'),
                        'content': msg. get('content', '')
                    })
                return context
        return []
    
    @staticmethod
    def clear_memory(user_id: int):
        """Clear user memory"""
        with db.get_session() as session:
            user = session. query(User).filter_by(user_id=user_id).first()
            if user: 
                user.conversation_summary = None
                user.last_messages = []
                session.commit()
                logger.info(f"Memory cleared for user {user_id}")


class GroupManager:
    """Manage groups"""
    
    @staticmethod
    def get_or_create_group(chat_id: int, chat_title: str = None) -> GroupChat:
        """Get or create group"""
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
                logger.info(f"✅ New group created: {chat_id}")
            else:
                if chat_title: 
                    group.chat_title = chat_title
                session.commit()
            
            session.expunge(group)
            return group


# ============================================================================
# CONTENT FILTER
# ============================================================================

class ContentFilter:
    """Filter content for safety"""
    
    SENSITIVE_PATTERNS = [
        r'\b(password|pin|cvv|card\s*number)\b',
        r'\b(suicide|kill\s*myself)\b',
        r'\b\d{12}\b',
    ]
    
    @staticmethod
    def contains_sensitive_data(text: str) -> bool:
        """Check for sensitive data"""
        text_lower = text.lower()
        for pattern in ContentFilter. SENSITIVE_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False
    
    @staticmethod
    def detect_distress(text: str) -> bool:
        """Detect distress"""
        keywords = ['suicide', 'kill myself', 'want to die', 'end my life']
        return any(kw in text.lower() for kw in keywords)


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start"""
    user = update.effective_user
    chat = update.effective_chat
    
    is_private = chat.type == 'private'
    
    if is_private: 
        UserManager.get_or_create_user(user.id, user.first_name, user.username)
        
        welcome = (
            f"heyy {user.first_name}!  💫\n"
            f"main Niyati...  meri baat karo! ✨\n"
            f"memes, shayari sab ON hai 😊"
        )
        await update.message.reply_text(welcome)
    else:
        GroupManager.get_or_create_group(chat.id, chat.title)
        welcome = "namaskar! 🙏 Main Niyati hoon."
        await update.message.reply_text(welcome)
    
    logger.info(f"Start:  User {user.id}, Chat {chat.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help"""
    help_text = (
        "💫 *Niyati se baat karein: *\n\n"
        "• Seedhe message bhejo\n"
        "• /meme on/off\n"
        "• /shayari on/off\n"
        "• /forget (memory clear)\n\n"
        "Enjoy!  ✨"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle meme"""
    user = update.effective_user
    args = context.args
    
    if not args or args[0]. lower() not in ['on', 'off']: 
        await update.message.reply_text("Use:  /meme on or /meme off")
        return
    
    value = args[0].lower() == 'on'
    UserManager.update_preference(user. id, 'meme', value)
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Memes {status} 💫")


async def shayari_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle shayari"""
    user = update.effective_user
    args = context. args
    
    if not args or args[0].lower() not in ['on', 'off']: 
        await update.message.reply_text("Use: /shayari on or /shayari off")
        return
    
    value = args[0].lower() == 'on'
    UserManager.update_preference(user. id, 'shayari', value)
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Shayari {status} 💫")


async def forget_command(update:  Update, context: ContextTypes. DEFAULT_TYPE):
    """Clear memory"""
    user = update. effective_user
    UserManager. clear_memory(user.id)
    await update.message.reply_text("Memory clear! Fresh start 💫")


# ============================================================================
# MESSAGE HANDLER - MAIN LOGIC FIXED
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    MAIN MESSAGE HANDLER - FIXED
    This is where the bot generates responses
    """
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    
    # Get user message
    user_message = message. text or message.caption or ""
    
    if not user_message:
        return
    
    logger.info(f"📨 Message from {user.id}: {user_message[: 50]}")
    
    # ---- RATE LIMITING ----
    is_allowed, reason = rate_limiter.check_rate_limit(user.id)
    if not is_allowed:
        if reason == "rate_limit_minute":
            await message.reply_text("thoda slow...  ek minute? 🫶")
        else:
            await message.reply_text("aaj bahut baat ho gayi 💕")
        return
    
    # ---- SAFETY CHECKS ----
    if ContentFilter.contains_sensitive_data(user_message):
        await message.reply_text("sensitive info mat share karo yaar 💕")
        return
    
    if ContentFilter.detect_distress(user_message):
        await message.reply_text("yaar, thik nahi lag raha... professional se baat karo 💕")
        return
    
    # ---- TYPING INDICATOR ----
await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)

try:
    # ---- GET/CREATE USER ----
    user_obj = UserManager.get_or_create_user(user.id, user.first_name, user.username)

    # ✅ IMPORTANT FIX — DetachedInstanceError ka ilaaj
    session = SessionLocal()
    user_obj = session.merge(user_obj)
    session.refresh(user_obj)

    # ---- BUILD CONTROL FLAGS ----
    is_private = chat.type == 'private'
    control_flags = {
        'mode': 'private' if is_private else 'group',
        'features': {
            'memes': user_obj.meme_enabled if is_private else False,
            'shayari': user_obj.shayari_enabled if is_private else False,
        },
        'low_budget': rate_limiter.is_low_budget(),
    }

except Exception as e:
    logger.error(f"❌ Control flag error: {e}")
        
        # ---- GET CONTEXT ----
        user_context = UserManager.get_user_context(user.id)
        
        # ---- CALL OPENAI API ----
        logger.info(f"🤖 Calling OpenAI API...")
        response = await ai_assistant.generate_response(
            user_message=user_message,
            context=user_context,
            control_flags=control_flags
        )
        
        # ---- ADD EXTRAS (MEME/SHAYARI) ----
        extras = []
        
        if ai_assistant.should_include_meme(control_flags):
            meme = await ai_assistant.generate_meme_reference(user_message)
            extras.append(f"_{meme}_")
        
        if ai_assistant.should_include_shayari(control_flags):
            shayari = await ai_assistant.generate_shayari()
            extras.append(shayari)
        
        # ---- COMBINE RESPONSE ----
        if extras and not control_flags['low_budget']:
            final_response = response + "\n\n" + "\n\n".join(extras)
        else:
            final_response = response
        
        # ---- SEND RESPONSE ----
        logger.info(f"📤 Sending response: {final_response[:50]}...")
        await message.reply_text(final_response)
        
        # ---- SAVE TO MEMORY ----
        UserManager.add_message_to_memory(user.id, 'user', user_message)
        UserManager.add_message_to_memory(user.id, 'assistant', response)
        
        # ---- LOG USAGE ----
        with db.get_session() as session:
            usage = UsageStats(
                user_id=user.id,
                chat_id=chat.id,
                request_type='message',
                tokens_used=len(response. split()),
                date=datetime.utcnow().strftime('%Y-%m-%d'),
                success=True
            )
            session.add(usage)
        
        logger.info(f"✅ Message handled successfully")
        
    except Exception as e:
        logger.error(f"❌ Error handling message: {type(e).__name__}: {e}", exc_info=True)
        await message.reply_text("sorry yaar, kuch gadbad... dobara try karo?  🫶")


# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"❌ Error: {context.error}", exc_info=True)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "oops, kuch technical issue... retry karo?  🫶"
            )
        except Exception as e: 
            logger.error(f"Error sending error message: {e}")


# ============================================================================
# BOT SETUP
# ============================================================================

def setup_handlers(application:  Application):
    """Setup handlers"""
    
    # Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("meme", meme_command))
    application.add_handler(CommandHandler("shayari", shayari_command))
    application.add_handler(CommandHandler("forget", forget_command))
    
    # Messages
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # Error
    application.add_error_handler(error_handler)
    
    logger.info("✅ All handlers registered")


async def post_init(application: Application):
    """Post-init"""
    logger.info("✅ Bot initialized")


async def post_shutdown(application: Application):
    """Shutdown"""
    logger.info("🛑 Shutting down...")
    db.close()


def main():
    """Main entry point"""
    
    banner = """
    ╔════════════════════════════════════════════════════════╗
    ║                    NIYATI BOT v2.0                     ║
    ║            🌸 Your Hinglish Companion 🌸               ║
    ║                                                        ║
    ║         Powered by OpenAI GPT-3. 5-turbo               ║
    ╚════════════════════════════════════════════════════════╝
    """
    
    print(banner)
    logger.info("=" * 60)
    logger.info("🚀 Starting Niyati Bot...")
    logger.info(f"Token: {Config.TELEGRAM_BOT_TOKEN[: 20]}***")
    logger.info(f"Model: {Config.OPENAI_MODEL}")
    logger.info(f"Database: {Config.DATABASE_URL}")
    logger.info("=" * 60)
    
    # Init database
    db.init_db()
    
    # Create application
    application = (
        Application.builder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )
    
    # Setup
    setup_handlers(application)
    
    # Start
    logger.info("🎯 Bot is polling...")
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        logger. info("⏹️ Keyboard interrupt")
    except Exception as e: 
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        logger.info("🛑 Shutdown complete")


if __name__ == "__main__":
    main()
