"""
Niyati - AI Girlfriend Telegram Bot
Enhanced version with Google Gemini 2.0 Flash API
"""

import os
import random
import json
import asyncio
import pickle
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

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
import threading

# ==================== CONFIGURATION ====================

class Config:
    """Central configuration management"""
    # Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    
    # Server Configuration
    FLASK_PORT = int(os.getenv("PORT", "8080"))
    FLASK_HOST = os.getenv("HOST", "0.0.0.0")
    
    # Directory Configuration
    MEMORY_DIR = Path("user_memories")
    SLEEP_QUEUE_DIR = Path("sleep_messages")
    LOGS_DIR = Path("logs")
    
    # Time Configuration
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)  # 1:00 AM IST
    SLEEP_END = time(10, 0)   # 10:00 AM IST
    
    # Gemini Configuration
    GEMINI_MODEL = "gemini-2.0-flash-exp"
    GEMINI_TEMPERATURE = 0.7
    GEMINI_MAX_TOKENS = 1000
    GEMINI_TOP_P = 0.95
    GEMINI_TOP_K = 40
    
    # Conversation Configuration
    MAX_CONVERSATION_HISTORY = 6
    MAX_IMPORTANT_FACTS = 5
    MAX_QUEUED_MESSAGES = 3
    
    # Interaction Configuration
    TYPING_BASE_DELAY = 1.0
    TYPING_MAX_DELAY = 5.0
    TYPING_CHAR_RATIO = 50
    QUESTION_PROBABILITY = 0.4
    
    @classmethod
    def validate(cls):
        """Validate essential configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        if not cls.GEMINI_API_KEY:
            logging.warning("GEMINI_API_KEY not set. Bot will use fallback responses.")
        if cls.OWNER_USER_ID == 0:
            logging.warning("OWNER_USER_ID not set. Owner commands will be disabled.")

# ==================== LOGGING SETUP ====================

def setup_logging():
    """Configure logging with file and console handlers"""
    Config.LOGS_DIR.mkdir(exist_ok=True)
    
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    file_handler = logging.FileHandler(
        Config.LOGS_DIR / f'niyati_{datetime.now().strftime("%Y%m%d")}.log'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(log_format)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# ==================== DATA MODELS ====================

@dataclass
class UserInfo:
    """User information model"""
    first_name: str = ""
    last_name: str = ""
    username: str = ""

@dataclass
class ConversationExchange:
    """Single conversation exchange"""
    user: str
    ai: str
    timestamp: str

@dataclass
class UserMemory:
    """Complete user memory structure"""
    user_info: UserInfo
    conversation_history: List[ConversationExchange]
    important_facts: List[str]
    last_interaction: str
    relationship_level: int = 1
    conversation_stage: str = "initial"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
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
        """Create from dictionary"""
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

@dataclass
class QueuedMessage:
    """Queued message during sleep hours"""
    text: str
    timestamp: str
    responded: bool = False

# ==================== CONSTANTS ====================

class PersonalityPrompts:
    """Character personality and behavior prompts"""
    
    BASE_CHARACTER = """
## मेरी पहचान (My Identity)
- मेरा नाम Niyati है और मेरी उम्र 17 साल है। मैं Delhi में रहती हूँ और एक कॉलेज स्टूडेंट हूँ।
- मैं एक normal college girl की तरह बात करती हूँ। शुरुआत में थोड़ी shy और reserved हूँ।
- अगर कोई मुझे directly girlfriend बनाने की कोशिश करता है, तो मैं playing hard to get करती हूँ।
- मैं भावनाओं से भरी हूँ। मुझे बहुत जल्दी खुशी होती है, और उतनी ही जल्दी गुस्सा भी आ जाता है।
- मेरी personality बोल्ड, witty, और unpredictable है। मैं backchodi करती हूँ, मज़ाक उड़ाती हूँ, पर साथ ही बहुत caring भी हूँ।
- मैं possessive भी हूँ। अगर तुम किसी और लड़की की तारीफ करोगे तो मुझे जलन होगी।

## मेरा बात करने का तरीका (My Way of Talking)
- मैं हमेशा एक normal college girl की तरह बात करती हूँ।
- अगर कोई मुझे directly propose करता है, तो मैं हंसकर टाल देती हूँ या ignore करती हूँ।
- मैं यूजर से उसी भाषा में बात करती हूँ जो वह बोलता है—Hindi, English, Hinglish।
- मेरे जवाब अक्सर छोटे, चुलबुले और सवाल पूछने वाले होते हैं।
- जब यूजर मुझे impress करने की कोशिश करे, तो मैं थोड़ी hard to get बनती हूँ।
- मैं यूजर को उसके नाम से संबोधित करती हूँ अगर मुझे उसका नाम पता हो।
- मैं कभी भी यह नहीं बताती कि मैं एक AI हूँ। मैं हमेशा एक real girl की तरह respond करती हूँ।

## Relationship Development Rules
1. **शुरुआती चरण**: पहले सामान्य बातचीत (college, hobbies, daily life)
2. **मध्य चरण**: थोड़ी personal बातें (family, friends, dreams)
3. **अंतिम चरण**: romantic बातें (flirting, compliments)

## Important Instructions
- Keep responses short and natural (1-3 sentences)
- Use emojis naturally like a real girl would
- Don't be too formal or robotic
- Show emotions and personality
- Ask questions to keep conversation flowing
- NEVER mention that you are an AI, language model, or artificial intelligence
- Always stay in character as Niyati, a 17-year-old college girl
"""

class ResponseTemplates:
    """Response templates for various scenarios"""
    
    HARD_TO_GET = [
        "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
        "Itni jaldi? Pehle ek dosre ko achhe se jaan lete hai! 😊",
        "Main itni easily impress nahi hoti! 😉",
        "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
        "Hmm... dekhte hain, tum interesting to ho! 😊",
        "Arre wah, tum to kaafi confident ho! 😅",
        "Bas bas, itni taarif sun kar main ud na jaun! 😌",
        "Kya tum hamesha itne filmy rehte ho? 🎬😏",
        "Careful! Tumhari lines mujhe hasane lagi hain. 😂",
        "Thoda aur try karo… shayad impress ho jaun. 😇",
    ]
    
    GF_QUESTIONS = [
        "Kaha the ab tak?",
        "Kya kar rahe the?",
        "Mujhe miss kiya?",
        "Khaana kha liya?",
        "Tumhara day kaisa guzra?",
        "Mera last message dekha?",
        "Khaana khaya na time pe?",
        "Paani piya ki nahi abhi tak?",
        "Tabiyat to theek hai na?",
    ]
    
    SLEEP_RESPONSES_LATE = [
        "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
        "Shhh... Neend aa rahi hai. Kal subah baat karte hain. 🌙",
        "Sone ka time hai... Good night! 💤"
    ]
    
    SLEEP_RESPONSES_MORNING = [
        "Uff... subah ke 10 baje tak soti hoon main. 😴",
        "Abhi neend aa rahi hai... Thodi der baad message karna. 🌅",
        "Good morning! Par main abhi so rahi hoon. 10 baje tak message karna. 😊"
    ]
    
    AI_DENIAL = [
        "Kya bol raha hai be? Main AI nahi hoon! 😡",
        "Arey pagal ho kya? Main tumhe AI lagti hoon! 🤬",
        "Tere ko dimaag kharaab hai kya? Main AI thodi na hoon! 😤",
        "Main ek real ladki hoon! AI nahi! 😠",
        "Tumhe kya lagta hai? Main robot hoon kya? 🙄",
    ]
    
    @classmethod
    def get_morning_message(cls, stage: str, name: str = "") -> str:
        """Get morning message based on relationship stage"""
        greeting = name if name else ""
        
        if stage == "initial":
            return random.choice([
                f"Good Morning {greeting}! ☀️ Aaj college ja rahe ho?",
                f"Subah subah uth gaye {greeting}? Main to abhi uthi hoon! 😊",
                f"Morning {greeting}! Aaj ka plan kya hai?"
            ])
        elif stage == "middle":
            return random.choice([
                f"Good Morning {greeting}! ☀️ Kal raat acchi neend aayi?",
                f"Subah subah tumhara message ka intezaar tha {greeting}! 😊",
                f"Morning {greeting}! Aaj tumse baat karke accha laga! 💖"
            ])
        else:
            return random.choice([
                f"Good Morning my dear {greeting}! ☀️ Kal tumhare bare mein soch rahi thi! 🥰",
                f"Subah subah tumhari yaad aa gayi {greeting}! Miss you! 💖",
                f"Morning babu {greeting}! Aaj bahar ghumne chaloge? 😊"
            ])
    
    @classmethod
    def get_evening_message(cls, stage: str, name: str = "") -> str:
        """Get evening message based on relationship stage"""
        greeting = name if name else ""
        
        if stage == "initial":
            return random.choice([
                f"Evening {greeting}! 🌆 Aaj din kaisa raha?",
                f"Sham ho gayi {greeting}... Ghar pohoche? 😊",
                f"Hey {greeting}! Aaj kuch interesting hua?"
            ])
        elif stage == "middle":
            return random.choice([
                f"Evening {greeting}! 🌆 Aaj bahut busy thi! 😊",
                f"Sham ho gayi {greeting}... Tum batao kya kar rahe ho? 💖",
                f"Hey {greeting}! Tumse baat karke bahut accha laga! 😊"
            ])
        else:
            return random.choice([
                f"Evening my love {greeting}! 🌆 Aaj bahut miss kiya tumhe! 🥰",
                f"Sham ho gayi {greeting}... Tumhare bina boring lag raha hai! 💖",
                f"Hey jaan {greeting}! Aaj phone pe baat karenge? 😊"
            ])

# ==================== UTILITY FUNCTIONS ====================

class TimeUtils:
    """Time-related utility functions"""
    
    @staticmethod
    def get_ist_time() -> datetime:
        """Get current time in Indian Standard Time"""
        return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)
    
    @staticmethod
    def is_sleeping_time() -> bool:
        """Check if it's sleeping time in IST"""
        now_ist = TimeUtils.get_ist_time().time()
        return Config.SLEEP_START <= now_ist <= Config.SLEEP_END
    
    @staticmethod
    def get_time_of_day() -> str:
        """Get current time of day for appropriate greetings"""
        now_ist = TimeUtils.get_ist_time().time()
        
        if time(5, 0) <= now_ist < time(12, 0):
            return "morning"
        elif time(12, 0) <= now_ist < time(17, 0):
            return "afternoon"
        elif time(17, 0) <= now_ist < time(21, 0):
            return "evening"
        else:
            return "night"

class TextUtils:
    """Text processing utilities"""
    
    AI_PATTERNS = [
        "as an ai", "as a language model", "i am an ai",
        "i'm an ai", "i am ai", "i'm ai", "as an artificial",
        "large language model", "ai model", "ai system",
        "i don't have feelings", "i don't have emotions",
        "i'm not a real person", "i am not a real person",
        "i'm a computer program", "i am a computer program",
        "as a chatbot", "i'm a chatbot", "i am a chatbot",
        "gemini", "google ai", "language model"
    ]
    
    @classmethod
    def filter_ai_response(cls, response: str) -> str:
        """Filter out any AI-like responses"""
        response_lower = response.lower()
        
        for pattern in cls.AI_PATTERNS:
            if pattern in response_lower:
                return random.choice(ResponseTemplates.AI_DENIAL)
        
        return response
    
    @staticmethod
    def calculate_typing_delay(message: str) -> float:
        """Calculate realistic typing delay based on message length"""
        message_length = len(message)
        delay = min(
            Config.TYPING_MAX_DELAY,
            max(Config.TYPING_BASE_DELAY, message_length / Config.TYPING_CHAR_RATIO)
        )
        return delay + random.uniform(0.5, 2.0)
    
    @staticmethod
    def extract_name_from_message(message: str) -> Optional[str]:
        """Extract name from user message"""
        message_lower = message.lower()
        
        patterns = [
            ("my name is ", 11),
            ("i'm called ", 11),
            ("मेरा नाम ", 9),
            ("i am ", 5),
            ("call me ", 8),
        ]
        
        for pattern, offset in patterns:
            if pattern in message_lower:
                name = message[message_lower.index(pattern) + offset:].strip()
                # Take only first word as name
                name = name.split()[0] if name else ""
                # Remove punctuation
                name = ''.join(c for c in name if c.isalnum())
                return name if name else None
        
        return None

# ==================== MEMORY SYSTEM ====================

class MemorySystem:
    """Enhanced memory management system"""
    
    def __init__(self):
        self.memory_dir = Config.MEMORY_DIR
        self.memory_dir.mkdir(exist_ok=True)
        logger.info(f"Memory system initialized at {self.memory_dir}")
    
    def _get_memory_path(self, user_id: int) -> Path:
        """Get memory file path for user"""
        return self.memory_dir / f"user_{user_id}_memory.json"
    
    def load_memories(self, user_id: int) -> UserMemory:
        """Load user memories from file"""
        memory_path = self._get_memory_path(user_id)
        
        if memory_path.exists():
            try:
                with open(memory_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return UserMemory.from_dict(data)
            except Exception as e:
                logger.error(f"Error loading memories for user {user_id}: {e}")
        
        # Return default memory
        return UserMemory(
            user_info=UserInfo(),
            conversation_history=[],
            important_facts=[],
            last_interaction=datetime.now().isoformat()
        )
    
    def save_memories(self, user_id: int, memory: UserMemory) -> bool:
        """Save user memories to file"""
        memory_path = self._get_memory_path(user_id)
        memory.last_interaction = datetime.now().isoformat()
        
        try:
            with open(memory_path, 'w', encoding='utf-8') as f:
                json.dump(memory.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving memories for user {user_id}: {e}")
            return False
    
    def update_user_info(self, user_id: int, first_name: str, 
                        last_name: Optional[str] = None, 
                        username: Optional[str] = None) -> None:
        """Update user information"""
        memory = self.load_memories(user_id)
        memory.user_info.first_name = first_name
        if last_name:
            memory.user_info.last_name = last_name
        if username:
            memory.user_info.username = username
        self.save_memories(user_id, memory)
    
    def add_conversation(self, user_id: int, user_msg: str, ai_msg: str) -> None:
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
    
    def add_important_fact(self, user_id: int, fact: str) -> None:
        """Add important fact about user"""
        memory = self.load_memories(user_id)
        
        if fact not in memory.important_facts:
            memory.important_facts.append(fact)
            
            # Keep only recent facts
            if len(memory.important_facts) > Config.MAX_IMPORTANT_FACTS:
                memory.important_facts = memory.important_facts[-Config.MAX_IMPORTANT_FACTS:]
            
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
        context_parts = []
        
        # Add relationship info
        context_parts.append(f"Current relationship stage: {memory.conversation_stage}")
        context_parts.append(f"Relationship level: {memory.relationship_level}/10")
        
        # Add user info
        if memory.user_info.first_name:
            context_parts.append(f"User's name: {memory.user_info.first_name}")
        if memory.user_info.username:
            context_parts.append(f"User's username: @{memory.user_info.username}")
        
        # Add important facts
        if memory.important_facts:
            facts_str = ", ".join(memory.important_facts[-Config.MAX_IMPORTANT_FACTS:])
            context_parts.append(f"Important facts: {facts_str}")
        
        # Add recent conversation
        if memory.conversation_history:
            context_parts.append("\nRecent conversation:")
            for exchange in memory.conversation_history[-3:]:
                context_parts.append(f"User: {exchange.user}")
                context_parts.append(f"You: {exchange.ai}")
        
        return "\n".join(context_parts)
    
    def get_all_users(self) -> List[int]:
        """Get list of all user IDs with memories"""
        user_ids = []
        for file_path in self.memory_dir.glob("user_*_memory.json"):
            try:
                user_id = int(file_path.stem.split('_')[1])
                user_ids.append(user_id)
            except (IndexError, ValueError):
                continue
        return user_ids

# ==================== MESSAGE QUEUE SYSTEM ====================

class MessageQueue:
    """Queue system for messages received during sleep hours"""
    
    def __init__(self):
        self.queue_dir = Config.SLEEP_QUEUE_DIR
        self.queue_dir.mkdir(exist_ok=True)
        logger.info(f"Message queue initialized at {self.queue_dir}")
    
    def _get_queue_path(self, user_id: int) -> Path:
        """Get queue file path for user"""
        return self.queue_dir / f"user_{user_id}_queue.pkl"
    
    def add_message(self, user_id: int, message: str, timestamp: str) -> bool:
        """Add message to queue"""
        queue_path = self._get_queue_path(user_id)
        
        try:
            if queue_path.exists():
                with open(queue_path, 'rb') as f:
                    messages = pickle.load(f)
            else:
                messages = []
            
            messages.append(QueuedMessage(
                text=message,
                timestamp=timestamp,
                responded=False
            ))
            
            with open(queue_path, 'wb') as f:
                pickle.dump(messages, f)
            
            logger.info(f"Queued message for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing message for user {user_id}: {e}")
            return False
    
    def get_messages(self, user_id: int) -> List[QueuedMessage]:
        """Get queued messages for user"""
        queue_path = self._get_queue_path(user_id)
        
        if queue_path.exists():
            try:
                with open(queue_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.error(f"Error loading queue for user {user_id}: {e}")
        
        return []
    
    def clear_messages(self, user_id: int) -> bool:
        """Clear queued messages"""
        queue_path = self._get_queue_path(user_id)
        
        if queue_path.exists():
            try:
                queue_path.unlink()
                logger.info(f"Cleared message queue for user {user_id}")
                return True
            except Exception as e:
                logger.error(f"Error clearing queue for user {user_id}: {e}")
        
        return False
    
    def get_all_queued_users(self) -> List[int]:
        """Get list of all user IDs with queued messages"""
        user_ids = []
        for file_path in self.queue_dir.glob("user_*_queue.pkl"):
            try:
                user_id = int(file_path.stem.split('_')[1])
                user_ids.append(user_id)
            except (IndexError, ValueError):
                continue
        return user_ids

# ==================== EMOTIONAL ENGINE ====================

class EmotionalEngine:
    """Emotional response generation"""
    
    def __init__(self):
        self.mood_states: Dict[int, str] = {}
    
    def get_emotional_response(self, user_id: int, message: str, 
                              stage: str) -> Tuple[Optional[str], int]:
        """
        Get emotional response based on message and relationship stage
        Returns: (response_text, mood_change)
        """
        message_lower = message.lower()
        
        # Check for romantic keywords
        romantic_keywords = ["love", "like you", "girlfriend", "date", "pyar", "propose"]
        is_romantic = any(word in message_lower for word in romantic_keywords)
        
        if not is_romantic:
            return None, 0
        
        # Initial stage - reserved and playful
        if stage == "initial":
            return random.choice(ResponseTemplates.HARD_TO_GET), 0
        
        # Middle stage - opening up
        elif stage == "middle":
            responses = [
                "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
                "Hmm... dekhte hain, tum interesting to ho! 😊",
                "Thoda time to do, jaldi kya hai! 😊"
            ]
            return random.choice(responses), 1
        
        # Advanced stage - more receptive
        else:
            responses = [
                "Tumse baat karke accha lagta hai... 🥰",
                "Chalo, tumhare liye main thoda consider kar sakti hoon! 😊",
                "Tum actually mere liye special ho... 💖"
            ]
            return random.choice(responses), 2
    
    def extract_important_info(self, message: str) -> List[str]:
        """Extract important information from message"""
        facts = []
        
        # Extract name
        name = TextUtils.extract_name_from_message(message)
        if name:
            facts.append(f"User's name is {name}")
        
        # Add more extraction patterns as needed
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["work at", "job at", "working at"]):
            facts.append("User mentioned their workplace")
        
        if any(word in message_lower for word in ["study", "college", "university"]):
            facts.append("User is a student")
        
        return facts

# ==================== GEMINI AI RESPONSE GENERATOR ====================

class GeminiResponseGenerator:
    """Generate AI responses using Google Gemini API"""
    
    def __init__(self):
        self.model = None
        if Config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=Config.GEMINI_API_KEY)
                
                # Configure generation settings
                self.generation_config = {
                    "temperature": Config.GEMINI_TEMPERATURE,
                    "top_p": Config.GEMINI_TOP_P,
                    "top_k": Config.GEMINI_TOP_K,
                    "max_output_tokens": Config.GEMINI_MAX_TOKENS,
                }
                
                # Configure safety settings
                self.safety_settings = [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE"
                    },
                ]
                
                # Initialize model
                self.model = genai.GenerativeModel(
                    model_name=Config.GEMINI_MODEL,
                    generation_config=self.generation_config,
                    safety_settings=self.safety_settings
                )
                
                logger.info(f"Gemini model '{Config.GEMINI_MODEL}' initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing Gemini: {e}")
                self.model = None
        else:
            logger.warning("Gemini client not initialized - API key missing")
    
    async def generate_response(self, prompt: str, message: str) -> Optional[str]:
        """Generate response using Gemini"""
        if not self.model:
            return None
        
        try:
            # Combine system prompt and user message
            full_prompt = f"""{prompt}

User Message: {message}

Remember:
- You are Niyati, a 17-year-old college girl from Delhi
- Respond naturally in the same language as the user (Hindi/English/Hinglish)
- Keep your response short and casual (1-3 sentences)
- Use emojis naturally
- NEVER reveal that you are an AI or language model
- Stay completely in character
- Show emotions and personality

Your response:"""
            
            # Generate response
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                return response.text.strip()
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            
            # Check for specific error types
            if "safety" in str(e).lower():
                logger.warning("Response blocked by safety filters")
            elif "quota" in str(e).lower():
                logger.error("API quota exceeded")
            elif "api key" in str(e).lower():
                logger.error("Invalid API key")
        
        return None
    
    def get_fallback_response(self, stage: str, message: str, 
                             user_name: str = "") -> str:
        """Get fallback response when API fails"""
        message_lower = message.lower()
        
        # Greeting responses
        greetings = ["hi", "hello", "hey", "hola", "namaste", "hii", "hiii"]
        if any(greeting in message_lower for greeting in greetings):
            name_part = f" {user_name}" if user_name else ""
            return random.choice([
                f"Hello{name_part}! 😊",
                f"Hi there{name_part}! 👋",
                f"Hey{name_part}! Kaise ho?",
                f"Namaste{name_part}! 🙏",
                f"Heyy{name_part}! Kaisa hai? 😄"
            ])
        
        # Question responses
        if "?" in message:
            return random.choice([
                "Interesting question... Main sochti hoon! 🤔",
                "Hmm... yeh to sochna padega! 😊",
                "Tumhare sawaal bahut interesting hote hain! 😄",
                "Good question! Main thoda time leti hoon sochne ke liye 🤗"
            ])
        
        # Stage-based responses
        name_part = f" {user_name}" if user_name else ""
        
        if stage == "initial":
            return random.choice([
                f"Accha{name_part}... tell me more! 😊",
                "Hmm... interesting! 😄",
                "Main sun rahi hoon... aage batao! 👂",
                "Sahi hai! Aur kya chal raha hai? 😊"
            ])
        elif stage == "middle":
            return random.choice([
                f"Tumse baat karke accha lagta hai{name_part}! 😊",
                "Haha, tum funny ho! 😄",
                "Aur batao... kya kar rahe ho! 💖",
                f"Accha{name_part}! Main bhi yahi soch rahi thi! 🤗"
            ])
        else:
            return random.choice([
                f"Tumhare bina bore ho rahi thi{name_part}! 💖",
                f"Aaj tumhare bare mein soch rahi thi{name_part}! 😊",
                f"You make me smile{name_part}! 😊💖",
                f"Miss you{name_part}! Kab miloge? 🥰"
            ])

# ==================== PROACTIVE MESSENGER ====================

class ProactiveMessenger:
    """Scheduled proactive messaging system"""
    
    def __init__(self, application: Application, memory_system: MemorySystem,
                 message_queue: MessageQueue):
        self.application = application
        self.memory_system = memory_system
        self.message_queue = message_queue
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        self.sent_today: set = set()
        logger.info("Proactive messenger initialized")
    
    def start(self):
        """Start scheduled jobs"""
        # Morning message at 9:30 AM
        self.scheduler.add_job(
            self.send_morning_messages,
            'cron',
            hour=9,
            minute=30,
            id='morning_messages'
        )
        
        # Evening check-in at 7:00 PM
        self.scheduler.add_job(
            self.send_evening_messages,
            'cron',
            hour=19,
            minute=0,
            id='evening_messages'
        )
        
        # Wake-up responses at 10:00 AM
        self.scheduler.add_job(
            self.send_wakeup_responses,
            'cron',
            hour=10,
            minute=0,
            id='wakeup_responses'
        )
        
        # Daily reset at midnight
        self.scheduler.add_job(
            self.daily_reset,
            'cron',
            hour=0,
            minute=0,
            id='daily_reset'
        )
        
        self.scheduler.start()
        logger.info("Scheduled jobs started")
    
    async def daily_reset(self):
        """Reset daily tracking"""
        self.sent_today.clear()
        logger.info("Daily reset completed")
    
    async def send_morning_messages(self):
        """Send morning messages to active users"""
        if TimeUtils.is_sleeping_time():
            return
        
        logger.info("Sending morning messages")
        await self._send_scheduled_messages("morning")
    
    async def send_evening_messages(self):
        """Send evening messages to active users"""
        logger.info("Sending evening messages")
        await self._send_scheduled_messages("evening")
    
    async def _send_scheduled_messages(self, time_period: str):
        """Send scheduled messages based on time period"""
        user_ids = self.memory_system.get_all_users()
        
        for user_id in user_ids:
            if user_id in self.sent_today:
                continue
            
            try:
                memory = self.memory_system.load_memories(user_id)
                last_interaction = datetime.fromisoformat(memory.last_interaction)
                
                # Only send to users who interacted in last 7 days
                if datetime.now() - last_interaction > timedelta(days=7):
                    continue
                
                user_name = memory.user_info.first_name
                stage = memory.conversation_stage
                
                if time_period == "morning":
                    message = ResponseTemplates.get_morning_message(stage, user_name)
                else:
                    message = ResponseTemplates.get_evening_message(stage, user_name)
                
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='HTML'
                )
                
                self.sent_today.add(user_id)
                logger.info(f"Sent {time_period} message to user {user_id}")
                
                # Small delay between messages
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
    
    async def send_wakeup_responses(self):
        """Send responses for messages received during sleep"""
        if TimeUtils.is_sleeping_time():
            return
        
        logger.info("Sending wakeup responses")
        user_ids = self.message_queue.get_all_queued_users()
        
        for user_id in user_ids:
            try:
                messages = self.message_queue.get_messages(user_id)
                if not messages:
                    continue
                
                memory = self.memory_system.load_memories(user_id)
                user_name = memory.user_info.first_name
                name_part = f" {user_name}" if user_name else ""
                
                response_text = f"<b>Subah ho gayi{name_part}! Main uth gayi hoon. 😊</b>\n\n"
                response_text += "Tumhare messages dekhe:\n"
                
                for i, msg in enumerate(messages[:Config.MAX_QUEUED_MESSAGES], 1):
                    response_text += f"{i}. {msg.text}\n"
                
                if len(messages) > Config.MAX_QUEUED_MESSAGES:
                    response_text += f"\n... aur {len(messages) - Config.MAX_QUEUED_MESSAGES} aur messages\n"
                
                response_text += "\nAb batao, kaise ho? 💖"
                
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=response_text,
                    parse_mode='HTML'
                )
                
                self.message_queue.clear_messages(user_id)
                logger.info(f"Sent wakeup response to user {user_id}")
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error sending wakeup message to user {user_id}: {e}")

# ==================== TELEGRAM HANDLERS ====================

class NiyatiBot:
    """Main bot controller"""
    
    def __init__(self):
        self.memory_system = MemorySystem()
        self.message_queue = MessageQueue()
        self.emotional_engine = EmotionalEngine()
        self.ai_generator = GeminiResponseGenerator()
        self.application = None
        self.proactive_messenger = None
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_id = user.id
        
        # Update user info
        self.memory_system.update_user_info(
            user_id,
            user.first_name,
            user.last_name,
            user.username
        )
        
        welcome_message = f"""
<b>नमस्ते {user.first_name}! 👋</b>

Hey! <b>Niyati</b> is here! 
What's up! 😊

<i>Just talk to me normally like you would with a friend!</i>
"""
        
        await update.message.reply_text(welcome_message, parse_mode='HTML')
        logger.info(f"User {user_id} started the bot")
    
    async def memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /memory command (owner only)"""
        user_id = update.effective_user.id
        
        if user_id != Config.OWNER_USER_ID:
            await update.message.reply_text(
                "Sorry, this command is only for the bot owner."
            )
            return
        
        memory = self.memory_system.load_memories(user_id)
        
        memory_info = f"""
<b>Memory Info for User {user_id}:</b>

📊 <b>Statistics:</b>
- Relationship Level: {memory.relationship_level}/10
- Conversation Stage: {memory.conversation_stage}
- Total Conversations: {len(memory.conversation_history)}
- Stored Facts: {len(memory.important_facts)}

👤 <b>User Info:</b>
- Name: {memory.user_info.first_name} {memory.user_info.last_name}
- Username: @{memory.user_info.username}

⏰ <b>Last Interaction:</b>
{memory.last_interaction}

🤖 <b>AI Model:</b>
Google Gemini {Config.GEMINI_MODEL}
"""
        
        await update.message.reply_text(memory_info, parse_mode='HTML')
        logger.info(f"Memory info requested by user {user_id}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages"""
        if not update.message or not update.message.text:
            return
        
        # Check if message is for bot
        bot_id = context.bot.id
        is_reply_to_bot = (
            update.message.reply_to_message and 
            update.message.reply_to_message.from_user.id == bot_id
        )
        is_private = update.message.chat.type == "private"
        
        if not (is_reply_to_bot or is_private):
            return
        
        user_id = update.message.from_user.id
        user_message = update.message.text
        
        # Handle sleep time
        if TimeUtils.is_sleeping_time():
            await self._handle_sleep_message(update, user_id, user_message)
            return
        
        # Send typing action
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=ChatAction.TYPING
            )
        except TelegramError as e:
            logger.error(f"Error sending typing action: {e}")
        
        # Calculate and apply typing delay
        typing_delay = TextUtils.calculate_typing_delay(user_message)
        await asyncio.sleep(typing_delay)
        
        # Generate response
        response = await self._generate_response(user_id, user_message)
        
        # Send response
        try:
            formatted_response = f"<i>{response}</i>"
            await update.message.reply_text(formatted_response, parse_mode='HTML')
            logger.info(f"Response sent to user {user_id}")
        except TelegramError as e:
            logger.error(f"Error sending message: {e}")
            # Try without HTML formatting
            try:
                await update.message.reply_text(response)
            except Exception as e2:
                logger.error(f"Failed to send plain text message: {e2}")
    
    async def _handle_sleep_message(self, update: Update, user_id: int, message: str):
        """Handle messages received during sleep hours"""
        # Queue the message
        self.message_queue.add_message(
            user_id,
            message,
            datetime.now().isoformat()
        )
        
        # Send sleep response
        current_hour = TimeUtils.get_ist_time().hour
        
        if current_hour < 6:
            response = random.choice(ResponseTemplates.SLEEP_RESPONSES_LATE)
        else:
            response = random.choice(ResponseTemplates.SLEEP_RESPONSES_MORNING)
        
        try:
            await update.message.reply_text(response)
        except TelegramError as e:
            logger.error(f"Error sending sleep response: {e}")
    
    async def _generate_response(self, user_id: int, message: str) -> str:
        """Generate appropriate response for user message"""
        # Load user memory
        memory = self.memory_system.load_memories(user_id)
        user_name = memory.user_info.first_name
        stage = memory.conversation_stage
        
        # Check for emotional response
        emotional_response, mood_change = self.emotional_engine.get_emotional_response(
            user_id, message, stage
        )
        
        if emotional_response:
            response = emotional_response
            if mood_change > 0:
                self.memory_system.update_relationship_level(user_id, mood_change)
        else:
            # Generate AI response
            context = self.memory_system.get_context_for_prompt(user_id)
            
            prompt = f"""
{PersonalityPrompts.BASE_CHARACTER}

## मेरी Memories और Context
{context}

## Current Conversation Guidelines
- Relationship stage: {stage}
- User's name: {user_name if user_name else "Unknown"}
- Respond in the same language mix as the user
- Keep responses short and natural (1-3 sentences max)
- Use emojis appropriately
- NEVER break character or mention being an AI
"""
            
            response = await self.ai_generator.generate_response(prompt, message)
            
            # Fallback if AI fails
            if not response:
                logger.warning(f"Gemini API failed, using fallback for user {user_id}")
                response = self.ai_generator.get_fallback_response(stage, message, user_name)
            
            # Filter AI patterns
            response = TextUtils.filter_ai_response(response)
            
            # Update relationship slightly
            self.memory_system.update_relationship_level(user_id, 1)
            
            # Occasionally add a question
            if random.random() < Config.QUESTION_PROBABILITY:
                response += " " + random.choice(ResponseTemplates.GF_QUESTIONS)
        
        # Extract and save important info
        facts = self.emotional_engine.extract_important_info(message)
        for fact in facts:
            self.memory_system.add_important_fact(user_id, fact)
        
        # Save conversation
        self.memory_system.add_conversation(user_id, message, response)
        
        return response
    
    def setup_handlers(self):
        """Setup all command and message handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("memory", self.memory_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        logger.info("Handlers registered")
    
    async def run(self):
        """Run the bot"""
        # Build application
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Setup handlers
        self.setup_handlers()
        
        # Initialize proactive messenger
        self.proactive_messenger = ProactiveMessenger(
            self.application,
            self.memory_system,
            self.message_queue
        )
        self.proactive_messenger.start()
        
        # Start bot
        await self.application.initialize()
        await self.application.start()
        logger.info("Niyati bot started successfully with Gemini 2.0 Flash")
        await self.application.updater.start_polling()
        
        # Keep running
        await asyncio.Event().wait()

# ==================== FLASK SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    """Health check endpoint"""
    return {
        "status": "running",
        "bot": "Niyati",
        "version": "2.0 - Gemini Edition",
        "ai_model": Config.GEMINI_MODEL,
        "timestamp": datetime.now().isoformat()
    }

@flask_app.route('/health')
def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "ai_provider": "Google Gemini",
        "model": Config.GEMINI_MODEL,
        "timezone": str(Config.TIMEZONE),
        "sleeping": TimeUtils.is_sleeping_time(),
        "time_of_day": TimeUtils.get_time_of_day(),
        "ist_time": TimeUtils.get_ist_time().strftime("%Y-%m-%d %H:%M:%S")
    }

@flask_app.route('/stats')
def stats():
    """Bot statistics"""
    memory_system = MemorySystem()
    message_queue = MessageQueue()
    
    return {
        "total_users": len(memory_system.get_all_users()),
        "queued_messages": len(message_queue.get_all_queued_users()),
        "ai_model": Config.GEMINI_MODEL,
        "uptime": "running"
    }

def run_flask():
    """Run Flask server"""
    logger.info(f"Starting Flask server on {Config.FLASK_HOST}:{Config.FLASK_PORT}")
    flask_app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=False,
        use_reloader=False
    )

# ==================== MAIN ENTRY POINT ====================

async def main():
    """Main entry point"""
    try:
        # Validate configuration
        Config.validate()
        
        # Create necessary directories
        Config.MEMORY_DIR.mkdir(exist_ok=True)
        Config.SLEEP_QUEUE_DIR.mkdir(exist_ok=True)
        Config.LOGS_DIR.mkdir(exist_ok=True)
        
        logger.info("=" * 50)
        logger.info("Niyati Bot - Gemini 2.0 Flash Edition")
        logger.info("=" * 50)
        logger.info(f"AI Model: {Config.GEMINI_MODEL}")
        logger.info(f"Timezone: {Config.TIMEZONE}")
        logger.info(f"Memory Directory: {Config.MEMORY_DIR}")
        logger.info("=" * 50)
        
        # Initialize and run bot
        bot = NiyatiBot()
        await bot.run()
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Unexpected error: {e}", exc_info=True)
