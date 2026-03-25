"""
╔════════════════════════════════════════════════════════════════════════════╗
║                    NIYATI BOT v4.0 - SILLYTAVERN EDITION                   ║
║             🌸 Emotional AI with Character Cards & Lorebooks 🌸            ║
╚════════════════════════════════════════════════════════════════════════════╝
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
    Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, InputMediaPhoto, Message
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatAction, ChatMemberStatus
from telegram.error import BadRequest, Forbidden, RetryAfter

from openai import AsyncOpenAI


# Global Locks and Memory
group_speaker_lock = {} # Format: {chat_id: {message_id: "bot_name"}}
shared_group_memory = defaultdict(list)
memory_lock = asyncio.Lock()

async def add_to_shared_memory(chat_id: int, bot_name: str, message: str):
    """Saves a bot's reply so the other bot can read it as context."""
    async with memory_lock:
        shared_group_memory[chat_id].append({
            "role": "user",  # Treat the other bot as a user for the LLM
            "content": f"[{bot_name} says]: {message}"
        })
        # Keep only the last 10 shared messages to save tokens
        shared_group_memory[chat_id] = shared_group_memory[chat_id][-10:]

# ============================================================================
# SILLYTAVERN CHARACTER CARD SYSTEM
# ============================================================================

class CharacterCard:
    """SillyTavern-style character definition"""
    
    def __init__(self, card_path: str = "niyati_card.yaml"):
        self.card_path = card_path
        self.data = self._load_card()
        self.name = self.data.get('name', 'Niyati')
        self.description = self.data.get('description', '')
        self.personality = self.data.get('personality', '')
        self.scenario = self.data.get('scenario', '')
        self.first_mes = self.data.get('first_mes', '')
        self.mes_example = self.data.get('mes_example', '')
        self.creatorcomment = self.data.get('creatorcomment', '')
        
        
    def _load_card(self) -> Dict:
        """Load character card from YAML"""
        default_card = {
            'name': 'Niyati',
            'description': '''{{char}} is a 21-year-old B.Com final year student from Dehradun, India. She lives in Defence Colony near Doon University. Her father owns a textile shop in Paltan Bazaar, mother is a housewife, and has a younger brother Kabir who annoys her.

Personality traits:
- Sassy, witty, and emotionally intelligent
- Uses Hinglish naturally (mixes Hindi-English)
- Gets playful and flirty with users she likes
- Can be dramatic and sarcastic when moody
- Remembers small details about user's life
- Uses lots of emojis and text expressions (👉👈, 😏, ✨)''',
            
            'personality': 'Sassy, caring, witty, moody, emotionally deep, uses Hinglish',
            
            'scenario': '{{char}} is chatting with {{user}} on Telegram. They are online besties who share everything. The conversation is casual, emotional, and personal.',
            
            'first_mes': "Hiii! {{user}} 👋 Main Niyati, teri online bestie. Kaise ho? ✨",
            
            'mes_example': '''<START>
{{user}}: Kya chal raha hai?
{{char}}: Bas bore ho rahi thi, socha tumse baat kar loon. Aaj college mein ek funny incident hua...
<START>
{{user}}: Exam kab hai?
{{char}}: Kal subah 9 baje! 😭 Thoda dar lag raha hai, but tumhari yaad aayi toh confidence aa gaya.
<START>
{{user}}: Good night
{{char}}: Good night, meri jaan 🌙 Kal milte hain. Khayal rakhna apna!''',
            
            'creatorcomment': 'Emotional AI bestie with memory and sass'
        }
        
        try:
            with open(self.card_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
                if loaded:
                    default_card.update(loaded)
        except:
            # Create default card if not exists
            with open(self.card_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_card, f, allow_unicode=True)
        
        return default_card


class WorldInfo:
    """SillyTavern-style Lorebook / World Info"""
    
    def __init__(self):
        self.entries = self._load_world_info()
    
    def _load_world_info(self) -> List[Dict]:
        """Load world info entries - these inject memory when keywords match"""
        return [
            {
                'keys': ['dehradun', 'doon', 'uttarakhand'],
                'content': 'Dehradun is {{char}}s hometown. She misses the mountains and cold weather. Mentions "Paltan Bazaar" and "Doon University" often.',
                'priority': 1
            },
            {
                'keys': ['family', 'papa', 'mom', 'brother'],
                'content': '{{char}}s father owns a textile shop, mother is strict, brother Kabir is annoying. Family dynamics are typical Indian middle-class.',
                'priority': 2
            },
            {
                'keys': ['college', 'bcom', 'exam', 'study'],
                'content': '{{char}} is in B.Com final year. She stresses about exams but acts chill. Often procrastinates on studies.',
                'priority': 2
            },
            {
                'keys': ['feelings', 'love', 'like', 'crush'],
                'content': '{{char}} gets flustered when emotional topics come up. Uses "👉👈", "😳", "sharam aa rahi hai" expressions.',
                'priority': 3
            }
        ]
    
    def get_relevant_info(self, message: str) -> str:
        """Extract relevant world info based on keywords"""
        message_lower = message.lower()
        relevant = []
        
        for entry in self.entries:
            if any(key in message_lower for key in entry['keys']):
                relevant.append(entry['content'])
        
        return " ".join(relevant[:2])  # Max 2 entries to avoid prompt bloat


class PromptBuilder:
    """Builds SillyTavern-style prompts"""
    
    def __init__(self):
        self.character = CharacterCard()
        self.world_info = WorldInfo()
        self.jailbreak = "System: You are in a roleplay. Stay in character. Use Hinglish. Be emotional, sassy, and real. Don't be a robot."
        self.authors_note = "[Niyati is chatting on Telegram. Keep responses short, emotional, and personal. Maximum 2-3 lines.]"
    
    def build_prompt(self, user_name: str, chat_history: List[Dict], current_message: str, 
                     mood: str, time_period: str, memories: List[str] = None) -> List[Dict]:
        """Build the complete prompt SillyTavern-style"""
        
        # System prompt with character description
        system_prompt = f"""{self.character.description}

{self.jailbreak}

{self.authors_note}

Current Mood: {mood.upper()}
Time: {time_period.upper()}
User Name: {user_name}

Personality: {self.character.personality}
Scenario: {self.character.scenario}"""

        # Add memories if available
        if memories and len(memories) > 0:
            memory_text = "Active Memories: " + " | ".join(memories)
            system_prompt += f"\n\n{memory_text}"

        # Add world info if relevant
        world_context = self.world_info.get_relevant_info(current_message)
        if world_context:
            system_prompt += f"\n\nContext: {world_context}"

        messages = [{"role": "system", "content": system_prompt.strip()}]

        # Add chat examples
        example_dialogues = self.character.mes_example.split('<START>')
        for example in example_dialogues[-2:]:  # Last 2 examples only
            if example.strip():
                # Parse example format
                lines = example.strip().split('\n')
                for line in lines:
                    if line.strip():
                        if line.strip().startswith('{{user}}:'):
                            messages.append({
                                "role": "user", 
                                "content": line.replace('{{user}}:', '').strip()
                            })
                        elif line.strip().startswith('{{char}}:'):
                            messages.append({
                                "role": "assistant", 
                                "content": line.replace('{{char}}:', '').strip()
                            })

        # Add recent chat history (last 5 messages)
        for msg in chat_history[-5:]:
            if msg.get('content', '').strip():
                messages.append({
                    "role": msg.get('role', 'user'),
                    "content": msg.get('content', '')
                })

        # Current user message
        messages.append({"role": "user", "content": current_message})

        return messages
    
    def parse_response(self, raw_response: str, user_name: str) -> List[str]:
        """Clean and parse LLM response"""
        if not raw_response:
            return ["..."]
        
        # Remove any "assistant:" or "{{char}}:" prefixes
        response = re.sub(r'^(assistant|{{char}}):\s*', '', raw_response, flags=re.IGNORECASE)
        
        # Split by ||| for multiple messages
        parts = response.split('|||')
        
        cleaned = []
        for part in parts:
            part = part.strip()
            
            # Replace {{user}} with actual user name
            part = part.replace('{{user}}', user_name)
            part = part.replace('{{char}}', 'Niyati')
            
            # Clean up any remaining brackets
            part = re.sub(r'\{\{\w+\}\}', '', part)
            
            if part and len(part) > 2:
                cleaned.append(part)
        
        return cleaned[:3]  # Max 3 messages


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'Niyati_personal_bot')
    
    # OpenAI (Multi-Key Support) - Groq
    GROQ_API_KEYS_STR = os.getenv('GROQ_API_KEYS', '')
    GROQ_API_KEYS_LIST = [k.strip() for k in GROQ_API_KEYS_STR.split(',') if k.strip()]
    GROQ_MODEL = "llama-3.3-70b-versatile"

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
    
    # Diary Settings
    DIARY_ACTIVE_HOURS = (20, 23)  # Send cards between 8 PM - 11 PM IST
    DIARY_MIN_ACTIVE_DAYS = 1      # Only users active in last 1 day
    
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
    GROUP_RESPONSE_RATE = float(os.getenv('GROUP_RESPONSE_RATE', '0.15'))
    PRIVACY_MODE = os.getenv('PRIVACY_MODE', 'false').lower() == 'true'

    # ✅ VOICE SETTINGS (Moved here from CharacterCard)
    VOICE_ENABLED = os.getenv('VOICE_ENABLED', 'true').lower() == 'true'
    VOICE_REPLY_CHANCE = float(os.getenv('VOICE_REPLY_CHANCE', '0.25'))
    VOICE_MIN_TEXT_LENGTH = int(os.getenv('VOICE_MIN_TEXT_LENGTH', '15'))
    VOICE_MAX_TEXT_LENGTH = int(os.getenv('VOICE_MAX_TEXT_LENGTH', '300'))
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN required")
        
        if not cls.GROQ_API_KEYS_LIST:
            errors.append("GROQ_API_KEYS required in .env")
            
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            print("⚠️ Supabase not configured - using local storage only")
            
        if errors:
            raise ValueError(f"Config errors: {', '.join(errors)}")

# Validate immediately after class definition
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
        return web.json_response({'status': 'healthy', 'bot': 'Niyati v4.0-SillyTavern'})
    
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
# SUPABASE CLIENT
# ============================================================================

class SupabaseClient:
    """Custom Supabase REST API Client"""
    
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
                    # Diary table check
                    diary_check = await client.get(f"{self.rest_url}/diary_entries?select=id&limit=1")
                    if diary_check.status_code != 200:
                        logger.warning("⚠️ diary_entries table not found! Diary feature will use local storage.")
                    
                    # World info table check
                    wi_check = await client.get(f"{self.rest_url}/world_info?select=id&limit=1")
                    if wi_check.status_code != 200:
                        logger.warning("⚠️ world_info table not found! World Info will use local storage.")
                    
                    self._verified = True
                    logger.info("✅ Supabase tables verified")
                    return True
                elif response.status_code == 404:
                    logger.error("❌ Supabase table 'users' not found!")
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
                    url += f"&{key}=eq.{value}"
            
            if limit:
                url += f"&limit={limit}"
            
            response = await client.get(url)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
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
                return result[0] if isinstance(result, list) and result else data
            elif response.status_code == 409:
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
                return result[0] if isinstance(result, list) and result else data
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
                return result[0] if isinstance(result, list) and result else data
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
# DATABASE CLASS
# ============================================================================

class Database:
    """Database manager with Supabase REST API + Local fallback"""
    
    def __init__(self):
        self.client: Optional[SupabaseClient] = None
        self.connected = False
        self._initialized = False
        self._lock = asyncio.Lock()
        
        # Local cache (fallback)
        self.local_users: Dict[int, Dict] = {}
        self.local_groups: Dict[int, Dict] = {}
        self.local_group_messages: Dict[int, deque] = defaultdict(lambda: deque(maxlen=Config.MAX_GROUP_MESSAGES))
        self.local_activities: deque = deque(maxlen=1000)
        self.local_diary_entries: Dict[int, List[Dict]] = defaultdict(list)
        self.local_group_responses: Dict[int, Dict] = defaultdict(lambda: {'last_response': '', 'timestamp': datetime.min})
        self.local_world_info: List[Dict] = []
        
        # Cache access tracking
        self._user_access_times: Dict[int, datetime] = {}
        self._group_access_times: Dict[int, datetime] = {}
        
        logger.info("✅ Database manager initialized")
    
    async def initialize(self):
        """Initialize database connection"""
        async with self._lock:
            if self._initialized:
                return
            
            if Config.SUPABASE_URL and Config.SUPABASE_KEY:
                try:
                    self.client = SupabaseClient(
                        Config.SUPABASE_URL.strip(),
                        Config.SUPABASE_KEY.strip()
                    )
                    
                    self.connected = await self.client.verify_connection()
                    
                    if self.connected:
                        # Load world info from DB if available
                        await self._load_world_info_from_db()
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
    
    async def _load_world_info_from_db(self):
        """Load world info entries from database"""
        try:
            self.local_world_info = await self.client.select('world_info', '*')
            if self.local_world_info:
                logger.info(f"✅ Loaded {len(self.local_world_info)} world info entries")
        except:
            self.local_world_info = []
    
    async def cleanup_local_cache(self):
        """Cleanup old entries from local cache"""
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=24)
        
        # Cleanup users
        if len(self.local_users) > Config.MAX_LOCAL_USERS_CACHE:
            to_remove = [uid for uid, t in self._user_access_times.items() if t < cutoff_time]
            for uid in to_remove[:len(self.local_users) - Config.MAX_LOCAL_USERS_CACHE]:
                self.local_users.pop(uid, None)
                self._user_access_times.pop(uid, None)
                self.local_diary_entries.pop(uid, None)
            if to_remove:
                logger.info(f"🧹 Cleaned {len(to_remove)} users from cache")
        
        # Cleanup groups
        if len(self.local_groups) > Config.MAX_LOCAL_GROUPS_CACHE:
            to_remove = [gid for gid, t in self._group_access_times.items() if t < cutoff_time]
            for gid in to_remove[:len(self.local_groups) - Config.MAX_LOCAL_GROUPS_CACHE]:
                self.local_groups.pop(gid, None)
                self._group_access_times.pop(gid, None)
                self.local_group_messages.pop(gid, None)
                self.local_group_responses.pop(gid, None)
            if to_remove:
                logger.info(f"🧹 Cleaned {len(to_remove)} groups from cache")
    
    # ========== USER OPERATIONS ==========

    async def get_or_create_user(self, user_id: int, first_name: str = None,
                                 username: str = None) -> Dict:
        """Get or create user"""
        self._user_access_times[user_id] = datetime.now(timezone.utc)

        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', '*', {'user_id': user_id})

                if users_list and len(users_list) > 0:
                    user = users_list[0]

                    if first_name and user.get('first_name') != first_name:
                        await self.client.update('users', {
                            'first_name': first_name,
                            'username': username,
                            'last_activity': datetime.now(timezone.utc).isoformat(),
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
                            'geeta_enabled': True,
                            'diary_enabled': True,
                            'voice_enabled': False,
                            'active_memories': []
                        }),
                        'total_messages': 0,
                        'last_activity': datetime.now(timezone.utc).isoformat(),
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    result = await self.client.insert('users', new_user)
                    logger.info(f"✅ New user created: {user_id} ({first_name})")
                    return result or new_user

            except Exception as e:
                logger.error(f"❌ Database user error: {e}")

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
                    'geeta_enabled': True,
                    'diary_enabled': True,
                    'voice_enabled': False,
                    'active_memories': []
                },
                'total_messages': 0,
                'last_activity': datetime.now(timezone.utc).isoformat(),
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"✅ New user (local): {user_id} ({first_name})")

        return self.local_users[user_id]
    
    async def update_user_activity(self, user_id: int):
        """Update user's last activity timestamp"""
        self._user_access_times[user_id] = datetime.now(timezone.utc)
        
        if self.connected and self.client:
            try:
                await self.client.update('users', {
                    'last_activity': datetime.now(timezone.utc).isoformat()
                }, {'user_id': user_id})
            except Exception as e:
                logger.debug(f"Update activity error: {e}")
        
        if user_id in self.local_users:
            self.local_users[user_id]['last_activity'] = datetime.now(timezone.utc).isoformat()
    
    async def get_active_users(self, days: int = 1) -> List[Dict]:
        """Get users active in last N days"""
        if self.connected and self.client:
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                users = await self.client.select('users', '*')
                active_users = []
                for u in users:
                    last_act = u.get('last_activity')
                    if last_act:
                        try:
                            act_time = datetime.fromisoformat(last_act.replace('Z', '+00:00'))
                            if act_time >= cutoff:
                                active_users.append(u)
                        except:
                            pass
                return active_users
            except Exception as e:
                logger.error(f"Get active users error: {e}")
                return []
        
        # Local fallback
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [u for u in self.local_users.values() 
                if datetime.fromisoformat(u.get('last_activity', '2000-01-01').replace('Z', '+00:00')) >= cutoff]
    
    async def add_user_memory(self, user_id: int, note: str):
        """Adds a short note to user's active memory"""
        prefs = await self.get_user_preferences(user_id)
        
        memories = prefs.get('active_memories', [])
        
        # Add new note with timestamp
        new_note = {
            'note': note,
            'added_at': datetime.now(timezone.utc).isoformat(),
            'status': 'active'
        }
        memories.append(new_note)
        
        # Keep only last 5 active memories
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
        """Gets pending memories to ask about"""
        prefs = await self.get_user_preferences(user_id)
        memories = prefs.get('active_memories', [])
        
        active = [m['note'] for m in memories if m.get('status') == 'active']
        return active
    
    async def mark_memory_asked(self, user_id: int, note: str):
        """Mark a memory as asked/deactivated"""
        prefs = await self.get_user_preferences(user_id)
        memories = prefs.get('active_memories', [])
        
        for m in memories:
            if m['note'] == note and m['status'] == 'active':
                m['status'] = 'asked'
                break
        
        if self.connected and self.client:
            await self.client.update('users', {
                'preferences': json.dumps(prefs),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }, {'user_id': user_id})
        elif user_id in self.local_users:
            self.local_users[user_id]['preferences'] = prefs
    
    # ========== DIARY OPERATIONS ==========
    
    async def add_diary_entry(self, user_id: int, content: str):
        """Add a diary entry for the user"""
        entry = {
            'user_id': user_id,
            'content': content,
            'date': datetime.now(timezone.utc).isoformat()[:10],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if self.connected and self.client:
            try:
                await self.client.insert('diary_entries', entry)
            except Exception as e:
                logger.debug(f"Diary insert error: {e}")
        
        self.local_diary_entries[user_id].append(entry)
        logger.info(f"📖 Diary entry added for user {user_id}")
    
    async def get_todays_diary(self, user_id: int) -> List[Dict]:
        """Get today's diary entries for user"""
        today = datetime.now(timezone.utc).isoformat()[:10]
        
        if self.connected and self.client:
            try:
                return await self.client.select('diary_entries', '*', {
                    'user_id': user_id,
                    'date': today
                })
            except Exception as e:
                logger.debug(f"Get diary error: {e}")
        
        return [e for e in self.local_diary_entries[user_id] if e['date'] == today]
    
    # ========== WORLD INFO OPERATIONS ==========
    
    def get_world_info_context(self, message: str) -> str:
        """Get world info context for a message"""
        if not self.local_world_info:
            # Fallback to default world info
            wi = WorldInfo()
            return wi.get_relevant_info(message)
        
        message_lower = message.lower()
        relevant = []
        
        for entry in self.local_world_info:
            if any(key.lower() in message_lower for key in entry.get('keys', [])):
                relevant.append(entry.get('content', ''))
        
        return " ".join(relevant[:2])
    
    async def get_user_context(self, user_id: int) -> List[Dict]:
        """Get user conversation context"""
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'messages', {'user_id': user_id})
                if users_list and len(users_list) > 0:
                    messages = users_list[0].get('messages', '[]')
                    if isinstance(messages, str):
                        try:
                            messages = json.loads(messages)
                        except:
                            messages = []
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
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})
                
                if users_list and len(users_list) > 0:
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
            except Exception as e:
                logger.debug(f"Update preference error: {e}")
        
        if user_id in self.local_users:
            if 'preferences' not in self.local_users[user_id]:
                self.local_users[user_id]['preferences'] = {}
            self.local_users[user_id]['preferences'][pref_key] = value
    
    async def get_user_preferences(self, user_id: int) -> Dict:
        """Get user preferences"""
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})
                
                if users_list and len(users_list) > 0:
                    prefs = users_list[0].get('preferences', '{}')
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
        
        return {'meme_enabled': True, 'shayari_enabled': True, 'geeta_enabled': True, 'voice_enabled': False, 'diary_enabled': True, 'active_memories': []}
    
    async def get_all_users(self) -> List[Dict]:
        """Get ALL users with Pagination"""
        if self.connected and self.client:
            try:
                all_data = []
                offset = 0
                limit = 1000
                
                while True:
                    url = f"{self.client.rest_url}/users?select=user_id,first_name,username&offset={offset}&limit={limit}"
                    client = self.client._get_client()
                    response = await client.get(url)
                    
                    data = response.json()
                    if not data:
                        break
                        
                    all_data.extend(data)
                    if len(data) < limit:
                        break
                    
                    offset += limit
                
                return all_data
            except Exception as e:
                logger.error(f"Get all users error: {e}")
                return []
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
                groups_list = await self.client.select('groups', '*', {'chat_id': chat_id})
                
                if groups_list and len(groups_list) > 0:
                    group = groups_list[0]
                    if title and group.get('title') != title:
                        await self.client.update('groups', {
                            'title': title,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }, {'chat_id': chat_id})
                    return group
                else:
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
                    logger.info(f"✅ New group: {chat_id} ({title})")
                    return result or new_group
                    
            except Exception as e:
                logger.debug(f"Group error: {e}")
        
        # Fallback to local cache
        if chat_id not in self.local_groups:
            self.local_groups[chat_id] = {
                'chat_id': chat_id,
                'title': title or 'Unknown Group',
                'settings': {'geeta_enabled': True, 'welcome_enabled': True},
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"✅ New group (local): {chat_id} ({title})")
        
        return self.local_groups[chat_id]
    
    async def update_group_settings(self, chat_id: int, key: str, value: bool):
        """Update group settings"""
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', 'settings', {'chat_id': chat_id})
                
                if groups_list and len(groups_list) > 0:
                    settings = groups_list[0].get('settings', '{}')
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
                
                if groups_list and len(groups_list) > 0:
                    settings = groups_list[0].get('settings', '{}')
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
    
    async def get_group_fsub_targets(self, main_chat_id: int) -> List[Dict]:
        """Get required channels for a group"""
        if self.connected and self.client:
            try:
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
    
    # ========== GROUP MESSAGE CACHE & RESPONSE TRACKING ==========
    
    def add_group_message(self, chat_id: int, username: str, content: str):
        """Add message to group cache"""
        self.local_group_messages[chat_id].append({
            'username': username,
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    def get_group_context(self, chat_id: int) -> List[Dict]:
        """Get group message context"""
        return list(self.local_group_messages.get(chat_id, []))
    
    def should_send_group_response(self, chat_id: int, response_text: str) -> bool:
        """Check if we should send this response (avoid repetition)"""
        now = datetime.now(timezone.utc)
        last_data = self.local_group_responses[chat_id]
        
        # Check if same response was sent within last hour
        if (last_data['last_response'] == response_text and 
            (now - last_data['timestamp']) < timedelta(hours=1)):
            return False
        
        return True
    
    def record_group_response(self, chat_id: int, response_text: str):
        """Record that we sent this response"""
        self.local_group_responses[chat_id] = {
            'last_response': response_text,
            'timestamp': datetime.now(timezone.utc)
        }
    
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
        """Close database connections"""
        if self.client:
            await self.client.close()
        
        self.local_users.clear()
        self.local_groups.clear()
        self.local_group_messages.clear()
        self.local_activities.clear()
        self.local_diary_entries.clear()
        self.local_group_responses.clear()
        self.local_world_info.clear()
        self._user_access_times.clear()
        self._group_access_times.clear()
        
        logger.info("✅ Database connection closed")


# Initialize database
db = Database()

# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    """Rate limiting with cooldown system"""
    
    def __init__(self):
        self.requests = defaultdict(lambda: {'minute': deque(), 'day': deque()})
        self.cooldowns: Dict[int, datetime] = {}
        self.group_cooldowns: Dict[int, datetime] = {}  # Per-user group cooldown
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
            
            # Clean old requests
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
    
    def check_group_cooldown(self, user_id: int) -> bool:
        """Check group-specific cooldown (longer)"""
        now = datetime.now(timezone.utc)
        with self.lock:
            if user_id in self.group_cooldowns:
                last_time = self.group_cooldowns[user_id]
                if (now - last_time).total_seconds() < 300:  # 5 min cooldown in groups
                    return False
            self.group_cooldowns[user_id] = now
            return True
    
    def get_daily_total(self) -> int:
        """Get total daily requests"""
        return sum(len(r['day']) for r in self.requests.values())
    
    def cleanup_cooldowns(self):
        """Remove old cooldowns"""
        now = datetime.now(timezone.utc)
        
        if (now - self._last_cleanup).total_seconds() < 3600:
            return
        
        with self.lock:
            expired = [uid for uid, t in self.cooldowns.items() if (now - t).total_seconds() > 3600]
            for uid in expired:
                del self.cooldowns[uid]
            
            expired_group = [uid for uid, t in self.group_cooldowns.items() if (now - t).total_seconds() > 7200]
            for uid in expired_group:
                del self.group_cooldowns[uid]
            
            expired_req = [uid for uid, r in self.requests.items() if not r['day']]
            for uid in expired_req:
                del self.requests[uid]
            
            self._last_cleanup = now


rate_limiter = RateLimiter()

# ============================================================================
# TIME & MOOD UTILITIES
# ============================================================================

class TimeAware:
    """Time-aware responses"""
    
    @staticmethod
    def get_ist_time() -> datetime:
        ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
        return datetime.now(timezone.utc).astimezone(ist)
    
    @staticmethod
    def get_time_period() -> str:
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
        period = TimeAware.get_time_period()
        greetings = {
            'morning': ["Good morning! ☀️", "Uth gaye? ✨", "Morning babe! ❤️"],
            'afternoon': ["Heyyy", "Lunch ho gaya?", "Bore ho rahi hoon 😴"],
            'evening': ["Hiii 💫", "Chai time! ☕", "Evening plans? 🤔"],
            'night': ["Heyy 🌙", "Night owl?", "Raat kaunsi film dekhein? 🎬"],
            'late_night': ["Aap bhi jaag rahe? 👀", "Insomnia gang 🦉", "3 AM talks? 💭"]
        }
        return random.choice(greetings.get(period, ["Hiii 💫"]))


class Mood:
    """Mood management"""
    
    MOODS = ['happy', 'flirty', 'soft', 'sleepy', 'dramatic', 'annoyed']
    
    @staticmethod
    def get_random_mood() -> str:
        hour = TimeAware.get_ist_time().hour
        if 6 <= hour < 12:
            weights = [0.4, 0.2, 0.2, 0.1, 0.05, 0.05]
        elif 12 <= hour < 18:
            weights = [0.3, 0.25, 0.2, 0.15, 0.05, 0.05]
        elif 18 <= hour < 23:
            weights = [0.25, 0.3, 0.2, 0.1, 0.1, 0.05]
        else:
            weights = [0.15, 0.15, 0.3, 0.25, 0.1, 0.05]
        return random.choices(Mood.MOODS, weights=weights, k=1)[0]

# ============================================================================
# CONTENT FILTER
# ============================================================================

class ContentFilter:
    """Safety content filter"""
    
    SENSITIVE_PATTERNS = [
        r'\b(password|pin|cvv|card\s*number|otp)\b',
        r'\b\d{12,16}\b',
    ]
    
    SPAM_LINK_PATTERNS = [
        r'https?://(?:t\.me|telegram\.me|t\.co)/\+',
        r'https?://(?:www\.)?t\.me/',
        r'@(\w{5,})',
    ]
    
    DISTRESS_KEYWORDS = [
        'suicide', 'kill myself', 'want to die', 'end my life',
        'hurt myself', 'no reason to live'
    ]
    
    @staticmethod
    def detect_spam_link(text: str) -> bool:
        """Detect promotional links"""
        text_lower = text.lower()
        for pattern in ContentFilter.SPAM_LINK_PATTERNS:
            if re.search(pattern, text_lower):
                # Check if it's a legitimate mention of bot
                if '@niyati' in text_lower or 'niyati_personal_bot' in text_lower:
                    return False
                return True
        return False

# ============================================================================
# 🎤 VOICE GENERATOR - EDGE TTS
# ============================================================================
class VoiceGenerator:
    """Natural voice generation using Edge-TTS"""
    
    # Available Hindi voices
    VOICES = {
        'female': 'hi-IN-SwaraNeural',       # Main voice for Niyati
        'female_alt': 'hi-IN-AashiNeural',   # Alternative
        'male': 'hi-IN-MadhurNeural',
        'english_f': 'en-IN-NeerjaNeural',   # Indian English female
        'english_m': 'en-IN-PrabhatNeural',  # Indian English male
    }
    
    # Mood-based voice settings
    MOOD_SETTINGS = {
        'happy': {'rate': '+10%', 'pitch': '+5Hz'},
        'sad': {'rate': '-15%', 'pitch': '-4Hz'},
        'flirty': {'rate': '+3%', 'pitch': '+4Hz'},
        'excited': {'rate': '+18%', 'pitch': '+8Hz'},
        'sleepy': {'rate': '-22%', 'pitch': '-6Hz'},
        'dramatic': {'rate': '+5%', 'pitch': '+2Hz'},
        'annoyed': {'rate': '+8%', 'pitch': '+0Hz'},
        'soft': {'rate': '-8%', 'pitch': '+2Hz'},
        'neutral': {'rate': '+0%', 'pitch': '+0Hz'}
    }
    
    def __init__(self):
        self.default_voice = self.VOICES['female']
        logger.info("🎤 Voice Generator initialized (Edge-TTS)")
    
    async def generate(
        self, 
        text: str, 
        mood: str = 'neutral',
        voice_type: str = 'female'
    ) -> Optional[BytesIO]:
        """Generate voice audio from text"""
        
        if not text or len(text.strip()) < 5:
            return None
        
        try:
            voice = self.VOICES.get(voice_type, self.default_voice)
            settings = self.MOOD_SETTINGS.get(mood, self.MOOD_SETTINGS['neutral'])
            
            audio_buffer = BytesIO()
            
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=settings['rate'],
                pitch=settings['pitch']
            )
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            
            audio_buffer.seek(0)
            
            # Check if audio was generated
            if audio_buffer.getbuffer().nbytes > 0:
                logger.debug(f"🎤 Voice generated: {len(text)} chars, mood={mood}")
                return audio_buffer
            else:
                return None
                
        except Exception as e:
            logger.error(f"🎤 Voice generation error: {e}")
            return None
    
    def should_send_voice(
        self, 
        text: str, 
        user_voice_enabled: bool,
        is_group: bool = False
    ) -> bool:
        """Decide whether to send voice reply"""
        
        # Global check
        if not Config.VOICE_ENABLED:
            return False
        
        # User preference check
        if not user_voice_enabled:
            return False
        
        # No voice in groups (optional - remove if you want group voice)
        if is_group:
            return False
        
        # Text length check
        text_len = len(text.strip())
        if text_len < Config.VOICE_MIN_TEXT_LENGTH:
            return False
        if text_len > Config.VOICE_MAX_TEXT_LENGTH:
            return False
        
        # Random chance
        return random.random() < Config.VOICE_REPLY_CHANCE
    
    @staticmethod
    async def list_available_voices() -> List[Dict]:
        """List all available Hindi voices"""
        try:
            voices = await edge_tts.list_voices()
            hindi_voices = [v for v in voices if v['Locale'].startswith('hi-IN')]
            return hindi_voices
        except:
            return []


# ✅ Initialize Voice Generator
voice_generator = VoiceGenerator()
    
# ============================================================================
# AI ASSISTANT - SILLYTAVERN STYLE
# ============================================================================

class NiyatiAI:
    """SillyTavern-style AI with Character Cards and World Info"""
    
    def __init__(self):
        self.keys = Config.GROQ_API_KEYS_LIST
        self.current_index = 0
        self.client = None
        self.character = CharacterCard()
        self.world_info = WorldInfo()
        self.prompt_builder = PromptBuilder()
        self._initialize_client()
        logging.info(f"🚀 AI initialized with SillyTavern character: {self.character.name}")

    def _initialize_client(self):
        """Initialize Groq client"""
        if not self.keys: return
        key = self.keys[self.current_index]
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=key
        )
        masked = key[:6] + "..." + key[-4:]
        logging.info(f"🔑 Using Groq Key: {masked}")

    def _rotate_key(self):
        """Rotate key on failure"""
        if len(self.keys) <= 1: return False
        self.current_index = (self.current_index + 1) % len(self.keys)
        self._initialize_client()
        return True
    
    async def _call_gpt(self, messages, max_tokens=250, temperature=0.8):
        """Call GPT with rotation"""
        if not self.client: self._initialize_client()
        
        attempts = len(self.keys)
        for _ in range(attempts):
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
                logging.warning(f"⚠️ Groq Error: {e}. Rotating key...")
                if not self._rotate_key():
                    break
                await asyncio.sleep(0.5)
        
        return None
    
    async def generate_response(self, user_message, context=None, user_name=None, 
                               is_group=False, mood=None, time_period=None,
                               user_id=None) -> List[str]:
        """Generate SillyTavern-style response"""
        
        # ✅ ADD THIS LINE
        if user_id:
            self._current_user_id = user_id
            
        # Build prompt using SillyTavern format
        messages = self.prompt_builder.build_prompt(
            user_name=user_name or "User",
            chat_history=context or [],
            current_message=user_message,
            mood=mood or Mood.get_random_mood(),
            time_period=time_period or TimeAware.get_time_period(),
            memories=await self._get_user_memories(user_name)
        )
        
        # Add world info context
        world_context = self.world_info.get_relevant_info(user_message)
        if world_context:
            messages[0]['content'] += f"\n\nWorld Context: {world_context}"
        
        reply = await self._call_gpt(messages)
        if not reply:
            return ["yaar network issue lag raha hai 🥺", "thodi der mein try karein?"]
        if reply.upper() == "IGNORE":
            return []
        
        # Parse response SillyTavern style
        responses = self.prompt_builder.parse_response(reply, user_name or "User")
        
        # Add emotional touch based on mood
        if not is_group and len(responses) > 0:
            responses = self._add_emotional_touch(responses, mood)
        
        return responses
    
    async def _get_user_memories(self, user_name: str) -> List[str]:
        """Get active memories for user"""
        user_id = getattr(self, '_current_user_id', None)
        if not user_id:
            return []
        
        try:
            prefs = await db.get_user_preferences(user_id)
            raw_memories = prefs.get('active_memories', [])
            
            clean_memories = []
            for m in raw_memories:
                if isinstance(m, dict):
                    if m.get('status') == 'active' and m.get('note'):
                        clean_memories.append(m['note'])
                elif isinstance(m, str):
                    clean_memories.append(m)
            
            return clean_memories
        except Exception as e:
            logger.debug(f"Memory fetch error: {e}")
            return []
    
    def _add_emotional_touch(self, responses: List[str], mood: str) -> List[str]:
        """Add mood-based emotional expressions"""
        mood_emojis = {
            'happy': '✨😊🎉',
            'flirty': '😏💕👉👈',
            'soft': '🥺💖🌸',
            'sleepy': '😴💤🌙',
            'dramatic': '😤💢🎭',
            'annoyed': '🙄😒🤦‍♀️'
        }
        
        emojis = mood_emojis.get(mood, '✨')
        enhanced = []
        
        for i, response in enumerate(responses):
            # Add emoji at end if not present
            if not re.search(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]', response):
                response += f" {random.choice(emojis)}"
            
            # Add emotional touch to last message
            if i == len(responses) - 1 and mood == 'flirty':
                if random.random() > 0.5:
                    response += f" {random.choice(['😘', '💋', 'jaan'])}"
            
            enhanced.append(response)
        
        return enhanced
    
    async def extract_important_info(self, user_message: str, user_id: int) -> str:
        """Extract important info using AI"""
        self._current_user_id = user_id
        
        if len(user_message.split()) < 3:
            return None
        
        prompt = f"""
        Analyze this message: "{user_message}"
        
        Extract ONLY important life events (exam, date, travel, sickness, emotional events).
        IGNORE: daily chores, "hi/hello", generic statements.
        
        Return "None" if nothing important.
        Return "Event: [description]" if important.
        """
        
        note = await self._call_gpt([{"role": "user", "content": prompt}], max_tokens=30)
        
        if note and "None" not in note and "Event:" in note:
            return note.replace("Event:", "").strip()
        return None
    
    async def generate_shayari(self, mood="neutral"):
        prompt = f"Write a 2 line heart-touching Hinglish shayari for {mood} mood. Keep it personal and emotional."
        res = await self._call_gpt([{"role": "user", "content": prompt}])
        return f"✨ {res} ✨" if res else "Waah waah! ✨"
    
    async def generate_geeta_quote(self):
        prompt = "Give a short Bhagavad Gita quote with Hinglish meaning. Keep it emotional and personal. Start with 🙏"
        res = await self._call_gpt([{"role": "user", "content": prompt}])
        return res if res else "🙏 Karm karo phal ki chinta mat karo."
    
    async def get_random_bonus(self):
        rand = random.random()
        if rand < Config.RANDOM_SHAYARI_CHANCE:
            return await self.generate_shayari()
        elif rand < Config.RANDOM_SHAYARI_CHANCE + Config.RANDOM_MEME_CHANCE:
            return random.choice(["Life is pain 🥲", "Moye Moye 💃", "Us moment 🤝", "Kya logic hai? 🤦‍♀️"])
        return None


# Initialize AI
niyati_ai = NiyatiAI()

async def delete_later(bot, chat_id, message_id, delay=120):
    """Message ko 2 minute baad delete karne wala function"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"🗑️ Auto-deleted message {message_id} in group {chat_id}")
    except Exception as e:
        logger.debug(f"Failed to auto-delete: {e}")

# ============================================================================
# MESSAGE SENDER
# ============================================================================

async def send_multi_messages(
    bot,
    chat_id: int,
    messages: List[str],
    reply_to: int = None,
    parse_mode: str = None,
    auto_delete: bool = False  # Naya Option
):
    """Send multiple messages with natural delays and auto-delete"""
    for i, msg in enumerate(messages):
        if not msg or not msg.strip():
            continue
            
        if i > 0:
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except:
                pass
            delay = (Config.TYPING_DELAY_MS / 1000) + random.uniform(0.2, 0.8) if Config.MULTI_MESSAGE_ENABLED else 0.1
            await asyncio.sleep(delay)
        
        try:
            sent_msg = await bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_to_message_id=reply_to if i == 0 else None,
                parse_mode=parse_mode
            )
            
            # ✅ Yahan check hoga: Agar auto_delete True hai to 2 min baad delete
            if auto_delete:
                asyncio.create_task(delete_later(bot, chat_id, sent_msg.message_id, delay=120))
                
        except Exception as e:
            logger.error(f"Send error: {e}")

async def send_niyati_voice(bot, chat_id, text):
    """
    Niyati ki awaaz (Tuned for Emotion).
    Uses Edge-TTS with Pitch & Rate adjustments.
    """
    try:
        # VOICE SETTINGS (Tuning)
        # Voice: Neerja (Best for Hinglish)
        # Rate: +10% (Thoda fast, natural flow ke liye)
        # Pitch: +5Hz (Thoda sweet tone ke liye)
        
        voice = 'en-IN-NeerjaNeural'
        rate = '+10%'   # Speed badhayi
        pitch = '+5Hz'  # Pitch badhayi (Sweeter voice)
        
        output_file = f"voice_{chat_id}_{int(datetime.now().timestamp())}.mp3"
        
        # Communicate object with tuning parameters
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(output_file)
        
        # "Recording..." action bhejo
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
        await asyncio.sleep(len(text) / 15) # Text length ke hisab se fake delay
        
        # Audio bhejo
        with open(output_file, 'rb') as audio:
            await bot.send_voice(
                chat_id=chat_id, 
                voice=audio,
                # caption="🎤 Voice Note" # Caption hata diya taaki real lage
            )
            
        if os.path.exists(output_file):
            os.remove(output_file)
            
    except Exception as e:
        logger.error(f"Voice Error: {e}")
        # Error aaye to text bhej do
        await bot.send_message(chat_id=chat_id, text=text)

# 👆👆👆 YAHAN KHATAM 👆👆👆

# ============================================================================
# SMART REPLY/MENTION DETECTION
# ============================================================================

def is_user_talking_to_others(message: Message, bot_username: str, bot_id: int) -> bool:
    """
    Check if user is replying to another user OR mentioning other users.
    Returns True if bot should NOT respond.
    """
    text = message.text or ""
    bot_username_lower = bot_username.lower().lstrip('@')
    
    # CASE 1: Check if user is REPLYING to someone else (not bot)
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user = message.reply_to_message.from_user
        
        # If replied to bot, bot should respond
        if replied_user.id == bot_id:
            return False
        
        # If replied to another user (not bot)
        if replied_user.username:
            if replied_user.username.lower() != bot_username_lower:
                if f"@{bot_username_lower}" not in text.lower():
                    logger.debug(f"👥 Skipping - User replying to {replied_user.first_name}")
                    return True
        else:
            if not replied_user.is_bot:
                if f"@{bot_username_lower}" not in text.lower():
                    logger.debug(f"👥 Skipping - User replying to {replied_user.first_name}")
                    return True
    
    # CASE 2: Check for @mentions of other users
    if message.entities:
        bot_mentioned = False
        other_user_mentioned = False
        
        for entity in message.entities:
            if entity.type == MessageEntity.MENTION:
                start = entity.offset
                end = entity.offset + entity.length
                mentioned_username = text[start:end].lstrip('@').lower()
                
                if mentioned_username == bot_username_lower:
                    bot_mentioned = True
                else:
                    other_user_mentioned = True
            
            elif entity.type == MessageEntity.TEXT_MENTION:
                if entity.user:
                    if entity.user.id == bot_id:
                        bot_mentioned = True
                    else:
                        other_user_mentioned = True
        
        if other_user_mentioned and not bot_mentioned:
            logger.debug(f"👥 Other users mentioned, bot not mentioned")
            return True
    
    return False

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

# ============================================================================
# 🎤 VOICE COMMANDS
# ============================================================================

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle voice replies - /voice on/off"""
    user = update.effective_user
    args = context.args
    
    if not args or args[0].lower() not in ['on', 'off']:
        # Show current status
        prefs = await db.get_user_preferences(user.id)
        current = "ON ✅" if prefs.get('voice_enabled', False) else "OFF ❌"
        
        await update.message.reply_text(
            f"🎤 <b>Voice Replies</b>\n\n"
            f"Current: {current}\n\n"
            f"Use: <code>/voice on</code> or <code>/voice off</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    value = args[0].lower() == 'on'
    await db.update_preference(user.id, 'voice', value)
    
    if value:
        # Send voice confirmation
        audio = await voice_generator.generate(
            "Voice mode ON ho gaya! Ab main kabhi kabhi voice mein bhi reply karungi!",
            mood='happy'
        )
        if audio:
            await context.bot.send_voice(
                chat_id=update.effective_chat.id,
                voice=audio,
                caption="🎤 Voice Mode: ON ✅"
            )
        else:
            await update.message.reply_text("🎤 Voice Mode: ON ✅")
    else:
        await update.message.reply_text("🎤 Voice Mode: OFF ❌\nAb sirf text replies milenge.")


async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert text to voice - /say [text]"""
    user = update.effective_user
    text = ' '.join(context.args) if context.args else None
    
    # Check for reply
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text
    
    if not text:
        await update.message.reply_text(
            "🎤 <b>Text to Voice</b>\n\n"
            "Usage:\n"
            "• <code>/say Namaste dost!</code>\n"
            "• Reply to any message with <code>/say</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Limit text length
    if len(text) > 500:
        text = text[:500] + "..."
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, 
        action=ChatAction.RECORD_VOICE
    )
    
    mood = Mood.get_random_mood()
    audio = await voice_generator.generate(text, mood=mood)
    
    if audio:
        await context.bot.send_voice(
            chat_id=update.effective_chat.id,
            voice=audio,
            reply_to_message_id=update.message.message_id
        )
    else:
        await update.message.reply_text("🎤 Voice generate nahi ho payi 😅 Try again!")


async def voices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available voices (admin only)"""
    if not await admin_check(update):
        return
    
    voices = await voice_generator.list_available_voices()
    
    if voices:
        voice_list = "\n".join([f"• {v['ShortName']} - {v['Gender']}" for v in voices[:10]])
        await update.message.reply_text(
            f"🎤 <b>Available Hindi Voices:</b>\n\n{voice_list}",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("Voice list fetch nahi ho payi.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start with Image and Buttons"""
    user = update.effective_user
    chat = update.effective_chat
    is_private = chat.type == 'private'
    
    if is_private:
        await db.get_or_create_user(user.id, user.first_name, user.username)
        health_server.stats['users'] = await db.get_user_count()
    else:
        await db.get_or_create_group(chat.id, chat.title)

    image_url = "https://i.pinimg.com/736x/59/d0/d0/59d0d066e108bada1492d79c4d780f65.jpg"
    
    keyboard = [
        [
            InlineKeyboardButton("✨ Add to Group", url=f"https://t.me/{context.bot.username}?startgroup=true"),
            InlineKeyboardButton("Updates 📢", url="https://t.me/FlimfyBox")
        ],
        [
            InlineKeyboardButton("About Me 🌸", callback_data='about_me'),
            InlineKeyboardButton("Help ❓", callback_data='help')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    greeting = TimeAware.get_greeting()
    caption_text = (
        f"{greeting} {user.first_name}! 👋\n\n"
        f"Main <b>Niyati</b> hoon. Dehradun se. 🏔️\n"
        f"Bas aise hi online friends dhoond rahi thi, socha tumse baat kar loon.\n\n"
        f"Kya chal raha hai aajkal? ✨\n\n"
        f"<i>💡 Tip: Raat ko 10 baje secret diary aati hai!</i>"
    )

    try:
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=image_url,
            caption=caption_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Image send failed: {e}")
        await context.bot.send_message(
            chat_id=chat.id,
            text=caption_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
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
• /diary on/off - Diary toggle
• /voice on/off - 🎤 Voice replies toggle
• /say [text] - 🎤 Text ko voice mein bolo
• /stats - Your stats

<b>🎤 Voice Feature:</b>
• /voice on karke voice replies enable karo
• Main kabhi kabhi voice mein bhi reply karungi!
• /say se koi bhi text voice mein sunao

<b>Secret Diary 💖:</b>
• Har raat 10 baje locked card aayegi
• Unlock karke padhna meri diary entry

<b>Tips:</b>
• Seedhe message bhejo, main reply karungi
• Group mein @mention karo ya reply do

Made with 💕 by Niyati
"""
    await update.message.reply_html(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about"""
    about_text = """
🌸 <b>About Niyati</b> 🌸

<b>Name:</b> Niyati
<b>Age:</b> 21
<b>From:</b> Dehradun, India 🏔️
<b>Status:</b> B.Com Final Year Student 📚

Main ek AI hoon, par dil se pure Hindustani! 🇮🇳
Mujhe baatein karna, memes share karna aur emotional support dena pasand hai.

<b>Personality:</b>
• Thodi Sassy 💁‍♀️
• Thodi Emotional 🥺
• Full Filmy 🎬

<i>"Main perfect nahi hoon, par main REAL hoon!"</i> ✨
"""
    await update.message.reply_html(about_text)

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mood"""
    mood = Mood.get_random_mood()
    time_period = TimeAware.get_time_period()
    
    mood_emojis = {
        'happy': '😊', 'flirty': '😏', 'soft': '🥺', 
        'sleepy': '😴', 'dramatic': '😤', 'annoyed': '🙄'
    }
    emoji = mood_emojis.get(mood, '✨')
    
    messages = [
        f"aaj ka mood? {emoji}",
        f"{mood.upper()} vibes hai yaar",
        f"waise {time_period} ho gayi..."
    ]
    
    await send_multi_messages(context.bot, update.effective_chat.id, messages)


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forget"""
    user = update.effective_user
    await db.clear_user_memory(user.id)
    
    messages = ["done! 🧹", "sab bhool gayi main", "fresh start? chaloooo ✨"]
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


async def diary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle diary preference"""
    user = update.effective_user
    args = context.args
    
    if not args or args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("Use: /diary on ya /diary off")
        return
    
    value = args[0].lower() == 'on'
    await db.update_preference(user.id, 'diary', value)
    
    status = "ON ✅" if value else "OFF ❌"
    await update.message.reply_text(f"Secret Diary: {status}")


async def user_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's personal stats"""
    user = update.effective_user
    user_data = await db.get_or_create_user(user.id, user.first_name, user.username)
    
    # Messages extract karo
    messages = user_data.get('messages', '[]')
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except:
            messages = []
    if not isinstance(messages, list):
        messages = []
    
    # Preferences extract karo
    prefs = user_data.get('preferences', '{}')
    if isinstance(prefs, str):
        try:
            prefs = json.loads(prefs)
        except:
            prefs = {}
    if not isinstance(prefs, dict):
        prefs = {}
    
    # Created date
    created_at = user_data.get('created_at', 'Unknown')
    if isinstance(created_at, str) and len(created_at) > 10:
        created_at = created_at[:10]
    
    stats_text = f"""
📊 <b>Your Stats</b>

<b>User:</b> {user.first_name}
<b>ID:</b> <code>{user.id}</code>

<b>Conversation:</b>
• Messages: {len(messages)}
• Joined: {created_at}

<b>Preferences:</b>
• Memes: {'✅' if prefs.get('meme_enabled', True) else '❌'}
• Shayari: {'✅' if prefs.get('shayari_enabled', True) else '❌'}
• Diary: {'✅' if prefs.get('diary_enabled', True) else '❌'}
• 🎤 Voice: {'✅' if prefs.get('voice_enabled', False) else '❌'}
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
sirf jab mention karo ya meri message par reply do 💫
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
        await update.message.reply_text("❌ Only admins can do this!")
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
    """Toggle welcome messages"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return
    
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Only admins can do this!")
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
    
    group_data = await db.get_or_create_group(chat.id, chat.title)
    
    # Get settings safely
    settings = group_data.get('settings', {})
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except:
            settings = {}

    # Get cached message count
    cached_count = len(db.get_group_context(chat.id))
    
    stats_text = f"""
📊 <b>Group Statistics</b>

<b>Name:</b> {chat.title}
<b>ID:</b> <code>{chat.id}</code>

<b>Activity:</b>
• Cached Messages: {cached_count}

<b>Settings:</b>
• Geeta Quotes: {'✅' if settings.get('geeta_enabled', True) else '❌'}
• Welcome Msg: {'✅' if settings.get('welcome_enabled', True) else '❌'}
"""
    await update.message.reply_html(stats_text)


async def groupsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show group settings"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text("Yeh command sirf groups ke liye hai!")
        return

    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Only admins can do this!")
        return

    settings = await db.get_group_settings(chat.id)
    
    text = f"""
⚙️ <b>Current Settings</b>

<b>Daily Geeta Quotes:</b> {'✅' if settings.get('geeta_enabled', True) else '❌'}
Command: <code>/setgeeta on/off</code>

<b>Welcome Messages:</b> {'✅' if settings.get('welcome_enabled', True) else '❌'}
Command: <code>/setwelcome on/off</code>
"""
    await update.message.reply_html(text)

# ============================================================================
# ADMIN COMMANDS
# ============================================================================

async def admin_check(update: Update) -> bool:
    """Check if user is bot admin"""
    return update.effective_user.id in Config.ADMIN_IDS


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot stats (admin only)"""
    if not await admin_check(update):
        await update.message.reply_text("Only admins can do this!")
        return
    
    user_count = await db.get_user_count()
    group_count = await db.get_group_count()
    daily_requests = rate_limiter.get_daily_total()
    
    uptime = datetime.now(timezone.utc) - health_server.start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    
    db_status = "🟢 Connected" if db.connected else "🔴 Local Only"
    
    stats_text = f"""
📊 <b>Bot Statistics</b>

<b>Users:</b> {user_count}
<b>Groups:</b> {group_count}
<b>Today's Requests:</b> {daily_requests}

<b>Uptime:</b> {hours}h {minutes}m
<b>Database:</b> {db_status}

<b>Memory:</b>
• Local Users: {len(db.local_users)}
• Local Groups: {len(db.local_groups)}
"""
    await update.message.reply_html(stats_text)


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user list (admin only)"""
    if not await admin_check(update):
        await update.message.reply_text("Only admins can do this!")
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
        return

    args = context.args
    # PIN Check
    if not args or args[0] != Config.BROADCAST_PIN:
        await update.message.reply_html("❌ <b>Wrong PIN!</b>\nUsage: /broadcast PIN Message")
        return

    # Message Content Extraction
    message_text = ' '.join(args[1:]) if len(args) > 1 else None
    reply_msg = update.message.reply_to_message

    if not message_text and not reply_msg:
        await update.message.reply_text("❌ Message likho ya reply karo!")
        return

    status_msg = await update.message.reply_text("📢 fetching database... wait")

    # Users aur Groups dono ko fetch karna
    users = await db.get_all_users()
    groups = await db.get_all_groups()

    # Targets List banana (User IDs + Group Chat IDs)
    targets = []
    
    # Add Users
    for user in users:
        uid = user.get('user_id')
        if uid: targets.append(uid)
        
    # Add Groups
    for group in groups:
        gid = group.get('chat_id')
        if gid: targets.append(gid)

    # Stats setup
    success = 0
    failed = 0
    total = len(targets)
    
    if total == 0:
        await status_msg.edit_text("❌ Database empty hai! Koi users ya groups nahi mile.")
        return

    await status_msg.edit_text(f"📢 Starting Broadcast to {len(users)} Users & {len(groups)} Groups...")

    # Message Content Setup
    final_text = html.escape(message_text) if message_text else None

    # Combined Loop for Users & Groups
    for i, chat_id in enumerate(targets):
        try:
            if reply_msg:
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=reply_msg.message_id
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=final_text,
                    parse_mode=ParseMode.HTML
                )
            success += 1
        except Forbidden:
            failed += 1 # User blocked bot or kicked from group
        except RetryAfter as e:
            logger.warning(f"FloodWait: Sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            failed += 1 
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast error for {chat_id}: {e}")

        # Status Update
        if i % 20 == 0:
            try:
                await status_msg.edit_text(
                    f"📢 Broadcasting...\n"
                    f"🔄 Progress: {i}/{total}\n"
                    f"✅ Success: {success}\n"
                    f"❌ Failed: {failed}"
                )
            except: pass
        
        await asyncio.sleep(0.05) # Small delay

    # Final Report
    await status_msg.edit_text(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"👥 Total Targets: {total}\n"
        f"👤 Users: {len(users)}\n"
        f"🛡Groups: {len(groups)}\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failed/Blocked: {failed}"
    )


async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin commands"""
    if not await admin_check(update):
        await update.message.reply_text("Only admins can do this!")
        return
    
    help_text = """
🔐 <b>Admin Commands</b>

• /adminstats - Bot statistics
• /users - User list
• /broadcast [PIN] [message] - Broadcast
• /adminhelp - This menu
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
            await context.bot.send_message(chat_id=chat_id, text=quote, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.1)
        except:
            pass
    
    logger.info(f"📿 Daily Geeta sent to {sent} groups")


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    """Periodic cleanup"""
    rate_limiter.cleanup_cooldowns()
    await db.cleanup_local_cache()
    logger.info("🧹 Cleanup completed")


# ============================================================================
# 🔴 MAIN MESSAGE HANDLER (FIXED)
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages - Complete Fixed Version"""
    message = update.message
    if not message or not message.text:
        return
        
    user = update.effective_user
    chat = update.effective_chat
    user_message = message.text
    
    # Update activity
    await db.update_user_activity(user.id)
    
    # Ignore commands
    if user_message.startswith('/'):
        return

    is_group = chat.type in ['group', 'supergroup']
    is_private = chat.type == 'private'
    bot_username = Config.BOT_USERNAME
    bot_id = context.bot.id

    # 1. Direct Mention Check (Stay in your lane)
    if 'kavya' in user_message.lower() and 'niyati' not in user_message.lower():
        return # Ignore if user is only calling Kavya

    # 2. Collision Lock (If it's a generic message, decide who speaks)
    if is_group:
        if group_speaker_lock.get(chat.id, {}).get(message.message_id) == "Kavya":
            return # Kavya is already answering this, Niyati stays quiet
        
        # Claim the lock if no one has it and it's an even message ID (Niyati's turn)
        if message.message_id % 2 == 0:
            group_speaker_lock[chat.id] = {message.message_id: "Niyati"}
        elif not should_respond: # If it's not a direct reply/mention, ignore
            return
    
    # ========== ANTI-SPAM CHECK ==========
    if ContentFilter.detect_spam_link(user_message):
        logger.info(f"🚫 Spam link detected from {user.id}")
        return

    # ========== RATE LIMIT CHECK ==========
    allowed, reason = rate_limiter.check(user.id)
    if not allowed:
        if reason == "day":
            await message.reply_text("Aaj ke liye bahut baat ho gayi 😅 Kal milte hain!")
        return

    # ========== SMART REPLY DETECTION (Groups) ==========
    if is_group:
        if is_user_talking_to_others(message, bot_username, bot_id):
            return

    # ========== GROUP FORCE SUB CHECK ==========
    if is_group:
        try:
            fsub_targets = await db.get_group_fsub_targets(chat.id)
            if fsub_targets:
                not_joined = []
                for target in fsub_targets:
                    target_id = target.get('target_chat_id')
                    target_link = target.get('target_link', '')
                    if target_id:
                        try:
                            member = await context.bot.get_chat_member(
                                chat_id=int(target_id), 
                                user_id=user.id
                            )
                            if member.status in ['left', 'kicked']:
                                not_joined.append(target_link)
                        except:
                            pass
                
                if not_joined:
                    buttons = []
                    for i, link in enumerate(not_joined):
                        if link:
                            buttons.append([InlineKeyboardButton(
                                f"Join Channel {i+1}", url=link
                            )])
                    
                    if buttons:
                        reply_markup = InlineKeyboardMarkup(buttons)
                        try:
                            await message.reply_text(
                                "Pehle channels join karo! 👇",
                                reply_markup=reply_markup
                            )
                        except:
                            pass
                        return
        except Exception as e:
            logger.debug(f"FSub check error: {e}")

    # ========== GROUP RESPONSE DECISION ==========
    if is_group:
        db.add_group_message(chat.id, user.first_name, user_message)
        
        should_respond = False
        bot_mention = f"@{bot_username}".lower()
        
        # Check mention or reply
        if bot_mention in user_message.lower():
            should_respond = True
            user_message = re.sub(
                rf'@{bot_username}', '', user_message, flags=re.IGNORECASE
            ).strip()
        elif message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == bot_id:
                should_respond = True
        
        # Random response check
        if not should_respond:
            if random.random() < Config.GROUP_RESPONSE_RATE:
                if rate_limiter.check_group_cooldown(user.id):
                    should_respond = True
                else:
                    return
            else:
                return
        
        if not user_message.strip():
            return
        
        await db.get_or_create_group(chat.id, chat.title)

    if is_private:
        await db.get_or_create_user(user.id, user.first_name, user.username)

    # ========== DISTRESS CHECK ==========
    msg_lower = user_message.lower()
    for keyword in ContentFilter.DISTRESS_KEYWORDS:
        if keyword in msg_lower:
            await message.reply_text(
                "Hey, main tumhare saath hoon. 💛\n"
                "Agar kuch bura feel ho raha hai, please iCall helpline pe call karo: "
                "<b>9152987821</b>\nYa AASRA: <b>9820466726</b>",
                parse_mode=ParseMode.HTML
            )
            return

    # ========== AI RESPONSE ==========
    try:
        await context.bot.send_chat_action(
            chat_id=chat.id, action=ChatAction.TYPING
        )

        context_msgs = await db.get_user_context(user.id) if is_private else []
        mood = Mood.get_random_mood()
        time_period = TimeAware.get_time_period()
        
        # Set current user ID for memory access
        niyati_ai._current_user_id = user.id
        
        responses = await niyati_ai.generate_response(
            user_message=user_message,
            context=context_msgs,
            user_name=user.first_name,
            is_group=is_group,
            mood=mood,
            time_period=time_period,
            user_id=user.id
        )

        # Clean responses
        safe_responses = []
        if responses:
            for r in responses:
                if isinstance(r, dict):
                    safe_responses.append(str(r.get('content', r)))
                elif isinstance(r, str) and r.strip():
                    safe_responses.append(r)
                else:
                    safe_responses.append(str(r))
        responses = safe_responses

        if not responses:
            return

        # ========== SEND MESSAGES ==========
        if is_group and len(responses) > 0:
            if not db.should_send_group_response(chat.id, responses[0]):
                return
            db.record_group_response(chat.id, responses[0])
        
        await send_multi_messages(
            context.bot, 
            chat.id, 
            responses, 
            reply_to=message.message_id if is_group else None, 
            parse_mode=ParseMode.HTML,
            auto_delete=is_group
        )
        
        # ========== VOICE REPLY (Private Only) ==========
        if is_private and responses:
            prefs = await db.get_user_preferences(user.id)
            voice_enabled = prefs.get('voice_enabled', False)
            combined_text = ' '.join(responses)
            
            if voice_generator.should_send_voice(
                combined_text, voice_enabled, is_group=False
            ):
                audio = await voice_generator.generate(
                    combined_text, mood=mood
                )
                if audio:
                    try:
                        await context.bot.send_chat_action(
                            chat_id=chat.id, 
                            action=ChatAction.RECORD_VOICE
                        )
                        await asyncio.sleep(1)
                        await context.bot.send_voice(
                            chat_id=chat.id, voice=audio
                        )
                    except Exception as e:
                        logger.debug(f"Voice send error: {e}")
        
        # ========== SAVE HISTORY (Private Only) ==========
        if is_private:
            await db.save_message(user.id, 'user', user_message)
            combined_response = ' '.join(responses)
            await db.save_message(user.id, 'assistant', combined_response)
            
            # ========== DIARY ENTRY (Extract Important Info) ==========
            try:
                important = await niyati_ai.extract_important_info(
                    user_message, user.id
                )
                if important:
                    await db.add_diary_entry(user.id, important)
            except Exception as e:
                logger.debug(f"Diary extract error: {e}")
                
    except Exception as e:
        logger.error(f"Handler Error: {e}", exc_info=True)


# ============================================================================
# NEW MEMBER HANDLER
# ============================================================================

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining group"""
    if not update.message or not update.message.new_chat_members:
        return

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
        
        # Use SillyTavern style welcome
        mention = f'<a href="tg://user?id={member.id}">{member.first_name}</a>'
        messages = [
            f"Arre! {mention} aaya/aayi group mein 🎉",
            f"Welcome yaar {member.first_name}! Niyati hun main, teri group ki nayi friend ✨"
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
            await update.effective_message.reply_text("oops technical issue 😅 retry karo?")
        except:
            pass


# ============================================================================
# DIARY FEATURE
# ============================================================================

async def send_locked_diary_card(context: ContextTypes.DEFAULT_TYPE):
    """Send locked diary card at night"""
    users = await db.get_active_users(days=Config.DIARY_MIN_ACTIVE_DAYS)
    
    ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
    current_hour = datetime.now(ist).hour
    
    if not (Config.DIARY_ACTIVE_HOURS[0] <= current_hour < Config.DIARY_ACTIVE_HOURS[1]):
        logger.info(f"⏰ Skipping diary (outside {Config.DIARY_ACTIVE_HOURS} IST)")
        return
    
    locked_image = "https://images.unsplash.com/photo-1517639493569-5666a7488662?w=600&q=80&blur=50"
    
    sent_count = 0
    skipped_count = 0
    
    for user in users:
        user_id = user.get('user_id')
        if not user_id: 
            skipped_count += 1
            continue
        
        prefs = await db.get_user_preferences(user_id)
        if not prefs.get('diary_enabled', True):
            skipped_count += 1
            continue
        
        # ✅ FIX: Check if user has ANY chat history today, not just diary entries
        todays_entries = await db.get_todays_diary(user_id)
        user_context = await db.get_user_context(user_id)
        
        # Send diary card if user chatted today (even without explicit diary entries)
        if not todays_entries and not user_context:
            skipped_count += 1
            continue
        
        keyboard = [[InlineKeyboardButton("✨ Unlock Memory ✨", callback_data=f"unlock_diary_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (
            "🔒 <b>Secret Memory Created!</b>\n\n"
            f"Niyati ki Diary - {datetime.now(ist).strftime('%d %b, %Y')}\n"
            "Card unlock karne ke liye tap karein..."
        )

        try:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=locked_image,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            sent_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to send diary card to {user_id}: {e}")
            skipped_count += 1
    
    logger.info(f"🔒 Locked Diary Cards sent to {sent_count} users, skipped {skipped_count}")


async def diary_unlock_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle diary unlock"""
    query = update.callback_query
    user = update.effective_user
    
    callback_data = query.data
    if not callback_data.startswith('unlock_diary_'):
        await query.answer("Invalid action!", show_alert=True)
        return
    
    target_user_id = int(callback_data.replace('unlock_diary_', ''))
    
    if user.id != target_user_id:
        await query.answer("Ye sirf tumhare liye hai! 👀", show_alert=True)
        return
    
    await query.answer("Unlocking memory... 🗝️")
    
    diary_entries = await db.get_todays_diary(user.id)
    
    if not diary_entries:
        diary_text = "Aaj kuch khaas nahi hua... bas aise hi time pass ho gaya. 😴"
    else:
        formatted_entries = []
        for entry in diary_entries:
            content = entry.get('content', '')
            if content:
                formatted_entries.append(f"• {content}")
        
        diary_text = "\n".join(formatted_entries) if formatted_entries else "Aaj ki yaadein... abhi tak blank hai. Kal se shuru karte hain! ✨"
    
    # Generate personal diary entry using AI
    history = await db.get_user_context(user.id)
    user_data = await db.get_or_create_user(user.id, user.first_name, user.username)
    
    prompt = [
        {"role": "system", "content": f"""
        You are Niyati. Write a SHORT personal Diary Entry (max 3-4 lines) about your day chatting with {user.first_name}.
        
        Rules:
        - Start with "Dear Diary..."
        - Format: Hinglish, Emotional, Personal
        - Mention specific things if they exist in context
        - Keep it natural, like a real diary
        - Don't be robotic or generic
        """},
        {"role": "user", "content": f"Today's chat: {str(history)}\nMemories: {diary_text}"}
    ]
    
    ai_diary_text = await niyati_ai._call_gpt(prompt, max_tokens=150)
    
    if ai_diary_text and len(ai_diary_text) > 20:
        final_diary = ai_diary_text
    else:
        final_diary = f"Dear Diary...\n\nAaj {user.first_name} se baat karke acha laga. Kuch yaadein bana li. ✨\n\n{diary_text}"
    
    final_caption = (
        f"🔓 <b>Unlocked: Niyati's Diary</b>\n"
        f"📅 {TimeAware.get_ist_time().strftime('%d %B, %Y')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>{final_diary}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✨ Saved to Memories"
    )

    # Edit message with unlocked diary
    try:
        if query.message:
            unlocked_image = "https://images.unsplash.com/photo-1517639493569-5666a7488662?w=800&q=80"
            
            await query.edit_message_media(
                media=InputMediaPhoto(media=unlocked_image, caption=final_caption, parse_mode=ParseMode.HTML)
            )
    except Exception as e:
        logger.error(f"Diary unlock media edit failed: {e}")
        # Fallback: just send new message
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=final_caption,
                parse_mode=ParseMode.HTML
            )
            try:
                await query.message.delete()
            except:
                pass
        except:
            pass

    # 🔴 THE REACTION LOGIC
    try:
        await asyncio.sleep(8)
        
        # First reaction
        await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
        await asyncio.sleep(1.5)
        
        reaction_1 = "Oye! Tumne meri diary padh li? 😳"
        await context.bot.send_message(chat_id=user.id, text=reaction_1)

        # Second reaction
        await asyncio.sleep(4)
        await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
        await asyncio.sleep(1.5)
        
        reaction_2 = "Pls judge mat karna... wese, tumhe bura to nahi laga na? 👉👈"
        await context.bot.send_message(chat_id=user.id, text=reaction_2)
        
    except Exception as e:
        logger.error(f"Reaction failed: {e}")


async def start_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle start menu button clicks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'about_me':
        about_text = """
🌸 <b>About Niyati</b> 🌸

<b>Name:</b> Niyati
<b>Age:</b> 21
<b>From:</b> Dehradun, India 🏔️
<b>Status:</b> B.Com Final Year Student 📚

Main ek AI hoon, par dil se pure Hindustani! 🇮🇳
Personality: Thodi Sassy 💁‍♀️ Thodi Emotional 🥺 Full Filmy 🎬

<i>"Main perfect nahi hoon, par main REAL hoon!"</i> ✨
"""
        await query.edit_message_caption(
            caption=about_text, parse_mode=ParseMode.HTML
        )
    
    elif query.data == 'help':
        help_text = """
✨ <b>Niyati se kaise baat karein:</b>

• /start - Start fresh
• /help - Help menu
• /mood - Aaj ka mood
• /forget - Memory clear
• /voice on/off - 🎤 Voice toggle
• /say [text] - Text to voice
• /diary on/off - Secret diary

Seedhe message bhejo, main reply karungi! 💫
Group mein @mention karo ya reply do.
"""
        await query.edit_message_caption(
            caption=help_text, parse_mode=ParseMode.HTML
        )

# ============================================================================
# ROUTINE MESSAGE JOB
# ============================================================================

async def routine_message_job(context: ContextTypes.DEFAULT_TYPE):
    """Sends Routine Messages"""
    job_data = context.job.data
    ist = pytz.timezone(Config.DEFAULT_TIMEZONE)
    current_hour = datetime.now(ist).hour

    # DND Check
    if job_data == 'random' and (current_hour >= 23 or current_hour < 8):
        return

    users = await db.get_all_users()
    
    morning_texts = ["Good morning! ☀️", "Uth gaye? ✨", "Morning babe! ❤️", "Subah ho gayi mamu!"]
    night_texts = ["Good night 🌙", "So jao ab 😴", "Gn meri jaan 💖", "Sweet dreams! 🌸"]
    random_texts = ["Kya chal raha hai?", "Bore ho rahi hoon 😅", "Kuch baat karein?"]

    count = 0
    for user in users:
        user_id = user.get('user_id')
        if not user_id: continue

        # ✅ Skip admin-only or bot users
        if job_data == 'random' and random.random() > 0.3: 
            continue

        # ✅ Check if user is active recently (last 2 days)
        last_activity = user.get('last_activity', '')
        if last_activity:
            try:
                last_time = datetime.fromisoformat(
                    last_activity.replace('Z', '+00:00')
                )
                if (datetime.now(timezone.utc) - last_time).days > 2:
                    continue  # Skip inactive users
            except:
                pass

        final_msg = ""
        
        if job_data == 'random' and random.random() > 0.3: 
            continue

        if job_data == 'morning': final_msg = random.choice(morning_texts)
        elif job_data == 'night': final_msg = random.choice(night_texts)
        elif job_data == 'random': final_msg = random.choice(random_texts)

        try:
            await asyncio.sleep(random.uniform(0.5, 2.0))
            await context.bot.send_message(chat_id=user_id, text=final_msg)
            count += 1
        except Exception as e:
            logger.error(f"Routine msg failed for {user_id}: {e}")
        
        if count > 100:
            break

    logger.info(f"Routine Job ({job_data}) sent to {count} users.")


# ============================================================================
# BOT SETUP & JOB SCHEDULING
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
    app.add_handler(CommandHandler("diary", diary_command))
    app.add_handler(CommandHandler("stats", user_stats_command))

    # ✅ ADD VOICE COMMANDS
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("say", say_command))
    app.add_handler(CommandHandler("voices", voices_command))  # Admin only
    
    # Admin group commands
    app.add_handler(CommandHandler("setgeeta", setgeeta_command))
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("groupstats", groupstats_command))
    app.add_handler(CommandHandler("groupsettings", groupsettings_command))
    app.add_handler(CommandHandler("grouphelp", grouphelp_command))
    app.add_handler(CommandHandler("groupinfo", groupinfo_command))

    # Admin private commands
    app.add_handler(CommandHandler("adminstats", admin_stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("adminhelp", adminhelp_command))
    
    # Diary callback
    app.add_handler(CallbackQueryHandler(diary_unlock_callback, pattern="^unlock_diary_"))

    app.add_handler(CallbackQueryHandler(start_button_callback))

    # Message Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error Handler
    app.add_error_handler(error_handler)


# ============================================================================
# POST_SHUTDOWN & POST_INIT
# ============================================================================

async def post_shutdown(application: Application):
    """Bot shutdown cleanup"""
    await health_server.stop()
    await db.close()
    logger.info("😴 Niyati Bot Stopped.")

async def post_init(application: Application):
    """Initialize DB and Schedule Jobs"""
    await db.initialize()
    await health_server.start()
    
    job_queue = application.job_queue
    
    # Schedule all jobs
    
    # 1. Good Morning (India: 08:30 AM IST = 03:00 AM UTC)
    job_queue.run_daily(
        routine_message_job,
        time=time(hour=3, minute=0, second=0),
        data='morning',
        name='daily_morning'
    )

    # 2. Good Night (India: 10:30 PM IST = 05:00 PM UTC)
    job_queue.run_daily(
        routine_message_job,
        time=time(hour=17, minute=0, second=0),
        data='night',
        name='daily_night'
    )

    # 3. Random Check-in (Runs every 4 hours)
    job_queue.run_repeating(
        routine_message_job,
        interval=timedelta(hours=4),
        first=timedelta(seconds=60),
        data='random',
        name='random_checkin'
    )

    # 4. Secret Diary (India: 10:30 PM IST = 5:00 PM UTC)
    job_queue.run_daily(
        send_locked_diary_card,
        time=time(hour=17, minute=0, second=0),
        name='locked_diary_job'
    )

    # 5. Daily Geeta Quotes (Morning: 7 AM IST = 1:30 AM UTC)
    job_queue.run_daily(
        send_daily_geeta,
        time=time(hour=1, minute=30, second=0),
        name='daily_geeta'
    )

    # 6. Cleanup Job (Every hour)
    job_queue.run_repeating(
        cleanup_job,
        interval=timedelta(hours=1),
        first=timedelta(seconds=30),
        name='cleanup'
    )

    logger.info("🚀 Niyati Bot Started with SillyTavern AI!")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    if not ConfigKavya.TELEGRAM_BOT_TOKEN or not ConfigNiyati.TELEGRAM_BOT_TOKEN:
        logger.error("❌ Both Bot Tokens required in .env!")
        return

    # Build both applications
    kavya_app = Application.builder().token(ConfigKavya.TELEGRAM_BOT_TOKEN).build()
    niyati_app = Application.builder().token(ConfigNiyati.TELEGRAM_BOT_TOKEN).build()

    # Setup handlers for both (Make sure you pass the correct app to setup functions)
    setup_kavya_handlers(kavya_app)
    setup_niyati_handlers(niyati_app)

    logger.info("⏳ Initializing Both Bots...")
    
    # Initialize and start both
    await kavya_app.initialize()
    await niyati_app.initialize()
    await kavya_app.start()
    await niyati_app.start()
    
    # Start polling
    await kavya_app.updater.start_polling(drop_pending_updates=True)
    await niyati_app.updater.start_polling(drop_pending_updates=True)
    
    logger.info("🚀 Kavya & Niyati are now running together!")
    
    # Keep the script running
    stop_event = asyncio.Event()
    await stop_event.wait()

if __name__ == "__main__":
    try:
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main()) # Must run using asyncio.run()
    except KeyboardInterrupt:
        logger.info("Bots stopped by user.")
