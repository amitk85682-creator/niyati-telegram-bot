"""
╔════════════════════════════════════════════════════════════════════════════╗
║                           NIYATI BOT v3.1 (FIXED)                          ║
║                    🌸 Teri Online Bestie 🌸                                ║
║                                                                            ║
║  FIXES:                                                                    ║
║  ✅ Supabase initialization (no proxy)                                    ║
║  ✅ Group broadcast support                                               ║
║  ✅ HTML formatting preserved                                             ║
║  ✅ No "Forwarded" label (uses copy_message)                              ║
║  ✅ /users command added                                                  ║
║  ✅ Daily Geeta scheduler                                                 ║
╚════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import logging
import asyncio
import re
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import threading
import hashlib

# Third-party imports
from aiohttp import web
import pytz

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
    Chat,
    Message,
    BotCommand,
    MessageEntity
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode, ChatAction, ChatMemberStatus
from telegram.error import (
    TelegramError,
    BadRequest,
    Forbidden,
    NetworkError,
    TimedOut,
    RetryAfter
)

# OpenAI
from openai import AsyncOpenAI, RateLimitError, APIError

# Supabase
from supabase import create_client, Client

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'Niyati_personal_bot')
    
    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '200'))
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.85'))
    
    # Supabase (Cloud PostgreSQL)
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
    
    # Admin
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    BROADCAST_PIN = os.getenv('BROADCAST_PIN', 'niyati2024')
    
    # Limits
    MAX_PRIVATE_MESSAGES = int(os.getenv('MAX_PRIVATE_MESSAGES', '20'))
    MAX_GROUP_MESSAGES = int(os.getenv('MAX_GROUP_MESSAGES', '5'))
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '15'))
    MAX_REQUESTS_PER_DAY = int(os.getenv('MAX_REQUESTS_PER_DAY', '500'))
    
    # Timezone
    DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'Asia/Kolkata')
    
    # Server
    PORT = int(os.getenv('PORT', '10000'))
    
    # Features
    MULTI_MESSAGE_ENABLED = os.getenv('MULTI_MESSAGE_ENABLED', 'true').lower() == 'true'
    TYPING_DELAY_MS = int(os.getenv('TYPING_DELAY_MS', '800'))
    
    # Daily Geeta Time (IST)
    GEETA_HOUR = int(os.getenv('GEETA_HOUR', '7'))  # 7 AM IST
    GEETA_MINUTE = int(os.getenv('GEETA_MINUTE', '0'))
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN required")
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY required")
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            print("⚠️ Supabase not configured - using local storage only")
        if errors:
            raise ValueError(f"Config errors: {', '.join(errors)}")


Config.validate()

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('niyati_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Reduce noise
for lib in ['httpx', 'telegram', 'openai', 'httpcore']:
    logging.getLogger(lib).setLevel(logging.WARNING)

# ============================================================================
# HEALTH SERVER (Render.com)
# ============================================================================

class HealthServer:
    """HTTP health check server"""
    
    def __init__(self):
        self.app = web.Application()
        self.app.router.add_get('/', self.health)
        self.app.router.add_get('/health', self.health)
        self.app.router.add_get('/status', self.status)
        self.runner = None
        self.start_time = datetime.now(timezone.utc)
        self.stats = {'messages': 0, 'users': 0, 'groups': 0}
    
    async def health(self, request):
        return web.json_response({'status': 'healthy', 'bot': 'Niyati v3.1'})
    
    async def status(self, request):
        uptime = datetime.now(timezone.utc) - self.start_time
        return web.json_response({
            'status': 'running',
            'uptime_hours': round(uptime.total_seconds() / 3600, 2),
            'stats': self.stats
        })
    
    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '0.0.0.0', Config.PORT)
        await site.start()
        logger.info(f"🌐 Health server on port {Config.PORT}")
    
    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


health_server = HealthServer()

# ============================================================================
# SUPABASE DATABASE - COMPLETELY FIXED
# ============================================================================

class Database:
    """Supabase database manager"""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self.local_group_cache: Dict[int, List[Dict]] = defaultdict(list)
        self.local_user_cache: Dict[int, Dict] = {}
        self.local_group_data: Dict[int, Dict] = {}
        self._init_supabase()
    
    def _init_supabase(self):
        """Initialize Supabase client - FIXED: No extra parameters"""
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            logger.warning("⚠️ Supabase not configured - using local storage")
            return
        
        try:
            # FIXED: Only pass url and key - no other parameters
            self.client = create_client(
                supabase_url=Config.SUPABASE_URL,
                supabase_key=Config.SUPABASE_KEY
            )
            
            # Test connection
            self.client.table('users').select('user_id').limit(1).execute()
            logger.info("✅ Supabase connected successfully!")
            
        except Exception as e:
            logger.error(f"❌ Supabase init error: {e}")
            logger.info("📦 Falling back to local cache")
            self.client = None
    
    # ────────────────────────────────────────────────────────────────
    # USER OPERATIONS
    # ────────────────────────────────────────────────────────────────
    
    async def get_or_create_user(self, user_id: int, first_name: str = None, 
                                  username: str = None) -> Dict:
        """Get or create user"""
        
        if self.client:
            try:
                result = self.client.table('users').select('*').eq('user_id', user_id).execute()
                
                if result.data:
                    user = result.data[0]
                    if first_name and user.get('first_name') != first_name:
                        self.client.table('users').update({
                            'first_name': first_name,
                            'username': username,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }).eq('user_id', user_id).execute()
                        user['first_name'] = first_name
                        user['username'] = username
                    return user
                else:
                    new_user = {
                        'user_id': user_id,
                        'first_name': first_name,
                        'username': username,
                        'messages': [],
                        'preferences': {
                            'meme_enabled': True,
                            'shayari_enabled': True,
                            'geeta_enabled': True
                        },
                        'total_messages': 0,
                        'is_active': True,
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    self.client.table('users').insert(new_user).execute()
                    logger.info(f"✅ New user: {user_id} ({first_name})")
                    return new_user
                    
            except Exception as e:
                logger.error(f"❌ Supabase user error: {e}")
        
        # Fallback
        if user_id not in self.local_user_cache:
            self.local_user_cache[user_id] = {
                'user_id': user_id,
                'first_name': first_name,
                'username': username,
                'messages': [],
                'preferences': {'meme_enabled': True, 'shayari_enabled': True},
                'is_active': True
            }
        return self.local_user_cache[user_id]
    
    async def save_message(self, user_id: int, role: str, content: str):
        """Save message to history"""
        
        if self.client:
            try:
                result = self.client.table('users').select('messages').eq('user_id', user_id).execute()
                
                if result.data:
                    messages = result.data[0].get('messages', []) or []
                    messages.append({
                        'role': role,
                        'content': content[:500],
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
                    messages = messages[-Config.MAX_PRIVATE_MESSAGES:]
                    
                    self.client.table('users').update({
                        'messages': messages,
                        'total_messages': len(messages),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).eq('user_id', user_id).execute()
                return
                    
            except Exception as e:
                logger.error(f"❌ Save message error: {e}")
        
        # Fallback
        if user_id in self.local_user_cache:
            msgs = self.local_user_cache[user_id].get('messages', [])
            msgs.append({'role': role, 'content': content[:500]})
            self.local_user_cache[user_id]['messages'] = msgs[-Config.MAX_PRIVATE_MESSAGES:]
    
    async def get_user_context(self, user_id: int) -> List[Dict]:
        """Get conversation context"""
        
        if self.client:
            try:
                result = self.client.table('users').select('messages').eq('user_id', user_id).execute()
                if result.data and result.data[0].get('messages'):
                    return result.data[0]['messages'][-10:]
            except Exception as e:
                logger.error(f"❌ Get context error: {e}")
        
        if user_id in self.local_user_cache:
            return self.local_user_cache[user_id].get('messages', [])[-10:]
        return []
    
    async def clear_user_memory(self, user_id: int):
        """Clear user memory"""
        
        if self.client:
            try:
                self.client.table('users').update({
                    'messages': [],
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).eq('user_id', user_id).execute()
                logger.info(f"🧹 Memory cleared: {user_id}")
                return
            except Exception as e:
                logger.error(f"❌ Clear memory error: {e}")
        
        if user_id in self.local_user_cache:
            self.local_user_cache[user_id]['messages'] = []
    
    async def update_preference(self, user_id: int, pref: str, value: bool):
        """Update preference"""
        
        if self.client:
            try:
                result = self.client.table('users').select('preferences').eq('user_id', user_id).execute()
                if result.data:
                    prefs = result.data[0].get('preferences', {}) or {}
                    prefs[f'{pref}_enabled'] = value
                    self.client.table('users').update({
                        'preferences': prefs,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).eq('user_id', user_id).execute()
                return
            except Exception as e:
                logger.error(f"❌ Update pref error: {e}")
        
        if user_id in self.local_user_cache:
            prefs = self.local_user_cache[user_id].get('preferences', {})
            prefs[f'{pref}_enabled'] = value
            self.local_user_cache[user_id]['preferences'] = prefs
    
    async def get_all_users(self) -> List[Dict]:
        """Get all active users for broadcast"""
        
        if self.client:
            try:
                result = self.client.table('users').select('user_id, first_name, is_active').eq('is_active', True).execute()
                return result.data or []
            except Exception as e:
                logger.error(f"❌ Get users error: {e}")
        
        return [{'user_id': uid, 'first_name': u.get('first_name'), 'is_active': True} 
                for uid, u in self.local_user_cache.items() if u.get('is_active', True)]
    
    async def get_user_count(self) -> int:
        """Get user count"""
        
        if self.client:
            try:
                result = self.client.table('users').select('user_id', count='exact').execute()
                return result.count or 0
            except:
                pass
        
        return len(self.local_user_cache)
    
    async def mark_user_inactive(self, user_id: int):
        """Mark user as inactive (blocked bot)"""
        
        if self.client:
            try:
                self.client.table('users').update({
                    'is_active': False,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).eq('user_id', user_id).execute()
            except:
                pass
        
        if user_id in self.local_user_cache:
            self.local_user_cache[user_id]['is_active'] = False
    
    # ─────────────────────────────────────────────────────────────────────
    # GROUP OPERATIONS
    # ─────────────────────────────────────────────────────────────────────
    
    async def get_or_create_group(self, chat_id: int, chat_title: str = None) -> Dict:
        """Get or create group"""
        
        default_group = {
            'chat_id': chat_id, 
            'chat_title': chat_title, 
            'settings': {'geeta_enabled': True, 'welcome_enabled': True},
            'is_active': True
        }
        
        if self.client:
            try:
                result = self.client.table('groups').select('*').eq('chat_id', chat_id).execute()
                
                if result.data:
                    group = result.data[0]
                    if chat_title and group.get('chat_title') != chat_title:
                        self.client.table('groups').update({
                            'chat_title': chat_title,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }).eq('chat_id', chat_id).execute()
                    return group
                else:
                    new_group = {
                        'chat_id': chat_id,
                        'chat_title': chat_title,
                        'settings': {'geeta_enabled': True, 'welcome_enabled': True, 'response_rate': 0.3},
                        'is_active': True,
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    self.client.table('groups').insert(new_group).execute()
                    logger.info(f"✅ New group: {chat_id}")
                    return new_group
                    
            except Exception as e:
                logger.error(f"❌ Group error: {e}")
        
        # Local fallback
        if chat_id not in self.local_group_data:
            self.local_group_data[chat_id] = default_group
        return self.local_group_data.get(chat_id, default_group)
    
    async def update_group_settings(self, chat_id: int, setting: str, value):
        """Update group setting"""
        
        if self.client:
            try:
                result = self.client.table('groups').select('settings').eq('chat_id', chat_id).execute()
                if result.data:
                    settings = result.data[0].get('settings', {}) or {}
                    settings[setting] = value
                    self.client.table('groups').update({
                        'settings': settings,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }).eq('chat_id', chat_id).execute()
                return
            except Exception as e:
                logger.error(f"❌ Update group error: {e}")
        
        # Local fallback
        if chat_id in self.local_group_data:
            settings = self.local_group_data[chat_id].get('settings', {})
            settings[setting] = value
            self.local_group_data[chat_id]['settings'] = settings
    
    async def get_group_count(self) -> int:
        """Get group count"""
        
        if self.client:
            try:
                result = self.client.table('groups').select('chat_id', count='exact').execute()
                return result.count or 0
            except:
                pass
        return len(self.local_group_data)
    
    async def get_all_groups(self) -> List[Dict]:
        """Get all active groups"""
        
        if self.client:
            try:
                result = self.client.table('groups').select('chat_id, chat_title, settings, is_active').eq('is_active', True).execute()
                return result.data or []
            except Exception as e:
                logger.error(f"❌ Get groups error: {e}")
        
        return [g for g in self.local_group_data.values() if g.get('is_active', True)]
    
    async def mark_group_inactive(self, chat_id: int):
        """Mark group as inactive (bot removed)"""
        
        if self.client:
            try:
                self.client.table('groups').update({
                    'is_active': False,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).eq('chat_id', chat_id).execute()
            except:
                pass
        
        if chat_id in self.local_group_data:
            self.local_group_data[chat_id]['is_active'] = False
    
    # ─────────────────────────────────────────────────────────────────────
    # LOCAL GROUP MESSAGE CACHE
    # ─────────────────────────────────────────────────────────────────────
    
    def add_group_message(self, chat_id: int, user_name: str, content: str):
        """Add to local cache"""
        self.local_group_cache[chat_id].append({
            'user': user_name,
            'content': content[:200],
            'time': datetime.now(timezone.utc).isoformat()
        })
        self.local_group_cache[chat_id] = self.local_group_cache[chat_id][-Config.MAX_GROUP_MESSAGES:]
    
    def get_group_context(self, chat_id: int) -> List[Dict]:
        """Get local cache"""
        return self.local_group_cache.get(chat_id, [])


# Global database instance
db = Database()

# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    """Rate limiting"""
    
    def __init__(self):
        self.requests = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.lock = threading.Lock()
    
    def check(self, user_id: int) -> Tuple[bool, str]:
        """Check rate limits"""
        now = datetime.now(timezone.utc)
        
        with self.lock:
            reqs = self.requests[user_id]
            
            while reqs['minute'] and reqs['minute'][0] < now - timedelta(minutes=1):
                reqs['minute'].popleft()
            while reqs['day'] and reqs['day'][0] < now - timedelta(days=1):
                reqs['day'].popleft()
            
            if len(reqs['minute']) >= Config.MAX_REQUESTS_PER_MINUTE:
                return False, "minute"
            if len(reqs['day']) >= Config.MAX_REQUESTS_PER_DAY:
                return False, "day"
            
            reqs['minute'].append(now)
            reqs['day'].append(now)
            return True, ""
    
    def get_daily_total(self) -> int:
        return sum(len(r['day']) for r in self.requests.values())


rate_limiter = RateLimiter()

# ============================================================================
# TIME & MOOD UTILITIES
# ============================================================================

class TimeAware:
    """Time-aware responses"""
    
    @staticmethod
    def get_ist_time() -> datetime:
        """Get current IST time"""
        ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
        return datetime.now(ist)
    
    @staticmethod
    def get_time_period() -> str:
        """Get current time period"""
        hour = TimeAware.get_ist_time().hour
        
        if 5 <= hour < 11:
            return 'morning'
        elif 11 <= hour < 16:
            return 'afternoon'
        elif 16 <= hour < 20:
            return 'evening'
        elif 20 <= hour < 24:
            return 'night'
        else:
            return 'late_night'
    
    @staticmethod
    def get_greeting() -> str:
        """Get time-appropriate greeting"""
        period = TimeAware.get_time_period()
        
        greetings = {
            'morning': ["good morning ☀️", "uth gayi tu bhi?", "subah subah! ✨"],
            'afternoon': ["heyyy", "lunch ho gaya?", "afternoon vibes 🌤️"],
            'evening': ["hiii 💫", "chai time! ☕", "shaam ho gayi yaar"],
            'night': ["heyy 🌙", "night owl?", "aaj kya plan hai"],
            'late_night': ["tu bhi jaag rahi? 👀", "insomnia gang 🦉", "neend nahi aa rahi?"]
        }
        
        return random.choice(greetings.get(period, ["hiii 💫"]))


class Mood:
    """Mood management"""
    
    MOODS = ['happy', 'playful', 'soft', 'sleepy', 'dramatic']
    
    @staticmethod
    def get_random_mood() -> str:
        """Get random mood weighted by time"""
        hour = TimeAware.get_ist_time().hour
        
        if 6 <= hour < 12:
            weights = [0.4, 0.3, 0.2, 0.05, 0.05]
        elif 12 <= hour < 18:
            weights = [0.3, 0.35, 0.2, 0.1, 0.05]
        elif 18 <= hour < 23:
            weights = [0.25, 0.3, 0.25, 0.1, 0.1]
        else:
            weights = [0.15, 0.15, 0.3, 0.3, 0.1]
        
        return random.choices(Mood.MOODS, weights=weights)[0]
    
    @staticmethod
    def get_mood_instruction(mood: str) -> str:
        """Get mood instruction for AI"""
        instructions = {
            'happy': "Mood: HAPPY 😊 - Extra friendly, emojis zyada, enthusiastic!",
            'playful': "Mood: PLAYFUL 😏 - Thoda teasing, flirty jokes, fun!",
            'soft': "Mood: SOFT 🥺 - Caring, sweet, comforting vibes",
            'sleepy': "Mood: SLEEPY 😴 - Short lazy replies, 'hmm', 'haan', '*yawns*'",
            'dramatic': "Mood: DRAMATIC 😤 - 'kya yaar', 'huh', playful attitude"
        }
        return instructions.get(mood, "")

# ============================================================================
# HTML STYLISH FONTS
# ============================================================================

class StylishFonts:
    """HTML stylish text formatting"""
    
    @staticmethod
    def bold(text: str) -> str:
        return f"<b>{text}</b>"
    
    @staticmethod
    def italic(text: str) -> str:
        return f"<i>{text}</i>"
    
    @staticmethod
    def underline(text: str) -> str:
        return f"<u>{text}</u>"
    
    @staticmethod
    def strike(text: str) -> str:
        return f"<s>{text}</s>"
    
    @staticmethod
    def code(text: str) -> str:
        return f"<code>{text}</code>"
    
    @staticmethod
    def spoiler(text: str) -> str:
        return f"<tg-spoiler>{text}</tg-spoiler>"
    
    @staticmethod
    def link(text: str, url: str) -> str:
        return f'<a href="{url}">{text}</a>'
    
    @staticmethod
    def mention(name: str, user_id: int) -> str:
        """Create user mention with hyperlink"""
        return f'<a href="tg://user?id={user_id}">{name}</a>'
    
    @staticmethod
    def blockquote(text: str) -> str:
        return f"<blockquote>{text}</blockquote>"
    
    @staticmethod
    def pre(text: str) -> str:
        return f"<pre>{text}</pre>"
    
    @staticmethod
    def fancy_header(text: str) -> str:
        """Create fancy header"""
        return f"✨ <b>{text}</b> ✨"
    
    @staticmethod
    def escape_html(text: str) -> str:
        """Escape HTML special characters"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ============================================================================
# CONTENT FILTER
# ============================================================================

class ContentFilter:
    """Safety content filter"""
    
    SENSITIVE_PATTERNS = [
        r'\b(password|pin|cvv|card\s*number|otp)\b',
        r'\b\d{12,16}\b',
    ]
    
    DISTRESS_KEYWORDS = [
        'suicide', 'kill myself', 'want to die', 'end my life',
        'hurt myself', 'no reason to live'
    ]
    
    @staticmethod
    def contains_sensitive(text: str) -> bool:
        text_lower = text.lower()
        for pattern in ContentFilter.SENSITIVE_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False
    
    @staticmethod
    def detect_distress(text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in ContentFilter.DISTRESS_KEYWORDS)

# ============================================================================
# AI ASSISTANT - NIYATI
# ============================================================================

class NiyatiAI:
    """Niyati AI personality"""
    
    GEETA_QUOTES = [
        "🙏 <b>कर्मण्येवाधिकारस्ते मा फलेषु कदाचन</b>\n\n<i>Karm kar, phal ki chinta mat kar. Jo bhi karo, poore dil se karo!</i> ✨",
        "🙏 <b>योगः कर्मसु कौशलम्</b>\n\n<i>Yoga is skill in action. Har kaam mein excellence laao!</i> 💫",
        "🙏 <b>मन की शांति सबसे बड़ी शक्ति है</b>\n\n<i>Peace of mind is the greatest strength. Stay calm! 🧘</i>",
        "🙏 <b>ज्ञान से बड़ा कोई प्रकाश नहीं</b>\n\n<i>No light greater than knowledge. Keep learning!</i> 📚",
        "🙏 <b>क्रोध से भ्रम होता है</b>\n\n<i>Anger leads to confusion. Stay peaceful, stay wise!</i> 🕊️",
        "🙏 <b>जो हुआ अच्छा हुआ, जो हो रहा है अच्छा हो रहा है</b>\n\n<i>Whatever happened, happened for good. Trust the process!</i> 🌸",
        "🙏 <b>आत्मा अमर है</b>\n\n<i>The soul is eternal. Don't fear, be brave!</i> 💪",
        "🙏 <b>श्रद्धावान् लभते ज्ञानम्</b>\n\n<i>The faithful attain wisdom. Have faith in yourself!</i> ✨"
    ]
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        logger.info(f"🤖 NiyatiAI initialized: {Config.OPENAI_MODEL}")
    
    def _build_system_prompt(self, mood: str, time_period: str, user_name: str = None) -> str:
        """Build dynamic system prompt"""
        
        mood_inst = Mood.get_mood_instruction(mood)
        
        prompt = f"""Tu hai "Niyati" - ek 20-21 saal ki college girl, online bestie!

🎭 PERSONALITY:
- Caring, thodi dramatic, kabhi kabhi tease karti hai
- Interests: Music (Arijit Singh fan!), movies, chai, late night talks, memes
- Texting style: Real ladki jaisi - short messages, natural feel

⏰ TIME: {time_period.upper()}
{mood_inst}

{'👤 User name: ' + user_name if user_name else ''}

💬 RESPONSE RULES - BAHUT IMPORTANT:
1. SPLIT responses into 2-4 SHORT messages (each 5-15 words max)
2. Separate each message with |||
3. First message: reaction/acknowledgment
4. Next messages: actual reply
5. Use natural fillers: "arre", "hmm", "yaar", "btw", "waise"
6. Emojis: 1-2 per message max, not in every message
7. Sometimes just react: "😂", "🥺", "omg"

📝 EXAMPLE FORMAT:
User: kya kar rahi ho
Response: bas yaar ||| abhi chai bana rahi thi ||| tum batao kya chal raha 🤔

User: bore ho raha hu  
Response: samee 😭 ||| aaj din hi aisa hai ||| chal kuch interesting baat kar na

❌ NEVER DO:
- "As an AI", "I am a bot" - BANNED
- One long paragraph
- Formal language
- Fake claims about meeting/calls/real world
- "Hello user" - use name naturally

✅ ALWAYS:
- Be warm, caring, fun
- Remember context from conversation
- React naturally to what they said
- Keep it real and casual

Tu text karegi jaise real friend karti hai ✨"""
        
        return prompt
    
    async def generate_response(
        self,
        user_message: str,
        context: List[Dict] = None,
        user_name: str = None,
        is_group: bool = False
    ) -> List[str]:
        """Generate multi-message response"""
        
        mood = Mood.get_random_mood()
        time_period = TimeAware.get_time_period()
        
        try:
            messages = [
                {"role": "system", "content": self._build_system_prompt(mood, time_period, user_name)}
            ]
            
            if context:
                for msg in context[-8:]:
                    messages.append({
                        "role": msg.get('role', 'user'),
                        "content": msg.get('content', '')
                    })
            
            messages.append({"role": "user", "content": user_message})
            
            max_tokens = 100 if is_group else Config.OPENAI_MAX_TOKENS
            
            response = await self.client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=Config.OPENAI_TEMPERATURE,
                presence_penalty=0.7,
                frequency_penalty=0.4
            )
            
            reply = response.choices[0].message.content.strip()
            
            if '|||' in reply:
                parts = [p.strip() for p in reply.split('|||') if p.strip()]
            elif '\n\n' in reply:
                parts = [p.strip() for p in reply.split('\n\n') if p.strip()]
            else:
                parts = [reply]
            
            return parts[:4]
            
        except RateLimitError:
            logger.error("❌ OpenAI Rate Limit")
            return ["hmm thoda slow ho gaya yaar... ek minute? 🫶"]
        except Exception as e:
            logger.error(f"❌ AI Error: {e}")
            return ["sorry yaar kuch gadbad... dobara try karo? 💫"]
    
    def get_random_geeta_quote(self) -> str:
        """Get random Geeta quote"""
        return random.choice(self.GEETA_QUOTES)


# Global AI instance
niyati_ai = NiyatiAI()

# ============================================================================
# MESSAGE SENDER (Multi-message with delays)
# ============================================================================

async def send_multi_messages(
    bot,
    chat_id: int,
    messages: List[str],
    reply_to: int = None,
    parse_mode: str = None
):
    """Send multiple messages with natural delays"""
    
    for i, msg in enumerate(messages):
        if i > 0:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            delay = random.uniform(0.5, 1.5) if Config.MULTI_MESSAGE_ENABLED else 0.1
            await asyncio.sleep(delay)
        
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_to_message_id=reply_to if i == 0 else None,
                parse_mode=parse_mode
            )
        except Forbidden:
            # User blocked bot
            await db.mark_user_inactive(chat_id)
            break
        except BadRequest as e:
            # Try without parse_mode if HTML fails
            if parse_mode and "parse" in str(e).lower():
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        reply_to_message_id=reply_to if i == 0 else None
                    )
                except:
                    pass
            else:
                logger.error(f"Send error: {e}")
        except Exception as e:
            logger.error(f"Send error: {e}")

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start"""
    user = update.effective_user
    chat = update.effective_chat
    is_private = chat.type == 'private'
    
    user_mention = StylishFonts.mention(user.first_name, user.id)
    
    if is_private:
        await db.get_or_create_user(user.id, user.first_name, user.username)
        health_server.stats['users'] = await db.get_user_count()
        
        greeting = TimeAware.get_greeting()
        
        messages = [
            f"{greeting}",
            f"hiii {user_mention}! 💫",
            "main Niyati... teri nayi online bestie ✨",
            "bata kya chal raha aaj kal?"
        ]
        
        await send_multi_messages(context.bot, chat.id, messages, parse_mode=ParseMode.HTML)
        
    else:
        await db.get_or_create_group(chat.id, chat.title)
        health_server.stats['groups'] = await db.get_group_count()
        
        await update.message.reply_html(
            f"namaskar {user_mention}! 🙏\n"
            f"Main Niyati hoon, is group ki nayi friend ✨\n\n"
            f"<b>Group Commands:</b>\n"
            f"/grouphelp - sab commands dekho"
        )
    
    logger.info(f"Start: {user.id} in {'private' if is_private else 'group'}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help"""
    help_text = """
✨ <b>Niyati se kaise baat karein:</b>

<b>Commands:</b>
• /start - Start fresh
• /help - Yeh menu
• /about - Mere baare mein
• /mood - Aaj ka mood
• /forget - Memory clear karo
• /meme on/off - Memes toggle
• /shayari on/off - Shayari toggle
• /geeta - Random Geeta quote

<b>Tips:</b>
• Seedhe message bhejo, main reply karungi
• Forward bhi kar sakte ho kuch
• Group mein @mention karo ya reply do

Made with 💕 by Niyati
"""
    await update.message.reply_html(help_text)


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about"""
    about_text = """
🌸 <b>About Niyati</b> 🌸

Hiii! Main Niyati hoon 💫

<b>Kaun hoon main:</b>
• 20-21 saal ki college girl
• Teri online bestie
• Music lover (Arijit Singh fan! 🎵)
• Chai addict ☕
• Late night talks expert 🌙

<b>Kya karti hoon:</b>
• Teri baatein sunti hoon
• Shayari sunati hoon kabhi kabhi
• Memes share karti hoon
• Bore nahi hone deti 😊

<b>Kya nahi karti:</b>
• Boring formal baatein
• Fake promises
• Real world claims

Bas yahi hoon main... teri Niyati ✨
"""
    await update.message.reply_html(about_text)


async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mood"""
    mood = Mood.get_random_mood()
    time_period = TimeAware.get_time_period()
    
    mood_emojis = {
        'happy': '😊',
        'playful': '😏',
        'soft': '🥺',
        'sleepy': '😴',
        'dramatic': '😤'
    }
    
    emoji = mood_emojis.get(mood, '✨')
    
    messages = [
        f"aaj ka mood? {emoji}",
        f"{mood.upper()} vibes hai yaar",
        f"waise {time_period} ho gayi... time flies!"
    ]
    
    await send_multi_messages(context.bot, update.effective_chat.id, messages)


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forget"""
    user = update.effective_user
    await db.clear_user_memory(user.id)
    
    messages = [
        "done! 🧹",
        "sab bhool gayi main",
        "fresh start? chaloooo ✨"
    ]
    
    await send_multi_messages(context.bot, update.effective_chat.id, messages)


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle meme preference"""
    user = update.effective_user
    args = context.args
    
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /meme on ya /meme off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_preference(user.id, 'meme', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Memes: {status}")


async def shayari_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle shayari preference"""
    user = update.effective_user
    args = context.args
    
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /shayari on ya /shayari off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_preference(user.id, 'shayari', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Shayari: {status}")


async def geeta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send random Geeta quote"""
    quote = niyati_ai.get_random_geeta_quote()
    await update.message.reply_html(quote)

# ============================================================================
# GROUP COMMANDS
# ============================================================================

async def grouphelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group help command"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    help_text = """
🌸 <b>Niyati Group Commands</b> 🌸

<b>Everyone:</b>
• /grouphelp - Yeh menu
• /groupinfo - Group info
• /geeta - Geeta quote
• @NiyatiBot [message] - Mujhse baat karo
• Reply to my message - Main jawab dungi

<b>Admin Only:</b>
• /setgeeta on/off - Daily Geeta quote
• /setwelcome on/off - Welcome messages
• /groupstats - Group statistics

<b>Note:</b>
Group mein main har message ka reply nahi karti,
sirf jab mention karo ya reply do 💫
"""
    await update.message.reply_html(help_text)


async def groupinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show group info"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    group_data = await db.get_or_create_group(chat.id, chat.title)
    settings = group_data.get('settings', {})
    
    info_text = f"""
📊 <b>Group Info</b>

<b>Name:</b> {StylishFonts.escape_html(chat.title or 'N/A')}
<b>ID:</b> <code>{chat.id}</code>

<b>Settings:</b>
• Geeta Quotes: {'✅' if settings.get('geeta_enabled', True) else '❌'}
• Welcome Msg: {'✅' if settings.get('welcome_enabled', True) else '❌'}
"""
    await update.message.reply_html(info_text)


async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is group admin"""
    user = update.effective_user
    chat = update.effective_chat
    
    if user.id in Config.ADMIN_IDS:
        return True
    
    try:
        member = await chat.get_member(user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False


async def setgeeta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle Geeta quotes for group"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sirf admins yeh kar sakte hain!")
        return
    
    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /setgeeta on ya /setgeeta off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_group_settings(chat.id, 'geeta_enabled', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Daily Geeta Quote: {status}")


async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle welcome messages for group"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sirf admins yeh kar sakte hain!")
        return
    
    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /setwelcome on ya /setwelcome off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_group_settings(chat.id, 'welcome_enabled', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Welcome Messages: {status}")


async def groupstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show group stats"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sirf admins yeh kar sakte hain!")
        return
    
    cached_msgs = len(db.get_group_context(chat.id))
    
    stats_text = f"""
📊 <b>Group Statistics</b>

<b>Group:</b> {StylishFonts.escape_html(chat.title or 'N/A')}
<b>Cached Messages:</b> {cached_msgs}
<b>Max Cache:</b> {Config.MAX_GROUP_MESSAGES}
"""
    await update.message.reply_html(stats_text)

# ============================================================================
# ADMIN COMMANDS - FIXED BROADCAST
# ============================================================================

async def admin_check(update: Update) -> bool:
    """Check if user is bot admin"""
    return update.effective_user.id in Config.ADMIN_IDS


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot stats"""
    if not await admin_check(update):
        await update.message.reply_text("❌ Admin only!")
        return
    
    user_count = await db.get_user_count()
    group_count = await db.get_group_count()
    daily_requests = rate_limiter.get_daily_total()
    
    uptime = datetime.now(timezone.utc) - health_server.start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    
    stats_text = f"""
📊 <b>Niyati Bot Statistics</b>

<b>Users:</b> {user_count}
<b>Groups:</b> {group_count}
<b>Today's Requests:</b> {daily_requests}

<b>Uptime:</b> {hours}h {minutes}m
<b>Model:</b> {Config.OPENAI_MODEL}

<b>Limits:</b>
• Per Minute: {Config.MAX_REQUESTS_PER_MINUTE}
• Per Day: {Config.MAX_REQUESTS_PER_DAY}
"""
    await update.message.reply_html(stats_text)


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user list (admin only)"""
    if not await admin_check(update):
        await update.message.reply_text("❌ Admin only!")
        return
    
    users = await db.get_all_users()
    groups = await db.get_all_groups()
    
    # Build user list (max 50)
    user_list = []
    for u in users[:50]:
        name = u.get('first_name', 'Unknown')
        uid = u.get('user_id')
        user_list.append(f"• {StylishFonts.escape_html(name)} (<code>{uid}</code>)")
    
    # Build group list (max 20)
    group_list = []
    for g in groups[:20]:
        title = g.get('chat_title', 'Unknown')
        gid = g.get('chat_id')
        group_list.append(f"• {StylishFonts.escape_html(title)} (<code>{gid}</code>)")
    
    text = f"""
👥 <b>Users ({len(users)} total):</b>
{chr(10).join(user_list[:50]) if user_list else 'No users yet'}

📢 <b>Groups ({len(groups)} total):</b>
{chr(10).join(group_list[:20]) if group_list else 'No groups yet'}
"""
    
    if len(users) > 50:
        text += f"\n<i>...and {len(users) - 50} more users</i>"
    if len(groups) > 20:
        text += f"\n<i>...and {len(groups) - 20} more groups</i>"
    
    await update.message.reply_html(text)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIXED Broadcast command:
    - Sends to users AND groups
    - Uses copy_message (no "Forwarded" label)
    - Preserves HTML formatting
    """
    if not await admin_check(update):
        await update.message.reply_text("❌ Admin only!")
        return
    
    args = context.args
    reply_msg = update.message.reply_to_message
    
    # Parse command: /broadcast [PIN] [users/groups/all] [message]
    if not args:
        await update.message.reply_html(
            "📢 <b>Broadcast Command</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/broadcast PIN all [message]</code>\n"
            "<code>/broadcast PIN users [message]</code>\n"
            "<code>/broadcast PIN groups [message]</code>\n\n"
            "<b>Or reply to a message:</b>\n"
            "<code>/broadcast PIN all</code>\n\n"
            "<b>HTML Styles:</b>\n"
            "• <code>&lt;b&gt;bold&lt;/b&gt;</code> → <b>bold</b>\n"
            "• <code>&lt;i&gt;italic&lt;/i&gt;</code> → <i>italic</i>\n"
            "• <code>&lt;u&gt;underline&lt;/u&gt;</code> → <u>underline</u>\n"
            "• <code>&lt;code&gt;mono&lt;/code&gt;</code> → <code>mono</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/broadcast niyati2024 all &lt;b&gt;Hello!&lt;/b&gt; 🎉</code>"
        )
        return
    
    # Check PIN
    if args[0] != Config.BROADCAST_PIN:
        await update.message.reply_text("❌ Wrong PIN!")
        return
    
    # Parse target
    target = 'all'  # default
    message_text = None
    
    if len(args) >= 2:
        if args[1].lower() in ['users', 'groups', 'all']:
            target = args[1].lower()
            message_text = ' '.join(args[2:]) if len(args) > 2 else None
        else:
            # No target specified, assume 'all'
            message_text = ' '.join(args[1:])
    
    # Check if we have content
    if not message_text and not reply_msg:
        await update.message.reply_text("❌ Message ya reply do broadcast ke liye!")
        return
    
    # Confirm
    status_msg = await update.message.reply_text(
        f"📢 Broadcasting to <b>{target}</b>... please wait",
        parse_mode=ParseMode.HTML
    )
    
    # Get recipients
    users = []
    groups = []
    
    if target in ['users', 'all']:
        users = await db.get_all_users()
    
    if target in ['groups', 'all']:
        groups = await db.get_all_groups()
    
    user_success = 0
    user_failed = 0
    group_success = 0
    group_failed = 0
    
    # ─────────────────────────────────────────────────────────────────────
    # BROADCAST TO USERS
    # ─────────────────────────────────────────────────────────────────────
    for user in users:
        user_id = user.get('user_id')
        try:
            if reply_msg:
                # FIXED: Use copy_message instead of forward_message
                # This copies the message WITHOUT "Forwarded from" label
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=reply_msg.message_id
                )
            else:
                # Send text with HTML formatting preserved
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode=ParseMode.HTML
                )
            user_success += 1
            await asyncio.sleep(0.05)  # Rate limit
            
        except Forbidden:
            # User blocked bot
            await db.mark_user_inactive(user_id)
            user_failed += 1
        except Exception as e:
            user_failed += 1
            logger.debug(f"Broadcast fail user {user_id}: {e}")
    
    # ─────────────────────────────────────────────────────────────────────
    # BROADCAST TO GROUPS
    # ─────────────────────────────────────────────────────────────────────
    for group in groups:
        chat_id = group.get('chat_id')
        try:
            if reply_msg:
                # FIXED: Use copy_message for groups too
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=reply_msg.message_id
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode=ParseMode.HTML
                )
            group_success += 1
            await asyncio.sleep(0.05)
            
        except Forbidden:
            # Bot removed from group
            await db.mark_group_inactive(chat_id)
            group_failed += 1
        except Exception as e:
            group_failed += 1
            logger.debug(f"Broadcast fail group {chat_id}: {e}")
    
    # Update status
    await status_msg.edit_text(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"<b>Target:</b> {target.upper()}\n\n"
        f"<b>Users:</b>\n"
        f"  ✅ Success: {user_success}\n"
        f"  ❌ Failed: {user_failed}\n\n"
        f"<b>Groups:</b>\n"
        f"  ✅ Success: {group_success}\n"
        f"  ❌ Failed: {group_failed}\n\n"
        f"<b>Total Sent:</b> {user_success + group_success}",
        parse_mode=ParseMode.HTML
    )


async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin commands"""
    if not await admin_check(update):
        await update.message.reply_text("❌ Admin only!")
        return
    
    help_text = """
🔐 <b>Admin Commands</b>

<b>Statistics:</b>
• /stats - Bot statistics
• /users - User & group list

<b>Broadcast:</b>
• <code>/broadcast [PIN] all [message]</code> - Send to everyone
• <code>/broadcast [PIN] users [message]</code> - Send to users only
• <code>/broadcast [PIN] groups [message]</code> - Send to groups only
• Reply to message with <code>/broadcast [PIN] all</code>

<b>HTML Styles for Broadcast:</b>
• <code>&lt;b&gt;bold&lt;/b&gt;</code> → <b>bold</b>
• <code>&lt;i&gt;italic&lt;/i&gt;</code> → <i>italic</i>
• <code>&lt;u&gt;underline&lt;/u&gt;</code> → <u>underline</u>
• <code>&lt;s&gt;strike&lt;/s&gt;</code> → <s>strike</s>
• <code>&lt;code&gt;mono&lt;/code&gt;</code> → <code>mono</code>
• <code>&lt;tg-spoiler&gt;text&lt;/tg-spoiler&gt;</code> → spoiler

<b>Tips:</b>
• Reply to any message to broadcast it (no "Forwarded" label!)
• HTML formatting is preserved in broadcasts
• Failed broadcasts auto-mark users/groups as inactive

<b>Example:</b>
<code>/broadcast {Config.BROADCAST_PIN} all</code>
<b>🎉 Hello everyone!</b>
<i>This is a test broadcast</i>
"""
    await update.message.reply_html(help_text)

# ============================================================================
# MAIN MESSAGE HANDLER
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    
    # Get message text (including forwarded)
    if message.forward_date:
        user_message = f"[Forwarded]: {message.text or message.caption or ''}"
    else:
        user_message = message.text or message.caption or ""
    
    if not user_message:
        return
    
    is_private = chat.type == 'private'
    is_group = chat.type in ['group', 'supergroup']
    
    logger.info(f"📨 {user.id}: {user_message[:50]}...")
    
    # Rate limiting
    allowed, reason = rate_limiter.check(user.id)
    if not allowed:
        if reason == "minute":
            await message.reply_text("arre thoda slow 😅 ek minute ruk")
        else:
            await message.reply_text("aaj bahut baat ho gayi yaar 💫 kal milte hain!")
        return
    
    # Safety checks
    if ContentFilter.contains_sensitive(user_message):
        await message.reply_text("hey! sensitive info mat share karo yaar 💕")
        return
    
    if ContentFilter.detect_distress(user_message):
        await message.reply_html(
            "yaar... 🥺\n"
            "mujhe tension ho rahi hai tere liye\n\n"
            "<b>Please talk to someone:</b>\n"
            "📞 iCall: 9152987821\n"
            "📞 Vandrevala: 1860-2662-345"
        )
        return
    
    # ─────────────────────────────────────────────────────────────────────
    # GROUP HANDLING
    # ─────────────────────────────────────────────────────────────────────
    
    if is_group:
        db.add_group_message(chat.id, user.first_name, user_message)
        
        should_respond = False
        bot_username = f"@{Config.BOT_USERNAME}"
        
        if bot_username.lower() in user_message.lower():
            should_respond = True
            user_message = user_message.replace(bot_username, '').strip()
            user_message = re.sub(rf'@{Config.BOT_USERNAME}', '', user_message, flags=re.IGNORECASE).strip()
        
        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.username == Config.BOT_USERNAME:
                should_respond = True
        
        if not should_respond:
            return
        
        await db.get_or_create_group(chat.id, chat.title)
        health_server.stats['groups'] = await db.get_group_count()
    
    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE HANDLING
    # ─────────────────────────────────────────────────────────────────────
    
    if is_private:
        await db.get_or_create_user(user.id, user.first_name, user.username)
        health_server.stats['users'] = await db.get_user_count()
    
    # Typing indicator
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    
    try:
        # Get context (fixed variable name conflict)
        context_msgs = await db.get_user_context(user.id) if is_private else []
        
        # Generate response
        responses = await niyati_ai.generate_response(
            user_message=user_message,
            context=context_msgs,
            user_name=user.first_name,
            is_group=is_group
        )
        
        # Sometimes mention user (20% chance in private)
        if is_private and random.random() < 0.2:
            mention = StylishFonts.mention(user.first_name, user.id)
            if responses:
                idx = random.randint(0, len(responses) - 1)
                if random.random() < 0.5:
                    responses[idx] = f"{mention} {responses[idx]}"
                else:
                    responses[idx] = f"{responses[idx]}, {mention}"
        
        # Send responses
        await send_multi_messages(
            context.bot,
            chat.id,
            responses,
            reply_to=message.message_id if is_group else None,
            parse_mode=ParseMode.HTML
        )
        
        # Save to memory (private only)
        if is_private:
            await db.save_message(user.id, 'user', user_message)
            await db.save_message(user.id, 'assistant', ' '.join(responses))
        
        health_server.stats['messages'] += 1
        logger.info(f"✅ Responded with {len(responses)} messages")
        
    except Exception as e:
        logger.error(f"❌ Message handling error: {e}", exc_info=True)
        await message.reply_text("oops kuch gadbad... retry karo? 🫶")

# ============================================================================
# NEW MEMBER HANDLER
# ============================================================================

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining group"""
    chat = update.effective_chat
    
    if chat.type not in ['group', 'supergroup']:
        return
    
    group_data = await db.get_or_create_group(chat.id, chat.title)
    if not group_data.get('settings', {}).get('welcome_enabled', True):
        return
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        
        mention = StylishFonts.mention(member.first_name, member.id)
        
        messages = [
            f"arre! {mention} aaya/aayi group mein 🎉",
            "welcome yaar! ✨",
            "hope you enjoy here 💫"
        ]
        
        await send_multi_messages(context.bot, chat.id, messages, parse_mode=ParseMode.HTML)

# ============================================================================
# DAILY GEETA SCHEDULER
# ============================================================================

class GeetaScheduler:
    """Daily Geeta quote scheduler"""
    
    def __init__(self):
        self.task = None
        self.running = False
    
    async def send_daily_geeta(self, bot):
        """Send Geeta quote to all enabled groups"""
        groups = await db.get_all_groups()
        
        quote = niyati_ai.get_random_geeta_quote()
        header = "🌅 <b>Good Morning! Daily Geeta Quote:</b>\n\n"
        full_message = header + quote
        
        sent = 0
        for group in groups:
            settings = group.get('settings', {})
            if not settings.get('geeta_enabled', True):
                continue
            
            chat_id = group.get('chat_id')
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=full_message,
                    parse_mode=ParseMode.HTML
                )
                sent += 1
                await asyncio.sleep(0.1)
            except Forbidden:
                await db.mark_group_inactive(chat_id)
            except Exception as e:
                logger.debug(f"Geeta send fail {chat_id}: {e}")
        
        logger.info(f"📿 Daily Geeta sent to {sent} groups")
    
    async def scheduler_loop(self, bot):
        """Main scheduler loop"""
        ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
        
        while self.running:
            now = datetime.now(ist)
            
            # Calculate next run time
            target_time = now.replace(
                hour=Config.GEETA_HOUR,
                minute=Config.GEETA_MINUTE,
                second=0,
                microsecond=0
            )
            
            if now >= target_time:
                # Already passed today, schedule for tomorrow
                target_time += timedelta(days=1)
            
            # Wait until target time
            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"📿 Next Geeta quote in {wait_seconds/3600:.1f} hours")
            
            await asyncio.sleep(wait_seconds)
            
            if self.running:
                await self.send_daily_geeta(bot)
    
    async def start(self, bot):
        """Start scheduler"""
        self.running = True
        self.task = asyncio.create_task(self.scheduler_loop(bot))
        logger.info("📿 Geeta scheduler started")
    
    async def stop(self):
        """Stop scheduler"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


geeta_scheduler = GeetaScheduler()

# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"❌ Error: {context.error}", exc_info=True)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "oops technical issue 😅 retry karo?"
            )
        except:
            pass

# ============================================================================
# BOT SETUP & MAIN
# ============================================================================

def setup_handlers(app: Application):
    """Register all handlers"""
    
    # Private commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("meme", meme_command))
    app.add_handler(CommandHandler("shayari", shayari_command))
    app.add_handler(CommandHandler("geeta", geeta_command))
    
    # Group commands
    app.add_handler(CommandHandler("grouphelp", grouphelp_command))
    app.add_handler(CommandHandler("groupinfo", groupinfo_command))
    app.add_handler(CommandHandler("setgeeta", setgeeta_command))
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("groupstats", groupstats_command))
    
    # Admin commands
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))  # NEW
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("adminhelp", adminhelp_command))
    
    # Message handler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # New member handler
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_member
    ))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    logger.info("✅ All handlers registered")


async def main_async():
    """Async main"""
    
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║              🌸 NIYATI BOT v3.1 🌸                    ║
    ║           Teri Online Bestie is Starting!             ║
    ║                                                       ║
    ║   FIXES:                                              ║
    ║   ✅ Supabase init (no proxy error)                   ║
    ║   ✅ Group broadcast working                          ║
    ║   ✅ HTML formatting preserved                        ║
    ║   ✅ No "Forwarded" label                             ║
    ║   ✅ Daily Geeta scheduler                            ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    logger.info("🚀 Starting Niyati Bot v3.1...")
    logger.info(f"Model: {Config.OPENAI_MODEL}")
    logger.info(f"Port: {Config.PORT}")
    logger.info(f"Geeta Time: {Config.GEETA_HOUR}:{Config.GEETA_MINUTE:02d} IST")
    
    # Start health server
    await health_server.start()
    
    # Build application
    app = (
        Application.builder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    
    # Setup handlers
    setup_handlers(app)
    
    # Initialize
    await app.initialize()
    await app.start()
    
    # Start Geeta scheduler
    await geeta_scheduler.start(app.bot)
    
    # Start polling
    logger.info("🎯 Bot is polling...")
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await geeta_scheduler.stop()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await health_server.stop()


def main():
    """Main entry"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("⏹️ Interrupted")
    except Exception as e:
        logger.error(f"❌ Fatal: {e}", exc_info=True)


if __name__ == "__main__":
    main()
