"""
╔════════════════════════════════════════════════════════════════════════════╗
║                           NIYATI BOT v3.0                                  ║
║                    🌸 Teri Online Bestie 🌸                                ║
║                                                                            ║
║  Features:                                                                 ║
║  ✅ Real girl texting style (multiple short messages)                     ║
║  ✅ Supabase cloud database for memory                                    ║
║  ✅ Time-aware & mood-based responses                                     ║
║  ✅ User mentions with hyperlinks                                         ║
║  ✅ Forward message support                                               ║
║  ✅ Group commands (admin + user)                                         ║
║  ✅ Broadcast with HTML stylish fonts                                     ║
║  ✅ Health server for Render. com                                          ║
║  ✅ Geeta quotes scheduler                                                ║
║  ✅ Random shayari & memes                                                ║
║  ✅ User analytics & cooldown system                                       ║
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
    filters,
    JobQueue
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
    
    # Broadcast
    BROADCAST_RETRY_ATTEMPTS = int(os.getenv('BROADCAST_RETRY_ATTEMPTS', '3'))
    BROADCAST_RATE_LIMIT = float(os.getenv('BROADCAST_RATE_LIMIT', '0.05'))
    
    # NEW:  Cooldown & Features
    USER_COOLDOWN_SECONDS = int(os.getenv('USER_COOLDOWN_SECONDS', '3'))
    RANDOM_SHAYARI_CHANCE = float(os.getenv('RANDOM_SHAYARI_CHANCE', '0.15'))  # 15% chance
    RANDOM_MEME_CHANCE = float(os.getenv('RANDOM_MEME_CHANCE', '0.10'))  # 10% chance
    GROUP_RESPONSE_RATE = float(os. getenv('GROUP_RESPONSE_RATE', '0.3'))  # 30% chance
    PRIVACY_MODE = os.getenv('PRIVACY_MODE', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN required")
        if not cls. OPENAI_API_KEY: 
            errors.append("OPENAI_API_KEY required")
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            print("⚠️ Supabase not configured - using local storage only")
        if errors:
            raise ValueError(f"Config errors: {', '.join(errors)}")


Config. validate()

# ============================================================================
# LOGGING
# ============================================================================

logging. basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('niyati_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

for lib in ['httpx', 'telegram', 'openai', 'httpcore']: 
    logging.getLogger(lib).setLevel(logging.WARNING)

# ============================================================================
# HEALTH SERVER (Render.com)
# ============================================================================

class HealthServer:
    """HTTP health check server"""
    
    def __init__(self):
        self.app = web. Application()
        self.app.router. add_get('/', self.health)
        self.app.router. add_get('/health', self. health)
        self.app.router.add_get('/status', self.status)
        self.runner = None
        self.start_time = datetime.now(timezone.utc)
        self.stats = {'messages': 0, 'users': 0, 'groups':  0}
    
    async def health(self, request):
        return web.json_response({'status': 'healthy', 'bot':  'Niyati v3.0'})
    
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
        await site. start()
        logger.info(f"🌐 Health server on port {Config.PORT}")
    
    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


health_server = HealthServer()

# ============================================================================
# SUPABASE DATABASE
# ============================================================================

class Database:
    """Supabase database manager"""
    
    def __init__(self):
        self.client = None
        self.local_group_cache:  Dict[int, List[Dict]] = defaultdict(list)
        self.local_user_cache: Dict[int, Dict] = {}
        self._init_supabase()
    
    def _init_supabase(self):
        """Initialize Supabase client"""
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            logger.warning("⚠️ Supabase not configured")
            return
        
        try:
            self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            logger.info("✅ Supabase connected successfully")
        except Exception as e:
            logger. error(f"❌ Supabase init error: {e}")
            self.client = None
    
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
                            'first_name':  first_name,
                            'username': username,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }).eq('user_id', user_id).execute()
                        user['first_name'] = first_name
                        user['username'] = username
                    return user
                else:
                    new_user = {
                        'user_id': user_id,
                        'first_name':  first_name,
                        'username': username,
                        'messages': [],
                        'preferences': {
                            'meme_enabled': True,
                            'shayari_enabled': True,
                            'geeta_enabled': True
                        },
                        'total_messages': 0,
                        'created_at': datetime. now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    self.client.table('users').insert(new_user).execute()
                    logger.info(f"✅ New user:  {user_id} ({first_name})")
                    return new_user
                    
            except Exception as e: 
                logger.error(f"❌ Supabase user error: {e}")
        
        if user_id not in self.local_user_cache:
            self. local_user_cache[user_id] = {
                'user_id': user_id,
                'first_name': first_name,
                'username': username,
                'messages': [],
                'preferences': {'meme_enabled': True, 'shayari_enabled': True}
            }
        return self.local_user_cache[user_id]
    
    async def save_message(self, user_id: int, role: str, content: str):
        """Save message to history"""
        
        if self.client:
            try:
                result = self.client.table('users').select('messages').eq('user_id', user_id).execute()
                
                if result.data:
                    messages = result.data[0]. get('messages', []) or []
                    messages.append({
                        'role': role,
                        'content': content[: 500],
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
        
        if user_id in self.local_user_cache:
            msgs = self.local_user_cache[user_id]. get('messages', [])
            msgs.append({'role': role, 'content':  content[: 500]})
            self.local_user_cache[user_id]['messages'] = msgs[-Config.MAX_PRIVATE_MESSAGES:]
    
    async def get_user_context(self, user_id: int) -> List[Dict]:
        """Get conversation context"""
        
        if self.client:
            try:
                result = self.client.table('users').select('messages').eq('user_id', user_id).execute()
                if result.data and result.data[0].get('messages'):
                    return result. data[0]['messages'][-10:]
            except Exception as e:
                logger.error(f"❌ Get context error: {e}")
        
        if user_id in self. local_user_cache:
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
                logger.info(f"🧹 Memory cleared:  {user_id}")
                return
            except Exception as e:
                logger.error(f"❌ Clear memory error: {e}")
        
        if user_id in self.local_user_cache:
            self.local_user_cache[user_id]['messages'] = []
    
    async def update_preference(self, user_id: int, pref:  str, value: bool):
        """Update preference"""
        
        if self. client:
            try:
                result = self.client.table('users').select('preferences').eq('user_id', user_id).execute()
                if result.data:
                    prefs = result.data[0]. get('preferences', {}) or {}
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
        """Get all users for broadcast"""
        
        if self. client:
            try:
                result = self.client.table('users').select('user_id, first_name').execute()
                return result.data or []
            except Exception as e: 
                logger.error(f"❌ Get users error: {e}")
        
        return [{'user_id': uid, 'first_name': u.get('first_name')} 
                for uid, u in self.local_user_cache. items()]
    
    async def get_user_count(self) -> int:
        """Get user count"""
        
        if self.client:
            try:
                result = self. client.table('users').select('user_id', count='exact').execute()
                return result. count or 0
            except Exception as e:
                logger.error(f"❌ User count error: {e}")
        
        return len(self.local_user_cache)
    
    # ISSUE #15: NEW - Group member caching
    async def update_group_member_count(self, chat_id: int, member_count: int):
        """Update group member count"""
        if not self.client:
            return
        
        try:
            self.client.table('groups').update({
                'member_count': member_count,
                'updated_at': datetime. now(timezone.utc).isoformat()
            }).eq('chat_id', chat_id).execute()
        except Exception as e:
            logger.error(f"❌ Update member count error: {e}")
    
    async def get_or_create_group(self, chat_id: int, chat_title: str = None) -> Dict:
        """Get or create group"""
        
        default_group = {
            'chat_id': chat_id,
            'chat_title': chat_title,
            'settings': {'geeta_enabled': True, 'welcome_enabled': True}
        }
        
        if self.client:
            try:
                result = self.client. table('groups').select('*').eq('chat_id', chat_id).execute()
                
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
                        'settings': {'geeta_enabled': True, 'welcome_enabled': True},
                        'is_active': True,
                        'member_count': 0,
                        'created_at': datetime. now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    self.client.table('groups').insert(new_group).execute()
                    logger.info(f"✅ New group: {chat_id}")
                    return new_group
                    
            except Exception as e:
                logger. error(f"❌ Group error: {e}")
        
        return default_group
    
    async def update_group_settings(self, chat_id: int, setting: str, value):
        """Update group setting"""
        
        if not self.client:
            return
        
        try:
            result = self.client.table('groups').select('settings').eq('chat_id', chat_id).execute()
            if result.data:
                settings = result.data[0].get('settings', {}) or {}
                settings[setting] = value
                self.client.table('groups').update({
                    'settings': settings,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).eq('chat_id', chat_id).execute()
        except Exception as e:
            logger.error(f"❌ Update group error: {e}")
    
    async def get_group_count(self) -> int:
        """Get group count"""
        
        if self.client:
            try:
                result = self. client.table('groups').select('chat_id', count='exact').execute()
                return result.count or 0
            except: 
                pass
        return 0
    
    async def get_all_groups(self) -> List[Dict]:
        """Get all groups"""
        
        if self. client:
            try:
                result = self.client.table('groups').select('chat_id, chat_title').eq('is_active', True).execute()
                return result.data or []
            except: 
                pass
        return []
    
    # ISSUE #12: Memory leak prevention - cleanup old messages
    async def cleanup_old_messages(self, days:  int = 30):
        """Clean up old messages (prevent memory leak)"""
        if not self.client:
            return
        
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            # This would need a custom function in Supabase to delete old messages
            logger.info(f"🧹 Cleanup:  Messages older than {days} days")
        except Exception as e: 
            logger.error(f"❌ Cleanup error: {e}")
    
    def add_group_message(self, chat_id: int, user_name: str, content: str):
        """Add to local cache with duplicate detection"""
        
        # ISSUE #11: Duplicate detection
        recent = self.local_group_cache. get(chat_id, [])
        if recent and recent[-1]. get('content') == content[:200] and recent[-1].get('user') == user_name:
            return  # Skip duplicate
        
        self.local_group_cache[chat_id]. append({
            'user': user_name,
            'content': content[:200],
            'time': datetime.now(timezone.utc).isoformat()
        })
        self.local_group_cache[chat_id] = self.local_group_cache[chat_id][-Config.MAX_GROUP_MESSAGES:]
    
    def get_group_context(self, chat_id: int) -> List[Dict]:
        """Get local cache"""
        return self.local_group_cache.get(chat_id, [])
    
    # ISSUE #20: User analytics
    async def log_user_activity(self, user_id: int, action: str):
        """Log user activity for analytics"""
        if not self.client:
            return
        
        try:
            self.client.table('user_analytics').insert({
                'user_id': user_id,
                'action': action,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            logger. debug(f"Analytics error: {e}")


db = Database()

# ============================================================================
# RATE LIMITER WITH COOLDOWN (ISSUE #16)
# ============================================================================

class RateLimiter:
    """Rate limiting with cooldown system"""
    
    def __init__(self):
        self.requests = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.cooldowns = {}  # user_id -> last_message_time
        self.lock = threading.Lock()
    
    def check(self, user_id: int) -> Tuple[bool, str]:
        """Check rate limits"""
        now = datetime.now(timezone.utc)
        
        with self.lock:
            # Check cooldown - ISSUE #16
            if user_id in self. cooldowns:
                last_time = self.cooldowns[user_id]
                if (now - last_time).total_seconds() < Config.USER_COOLDOWN_SECONDS: 
                    return False, "cooldown"
            
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
            self.cooldowns[user_id] = now  # Update cooldown
            return True, ""
    
    def get_daily_total(self) -> int:
        return sum(len(r['day']) for r in self.requests.values())
    
    # ISSUE #12: Cleanup old cooldowns to prevent memory leak
    def cleanup_cooldowns(self):
        """Remove old cooldowns"""
        now = datetime.now(timezone.utc)
        expired = [uid for uid, time in self.cooldowns.items() 
                   if (now - time).total_seconds() > 3600]
        for uid in expired:
            del self.cooldowns[uid]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} cooldowns")


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
        utc_now = datetime.now(timezone. utc)
        return utc_now.astimezone(ist)
    
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
            'morning': ["good morning ☀️", "uth gayi tu bhi? ", "subah subah!  ✨"],
            'afternoon': ["heyyy", "lunch ho gaya? ", "afternoon vibes 🌤️"],
            'evening': ["hiii 💫", "chai time!  ☕", "shaam ho gayi yaar"],
            'night': ["heyy 🌙", "night owl? ", "aaj kya plan hai"],
            'late_night': ["tu bhi jaag rahi?  👀", "insomnia gang 🦉", "neend nahi aa rahi? "]
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
        
        return random. choices(Mood.MOODS, weights=weights)[0]
    
    @staticmethod
    def get_mood_instruction(mood: str) -> str:
        """Get mood instruction for AI"""
        instructions = {
            'happy': "Mood:  HAPPY 😊 - Extra friendly, emojis zyada, enthusiastic! ",
            'playful': "Mood: PLAYFUL 😏 - Thoda teasing, flirty jokes, fun!",
            'soft': "Mood: SOFT 🥺 - Caring, sweet, comforting vibes",
            'sleepy':  "Mood: SLEEPY 😴 - Short lazy replies, 'hmm', 'haan', '*yawns*'",
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
    def apply_style(text: str, style: str) -> str:
        """Apply style by name"""
        styles = {
            'bold': StylishFonts.bold,
            'italic': StylishFonts.italic,
            'underline': StylishFonts.underline,
            'code': StylishFonts. code,
            'spoiler':  StylishFonts.spoiler
        }
        return styles.get(style, lambda x: x)(text)


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
        for pattern in ContentFilter. SENSITIVE_PATTERNS:
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
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        logger.info(f"🤖 NiyatiAI initialized:  {Config.OPENAI_MODEL}")
    
    def _build_system_prompt(self, mood: str, time_period: str, user_name: str = None) -> str:
        """Build dynamic system prompt"""
        
        mood_inst = Mood.get_mood_instruction(mood)
        
        prompt = f"""Tu hai "Niyati" - ek 20-21 saal ki college girl, online bestie! 

🎭 PERSONALITY: 
- Caring, thodi dramatic, kabhi kabhi tease karti hai
- Interests: Music (Arijit Singh fan! ), movies, chai, late night talks, memes
- Texting style: Real ladki jaisi - short messages, natural feel

⏰ TIME:  {time_period. upper()}
{mood_inst}

{'👤 User name: ' + user_name if user_name else ''}

💬 RESPONSE RULES - BAHUT IMPORTANT:
1.  SPLIT responses into 2-4 SHORT messages (each 5-15 words max)
2. Separate each message with |||
3. First message: reaction/acknowledgment
4. Next messages: actual reply
5. Use natural fillers: "arre", "hmm", "yaar", "btw", "waise"
6. Emojis:  1-2 per message max, not in every message
7. Sometimes just react:  "😂", "🥺", "omg"

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
                        "role": msg. get('role', 'user'),
                        "content": msg.get('content', '')
                    })
            
            messages.append({"role": "user", "content": user_message})
            
            max_tokens = 100 if is_group else Config. OPENAI_MAX_TOKENS
            
            response = await self.client.chat. completions.create(
                model=Config.OPENAI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=Config. OPENAI_TEMPERATURE,
                presence_penalty=0. 7,
                frequency_penalty=0.4
            )
            
            reply = response.choices[0].message.content. strip()
            
            # ISSUE #9: Better message splitting on newlines
            if '|||' in reply:
                parts = [p.strip() for p in reply.split('|||') if p.strip()]
            elif '\n' in reply:  # FIXED: Split on single newline too
                parts = [p.strip() for p in reply.split('\n') if p.strip()]
            else:
                parts = [reply]
            
            return parts[: 4]
            
        except RateLimitError:
            logger.error("❌ OpenAI Rate Limit")
            return ["hmm thoda slow ho gaya yaar...  ek minute?  🫶"]
        except Exception as e: 
            logger.error(f"❌ AI Error: {e}")
            return ["sorry yaar kuch gadbad...  dobara try karo?  💫"]
    
    async def generate_shayari(self, mood: str = "neutral") -> str:
        """Generate shayari"""
        shayaris = {
            'happy': [
                "khushiyon ki baarish ho, dil khil jaye\nteri baat se ye din haseen lage ✨",
                "chhoti chhoti khushiyan, badi si muskaan\nyahi toh hai zindagi ki pehchaan 💫"
            ],
            'sad': [
                "udaasi bhi guzar jayegi\nwaqt sab theek kar deta hai 🌸",
                "dard mein bhi ek khoobsurti hai\nsamjhega woh jo dil se dekhega 💕"
            ],
            'neutral': [
                "dil ki raahon mein tera saath ho\nkhwabon ki roshni hamesha chale ✨",
                "baatein khatam na ho kabhi\nyeh silsila yun hi chale 💫"
            ]
        }
        return random.choice(shayaris.get(mood, shayaris['neutral']))
    
    async def generate_geeta_quote(self) -> str:
        """Generate Geeta quote"""
        quotes = [
            "🙏 <b>कर्मण्येवाधिकारस्ते</b>\nKarm kar, phal ki chinta mat kar",
            "🙏 <b>योगः कर्मसु कौशलम्</b>\nYoga is skill in action",
            "🙏 <b>मन की शांति सबसे बड़ी शक्ति है</b>\nPeace of mind is greatest strength",
            "🙏 <b>ज्ञान से बड़ा कोई प्रकाश नहीं</b>\nNo light greater than knowledge"
        ]
        return random. choice(quotes)
    
    # ISSUE #13: Random trigger helpers
    async def get_random_bonus(self) -> Optional[str]:
        """Get random shayari or meme"""
        rand = random.random()
        
        if rand < Config.RANDOM_SHAYARI_CHANCE:
            mood = Mood.get_random_mood()
            return await self. generate_shayari(mood)
        elif rand < Config. RANDOM_SHAYARI_CHANCE + Config. RANDOM_MEME_CHANCE:
            return self._get_random_meme()
        
        return None
    
    @staticmethod
    def _get_random_meme() -> str:
        """Get random meme"""
        memes = [
            "life kya hai bhai...  https://t.me/memepacks",
            "relatable moment 😂",
            "us moment 🤝",
            "kya logic hai 🤦‍♀️",
            "haan bilkul 😏",
            "💀💀",
            "rip 🪦"
        ]
        return random. choice(memes)


niyati_ai = NiyatiAI()

# ============================================================================
# MESSAGE SENDER
# ============================================================================

async def send_multi_messages(
    bot,
    chat_id: int,
    messages: List[str],
    reply_to:  int = None,
    parse_mode: str = None
):
    """Send multiple messages with natural delays"""
    
    for i, msg in enumerate(messages):
        if i > 0:
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except: 
                pass
            
            if Config.MULTI_MESSAGE_ENABLED:
                delay = (Config.TYPING_DELAY_MS / 1000) + random.uniform(0.2, 0.8)
            else:
                delay = 0.1
            await asyncio.sleep(delay)
        
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_to_message_id=reply_to if i == 0 else None,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Send error: {e}")

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def start_command(update: Update, context: ContextTypes. DEFAULT_TYPE):
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
            f"hiii {user_mention}!  💫",
            "main Niyati...  teri nayi online bestie ✨",
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
    
    logger.info(f"Start:  {user. id} in {'private' if is_private else 'group'}")


async def help_command(update:  Update, context: ContextTypes. DEFAULT_TYPE):
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
• /stats - Your stats

<b>Tips:</b>
• Seedhe message bhejo, main reply karungi
• Forward bhi kar sakte ho kuch
• Group mein @mention karo ya reply do

Made with 💕 by Niyati
"""
    await update.message. reply_html(help_text)


async def about_command(update: Update, context:  ContextTypes.DEFAULT_TYPE):
    """Handle /about"""
    about_text = """
🌸 <b>About Niyati</b> 🌸

Hiii!  Main Niyati hoon 💫

<b>Kaun hoon main: </b>
• 20-21 saal ki college girl
• Teri online bestie
• Music lover (Arijit Singh fan!  🎵)
• Chai addict ☕
• Late night talks expert 🌙

<b>Kya karti hoon: </b>
• Teri baatein sunti hoon
• Shayari sunati hoon kabhi kabhi
• Memes share karti hoon
• Bore nahi hone deti 😊

<b>Kya nahi karti: </b>
• Boring formal baatein
• Fake promises
• Real world claims

Bas yahi hoon main... teri Niyati ✨
"""
    await update.message.reply_html(about_text)


async def mood_command(update: Update, context:  ContextTypes.DEFAULT_TYPE):
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
    
    emoji = mood_emojis. get(mood, '✨')
    
    messages = [
        f"aaj ka mood?  {emoji}",
        f"{mood. upper()} vibes hai yaar",
        f"waise {time_period} ho gayi...  time flies!"
    ]
    
    await send_multi_messages(context. bot, update.effective_chat. id, messages)


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forget"""
    user = update.effective_user
    await db.clear_user_memory(user.id)
    
    messages = [
        "done! 🧹",
        "sab bhool gayi main",
        "fresh start?  chaloooo ✨"
    ]
    
    await send_multi_messages(context. bot, update.effective_chat. id, messages)


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle meme preference"""
    user = update.effective_user
    args = context.args
    
    if not args or args[0]. lower() not in ['on', 'off']: 
        await update.message.reply_text("Use:  /meme on ya /meme off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_preference(user.id, 'meme', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update. message.reply_text(f"Memes:  {status}")


async def shayari_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle shayari preference"""
    user = update.effective_user
    args = context.args
    
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /shayari on ya /shayari off")
        return
    
    value = args[0]. lower() == 'on'
    await db.update_preference(user.id, 'shayari', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message. reply_text(f"Shayari: {status}")


# ISSUE #8: Missing /users command
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics (admin only)"""
    if not await admin_check(update):
        await update.message.reply_text("❌ Admin only!")
        return
    
    users = await db.get_all_users()
    user_list = "\n".join([f"• {u.get('first_name', 'Unknown')} (ID: {u.get('user_id')})" 
                           for u in users[: 20]])
    
    text = f"""
👥 <b>User List (Last 20)</b>

{user_list if user_list else 'No users yet'}

<b>Total Users:</b> {len(users)}
"""
    await update. message.reply_html(text)


# ============================================================================
# GROUP COMMANDS
# ============================================================================

async def grouphelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group help command"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message. reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    help_text = """
🌸 <b>Niyati Group Commands</b> 🌸

<b>Everyone: </b>
• /grouphelp - Yeh menu
• /groupinfo - Group info
• @NiyatiBot [message] - Mujhse baat karo
• Reply to my message - Main jawab dungi

<b>Admin Only:</b>
• /setgeeta on/off - Daily Geeta quote
• /setwelcome on/off - Welcome messages
• /groupstats - Group statistics
• /groupsettings - Current settings

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

<b>Name:</b> {chat.title}
<b>ID:</b> <code>{chat.id}</code>

<b>Settings:</b>
• Geeta Quotes:  {'✅' if settings.get('geeta_enabled', True) else '❌'}
• Welcome Msg: {'✅' if settings. get('welcome_enabled', True) else '❌'}
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
    """Toggle Geeta quotes"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update. message.reply_text("Yeh command sirf groups ke liye hai!")
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
    await update. message.reply_text(f"Daily Geeta Quote: {status}")


async def setwelcome_command(update:  Update, context: ContextTypes. DEFAULT_TYPE):
    """Toggle welcome messages"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message. reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sirf admins yeh kar sakte hain!")
        return
    
    args = context.args
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message. reply_text("Use: /setwelcome on ya /setwelcome off")
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

<b>Group: </b> {chat.title}
<b>Cached Messages:</b> {cached_msgs}
<b>Max Cache: </b> {Config.MAX_GROUP_MESSAGES}
"""
    await update.message. reply_html(stats_text)


async def groupsettings_command(update: Update, context:  ContextTypes.DEFAULT_TYPE):
    """Show current group settings"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message. reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sirf admins yeh kar sakte hain!")
        return
    
    group_data = await db.get_or_create_group(chat. id, chat.title)
    settings = group_data.get('settings', {})
    
    settings_text = f"""
⚙️ <b>Group Settings</b>

<b>Group:</b> {chat.title}

<b>Current Settings:</b>
• Geeta Quotes: {'✅ ON' if settings.get('geeta_enabled', True) else '❌ OFF'}
• Welcome Messages: {'✅ ON' if settings.get('welcome_enabled', True) else '❌ OFF'}

<b>Commands to Change:</b>
• /setgeeta on/off
• /setwelcome on/off
"""
    await update.message. reply_html(settings_text)

# ============================================================================
# ADMIN COMMANDS
# ============================================================================

async def admin_check(update:  Update) -> bool:
    """Check if user is bot admin"""
    return update.effective_user.id in Config.ADMIN_IDS


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot stats (admin only)"""
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
<b>Model: </b> {Config.OPENAI_MODEL}

<b>Limits:</b>
• Per Minute: {Config.MAX_REQUESTS_PER_MINUTE}
• Per Day: {Config.MAX_REQUESTS_PER_DAY}
"""
    await update.message. reply_html(stats_text)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users"""
    if not await admin_check(update):
        await update.message.reply_text("❌ Admin only!")
        return
    
    args = context.args
    if not args or args[0] != Config.BROADCAST_PIN:
        await update.message. reply_text(
            "🔐 <b>Broadcast Command</b>\n\n"
            "Usage: /broadcast [PIN] [message]\n"
            "Example: /broadcast 1234 <b>Hello</b> everyone!\n\n"
            "<b>Supported HTML Tags:</b>\n"
            "&lt;b&gt;bold&lt;/b&gt;, &lt;i&gt;italic&lt;/i&gt;, &lt;u&gt;underline&lt;/u&gt;, "
            "&lt;s&gt;strike&lt;/s&gt;, &lt;code&gt;mono&lt;/code&gt;, &lt;tg-spoiler&gt;spoiler&lt;/tg-spoiler&gt;",
            parse_mode=ParseMode.HTML
        )
        return
    
    message_text = ' '.join(args[1:]) if len(args) > 1 else None
    reply_msg = update.message.reply_to_message
    
    if not message_text and not reply_msg:
        await update.message.reply_text("❌ Message ya reply do broadcast ke liye!")
        return
    
    await update.message.reply_text("📢 Broadcasting...  please wait")
    
    users = await db.get_all_users()
    success = 0
    failed = 0
    
    for user in users:
        user_id = user. get('user_id')
        
        if not user_id or user_id <= 0:
            failed += 1
            continue
        
        retry_count = 0
        sent = False
        
        while retry_count < Config. BROADCAST_RETRY_ATTEMPTS and not sent:
            try: 
                if reply_msg:
                    if reply_msg.text:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=reply_msg. text,
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        await context. bot.forward_message(
                            chat_id=user_id,
                            from_chat_id=update.effective_chat.id,
                            message_id=reply_msg.message_id
                        )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        parse_mode=ParseMode.HTML
                    )
                
                success += 1
                sent = True
                await asyncio.sleep(Config. BROADCAST_RATE_LIMIT)
                
            except BadRequest as e:
                logger.debug(f"BadRequest {user_id}: {e}")
                failed += 1
                sent = True
                break
                
            except Forbidden: 
                logger.debug(f"Forbidden {user_id}")
                failed += 1
                sent = True
                break
                
            except (NetworkError, TimedOut, RetryAfter) as e:
                retry_count += 1
                if retry_count < Config.BROADCAST_RETRY_ATTEMPTS:
                    wait_time = min(2 ** retry_count, 10)
                    await asyncio.sleep(wait_time)
                else:
                    logger.debug(f"Failed after retries {user_id}: {e}")
                    failed += 1
                    sent = True
                    
            except Exception as e:
                logger.debug(f"Broadcast error {user_id}: {e}")
                failed += 1
                sent = True
    
    report = (
        f"✅ <b>Broadcast Complete! </b>\n\n"
        f"<b>Success:</b> {success}\n"
        f"<b>Failed:</b> {failed}\n"
        f"<b>Total Users:</b> {len(users)}"
    )
    
    if failed > 0:
        report += f"\n\n⚠️ <i>Failed users likely blocked or inactive</i>"
    
    await update.message.reply_html(report)
    logger.info(f"📢 Broadcast complete: {success} success, {failed} failed")


# ============================================================================
# ADMIN COMMANDS (Continued)
# ============================================================================

async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin commands"""
    if not await admin_check(update):
        await update.message.reply_text("❌ Admin only!")
        return
    
    help_text = """
🔐 <b>Admin Commands</b>

<b>Statistics:</b>
• /stats - Bot statistics
• /users - User list

<b>Broadcast (with PIN):</b>
• /broadcast [PIN] [message]
• Reply to message + /broadcast [PIN]

<b>HTML Styles for Broadcast:</b>
• <code>&lt;b&gt;bold&lt;/b&gt;</code> → <b>bold</b>
• <code>&lt;i&gt;italic&lt;/i&gt;</code> → <i>italic</i>
• <code>&lt;u&gt;underline&lt;/u&gt;</code> → <u>underline</u>
• <code>&lt;s&gt;strike&lt;/s&gt;</code> → <s>strike</s>
• <code>&lt;code&gt;mono&lt;/code&gt;</code> → <code>mono</code>
• <code>&lt;blockquote&gt;quote&lt;/blockquote&gt;</code> → quote
• <code>&lt;tg-spoiler&gt;spoiler&lt;/tg-spoiler&gt;</code> → spoiler

<b>Example:  </b>
/broadcast PIN <b>Hello</b> everyone!  Check this <i>special</i> offer 🎉
"""
    await update.message.reply_html(help_text)


# ISSUE #19:  Geeta quote scheduler - NEW
async def send_daily_geeta(context: ContextTypes.DEFAULT_TYPE):
    """Send daily Geeta quote to all groups"""
    groups = await db.get_all_groups()
    quote = await niyati_ai.generate_geeta_quote()
    
    sent = 0
    for group in groups:
        chat_id = group.get('chat_id')
        settings = group.get('settings', {})
        
        if not settings.get('geeta_enabled', True):
            continue
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=quote,
                parse_mode=ParseMode. HTML
            )
            sent += 1
            await asyncio.sleep(0.1)  # Rate limit
        except Exception as e:
            logger.debug(f"Geeta send error to {chat_id}: {e}")
    
    logger.info(f"📿 Daily Geeta sent to {sent} groups")


# ISSUE #20: User stats command - NEW
async def user_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's personal stats"""
    user = update.effective_user
    user_data = await db.get_or_create_user(user.id, user.first_name, user.username)
    
    messages = user_data.get('messages', [])
    prefs = user_data.get('preferences', {})
    
    stats_text = f"""
📊 <b>Your Stats</b>

<b>User: </b> {user.first_name}
<b>ID:</b> <code>{user.id}</code>
<b>Username:</b> @{user.username if user.username else 'Not set'}

<b>Conversation: </b>
• Messages: {len(messages)}
• Joined: {user_data.get('created_at', 'Unknown')[: 10]}

<b>Your Preferences:</b>
• Memes: {'✅' if prefs.get('meme_enabled', True) else '❌'}
• Shayari: {'✅' if prefs.get('shayari_enabled', True) else '❌'}
• Geeta: {'✅' if prefs.get('geeta_enabled', True) else '❌'}

<b>Commands:</b>
• /forget - Clear your memory
• /meme on/off - Toggle memes
• /shayari on/off - Toggle shayari
"""
    await update.message.reply_html(stats_text)


# ============================================================================
# MAIN MESSAGE HANDLER - ISSUE #17 (COMPLETED)
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages - COMPLETE"""
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    
    # Get message text
    if message.forward_date:
        user_message = f"[Forwarded]:  {message.text or message.caption or ''}"
    else:
        user_message = message.text or message.caption or ""
    
    if not user_message or user_message.startswith('/'):  # ISSUE #14: Command prefix handling
        return
    
    is_private = chat.type == 'private'
    is_group = chat.type in ['group', 'supergroup']
    
    logger.info(f"📨 {user. id}:  {user_message[: 50]}...")
    
    # Rate limiting with cooldown - ISSUE #16
    allowed, reason = rate_limiter.check(user. id)
    if not allowed: 
        if reason == "cooldown":
            return  # Silent cooldown
        elif reason == "minute":
            await message.reply_text("arre thoda slow 😅 ek minute ruk")
        else:
            await message.reply_text("aaj bahut baat ho gayi yaar 💫 kal milte hain!")
        return
    
    # Safety checks
    if ContentFilter.contains_sensitive(user_message):
        await message.reply_text("hey!  sensitive info mat share karo yaar 💕")
        return
    
    if ContentFilter.detect_distress(user_message):
        await message.reply_html(
            "yaar...  🥺\n"
            "mujhe tension ho rahi hai tere liye\n\n"
            "<b>Please talk to someone:</b>\n"
            "📞 iCall: 9152987821\n"
            "📞 Vandrevala: 1860-2662-345"
        )
        return
    
    # ────────────────────────────────────────────────────────────────
    # GROUP HANDLING - ISSUE #10 (Response Rate)
    # ────────────────────────────────────────────────────────────────
    
    if is_group:
        db. add_group_message(chat.id, user.first_name, user_message)
        
        should_respond = False
        bot_username = f"@{Config.BOT_USERNAME}"
        
        # Check if mentioned
        if bot_username. lower() in user_message.lower():
            should_respond = True
            user_message = user_message.replace(bot_username, '').strip()
        
        # Check if reply to bot
        if message.reply_to_message and message.reply_to_message. from_user: 
            if message.reply_to_message.from_user.username == Config.BOT_USERNAME:
                should_respond = True
        
        # ISSUE #10: Random response rate in groups
        if not should_respond:
            if random.random() < Config.GROUP_RESPONSE_RATE: 
                should_respond = True
            else:
                return
        
        await db.get_or_create_group(chat.id, chat.title)
        health_server.stats['groups'] = await db.get_group_count()
        
        # Log group activity
        await db.log_user_activity(user.id, f"group_message:{chat.id}")
    
    # ────────────────────────────────────────────────────────────────
    # PRIVATE HANDLING
    # ────────────────────────────────────────────────────────────────
    
    if is_private:
        user_data = await db.get_or_create_user(user. id, user.first_name, user.username)
        health_server.stats['users'] = await db.get_user_count()
        
        # Log private activity
        await db.log_user_activity(user.id, "private_message")
    
    # Typing indicator
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    except: 
        pass
    
    try:
        # Get context
        context_msgs = await db.get_user_context(user.id) if is_private else []
        
        # Generate response
        responses = await niyati_ai. generate_response(
            user_message=user_message,
            context=context_msgs,
            user_name=user.first_name,
            is_group=is_group
        )
        
        # ISSUE #13: Random bonus (shayari/meme)
        if is_private and random.random() < 0.1:  # 10% chance
            bonus = await niyati_ai. get_random_bonus()
            if bonus:
                responses.append(bonus)
        
        # Sometimes mention user in response
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
            context. bot,
            chat. id,
            responses,
            reply_to=message. message_id if is_group else None,
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
        try:
            await message.reply_text("oops kuch gadbad...  retry karo?  🫶")
        except:
            pass


# ============================================================================
# NEW MEMBER HANDLER
# ============================================================================

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining group"""
    chat = update.effective_chat
    
    if chat.type not in ['group', 'supergroup']:
        return
    
    group_data = await db.get_or_create_group(chat.id, chat.title)
    if not group_data. get('settings', {}).get('welcome_enabled', True):
        return
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        
        mention = StylishFonts. mention(member.first_name, member.id)
        
        messages = [
            f"arre!  {mention} aaya/aayi group mein 🎉",
            "welcome yaar! ✨",
            "hope you enjoy here 💫"
        ]
        
        await send_multi_messages(context.bot, chat.id, messages, parse_mode=ParseMode.HTML)
        
        # Log new member
        await db.log_user_activity(member.id, f"joined_group:{chat.id}")


# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"❌ Error:  {context.error}", exc_info=True)
    
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

def setup_handlers(app:  Application):
    """Register all handlers"""
    
    # Private commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("meme", meme_command))
    app.add_handler(CommandHandler("shayari", shayari_command))
    app.add_handler(CommandHandler("stats", user_stats_command))  # User stats
    
    # Group commands
    app.add_handler(CommandHandler("grouphelp", grouphelp_command))
    app.add_handler(CommandHandler("groupinfo", groupinfo_command))
    app.add_handler(CommandHandler("setgeeta", setgeeta_command))
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("groupstats", groupstats_command))
    app.add_handler(CommandHandler("groupsettings", groupsettings_command))
    
    # Admin commands
    app.add_handler(CommandHandler("users", users_command))  # ISSUE #8
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("adminhelp", adminhelp_command))
    
    # Message handler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # New member handler
    app.add_handler(MessageHandler(
        filters.StatusUpdate. NEW_CHAT_MEMBERS,
        handle_new_member
    ))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    logger.info("✅ All handlers registered")


async def setup_jobs(app: Application):
    """Setup scheduled jobs - ISSUE #19"""
    job_queue = app.job_queue
    
    # Daily Geeta quote at 6 AM IST
    job_queue.run_daily(
        send_daily_geeta,
        time=datetime. now(pytz.timezone(Config.DEFAULT_TIMEZONE)).replace(hour=6, minute=0, second=0),
        name='daily_geeta'
    )
    
    # Cleanup cooldowns every hour - ISSUE #12
    def cleanup_task():
        rate_limiter.cleanup_cooldowns()
    
    job_queue.run_repeating(cleanup_task, interval=3600, first=3600, name='cleanup')
    
    logger.info("✅ Scheduled jobs setup")


async def main_async():
    """Async main"""
    
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║              🌸 NIYATI BOT v3.0 🌸                    ║
    ║           Teri Online Bestie is Starting!              ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    logger.info("🚀 Starting Niyati Bot...")
    logger.info(f"Model: {Config. OPENAI_MODEL}")
    logger.info(f"Port: {Config.PORT}")
    logger.info(f"Privacy Mode: {'ON' if Config.PRIVACY_MODE else 'OFF'}")
    
    # Start health server
    await health_server.start()
    
    # Build application
    app = (
        Application.builder()
        .token(Config. TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    
    # Setup handlers
    setup_handlers(app)
    
    # Setup scheduled jobs - ISSUE #19
    await setup_jobs(app)
    
    # Initialize
    await app.initialize()
    await app.start()
    
    # Start polling
    logger.info("🎯 Bot is polling...")
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
    # Keep running
    try:
        while True:
            await asyncio. sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await health_server.stop()
        logger.info("⏹️ Bot stopped")


def main():
    """Main entry"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger. info("⏹️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal:  {e}", exc_info=True)


if __name__ == "__main__":
    main()
