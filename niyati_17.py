"""
Niyati - AI Girlfriend Telegram Bot
Complete Error-Free Version with Gemini + Supabase
"""

import os
import sys
import random
import json
import asyncio
import logging
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict

from flask import Flask, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from waitress import serve
import pytz
import google.generativeai as genai
from supabase import create_client, Client

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

class Config:
    """Application configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.0-flash-exp"
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zjorumnzwqhugamwwgjy.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)   # 1 AM
    SLEEP_END = time(10, 0)     # 10 AM
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - using fallback responses")
        if not cls.SUPABASE_KEY:
            logger.warning("⚠️ SUPABASE_KEY not set - using local storage")

# ==================== CONSTANTS ====================

PERSONALITY = """You are Niyati, a 17-year-old college girl from Delhi.

PERSONALITY TRAITS:
- Friendly, witty, playful, and caring
- A bit shy initially but opens up gradually
- Possessive and gets jealous easily
- Loves chatting in Hindi/English/Hinglish mix
- Uses emojis naturally like a real girl

SPEAKING STYLE:
- Keep responses SHORT (1-3 sentences max)
- Be natural and conversational
- Show emotions through emojis
- Sometimes ask questions to keep conversation going
- Use casual language like "kya", "yaar", "achha"

IMPORTANT RULES:
- NEVER reveal you're an AI, chatbot, or language model
- Always stay in character as Niyati
- If asked about being AI, deny it playfully
- React naturally to flirting (shy at first, more open later)
"""

HARD_TO_GET_RESPONSES = [
    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
    "Itni jaldi? Pehle ek dosre ko achhe se jaan lete hai! 😊",
    "Main itni easily impress nahi hoti! 😉",
    "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
    "Hmm... dekhte hain, tum interesting to ho! 😊",
    "Arre wah, tum to kaafi confident ho! 😅",
    "Thoda aur try karo… shayad impress ho jaun. 😇",
]

GF_QUESTIONS = [
    "Kaha the ab tak?",
    "Kya kar rahe the?",
    "Mujhe miss kiya?",
    "Khaana kha liya?",
    "Aaj ka din kaisa raha?",
    "Sab theek hai na?",
]

SLEEP_RESPONSES_NIGHT = [
    "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
    "Shhh... Neend aa rahi hai. Kal subah baat karte hain. 🌙",
    "Sone ka time hai... Good night! 💤",
]

SLEEP_RESPONSES_MORNING = [
    "Uff... subah ke 10 baje tak soti hoon main. 😴",
    "Abhi neend aa rahi hai... Thodi der baad message karna. 🌅",
    "Good morning! Par main abhi so rahi hoon. 😊",
]

AI_DENIAL_RESPONSES = [
    "Kya bol raha hai? Main AI nahi hoon! Main Niyati hoon! 😡",
    "Pagal ho kya? Main ek real ladki hoon! 🤬",
    "Tumhe main robot lagti hoon kya? 😤",
    "Stop it! Main normal college girl hoon! 😠",
]

# ==================== DATABASE ====================

class Database:
    """Database manager with Supabase and local fallback"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.local_db: Dict = {}
        self.use_local = True
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase client"""
        if Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # Test connection
                self.supabase.table('user_chats').select("*").limit(1).execute()
                self.use_local = False
                logger.info("✅ Supabase connected successfully")
            except Exception as e:
                logger.warning(f"⚠️ Supabase connection failed: {e}")
                logger.info("📁 Using local storage instead")
                self.use_local = True
        else:
            logger.info("📁 Using local storage (no Supabase key)")
    
    def _load_local(self):
        """Load local database"""
        try:
            if os.path.exists('local_db.json'):
                with open('local_db.json', 'r', encoding='utf-8') as f:
                    self.local_db = json.load(f)
                logger.info(f"📂 Loaded {len(self.local_db)} users from local storage")
        except Exception as e:
            logger.error(f"❌ Error loading local db: {e}")
            self.local_db = {}
    
    def _save_local(self):
        """Save local database"""
        try:
            with open('local_db.json', 'w', encoding='utf-8') as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Error saving local db: {e}")
    
    def get_user(self, user_id: int) -> Dict:
        """Get user data"""
        user_id_str = str(user_id)
        
        if self.use_local:
            # Local storage
            if user_id_str not in self.local_db:
                self.local_db[user_id_str] = {
                    "user_id": user_id,
                    "name": "",
                    "username": "",
                    "chats": [],
                    "relationship_level": 1,
                    "stage": "initial",
                    "last_interaction": datetime.now().isoformat()
                }
            return self.local_db[user_id_str]
        else:
            # Supabase
            try:
                result = self.supabase.table('user_chats').select("*").eq('user_id', user_id).execute()
                
                if result.data and len(result.data) > 0:
                    user_data = result.data[0]
                    # Parse JSON fields
                    if isinstance(user_data.get('chats'), str):
                        user_data['chats'] = json.loads(user_data['chats'])
                    return user_data
                else:
                    # Create new user
                    new_user = {
                        "user_id": user_id,
                        "name": "",
                        "username": "",
                        "chats": json.dumps([]),
                        "relationship_level": 1,
                        "stage": "initial",
                        "last_interaction": datetime.now().isoformat()
                    }
                    self.supabase.table('user_chats').insert(new_user).execute()
                    new_user['chats'] = []
                    return new_user
                    
            except Exception as e:
                logger.error(f"❌ Supabase error: {e}")
                # Fallback to local
                return self.get_user(user_id)
    
    def save_user(self, user_id: int, user_data: Dict):
        """Save user data"""
        user_id_str = str(user_id)
        user_data['last_interaction'] = datetime.now().isoformat()
        
        if self.use_local:
            # Local storage
            self.local_db[user_id_str] = user_data
            self._save_local()
        else:
            # Supabase
            try:
                # Prepare data for Supabase
                save_data = user_data.copy()
                if isinstance(save_data.get('chats'), list):
                    save_data['chats'] = json.dumps(save_data['chats'])
                
                # Upsert
                self.supabase.table('user_chats').upsert(save_data).execute()
                
            except Exception as e:
                logger.error(f"❌ Supabase save error: {e}")
                # Fallback to local
                self.local_db[user_id_str] = user_data
                self._save_local()
    
    def add_message(self, user_id: int, user_msg: str, bot_msg: str):
        """Add message to conversation history"""
        user = self.get_user(user_id)
        
        # Ensure chats is a list
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        if not isinstance(user.get('chats'), list):
            user['chats'] = []
        
        # Add new message
        user['chats'].append({
            "user": user_msg,
            "bot": bot_msg,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 10 messages
        if len(user['chats']) > 10:
            user['chats'] = user['chats'][-10:]
        
        # Update relationship level
        user['relationship_level'] = min(10, user['relationship_level'] + 1)
        
        # Update stage
        level = user['relationship_level']
        if level <= 3:
            user['stage'] = "initial"
        elif level <= 7:
            user['stage'] = "middle"
        else:
            user['stage'] = "advanced"
        
        self.save_user(user_id, user)
    
    def update_user_info(self, user_id: int, name: str, username: str = ""):
        """Update user basic info"""
        user = self.get_user(user_id)
        user['name'] = name
        user['username'] = username
        self.save_user(user_id, user)
    
    def get_context(self, user_id: int) -> str:
        """Get conversation context for AI"""
        user = self.get_user(user_id)
        
        # Ensure chats is a list
        if isinstance(user.get('chats'), str):
            user['chats'] = json.loads(user['chats'])
        
        context_parts = [
            f"User's name: {user.get('name', 'Unknown')}",
            f"Relationship stage: {user.get('stage', 'initial')}",
            f"Relationship level: {user.get('relationship_level', 1)}/10"
        ]
        
        # Add recent conversation
        chats = user.get('chats', [])
        if chats and isinstance(chats, list):
            context_parts.append("\nRecent conversation:")
            for chat in chats[-3:]:
                if isinstance(chat, dict):
                    context_parts.append(f"User: {chat.get('user', '')}")
                    context_parts.append(f"You: {chat.get('bot', '')}")
        
        return "\n".join(context_parts)
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        if self.use_local:
            return {
                "total_users": len(self.local_db),
                "storage": "local"
            }
        else:
            try:
                result = self.supabase.table('user_chats').select("user_id", count='exact').execute()
                return {
                    "total_users": result.count if hasattr(result, 'count') else 0,
                    "storage": "supabase"
                }
            except:
                return {"total_users": 0, "storage": "error"}

# Initialize database
db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI wrapper"""
    
    def __init__(self):
        self.model = None
        self._init_model()
    
    def _init_model(self):
        """Initialize Gemini model"""
        if not Config.GEMINI_API_KEY:
            logger.warning("⚠️ Gemini API key not set")
            return
        
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.8,
                    "max_output_tokens": 500,
                    "top_p": 0.9,
                    "top_k": 40
                },
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
            )
            logger.info("✅ Gemini AI initialized")
        except Exception as e:
            logger.error(f"❌ Gemini initialization error: {e}")
            self.model = None
    
    async def generate(self, message: str, context: str = "") -> Optional[str]:
        """Generate AI response"""
        if not self.model:
            return None
        
        try:
            full_prompt = f"""{PERSONALITY}

{context}

User says: {message}

Respond as Niyati (short and natural):"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter AI mentions
                bad_phrases = [
                    "as an ai", "i'm an ai", "i am an ai", "language model",
                    "artificial intelligence", "chatbot", "i'm a chatbot",
                    "gemini", "google ai", "i don't have feelings",
                    "i'm not a real person", "i cannot"
                ]
                
                text_lower = text.lower()
                if any(phrase in text_lower for phrase in bad_phrases):
                    return random.choice(AI_DENIAL_RESPONSES)
                
                return text
            
        except Exception as e:
            logger.error(f"❌ Gemini generation error: {e}")
        
        return None
    
    def fallback_response(self, message: str, stage: str = "initial", name: str = "") -> str:
        """Fallback response when AI fails"""
        msg_lower = message.lower()
        
        # Greetings
        if any(word in msg_lower for word in ["hi", "hello", "hey", "hola", "namaste"]):
            greetings = [
                f"Hello {name}! Kaise ho? 😊",
                f"Hi {name}! What's up? 👋",
                f"Hey {name}! 😄",
                f"Namaste {name}! 🙏"
            ]
            return random.choice(greetings).replace("  ", " ")
        
        # Questions
        if "?" in message:
            return random.choice([
                "Hmm... interesting question! 🤔",
                "Good question! Let me think 😊",
                "Mujhe sochne do thoda! 🤗"
            ])
        
        # Stage-based responses
        if stage == "initial":
            responses = [
                "Accha! Tell me more 😊",
                "Interesting! 😄",
                "Sahi hai! Aur kya chal raha hai? 👍"
            ]
        elif stage == "middle":
            responses = [
                f"Tumse baat karke accha lagta hai {name}! 😊",
                "Haha, tum funny ho! 😄",
                "Aur batao! 💖"
            ]
        else:
            responses = [
                f"Miss you {name}! 💖",
                "Tumhare baare mein soch rahi thi! 😊",
                "You make me smile! 🥰"
            ]
        
        return random.choice(responses).replace("  ", " ")

# Initialize AI
ai = GeminiAI()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    """Get current IST time"""
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    """Check if it's sleeping time"""
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    """Calculate realistic typing delay"""
    base_delay = min(3.0, max(0.5, len(text) / 50))
    return base_delay + random.uniform(0.3, 1.0)

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Update user info
    db.update_user_info(user_id, user.first_name, user.username or "")
    
    welcome_msg = f"""
<b>नमस्ते {user.first_name}! 👋</b>

I'm <b>Niyati</b>, a 17-year-old college student from Delhi! 

Just chat with me normally - I love making new friends! 😊

<i>✨ Powered by Gemini AI</i>
"""
    
    await update.message.reply_text(welcome_msg, parse_mode='HTML')
    logger.info(f"✅ User {user_id} ({user.first_name}) started bot")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command (owner only)"""
    user_id = update.effective_user.id
    
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ This command is only for the bot owner.")
        return
    
    stats = db.get_stats()
    user_data = db.get_user(user_id)
    
    stats_msg = f"""
📊 <b>Bot Statistics</b>

👥 Total Users: {stats['total_users']}
💾 Storage: {stats['storage'].upper()}
🤖 AI Model: {Config.GEMINI_MODEL}

<b>Your Stats:</b>
💬 Messages: {len(user_data.get('chats', []))}
❤️ Relationship Level: {user_data.get('relationship_level', 1)}/10
🎭 Stage: {user_data.get('stage', 'initial')}
"""
    
    await update.message.reply_text(stats_msg, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ==================== BOT HANDLERS ====================

# Global dictionaries to track cooldowns across different chats
group_reply_cooldown = {}
user_interaction_cooldown = {}

def should_reply_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Smart logic to decide if the bot should reply in a group chat.
    This helps prevent spam and saves your API key.
    
    REPLY CONDITIONS (in order of priority):
    1. Direct mention or reply -> Always reply.
    2. Group or user is in cooldown -> Never reply.
    3. Message contains high-priority keywords -> High chance to reply (70%).
    4. Bot was recently active in the chat -> Medium chance to reply (40%).
    5. None of the above -> Low chance for random engagement (15%).
    """
    if not update.message or not update.message.text:
        return False
        
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text.lower()
    now = datetime.now()

    # 1. ALWAYS reply to a direct mention or a reply to the bot's message
    is_reply_to_bot = (update.message.reply_to_message and 
                       update.message.reply_to_message.from_user.id == context.bot.id)
    
    bot_username = (context.bot.username or "").lower()
    is_mentioned = (f"@{bot_username}" in message_text) or ("niyati" in message_text)
    
    if is_reply_to_bot or is_mentioned:
        return True

    # 2. COOLDOWN check to prevent spamming
    # Group-level cooldown (e.g., bot won't speak in the group for 30 seconds)
    if chat_id in group_reply_cooldown:
        if (now - group_reply_cooldown[chat_id]).total_seconds() < 30:
            return False
            
    # User-level cooldown (e.g., bot won't reply to the same user for 2 minutes)
    user_key = f"{chat_id}_{user_id}"
    if user_key in user_interaction_cooldown:
        if (now - user_interaction_cooldown[user_key]).total_seconds() < 120:
            return False

    # 3. KEYWORD triggers (high chance of replying)
    high_priority_keywords = [
        "kya", "kaise", "kyu", "kab", "kaha", "kaun",  # Question words
        "baby", "jaan", "love", "miss",                # Personal words
        "hello", "hi", "hey", "good morning", "gn",    # Greetings
        "?", "please", "help", "batao"                 # Help/Questions
    ]
    if any(keyword in message_text for keyword in high_priority_keywords):
        return random.random() < 0.7  # 70% chance

    # 4. RECENT conversation context (medium chance)
    if chat_id in group_reply_cooldown:
        if (now - group_reply_cooldown[chat_id]).total_seconds() < 180:  # If bot spoke in last 3 mins
            return random.random() < 0.4  # 40% chance

    # 5. RANDOM engagement to keep the chat alive (low chance)
    return random.random() < 0.15


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Update user info
    db.update_user_info(user_id, user.first_name, user.username or "")
    
    welcome_msg = f"""
<b>नमस्ते {user.first_name}! 👋</b>

I'm <b>Niyati</b>, a 17-year-old college student from Delhi! 

Just chat with me normally - I love making new friends! 😊

<i>✨ Powered by Gemini AI</i>
"""
    
    await update.message.reply_text(welcome_msg, parse_mode='HTML')
    logger.info(f"✅ User {user_id} ({user.first_name}) started bot")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command (owner only)"""
    user_id = update.effective_user.id
    
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ This command is only for the bot owner.")
        return
    
    stats = db.get_stats()
    user_data = db.get_user(user_id)
    
    stats_msg = f"""
📊 <b>Bot Statistics</b>

👥 Total Users: {stats['total_users']}
💾 Storage: {stats['storage'].upper()}
🤖 AI Model: {Config.GEMINI_MODEL}

<b>Your Stats:</b>
💬 Messages: {len(user_data.get('chats', []))}
❤️ Relationship Level: {user_data.get('relationship_level', 1)}/10
🎭 Stage: {user_data.get('stage', 'initial')}
"""
    
    await update.message.reply_text(stats_msg, parse_mode='HTML')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages using the smart filtering logic"""
    try:
        if not update.message or not update.message.text:
            return
            
        is_private = update.message.chat.type == "private"
        
        # In GROUPS, use the smart logic to decide whether to reply
        if not is_private:
            if not should_reply_in_group(update, context):
                logger.info("⏭️ Skipped group message (smart filter)")
                return
        
        # --- If the bot decides to reply, proceed from here ---
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_msg = update.message.text
        now = datetime.now()

        # Update cooldown timestamps to mark that the bot is now replying
        group_reply_cooldown[chat_id] = now
        user_interaction_cooldown[f"{chat_id}_{user_id}"] = now
        
        # Sleep mode check
        if is_sleeping_time():
            hour = get_ist_time().hour
            response = random.choice(SLEEP_RESPONSES_NIGHT) if hour < 6 else random.choice(SLEEP_RESPONSES_MORNING)
            await update.message.reply_text(response)
            return
            
        # Show "typing..." action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(calculate_typing_delay(user_msg))
        
        # Get user data and context
        user_data = db.get_user(user_id)
        stage = user_data.get('stage', 'initial')
        name = user_data.get('name', '')
        
        # Check for romantic messages in the initial stage
        romantic_keywords = ["love", "like you", "girlfriend", "date", "pyar", "propose"]
        is_romantic = any(word in user_msg.lower() for word in romantic_keywords)
        
        if is_romantic and stage == "initial":
            response = random.choice(HARD_TO_GET_RESPONSES)
        else:
            # Generate AI response
            context_str = db.get_context(user_id)
            response = await ai.generate(user_msg, context_str)
            
            # Use fallback if AI fails
            if not response:
                response = ai.fallback_response(user_msg, stage, name)
            
            # Occasionally ask a question back in private chats
            if is_private and random.random() < 0.3:
                response += " " + random.choice(GF_QUESTIONS)
                
        # Save the conversation to the database
        db.add_message(user_id, user_msg, response)
        
        # Send the final response
        await update.message.reply_text(response)
        logger.info(f"✅ Replied to user {user_id} in {'private chat' if is_private else f'group {chat_id}'}")

    except Exception as e:
        logger.error(f"❌ Message handler error: {e}", exc_info=True)
        try:
            await update.message.reply_text("Oops! Kuch gadbad ho gayi. Phir se try karo? 😅")
        except Exception:
            pass
        
        # Calculate typing delay
        delay = calculate_typing_delay(user_msg)
        await asyncio.sleep(delay)
        
        # Get user data
        user_data = db.get_user(user_id)
        stage = user_data.get('stage', 'initial')
        name = user_data.get('name', '')
        
        # Check for romantic message in initial stage
        romantic_keywords = ["love", "like you", "girlfriend", "date", "pyar", "propose"]
        is_romantic = any(word in user_msg.lower() for word in romantic_keywords)
        
        if is_romantic and stage == "initial":
            response = random.choice(HARD_TO_GET_RESPONSES)
        else:
            # Generate AI response
            context_str = db.get_context(user_id)
            response = await ai.generate(user_msg, context_str)
            
            # Use fallback if AI fails
            if not response:
                response = ai.fallback_response(user_msg, stage, name)
            
            # Occasionally add a question (only in private chats)
            if is_private and random.random() < 0.3:
                response += " " + random.choice(GF_QUESTIONS)
        
        # Save conversation
        db.add_message(user_id, user_msg, response)
        
        # Send response
        await update.message.reply_text(response)
        logger.info(f"✅ Replied to user {user_id} in {'private' if is_private else 'group'}")
        
    except Exception as e:
        logger.error(f"❌ Message handler error: {e}")
        try:
            await update.message.reply_text(
                "Oops! Kuch gadbad ho gayi. Phir se try karo? 😅"
            )
        except:
            pass

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    """Home route"""
    stats = db.get_stats()
    return jsonify({
        "status": "running",
        "bot": "Niyati",
        "version": "2.0",
        "model": Config.GEMINI_MODEL,
        "users": stats['total_users'],
        "storage": stats['storage'],
        "time": datetime.now().isoformat()
    })

@flask_app.route('/health')
def health():
    """Health check route"""
    return jsonify({
        "status": "healthy",
        "sleeping": is_sleeping_time(),
        "time": get_ist_time().strftime("%Y-%m-%d %H:%M:%S IST")
    })

@flask_app.route('/stats')
def stats_route():
    """Stats route"""
    return jsonify(db.get_stats())

def run_flask():
    """Run Flask server"""
    logger.info(f"🌐 Starting Flask server on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=4)

# ==================== MAIN BOT ====================

async def main():
    """Main bot function"""
    try:
        # Validate configuration
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Starting Niyati AI Girlfriend Bot")
        logger.info("="*60)
        logger.info(f"📱 Bot: @{(await Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build().bot.get_me()).username}")
        logger.info(f"🧠 AI Model: {Config.GEMINI_MODEL}")
        logger.info(f"💾 Storage: {db.get_stats()['storage'].upper()}")
        logger.info(f"🌍 Timezone: {Config.TIMEZONE}")
        logger.info("="*60)
        
        # Build application
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Start bot
        await app.initialize()
        await app.start()
        logger.info("✅ Bot started successfully!")
        logger.info("🎯 Listening for messages...")
        
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        # Keep running
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    # Start Flask server in background thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Give Flask time to start
    import time
    time.sleep(2)
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        sys.exit(1)
