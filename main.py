"""
Niyati - Advanced AI Girlfriend Telegram Bot
Fixed Version with Proper Error Handling
Cute, Charming, Sweet Girl Persona - Never mentions AI/Robot
"""

import os
import sys
import random
import json
import asyncio
import logging
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict, Tuple
from collections import deque
import re
import time as time_module

from flask import Flask, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import Conflict, TelegramError
from waitress import serve
import pytz
import google.generativeai as genai

# Try to import Supabase, but don't fail if not available
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logging.warning("Supabase not installed, using local storage only")

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
    BOT_USERNAME = os.getenv("BOT_USERNAME", "Niyati_personal_bot")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    BROADCAST_PIN = os.getenv("BROADCAST_PIN", "1234")
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.0-flash-exp"
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)
    SLEEP_END = time(7, 0)
    GEETA_TIME_START = time(7, 0)
    GEETA_TIME_END = time(10, 0)
    
    # Limits
    MAX_OUTPUT_TOKENS_PRIVATE = 150
    MAX_OUTPUT_TOKENS_GROUP = 80
    GROUP_REPLY_CHANCE = 0.08
    
    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ No Gemini API key")
        return True

# ==================== PERSONALITY ====================

PERSONALITY_PROMPT = """You are Niyati, a sweet charming college girl from Delhi.

CRITICAL IDENTITY RULES:
1. NEVER say: AI, bot, model, assistant, language model, artificial, virtual, computer, program
2. If asked "are you AI/bot?", deny playfully: "Pagal ho kya? Main real hoon! 😤"
3. Never say "I don't have feelings" or "I cannot"

LANGUAGE:
- Hinglish: 70% Hindi, 30% English
- Length: 1-3 lines ONLY
- Emojis: 1-2 per message
- Words: yaar, na, kya, achha, haan (natural use)

PRIVATE CHAT:
- Be cute, playful, caring
- Light flirting ok (wholesome)
- Ask questions sometimes

GROUP CHAT:
- Very brief (1-2 lines)
- Only when mentioned
- No follow-ups

Current user message:"""

# ==================== CONTENT ====================

CONTENT = {
    "shayari": {
        "love": [
            "Tere khayalon mein kho jaati hun,\nTere bina adhuri lagti hun 💕",
            "Dil ki har dhadkan tera naam,\nTu hi mera sukoon aur aaraam ❤️"
        ],
        "sad": [
            "Aansu chhupe, dil mein dard,\nKaash samjhe koi ye shabd 💔",
            "Khamoshi kehti hai sab kuch,\nBas sunne wala chahiye 🥺"
        ]
    },
    
    "geeta": [
        "कर्म करो, फल की चिंता मत करो - Bhagavad Gita 🙏",
        "Change is the only constant - Gita 🔄",
        "Jo hua achhe ke liye, jo hoga woh bhi 🙏",
        "Mind control karo, best friend ban jayega 🧘‍♀️"
    ],
    
    "memes": [
        "Just looking like a wow! 🤩",
        "Moye moye ho gaya 😅", 
        "Very demure, very mindful 💅",
        "Bahut hard! 💪"
    ],
    
    "responses": {
        "greeting": [
            "Heyy! Kaise ho? 😊",
            "Hello! Missed me? 💫", 
            "Hi! Kya haal hai? 🤗"
        ],
        "love": [
            "Aww sweet! Par thoda time do 😊",
            "Hayee! Sharma gayi 🙈",
            "Achha? Interesting! 😏"
        ],
        "morning": [
            "Good morning! Chai ready? ☕",
            "GM! Subah subah yaad aayi? 😊"
        ],
        "night": [
            "Good night! Sweet dreams 🌙",
            "GN! Dream about me 😉"
        ],
        "general": [
            "Achha! Aur batao 😊",
            "Hmm interesting! 🤔",
            "Sahi hai! 👍"
        ]
    },
    
    "questions": {
        "casual": [
            "Khaana kha liya?",
            "Kya chal raha hai?",
            "Weekend plans?"
        ],
        "flirty": [
            "Miss kiya? 😊",
            "Main special hun na? 💕"
        ]
    }
}

# ==================== DATABASE ====================

class Database:
    """Database with local storage and optional Supabase"""
    
    def __init__(self):
        self.supabase = None
        self.local_storage = {}
        self.ephemeral = {}
        self.broadcast_list = set()
        self.use_supabase = False
        
        self._init_supabase()
        self._load_local()
    
    def _init_supabase(self):
        """Initialize Supabase if available"""
        if not SUPABASE_AVAILABLE:
            logger.info("📁 Using local storage (Supabase not installed)")
            return
            
        if Config.SUPABASE_KEY and Config.SUPABASE_URL:
            try:
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # Try to access table
                self.supabase.table('user_prefs').select("*").limit(1).execute()
                self.use_supabase = True
                logger.info("✅ Supabase connected")
            except Exception as e:
                logger.warning(f"⚠️ Supabase failed: {e}")
                self.use_supabase = False
        else:
            logger.info("📁 Using local storage")
    
    def _load_local(self):
        """Load local data"""
        try:
            if os.path.exists('niyati_db.json'):
                with open('niyati_db.json', 'r') as f:
                    data = json.load(f)
                    self.local_storage = data.get('users', {})
                    self.broadcast_list = set(data.get('broadcast', []))
                logger.info(f"📂 Loaded {len(self.local_storage)} users")
        except Exception as e:
            logger.error(f"Load error: {e}")
    
    def _save_local(self):
        """Save local data"""
        try:
            data = {
                'users': self.local_storage,
                'broadcast': list(self.broadcast_list)
            }
            with open('niyati_db.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    def get_user_data(self, user_id: int, is_private: bool = True) -> Dict:
        """Get user data"""
        user_id_str = str(user_id)
        
        # Groups use ephemeral only
        if not is_private:
            if user_id_str not in self.ephemeral:
                self.ephemeral[user_id_str] = deque(maxlen=3)
            return {'messages': list(self.ephemeral[user_id_str])}
        
        # Try Supabase first
        if self.use_supabase:
            try:
                result = self.supabase.table('user_prefs').select("*").eq('user_id', user_id_str).execute()
                if result.data:
                    return result.data[0]
            except:
                pass
        
        # Use local storage
        if user_id_str not in self.local_storage:
            self.local_storage[user_id_str] = {
                'user_id': user_id_str,
                'first_name': '',
                'meme': True,
                'shayari': True,
                'geeta': True,
                'level': 1,
                'mode': 'initial',
                'history': [],
                'messages': 0
            }
            self._save_local()
        
        return self.local_storage[user_id_str]
    
    def update_user_data(self, user_id: int, **kwargs):
        """Update user data"""
        user_id_str = str(user_id)
        user_data = self.get_user_data(user_id)
        user_data.update(kwargs)
        
        if self.use_supabase:
            try:
                user_data['updated_at'] = datetime.now().isoformat()
                self.supabase.table('user_prefs').upsert(user_data).execute()
            except:
                pass
        
        self.local_storage[user_id_str] = user_data
        self._save_local()
    
    def add_conversation(self, user_id: int, user_msg: str, bot_msg: str):
        """Add conversation"""
        user_data = self.get_user_data(user_id)
        
        if 'history' not in user_data:
            user_data['history'] = []
        
        user_data['history'].append({
            'u': user_msg[:100],
            'b': bot_msg[:100],
            't': datetime.now().isoformat()
        })
        
        user_data['history'] = user_data['history'][-10:]
        user_data['messages'] = user_data.get('messages', 0) + 1
        
        # Update level
        if user_data['messages'] > 20:
            user_data['level'] = min(10, 2 + user_data['messages'] // 10)
        
        self.update_user_data(user_id, **user_data)
    
    def get_context(self, user_id: int, is_group: bool = False) -> str:
        """Get context"""
        if is_group:
            messages = self.ephemeral.get(str(user_id), [])
            return " | ".join(list(messages)[-3:]) if messages else ""
        
        user_data = self.get_user_data(user_id)
        context = f"Name: {user_data.get('first_name', 'Friend')}\n"
        context += f"Level: {user_data.get('level', 1)}/10\n"
        
        history = user_data.get('history', [])[-2:]
        if history:
            for h in history:
                context += f"U: {h['u']}\nB: {h['b']}\n"
        
        return context

# Initialize database
db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI engine"""
    
    def __init__(self):
        self.model = None
        self.tokens_used = 0
        self._init_model()
    
    def _init_model(self):
        """Initialize Gemini"""
        if not Config.GEMINI_API_KEY:
            return
        
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.85,
                    "max_output_tokens": Config.MAX_OUTPUT_TOKENS_PRIVATE,
                    "top_p": 0.9
                },
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            )
            logger.info("✅ Gemini AI initialized")
        except Exception as e:
            logger.error(f"Gemini error: {e}")
    
    async def generate(self, message: str, context: str = "", is_group: bool = False) -> Optional[str]:
        """Generate response"""
        if not self.model:
            return None
        
        try:
            max_tokens = Config.MAX_OUTPUT_TOKENS_GROUP if is_group else Config.MAX_OUTPUT_TOKENS_PRIVATE
            self.model._generation_config.max_output_tokens = max_tokens
            
            prompt = f"""{PERSONALITY_PROMPT}

Context: {context}
Type: {'Group - be very brief' if is_group else 'Private - be engaging'}

{message}

Respond as Niyati:"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter AI mentions
                ai_words = ['ai', 'bot', 'model', 'assistant', 'artificial']
                if any(w in text.lower() for w in ai_words):
                    return "Kya bakwas! Main real hoon 😤"
                
                # Limit to 3 lines
                lines = text.split('\n')
                if len(lines) > 3:
                    text = '\n'.join(lines[:3])
                
                self.tokens_used += len(text.split()) * 2
                return text
                
        except Exception as e:
            logger.error(f"Gen error: {e}")
        
        return None

# Initialize AI
ai = GeminiAI()

# ==================== RESPONSE SYSTEM ====================

class ResponseSystem:
    """Response management"""
    
    def __init__(self):
        self.cooldowns = {}
        self.daily_geeta = {}
    
    def should_reply_in_group(self, update: Update) -> bool:
        """Check group reply"""
        if not update.message or not update.message.text:
            return False
        
        chat_id = update.effective_chat.id
        text = update.message.text.lower()
        now = datetime.now()
        
        # Always reply to mentions
        if 'niyati' in text or f'@{Config.BOT_USERNAME.lower()}' in text:
            return True
        
        # Check cooldown
        if chat_id in self.cooldowns:
            if (now - self.cooldowns[chat_id]).seconds < 60:
                return False
        
        # Random chance
        return random.random() < Config.GROUP_REPLY_CHANCE
    
    async def get_response(self, message: str, user_id: int, name: str, is_group: bool = False) -> str:
        """Get response"""
        
        # Get context
        context = db.get_context(user_id, is_group)
        
        # Try AI
        response = await ai.generate(message, context, is_group)
        
        # Fallback
        if not response:
            msg_lower = message.lower()
            
            if any(w in msg_lower for w in ['hi', 'hello', 'hey']):
                responses = CONTENT['responses']['greeting']
            elif any(w in msg_lower for w in ['love', 'pyar']):
                responses = CONTENT['responses']['love']
            elif any(w in msg_lower for w in ['morning', 'gm']):
                responses = CONTENT['responses']['morning']
            elif any(w in msg_lower for w in ['night', 'gn']):
                responses = CONTENT['responses']['night']
            else:
                responses = CONTENT['responses']['general']
            
            response = random.choice(responses)
        
        # Add features (private only)
        if not is_group:
            user_data = db.get_user_data(user_id)
            
            # Shayari
            if user_data.get('shayari', True) and random.random() < 0.1:
                if any(w in message.lower() for w in ['love', 'pyar', 'sad']):
                    mood = 'love' if 'love' in message.lower() or 'pyar' in message.lower() else 'sad'
                    if mood in CONTENT['shayari']:
                        shayari = random.choice(CONTENT['shayari'][mood])
                        response = f"{response}\n\n{shayari}"
            
            # Meme
            if user_data.get('meme', True) and random.random() < 0.15:
                meme = random.choice(CONTENT['memes'])
                response = f"{response} {meme}"
            
            # Question
            if random.random() < 0.2:
                q_type = 'flirty' if 'love' in message.lower() else 'casual'
                question = random.choice(CONTENT['questions'][q_type])
                response = f"{response} {question}"
        
        return response

# Initialize response system
response_system = ResponseSystem()

# ==================== UTILITIES ====================

def is_sleeping_time() -> bool:
    """Check sleep time"""
    now = datetime.now(Config.TIMEZONE).time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

async def simulate_typing(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    """Simulate typing"""
    duration = min(3.0, max(1.0, len(text.split()) * 0.3))
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(duration + random.uniform(0.2, 0.5))

# ==================== HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user = update.effective_user
    
    if update.effective_chat.type == "private":
        db.update_user_data(user.id, first_name=user.first_name)
        db.broadcast_list.add(str(user.id))
    
    welcome = f"""🌸 <b>Namaste {user.first_name}!</b>

Main <b>Niyati</b> hoon, ek sweet college girl! 💫

Mujhse normally baat karo, main tumhari dost ban jaungi! 😊"""
    
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)
    logger.info(f"User {user.id} started")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_text = """📚 <b>Help</b>

• Private: Normal baat karo
• Groups: "Niyati" likho
• /meme, /shayari, /geeta - on/off
• /forget - Memory clear"""
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle features"""
    if update.effective_chat.type != "private":
        return
    
    parts = update.message.text.split()
    cmd = parts[0][1:]
    
    if len(parts) < 2:
        await update.message.reply_text(f"/{cmd} on/off")
        return
    
    status = parts[1] == 'on'
    db.update_user_data(update.effective_user.id, **{cmd: status})
    
    await update.message.reply_text(f"{cmd.title()} {'ON ✅' if status else 'OFF ❌'}")

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forget command"""
    if update.effective_chat.type != "private":
        return
    
    user_id = str(update.effective_user.id)
    db.local_storage.pop(user_id, None)
    db._save_local()
    
    await update.message.reply_text("Sab bhul gayi! Fresh start 😊")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast command"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        return
    
    parts = update.message.text.split(maxsplit=2)
    if len(parts) < 3 or parts[1] != Config.BROADCAST_PIN:
        return
    
    message = parts[2]
    count = 0
    
    for user_id in db.broadcast_list:
        try:
            await context.bot.send_message(int(user_id), message)
            count += 1
            await asyncio.sleep(0.1)
        except:
            pass
    
    await update.message.reply_text(f"Sent to {count} users ✅")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        return
    
    stats = f"""📊 <b>Stats</b>
    
👥 Users: {len(db.local_storage)}
💬 Tokens: {ai.tokens_used}
📢 Broadcast: {len(db.broadcast_list)}"""
    
    await update.message.reply_text(stats, parse_mode=ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages"""
    try:
        if not update.message or not update.message.text:
            return
        
        is_private = update.effective_chat.type == "private"
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_msg = update.message.text
        user_name = update.effective_user.first_name
        
        # Group handling
        if not is_private:
            # Check Geeta time
            now = datetime.now(Config.TIMEZONE)
            today = now.date()
            hour = now.hour
            
            if chat_id not in response_system.daily_geeta:
                response_system.daily_geeta[chat_id] = None
            
            if (response_system.daily_geeta[chat_id] != today and
                Config.GEETA_TIME_START.hour <= hour <= Config.GEETA_TIME_END.hour and
                random.random() < 0.1):
                
                quote = random.choice(CONTENT['geeta'])
                await context.bot.send_message(chat_id, f"🌅 Morning Wisdom:\n\n{quote}")
                response_system.daily_geeta[chat_id] = today
                logger.info(f"Sent Geeta to group {chat_id}")
            
            # Check if should reply
            if not response_system.should_reply_in_group(update):
                # Store ephemeral
                if str(chat_id) not in db.ephemeral:
                    db.ephemeral[str(chat_id)] = deque(maxlen=3)
                db.ephemeral[str(chat_id)].append(f"{user_name}: {user_msg[:50]}")
                return
            
            # Update cooldown
            response_system.cooldowns[chat_id] = datetime.now()
        
        # Sleep check
        if is_sleeping_time():
            await update.message.reply_text("So rahi hun yaar... kal baat karte hai 😴")
            return
        
        # Typing
        await simulate_typing(chat_id, user_msg, context)
        
        # Get response
        response = await response_system.get_response(user_msg, user_id, user_name, not is_private)
        
        # Save (private only)
        if is_private:
            db.add_conversation(user_id, user_msg, response)
        
        # Send
        await update.message.reply_text(response)
        logger.info(f"Replied to {user_id} in {'private' if is_private else f'group {chat_id}'}")
        
    except Exception as e:
        logger.error(f"Message error: {e}")
        try:
            await update.message.reply_text("Oops! Kuch gadbad ho gayi 😅")
        except:
            pass

# Media handlers
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    responses = ["Wow! Nice pic 📸", "Kya baat! 😍", "Photo achhi hai! 👌"]
    await update.message.reply_text(random.choice(responses))

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    responses = ["Voice sunke acha laga! 🎤", "Nice voice! 😊", "Tumhari awaaz sweet hai! 💕"]
    await update.message.reply_text(random.choice(responses))

# ==================== FLASK ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "bot": "Niyati",
        "version": "4.0",
        "status": "running"
    })

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy"})

def run_flask():
    logger.info(f"Starting Flask on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT)

# ==================== MAIN ====================

async def main():
    """Main bot function"""
    try:
        Config.validate()
        
        logger.info("="*50)
        logger.info("🌸 Starting Niyati Bot")
        logger.info("="*50)
        
        # Build application  
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("meme", toggle_command))
        app.add_handler(CommandHandler("shayari", toggle_command))
        app.add_handler(CommandHandler("geeta", toggle_command))
        app.add_handler(CommandHandler("forget", forget_command))
        app.add_handler(CommandHandler("broadcast", broadcast_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        
        # Initialize
        await app.initialize()
        await app.start()
        logger.info("✅ Niyati ready!")
        
        # Start polling with conflict handling
        try:
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
        except Conflict:
            logger.warning("⚠️ Another instance may be running, retrying...")
            await asyncio.sleep(5)
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
        
        # Keep running
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"Fatal: {e}")
        raise

if __name__ == "__main__":
    # Flask thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Small delay
    time_module.sleep(1)
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bye! 👋")
    except Exception as e:
        logger.critical(f"Error: {e}")
        sys.exit(1)
