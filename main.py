"""
╔════════════════════════════════════════════════════════════════════════════╗
║                           NIYATI BOT v3.0                                  ║
║                    🌸 Teri Online Bestie 🌸                                ║
║                                                                            ║
║  Features:                                                                 ║
║  ✅ Real girl texting style (multiple short messages)                     ║
║  ✅ Supabase cloud database for memory (FIXED)                            ║
║  ✅ Time-aware & mood-based responses                                     ║
║  ✅ User mentions with hyperlinks                                         ║
║  ✅ Forward message support                                               ║
║  ✅ Group commands (admin + user)                                         ║
║  ✅ Broadcast with HTML stylish fonts                                     ║
║  ✅ Health server for Render.com                                          ║
║  ✅ Geeta quotes scheduler                                                ║
║  ✅ Random shayari & memes                                                ║
║  ✅ User analytics & cooldown system                                      ║
║  ✅ Memory leak prevention & cleanup                                      ║
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
import time
import weakref

# Third-party imports
from aiohttp import web
import pytz
import httpx

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
# Groq
from groq import AsyncGroq
# Gemini
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'Niyati_personal_bot')
    
    # OpenAI (Multi-Key Support)
    # Pehle naya variable check karega
    OPENAI_API_KEYS_STR = os.getenv('OPENAI_API_KEYS', '')
    
    # Agar naya nahi mila, toh purana check karega
    if not OPENAI_API_KEYS_STR:
        OPENAI_API_KEYS_STR = os.getenv('OPENAI_API_KEY', '')
        
    # List banayega
    API_KEYS_LIST = [k.strip() for k in OPENAI_API_KEYS_STR.split(',') if k.strip()]
    
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '200'))
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.85'))
    # Config class mein yeh add karo:
    GROQ_API_KEYS_LIST = [...]  # Groq keys list
    GEMINI_API_KEYS_LIST = [...]  # Gemini keys list
    GROQ_MODEL = "llama-3.3-70b-versatile"
    GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"
    
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
    
    # Memory Management
    MAX_LOCAL_USERS_CACHE = int(os.getenv('MAX_LOCAL_USERS_CACHE', '10000'))
    MAX_LOCAL_GROUPS_CACHE = int(os.getenv('MAX_LOCAL_GROUPS_CACHE', '1000'))
    CACHE_CLEANUP_INTERVAL = int(os.getenv('CACHE_CLEANUP_INTERVAL', '3600'))
    
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
    
    # Cooldown & Features
    USER_COOLDOWN_SECONDS = int(os.getenv('USER_COOLDOWN_SECONDS', '3'))
    RANDOM_SHAYARI_CHANCE = float(os.getenv('RANDOM_SHAYARI_CHANCE', '0.15'))
    RANDOM_MEME_CHANCE = float(os.getenv('RANDOM_MEME_CHANCE', '0.10'))
    GROUP_RESPONSE_RATE = float(os.getenv('GROUP_RESPONSE_RATE', '0.3'))
    PRIVACY_MODE = os.getenv('PRIVACY_MODE', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN required")
        
        # YAHAN FIX KIYA HAI: Ab ye API_KEYS_LIST check karega
        if not cls.API_KEYS_LIST:
            errors.append("OPENAI_API_KEYS required")
            
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
        return web.json_response({'status': 'healthy', 'bot': 'Niyati v3.0'})
    
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
# SUPABASE CLIENT - FULLY FIXED VERSION
# ============================================================================

class SupabaseClient:
    """
    Custom Supabase REST API Client
    ✅ FIXED: Better error handling, proper URL encoding, connection pooling
    """
    
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        self.rest_url = f"{self.url}/rest/v1"
        self._client = None
        self._verified = False
        self._lock = asyncio.Lock()
        logger.info("✅ SupabaseClient initialized")
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create async client with connection pooling"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return self._client
    
    async def close(self):
        """Close the client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("✅ Supabase client closed")
    
    async def verify_connection(self) -> bool:
        """Verify database connection and tables exist"""
        if self._verified:
            return True
        
        async with self._lock:
            if self._verified:
                return True
            
            try:
                client = self._get_client()
                response = await client.get(f"{self.rest_url}/users?select=user_id&limit=1")
                
                if response.status_code == 200:
                    self._verified = True
                    logger.info("✅ Supabase tables verified")
                    return True
                elif response.status_code == 404:
                    logger.error("❌ Supabase table 'users' not found! Run the SQL setup.")
                    return False
                else:
                    logger.error(f"❌ Supabase verification failed: {response.status_code}")
                    return False
            except Exception as e:
                logger.error(f"❌ Supabase connection error: {e}")
                return False
    
    async def select(self, table: str, columns: str = '*', 
                     filters: Dict = None, limit: int = None) -> List[Dict]:
        """SELECT from table"""
        try:
            client = self._get_client()
            url = f"{self.rest_url}/{table}?select={columns}"
            
            if filters:
                for key, value in filters.items():
                    if isinstance(value, str):
                        url += f"&{key}=eq.{value}"
                    else:
                        url += f"&{key}=eq.{value}"
            
            if limit:
                url += f"&limit={limit}"
            
            response = await client.get(url)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.debug(f"Table '{table}' not found")
                return []
            else:
                logger.error(f"Supabase SELECT error {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Supabase SELECT exception: {e}")
            return []
    
    async def insert(self, table: str, data: Dict) -> Optional[Dict]:
        """INSERT into table"""
        try:
            client = self._get_client()
            url = f"{self.rest_url}/{table}"
            
            response = await client.post(url, json=data)
            
            if response.status_code in [200, 201]:
                result = response.json()
                return result if isinstance(result, list) and result else data
            elif response.status_code == 409:
                logger.debug(f"Record already exists in {table}")
                return data
            else:
                logger.error(f"Supabase INSERT error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Supabase INSERT exception: {e}")
            return None
    
    async def update(self, table: str, data: Dict, filters: Dict) -> Optional[Dict]:
        """UPDATE table"""
        try:
            client = self._get_client()
            filter_parts = [f"{key}=eq.{value}" for key, value in filters.items()]
            url = f"{self.rest_url}/{table}?" + "&".join(filter_parts)
            
            response = await client.patch(url, json=data)
            
            if response.status_code == 200:
                result = response.json()
                return result if isinstance(result, list) and result else data
            else:
                logger.error(f"Supabase UPDATE error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Supabase UPDATE exception: {e}")
            return None
    
    async def upsert(self, table: str, data: Dict) -> Optional[Dict]:
        """UPSERT (insert or update) into table"""
        try:
            client = self._get_client()
            url = f"{self.rest_url}/{table}"
            
            headers = self.headers.copy()
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'
            
            response = await client.post(url, json=data, headers=headers)
            
            if response.status_code in [200, 201]:
                result = response.json()
                return result if isinstance(result, list) and result else data
            else:
                logger.error(f"Supabase UPSERT error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Supabase UPSERT exception: {e}")
            return None
    
    async def delete(self, table: str, filters: Dict) -> bool:
        """DELETE from table"""
        try:
            client = self._get_client()
            filter_parts = [f"{key}=eq.{value}" for key, value in filters.items()]
            url = f"{self.rest_url}/{table}?" + "&".join(filter_parts)
            
            response = await client.delete(url)
            return response.status_code in [200, 204]
            
        except Exception as e:
            logger.error(f"Supabase DELETE exception: {e}")
            return False

# ============================================================================
# DATABASE CLASS - COMPLETE FIXED IMPLEMENTATION
# ============================================================================

class Database:
    """Database manager with Supabase REST API + Local fallback + Memory optimization"""
    
    def __init__(self):
        self.client: Optional[SupabaseClient] = None
        self.connected = False
        self._initialized = False
        self._lock = asyncio.Lock()
        
        # Local cache (fallback) with size limits
        self.local_users: Dict[int, Dict] = {}
        self.local_groups: Dict[int, Dict] = {}
        self.local_group_messages: Dict[int, deque] = defaultdict(lambda: deque(maxlen=Config.MAX_GROUP_MESSAGES))
        self.local_activities: deque = deque(maxlen=1000)
        
        # Cache access tracking for LRU cleanup
        self._user_access_times: Dict[int, datetime] = {}
        self._group_access_times: Dict[int, datetime] = {}
        
        logger.info("✅ Database manager initialized")
    
    async def initialize(self):
        """Initialize database connection asynchronously"""
        async with self._lock:
            if self._initialized:
                return
            
            if Config.SUPABASE_URL and Config.SUPABASE_KEY:
                try:
                    self.client = SupabaseClient(
                        Config.SUPABASE_URL.strip(),
                        Config.SUPABASE_KEY.strip()
                    )
                    
                    # Verify connection
                    self.connected = await self.client.verify_connection()
                    
                    if self.connected:
                        logger.info("✅ Supabase connected and verified")
                    else:
                        logger.warning("⚠️ Supabase verification failed - using local storage")
                    
                except Exception as e:
                    logger.error(f"❌ Supabase init failed: {e}")
                    self.connected = False
            else:
                logger.warning("⚠️ Supabase not configured - using local storage")
                self.connected = False
            
            self._initialized = True
    
    async def cleanup_local_cache(self):
        """Cleanup old entries from local cache to prevent memory leaks"""
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=24)
        
        # Cleanup users
        if len(self.local_users) > Config.MAX_LOCAL_USERS_CACHE:
            to_remove = []
            for user_id, last_access in self._user_access_times.items():
                if last_access < cutoff_time:
                    to_remove.append(user_id)
            
            for user_id in to_remove[:len(self.local_users) - Config.MAX_LOCAL_USERS_CACHE]:
                self.local_users.pop(user_id, None)
                self._user_access_times.pop(user_id, None)
            
            if to_remove:
                logger.info(f"🧹 Cleaned {len(to_remove)} users from local cache")
        
        # Cleanup groups
        if len(self.local_groups) > Config.MAX_LOCAL_GROUPS_CACHE:
            to_remove = []
            for group_id, last_access in self._group_access_times.items():
                if last_access < cutoff_time:
                    to_remove.append(group_id)
            
            for group_id in to_remove[:len(self.local_groups) - Config.MAX_LOCAL_GROUPS_CACHE]:
                self.local_groups.pop(group_id, None)
                self._group_access_times.pop(group_id, None)
                self.local_group_messages.pop(group_id, None)
            
            if to_remove:
                logger.info(f"🧹 Cleaned {len(to_remove)} groups from local cache")
    
# ========== USER OPERATIONS (FIXED) ==========
    
    async def get_or_create_user(self, user_id: int, first_name: str = None,
                                  username: str = None) -> Dict:
        """Get or create user"""
        self._user_access_times[user_id] = datetime.now(timezone.utc)
        
        if self.connected and self.client:
            try:
                # Returns a LIST of users
                users_list = await self.client.select('users', '*', {'user_id': user_id})
                
                # FIX: Check if list is not empty and get index 0
                if users_list and len(users_list) > 0:
                    user = users_list[0]
                    
                    if first_name and user.get('first_name') != first_name:
                        await self.client.update('users', {
                            'first_name': first_name,
                            'username': username,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }, {'user_id': user_id})
                    return user
                else:
                    new_user = {
                        'user_id': user_id,
                        'first_name': first_name or 'User',
                        'username': username,
                        'messages': json.dumps([]),
                        'preferences': json.dumps({
                            'meme_enabled': True,
                            'shayari_enabled': True,
                            'geeta_enabled': True
                        }),
                        'total_messages': 0,
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    result = await self.client.insert('users', new_user)
                    
                    # FIX: Handle insert returning a list
                    if isinstance(result, list) and len(result) > 0:
                         return result[0]
                    
                    logger.info(f"✅ New user created: {user_id} ({first_name})")
                    return new_user
                    
            except Exception as e:
                logger.error(f"❌ Database user error: {e}")
                # Fallback to local on error is handled below
        
        # Fallback to local cache
        if user_id not in self.local_users:
            self.local_users[user_id] = {
                'user_id': user_id,
                'first_name': first_name or 'User',
                'username': username,
                'messages': [],
                'preferences': {
                    'meme_enabled': True,
                    'shayari_enabled': True,
                    'geeta_enabled': True
                },
                'total_messages': 0,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"✅ New user (local): {user_id} ({first_name})")
        
        return self.local_users[user_id]
    
    async def get_user_context(self, user_id: int) -> List[Dict]:
        """Get user conversation context"""
        if self.connected and self.client:
            try:
                # FIX: Variable naming and list access
                users_list = await self.client.select('users', 'messages', {'user_id': user_id})
                if users_list and len(users_list) > 0:
                    user_data = users_list[0]
                    messages = user_data.get('messages', '[]')
                    
                    if isinstance(messages, str):
                        try:
                            messages = json.loads(messages)
                        except json.JSONDecodeError:
                            messages = []
                    
                    # Ensure it is a list
                    if not isinstance(messages, list):
                        messages = []
                        
                    return messages[-Config.MAX_PRIVATE_MESSAGES:]
            except Exception as e:
                logger.debug(f"Get context error: {e}")
        
        if user_id in self.local_users:
            return self.local_users[user_id].get('messages', [])[-Config.MAX_PRIVATE_MESSAGES:]
        
        return []
    
    async def save_message(self, user_id: int, role: str, content: str):
        """Save message to user history"""
        new_msg = {
            'role': role,
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'messages,total_messages', {'user_id': user_id})
                
                if users_list and len(users_list) > 0:
                    user_data = users_list[0]
                    
                    messages = user_data.get('messages', '[]')
                    if isinstance(messages, str):
                        try:
                            messages = json.loads(messages)
                        except:
                            messages = []
                    
                    if not isinstance(messages, list):
                        messages = []
                    
                    messages.append(new_msg)
                    messages = messages[-Config.MAX_PRIVATE_MESSAGES:]
                    
                    total = user_data.get('total_messages', 0) + 1
                    
                    await self.client.update('users', {
                        'messages': json.dumps(messages),
                        'total_messages': total,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }, {'user_id': user_id})
                return
            except Exception as e:
                logger.debug(f"Save message error: {e}")
        
        # Local fallback
        if user_id in self.local_users:
            if 'messages' not in self.local_users[user_id]:
                self.local_users[user_id]['messages'] = []
            self.local_users[user_id]['messages'].append(new_msg)
            self.local_users[user_id]['messages'] = \
                self.local_users[user_id]['messages'][-Config.MAX_PRIVATE_MESSAGES:]
            self.local_users[user_id]['total_messages'] = \
                self.local_users[user_id].get('total_messages', 0) + 1
    
    async def clear_user_memory(self, user_id: int):
        """Clear user conversation memory"""
        if self.connected and self.client:
            try:
                await self.client.update('users', {
                    'messages': json.dumps([]),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }, {'user_id': user_id})
                logger.info(f"Memory cleared for user: {user_id}")
                return
            except Exception as e:
                logger.debug(f"Clear memory error: {e}")
        
        if user_id in self.local_users:
            self.local_users[user_id]['messages'] = []
    
    async def update_preference(self, user_id: int, key: str, value: bool):
        """Update user preference"""
        pref_key = f"{key}_enabled"
        
        if self.connected and self.client:
            try:
                # FIX: Variable naming and list access
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})
                
                if users_list and len(users_list) > 0:
                    user_data = users_list[0] # List se pehla item nikala
                    
                    prefs = user_data.get('preferences', '{}')
                    if isinstance(prefs, str):
                        try:
                            prefs = json.loads(prefs)
                        except:
                            prefs = {}
                    
                    prefs[pref_key] = value
                    
                    await self.client.update('users', {
                        'preferences': json.dumps(prefs),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }, {'user_id': user_id})
                return
            except Exception as e:
                logger.debug(f"Update preference error: {e}")
        
        # Local fallback remains same
        if user_id in self.local_users:
            if 'preferences' not in self.local_users[user_id]:
                self.local_users[user_id]['preferences'] = {}
            self.local_users[user_id]['preferences'][pref_key] = value
    
    async def get_user_preferences(self, user_id: int) -> Dict:
        """Get user preferences"""
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})
                
                # FIX: List check
                if users_list and len(users_list) > 0:
                    user_data = users_list[0]
                    prefs = user_data.get('preferences', '{}')
                    if isinstance(prefs, str):
                        try:
                            prefs = json.loads(prefs)
                        except:
                            prefs = {}
                    return prefs
            except Exception as e:
                logger.debug(f"Get preferences error: {e}")
        
        if user_id in self.local_users:
            return self.local_users[user_id].get('preferences', {})
        
        return {'meme_enabled': True, 'shayari_enabled': True, 'geeta_enabled': True}
    
    async def get_all_users(self) -> List[Dict]:
        """Get all users"""
        if self.connected and self.client:
            try:
                return await self.client.select('users', 'user_id,first_name,username,created_at')
            except Exception as e:
                logger.debug(f"Get all users error: {e}")
        
        return list(self.local_users.values())
    
    async def get_user_count(self) -> int:
        """Get total user count"""
        if self.connected and self.client:
            try:
                users = await self.client.select('users', 'user_id')
                return len(users)
            except Exception as e:
                logger.debug(f"User count error: {e}")
        
        return len(self.local_users)
    
    # ========== GROUP OPERATIONS ==========
    
    async def get_or_create_group(self, chat_id: int, title: str = None) -> Dict:
        """Get or create group"""
        self._group_access_times[chat_id] = datetime.now(timezone.utc)
        
        if self.connected and self.client:
            try:
                # 1. List fetch karo
                groups_list = await self.client.select('groups', '*', {'chat_id': chat_id})
                
                # 2. Check karo agar list mein item hai
                if groups_list and len(groups_list) > 0:
                    group = groups_list[0]  # Pehla item nikalo
                    
                    # Title update logic
                    if title and group.get('title') != title:
                        await self.client.update('groups', {
                            'title': title,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }, {'chat_id': chat_id})
                    return group
                else:
                    # 3. Agar group nahi mila to naya banao
                    new_group = {
                        'chat_id': chat_id,
                        'title': title or 'Unknown Group',
                        'settings': json.dumps({
                            'geeta_enabled': True,
                            'welcome_enabled': True
                        }),
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    result = await self.client.insert('groups', new_group)
                    
                    # Insert return ko bhi handle karo (kyunki wo bhi list ho sakta hai)
                    if isinstance(result, list) and len(result) > 0:
                        return result[0]
                        
                    logger.info(f"✅ New group: {chat_id} ({title})")
                    return result or new_group
                    
            except Exception as e:
                logger.debug(f"Group error: {e}")
        
        # Fallback to local cache (Previous logic remains same here)
        if chat_id not in self.local_groups:
            self.local_groups[chat_id] = {
                'chat_id': chat_id,
                'title': title or 'Unknown Group',
                'settings': {
                    'geeta_enabled': True,
                    'welcome_enabled': True
                },
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"✅ New group (local): {chat_id} ({title})")
        
        return self.local_groups[chat_id]
    
    async def update_group_settings(self, chat_id: int, key: str, value: bool):
        """Update group settings"""
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', 'settings', {'chat_id': chat_id})
                
                # FIX: List check
                if groups_list and len(groups_list) > 0:
                    group_data = groups_list[0]
                    
                    settings = group_data.get('settings', '{}')
                    if isinstance(settings, str):
                        try:
                            settings = json.loads(settings)
                        except:
                            settings = {}
                    
                    settings[key] = value
                    
                    await self.client.update('groups', {
                        'settings': json.dumps(settings),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }, {'chat_id': chat_id})
                return
            except Exception as e:
                logger.debug(f"Update group settings error: {e}")
        
        if chat_id in self.local_groups:
            if 'settings' not in self.local_groups[chat_id]:
                self.local_groups[chat_id]['settings'] = {}
            self.local_groups[chat_id]['settings'][key] = value
    
    async def get_group_settings(self, chat_id: int) -> Dict:
        """Get group settings"""
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', 'settings', {'chat_id': chat_id})
                
                # FIX: List check
                if groups_list and len(groups_list) > 0:
                    group_data = groups_list[0]
                    settings = group_data.get('settings', '{}')
                    if isinstance(settings, str):
                        try:
                            settings = json.loads(settings)
                        except:
                            settings = {}
                    return settings
            except Exception as e:
                logger.debug(f"Get group settings error: {e}")
        
        if chat_id in self.local_groups:
            return self.local_groups[chat_id].get('settings', {})
        
        return {'geeta_enabled': True, 'welcome_enabled': True}
    
    # ========== FSUB MAP OPERATIONS (NEW) ==========

    async def get_group_fsub_targets(self, main_chat_id: int) -> List[Dict]:
        """Get required channels for a group"""
        if self.connected and self.client:
            try:
                # Fetch rows matching the main group ID
                result = await self.client.select(
                    'group_fsub_map', 
                    'target_chat_id,target_link', 
                    {'main_chat_id': main_chat_id}
                )
                return result if result else []
            except Exception as e:
                logger.error(f"FSub fetch error: {e}")
                return []
        return []
    
    async def get_all_groups(self) -> List[Dict]:
        """Get all groups"""
        if self.connected and self.client:
            try:
                return await self.client.select('groups', '*')
            except Exception as e:
                logger.debug(f"Get all groups error: {e}")
        
        return list(self.local_groups.values())
    
    async def get_group_count(self) -> int:
        """Get total group count"""
        if self.connected and self.client:
            try:
                groups = await self.client.select('groups', 'chat_id')
                return len(groups)
            except Exception as e:
                logger.debug(f"Group count error: {e}")
        
        return len(self.local_groups)
    
    # ========== GROUP MESSAGE CACHE ==========
    
    def add_group_message(self, chat_id: int, username: str, content: str):
        """Add message to group cache (local only for performance)"""
        self.local_group_messages[chat_id].append({
            'username': username,
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    def get_group_context(self, chat_id: int) -> List[Dict]:
        """Get group message context"""
        return list(self.local_group_messages.get(chat_id, []))
    
    # ========== ACTIVITY LOGGING ==========
    
    async def log_user_activity(self, user_id: int, activity_type: str):
        """Log user activity"""
        activity = {
            'user_id': user_id,
            'activity_type': activity_type,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if self.connected and self.client:
            try:
                await self.client.insert('activities', activity)
                return
            except Exception as e:
                logger.debug(f"Activity log error: {e}")
        
        self.local_activities.append(activity)
    
    # ========== CLEANUP ==========
    
    async def close(self):
        """Close database connections and cleanup"""
        if self.client:
            await self.client.close()
        
        # Clear local caches
        self.local_users.clear()
        self.local_groups.clear()
        self.local_group_messages.clear()
        self.local_activities.clear()
        self._user_access_times.clear()
        self._group_access_times.clear()
        
        logger.info("✅ Database connection closed and caches cleared")


# Initialize database (will be initialized asynchronously in main)
db = Database()

# ============================================================================
# RATE LIMITER WITH COOLDOWN - MEMORY OPTIMIZED
# ============================================================================

class RateLimiter:
    """Rate limiting with cooldown system and memory optimization"""
    
    def __init__(self):
        self.requests = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.cooldowns: Dict[int, datetime] = {}
        self.lock = threading.Lock()
        self._last_cleanup = datetime.now(timezone.utc)
    
    def check(self, user_id: int) -> Tuple[bool, str]:
        """Check rate limits"""
        now = datetime.now(timezone.utc)
        
        with self.lock:
            # Check cooldown
            if user_id in self.cooldowns:
                last_time = self.cooldowns[user_id]
                if (now - last_time).total_seconds() < Config.USER_COOLDOWN_SECONDS:
                    return False, "cooldown"
            
            reqs = self.requests[user_id]
            
            # Clean old requests (FIXED LOGIC HERE)
            # Check the first element (oldest time) of the deque
            while reqs['minute'] and reqs['minute'][0] < now - timedelta(minutes=1):
                reqs['minute'].popleft()
            
            while reqs['day'] and reqs['day'][0] < now - timedelta(days=1):
                reqs['day'].popleft()
            
            # Check limits
            if len(reqs['minute']) >= Config.MAX_REQUESTS_PER_MINUTE:
                return False, "minute"
            if len(reqs['day']) >= Config.MAX_REQUESTS_PER_DAY:
                return False, "day"
            
            # Record request
            reqs['minute'].append(now)
            reqs['day'].append(now)
            self.cooldowns[user_id] = now
            return True, ""
    
    def get_daily_total(self) -> int:
        """Get total daily requests"""
        return sum(len(r['day']) for r in self.requests.values())
    
    def cleanup_cooldowns(self):
        """Remove old cooldowns and requests to prevent memory leak"""
        now = datetime.now(timezone.utc)
        
        # Only cleanup once per hour
        if (now - self._last_cleanup).total_seconds() < 3600:
            return
        
        with self.lock:
            # Remove old cooldowns
            expired_cooldowns = [uid for uid, time in self.cooldowns.items()
                                 if (now - time).total_seconds() > 3600]
            for uid in expired_cooldowns:
                del self.cooldowns[uid]
            
            # Remove old requests
            expired_requests = []
            for uid, reqs in self.requests.items():
                if not reqs['day']:
                    expired_requests.append(uid)
            for uid in expired_requests:
                del self.requests[uid]
            
            self._last_cleanup = now
            
            if expired_cooldowns or expired_requests:
                logger.info(f"🧹 Cleaned {len(expired_cooldowns)} cooldowns, {len(expired_requests)} request histories")


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
        utc_now = datetime.now(timezone.utc)
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
            'morning': ["good morning ☀️", "uth gaye aap bhi?", "subah subah! ✨"],
            'afternoon': ["heyyy", "lunch ho gaya?", "afternoon vibes 🌤️"],
            'evening': ["hiii 💫", "chai time! ☕", "shaam ho gayi yaar"],
            'night': ["heyy 🌙", "night owl?", "aaj kya plan hai"],
            'late_night': ["aap bhi jaag rahe ho? 👀", "insomnia gang 🦉", "neend nahi aa rahi?"]
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
        
        # FIX: Added [0] at the end because choices returns a list ['mood']
        return random.choices(Mood.MOODS, weights=weights, k=1)[0]
    
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
        # Safe get incase mood is somehow invalid
        return instructions.get(mood, "Mood: HAPPY 😊 - Friendly vibes")
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
    """Niyati AI personality with Multi-Key Rotation & Multi-Provider Fallback"""
    
    def __init__(self):
        # ═══════════════════════════════════════
        # 🔑 OPENAI SETUP
        # ═══════════════════════════════════════
        self.openai_keys = Config.OPENAI_API_KEYS_LIST or []
        self.openai_key_index = 0
        self.openai_client: Optional[AsyncOpenAI] = None
        self.openai_exhausted = False
        
        # ═══════════════════════════════════════
        # 🔑 GROQ SETUP
        # ═══════════════════════════════════════
        self.groq_keys = Config.GROQ_API_KEYS_LIST or []
        self.groq_key_index = 0
        self.groq_client: Optional[AsyncGroq] = None
        self.groq_exhausted = False
        
        # ═══════════════════════════════════════
        # 🔑 GEMINI SETUP
        # ═══════════════════════════════════════
        self.gemini_keys = Config.GEMINI_API_KEYS_LIST or []
        self.gemini_key_index = 0
        self.gemini_model = None
        self.gemini_exhausted = False
        
        # Current active provider
        self.current_provider = "openai"  # openai, groq, gemini
        
        # Initialize all clients
        self._init_all_clients()
        logger.info(f"🤖 NiyatiAI initialized | OpenAI: {len(self.openai_keys)} keys | Groq: {len(self.groq_keys)} keys | Gemini: {len(self.gemini_keys)} keys")
    
    # ═══════════════════════════════════════════════════════════
    # 🔧 INITIALIZATION
    # ═══════════════════════════════════════════════════════════
    
    def _init_all_clients(self):
        """Initialize all AI clients"""
        self._init_openai()
        self._init_groq()
        self._init_gemini()
    
    def _init_openai(self):
        """Initialize OpenAI client"""
        if not self.openai_keys:
            self.openai_exhausted = True
            return
        key = self.openai_keys[self.openai_key_index]
        self.openai_client = AsyncOpenAI(api_key=key)
        logger.info(f"🔑 OpenAI Key [{self.openai_key_index + 1}/{len(self.openai_keys)}]: {key[:8]}...{key[-4:]}")
    
    def _init_groq(self):
        """Initialize Groq client"""
        if not self.groq_keys:
            self.groq_exhausted = True
            return
        key = self.groq_keys[self.groq_key_index]
        self.groq_client = AsyncGroq(api_key=key)
        logger.info(f"🔑 Groq Key [{self.groq_key_index + 1}/{len(self.groq_keys)}]: {key[:8]}...{key[-4:]}")
    
    def _init_gemini(self):
        """Initialize Gemini client"""
        if not self.gemini_keys:
            self.gemini_exhausted = True
            return
        key = self.gemini_keys[self.gemini_key_index]
        genai.configure(api_key=key)
        self.gemini_model = genai.GenerativeModel(
            model_name=Config.GEMINI_MODEL,
            generation_config={
                "temperature": Config.OPENAI_TEMPERATURE,
                "max_output_tokens": Config.OPENAI_MAX_TOKENS,
            },
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        logger.info(f"🔑 Gemini Key [{self.gemini_key_index + 1}/{len(self.gemini_keys)}]: {key[:8]}...{key[-4:]}")
    
    # ═══════════════════════════════════════════════════════════
    # 🔄 KEY ROTATION
    # ═══════════════════════════════════════════════════════════
    
    def _rotate_openai_key(self) -> bool:
        """Rotate OpenAI key. Returns False if all exhausted."""
        if len(self.openai_keys) <= 1:
            self.openai_exhausted = True
            return False
        
        self.openai_key_index = (self.openai_key_index + 1) % len(self.openai_keys)
        if self.openai_key_index == 0:
            self.openai_exhausted = True
            logger.warning("🔴 All OpenAI keys exhausted!")
            return False
        
        logger.warning(f"🔄 Rotating OpenAI → Key #{self.openai_key_index + 1}")
        self._init_openai()
        return True
    
    def _rotate_groq_key(self) -> bool:
        """Rotate Groq key. Returns False if all exhausted."""
        if len(self.groq_keys) <= 1:
            self.groq_exhausted = True
            return False
        
        self.groq_key_index = (self.groq_key_index + 1) % len(self.groq_keys)
        if self.groq_key_index == 0:
            self.groq_exhausted = True
            logger.warning("🔴 All Groq keys exhausted!")
            return False
        
        logger.warning(f"🔄 Rotating Groq → Key #{self.groq_key_index + 1}")
        self._init_groq()
        return True
    
    def _rotate_gemini_key(self) -> bool:
        """Rotate Gemini key. Returns False if all exhausted."""
        if len(self.gemini_keys) <= 1:
            self.gemini_exhausted = True
            return False
        
        self.gemini_key_index = (self.gemini_key_index + 1) % len(self.gemini_keys)
        if self.gemini_key_index == 0:
            self.gemini_exhausted = True
            logger.warning("🔴 All Gemini keys exhausted!")
            return False
        
        logger.warning(f"🔄 Rotating Gemini → Key #{self.gemini_key_index + 1}")
        self._init_gemini()
        return True
    
    def _switch_provider(self) -> bool:
        """Switch to next provider. Returns False if all exhausted."""
        if self.current_provider == "openai":
            if not self.groq_exhausted and self.groq_keys:
                self.current_provider = "groq"
                logger.warning("🔀 Switching: OpenAI → GROQ")
                return True
            elif not self.gemini_exhausted and self.gemini_keys:
                self.current_provider = "gemini"
                logger.warning("🔀 Switching: OpenAI → GEMINI")
                return True
        
        elif self.current_provider == "groq":
            if not self.gemini_exhausted and self.gemini_keys:
                self.current_provider = "gemini"
                logger.warning("🔀 Switching: GROQ → GEMINI")
                return True
        
        elif self.current_provider == "gemini":
            # Reset and try OpenAI again (cooldown might be over)
            if self.openai_keys:
                self.openai_exhausted = False
                self.openai_key_index = 0
                self._init_openai()
                self.current_provider = "openai"
                logger.warning("🔀 Switching: GEMINI → OPENAI (reset)")
                return True
        
        logger.error("🔴 All providers exhausted!")
        return False
    
    # ═══════════════════════════════════════════════════════════
    # 🧠 API CALLS
    # ═══════════════════════════════════════════════════════════
    
    async def _call_openai(self, messages: List[Dict], max_tokens: int, temperature: float) -> Tuple[Optional[str], bool]:
        """Call OpenAI. Returns (response, should_fallback)"""
        if self.openai_exhausted or not self.openai_client:
            return None, True
        
        try:
            response = await self.openai_client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                presence_penalty=0.6,
                frequency_penalty=0.4
            )
            return response.choices[0].message.content.strip(), False
        
        except (RateLimitError, APIError) as e:
            error_msg = str(e).lower()
            if any(x in error_msg for x in ["rate limit", "quota", "429", "insufficient"]):
                logger.warning(f"⚠️ OpenAI Limit: {e}")
                await asyncio.sleep(0.5)
                if self._rotate_openai_key():
                    return None, False  # Retry with new key
                return None, True  # Fallback
            logger.error(f"❌ OpenAI Error: {e}")
            return None, True
        
        except Exception as e:
            logger.error(f"❌ OpenAI Error: {e}")
            return None, True
    
    async def _call_groq(self, messages: List[Dict], max_tokens: int, temperature: float) -> Tuple[Optional[str], bool]:
        """Call Groq. Returns (response, should_fallback)"""
        if self.groq_exhausted or not self.groq_client:
            return None, True
        
        try:
            response = await self.groq_client.chat.completions.create(
                model=Config.GROQ_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip(), False
        
        except Exception as e:
            error_msg = str(e).lower()
            if any(x in error_msg for x in ["rate", "limit", "quota", "429"]):
                logger.warning(f"⚠️ Groq Limit: {e}")
                await asyncio.sleep(0.5)
                if self._rotate_groq_key():
                    return None, False
                return None, True
            logger.error(f"❌ Groq Error: {e}")
            return None, True
    
    async def _call_gemini(self, messages: List[Dict], max_tokens: int, temperature: float) -> Tuple[Optional[str], bool]:
        """Call Gemini. Returns (response, should_fallback)"""
        if self.gemini_exhausted or not self.gemini_model:
            return None, True
        
        try:
            # Convert to Gemini format
            prompt = self._messages_to_gemini(messages)
            
            # Update config
            self.gemini_model._generation_config["max_output_tokens"] = max_tokens
            self.gemini_model._generation_config["temperature"] = temperature
            
            response = await asyncio.to_thread(
                self.gemini_model.generate_content, prompt
            )
            
            if response.text:
                return response.text.strip(), False
            return None, True
        
        except Exception as e:
            error_msg = str(e).lower()
            if any(x in error_msg for x in ["quota", "rate", "limit", "429", "resource"]):
                logger.warning(f"⚠️ Gemini Limit: {e}")
                if self._rotate_gemini_key():
                    return None, False
                return None, True
            logger.error(f"❌ Gemini Error: {e}")
            return None, True
    
    def _messages_to_gemini(self, messages: List[Dict]) -> str:
        """Convert OpenAI format to Gemini prompt"""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System Instructions]\n{content}\n")
            elif role == "assistant":
                parts.append(f"Niyati: {content}\n")
            else:
                parts.append(f"User: {content}\n")
        parts.append("Niyati:")
        return "\n".join(parts)
    
    # ═══════════════════════════════════════════════════════════
    # 🎯 MAIN CALL METHOD
    # ═══════════════════════════════════════════════════════════
    
    async def _call_ai(self, messages: List[Dict], max_tokens: int = 200, temperature: float = None) -> Optional[str]:
        """Main AI call with automatic fallback"""
        if temperature is None:
            temperature = Config.OPENAI_TEMPERATURE
        
        max_attempts = 10
        for _ in range(max_attempts):
            result, should_fallback = None, False
            
            if self.current_provider == "openai":
                result, should_fallback = await self._call_openai(messages, max_tokens, temperature)
            elif self.current_provider == "groq":
                result, should_fallback = await self._call_groq(messages, max_tokens, temperature)
            elif self.current_provider == "gemini":
                result, should_fallback = await self._call_gemini(messages, max_tokens, temperature)
            
            if result:
                return result
            
            if should_fallback:
                if not self._switch_provider():
                    break
            
            await asyncio.sleep(0.3)
        
        return None
    
    # ═══════════════════════════════════════════════════════════
    # 💬 SYSTEM PROMPT
    # ═══════════════════════════════════════════════════════════
    
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

❌ NEVER DO:
- "As an AI", "I am a bot"
- One long paragraph
- Formal language
- Fake claims about meeting/calls
- "Hello user"

✅ ALWAYS:
- Be warm, caring, fun
- Keep it real and casual

Tu text karegi jaise real friend karti hai ✨"""
        return prompt
    
    # ═══════════════════════════════════════════════════════════
    # 📨 GENERATE RESPONSE
    # ═══════════════════════════════════════════════════════════
    
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
        
        reply = await self._call_ai(messages, max_tokens=max_tokens)
        
        if not reply:
            return ["yaar network issue lag raha hai 🥺", "thodi der mein message karun?"]
        
        # Parse response
        if '|||' in reply:
            parts = [p.strip() for p in reply.split('|||') if p.strip()]
        elif '\n' in reply:
            parts = [p.strip() for p in reply.split('\n') if p.strip()]
        else:
            parts = [reply]
        
        return parts[:4]
    
    # ═══════════════════════════════════════════════════════════
    # 📝 SHAYARI & GEETA QUOTE
    # ═══════════════════════════════════════════════════════════
    
    async def generate_shayari(self, mood: str = "neutral") -> str:
        """Generate AI Shayari"""
        prompt = f"""Write a short, heart-touching 2-line Shayari in 'Hinglish' (Roman Hindi) based on this mood: {mood.upper()}.
        Style: Casual, emotional, like a GenZ text message.
        Do NOT use formal/shuddh Hindi. Use words like 'dil', 'yaar', 'yaadein', 'waqt'.
        Output ONLY the shayari lines."""
        
        messages = [{"role": "user", "content": prompt}]
        shayari = await self._call_ai(messages, max_tokens=100, temperature=0.9)
        
        if shayari:
            return f"✨ {shayari} ✨"
        
        backups = [
            "dil ki raahon mein tera saath ho\nkhwabon ki roshni hamesha chale ✨",
            "kabhi kabhi adhoori baatein bhi\npoori kahani keh jaati hain 💫",
            "waqt badal jata hai insaan badal jate hain\npar yaadein wahi rehti hain 🥀"
        ]
        return random.choice(backups)
    
    async def generate_geeta_quote(self) -> str:
        """Generate AI Geeta Quote"""
        prompt = """Give me a powerful, short quote or lesson from Bhagavad Gita.
        Format: Start with '🙏', give meaning in simple 'Hinglish' (Roman Hindi).
        Keep it inspiring, modern and relevant. Max 20 words.
        Example: 🙏 Karm kar bande, phal ki chinta mat kar."""
        
        messages = [{"role": "user", "content": prompt}]
        quote = await self._call_ai(messages, max_tokens=150)
        
        if quote:
            return quote
        return "🙏 *कर्मण्येवाधिकारस्ते*\nKarm kar, phal ki chinta mat kar ✨"
    
    async def get_random_bonus(self) -> Optional[str]:
        """Get random shayari or meme"""
        rand = random.random()
        
        if rand < Config.RANDOM_SHAYARI_CHANCE:
            mood = Mood.get_random_mood()
            return await self.generate_shayari(mood)
        elif rand < Config.RANDOM_SHAYARI_CHANCE + Config.RANDOM_MEME_CHANCE:
            return self._get_random_meme()
        return None
    
    @staticmethod
    def _get_random_meme() -> str:
        """Get random meme"""
        memes = [
            "life kya hai bhai... 🙃", "control uday control 😂", "us moment 🤝",
            "kya logic hai 🤦‍♀️", "dukh. dard. peeda. 🥲", "padhai likhai karo IAS yaso bano 👨‍⚖️",
            "ye bik gayi hai gormint 😶", "khatam. tata. bye bye 👋"
        ]
        return random.choice(memes)


# Initialize
niyati_ai = NiyatiAI()
# ============================================================================
# MESSAGE SENDER
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
        if not msg or not msg.strip():
            continue
            
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
• /stats - Your stats

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
    
    # FIX: Access the first element of the list (args[0])
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
    
    # FIX: Access args[0]
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /shayari on ya /shayari off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_preference(user.id, 'shayari', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Shayari: {status}")


async def user_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's personal stats"""
    user = update.effective_user
    user_data = await db.get_or_create_user(user.id, user.first_name, user.username)
    
    messages = user_data.get('messages', [])
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except:
            messages = []
    
    prefs = user_data.get('preferences', {})
    if isinstance(prefs, str):
        try:
            prefs = json.loads(prefs)
        except:
            prefs = {}
    
    created_at = user_data.get('created_at', 'Unknown')
    if isinstance(created_at, str) and len(created_at) >= 10:
        created_at = created_at[:10]
    
    stats_text = f"""
📊 <b>Your Stats</b>

<b>User:</b> {user.first_name}
<b>ID:</b> <code>{user.id}</code>
<b>Username:</b> @{user.username if user.username else 'Not set'}

<b>Conversation:</b>
• Messages: {len(messages)}
• Joined: {created_at}

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
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except:
            settings = {}
    
    info_text = f"""
📊 <b>Group Info</b>

<b>Name:</b> {chat.title}
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
    """Toggle Geeta quotes"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sry baby, only admins can do this 😘💅")
        return
    
    args = context.args
    # FIX: Access args[0]
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /setgeeta on ya /setgeeta off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_group_settings(chat.id, 'geeta_enabled', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Daily Geeta Quote: {status}")

async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle welcome messages"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sry baby, only admins can do this 😘💅")
        return
    
    args = context.args
    # FIX: Access args[0]
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
        await update.message.reply_text("❌ Sry baby, only admins can do this 😘💅")
        return
    
    cached_msgs = len(db.get_group_context(chat.id))
    
    stats_text = f"""
📊 <b>Group Statistics</b>

<b>Group:</b> {chat.title}
<b>Cached Messages:</b> {cached_msgs}
<b>Max Cache:</b> {Config.MAX_GROUP_MESSAGES}
"""
    await update.message.reply_html(stats_text)


async def groupsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current group settings"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Sry baby, only admins can do this 😘💅")
        return
    
    group_data = await db.get_or_create_group(chat.id, chat.title)
    
    settings = group_data.get('settings', {})
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except:
            settings = {}
    
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
    await update.message.reply_html(settings_text)

# ============================================================================
# ADMIN COMMANDS
# ============================================================================

async def admin_check(update: Update) -> bool:
    """Check if user is bot admin"""
    return update.effective_user.id in Config.ADMIN_IDS


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot stats (admin only)"""
    if not await admin_check(update):
        await update.message.reply_text("Sry baby, only admins can do this 😘💅")
        return
    
    user_count = await db.get_user_count()
    group_count = await db.get_group_count()
    daily_requests = rate_limiter.get_daily_total()
    
    uptime = datetime.now(timezone.utc) - health_server.start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    
    db_status = "🟢 Connected" if db.connected else "🔴 Local Only"
    
    stats_text = f"""
📊 <b>Niyati Bot Statistics</b>

<b>Users:</b> {user_count}
<b>Groups:</b> {group_count}
<b>Today's Requests:</b> {daily_requests}

<b>Uptime:</b> {hours}h {minutes}m
<b>Model:</b> {Config.OPENAI_MODEL}
<b>Database:</b> {db_status}

<b>Limits:</b>
• Per Minute: {Config.MAX_REQUESTS_PER_MINUTE}
• Per Day: {Config.MAX_REQUESTS_PER_DAY}

<b>Memory:</b>
• Local Users: {len(db.local_users)}
• Local Groups: {len(db.local_groups)}
• Rate Limiter Cooldowns: {len(rate_limiter.cooldowns)}
"""
    await update.message.reply_html(stats_text)


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user list (admin only)"""
    if not await admin_check(update):
        await update.message.reply_text("Sry baby, only admins can do this 😘💅")
        return
    
    users = await db.get_all_users()
    
    user_lines = []
    for u in users[:20]:
        name = u.get('first_name', 'Unknown')
        uid = u.get('user_id', 0)
        username = u.get('username', '')
        line = f"• {name}"
        if username:
            line += f" (@{username})"
        line += f" - <code>{uid}</code>"
        user_lines.append(line)
    
    user_list = "\n".join(user_lines) if user_lines else "No users yet"
    
    text = f"""
👥 <b>User List (Last 20)</b>

{user_list}

<b>Total Users:</b> {len(users)}
"""
    await update.message.reply_html(text)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users AND groups"""
    if not await admin_check(update):
        await update.message.reply_text("Sry baby, only admins can do this 😘💅")
        return
    
    args = context.args
    
    # PIN Check
    if not args or args[0] != Config.BROADCAST_PIN:
        await update.message.reply_html(
            "🔐 <b>Broadcast Command</b>\n\n"
            "Usage: /broadcast [PIN] [message]\n"
            "Example: /broadcast 1234 <b>Hello</b> everyone!\n\n"
            "<b>Supported HTML Tags:</b>\n"
            "&lt;b&gt;bold&lt;/b&gt;, &lt;i&gt;italic&lt;/i&gt;, &lt;u&gt;underline&lt;/u&gt;, "
            "&lt;s&gt;strike&lt;/s&gt;, &lt;code&gt;mono&lt;/code&gt;, &lt;tg-spoiler&gt;spoiler&lt;/tg-spoiler&gt;"
        )
        return
    
    # Message Logic
    message_text = ' '.join(args[1:]) if len(args) > 1 else None
    reply_msg = update.message.reply_to_message
    
    if not message_text and not reply_msg:
        await update.message.reply_text("❌ Message ya reply do broadcast ke liye!")
        return
    
    await update.message.reply_text("📢 Broadcasting to Users & Groups... please wait")
    
    # --- STEP 1: BROADCAST TO USERS ---
    users = await db.get_all_users()
    user_success = 0
    user_failed = 0
    
    for user in users:
        user_id = user.get('user_id')
        if not user_id: continue
        
        sent = False
        try:
            if reply_msg:
                if reply_msg.text:
                    await context.bot.send_message(chat_id=user_id, text=reply_msg.text, parse_mode=ParseMode.HTML)
                else:
                    await context.bot.forward_message(chat_id=user_id, from_chat_id=update.effective_chat.id, message_id=reply_msg.message_id)
            else:
                await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode=ParseMode.HTML)
            
            user_success += 1
            sent = True
            await asyncio.sleep(Config.BROADCAST_RATE_LIMIT) # Avoid flood limits
            
        except Exception as e:
            user_failed += 1
            # logger.debug(f"User broadcast failed: {e}")

    # --- STEP 2: BROADCAST TO GROUPS ---
    groups = await db.get_all_groups()
    group_success = 0
    group_failed = 0
    
    for group in groups:
        chat_id = group.get('chat_id')
        if not chat_id: continue
        
        try:
            if reply_msg:
                if reply_msg.text:
                    await context.bot.send_message(chat_id=chat_id, text=reply_msg.text, parse_mode=ParseMode.HTML)
                else:
                    await context.bot.forward_message(chat_id=chat_id, from_chat_id=update.effective_chat.id, message_id=reply_msg.message_id)
            else:
                await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode=ParseMode.HTML)
            
            group_success += 1
            await asyncio.sleep(Config.BROADCAST_RATE_LIMIT) # Avoid flood limits
            
        except Exception as e:
            group_failed += 1
            # logger.debug(f"Group broadcast failed: {e}")

    # --- FINAL REPORT ---
    report = (
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"👤 <b>Users:</b> {user_success} sent, {user_failed} failed\n"
        f"📢 <b>Groups:</b> {group_success} sent, {group_failed} failed\n"
        f"📊 <b>Total Reach:</b> {user_success + group_success}"
    )
    
    await update.message.reply_html(report)
    logger.info(f"📢 Broadcast: Users({user_success}/{len(users)}), Groups({group_success}/{len(groups)})")

async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin commands"""
    if not await admin_check(update):
        await update.message.reply_text("Sry baby, only admins can do this 😘💅")
        return
    
    help_text = """
🔐 <b>Admin Commands</b>

<b>Statistics:</b>
• /adminstats - Bot statistics
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

<b>Example:</b>
/broadcast PIN <b>Hello</b> everyone! Check this <i>special</i> offer 🎉
"""
    await update.message.reply_html(help_text)


# ============================================================================
# SCHEDULED JOBS
# ============================================================================

async def send_daily_geeta(context: ContextTypes.DEFAULT_TYPE):
    """Send daily Geeta quote to all groups"""
    groups = await db.get_all_groups()
    quote = await niyati_ai.generate_geeta_quote()
    
    sent = 0
    for group in groups:
        chat_id = group.get('chat_id')
        
        settings = group.get('settings', {})
        if isinstance(settings, str):
            try:
                settings = json.loads(settings)
            except:
                settings = {}
        
        if not settings.get('geeta_enabled', True):
            continue
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=quote,
                parse_mode=ParseMode.HTML
            )
            sent += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.debug(f"Geeta send error to {chat_id}: {e}")
    
    logger.info(f"📿 Daily Geeta sent to {sent} groups")


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    """Periodic cleanup of rate limiter and database caches"""
    rate_limiter.cleanup_cooldowns()
    await db.cleanup_local_cache()
    logger.info("🧹 Periodic cleanup completed")


# ============================================================================
# MAIN MESSAGE HANDLER - FULLY FIXED
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages with FSub Check"""
    message = update.message
    if not message or not message.text: return
        
    user = update.effective_user
    chat = update.effective_chat
    user_message = message.text
    
    if not user_message or user_message.startswith('/'): return

    # 👇👇 YEH LINE ADD KARNI THI (Missing Definition) 👇👇
    is_group = chat.type in ['group', 'supergroup']
    is_private = chat.type == 'private'
    # 👆👆 AB CODE KO PATA HAI KI PRIVATE HAI YA GROUP 👆👆

    # --- 🔒 NEW FSUB LOGIC START ---
    if is_group:
        # 1. Database se channels ki list nikalo
        targets = await db.get_group_fsub_targets(chat.id)
        
        if targets:
            missing_channels = []
            
            # 2. Har channel ke liye check karo
            for target in targets:
                t_id = target.get('target_chat_id')
                t_link = target.get('target_link')
                
                if not t_id: continue

                try:
                    member = await context.bot.get_chat_member(chat_id=t_id, user_id=user.id)
                    if member.status in ['left', 'kicked', 'restricted']:
                        missing_channels.append(t_link)
                except Exception:
                    pass # Agar bot admin nahi hai to ignore karo

            # 3. Agar koi channel miss hai to rok do
            if missing_channels:
                try: await message.delete()
                except: pass
                
                # Buttons banao
                keyboard = []
                for idx, link in enumerate(missing_channels, 1):
                    keyboard.append([InlineKeyboardButton(f"Join Channel {idx} 🚀", url=link)])
                
                msg = await message.reply_text(
                    f"🚫 <b>Ruko {user.first_name}!</b>\n\n"
                    "Message karne ke liye niche diye gaye channels join karo.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                # Warning delete after 10s
                await asyncio.sleep(10)
                try: await msg.delete()
                except: pass
                
                return # Code yahi rook do
    # --- 🔒 NEW FSUB LOGIC END ---

    # --- Rate Limiting ---
    allowed, _ = rate_limiter.check(user.id)
    if not allowed: return

    # --- Anti-Spam Check (Optional) ---
    if is_group:
        spam_keywords = ['cp', 'child porn', 'videos price', 'job', 'profit', 'investment', 'crypto']
        if any(word in user_message.lower() for word in spam_keywords):
            return

    # --- Group Handling ---
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
            if random.random() < Config.GROUP_RESPONSE_RATE:
                should_respond = True
            else:
                return
        
        await db.get_or_create_group(chat.id, chat.title)
        await db.log_user_activity(user.id, f"group_message:{chat.id}")
    
    # --- Private Handling ---
    if is_private:
        await db.get_or_create_user(user.id, user.first_name, user.username)
        await db.log_user_activity(user.id, "private_message")
    
    # --- Response Generation ---
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    except:
        pass
    
    try:
        context_msgs = await db.get_user_context(user.id) if is_private else []
        
        responses = await niyati_ai.generate_response(
            user_message=user_message,
            context=context_msgs,
            user_name=user.first_name,
            is_group=is_group
        )
        
        # Random Bonus (Private Only)
        if is_private and random.random() < 0.1:
            prefs = await db.get_user_preferences(user.id)
            bonus = await niyati_ai.get_random_bonus()
            
            if bonus:
                if "shayari" in str(bonus).lower() and not prefs.get('shayari_enabled', True):
                    bonus = None
                if bonus and "meme" in str(bonus).lower() and not prefs.get('meme_enabled', True):
                    bonus = None
                if bonus:
                    responses.append(bonus)
        
        # Mention Logic
        if is_private and random.random() < 0.2:
            mention = StylishFonts.mention(user.first_name, user.id)
            if responses:
                idx = random.randint(0, len(responses) - 1)
                responses[idx] = f"{mention} {responses[idx]}" if random.random() < 0.5 else f"{responses[idx]}, {mention}"
        
        # Send
        await send_multi_messages(
            context.bot,
            chat.id,
            responses,
            reply_to=message.message_id if is_group else None,
            parse_mode=ParseMode.HTML
        )
        
        # Save Memory (Private)
        if is_private:
            await db.save_message(user.id, 'user', user_message)
            await db.save_message(user.id, 'assistant', ' '.join(responses))
            
        health_server.stats['messages'] += 1
        
    except Exception as e:
        logger.error(f"❌ Message handling error: {e}", exc_info=True)
        try:
            await message.reply_text("oops kuch gadbad... retry karo? 🫶")
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
    
    settings = group_data.get('settings', {})
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except:
            settings = {}
    
    if not settings.get('welcome_enabled', True):
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
        await db.log_user_activity(member.id, f"joined_group:{chat.id}")


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
# BOT SETUP
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
    app.add_handler(CommandHandler("stats", user_stats_command))
    
    # Group commands
    app.add_handler(CommandHandler("grouphelp", grouphelp_command))
    app.add_handler(CommandHandler("groupinfo", groupinfo_command))
    app.add_handler(CommandHandler("setgeeta", setgeeta_command))
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("groupstats", groupstats_command))
    app.add_handler(CommandHandler("groupsettings", groupsettings_command))
    
    # Admin commands
    app.add_handler(CommandHandler("adminstats", admin_stats_command))
    app.add_handler(CommandHandler("users", users_command))
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


async def setup_jobs(app: Application):
    """Setup scheduled jobs"""
    job_queue = app.job_queue
    
    if job_queue is None:
        logger.warning("⚠️ JobQueue not available")
        return
    
    # Daily Geeta quote at 6 AM IST
    ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
    target_time = datetime.now(ist).replace(hour=6, minute=0, second=0, microsecond=0)
    
    if target_time.time() < datetime.now(ist).time():
        target_time += timedelta(days=1)
    
    job_queue.run_daily(
        send_daily_geeta,
        time=target_time.timetz(),
        name='daily_geeta'
    )
    
    # Cleanup job every hour
    job_queue.run_repeating(
        cleanup_job,
        interval=Config.CACHE_CLEANUP_INTERVAL,
        first=Config.CACHE_CLEANUP_INTERVAL,
        name='cleanup'
    )
    
    logger.info("✅ Scheduled jobs setup")


# ============================================================================
# MAIN FUNCTION - FULLY FIXED
# ============================================================================

async def main_async():
    """Async main function"""
    
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║              🌸 NIYATI BOT v3.0 🌸                    ║
    ║           Teri Online Bestie is Starting!             ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    logger.info("🚀 Starting Niyati Bot...")
    logger.info(f"Model: {Config.OPENAI_MODEL}")
    logger.info(f"Port: {Config.PORT}")
    
    # Initialize database asynchronously
    await db.initialize()
    
    logger.info(f"Database: {'Connected' if db.connected else 'Local Mode'}")
    logger.info(f"Privacy Mode: {'ON' if Config.PRIVACY_MODE else 'OFF'}")
    
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
    
    # Setup scheduled jobs
    await setup_jobs(app)
    
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
        logger.info("⏹️ Shutting down...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await health_server.stop()
        await db.close()
        logger.info("✅ Bot stopped cleanly")


def main():
    """Main entry point"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("⏹️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
