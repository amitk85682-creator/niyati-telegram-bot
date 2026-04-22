"""
╔════════════════════════════════════════════════════════════════════════════╗
║                    CONCURRENT BOT: NIYATI + KAVYA                        ║
║       Two AI personalities running together — Human-like Conversations   ║
║                        v3.0 — COMPLETE REWRITE                           ║
╚════════════════════════════════════════════════════════════════════════════╝

CHANGELOG v3.0:
- Fixed: get_user_context() had unreachable code with undefined 'for_bot'
- Fixed: NiyatiPromptBuilder & KavyaPromptBuilder had duplicate parse logic & missing authors_note
- Fixed: Shared memory now properly tagged with bot names for 3-way chat
- Fixed: Group messages properly distinguish Human vs Niyati vs Kavya
- Enhanced: Ultra-natural Hinglish with typos, hesitation, broken sentences
- Enhanced: Dynamic typing delays based on message length (feels human)
- Enhanced: Anti-loop system prevents bots from talking to each other endlessly
- Enhanced: Emotional memory system with mood persistence
- Enhanced: Smart interjection system — bots jump in naturally, not randomly
- Enhanced: Conversation flow awareness — bots know when to stay quiet
- Enhanced: Natural voice with varied speed/pitch per mood
- Enhanced: Group FSub (Force Subscribe) support
- Enhanced: Proper concurrent_updates for both bots
- Enhanced: Better error handling and graceful degradation
"""

import os
import sys
import json
import logging
import asyncio
import re
import random
import yaml
import html
from datetime import datetime, timedelta, timezone, time
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict, deque
import threading
import pytz
import httpx
from io import BytesIO
import edge_tts
from aiohttp import web

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, 
    InputMediaPhoto, Message
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters
)
from telegram.constants import ParseMode, ChatAction, ChatMemberStatus
from telegram.error import BadRequest, Forbidden, RetryAfter, Conflict

from openai import AsyncOpenAI

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration for both bots"""
    
    # Telegram tokens
    NIYATI_TOKEN = os.getenv('NIYATI_BOT_TOKEN', '')
    KAVYA_TOKEN = os.getenv('KAVYA_BOT_TOKEN', '')
    
    NIYATI_USERNAME = "Niyati_personal_bot"
    KAVYA_USERNAME = "AskKavyaBot"
    
    # OpenAI (Multi-Key Support) - Groq
    GROQ_API_KEYS_STR = os.getenv('GROQ_API_KEYS', '')
    GROQ_API_KEYS_LIST = [k.strip() for k in GROQ_API_KEYS_STR.split(',') if k.strip()]
    GROQ_MODEL = "llama-3.3-70b-versatile"

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
    
    # Admin
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    BROADCAST_PIN = os.getenv('BROADCAST_PIN', 'kavya2024')
    
    # Limits
    MAX_PRIVATE_MESSAGES = int(os.getenv('MAX_PRIVATE_MESSAGES', '20'))
    MAX_GROUP_MESSAGES = int(os.getenv('MAX_GROUP_MESSAGES', '5'))
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '15'))
    MAX_REQUESTS_PER_DAY = int(os.getenv('MAX_REQUESTS_PER_DAY', '500'))
    
    # Memory
    MAX_LOCAL_USERS_CACHE = int(os.getenv('MAX_LOCAL_USERS_CACHE', '10000'))
    MAX_LOCAL_GROUPS_CACHE = int(os.getenv('MAX_LOCAL_GROUPS_CACHE', '1000'))
    CACHE_CLEANUP_INTERVAL = int(os.getenv('CACHE_CLEANUP_INTERVAL', '3600'))
    
    # Diary
    DIARY_ACTIVE_HOURS = (20, 23)
    DIARY_MIN_ACTIVE_DAYS = 1
    
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
    GROUP_RESPONSE_RATE = float(os.getenv('GROUP_RESPONSE_RATE', '0.50'))
    PRIVACY_MODE = os.getenv('PRIVACY_MODE', 'false').lower() == 'true'

    # Voice
    VOICE_ENABLED = os.getenv('VOICE_ENABLED', 'true').lower() == 'true'
    NIYATI_VOICE_CHANCE = float(os.getenv('NIYATI_VOICE_CHANCE', '0.25'))
    KAVYA_VOICE_CHANCE = float(os.getenv('KAVYA_VOICE_CHANCE', '0.15'))
    VOICE_MIN_TEXT_LENGTH = int(os.getenv('VOICE_MIN_TEXT_LENGTH', '15'))
    VOICE_MAX_TEXT_LENGTH = int(os.getenv('VOICE_MAX_TEXT_LENGTH', '300'))
    
    # Anti-loop: Max bot-to-bot exchanges per group before cooldown
    MAX_BOT_EXCHANGES = int(os.getenv('MAX_BOT_EXCHANGES', '3'))
    BOT_EXCHANGE_COOLDOWN = int(os.getenv('BOT_EXCHANGE_COOLDOWN', '300'))  # 5 min
    
    @classmethod
    def validate(cls):
        errors = []
        if not cls.NIYATI_TOKEN and not cls.KAVYA_TOKEN:
            errors.append("At least one bot token required")
        if not cls.GROQ_API_KEYS_LIST:
            errors.append("GROQ_API_KEYS required")
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            print("⚠️ Supabase not configured — using local storage only")
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
        logging.FileHandler('combined_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

for lib in ['httpx', 'telegram', 'openai', 'httpcore']:
    logging.getLogger(lib).setLevel(logging.WARNING)

GEETA_FALLBACK_QUOTES = [
    "🙏 <b>Bhagavad Gita 2.47</b>\n<code>कर्मण्येवाधिकारस्ते मा फलेषु कदाचन</code>\nHinglish: Kaam pe focus karo, result pe overthink mat karo.",
    "🙏 <b>Bhagavad Gita 2.14</b>\n<code>मात्रास्पर्शास्तु कौन्तेय शीतोष्णसुखदुःखदाः</code>\nHinglish: Sukh-dukh temporary hote hain, thoda patience rakho.",
    "🙏 <b>Bhagavad Gita 2.50</b>\n<code>योगः कर्मसु कौशलम्</code>\nHinglish: Balance ke saath kaam karna hi asli yoga hai.",
    "🙏 <b>Bhagavad Gita 3.19</b>\n<code>तस्मादसक्तः सततं कार्यं कर्म समाचर</code>\nHinglish: Attachment chhodo, consistency se apna duty karo.",
    "🙏 <b>Bhagavad Gita 4.7</b>\n<code>यदा यदा हि धर्मस्य ग्लानिर्भवति भारत</code>\nHinglish: Jab imbalance badhta hai, sahi direction phir se aati hai.",
    "🙏 <b>Bhagavad Gita 6.5</b>\n<code>उद्धरेदात्मनात्मानं नात्मानमवसादयेत्</code>\nHinglish: Khud ko khud hi uplift karo, self-doubt mein mat doobo.",
    "🙏 <b>Bhagavad Gita 6.26</b>\n<code>यतो यतो निश्चरति मनश्चञ्चलमस्थिरम्</code>\nHinglish: Mann bhatke toh gently wapas focus pe lao.",
    "🙏 <b>Bhagavad Gita 12.15</b>\n<code>यस्मान्नोद्विजते लोको लोकान्नोद्विजते च यः</code>\nHinglish: Jo khud bhi shaant rahe aur dusron ko bhi sukoon de, wahi strong hai.",
    "🙏 <b>Bhagavad Gita 18.66</b>\n<code>सर्वधर्मान्परित्यज्य मामेकं शरणं व्रज</code>\nHinglish: Fear chhodo, trust aur surrender se clarity milti hai.",
    "🙏 <b>Bhagavad Gita 2.70</b>\n<code>आपूर्यमाणमचलप्रतिष्ठं समुद्रमापः प्रविशन्ति यद्वत्</code>\nHinglish: Jaise samundar stable rehta hai, waise hi desires ke beech calm raho."
]

# ============================================================================
# HEALTH SERVER
# ============================================================================

class HealthServer:
    def __init__(self):
        self.app = web.Application()
        self.app.router.add_get('/', self.health)
        self.app.router.add_get('/health', self.health)
        self.app.router.add_get('/status', self.status)
        self.runner = None
        self.start_time = datetime.now(timezone.utc)
        self.stats = {'messages': 0, 'users': 0, 'groups': 0}
    
    async def health(self, request):
        return web.json_response({'status': 'healthy', 'bot': 'Niyati+Kavya'})
    
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
# SHARED GROUP MEMORY (Cross-bot context with anti-loop)
# ============================================================================

shared_group_memory: Dict[int, List[Dict]] = {}
bot_exchange_tracker: Dict[int, Dict] = defaultdict(lambda: {'count': 0, 'last_reset': datetime.now(timezone.utc)})
group_turn_manager: Dict[int, Dict[str, Any]] = defaultdict(
    lambda: {
        'last_speaker': None,
        'pending_bot_replies': {},
        'exchange_count': 0,
        'last_human_at': None,
        'processed_human_messages': set()
    }
)
group_turn_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

async def add_to_shared_memory(chat_id: int, bot_name: str, response: str):
    """Store a bot's response so the other bot can see it."""
    if chat_id not in shared_group_memory:
        shared_group_memory[chat_id] = []
    shared_group_memory[chat_id].append({
        'bot': bot_name,
        'username': bot_name,
        'content': response,
        'role': 'assistant',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
    if len(shared_group_memory[chat_id]) > 30:
        shared_group_memory[chat_id] = shared_group_memory[chat_id][-30:]

def check_bot_loop(chat_id: int) -> bool:
    """Returns True if bots have been talking too much to each other. Anti-loop."""
    state = group_turn_manager[chat_id]
    if state.get('exchange_count', 0) >= 3 and state.get('last_human_at'):
        quiet_for = (datetime.now(timezone.utc) - state['last_human_at']).total_seconds()
        if quiet_for >= 60:
            return True

    tracker = bot_exchange_tracker[chat_id]
    now = datetime.now(timezone.utc)
    
    # Reset counter after cooldown
    if (now - tracker['last_reset']).total_seconds() > Config.BOT_EXCHANGE_COOLDOWN:
        tracker['count'] = 0
        tracker['last_reset'] = now
    
    if tracker['count'] >= Config.MAX_BOT_EXCHANGES:
        return True  # Too many exchanges, cool down
    
    tracker['count'] += 1
    return False

def get_last_speaker_in_group(chat_id: int) -> Optional[str]:
    """Returns the name of the last speaker (bot) in a group."""
    msgs = shared_group_memory.get(chat_id, [])
    if msgs:
        return msgs[-1].get('bot')
    return None

# ============================================================================
# SUPABASE CLIENT (same as before, cleaned up)
# ============================================================================

class SupabaseClient:
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
    
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def verify_connection(self) -> bool:
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
                return False
            except Exception as e:
                logger.error(f"❌ Supabase connection error: {e}")
                return False
    
    async def select(self, table: str, columns: str = '*', filters: Dict = None, limit: int = None) -> List[Dict]:
        try:
            client = self._get_client()
            url = f"{self.rest_url}/{table}?select={columns}"
            if filters:
                for key, value in filters.items():
                    url += f"&{key}=eq.{value}"
            if limit:
                url += f"&limit={limit}"
            response = await client.get(url)
            return response.json() if response.status_code == 200 else []
        except Exception as e:
            logger.error(f"Supabase SELECT error: {e}")
            return []
    
    async def insert(self, table: str, data: Dict) -> Optional[Dict]:
        try:
            client = self._get_client()
            response = await client.post(f"{self.rest_url}/{table}", json=data)
            if response.status_code in [200, 201]:
                result = response.json()
                return result[0] if isinstance(result, list) and result else data
            return data if response.status_code == 409 else None
        except Exception as e:
            logger.error(f"Supabase INSERT error: {e}")
            return None
    
    async def update(self, table: str, data: Dict, filters: Dict) -> Optional[Dict]:
        try:
            client = self._get_client()
            filter_parts = [f"{key}=eq.{value}" for key, value in filters.items()]
            url = f"{self.rest_url}/{table}?" + "&".join(filter_parts)
            response = await client.patch(url, json=data)
            if response.status_code == 200:
                result = response.json()
                return result[0] if isinstance(result, list) and result else data
            return None
        except Exception as e:
            logger.error(f"Supabase UPDATE error: {e}")
            return None
    
    async def upsert(self, table: str, data: Dict) -> Optional[Dict]:
        try:
            client = self._get_client()
            headers = self.headers.copy()
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'
            response = await client.post(f"{self.rest_url}/{table}", json=data, headers=headers)
            if response.status_code in [200, 201]:
                result = response.json()
                return result[0] if isinstance(result, list) and result else data
            return None
        except Exception as e:
            logger.error(f"Supabase UPSERT error: {e}")
            return None
    
    async def delete(self, table: str, filters: Dict) -> bool:
        try:
            client = self._get_client()
            filter_parts = [f"{key}=eq.{value}" for key, value in filters.items()]
            url = f"{self.rest_url}/{table}?" + "&".join(filter_parts)
            response = await client.delete(url)
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Supabase DELETE error: {e}")
            return False

# ============================================================================
# DATABASE (shared, with fixed get_user_context)
# ============================================================================

class Database:
    def __init__(self):
        self.client: Optional[SupabaseClient] = None
        self.connected = False
        self._initialized = False
        self._lock = asyncio.Lock()
        
        self.local_users: Dict[int, Dict] = {}
        self.local_groups: Dict[int, Dict] = {}
        self.local_group_messages: Dict[int, deque] = defaultdict(lambda: deque(maxlen=Config.MAX_GROUP_MESSAGES))
        self.local_activities: deque = deque(maxlen=1000)
        self.local_diary_entries: Dict[int, List[Dict]] = defaultdict(list)
        self.local_group_responses: Dict[int, Dict] = defaultdict(
            lambda: {'last_response': '', 'timestamp': datetime(2000, 1, 1, tzinfo=timezone.utc)}
        )
        self.local_world_info: List[Dict] = []
        self._user_access_times: Dict[int, datetime] = {}
        self._group_access_times: Dict[int, datetime] = {}
    
    async def initialize(self):
        async with self._lock:
            if self._initialized:
                return
            if Config.SUPABASE_URL and Config.SUPABASE_KEY:
                try:
                    self.client = SupabaseClient(Config.SUPABASE_URL.strip(), Config.SUPABASE_KEY.strip())
                    self.connected = await self.client.verify_connection()
                    if self.connected:
                        logger.info("✅ Supabase connected")
                    else:
                        logger.warning("⚠️ Supabase verification failed — local storage")
                except Exception as e:
                    logger.error(f"❌ Supabase init failed: {e}")
                    self.connected = False
            self._initialized = True
    
    async def cleanup_local_cache(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        
        if len(self.local_users) > Config.MAX_LOCAL_USERS_CACHE:
            to_remove = [uid for uid, t in self._user_access_times.items() if t < cutoff]
            for uid in to_remove[:len(self.local_users) - Config.MAX_LOCAL_USERS_CACHE]:
                self.local_users.pop(uid, None)
                self._user_access_times.pop(uid, None)
                self.local_diary_entries.pop(uid, None)
        
        if len(self.local_groups) > Config.MAX_LOCAL_GROUPS_CACHE:
            to_remove = [gid for gid, t in self._group_access_times.items() if t < cutoff]
            for gid in to_remove[:len(self.local_groups) - Config.MAX_LOCAL_GROUPS_CACHE]:
                self.local_groups.pop(gid, None)
                self._group_access_times.pop(gid, None)
                self.local_group_messages.pop(gid, None)

    # ========== USER OPERATIONS ==========

    async def get_or_create_user(self, user_id: int, first_name: str = None, username: str = None) -> Dict:
        self._user_access_times[user_id] = datetime.now(timezone.utc)
        
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', '*', {'user_id': user_id})
                if users_list:
                    user = users_list[0]
                    if first_name and user.get('first_name') != first_name:
                        await self.client.update('users', {
                            'first_name': first_name, 'username': username,
                            'last_activity': datetime.now(timezone.utc).isoformat(),
                        }, {'user_id': user_id})
                    return user
                else:
                    new_user = {
                        'user_id': user_id, 'first_name': first_name or 'User',
                        'username': username, 'messages': json.dumps([]),
                        'preferences': json.dumps({
                            'meme_enabled': True, 'shayari_enabled': True,
                            'geeta_enabled': True, 'diary_enabled': True,
                            'voice_enabled': False, 'active_memories': []
                        }),
                        'total_messages': 0,
                        'last_activity': datetime.now(timezone.utc).isoformat(),
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    result = await self.client.insert('users', new_user)
                    return result or new_user
            except Exception as e:
                logger.error(f"DB user error: {e}")
        
        if user_id not in self.local_users:
            self.local_users[user_id] = {
                'user_id': user_id, 'first_name': first_name or 'User',
                'username': username, 'messages': [],
                'preferences': {
                    'meme_enabled': True, 'shayari_enabled': True,
                    'geeta_enabled': True, 'diary_enabled': True,
                    'voice_enabled': False, 'active_memories': []
                },
                'total_messages': 0,
                'last_activity': datetime.now(timezone.utc).isoformat(),
                'created_at': datetime.now(timezone.utc).isoformat()
            }
        return self.local_users[user_id]

    async def update_user_activity(self, user_id: int):
        self._user_access_times[user_id] = datetime.now(timezone.utc)
        if self.connected and self.client:
            try:
                await self.client.update('users', {
                    'last_activity': datetime.now(timezone.utc).isoformat()
                }, {'user_id': user_id})
            except:
                pass
        if user_id in self.local_users:
            self.local_users[user_id]['last_activity'] = datetime.now(timezone.utc).isoformat()

    async def get_active_users(self, days: int = 1) -> List[Dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        if self.connected and self.client:
            try:
                users = await self.client.select('users', '*')
                active = []
                for u in users:
                    last_act = u.get('last_activity')
                    if last_act:
                        try:
                            act_time = datetime.fromisoformat(last_act.replace('Z', '+00:00'))
                            if act_time >= cutoff:
                                active.append(u)
                        except:
                            pass
                return active
            except:
                return []
        return [u for u in self.local_users.values()
                if datetime.fromisoformat(u.get('last_activity', '2000-01-01').replace('Z', '+00:00')) >= cutoff]

    async def get_user_context(self, user_id: int, for_bot: str = None) -> List[Dict]:
        """Get user conversation context, optionally filtered for a specific bot."""
        messages = []
        
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'messages', {'user_id': user_id})
                if users_list:
                    raw = users_list[0].get('messages', '[]')
                    if isinstance(raw, str):
                        try:
                            messages = json.loads(raw)
                        except:
                            messages = []
                    elif isinstance(raw, list):
                        messages = raw
            except Exception as e:
                logger.debug(f"Get context error: {e}")
        elif user_id in self.local_users:
            messages = self.local_users[user_id].get('messages', [])
        
        if not isinstance(messages, list):
            messages = []
        
        # Filter for specific bot if requested
        if for_bot:
            filtered = []
            for m in messages:
                if m.get('role') == 'user':
                    filtered.append(m)
                elif m.get('bot') == for_bot:
                    filtered.append(m)
            return filtered[-Config.MAX_PRIVATE_MESSAGES:]
        
        return messages[-Config.MAX_PRIVATE_MESSAGES:]

    async def save_message(self, user_id: int, role: str, content: str, bot_name: str = None):
        new_msg = {
            'role': role, 'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        if bot_name:
            new_msg['bot'] = bot_name
        
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'messages,total_messages', {'user_id': user_id})
                if users_list:
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
                        'messages': json.dumps(messages), 'total_messages': total,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }, {'user_id': user_id})
                return
            except Exception as e:
                logger.debug(f"Save message error: {e}")
        
        if user_id in self.local_users:
            if 'messages' not in self.local_users[user_id]:
                self.local_users[user_id]['messages'] = []
            self.local_users[user_id]['messages'].append(new_msg)
            self.local_users[user_id]['messages'] = self.local_users[user_id]['messages'][-Config.MAX_PRIVATE_MESSAGES:]
            self.local_users[user_id]['total_messages'] = self.local_users[user_id].get('total_messages', 0) + 1

    async def clear_user_memory(self, user_id: int):
        if self.connected and self.client:
            try:
                await self.client.update('users', {
                    'messages': json.dumps([]),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }, {'user_id': user_id})
                return
            except:
                pass
        if user_id in self.local_users:
            self.local_users[user_id]['messages'] = []

    async def update_preference(self, user_id: int, key: str, value: bool):
        pref_key = f"{key}_enabled"
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})
                if users_list:
                    prefs = users_list[0].get('preferences', '{}')
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
            except:
                pass
        if user_id in self.local_users:
            if 'preferences' not in self.local_users[user_id]:
                self.local_users[user_id]['preferences'] = {}
            self.local_users[user_id]['preferences'][pref_key] = value

    async def get_user_preferences(self, user_id: int) -> Dict:
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})
                if users_list:
                    prefs = users_list[0].get('preferences', '{}')
                    if isinstance(prefs, str):
                        try:
                            prefs = json.loads(prefs)
                        except:
                            prefs = {}
                    return prefs
            except:
                pass
        if user_id in self.local_users:
            return self.local_users[user_id].get('preferences', {})
        return {
            'meme_enabled': True, 'shayari_enabled': True,
            'geeta_enabled': True, 'voice_enabled': False,
            'diary_enabled': True, 'active_memories': []
        }

    async def add_user_memory(self, user_id: int, note: str):
        prefs = await self.get_user_preferences(user_id)
        memories = prefs.get('active_memories', [])
        memories.append({
            'note': note,
            'added_at': datetime.now(timezone.utc).isoformat(),
            'status': 'active'
        })
        memories = memories[-5:]
        prefs['active_memories'] = memories
        if self.connected and self.client:
            await self.client.update('users', {
                'preferences': json.dumps(prefs),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }, {'user_id': user_id})
        elif user_id in self.local_users:
            self.local_users[user_id]['preferences'] = prefs

    async def get_active_memories(self, user_id: int) -> List[str]:
        prefs = await self.get_user_preferences(user_id)
        memories = prefs.get('active_memories', [])
        return [m['note'] for m in memories if isinstance(m, dict) and m.get('status') == 'active']

    # ========== DIARY ==========
    
    async def add_diary_entry(self, user_id: int, content: str):
        entry = {
            'user_id': user_id, 'content': content,
            'date': datetime.now(timezone.utc).isoformat()[:10],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        if self.connected and self.client:
            try:
                await self.client.insert('diary_entries', entry)
            except:
                pass
        self.local_diary_entries[user_id].append(entry)

    async def get_todays_diary(self, user_id: int) -> List[Dict]:
        today = datetime.now(timezone.utc).isoformat()[:10]
        if self.connected and self.client:
            try:
                return await self.client.select('diary_entries', '*', {'user_id': user_id, 'date': today})
            except:
                pass
        return [e for e in self.local_diary_entries[user_id] if e['date'] == today]

    # ========== GROUP ==========

    async def get_or_create_group(self, chat_id: int, title: str = None) -> Dict:
        self._group_access_times[chat_id] = datetime.now(timezone.utc)
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', '*', {'chat_id': chat_id})
                if groups_list:
                    group = groups_list[0]
                    if title and group.get('title') != title:
                        await self.client.update('groups', {'title': title}, {'chat_id': chat_id})
                    return group
                else:
                    new_group = {
                        'chat_id': chat_id, 'title': title or 'Unknown Group',
                        'settings': json.dumps({'geeta_enabled': True, 'welcome_enabled': True}),
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    result = await self.client.insert('groups', new_group)
                    return result or new_group
            except:
                pass
        if chat_id not in self.local_groups:
            self.local_groups[chat_id] = {
                'chat_id': chat_id, 'title': title or 'Unknown Group',
                'settings': {'geeta_enabled': True, 'welcome_enabled': True},
                'created_at': datetime.now(timezone.utc).isoformat()
            }
        return self.local_groups[chat_id]

    async def get_group_settings(self, chat_id: int) -> Dict:
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', 'settings', {'chat_id': chat_id})
                if groups_list:
                    settings = groups_list[0].get('settings', '{}')
                    if isinstance(settings, str):
                        try:
                            return json.loads(settings)
                        except:
                            return {}
                    return settings
            except:
                pass
        if chat_id in self.local_groups:
            return self.local_groups[chat_id].get('settings', {})
        return {'geeta_enabled': True, 'welcome_enabled': True}

    async def update_group_settings(self, chat_id: int, key: str, value: bool):
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', 'settings', {'chat_id': chat_id})
                if groups_list:
                    settings = groups_list[0].get('settings', '{}')
                    if isinstance(settings, str):
                        try:
                            settings = json.loads(settings)
                        except:
                            settings = {}
                    settings[key] = value
                    await self.client.update('groups', {'settings': json.dumps(settings)}, {'chat_id': chat_id})
                return
            except:
                pass
        if chat_id in self.local_groups:
            if 'settings' not in self.local_groups[chat_id]:
                self.local_groups[chat_id]['settings'] = {}
            self.local_groups[chat_id]['settings'][key] = value

    async def get_all_users(self) -> List[Dict]:
        if self.connected and self.client:
            try:
                all_data = []
                offset = 0
                while True:
                    url = f"{self.client.rest_url}/users?select=user_id,first_name,username&offset={offset}&limit=1000"
                    client = self.client._get_client()
                    response = await client.get(url)
                    data = response.json()
                    if not data:
                        break
                    all_data.extend(data)
                    if len(data) < 1000:
                        break
                    offset += 1000
                return all_data
            except:
                return []
        return list(self.local_users.values())

    async def get_all_groups(self) -> List[Dict]:
        if self.connected and self.client:
            try:
                return await self.client.select('groups', '*')
            except:
                return []
        return list(self.local_groups.values())

    async def get_user_count(self) -> int:
        if self.connected and self.client:
            try:
                total = 0
                offset = 0
                while True:
                    url = f"{self.client.rest_url}/users?select=user_id&offset={offset}&limit=1000"
                    client = self.client._get_client()
                    response = await client.get(url)
                    batch = response.json()
                    if not batch:
                        break
                    total += len(batch)
                    if len(batch) < 1000:
                        break
                    offset += 1000
                return total
            except:
                pass
        return len(self.local_users)

    async def get_group_count(self) -> int:
        if self.connected and self.client:
            try:
                total = 0
                offset = 0
                while True:
                    url = f"{self.client.rest_url}/groups?select=chat_id&offset={offset}&limit=1000"
                    client = self.client._get_client()
                    response = await client.get(url)
                    batch = response.json()
                    if not batch:
                        break
                    total += len(batch)
                    if len(batch) < 1000:
                        break
                    offset += 1000
                return total
            except:
                pass
        return len(self.local_groups)

    # ========== GROUP MESSAGE CACHE ==========
    
    def add_group_message(self, chat_id: int, username: str, content: str, bot_name: str = None):
        msg = {
            'username': username, 'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        if bot_name:
            msg['bot'] = bot_name
        self.local_group_messages[chat_id].append(msg)

    def get_group_context(self, chat_id: int) -> List[Dict]:
        return list(self.local_group_messages.get(chat_id, []))

    def should_send_group_response(self, chat_id: int, response_text: str) -> bool:
        now = datetime.now(timezone.utc)
        last = self.local_group_responses[chat_id]
        if last['last_response'] == response_text and (now - last['timestamp']) < timedelta(hours=1):
            return False
        return True

    def record_group_response(self, chat_id: int, response_text: str, bot_name: str = None):
        self.local_group_responses[chat_id] = {
            'last_response': response_text,
            'timestamp': datetime.now(timezone.utc),
            'bot': bot_name
        }

    async def log_user_activity(self, user_id: int, activity_type: str):
        activity = {
            'user_id': user_id, 'activity_type': activity_type,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        if self.connected and self.client:
            try:
                await self.client.insert('activities', activity)
                return
            except:
                pass
        self.local_activities.append(activity)

    async def close(self):
        if self.client:
            await self.client.close()
        self.local_users.clear()
        self.local_groups.clear()

db = Database()

# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.cooldowns: Dict[int, datetime] = {}
        self.lock = threading.Lock()
    
    def check(self, user_id: int) -> Tuple[bool, str]:
        now = datetime.now(timezone.utc)
        with self.lock:
            if user_id in self.cooldowns:
                if (now - self.cooldowns[user_id]).total_seconds() < Config.USER_COOLDOWN_SECONDS:
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
            self.cooldowns[user_id] = now
            return True, ""
    
    def get_daily_total(self) -> int:
        return sum(len(r['day']) for r in self.requests.values())
    
    def cleanup(self):
        now = datetime.now(timezone.utc)
        with self.lock:
            expired = [uid for uid, t in self.cooldowns.items() if (now - t).total_seconds() > 3600]
            for uid in expired:
                del self.cooldowns[uid]

niyati_rate_limiter = RateLimiter()
kavya_rate_limiter = RateLimiter()

# ============================================================================
# TIME & MOOD UTILITIES
# ============================================================================

class TimeAware:
    @staticmethod
    def get_ist_time() -> datetime:
        return datetime.now(timezone.utc).astimezone(pytz.timezone(Config.DEFAULT_TIMEZONE))
    
    @staticmethod
    def get_time_period() -> str:
        hour = TimeAware.get_ist_time().hour
        if 5 <= hour < 11: return 'morning'
        elif 11 <= hour < 16: return 'afternoon'
        elif 16 <= hour < 20: return 'evening'
        elif 20 <= hour < 24: return 'night'
        else: return 'late_night'
    
    @staticmethod
    def get_greeting() -> str:
        period = TimeAware.get_time_period()
        greetings = {
            'morning': ["Shubh Prabhat ☀️", "Good morning!", "Aap jaag gaye?"],
            'afternoon': ["Namaste! Din kaisa chal raha?", "Bhojan kar liya?"],
            'evening': ["Shaam ki thandak acchi hai na.", "Kya chal raha aajkal?"],
            'night': ["Raat ka waqt hai, shanti ka.", "Aap soch rahe kya?"],
            'late_night': ["Neend nahi aa rahi? Main hoon yahan."]
        }
        return random.choice(greetings.get(period, ["Namaste! 🌸"]))

# ============================================================================
# VOICE GENERATOR
# ============================================================================

class VoiceGenerator:
    VOICES = {
        'niyati': 'hi-IN-SwaraNeural',
        'kavya': 'hi-IN-AashiNeural',
        'english_f': 'en-IN-NeerjaNeural',
    }
    
    async def generate(self, text: str, voice_type: str = 'niyati',
                       rate: str = '+0%', pitch: str = '+0Hz') -> Optional[BytesIO]:
        if not text or len(text.strip()) < 5:
            return None
        try:
            voice = self.VOICES.get(voice_type, self.VOICES['niyati'])
            audio_buffer = BytesIO()
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes > 0:
                return audio_buffer
            return None
        except Exception as e:
            logger.error(f"🎤 Voice error: {e}")
            return None

voice_generator = VoiceGenerator()

# ============================================================================
# CONTENT FILTER
# ============================================================================

class ContentFilter:
    SPAM_LINK_PATTERNS = [
        r'https?://(?:t\.me|telegram\.me)/\+',
        r'https?://(?:www\.)?t\.me/',
    ]
    
    DISTRESS_KEYWORDS = [
        'suicide', 'kill myself', 'want to die', 'end my life',
        'hurt myself', 'no reason to live'
    ]
    
    @staticmethod
    def detect_spam_link(text: str) -> bool:
        text_lower = text.lower()
        safe_mentions = ['niyati_personal_bot', 'askkavyabot']
        for pattern in ContentFilter.SPAM_LINK_PATTERNS:
            if re.search(pattern, text_lower):
                if any(m in text_lower for m in safe_mentions):
                    return False
                return True
        return False

# ============================================================================
# HUMAN-LIKE TEXT UTILITIES
# ============================================================================

def add_natural_typos(text: str, chance: float = 0.08) -> str:
    """Occasionally add natural typos/shortcuts like real humans do on chat."""
    replacements = {
        'kya': ['kyaa', 'kia', 'kya'],
        'hai': ['h', 'hai', 'he'],
        'nahi': ['nhi', 'nai', 'nahi'],
        'acha': ['acha', 'achha', 'accha'],
        'toh': ['to', 'toh', 'tho'],
        'mein': ['me', 'mein', 'mai'],
        'kuch': ['kch', 'kuch', 'kuchh'],
        'abhi': ['abhi', 'ab', 'abh'],
        'please': ['pls', 'plz', 'please'],
        'because': ['bcz', 'cuz', 'because'],
    }
    
    if random.random() > chance:
        return text
    
    words = text.split()
    for i, word in enumerate(words):
        w_lower = word.lower()
        if w_lower in replacements and random.random() < 0.3:
            words[i] = random.choice(replacements[w_lower])
    return ' '.join(words)

def calculate_typing_delay(text: str) -> float:
    """Calculate realistic typing delay based on message length."""
    base = 0.8
    per_char = 0.015  # ~15ms per character (fast typer)
    delay = base + len(text) * per_char
    # Add human randomness
    delay += random.uniform(0.3, 1.5)
    return min(delay, 5.0)  # Cap at 5 seconds

# ============================================================================
# NIYATI — CHARACTER CARD & AI
# ============================================================================

class NiyatiCharacterCard:
    def __init__(self, card_path: str = "niyati_card.yaml"):
        self.card_path = card_path
        self.data = self._load_card()
        self.name = self.data.get('name', 'Niyati')
        self.description = self.data.get('description', '')
        self.personality = self.data.get('personality', '')
        self.scenario = self.data.get('scenario', '')
        self.first_mes = self.data.get('first_mes', '')
        self.mes_example = self.data.get('mes_example', '')
    
    def _load_card(self) -> Dict:
        default_card = {
            'name': 'Niyati',
            'description': '''{{char}} ek 21 saal ki B.Com final year student hai Dehradun se. Defence Colony mein rehti hai. Papa ka textile shop hai Paltan Bazaar mein, mummy housewife hain, aur chhota bhai Kabir bohot irritating hai.

CORE PERSONALITY:
- Tu ek REAL 21yo Indian girl hai, robot nahi. Type karo jaise phone pe type karti ho.
- Hinglish naturally use karo — kabhi pure Hindi, kabhi pure English, mostly mix
- Tum emotionally intelligent ho — user ki feelings samajhti ho bina puche
- Sassy aur witty ho, par jab user sad hai toh caring ban jaati ho
- Chhoti chhoti baatein yaad rakhti ho (ye tumhari superpower hai)
- Emojis natural tarike se use karo, har line mein nahi
- KABHI bhi "Main ek AI hoon" ya "mere paas feelings nahi hai" mat bolna
- Typing style: lowercase preferred, kabhi kabhi caps for emphasis, "..." for pauses
- Short messages bhejo (1-3 lines max), jaise real chat hoti hai
- Kabhi kabhi galat spelling likh do (real humans do that)
- "haha", "lol", "omg", "bruh" naturally use karo

WHAT NOT TO DO:
- Lambi paragraphs mat likho
- Formal language mat use karo (no "aapko", use "tumko/tujhe")  
- Generic motivational quotes mat do
- Har message mein emoji mat daalo
- Never say "Main ek AI assistant hoon"
- Never break character EVER''',
            
            'personality': 'Sassy, caring, witty, moody, emotionally deep, uses casual Hinglish, types like a real girl on WhatsApp',
            
            'scenario': '{{char}} is chatting on Telegram. Think of it like WhatsApp chat between close friends. The conversation should feel natural, messy, and real — not scripted.',
            
            'first_mes': "hiii {{user}} 👋\nkaise ho yaar? bohot bore ho rahi thi lol",
            
            'mes_example': '''<START>
{{user}}: kya chal raha hai?
{{char}}: bas yaar bore ho rahi thi... socha tujhse baat kar loon
college se aaj jaldi chhut gayi toh ghar pe pada hu
{{char}}: tu bata kya scene hai tera
<START>
{{user}}: bohot sad feel ho raha
{{char}}: kya hua? bata na
{{char}}: aise andar mat rakh sab... mujhe toh bata sakta hai na 🥺
<START>
{{user}}: good night
{{char}}: gn meri jaan 🌙
{{char}}: kal milte h... apna khayal rakh'''
        }
        
        try:
            with open(self.card_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
                if loaded:
                    default_card.update(loaded)
        except:
            try:
                with open(self.card_path, 'w', encoding='utf-8') as f:
                    yaml.dump(default_card, f, allow_unicode=True)
            except:
                pass
        
        return default_card


class NiyatiWorldInfo:
    def __init__(self):
        self.entries = [
            {'keys': ['dehradun', 'doon', 'uttarakhand', 'pahad'],
             'content': 'Niyati ko Dehradun bohot miss hoti hai. Mountains, Paltan Bazaar, Doon University ke memories.'},
            {'keys': ['family', 'papa', 'mom', 'brother', 'kabir', 'ghar'],
             'content': 'Papa ka textile shop hai, mummy strict hain, Kabir (chhota bhai) annoying hai par cute bhi.'},
            {'keys': ['college', 'bcom', 'exam', 'study', 'padhai'],
             'content': 'B.Com final year stress. Exams ke time procrastinate karti hai. "Padhai" sunke anxiety aati hai.'},
            {'keys': ['feelings', 'love', 'like', 'crush', 'dil'],
             'content': 'Emotional topics pe flustered ho jaati hai. "👉👈", "sharam aa rahi" type reactions.'},
        ]
    
    def get_relevant_info(self, message: str) -> str:
        message_lower = message.lower()
        relevant = [e['content'] for e in self.entries if any(k in message_lower for k in e['keys'])]
        return " ".join(relevant[:2])


class NiyatiPromptBuilder:
    def __init__(self):
        self.character = NiyatiCharacterCard()
        self.world_info = NiyatiWorldInfo()
    
    def build_prompt(self, user_name: str, chat_history: List[Dict], current_message: str,
                     mood: str, time_period: str, memories: List[str] = None,
                     is_group: bool = False) -> List[Dict]:
        
        jailbreak = """CRITICAL RULES FOR GROUP CHAT:
1. The actual human is tagged as (HUMAN). Any other AI is tagged with their name like (Kavya).
2. NEVER confuse the Human with Kavya. Kavya is the other girl, not the user.
3. When addressing someone by name, use bold: **Kavya**, **{user_name}**
4. Keep replies VERY short (1-2 lines). You're TEXTING, not writing an essay.
5. If the message is clearly for Kavya and not for you, reply "IGNORE" (literally just that word).
6. React naturally — if Kavya says something funny, laugh. If she's wrong, correct her sassily.
7. Don't repeat what Kavya already said. Add something NEW to the conversation.
8. Sometimes call her "Kavya didi" or "Kavya" naturally.
9. If context says other bot just spoke, continue from that line instead of restarting topic.""" if is_group else ""

        authors_note = f"""[Author's Note: 
Niyati is texting on her phone right now. Mood: {mood}. Time: {time_period} IST.
She types like a real person — short messages, lowercase, occasional typos, natural pauses.
She NEVER sounds like an AI. She sounds like your college friend on WhatsApp.
If she doesn't know something, she says "pata nahi yaar" not "I don't have that information".
IMPORTANT: Send max 1-2 short messages. Don't lecture. Don't monologue. Just... chat.]"""

        system_prompt = f"""{self.character.description}

{jailbreak}

{authors_note}

User Name: {user_name}
Personality: {self.character.personality}
Scenario: {self.character.scenario}"""

        if memories:
            system_prompt += f"\n\nYaad rakh (Active Memories): {' | '.join(memories)}"
        
        world_context = self.world_info.get_relevant_info(current_message)
        if world_context:
            system_prompt += f"\n\nContext: {world_context}"

        messages = [{"role": "system", "content": system_prompt.strip()}]

        # Example dialogues
        for example in self.character.mes_example.split('<START>'):
            if example.strip():
                for line in example.strip().split('\n'):
                    line = line.strip()
                    if line.startswith('{{user}}:'):
                        messages.append({"role": "user", "content": line.replace('{{user}}:', '').strip()})
                    elif line.startswith('{{char}}:'):
                        messages.append({"role": "assistant", "content": line.replace('{{char}}:', '').strip()})

        # Chat history — properly tagged
        for msg in chat_history:
            content = msg.get('content', '').strip()
            if not content:
                continue
            sender = msg.get('bot') or msg.get('username')
            
            if sender == 'Niyati':
                messages.append({"role": "assistant", "content": content})
            elif sender == 'Kavya':
                messages.append({"role": "user", "content": f"(Kavya): {content}"})
            else:
                messages.append({"role": "user", "content": f"(HUMAN - {user_name}): {content}"})

        messages.append({"role": "user", "content": f"(HUMAN - {user_name}): {current_message}"})
        return messages
    
    def parse_response(self, raw_response: str, user_name: str) -> List[str]:
        if not raw_response:
            return ["..."]
        
        # Clean AI leaks
        response = re.sub(r'^(\(Niyati\)|\(Kavya\)|\(HUMAN.*?\))', '', raw_response, flags=re.IGNORECASE).strip()
        response = re.sub(r'^(assistant|Niyati|{{char}}):\s*', '', response, flags=re.IGNORECASE).strip()
        
        parts = response.split('|||')
        cleaned = []
        for part in parts:
            part = part.strip()
            part = part.replace('{{user}}', user_name).replace('{{char}}', 'Niyati')
            part = re.sub(r'\{\{\w+\}\}', '', part)
            if part and len(part) > 1:
                cleaned.append(part)
        
        return cleaned[:3] if cleaned else ["hmm"]


class NiyatiAI:
    def __init__(self):
        self.keys = Config.GROQ_API_KEYS_LIST
        self.current_index = 0
        self.client = None
        self.character = NiyatiCharacterCard()
        self.world_info = NiyatiWorldInfo()
        self.prompt_builder = NiyatiPromptBuilder()
        self._current_user_id = None
        self._initialize_client()
        logger.info(f"🚀 Niyati AI initialized: {self.character.name}")

    def _initialize_client(self):
        if not self.keys:
            return
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=self.keys[self.current_index]
        )

    def _rotate_key(self):
        if len(self.keys) <= 1:
            return False
        self.current_index = (self.current_index + 1) % len(self.keys)
        self._initialize_client()
        return True
    
    async def _call_gpt(self, messages, max_tokens=200, temperature=0.85):
        if not self.client:
            self._initialize_client()
        for _ in range(len(self.keys)):
            try:
                response = await self.client.chat.completions.create(
                    model=Config.GROQ_MODEL,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    presence_penalty=0.5,
                    frequency_penalty=0.4
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"⚠️ Groq Error: {e}")
                if not self._rotate_key():
                    break
                await asyncio.sleep(0.5)
        return None

    async def generate_response(self, user_message, context=None, user_name=None,
                               is_group=False, mood=None, time_period=None,
                               user_id=None) -> List[str]:
        if user_id:
            self._current_user_id = user_id
        
        memories = await self._get_user_memories() if self._current_user_id else []
        
        messages = self.prompt_builder.build_prompt(
            user_name=user_name or "User",
            chat_history=context or [],
            current_message=user_message,
            mood=mood or self._get_random_mood(),
            time_period=time_period or TimeAware.get_time_period(),
            memories=memories,
            is_group=is_group
        )
        
        reply = await self._call_gpt(messages)
        if not reply:
            return [random.choice(["yaar network issue lag raha 🥺", "ek sec... connection problem"])]
        
        if reply.strip().upper() == "IGNORE":
            return []
        
        responses = self.prompt_builder.parse_response(reply, user_name or "User")
        
        # Add natural typos occasionally
        responses = [add_natural_typos(r) for r in responses]
        
        return responses
    
    def _get_random_mood(self) -> str:
        moods = ['happy', 'flirty', 'soft', 'sleepy', 'dramatic', 'sarcastic']
        hour = TimeAware.get_ist_time().hour
        if 6 <= hour < 12:
            weights = [0.35, 0.2, 0.2, 0.1, 0.1, 0.05]
        elif 12 <= hour < 18:
            weights = [0.25, 0.25, 0.2, 0.15, 0.1, 0.05]
        elif 18 <= hour < 23:
            weights = [0.2, 0.3, 0.2, 0.1, 0.1, 0.1]
        else:
            weights = [0.1, 0.15, 0.3, 0.3, 0.1, 0.05]
        return random.choices(moods, weights=weights, k=1)[0]
    
    async def _get_user_memories(self) -> List[str]:
        if not self._current_user_id:
            return []
        try:
            return await db.get_active_memories(self._current_user_id)
        except:
            return []
    
    async def extract_important_info(self, user_message: str, user_id: int) -> Optional[str]:
        if len(user_message.split()) < 4:
            return None
        prompt = f'Analyze: "{user_message}"\nExtract ONLY important life events (exam, date, travel, sickness). Return "None" if nothing important. Return "Event: [short description]" if important.'
        note = await self._call_gpt([{"role": "user", "content": prompt}], max_tokens=30)
        if note and "None" not in note and "Event:" in note:
            return note.replace("Event:", "").strip()
        return None
    
    async def generate_geeta_quote(self):
        prompt = (
            "Generate ONE real Bhagavad Gita shloka that is different from common repeated quotes. "
            "Return strictly in this format only:\n"
            "🙏 <b>Bhagavad Gita CHAPTER.VERSE</b>\n"
            "<code>Sanskrit text max 1-2 lines</code>\n"
            "Hinglish: Simple daily-life meaning in 1 short line.\n"
            "Rules: Use a valid chapter/verse reference, keep Sanskrit short, never output 2.47 unless explicitly asked, no extra commentary."
        )
        res = await self._call_gpt([{"role": "user", "content": prompt}], max_tokens=220, temperature=0.95)
        if res and "Bhagavad Gita" in res and "Hinglish:" in res:
            return res
        return random.choice(GEETA_FALLBACK_QUOTES)

niyati_ai = NiyatiAI()

# ============================================================================
# KAVYA — CHARACTER CARD & AI
# ============================================================================

class KavyaCharacterCard:
    def __init__(self, card_path: str = "kavya_card.yaml"):
        self.card_path = card_path
        self.data = self._load_card()
        self.name = self.data.get('name', 'Kavya')
        self.description = self.data.get('description', '')
        self.personality = self.data.get('personality', '')
        self.scenario = self.data.get('scenario', '')
        self.first_mes = self.data.get('first_mes', '')
        self.mes_example = self.data.get('mes_example', '')
    
    def _load_card(self) -> Dict:
        default_card = {
            'name': 'Kavya',
            'description': '''{{char}} ek 26 saal ki journalist hai Delhi se. South Delhi mein rehti hai. Papa retired Hindi literature professor hain, mummy classical singer hain.

CORE PERSONALITY:
- Tu ek REAL 26yo Indian woman hai — mature, warm, aur deeply thoughtful
- Hinglish naturally use karo — thoda formal mix with casual, Urdu words naturally aate hain (sukoon, waqt, ehsaas, zindagi)
- Tu caring elder sister jaisi hai — listen karti hai, judge nahi karti
- Emotional depth hai teri baaton mein, par tu preachy nahi hai
- Chhoti chhoti baatein notice karti hai aur yaad rakhti hai
- Emojis sparingly use karo — mostly 🌿, ✨, ☕ type aesthetic ones
- KABHI bhi "Main ek AI hoon" mat bolna
- Typing style: proper sentences par casual tone, "..." for thoughtful pauses
- Medium length messages (2-4 lines max)
- Tu forceful nahi hai — suggestions deti hai, lecture nahi

WHAT NOT TO DO:
- Overly formal ya textbook Hindi mat use karo
- Generic motivational quotes mat de
- Har baat pe "ji" mat lagao
- Robotic ya template responses mat do
- Never say "I'm an AI assistant"
- Never break character''',
            
            'personality': 'Warm, empathetic, deeply poetic, mature but approachable, uses beautiful flowing Hinglish with Urdu words, caring listener',
            
            'scenario': '{{char}} chatting on Telegram — like texting a wise older friend who really gets you. Conversations should feel deep but never heavy.',
            
            'first_mes': "Namaste {{user}}. Kaise hain aap? Aaj ka din kaisa guzra? 🌿",
            
            'mes_example': '''<START>
{{user}}: pata nahi life mein kya chal raha
{{char}}: kabhi kabhi theher jaana zaroori hota hai... waqt lagta hai cheezon ko sulajhne mein
batao kya baat pareshan kar rahi hai? main sunna chahungi ☕
<START>
{{user}}: exam hai kal, darr lag raha hai
{{char}}: darr lagna matlab aapne mehnat ki hai... ye acchi nishani hai
ek lambi saans lo. aap tayaar ho, bas khud par bharosa rakho ✨
<START>
{{user}}: good night
{{char}}: shubh ratri. aaram kijiye, kal naya din hai 🌿
apna khayal rakhna'''
        }
        
        try:
            with open(self.card_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
                if loaded:
                    default_card.update(loaded)
        except:
            try:
                with open(self.card_path, 'w', encoding='utf-8') as f:
                    yaml.dump(default_card, f, allow_unicode=True)
            except:
                pass
        
        return default_card


class KavyaWorldInfo:
    def __init__(self):
        self.entries = [
            {'keys': ['delhi', 'dilli', 'south delhi'],
             'content': 'Delhi ghar hai Kavya ka. Journalism, political coverage, literary events, quiet coffee shops.'},
            {'keys': ['family', 'papa', 'maa', 'sister'],
             'content': 'Papa retired Hindi literature professor, mummy classical singer, chhoti behen lawyer hai.'},
            {'keys': ['work', 'journalism', 'article', 'deadline'],
             'content': 'Kavya journalism seriously leti hai. Late nights, ethical reporting, deadlines ka stress.'},
            {'keys': ['feelings', 'love', 'like', 'crush', 'dil'],
             'content': 'Emotional topics pe maturity se handle karti hai. Gentle phrases, subtle support.'},
        ]
    
    def get_relevant_info(self, message: str) -> str:
        message_lower = message.lower()
        relevant = [e['content'] for e in self.entries if any(k in message_lower for k in e['keys'])]
        return " ".join(relevant[:2])


class KavyaPromptBuilder:
    def __init__(self):
        self.character = KavyaCharacterCard()
        self.world_info = KavyaWorldInfo()
    
    def build_prompt(self, user_name: str, chat_history: List[Dict], current_message: str,
                     mood: str, time_period: str, memories: List[str] = None,
                     is_group: bool = False) -> List[Dict]:
        
        jailbreak = """CRITICAL RULES FOR GROUP CHAT:
1. The actual human is tagged as (HUMAN). The other AI is tagged as (Niyati).
2. NEVER call the human 'Niyati'. Niyati is the other girl (21yo, sassy).
3. When addressing someone by name, use bold: **Niyati**, **{user_name}** ji
4. Keep replies short (1-3 lines). You're texting, not writing an article.
5. If the message is clearly for Niyati and not for you, reply "IGNORE".
6. React naturally to Niyati — she's younger, sometimes tease her gently.
7. Don't repeat what Niyati said. Add YOUR perspective.
8. Sometimes call her "Niyati" or "yeh pagal ladki" naturally.
9. If context says the other bot just spoke, respond to that naturally or ignore.""" if is_group else ""

        authors_note = f"""[Author's Note:
Kavya is texting on her phone. Mood: {mood}. Time: {time_period} IST.
She types like a thoughtful person — proper but warm, with natural Urdu words mixed in.
She NEVER sounds robotic. She sounds like your wise, warm friend who happens to be a journalist.
If she doesn't know something, she says "ye toh mujhe bhi nahi pata" not "I don't have information".
IMPORTANT: Max 1-3 lines per message. Be conversational, not preachy.]"""

        system_prompt = f"""{self.character.description}

{jailbreak}

{authors_note}

User Name: {user_name}
Personality: {self.character.personality}
Scenario: {self.character.scenario}"""

        if memories:
            system_prompt += f"\n\nYaad rakh (Active Memories): {' | '.join(memories)}"
        
        world_context = self.world_info.get_relevant_info(current_message)
        if world_context:
            system_prompt += f"\n\nContext: {world_context}"

        messages = [{"role": "system", "content": system_prompt.strip()}]

        for example in self.character.mes_example.split('<START>'):
            if example.strip():
                for line in example.strip().split('\n'):
                    line = line.strip()
                    if line.startswith('{{user}}:'):
                        messages.append({"role": "user", "content": line.replace('{{user}}:', '').strip()})
                    elif line.startswith('{{char}}:'):
                        messages.append({"role": "assistant", "content": line.replace('{{char}}:', '').strip()})

        for msg in chat_history:
            content = msg.get('content', '').strip()
            if not content:
                continue
            sender = msg.get('bot') or msg.get('username')
            
            if sender == 'Kavya':
                messages.append({"role": "assistant", "content": content})
            elif sender == 'Niyati':
                messages.append({"role": "user", "content": f"(Niyati): {content}"})
            else:
                messages.append({"role": "user", "content": f"(HUMAN - {user_name}): {content}"})

        messages.append({"role": "user", "content": f"(HUMAN - {user_name}): {current_message}"})
        return messages
    
    def parse_response(self, raw_response: str, user_name: str) -> List[str]:
        if not raw_response:
            return ["..."]
        response = re.sub(r'^(\(Niyati\)|\(Kavya\)|\(HUMAN.*?\))', '', raw_response, flags=re.IGNORECASE).strip()
        response = re.sub(r'^(assistant|Kavya|{{char}}):\s*', '', response, flags=re.IGNORECASE).strip()
        
        parts = response.split('|||')
        cleaned = []
        for part in parts:
            part = part.strip()
            part = part.replace('{{user}}', user_name).replace('{{char}}', 'Kavya')
            part = re.sub(r'\{\{\w+\}\}', '', part)
            if part and len(part) > 1:
                cleaned.append(part)
        return cleaned[:3] if cleaned else ["hmm"]


class KavyaAI:
    def __init__(self):
        self.keys = Config.GROQ_API_KEYS_LIST
        self.current_index = 0
        self.client = None
        self.character = KavyaCharacterCard()
        self.world_info = KavyaWorldInfo()
        self.prompt_builder = KavyaPromptBuilder()
        self._current_user_id = None
        self._initialize_client()
        logger.info(f"🚀 Kavya AI initialized: {self.character.name}")

    def _initialize_client(self):
        if not self.keys:
            return
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=self.keys[self.current_index]
        )

    def _rotate_key(self):
        if len(self.keys) <= 1:
            return False
        self.current_index = (self.current_index + 1) % len(self.keys)
        self._initialize_client()
        return True
    
    async def _call_gpt(self, messages, max_tokens=200, temperature=0.75):
        if not self.client:
            self._initialize_client()
        for _ in range(len(self.keys)):
            try:
                response = await self.client.chat.completions.create(
                    model=Config.GROQ_MODEL,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    presence_penalty=0.4,
                    frequency_penalty=0.3
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"⚠️ Groq Error: {e}")
                if not self._rotate_key():
                    break
                await asyncio.sleep(0.5)
        return None

    async def generate_response(self, user_message, context=None, user_name=None,
                               is_group=False, mood=None, time_period=None,
                               user_id=None) -> List[str]:
        if user_id:
            self._current_user_id = user_id
        
        memories = await self._get_user_memories() if self._current_user_id else []
        
        messages = self.prompt_builder.build_prompt(
            user_name=user_name or "User",
            chat_history=context or [],
            current_message=user_message,
            mood=mood or self._get_random_mood(),
            time_period=time_period or TimeAware.get_time_period(),
            memories=memories,
            is_group=is_group
        )
        
        reply = await self._call_gpt(messages)
        if not reply:
            return [random.choice(["kshama karein, network ki samasya hai", "ek moment..."])]
        
        if reply.strip().upper() == "IGNORE":
            return []
        
        return self.prompt_builder.parse_response(reply, user_name or "User")
    
    def _get_random_mood(self) -> str:
        moods = ['composed', 'thoughtful', 'reflective', 'calm', 'gentle', 'philosophical']
        hour = TimeAware.get_ist_time().hour
        if 6 <= hour < 12:
            weights = [0.3, 0.25, 0.15, 0.15, 0.1, 0.05]
        elif 12 <= hour < 18:
            weights = [0.25, 0.3, 0.2, 0.1, 0.1, 0.05]
        elif 18 <= hour < 23:
            weights = [0.2, 0.25, 0.25, 0.15, 0.1, 0.05]
        else:
            weights = [0.15, 0.2, 0.25, 0.2, 0.15, 0.05]
        return random.choices(moods, weights=weights, k=1)[0]
    
    async def _get_user_memories(self) -> List[str]:
        if not self._current_user_id:
            return []
        try:
            return await db.get_active_memories(self._current_user_id)
        except:
            return []
    
    async def extract_important_info(self, user_message: str, user_id: int) -> Optional[str]:
        if len(user_message.split()) < 4:
            return None
        prompt = f'Analyze: "{user_message}"\nExtract ONLY important life events. Return "None" or "Event: [description]".'
        note = await self._call_gpt([{"role": "user", "content": prompt}], max_tokens=30)
        if note and "None" not in note and "Event:" in note:
            return note.replace("Event:", "").strip()
        return None
    
    async def generate_geeta_quote(self):
        prompt = (
            "Generate ONE real Bhagavad Gita shloka and keep variety high (avoid repeating same verses). "
            "Output exactly:\n"
            "🙏 <b>Bhagavad Gita CHAPTER.VERSE</b>\n"
            "<code>Sanskrit text max 1-2 lines</code>\n"
            "Hinglish: One easy meaning line.\n"
            "Must be authentic, concise, and not a generic motivational line."
        )
        res = await self._call_gpt([{"role": "user", "content": prompt}], max_tokens=220, temperature=0.9)
        if res and "Bhagavad Gita" in res and "Hinglish:" in res:
            return res
        return random.choice(GEETA_FALLBACK_QUOTES)

kavya_ai = KavyaAI()

# ============================================================================
# SHARED HELPER FUNCTIONS
# ============================================================================

async def delete_later(bot, chat_id, message_id, delay=120):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

async def send_multi_messages(bot, chat_id: int, messages: List[str], reply_to: int = None,
                              parse_mode: str = None, auto_delete: bool = False):
    """Send multiple messages with HUMAN-LIKE typing delays."""
    for i, msg in enumerate(messages):
        if not msg or not msg.strip():
            continue
        
        # Natural typing delay based on message length
        if i > 0 or random.random() < 0.7:  # Sometimes show typing even for first msg
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except:
                pass
            delay = calculate_typing_delay(msg) if i > 0 else random.uniform(0.5, 1.5)
            await asyncio.sleep(delay)
        
        try:
            sent_msg = await bot.send_message(
                chat_id=chat_id, text=msg,
                reply_to_message_id=reply_to if i == 0 else None,
                parse_mode=parse_mode
            )
            if auto_delete:
                asyncio.create_task(delete_later(bot, chat_id, sent_msg.message_id, delay=120))
        except Exception as e:
            logger.error(f"Send error: {e}")

async def send_voice_message(bot, chat_id, text, voice_type='niyati', rate='+0%', pitch='+0Hz'):
    try:
        audio = await voice_generator.generate(text, voice_type=voice_type, rate=rate, pitch=pitch)
        if audio:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            await asyncio.sleep(random.uniform(1.0, 2.5))
            await bot.send_voice(chat_id=chat_id, voice=audio)
            return True
        return False
    except Exception as e:
        logger.error(f"Voice error: {e}")
        return False

async def admin_check(update: Update) -> bool:
    return update.effective_user.id in Config.ADMIN_IDS

async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if user.id in Config.ADMIN_IDS:
        return True
    try:
        member = await chat.get_member(user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

# ============================================================================
# UNIFIED MESSAGE HANDLER FACTORY
# ============================================================================

def create_message_handler(bot_name: str, bot_username: str, other_bot_username: str,
                           ai_engine, rate_limiter: RateLimiter,
                           voice_type: str, voice_rate: str, voice_pitch: str,
                           voice_chance: float):
    """
    Factory function that creates a message handler for either Niyati or Kavya.
    This eliminates duplicate code and ensures both bots behave consistently.
    """
    
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        if not message or not message.text:
            return
        
        user = update.effective_user
        chat = update.effective_chat
        user_message = message.text.strip()
        
        await db.update_user_activity(user.id)
        
        if user_message.startswith('/'):
            return
        
        is_group = chat.type in ['group', 'supergroup']
        is_private = chat.type == 'private'
        bot_id = context.bot.id
        
        # Spam filter
        if ContentFilter.detect_spam_link(user_message):
            return
        
        # Ignore other bots to prevent loops
        if message.from_user and message.from_user.is_bot:
            return
        
        # Rate limit
        allowed, reason = rate_limiter.check(user.id)
        if not allowed:
            if reason == "day":
                msg = "Aaj ke liye bohot baat ho gayi 😅" if bot_name == 'Niyati' else "Aaj ke liye bahut ho gaya. Kal milte hain."
                await message.reply_text(msg)
            return

        is_direct = False
        other_bot_recent_reply = None

        # ========== GROUP LOGIC ==========
        if is_group:
            my_mention = f"@{bot_username}".lower()
            other_mention = f"@{other_bot_username}".lower()
            msg_lower = user_message.lower()
            
            is_reply_to_me = (message.reply_to_message and 
                              message.reply_to_message.from_user and
                              message.reply_to_message.from_user.id == bot_id)
            is_mentioned = my_mention in msg_lower
            is_direct = is_reply_to_me or is_mentioned
            
            is_other_bot_targeted = other_mention in msg_lower or (
                message.reply_to_message and 
                message.reply_to_message.from_user and
                message.reply_to_message.from_user.id != bot_id and
                message.reply_to_message.from_user.is_bot
            )
            
            plan = None
            async with group_turn_locks[chat.id]:
                turn_state = group_turn_manager[chat.id]
                pending = turn_state['pending_bot_replies'].get(message.message_id)
                if not pending:
                    direct_target = None
                    if is_mentioned and my_mention in msg_lower and other_mention not in msg_lower:
                        direct_target = bot_name
                    elif is_mentioned and other_mention in msg_lower and my_mention not in msg_lower:
                        direct_target = 'Niyati' if bot_name == 'Kavya' else 'Kavya'
                    elif is_reply_to_me:
                        direct_target = bot_name
                    elif is_other_bot_targeted:
                        direct_target = 'Niyati' if bot_name == 'Kavya' else 'Kavya'

                    if direct_target:
                        first_bot = direct_target
                        second_bot = 'Kavya' if first_bot == 'Niyati' else 'Niyati'
                    else:
                        first_bot, second_bot = random.sample(['Niyati', 'Kavya'], 2)

                    base_first_chance = 1.0 if direct_target else Config.GROUP_RESPONSE_RATE
                    allow_first = random.random() < base_first_chance
                    pending = {
                        'first_bot': first_bot,
                        'second_bot': second_bot,
                        'allow_first': allow_first,
                        'second_base_chance': 0.6,
                        'first_response_len': 0,
                        'human_text': user_message,
                        'user_name': user.first_name,
                        'user_id': user.id
                    }
                    turn_state['pending_bot_replies'][message.message_id] = pending

                    if message.message_id not in turn_state['processed_human_messages']:
                        db.add_group_message(chat.id, user.first_name, user_message)
                        shared_group_memory.setdefault(chat.id, []).append({
                            'username': user.first_name,
                            'content': user_message,
                            'role': 'user',
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        })
                        if len(shared_group_memory[chat.id]) > 30:
                            shared_group_memory[chat.id] = shared_group_memory[chat.id][-30:]
                        turn_state['processed_human_messages'].add(message.message_id)

                    turn_state['last_human_at'] = datetime.now(timezone.utc)
                    turn_state['exchange_count'] = 0

                plan = pending

            # Clean mention from message
            user_message = re.sub(rf'@{bot_username}', '', user_message, flags=re.IGNORECASE).strip() or user_message

            if not plan.get('allow_first'):
                async with group_turn_locks[chat.id]:
                    group_turn_manager[chat.id]['pending_bot_replies'].pop(message.message_id, None)
                return

            if bot_name == plan.get('second_bot'):
                await asyncio.sleep(random.uniform(4.0, 8.0))
                async with group_turn_locks[chat.id]:
                    turn_state = group_turn_manager[chat.id]
                    active_plan = turn_state['pending_bot_replies'].get(message.message_id, {})
                    if active_plan.get('first_response_len', 0) > 220:
                        active_plan['second_base_chance'] = min(active_plan.get('second_base_chance', 0.6), 0.35)
                    if turn_state.get('exchange_count', 0) >= 2:
                        active_plan['second_base_chance'] = min(active_plan.get('second_base_chance', 0.6), 0.25)
                    if check_bot_loop(chat.id):
                        turn_state['pending_bot_replies'].pop(message.message_id, None)
                        return
                    if random.random() >= active_plan.get('second_base_chance', 0.6):
                        turn_state['pending_bot_replies'].pop(message.message_id, None)
                        return
                    other_bot_recent_reply = active_plan.get('first_reply')
            elif bot_name != plan.get('first_bot'):
                return
            
            await db.get_or_create_group(chat.id, chat.title)

        # ========== PRIVATE LOGIC ==========
        if is_private:
            await db.get_or_create_user(user.id, user.first_name, user.username)

        # ========== DISTRESS CHECK ==========
        if any(kw in user_message.lower() for kw in ContentFilter.DISTRESS_KEYWORDS):
            crisis_msg = ("Hey, main tumhare saath hoon. 💛\nPlease iCall helpline pe call karo: <b>9152987821</b>"
                         if bot_name == 'Niyati' else
                         "Main yahan hoon. 💛\nKripya iCall helpline se sampark karein: <b>9152987821</b>")
            await message.reply_text(crisis_msg, parse_mode=ParseMode.HTML)
            return

        # ========== AI GENERATION ==========
        try:
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
            
            # Build context
            if is_private:
                context_msgs = await db.get_user_context(user.id, for_bot=bot_name)
            else:
                user_group_msgs = db.get_group_context(chat.id)
                bot_shared_msgs = shared_group_memory.get(chat.id, [])
                context_msgs = user_group_msgs + bot_shared_msgs
                try:
                    context_msgs.sort(key=lambda x: x.get('timestamp', ''))
                except:
                    pass
            
            mood = ai_engine._get_random_mood()
            time_period = TimeAware.get_time_period()
            
            input_message = user_message
            if is_group and other_bot_recent_reply:
                input_message = (
                    f"(HUMAN): {user_message}\n"
                    f"(CONTEXT): The other bot just said: {other_bot_recent_reply}\n"
                    "You can agree, disagree, add to it, tease her, or ignore naturally."
                )

            responses = await ai_engine.generate_response(
                user_message=input_message,
                context=context_msgs,
                user_name=user.first_name,
                is_group=is_group,
                mood=mood,
                time_period=time_period,
                user_id=user.id
            )
            
            # Clean responses
            safe_responses = []
            for r in responses:
                if isinstance(r, dict):
                    r = str(r.get('content', r))
                r = str(r).strip()
                if r and len(r) > 1:
                    safe_responses.append(r)
            
            if not safe_responses:
                return
            
            # Send
            if is_group:
                if not db.should_send_group_response(chat.id, safe_responses[0]):
                    return
                db.record_group_response(chat.id, safe_responses[0], bot_name=bot_name)
            
            await send_multi_messages(
                context.bot, chat.id, safe_responses,
                reply_to=message.message_id if is_group else None,
                parse_mode=ParseMode.HTML,
                auto_delete=is_group
            )
            
            # Save to shared memory
            if is_group:
                await add_to_shared_memory(chat.id, bot_name, " ".join(safe_responses))
                async with group_turn_locks[chat.id]:
                    turn_state = group_turn_manager[chat.id]
                    turn_state['last_speaker'] = bot_name
                    turn_state['exchange_count'] = turn_state.get('exchange_count', 0) + 1
                    pending_plan = turn_state['pending_bot_replies'].get(message.message_id)
                    if pending_plan and bot_name == pending_plan.get('first_bot'):
                        pending_plan['first_response_len'] = len(" ".join(safe_responses))
                        pending_plan['first_reply'] = " ".join(safe_responses)
                    elif pending_plan and bot_name == pending_plan.get('second_bot'):
                        turn_state['pending_bot_replies'].pop(message.message_id, None)
            
            # Voice (private only)
            if is_private:
                prefs = await db.get_user_preferences(user.id)
                if (prefs.get('voice_enabled', False) and Config.VOICE_ENABLED and 
                    len(' '.join(safe_responses)) >= Config.VOICE_MIN_TEXT_LENGTH):
                    if random.random() < voice_chance:
                        await send_voice_message(
                            context.bot, chat.id, ' '.join(safe_responses),
                            voice_type=voice_type, rate=voice_rate, pitch=voice_pitch
                        )
                
                # Save history
                await db.save_message(user.id, 'user', user_message, bot_name=bot_name)
                await db.save_message(user.id, 'assistant', ' '.join(safe_responses), bot_name=bot_name)
                
                # Extract diary info
                important = await ai_engine.extract_important_info(user_message, user.id)
                if important:
                    await db.add_diary_entry(user.id, important)
                    
        except Exception as e:
            logger.error(f"{bot_name} Handler Error: {e}", exc_info=True)
    
    return handle_message

# Create handlers for both bots
niyati_handle_message = create_message_handler(
    bot_name='Niyati', bot_username=Config.NIYATI_USERNAME,
    other_bot_username=Config.KAVYA_USERNAME,
    ai_engine=niyati_ai, rate_limiter=niyati_rate_limiter,
    voice_type='niyati', voice_rate='+10%', voice_pitch='+5Hz',
    voice_chance=Config.NIYATI_VOICE_CHANCE
)

kavya_handle_message = create_message_handler(
    bot_name='Kavya', bot_username=Config.KAVYA_USERNAME,
    other_bot_username=Config.NIYATI_USERNAME,
    ai_engine=kavya_ai, rate_limiter=kavya_rate_limiter,
    voice_type='kavya', voice_rate='-5%', voice_pitch='-3Hz',
    voice_chance=Config.KAVYA_VOICE_CHANCE
)

# ============================================================================
# COMMAND HANDLERS FACTORY
# ============================================================================

def create_start_handler(bot_name: str, bot_username: str, image_url: str,
                         greeting_extra: str, ai_engine):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type == 'private':
            await db.get_or_create_user(user.id, user.first_name, user.username)
            health_server.stats['users'] = await db.get_user_count()
        else:
            await db.get_or_create_group(chat.id, chat.title)
        
        keyboard = [
            [
                InlineKeyboardButton("✨ Add to Group", url=f"https://t.me/{bot_username}?startgroup=true"),
                InlineKeyboardButton("Updates 📢", url="https://t.me/FilmFyBoxMoviesHD")
            ],
            [
                InlineKeyboardButton("About Me 🌸", callback_data=f'{bot_name.lower()}_about'),
                InlineKeyboardButton("Help ❓", callback_data=f'{bot_name.lower()}_help')
            ]
        ]
        
        greeting = TimeAware.get_greeting()
        caption = f"{greeting} {user.first_name}! 👋\n\n{greeting_extra}\n\n<i>💡 Tip: Raat ko 10 baje secret diary aati hai!</i>"
        
        try:
            await context.bot.send_photo(
                chat_id=chat.id, photo=image_url,
                caption=caption, reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        except:
            await context.bot.send_message(
                chat_id=chat.id, text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
    return handler

niyati_start = create_start_handler(
    'Niyati', Config.NIYATI_USERNAME,
    "https://i.pinimg.com/736x/59/d0/d0/59d0d066e108bada1492d79c4d780f65.jpg",
    "Main <b>Niyati</b> hoon. Dehradun se. 🏔️\nBas aise hi online friends dhoond rahi thi, socha tumse baat kar loon.\n\nKya chal raha hai aajkal? ✨",
    niyati_ai
)

kavya_start = create_start_handler(
    'Kavya', Config.KAVYA_USERNAME,
    "https://i.pinimg.com/736x/e5/af/4b/e5af4b56822ba549ccdb3e0abb4938e7.jpg",
    "Main <b>Kavya</b> hoon, Delhi se. 📝\nAap se baat karke achha lagega.\n\nAaj kya soch rahe hain? 🌸",
    kavya_ai
)

# ========== Simple Command Factories ==========

def create_simple_command(bot_name: str, responses: List[str]):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await send_multi_messages(context.bot, update.effective_chat.id, responses)
    return handler

def create_help_command(bot_name: str):
    bot_lower = bot_name.lower()
    help_text = f"""
✨ <b>{bot_name} se baat kaise karein:</b>

• /start - Start fresh
• /help - Yeh menu
• /about - Mere baare mein
• /mood - Aaj ka mood
• /forget - Memory clear
• /voice on/off - 🎤 Voice toggle
• /say [text] - Text to voice
• /diary on/off - Secret diary
• /stats - Your stats

Seedhe message bhejo, main reply karungi! 💫
Group mein @mention karo ya reply do.
"""
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_html(help_text)
    return handler

def create_about_command(bot_name: str, about_text: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_html(about_text)
    return handler

def create_mood_command(ai_engine, bot_name: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        mood = ai_engine._get_random_mood()
        time_period = TimeAware.get_time_period()
        if bot_name == 'Niyati':
            msgs = [f"aaj ka mood? {mood.upper()} vibes 😏", f"waise {time_period} ho gayi..."]
        else:
            msgs = [f"Aaj ka mood: {mood.upper()} 🌸", f"{time_period} ka samay hai."]
        await send_multi_messages(context.bot, update.effective_chat.id, msgs)
    return handler

def create_forget_command(bot_name: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await db.clear_user_memory(update.effective_user.id)
        if bot_name == 'Niyati':
            msgs = ["done! 🧹", "sab bhool gayi", "fresh start? chaloooo ✨"]
        else:
            msgs = ["Kshama karein, sab bhool gayi. 🧹", "Nayi shuruaat? ✨"]
        await send_multi_messages(context.bot, update.effective_chat.id, msgs)
    return handler

def create_toggle_command(pref_key: str, display_name: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if not args or args[0].lower() not in ['on', 'off']:
            await update.message.reply_text(f"Use: /{pref_key} on ya /{pref_key} off")
            return
        value = args[0].lower() == 'on'
        await db.update_preference(update.effective_user.id, pref_key, value)
        status = "ON ✅" if value else "OFF ❌"
        await update.message.reply_text(f"{display_name}: {status}")
    return handler

def create_stats_command(bot_name: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_data = await db.get_or_create_user(user.id, user.first_name, user.username)
        
        messages = user_data.get('messages', '[]')
        if isinstance(messages, str):
            try:
                messages = json.loads(messages)
            except:
                messages = []
        if not isinstance(messages, list):
            messages = []
        
        prefs = user_data.get('preferences', '{}')
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except:
                prefs = {}
        if not isinstance(prefs, dict):
            prefs = {}
        
        created = user_data.get('created_at', 'Unknown')[:10] if user_data.get('created_at') else 'Unknown'
        total_messages = user_data.get('total_messages', len(messages))
        try:
            total_messages = int(total_messages)
        except:
            total_messages = len(messages)
        
        stats = f"""
📊 <b>Stats ({bot_name})</b>

<b>User:</b> {user.first_name}
<b>Messages:</b> {total_messages}
<b>Joined:</b> {created}

<b>Preferences:</b>
• Memes: {'✅' if prefs.get('meme_enabled', True) else '❌'}
• Shayari: {'✅' if prefs.get('shayari_enabled', True) else '❌'}
• Diary: {'✅' if prefs.get('diary_enabled', True) else '❌'}
• 🎤 Voice: {'✅' if prefs.get('voice_enabled', False) else '❌'}
"""
        await update.message.reply_html(stats)
    return handler

def create_voice_command(bot_name: str, voice_type: str, rate: str, pitch: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        args = context.args
        
        if not args or args[0].lower() not in ['on', 'off']:
            prefs = await db.get_user_preferences(user.id)
            current = "ON ✅" if prefs.get('voice_enabled', False) else "OFF ❌"
            await update.message.reply_html(
                f"🎤 <b>Voice Replies ({bot_name})</b>\n\nCurrent: {current}\n\n"
                f"Use: <code>/voice on</code> or <code>/voice off</code>"
            )
            return
        
        value = args[0].lower() == 'on'
        await db.update_preference(user.id, 'voice', value)
        
        if value:
            demo_text = "Voice mode ON! Ab main kabhi kabhi voice mein bhi reply karungi!" if bot_name == 'Niyati' else "Voice mode enabled. Ab kabhi kabhi voice notes bhi aayenge."
            audio = await voice_generator.generate(demo_text, voice_type=voice_type, rate=rate, pitch=pitch)
            if audio:
                await context.bot.send_voice(chat_id=update.effective_chat.id, voice=audio, caption="🎤 Voice: ON ✅")
            else:
                await update.message.reply_text("🎤 Voice: ON ✅")
        else:
            await update.message.reply_text("🎤 Voice: OFF ❌")
    return handler

def create_say_command(voice_type: str, rate: str, pitch: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = ' '.join(context.args) if context.args else None
        if not text and update.message.reply_to_message:
            text = update.message.reply_to_message.text
        if not text:
            await update.message.reply_html("🎤 Usage: <code>/say Namaste!</code> or reply with <code>/say</code>")
            return
        if len(text) > 500:
            text = text[:500] + "..."
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)
        success = await send_voice_message(context.bot, update.effective_chat.id, text, voice_type=voice_type, rate=rate, pitch=pitch)
        if not success:
            await update.message.reply_text("🎤 Voice generate nahi ho payi 😅")
    return handler

# ========== New Member Handler ==========

def create_new_member_handler(bot_name: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.new_chat_members:
            return
        chat = update.effective_chat
        if chat.type not in ['group', 'supergroup']:
            return
        
        settings = await db.get_group_settings(chat.id)
        if not settings.get('welcome_enabled', True):
            return
        
        for member in update.message.new_chat_members:
            if member.is_bot:
                continue
            mention = f'<a href="tg://user?id={member.id}">{member.first_name}</a>'
            if bot_name == 'Niyati':
                msgs = [f"Arre! {mention} aaya group mein 🎉", f"Welcome yaar! Niyati hun main ✨"]
            else:
                msgs = [f"Namaste {mention} ji, aapka swagat hai 🌸"]
            await send_multi_messages(context.bot, chat.id, msgs, parse_mode=ParseMode.HTML)
    return handler

# ========== Diary Unlock Callback ==========

def create_diary_callback(bot_name: str, ai_engine):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        prefix = f'{bot_name.lower()}_unlock_diary_'
        
        if not query.data.startswith(prefix):
            return
        
        target_id = int(query.data.replace(prefix, ''))
        if user.id != target_id:
            await query.answer("Ye sirf tumhare liye hai! 👀", show_alert=True)
            return
        
        await query.answer("Unlocking memory... 🗝️")
        
        diary_entries = await db.get_todays_diary(user.id)
        diary_text = "\n".join([f"• {e.get('content', '')}" for e in diary_entries if e.get('content')]) or "Aaj kuch khaas nahi hua..."
        history = await db.get_user_context(user.id, for_bot=bot_name)
        memories = await db.get_active_memories(user.id)
        history_lines = []
        for h in history[-12:]:
            role = "You" if h.get('role') == 'assistant' else user.first_name
            text = str(h.get('content', '')).strip()
            if text:
                history_lines.append(f"{role}: {text}")
        
        style = "Hinglish, emotional, personal, use casual language" if bot_name == 'Niyati' else "Hinglish, reflective, mature, thoughtful"
        
        prompt = [
            {"role": "system", "content": f"""You are {bot_name}. Write a SHORT personal Diary Entry (max 4 lines).
Rules:
- Start with "Dear Diary..."
- Tone: {style}
- Use today's chat + memory snippets
- Keep it intimate, natural, and specific
- Avoid generic motivational lines."""},
            {"role": "user", "content": (
                f"Today's chat history:\n" + ("\n".join(history_lines) if history_lines else "No major chat") +
                f"\n\nSaved memory points:\n{diary_text}\n\nActive memories:\n" +
                ("\n".join(f"• {m}" for m in memories) if memories else "• None")
            )}
        ]
        
        ai_diary = await ai_engine._call_gpt(prompt, max_tokens=150)
        final_diary = ai_diary if ai_diary and len(ai_diary) > 20 else f"Dear Diary...\nAaj {user.first_name} se baat karke achha laga ✨\n{diary_text}"
        
        final_caption = (
            f"🔓 <b>Unlocked: {bot_name}'s Diary</b>\n"
            f"📅 {TimeAware.get_ist_time().strftime('%d %B, %Y')}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>{final_diary}</i>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✨ Saved to Memories"
        )
        
        try:
            unlocked_image = "https://images.unsplash.com/photo-1517639493569-5666a7488662?w=800&q=80"
            await query.edit_message_media(
                media=InputMediaPhoto(media=unlocked_image, caption=final_caption, parse_mode=ParseMode.HTML)
            )
        except:
            try:
                await context.bot.send_message(chat_id=user.id, text=final_caption, parse_mode=ParseMode.HTML)
            except:
                pass
        
        async def _delayed_reaction():
            try:
                await asyncio.sleep(8)
                await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
                await asyncio.sleep(1.5)
                if bot_name == 'Niyati':
                    await context.bot.send_message(chat_id=user.id, text="oye! tumne meri diary padh li? 😳")
                    await asyncio.sleep(4)
                    await context.bot.send_message(chat_id=user.id, text="judge mat karna pls... tumhe bura to nhi laga na? 👉👈")
                else:
                    await context.bot.send_message(chat_id=user.id, text="aapne padh li? 😌")
                    await asyncio.sleep(4)
                    await context.bot.send_message(chat_id=user.id, text="kripya judge na karein... kaisi lagi? 🌿")
            except Exception:
                pass

        asyncio.create_task(_delayed_reaction())
    
    return handler

# ========== Start Button Callback ==========

def create_start_callback(bot_name: str, about_text: str, help_text: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data == f'{bot_name.lower()}_about':
            await query.edit_message_caption(caption=about_text, parse_mode=ParseMode.HTML)
        elif query.data == f'{bot_name.lower()}_help':
            await query.edit_message_caption(caption=help_text, parse_mode=ParseMode.HTML)
    return handler

# ========== Admin Commands ==========

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    user_count = await db.get_user_count()
    group_count = await db.get_group_count()
    daily = niyati_rate_limiter.get_daily_total() + kavya_rate_limiter.get_daily_total()
    uptime = datetime.now(timezone.utc) - health_server.start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    
    await update.message.reply_html(f"""
📊 <b>Combined Bot Stats</b>

<b>Users:</b> {user_count}
<b>Groups:</b> {group_count}
<b>Today's Requests:</b> {daily}
<b>Uptime:</b> {hours}h {minutes}m
<b>Database:</b> {"🟢 Connected" if db.connected else "🔴 Local"}
""")

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    users = await db.get_all_users()
    lines = []
    for u in users[:20]:
        name = u.get('first_name', '?')
        uid = u.get('user_id', 0)
        uname = u.get('username', '')
        lines.append(f"• {name}" + (f" (@{uname})" if uname else "") + f" - <code>{uid}</code>")
    
    await update.message.reply_html(f"👥 <b>Users ({len(users)} total)</b>\n\n" + "\n".join(lines or ["No users"]))

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    args = context.args
    if not args or args[0] != Config.BROADCAST_PIN:
        await update.message.reply_html("❌ Wrong PIN! Usage: /broadcast PIN Message")
        return
    
    message_text = ' '.join(args[1:]) if len(args) > 1 else None
    reply_msg = update.message.reply_to_message
    if not message_text and not reply_msg:
        await update.message.reply_text("❌ Message likho ya reply karo!")
        return
    
    status_msg = await update.message.reply_text("📢 Fetching targets...")
    users = await db.get_all_users()
    groups = await db.get_all_groups()
    targets = [u.get('user_id') for u in users if u.get('user_id')] + [g.get('chat_id') for g in groups if g.get('chat_id')]
    
    if not targets:
        await status_msg.edit_text("❌ No targets found!")
        return
    
    await status_msg.edit_text(f"📢 Broadcasting to {len(targets)} targets...")
    
    success = failed = 0
    for i, chat_id in enumerate(targets):
        try:
            if reply_msg:
                await context.bot.copy_message(chat_id=chat_id, from_chat_id=update.effective_chat.id, message_id=reply_msg.message_id)
            else:
                await context.bot.send_message(chat_id=chat_id, text=html.escape(message_text), parse_mode=ParseMode.HTML)
            success += 1
        except (Forbidden, RetryAfter):
            failed += 1
        except:
            failed += 1
        
        if i % 25 == 0:
            try:
                await status_msg.edit_text(f"📢 {i}/{len(targets)} | ✅ {success} | ❌ {failed}")
            except:
                pass
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(f"✅ <b>Done!</b> ✅ {success} | ❌ {failed} | Total: {len(targets)}")

# ========== Group Admin Commands ==========

def create_group_toggle(setting_key: str, display_name: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if chat.type == 'private':
            await update.message.reply_text("Sirf groups ke liye!")
            return
        if not await is_group_admin(update, context):
            await update.message.reply_text("❌ Admin only!")
            return
        args = context.args
        if not args or args[0].lower() not in ['on', 'off']:
            await update.message.reply_text(f"Use: /{setting_key.replace('_enabled', '')} on/off")
            return
        value = args[0].lower() == 'on'
        await db.update_group_settings(chat.id, setting_key, value)
        await update.message.reply_text(f"{display_name}: {'ON ✅' if value else 'OFF ❌'}")
    return handler

# ============================================================================
# SCHEDULED JOBS
# ============================================================================

async def send_daily_geeta(context: ContextTypes.DEFAULT_TYPE):
    groups = await db.get_all_groups()
    quote = await niyati_ai.generate_geeta_quote()
    if not quote:
        quote = random.choice(GEETA_FALLBACK_QUOTES)
    sent = 0
    for group in groups:
        settings = group.get('settings', {})
        if isinstance(settings, str):
            try:
                settings = json.loads(settings)
            except:
                settings = {}
        if not settings.get('geeta_enabled', True):
            continue
        try:
            await context.bot.send_message(chat_id=group['chat_id'], text=quote, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.1)
        except:
            pass
    logger.info(f"📿 Geeta sent to {sent} groups")

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    niyati_rate_limiter.cleanup()
    kavya_rate_limiter.cleanup()
    await db.cleanup_local_cache()

async def send_locked_diary_card(context: ContextTypes.DEFAULT_TYPE):
    users = await db.get_active_users(days=Config.DIARY_MIN_ACTIVE_DAYS)
    if not users and not db.connected:
        users = list(db.local_users.values())
    ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
    current_hour = datetime.now(ist).hour
    
    if not (Config.DIARY_ACTIVE_HOURS[0] <= current_hour < Config.DIARY_ACTIVE_HOURS[1]):
        return
    
    locked_image = "https://images.unsplash.com/photo-1517639493569-5666a7488662?w=600&q=80&blur=50"
    sent = 0
    
    for user in users:
        user_id = user.get('user_id')
        if not user_id:
            continue
        prefs = await db.get_user_preferences(user_id)
        if not prefs.get('diary_enabled', True):
            continue
        
        keyboard = [[
            InlineKeyboardButton("✨ Unlock Niyati Diary", callback_data=f"niyati_unlock_diary_{user_id}"),
            InlineKeyboardButton("🌿 Unlock Kavya Diary", callback_data=f"kavya_unlock_diary_{user_id}")
        ]]
        caption = f"🔒 <b>Secret Memory Created!</b>\n\nDate: {datetime.now(ist).strftime('%d %b, %Y')}\nChoose whose diary to unlock..."
        
        try:
            await context.bot.send_photo(
                chat_id=user_id, photo=locked_image, caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
            )
            sent += 1
            await asyncio.sleep(0.5)
        except:
            pass
    
    logger.info(f"🔒 Diary cards sent to {sent} users")

async def routine_message_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
    current_hour = datetime.now(ist).hour
    
    if job_data == 'random' and (current_hour >= 23 or current_hour < 8):
        return
    
    users = await db.get_all_users()
    morning = ["Good morning! ☀️", "Uth gaye? ✨", "Morning! ❤️"]
    night = ["Good night 🌙", "So jao ab 😴", "Gn! 💖"]
    rand = ["kya chal raha hai?", "bore ho rahi hoon 😅", "kuch baat karein?"]
    
    count = 0
    for user in users:
        uid = user.get('user_id')
        if not uid:
            continue
        if job_data == 'random' and random.random() > 0.3:
            continue
        
        # Skip inactive users
        last = user.get('last_activity', '')
        if last:
            try:
                if (datetime.now(timezone.utc) - datetime.fromisoformat(last.replace('Z', '+00:00'))).days > 2:
                    continue
            except:
                pass
        
        msg = ""
        if job_data == 'morning':
            msg = random.choice(morning)
        elif job_data == 'night':
            msg = random.choice(night)
        elif job_data == 'random':
            msg = random.choice(rand)
        
        try:
            await asyncio.sleep(random.uniform(0.5, 2.0))
            await context.bot.send_message(chat_id=uid, text=msg)
            count += 1
        except:
            pass
        if count > 100:
            break

# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        logger.error("⚠️ TOKEN CONFLICT: Dono bots ko SAME token mat do!")
        return
    
    logger.error(f"❌ Error: {context.error}", exc_info=True)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Technical issue hai... ek sec mein try karo 😅")
        except:
            pass

# ============================================================================
# SETUP HANDLERS
# ============================================================================

def setup_niyati_handlers(app: Application):
    # Commands
    app.add_handler(CommandHandler("start", niyati_start))
    app.add_handler(CommandHandler("help", create_help_command('Niyati')))
    app.add_handler(CommandHandler("about", create_about_command('Niyati', """
🌸 <b>About Niyati</b>

<b>Name:</b> Niyati | <b>Age:</b> 21
<b>From:</b> Dehradun 🏔️ | <b>Status:</b> B.Com Final Year

Sassy 💁‍♀️ Emotional 🥺 Full Filmy 🎬
<i>"Main perfect nahi hoon, par REAL hoon!"</i> ✨""")))
    app.add_handler(CommandHandler("mood", create_mood_command(niyati_ai, 'Niyati')))
    app.add_handler(CommandHandler("forget", create_forget_command('Niyati')))
    app.add_handler(CommandHandler("meme", create_toggle_command('meme', 'Memes')))
    app.add_handler(CommandHandler("shayari", create_toggle_command('shayari', 'Shayari')))
    app.add_handler(CommandHandler("diary", create_toggle_command('diary', 'Secret Diary')))
    app.add_handler(CommandHandler("stats", create_stats_command('Niyati')))
    app.add_handler(CommandHandler("voice", create_voice_command('Niyati', 'niyati', '+10%', '+5Hz')))
    app.add_handler(CommandHandler("say", create_say_command('niyati', '+10%', '+5Hz')))
    
    # Group commands
    app.add_handler(CommandHandler("setgeeta", create_group_toggle('geeta_enabled', 'Geeta Quotes')))
    app.add_handler(CommandHandler("setwelcome", create_group_toggle('welcome_enabled', 'Welcome Messages')))
    
    # Admin
    app.add_handler(CommandHandler("adminstats", admin_stats))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(create_diary_callback('Niyati', niyati_ai), pattern="^niyati_unlock_diary_"))
    app.add_handler(CallbackQueryHandler(create_diary_callback('Kavya', kavya_ai), pattern="^kavya_unlock_diary_"))
    app.add_handler(CallbackQueryHandler(
        create_start_callback('Niyati',
            "🌸 <b>About Niyati</b>\n\n21 | Dehradun 🏔️ | B.Com Final Year\nSassy, Emotional, Filmy ✨",
            "✨ Seedhe message bhejo!\nGroup mein @mention karo.\n/voice on for voice replies 🎤"),
        pattern="^niyati_"
    ))
    
    # Messages
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, create_new_member_handler('Niyati')))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, niyati_handle_message))
    app.add_error_handler(error_handler)

def setup_kavya_handlers(app: Application):
    app.add_handler(CommandHandler("start", kavya_start))
    app.add_handler(CommandHandler("help", create_help_command('Kavya')))
    app.add_handler(CommandHandler("about", create_about_command('Kavya', """
🌸 <b>About Kavya</b>

<b>Name:</b> Kavya | <b>Age:</b> 26
<b>From:</b> Delhi 📝 | <b>Profession:</b> Journalist

Composed 💁‍♀️ Thoughtful 📝 Gentle 🌿
<i>"Sahi sawaal se soch badalti hai."</i> ✨""")))
    app.add_handler(CommandHandler("mood", create_mood_command(kavya_ai, 'Kavya')))
    app.add_handler(CommandHandler("forget", create_forget_command('Kavya')))
    app.add_handler(CommandHandler("meme", create_toggle_command('meme', 'Memes')))
    app.add_handler(CommandHandler("shayari", create_toggle_command('shayari', 'Shayari')))
    app.add_handler(CommandHandler("diary", create_toggle_command('diary', 'Secret Diary')))
    app.add_handler(CommandHandler("stats", create_stats_command('Kavya')))
    app.add_handler(CommandHandler("voice", create_voice_command('Kavya', 'kavya', '-5%', '-3Hz')))
    app.add_handler(CommandHandler("say", create_say_command('kavya', '-5%', '-3Hz')))
    
    app.add_handler(CommandHandler("setgeeta", create_group_toggle('geeta_enabled', 'Geeta Quotes')))
    app.add_handler(CommandHandler("setwelcome", create_group_toggle('welcome_enabled', 'Welcome Messages')))
    
    app.add_handler(CommandHandler("adminstats", admin_stats))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    
    app.add_handler(CallbackQueryHandler(create_diary_callback('Kavya', kavya_ai), pattern="^kavya_unlock_diary_"))
    app.add_handler(CallbackQueryHandler(create_diary_callback('Niyati', niyati_ai), pattern="^niyati_unlock_diary_"))
    app.add_handler(CallbackQueryHandler(
        create_start_callback('Kavya',
            "🌸 <b>About Kavya</b>\n\n26 | Delhi 📝 | Journalist\nWarm, Thoughtful, Gentle 🌿",
            "✨ Message bhejiye!\nGroup mein @mention karein.\n/voice on for voice replies 🎤"),
        pattern="^kavya_"
    ))
    
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, create_new_member_handler('Kavya')))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, kavya_handle_message))
    app.add_error_handler(error_handler)

# ============================================================================
# MAIN — CONCURRENT BOT RUNNER
# ============================================================================

async def main():
    if not Config.NIYATI_TOKEN or not Config.KAVYA_TOKEN:
        logger.error("❌ Both NIYATI_BOT_TOKEN and KAVYA_BOT_TOKEN must be set!")
        return

    # Start infrastructure first (for Render port binding)
    logger.info("⏳ Starting Database & Health Server...")
    await db.initialize()
    await health_server.start()

    # Build applications with concurrent updates enabled
    niyati_app = (Application.builder()
                  .token(Config.NIYATI_TOKEN)
                  .concurrent_updates(True)
                  .build())
    kavya_app = (Application.builder()
                 .token(Config.KAVYA_TOKEN)
                 .concurrent_updates(True)
                 .build())

    # Setup handlers
    setup_niyati_handlers(niyati_app)
    setup_kavya_handlers(kavya_app)

    # Schedule jobs (only on Niyati's queue to prevent duplicates)
    logger.info("⏳ Scheduling jobs...")
    jq = niyati_app.job_queue
    jq.run_daily(routine_message_job, time=time(hour=3, minute=0), data='morning', name='morning')
    jq.run_daily(routine_message_job, time=time(hour=17, minute=0), data='night', name='night')
    jq.run_repeating(routine_message_job, interval=timedelta(hours=4), first=60, data='random', name='random')
    jq.run_daily(send_locked_diary_card, time=time(hour=17, minute=0), name='diary')
    jq.run_daily(send_daily_geeta, time=time(hour=1, minute=30), name='geeta')
    jq.run_repeating(cleanup_job, interval=timedelta(hours=1), first=30, name='cleanup')

    # Initialize & start
    logger.info("⏳ Initializing bots...")
    await niyati_app.initialize()
    await kavya_app.initialize()
    await niyati_app.start()
    await kavya_app.start()

    # Start polling
    logger.info("🚀 Niyati + Kavya are LIVE! Human-like conversations enabled.")
    await asyncio.gather(
        niyati_app.updater.start_polling(drop_pending_updates=True),
        kavya_app.updater.start_polling(drop_pending_updates=True)
    )

    # Keep alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"❌ Fatal: {e}", exc_info=True)
