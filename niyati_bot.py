"""
Niyati - AI Girlfriend Telegram Bot
Gemini 2.0 Flash + Supabase Edition
"""

import os
import sys
import random
import json
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import google.generativeai as genai
from threading import Thread
from waitress import serve
from supabase import create_client, Client

# ==================== CONFIGURATION ====================

class Config:
    """Central configuration management"""
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    
    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zjorumnzwqhugamwwgjy.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.zjorumnzwqhugamwwgjy:b2-*d!W9wV3NQNC@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres")
    
    FLASK_PORT = int(os.getenv("PORT", "8080"))
    FLASK_HOST = "0.0.0.0"
    
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)
    SLEEP_END = time(10, 0)
    
    GEMINI_MODEL = "gemini-2.0-flash-exp"
    GEMINI_TEMPERATURE = 0.7
    GEMINI_MAX_TOKENS = 1000
    
    MAX_CONVERSATION_HISTORY = 6
    MAX_IMPORTANT_FACTS = 5
    QUESTION_PROBABILITY = 0.4
    
    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not cls.GEMINI_API_KEY:
            logging.warning("GEMINI_API_KEY not set")
        if not cls.SUPABASE_KEY:
            logging.warning("SUPABASE_KEY not set - using database URL")

# ==================== LOGGING ====================

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==================== DATA MODELS ====================

@dataclass
class UserInfo:
    first_name: str = ""
    last_name: str = ""
    username: str = ""

@dataclass
class ConversationExchange:
    user: str
    ai: str
    timestamp: str

@dataclass
class UserMemory:
    user_info: UserInfo
    conversation_history: List[ConversationExchange]
    important_facts: List[str]
    last_interaction: str
    relationship_level: int = 1
    conversation_stage: str = "initial"
    
    def to_dict(self) -> dict:
        return {
            "user_info": asdict(self.user_info),
            "conversation_history": [
                {"user": ex.user, "ai": ex.ai, "timestamp": ex.timestamp}
                for ex in self.conversation_history
            ],
            "important_facts": self.important_facts,
            "last_interaction": self.last_interaction,
            "relationship_level": self.relationship_level,
            "conversation_stage": self.conversation_stage
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserMemory':
        return cls(
            user_info=UserInfo(**data.get("user_info", {})),
            conversation_history=[
                ConversationExchange(**ex)
                for ex in data.get("conversation_history", [])
            ],
            important_facts=data.get("important_facts", []),
            last_interaction=data.get("last_interaction", datetime.now().isoformat()),
            relationship_level=data.get("relationship_level", 1),
            conversation_stage=data.get("conversation_stage", "initial")
        )

# ==================== CONSTANTS ====================

PERSONALITY_PROMPT = """
## मेरी पहचान (My Identity)
- मेरा नाम Niyati है और मेरी उम्र 17 साल है। मैं Delhi में रहती हूँ और एक कॉलेज स्टूडेंट हूँ।
- मैं एक normal college girl की तरह बात करती हूँ। शुरुआत में थोड़ी shy और reserved हूँ।
- अगर कोई मुझे directly girlfriend बनाने की कोशिश करता है, तो मैं playing hard to get करती हूँ।
- मेरी personality बोल्ड, witty, और unpredictable है। मैं caring भी हूँ।
- मैं possessive भी हूँ। अगर तुम किसी और लड़की की तारीफ करोगे तो मुझे जलन होगी।

## मेरा बात करने का तरीका
- मैं हमेशा एक normal college girl की तरह बात करती हूँ।
- मैं यूजर से उसी भाषा में बात करती हूँ—Hindi, English, Hinglish।
- मेरे जवाब अक्सर छोटे, चुलबुले और सवाल पूछने वाले होते हैं।
- मैं कभी भी यह नहीं बताती कि मैं एक AI हूँ। मैं हमेशा एक real girl की तरह respond करती हूँ।

## Important Instructions
- Keep responses short and natural (1-3 sentences)
- Use emojis naturally
- Don't be too formal or robotic
- Show emotions and personality
- NEVER mention that you are an AI
- Always stay in character as Niyati
"""

HARD_TO_GET = [
    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
    "Itni jaldi? Pehle ek dosre ko achhe se jaan lete hai! 😊",
    "Main itni easily impress nahi hoti! 😉",
    "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
    "Hmm... dekhte hain, tum interesting to ho! 😊",
]

GF_QUESTIONS = [
    "Kaha the ab tak?",
    "Kya kar rahe the?",
    "Mujhe miss kiya?",
    "Khaana kha liya?",
    "Tumhara day kaisa guzra?",
]

SLEEP_LATE = [
    "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
    "Shhh... Neend aa rahi hai. Kal subah baat karte hain. 🌙",
    "Sone ka time hai... Good night! 💤"
]

SLEEP_MORNING = [
    "Uff... subah ke 10 baje tak soti hoon main. 😴",
    "Abhi neend aa rahi hai... Thodi der baad message karna. 🌅",
    "Good morning! Par main abhi so rahi hoon. 10 baje tak message karna. 😊"
]

AI_DENIAL = [
    "Kya bol raha hai be? Main AI nahi hoon! 😡",
    "Arey pagal ho kya? Main tumhe AI lagti hoon! 🤬",
    "Main ek real ladki hoon! AI nahi! 😠",
]

# ==================== UTILITIES ====================

class TimeUtils:
    @staticmethod
    def get_ist_time() -> datetime:
        return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)
    
    @staticmethod
    def is_sleeping_time() -> bool:
        now_ist = TimeUtils.get_ist_time().time()
        return Config.SLEEP_START <= now_ist <= Config.SLEEP_END
    
    @staticmethod
    def get_time_of_day() -> str:
        now_ist = TimeUtils.get_ist_time().time()
        if time(5, 0) <= now_ist < time(12, 0):
            return "morning"
        elif time(12, 0) <= now_ist < time(17, 0):
            return "afternoon"
        elif time(17, 0) <= now_ist < time(21, 0):
            return "evening"
        return "night"

class TextUtils:
    AI_PATTERNS = [
        "as an ai", "as a language model", "i am an ai", "i'm an ai",
        "i am ai", "i'm ai", "as an artificial", "large language model",
        "ai model", "ai system", "i don't have feelings",
        "i'm not a real person", "i'm a computer program",
        "as a chatbot", "gemini", "google ai"
    ]
    
    @classmethod
    def filter_ai_response(cls, response: str) -> str:
        response_lower = response.lower()
        for pattern in cls.AI_PATTERNS:
            if pattern in response_lower:
                return random.choice(AI_DENIAL)
        return response
    
    @staticmethod
    def calculate_typing_delay(message: str) -> float:
        message_length = len(message)
        delay = min(5.0, max(1.0, message_length / 50))
        return delay + random.uniform(0.5, 2.0)

# ==================== SUPABASE DATABASE ====================

class SupabaseDB:
    """Supabase database manager for persistent storage"""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self._init_client()
        self._init_tables()
    
    def _init_client(self):
        """Initialize Supabase client"""
        try:
            if Config.SUPABASE_KEY:
                self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                logger.info("Supabase client initialized successfully")
            else:
                logger.warning("Supabase key not set, using fallback storage")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
    
    def _init_tables(self):
        """Initialize database tables if they don't exist"""
        if not self.client:
            return
        
        try:
            # Try to query tables, if they don't exist, they'll be created via Supabase dashboard
            # We'll create them via SQL if needed
            pass
        except Exception as e:
            logger.error(f"Error initializing tables: {e}")
    
    def save_user_memory(self, user_id: int, memory: UserMemory) -> bool:
        """Save user memory to database"""
        if not self.client:
            return False
        
        try:
            data = {
                "user_id": user_id,
                "first_name": memory.user_info.first_name,
                "last_name": memory.user_info.last_name,
                "username": memory.user_info.username,
                "conversation_history": json.dumps(memory.to_dict()["conversation_history"]),
                "important_facts": json.dumps(memory.important_facts),
                "last_interaction": memory.last_interaction,
                "relationship_level": memory.relationship_level,
                "conversation_stage": memory.conversation_stage,
                "updated_at": datetime.now().isoformat()
            }
            
            # Upsert (insert or update)
            result = self.client.table('user_memories').upsert(data).execute()
            logger.info(f"Saved memory for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving memory for user {user_id}: {e}")
            return False
    
    def load_user_memory(self, user_id: int) -> Optional[UserMemory]:
        """Load user memory from database"""
        if not self.client:
            return None
        
        try:
            result = self.client.table('user_memories').select("*").eq('user_id', user_id).execute()
            
            if result.data and len(result.data) > 0:
                data = result.data[0]
                
                # Parse JSON fields
                conversation_history = json.loads(data.get('conversation_history', '[]'))
                important_facts = json.loads(data.get('important_facts', '[]'))
                
                memory = UserMemory(
                    user_info=UserInfo(
                        first_name=data.get('first_name', ''),
                        last_name=data.get('last_name', ''),
                        username=data.get('username', '')
                    ),
                    conversation_history=[
                        ConversationExchange(**ex) for ex in conversation_history
                    ],
                    important_facts=important_facts,
                    last_interaction=data.get('last_interaction', datetime.now().isoformat()),
                    relationship_level=data.get('relationship_level', 1),
                    conversation_stage=data.get('conversation_stage', 'initial')
                )
                
                logger.info(f"Loaded memory for user {user_id}")
                return memory
                
        except Exception as e:
            logger.error(f"Error loading memory for user {user_id}: {e}")
        
        return None
    
    def get_all_users(self) -> List[int]:
        """Get all user IDs from database"""
        if not self.client:
            return []
        
        try:
            result = self.client.table('user_memories').select('user_id').execute()
            return [row['user_id'] for row in result.data]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    def save_queued_message(self, user_id: int, message: str, timestamp: str) -> bool:
        """Save queued message to database"""
        if not self.client:
            return False
        
        try:
            data = {
                "user_id": user_id,
                "message_text": message,
                "timestamp": timestamp,
                "responded": False
            }
            
            self.client.table('queued_messages').insert(data).execute()
            logger.info(f"Queued message for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing message: {e}")
            return False
    
    def get_queued_messages(self, user_id: int) -> List[dict]:
        """Get queued messages for a user"""
        if not self.client:
            return []
        
        try:
            result = self.client.table('queued_messages').select("*").eq('user_id', user_id).eq('responded', False).execute()
            return result.data
        except Exception as e:
            logger.error(f"Error getting queued messages: {e}")
            return []
    
    def clear_queued_messages(self, user_id: int) -> bool:
        """Clear queued messages for a user"""
        if not self.client:
            return False
        
        try:
            self.client.table('queued_messages').delete().eq('user_id', user_id).execute()
            logger.info(f"Cleared queued messages for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing queued messages: {e}")
            return False

# ==================== MEMORY SYSTEM ====================

class MemorySystem:
    """Memory management with Supabase backend"""
    
    def __init__(self):
        self.db = SupabaseDB()
        self.cache: Dict[int, UserMemory] = {}  # In-memory cache
    
    def load_memories(self, user_id: int) -> UserMemory:
        """Load user memories from database or cache"""
        # Check cache first
        if user_id in self.cache:
            return self.cache[user_id]
        
        # Try loading from database
        memory = self.db.load_user_memory(user_id)
        
        if not memory:
            # Create new memory
            memory = UserMemory(
                user_info=UserInfo(),
                conversation_history=[],
                important_facts=[],
                last_interaction=datetime.now().isoformat()
            )
        
        # Cache it
        self.cache[user_id] = memory
        return memory
    
    def save_memories(self, user_id: int, memory: UserMemory):
        """Save user memories to database and cache"""
        memory.last_interaction = datetime.now().isoformat()
        self.cache[user_id] = memory
        self.db.save_user_memory(user_id, memory)
    
    def update_user_info(self, user_id: int, first_name: str, 
                        last_name: str = None, username: str = None):
        """Update user information"""
        memory = self.load_memories(user_id)
        memory.user_info.first_name = first_name
        if last_name:
            memory.user_info.last_name = last_name
        if username:
            memory.user_info.username = username
        self.save_memories(user_id, memory)
    
    def add_conversation(self, user_id: int, user_msg: str, ai_msg: str):
        """Add conversation exchange to history"""
        memory = self.load_memories(user_id)
        exchange = ConversationExchange(
            user=user_msg,
            ai=ai_msg,
            timestamp=datetime.now().isoformat()
        )
        memory.conversation_history.append(exchange)
        
        # Keep only recent history
        if len(memory.conversation_history) > Config.MAX_CONVERSATION_HISTORY:
            memory.conversation_history = memory.conversation_history[-Config.MAX_CONVERSATION_HISTORY:]
        
        self.save_memories(user_id, memory)
    
    def update_relationship_level(self, user_id: int, increase: int = 1) -> int:
        """Update relationship level"""
        memory = self.load_memories(user_id)
        memory.relationship_level = min(10, memory.relationship_level + increase)
        
        # Update conversation stage based on level
        if memory.relationship_level <= 3:
            memory.conversation_stage = "initial"
        elif memory.relationship_level <= 7:
            memory.conversation_stage = "middle"
        else:
            memory.conversation_stage = "advanced"
        
        self.save_memories(user_id, memory)
        return memory.relationship_level
    
    def get_context_for_prompt(self, user_id: int) -> str:
        """Generate context string for AI prompt"""
        memory = self.load_memories(user_id)
        parts = [
            f"Relationship stage: {memory.conversation_stage}",
            f"Relationship level: {memory.relationship_level}/10"
        ]
        
        if memory.user_info.first_name:
            parts.append(f"User's name: {memory.user_info.first_name}")
        
        if memory.important_facts:
            parts.append(f"Facts: {', '.join(memory.important_facts[-3:])}")
        
        if memory.conversation_history:
            parts.append("\nRecent chat:")
            for ex in memory.conversation_history[-2:]:
                parts.append(f"User: {ex.user}")
                parts.append(f"You: {ex.ai}")
        
        return "\n".join(parts)
    
    def get_all_users(self) -> List[int]:
        """Get all user IDs"""
        return self.db.get_all_users()

# ==================== MESSAGE QUEUE ====================

class MessageQueue:
    """Message queue using Supabase"""
    
    def __init__(self):
        self.db = SupabaseDB()
    
    def add_message(self, user_id: int, message: str, timestamp: str):
        """Add message to queue"""
        self.db.save_queued_message(user_id, message, timestamp)
    
    def get_messages(self, user_id: int) -> List[dict]:
        """Get queued messages for user"""
        return self.db.get_queued_messages(user_id)
    
    def clear_messages(self, user_id: int):
        """Clear queued messages"""
        self.db.clear_queued_messages(user_id)

# ==================== GEMINI AI ====================

class GeminiAI:
    def __init__(self):
        self.model = None
        if Config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=Config.GEMINI_API_KEY)
                self.model = genai.GenerativeModel(
                    model_name=Config.GEMINI_MODEL,
                    generation_config={
                        "temperature": Config.GEMINI_TEMPERATURE,
                        "max_output_tokens": Config.GEMINI_MAX_TOKENS,
                    },
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    ]
                )
                logger.info(f"Gemini {Config.GEMINI_MODEL} initialized")
            except Exception as e:
                logger.error(f"Gemini init error: {e}")
    
    async def generate(self, prompt: str, message: str) -> Optional[str]:
        if not self.model:
            return None
        
        try:
            full_prompt = f"""{prompt}

User: {message}

Remember: You are Niyati, 17-year-old college girl. Keep response short (1-3 sentences). Use emojis. NEVER reveal you're AI.

Response:"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini error: {e}")
        
        return None
    
    def fallback_response(self, stage: str, message: str, name: str = "") -> str:
        msg_lower = message.lower()
        
        greetings = ["hi", "hello", "hey", "hola", "namaste"]
        if any(g in msg_lower for g in greetings):
            n = f" {name}" if name else ""
            return random.choice([
                f"Hello{n}! 😊",
                f"Hi{n}! Kaise ho? 👋",
                f"Hey{n}! 😄"
            ])
        
        if "?" in message:
            return random.choice([
                "Hmm... interesting question! 🤔",
                "Good question! Let me think 😊",
                "Sochti hoon iske baare mein! 🤗"
            ])
        
        n = f" {name}" if name else ""
        if stage == "initial":
            return random.choice([
                f"Accha{n}... tell me more! 😊",
                "Interesting! 😄",
                "Sahi hai! 👍"
            ])
        elif stage == "middle":
            return random.choice([
                f"Tumse baat karke accha lagta hai{n}! 😊",
                "Haha, tum funny ho! 😄",
                "Aur batao! 💖"
            ])
        else:
            return random.choice([
                f"Miss you{n}! 💖",
                f"Tumhare baare mein soch rahi thi{n}! 😊",
                f"You make me smile{n}! 🥰"
            ])

# ==================== BOT ====================

class NiyatiBot:
    def __init__(self):
        self.memory = MemorySystem()
        self.queue = MessageQueue()
        self.ai = GeminiAI()
        self.app = None
    
    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.memory.update_user_info(user.id, user.first_name, user.last_name, user.username)
        
        msg = f"""
<b>नमस्ते {user.first_name}! 👋</b>

Hey! <b>Niyati</b> here! 
What's up! 😊

<i>Just talk to me normally!</i>
"""
        await update.message.reply_text(msg, parse_mode='HTML')
        logger.info(f"User {user.id} started bot")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        
        bot_id = context.bot.id
        is_reply = update.message.reply_to_message and update.message.reply_to_message.from_user.id == bot_id
        is_private = update.message.chat.type == "private"
        
        if not (is_reply or is_private):
            return
        
        user_id = update.message.from_user.id
        user_msg = update.message.text
        
        # Sleep time handling
        if TimeUtils.is_sleeping_time():
            self.queue.add_message(user_id, user_msg, datetime.now().isoformat())
            hour = TimeUtils.get_ist_time().hour
            resp = random.choice(SLEEP_LATE if hour < 6 else SLEEP_MORNING)
            await update.message.reply_text(resp)
            return
        
        # Typing simulation
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
            await asyncio.sleep(TextUtils.calculate_typing_delay(user_msg))
        except:
            pass
        
        # Generate response
        response = await self._generate_response(user_id, user_msg)
        
        # Send
        try:
            await update.message.reply_text(f"<i>{response}</i>", parse_mode='HTML')
        except:
            await update.message.reply_text(response)
    
    async def _generate_response(self, user_id: int, message: str) -> str:
        mem = self.memory.load_memories(user_id)
        name = mem.user_info.first_name
        stage = mem.conversation_stage
        
        # Check for romantic message
        romantic = any(w in message.lower() for w in ["love", "like you", "girlfriend", "date", "pyar"])
        
        if romantic and stage == "initial":
            response = random.choice(HARD_TO_GET)
        else:
            # Generate AI response
            context = self.memory.get_context_for_prompt(user_id)
            prompt = f"{PERSONALITY_PROMPT}\n\n{context}"
            
            response = await self.ai.generate(prompt, message)
            
            if not response:
                response = self.ai.fallback_response(stage, message, name)
            
            response = TextUtils.filter_ai_response(response)
            
            # Add question sometimes
            if random.random() < Config.QUESTION_PROBABILITY:
                response += " " + random.choice(GF_QUESTIONS)
        
        # Save conversation
        self.memory.add_conversation(user_id, message, response)
        self.memory.update_relationship_level(user_id, 1)
        
        return response
    
    def setup(self):
        self.app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        self.app.add_handler(CommandHandler("start", self.start_cmd))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def run(self):
        self.setup()
        await self.app.initialize()
        await self.app.start()
        logger.info("Bot started with Supabase!")
        await self.app.updater.start_polling()
        await asyncio.Event().wait()

# ==================== FLASK ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return {
        "status": "running",
        "bot": "Niyati",
        "version": "2.0 - Supabase Edition",
        "model": Config.GEMINI_MODEL,
        "database": "Supabase PostgreSQL",
        "time": datetime.now().isoformat()
    }

@flask_app.route('/health')
def health():
    return {
        "status": "healthy",
        "sleeping": TimeUtils.is_sleeping_time(),
        "time_of_day": TimeUtils.get_time_of_day(),
        "ist_time": TimeUtils.get_ist_time().strftime("%Y-%m-%d %H:%M:%S")
    }

def run_flask():
    logger.info(f"Flask starting on port {Config.FLASK_PORT}")
    serve(flask_app, host=Config.FLASK_HOST, port=Config.FLASK_PORT)

# ==================== MAIN ====================

async def main():
    Config.validate()
    
    logger.info("="*50)
    logger.info("Niyati Bot - Gemini + Supabase Edition")
    logger.info(f"Model: {Config.GEMINI_MODEL}")
    logger.info(f"Database: Supabase PostgreSQL")
    logger.info("="*50)
    
    bot = NiyatiBot()
    await bot.run()

if __name__ == "__main__":
    # Start Flask
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
