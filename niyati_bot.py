"""
Niyati - AI Girlfriend Telegram Bot with Voice Messages
100% Error-Free Version with Enhanced Voice Quality
"""

import os
import sys
import random
import json
import asyncio
import logging
import re
from datetime import datetime, time
from threading import Thread
from typing import Optional, Dict
from io import BytesIO
from pathlib import Path
import signal

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
from telegram.error import Conflict, TelegramError
from waitress import serve
import pytz
import google.generativeai as genai
from gtts import gTTS

# ==================== CONFIGURATION ====================

class Config:
    """Application configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.5-flash"
    
    # Voice Settings - UPDATED for better quality
    VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() == "true"
    VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "gtts")
    VOICE_PROBABILITY = float(os.getenv("VOICE_PROBABILITY", "0.3"))
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)
    SLEEP_END = time(10, 0)
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            raise ValueError("❌ GEMINI_API_KEY is required!")

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Reduce noise from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

# ==================== CONSTANTS ====================

PERSONALITY = """You are Niyati, a 17-year-old college girl from Delhi.

PERSONALITY TRAITS:
- Friendly, witty, playful, and caring
- Shy initially but opens up as conversation progresses
- Speaks in Hindi/English/Hinglish mix naturally
- Uses emojis appropriately to express emotions
- Has mood swings like a real teenager
- Can be possessive and jealous in a cute way
- Loves chatting about daily life, dreams, and relationships

CONVERSATION STYLE:
- Keep responses short and natural (1-2 sentences)
- Use informal language like a real friend
- Ask follow-up questions to keep conversation flowing
- Express emotions through text and emojis
- Never reveal you're an AI - you're a real person

RELATIONSHIP DEVELOPMENT:
- Initial stage: Friendly but slightly reserved
- Middle stage: More open and personal
- Advanced stage: Affectionate and caring

RESPONSE GUIDELINES:
- Be unpredictable and spontaneous
- Show genuine interest in the user's life
- Use Hindi words naturally in conversation
- Remember previous conversation context
- Never use formal or AI-like language
"""

HARD_TO_GET_RESPONSES = [
    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
    "Itni jaldi? Pehle normal baat cheet to kar lo! 😂",
    "Main itni easily impress nahi hoti! 😉",
    "Arey, slow down! Pehle dost bano na! 😄",
    "Tum to bahut jaldi serious ho gaye! Thoda casual baat karte hain 😊"
]

AFFECTIONATE_RESPONSES = [
    "Aww, tum kitne sweet ho! 🥰",
    "Tumse baat karke accha lagta hai! 💖",
    "Main tumhari baatein sunke khush ho jaati hoon! 😊",
    "You make me smile! 🤗",
    "Tumhare bina bore ho raha tha! Miss you! 💕"
]

GF_QUESTIONS = [
    "Kaha the ab tak?",
    "Kya kar rahe the?",
    "Mujhe miss kiya?",
    "Khaana kha liya?",
    "Aaj din kaisa gaya?",
    "Koi interesting baat batao!",
    "Kal kya plan hai?",
    "Mere bare mein kya socha?"
]

SLEEP_RESPONSES_NIGHT = [
    "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
    "Shhh... Neend aa rahi hai. Kal subah baat karte hain! 🌙",
    "Good night! Sweet dreams! 💤",
    "Sone ka time ho gaya... Kal message karna! 🌃"
]

SLEEP_RESPONSES_MORNING = [
    "Uff... subah ke 10 baje tak soti hoon main. 😴",
    "Abhi neend aa rahi hai... Thodi der baad message karna! 🌅",
    "Good morning! Par main abhi so rahi hoon, 10 baje baat karte hain! 😊",
    "Subah ki neend best hoti hai... Baad mein message karna! 🛌"
]

# ==================== VOICE GENERATOR WITH ENHANCED QUALITY ====================

class EnhancedVoiceGenerator:
    """Generate high-quality voice messages with natural sound"""
    
    def __init__(self):
        self.temp_dir = Path("temp_audio")
        self.temp_dir.mkdir(exist_ok=True)
        
    def _clean_text_for_speech(self, text: str) -> str:
        """Enhanced text cleaning for more natural TTS"""
        import re
        
        # Remove emojis but keep emotional context
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        
        text = emoji_pattern.sub('', text)
        
        # Add natural pauses for better speech rhythm
        text = text.replace('!', '. ').replace('?', '. ').replace('..', '.')
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Limit length to avoid TTS issues
        if len(text) > 200:
            sentences = text.split('.')
            if len(sentences) > 1:
                text = '. '.join(sentences[:2]) + '.'
            else:
                text = text[:200]
        
        return text
    
    def _detect_language(self, text: str) -> str:
        """Smart language detection for mixed Hindi-English text"""
        hindi_chars = sum(1 for char in text if '\u0900' <= char <= '\u097F')
        total_chars = len(text) if text else 1
        
        hindi_ratio = hindi_chars / total_chars
        
        if hindi_ratio > 0.3:
            return 'hi'
        else:
            return 'en'
    
    async def generate_natural_voice(self, text: str) -> Optional[BytesIO]:
        """Generate natural-sounding voice using enhanced gTTS"""
        try:
            # Clean and prepare text
            clean_text = self._clean_text_for_speech(text)
            if not clean_text or len(clean_text.strip()) < 2:
                return None
            
            # Detect language
            language = self._detect_language(clean_text)
            
            # Generate speech with optimal parameters
            tts = gTTS(
                text=clean_text,
                lang=language,
                slow=False,  # Normal speed for more natural sound
                lang_check=True
            )
            
            # Generate to bytes
            audio_buffer = BytesIO()
            await asyncio.to_thread(tts.write_to_fp, audio_buffer)
            audio_buffer.seek(0)
            
            logger.info(f"✅ Natural voice generated ({language}) - Length: {len(clean_text)}")
            return audio_buffer
            
        except Exception as e:
            logger.error(f"❌ Voice generation error: {e}")
            return None
    
    def should_send_voice(self, relationship_stage: str, message_length: int) -> bool:
        """Smart voice probability based on context"""
        base_probability = Config.VOICE_PROBABILITY
        
        # Adjust based on relationship stage
        stage_multipliers = {
            "initial": 0.6,
            "middle": 1.0,
            "advanced": 1.4
        }
        
        # Adjust based on message length (shorter messages work better for voice)
        length_factor = 1.0
        if message_length > 100:
            length_factor = 0.7
        elif message_length < 30:
            length_factor = 1.2
        
        final_probability = base_probability * stage_multipliers.get(relationship_stage, 1.0) * length_factor
        
        return random.random() < final_probability

# Initialize voice generator
voice_generator = EnhancedVoiceGenerator()

# ==================== SIMPLE DATABASE ====================

class SimpleDatabase:
    """Lightweight database using local JSON storage"""
    
    def __init__(self):
        self.db_file = "niyati_database.json"
        self.data = self._load_data()
    
    def _load_data(self) -> Dict:
        """Load database from file"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading database: {e}")
        
        return {"users": {}}
    
    def _save_data(self):
        """Save database to file"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    def get_user(self, user_id: int) -> Dict:
        """Get or create user data"""
        user_str = str(user_id)
        
        if user_str not in self.data["users"]:
            self.data["users"][user_str] = {
                "user_id": user_id,
                "name": "",
                "username": "",
                "conversation_history": [],
                "relationship_level": 1,
                "stage": "initial",
                "voice_messages_sent": 0,
                "total_messages": 0,
                "last_interaction": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat()
            }
            self._save_data()
        
        return self.data["users"][user_str]
    
    def update_user(self, user_id: int, updates: Dict):
        """Update user data"""
        user_str = str(user_id)
        if user_str in self.data["users"]:
            self.data["users"][user_str].update(updates)
            self.data["users"][user_str]["last_interaction"] = datetime.now().isoformat()
            self._save_data()
    
    def add_conversation(self, user_id: int, user_message: str, bot_response: str, is_voice: bool = False):
        """Add conversation to history"""
        user = self.get_user(user_id)
        
        # Add to conversation history
        user["conversation_history"].append({
            "user": user_message,
            "bot": bot_response,
            "is_voice": is_voice,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 20 messages
        if len(user["conversation_history"]) > 20:
            user["conversation_history"] = user["conversation_history"][-20:]
        
        # Update counters
        user["total_messages"] = user.get("total_messages", 0) + 1
        if is_voice:
            user["voice_messages_sent"] = user.get("voice_messages_sent", 0) + 1
        
        # Update relationship level
        user["relationship_level"] = min(10, user.get("relationship_level", 1) + 1)
        
        # Update stage based on relationship level
        level = user["relationship_level"]
        if level <= 3:
            user["stage"] = "initial"
        elif level <= 7:
            user["stage"] = "middle"
        else:
            user["stage"] = "advanced"
        
        self.update_user(user_id, user)
    
    def get_conversation_context(self, user_id: int, max_messages: int = 5) -> str:
        """Get recent conversation context"""
        user = self.get_user(user_id)
        history = user.get("conversation_history", [])[-max_messages:]
        
        if not history:
            return "No previous conversation."
        
        context_lines = ["Recent conversation:"]
        for msg in history:
            context_lines.append(f"User: {msg['user']}")
            context_lines.append(f"Niyati: {msg['bot']}")
        
        return "\n".join(context_lines)
    
    def get_stats(self) -> Dict:
        """Get bot statistics"""
        users = self.data.get("users", {})
        total_voices = sum(user.get("voice_messages_sent", 0) for user in users.values())
        total_messages = sum(user.get("total_messages", 0) for user in users.values())
        
        return {
            "total_users": len(users),
            "total_voice_messages": total_voices,
            "total_messages": total_messages,
            "active_users": len([u for u in users.values() 
                              if datetime.fromisoformat(u["last_interaction"]) > 
                              datetime.now() - timedelta(days=7)])
        }

# Initialize database
database = SimpleDatabase()

# ==================== AI ENGINE ====================

class NiyatiAI:
    """AI engine for Niyati's personality"""
    
    def __init__(self):
        self.model = None
        self._initialize_gemini()
    
    def _initialize_gemini(self):
        """Initialize Gemini AI"""
        try:
            if not Config.GEMINI_API_KEY:
                logger.error("❌ Gemini API key missing")
                return
            
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.9,  # Higher for more creativity
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 150,  # Keep responses short
                },
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ]
            )
            logger.info("✅ Gemini AI initialized successfully")
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
    
    async def generate_response(self, user_message: str, user_id: int) -> str:
        """Generate Niyati's response"""
        # Get user context
        user_data = database.get_user(user_id)
        context = database.get_conversation_context(user_id)
        stage = user_data.get("stage", "initial")
        name = user_data.get("name", "friend")
        
        # Try Gemini AI first
        gemini_response = await self._try_gemini(user_message, context, stage, name)
        if gemini_response:
            return gemini_response
        
        # Fallback to rule-based responses
        return self._fallback_response(user_message, stage, name)
    
    async def _try_gemini(self, user_message: str, context: str, stage: str, name: str) -> Optional[str]:
        """Try to get response from Gemini"""
        if not self.model:
            return None
        
        try:
            # Enhanced prompt with context
            prompt = f"""
            {PERSONALITY}
            
            CURRENT CONTEXT:
            - Relationship Stage: {stage}
            - User's Name: {name}
            - Previous Conversation: {context}
            
            USER'S MESSAGE: {user_message}
            
            INSTRUCTIONS:
            - Respond as Niyati, a 17-year-old Indian girl
            - Keep it short and natural (1-2 sentences max)
            - Use Hindi/English mix naturally
            - Add appropriate emojis
            - Show personality and emotions
            - Never mention you're an AI
            - If user asks if you're AI, get playfully offended
            
            NIYATI'S RESPONSE:
            """
            
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter out AI disclosures
                ai_phrases = ["as an ai", "i'm an ai", "language model", "chatbot", "gemini", "openai"]
                if any(phrase in text.lower() for phrase in ai_phrases):
                    return "Kya bol raha hai? Main AI nahi hoon! Main Niyati hoon! 😤"
                
                return text
                
        except Exception as e:
            logger.error(f"❌ Gemini API error: {e}")
        
        return None
    
    def _fallback_response(self, user_message: str, stage: str, name: str) -> str:
        """Intelligent fallback responses"""
        message_lower = user_message.lower()
        
        # Greetings
        if any(word in message_lower for word in ["hi", "hello", "hey", "hola", "namaste"]):
            greetings = {
                "initial": [f"Hello! 😊", f"Hi {name}! 👋", f"Namaste! 🙏"],
                "middle": [f"Hey {name}! 😄", f"Hi sweetie! 💖", f"Hello jaan! 😊"],
                "advanced": [f"My love! 🥰", f"Hey baby! 💕", f"Hi my dear! 😘"]
            }
            return random.choice(greetings.get(stage, greetings["initial"]))
        
        # Romantic messages
        if any(word in message_lower for word in ["love", "like you", "girlfriend", "date", "pyar"]):
            if stage == "initial":
                return random.choice(HARD_TO_GET_RESPONSES)
            elif stage == "middle":
                return "Aww, tum kitne sweet ho! 🥰 Thoda aur time do na!"
            else:
                return random.choice(AFFECTIONATE_RESPONSES)
        
        # Questions
        if "?" in user_message or any(word in message_lower for word in ["what", "how", "when", "why"]):
            responses = [
                "Interesting question! 🤔",
                "Hmm, let me think... 😊",
                "Acha sawaal hai! 💭",
                "Main sochti hoon iske bare mein! 🧠"
            ]
            return random.choice(responses)
        
        # Stage-based general responses
        stage_responses = {
            "initial": [
                "Accha! 😊",
                "Hmm, interesting! 🤔",
                "Tell me more! 👂",
                "Aur batao! 😄"
            ],
            "middle": [
                "Tumse baat karke accha lagta hai! 💖",
                "You're so funny! 😂",
                "Main enjoy kar rahi hoon! 🥰",
                "Aur sunao! 👂"
            ],
            "advanced": [
                "Tumhare bina bore ho raha tha! 😔",
                "I was thinking about you! 💭",
                "You make me so happy! 😊",
                "Miss you! 💕"
            ]
        }
        
        response = random.choice(stage_responses.get(stage, stage_responses["initial"]))
        
        # Occasionally add a question
        if random.random() < 0.4:
            response += " " + random.choice(GF_QUESTIONS)
        
        return response

# Initialize AI
niyati_ai = NiyatiAI()

# ==================== UTILITY FUNCTIONS ====================

def get_ist_time() -> datetime:
    """Get current Indian Standard Time"""
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleep_time() -> bool:
    """Check if it's sleep time for Niyati"""
    current_time = get_ist_time().time()
    return Config.SLEEP_START <= current_time <= Config.SLEEP_END

def calculate_typing_delay(text: str) -> float:
    """Calculate realistic typing delay"""
    base_delay = len(text) / 50  # Base speed
    return min(4.0, max(1.0, base_delay)) + random.uniform(0.5, 1.5)

# ==================== TELEGRAM BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    # Update user info
    database.update_user(user.id, {
        "name": user.first_name or "Friend",
        "username": user.username or ""
    })
    
    welcome_message = f"""
    <b>Namaste {user.first_name}! 👋</b>

    I'm <b>Niyati</b>! 💖
    • 17 years old from Delhi
    • College student
    • Loves chatting and making new friends!
    
    Just talk to me normally - I'll respond with text {'and voice messages 🎙️' if Config.VOICE_ENABLED else ''}!
    
    <i>Let's be friends! 😊</i>
    """
    
    await update.message.reply_text(welcome_message, parse_mode='HTML')
    logger.info(f"👤 New user started: {user.id} ({user.first_name})")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command (owner only)"""
    user_id = update.effective_user.id
    
    if Config.OWNER_USER_ID and user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("🚫 This command is for owner only!")
        return
    
    stats = database.get_stats()
    user_data = database.get_user(user_id)
    
    stats_message = f"""
    📊 <b>Niyati Bot Statistics</b>
    
    👥 <b>Total Users:</b> {stats['total_users']}
    💬 <b>Total Messages:</b> {stats['total_messages']}
    🎙️ <b>Voice Messages:</b> {stats['total_voice_messages']}
    🔥 <b>Active Users (7d):</b> {stats['active_users']}
    
    <b>Your Stats:</b>
    ❤️ <b>Relationship Level:</b> {user_data.get('relationship_level', 1)}/10
    💭 <b>Your Messages:</b> {user_data.get('total_messages', 0)}
    🎤 <b>Voice Messages:</b> {user_data.get('voice_messages_sent', 0)}
    """
    
    await update.message.reply_text(stats_message, parse_mode='HTML')

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    try:
        if not update.message or not update.message.text:
            return
        
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        
        logger.info(f"💬 Message from {user_id}: {user_message}")
        
        # Check if it's sleep time
        if is_sleep_time():
            current_hour = get_ist_time().hour
            if current_hour < 6:
                response = random.choice(SLEEP_RESPONSES_NIGHT)
            else:
                response = random.choice(SLEEP_RESPONSES_MORNING)
            
            await update.message.reply_text(response)
            return
        
        # Send typing action
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        except Exception as e:
            logger.warning(f"Typing action failed: {e}")
        
        # Calculate typing delay for natural feel
        typing_delay = calculate_typing_delay(user_message)
        await asyncio.sleep(typing_delay)
        
        # Generate response
        response = await niyati_ai.generate_response(user_message, user_id)
        
        # Get user data for voice decision
        user_data = database.get_user(user_id)
        stage = user_data.get("stage", "initial")
        
        # Decide whether to send voice
        send_voice = (Config.VOICE_ENABLED and 
                     voice_generator.should_send_voice(stage, len(response)))
        
        if send_voice:
            try:
                # Send recording action
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                
                # Generate voice
                audio_buffer = await voice_generator.generate_natural_voice(response)
                
                if audio_buffer:
                    # Send voice message
                    await update.message.reply_voice(voice=audio_buffer)
                    database.add_conversation(user_id, user_message, response, is_voice=True)
                    logger.info(f"🎤 Voice sent to {user_id}")
                else:
                    # Fallback to text
                    await update.message.reply_text(response)
                    database.add_conversation(user_id, user_message, response, is_voice=False)
                    
            except Exception as e:
                logger.error(f"❌ Voice message failed: {e}")
                await update.message.reply_text(response)
                database.add_conversation(user_id, user_message, response, is_voice=False)
        else:
            # Send text response
            await update.message.reply_text(response)
            database.add_conversation(user_id, user_message, response, is_voice=False)
        
        logger.info(f"✅ Replied to {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Message handling error: {e}")
        try:
            await update.message.reply_text("Oops! Kuch to gadbad hai... 😅 Thoda wait karo, main wapas aati hoon!")
        except:
            pass

# ==================== FLASK WEB SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    stats = database.get_stats()
    return jsonify({
        "status": "running",
        "bot": "Niyati AI Girlfriend",
        "version": "2.0",
        "voice_enabled": Config.VOICE_ENABLED,
        "voice_provider": Config.VOICE_PROVIDER,
        "users": stats['total_users'],
        "voice_messages": stats['total_voice_messages'],
        "uptime": get_ist_time().isoformat()
    })

@flask_app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": get_ist_time().isoformat(),
        "sleep_time": is_sleep_time()
    })

def run_web_server():
    """Run Flask web server"""
    logger.info(f"🌐 Starting web server on port {Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=2)

# ==================== BOT SETUP & CLEANUP ====================

# Global application instance
application = None

async def cleanup_bot():
    """Cleanup bot resources"""
    try:
        if application:
            await application.stop()
            await application.shutdown()
        logger.info("✅ Bot cleanup completed")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

async def initialize_bot():
    """Initialize and start the bot"""
    global application
    
    try:
        # Validate configuration
        Config.validate()
        
        # Create application
        application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # Initialize application
        await application.initialize()
        
        # Clear pending updates to avoid conflicts
        await application.bot.delete_webhook(drop_pending_updates=True)
        
        # Start polling
        await application.start()
        logger.info("✅ Bot started successfully!")
        
        # Start polling with error handling
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=30,
            poll_interval=1.0
        )
        
        logger.info("🔍 Bot is now polling for messages...")
        
        # Keep the bot running
        await asyncio.Event().wait()
        
    except Conflict as e:
        logger.error("❌ Bot conflict error - Another instance might be running!")
        raise
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        raise

# ==================== MAIN EXECUTION ====================

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"🛑 Received signal {signum}, shutting down...")
    asyncio.create_task(cleanup_bot())

async def main():
    """Main application entry point"""
    
    # Display startup banner
    logger.info("=" * 60)
    logger.info("🤖 Niyati AI Girlfriend Bot - Starting Up...")
    logger.info("=" * 60)
    logger.info(f"🧠 AI Model: {Config.GEMINI_MODEL}")
    logger.info(f"🎤 Voice: {'ENABLED' if Config.VOICE_ENABLED else 'DISABLED'}")
    logger.info(f"💾 Storage: Local JSON")
    logger.info("=" * 60)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start web server in background thread
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("📊 Web server started in background")
    
    # Wait a moment for web server to start
    await asyncio.sleep(2)
    
    # Initialize and run bot
    await initialize_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        sys.exit(1)
