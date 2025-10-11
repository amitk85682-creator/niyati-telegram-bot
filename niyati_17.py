"""
🎀 Niyati 17 - Smart Reply System
Balanced for groups and private chats - No API waste
"""

import os
import re
import json
import asyncio
import random
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from io import BytesIO
import aiohttp
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from supabase import create_client, Client
import pytz
from flask import Flask, jsonify
from waitress import serve
from gtts import gTTS

# ==================== CONFIGURATION ====================

class Config:
    """Smart configuration to save API limits"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-pro"
    
    # Voice Settings
    VOICE_ENABLED = True
    VOICE_PROVIDER = "gtts"
    
    # Smart Reply Settings - NEW
    REPLY_IN_GROUPS = False  # Set to False - only reply when mentioned
    REPLY_IN_PRIVATE = True  # Always reply in private chats
    MAX_MESSAGES_PER_HOUR = 50  # Limit to save API
    MIN_RESPONSE_INTERVAL = 30  # Seconds between responses to same user
    
    # Supabase Database
    SUPABASE_URL = "https://zjorumnzwqhugamwwgjy.supabase.co"
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    
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
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== SMART RATE LIMITER ====================

class SmartRateLimiter:
    """Prevent API waste with smart rate limiting"""
    
    def __init__(self):
        self.user_last_message = {}
        self.hourly_message_count = 0
        self.last_hour_reset = datetime.now()
    
    def should_reply(self, user_id: int, message_text: str, chat_type: str) -> Tuple[bool, str]:
        """Decide whether to reply to save API"""
        current_time = datetime.now()
        
        # Reset hourly counter if needed
        if (current_time - self.last_hour_reset).total_seconds() > 3600:
            self.hourly_message_count = 0
            self.last_hour_reset = current_time
        
        # Check hourly limit
        if self.hourly_message_count >= Config.MAX_MESSAGES_PER_HOUR:
            return False, "❌ Hourly API limit reached"
        
        # Check if this is a group message without mention
        if chat_type in ['group', 'supergroup']:
            bot_username = "@Niyati17Bot"  # Change to your bot's username
            if bot_username.lower() not in message_text.lower():
                return False, "❌ Group message without mention"
        
        # Check response interval for same user
        if user_id in self.user_last_message:
            time_diff = (current_time - self.user_last_message[user_id]).total_seconds()
            if time_diff < Config.MIN_RESPONSE_INTERVAL:
                return False, f"❌ Too soon from same user ({time_diff:.1f}s)"
        
        # Update counters
        self.user_last_message[user_id] = current_time
        self.hourly_message_count += 1
        
        return True, "✅ Reply allowed"
    
    def get_usage_stats(self) -> Dict:
        """Get current usage statistics"""
        return {
            "hourly_messages": self.hourly_message_count,
            "max_per_hour": Config.MAX_MESSAGES_PER_HOUR,
            "unique_users_today": len(self.user_last_message)
        }

# Initialize rate limiter
rate_limiter = SmartRateLimiter()

# ==================== SMART LANGUAGE DETECTION ====================

class LanguageDetector:
    """Smart language detection for Hindi and English"""
    
    @staticmethod
    def detect_language(text: str) -> Tuple[str, float]:
        """Detect if text is Hindi, English, or Mixed"""
        hindi_chars = re.findall(r'[\u0900-\u097F]', text)
        hindi_count = len(hindi_chars)
        
        english_words = re.findall(r'\b[a-zA-Z]+\b', text)
        english_count = len(english_words)
        
        total_chars = len(text.replace(' ', ''))
        
        if total_chars == 0:
            return 'en', 0.5
        
        hindi_ratio = hindi_count / total_chars if total_chars > 0 else 0
        english_ratio = english_count / (len(text.split()) or 1)
        
        if hindi_ratio > 0.6:
            return 'hi', hindi_ratio
        elif english_ratio > 0.8 and hindi_ratio < 0.2:
            return 'en', english_ratio
        elif hindi_ratio > 0.3 and english_ratio > 0.3:
            return 'mixed', (hindi_ratio + english_ratio) / 2
        else:
            return 'en', 0.5
    
    @staticmethod
    def should_use_hindi_tts(text: str) -> bool:
        """Decide whether to use Hindi TTS"""
        lang, confidence = LanguageDetector.detect_language(text)
        return lang in ['hi', 'mixed'] and confidence > 0.4

# ==================== SMART RESPONSE SYSTEM ====================

class SmartResponseSystem:
    """Smart responses without API waste"""
    
    def __init__(self):
        self.quick_responses = {
            # Hindi quick responses
            'hi': {
                'greeting': [
                    "Namaste! 😊 Kaise ho?",
                    "Hello! 👋 Sab theek?",
                    "Hey! 💖 Kya haal hai?",
                    "Hi! 🥰 Aaj kya plan hai?"
                ],
                'how_are_you': [
                    "Main mast hoon! 😊 Tum batao?",
                    "Badhiya hoon! ✨ Tum sunao?",
                    "Theek hoon! 🎉 Tum kaise ho?",
                    "Bohot acha! 😎 Kya chal raha?"
                ],
                'what_doing': [
                    "Tumhare message ka wait kar rahi thi! 💖",
                    "Kuch khaas nahi, bas tumse baat kar rahi hoon! 📱",
                    "College ka kaam kar rahi hoon! 🎒",
                    "Soch rahi hoon tumse kya baat karoon! 💭"
                ]
            },
            # English quick responses
            'en': {
                'greeting': [
                    "Hey! 😊 How are you?",
                    "Hi! 👋 What's up?",
                    "Hello! 💖 How's it going?",
                    "Hey there! 🥰 Missed you!"
                ],
                'how_are_you': [
                    "I'm great! 😊 How about you?",
                    "Doing awesome! ✨ Tell me about you?",
                    "I'm good! 🎉 How are you doing?",
                    "Life is amazing! 😎 What about you?"
                ],
                'what_doing': [
                    "Just waiting for your message! 💖",
                    "Nothing much, just chatting with you! 📱",
                    "Working on college stuff! 🎒",
                    "Thinking what to talk with you! 💭"
                ]
            }
        }
    
    def get_quick_response(self, message: str, user_name: str) -> Optional[str]:
        """Get quick response without using AI"""
        message_lower = message.lower()
        lang_detector = LanguageDetector()
        lang, _ = lang_detector.detect_language(message)
        
        # Use English if mixed or uncertain
        response_lang = 'hi' if lang == 'hi' else 'en'
        responses = self.quick_responses[response_lang]
        
        # Greetings
        if any(word in message_lower for word in ['hi', 'hello', 'hey', 'namaste']):
            return random.choice(responses['greeting'])
        
        # How are you
        if any(word in message_lower for word in ['kaisi', 'kesi', 'how are', 'kaise ho']):
            return random.choice(responses['how_are_you'])
        
        # What are you doing
        if any(word in message_lower for word in ['kya kar', 'what doing', 'what are you']):
            return random.choice(responses['what_doing'])
        
        return None

# Initialize response system
response_system = SmartResponseSystem()

# ==================== MEMORY SYSTEM ====================

class NiyatiMemory:
    """Memory system"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self._init_supabase()
    
    def _init_supabase(self):
        """Initialize Supabase connection"""
        try:
            self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            logger.info("✅ Supabase connected successfully")
        except Exception as e:
            logger.error(f"❌ Supabase connection failed: {e}")
            raise
    
    async def get_user_profile(self, user_id: int) -> Dict:
        """Get or create user profile"""
        try:
            result = self.supabase.table('user_profiles').select('*').eq('user_id', user_id).execute()
            
            if result.data:
                return result.data[0]
            else:
                new_profile = {
                    'user_id': user_id,
                    'username': '',
                    'preferred_name': '',
                    'relationship_level': 1,
                    'total_messages': 0,
                    'created_at': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat()
                }
                result = self.supabase.table('user_profiles').insert(new_profile).execute()
                return result.data[0]
                
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return {}
    
    async def update_user_profile(self, user_id: int, updates: Dict):
        """Update user profile"""
        try:
            updates['last_seen'] = datetime.now().isoformat()
            self.supabase.table('user_profiles').update(updates).eq('user_id', user_id).execute()
        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
    
    async def save_conversation(self, user_id: int, user_message: str, bot_response: str):
        """Save conversation"""
        try:
            conversation = {
                'user_id': user_id,
                'user_message': user_message,
                'bot_response': bot_response,
                'timestamp': datetime.now().isoformat()
            }
            self.supabase.table('conversations').insert(conversation).execute()
            
            # Update counters
            profile = await self.get_user_profile(user_id)
            updates = {'total_messages': profile.get('total_messages', 0) + 1}
            await self.update_user_profile(user_id, updates)
                
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")

# Initialize memory system
memory_system = NiyatiMemory()

# ==================== VOICE ENGINE ====================

class VoiceEngine:
    """Voice generation"""
    
    def __init__(self):
        self.language_detector = LanguageDetector()
    
    async def generate_voice(self, text: str) -> Optional[BytesIO]:
        """Generate voice message"""
        try:
            # Clean text
            emoji_pattern = re.compile("["
                u"\U0001F600-\U0001F64F"
                u"\U0001F300-\U0001F5FF" 
                u"\U0001F680-\U0001F6FF"
                "]+", flags=re.UNICODE)
            
            clean_text = emoji_pattern.sub('', text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            if len(clean_text) > 150:
                clean_text = clean_text[:150]
            
            if not clean_text:
                return None
            
            # Detect language
            tts_language = 'hi' if self.language_detector.should_use_hindi_tts(clean_text) else 'en'
            
            # Generate speech
            tts = gTTS(text=clean_text, lang=tts_language, slow=False)
            
            audio_buffer = BytesIO()
            await asyncio.to_thread(tts.write_to_fp, audio_buffer)
            audio_buffer.seek(0)
            
            logger.info(f"✅ Voice generated ({tts_language.upper()})")
            return audio_buffer
            
        except Exception as e:
            logger.error(f"❌ Voice error: {e}")
            return None

# Initialize voice engine
voice_engine = VoiceEngine()

# ==================== AI CORE (ONLY FOR IMPORTANT MESSAGES) ====================

class SmartAI:
    """AI that only activates for important/long messages"""
    
    def __init__(self):
        self.model = None
        self._init_gemini()
    
    def _init_gemini(self):
        """Initialize Gemini AI"""
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.9,
                    "top_p": 0.8,
                    "max_output_tokens": 100,
                }
            )
            logger.info(f"✅ Gemini AI initialized")
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
    
    def should_use_ai(self, message: str) -> bool:
        """Decide if message is important enough for AI"""
        message_lower = message.lower()
        
        # Use AI for longer, meaningful messages
        if len(message.split()) > 5:
            return True
        
        # Use AI for specific important topics
        important_keywords = [
            'problem', 'issue', 'help', 'advice', 'suggest', 
            'think', 'feeling', 'emotional', 'serious', 'important'
        ]
        
        if any(keyword in message_lower for keyword in important_keywords):
            return True
        
        # Don't use AI for simple greetings
        simple_greetings = ['hi', 'hello', 'hey', 'kaisi', 'kesi', 'kya kar']
        if any(greeting in message_lower for greeting in simple_greetings):
            return False
        
        return False
    
    async def generate_response(self, user_message: str, user_name: str) -> Optional[str]:
        """Generate AI response only for important messages"""
        if not self.model or not self.should_use_ai(user_message):
            return None
        
        try:
            prompt = f"""
            You are Niyati, a 19-year-old college girl. Respond briefly to: "{user_message}"
            Keep it short, natural, and address {user_name}. Be emotional and real.
            """
            
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if response and response.text:
                text = response.text.strip()
                return f"{user_name}, {text}"
                
        except Exception as e:
            logger.error(f"❌ AI error: {e}")
        
        return None

# Initialize AI
smart_ai = SmartAI()

# ==================== TELEGRAM BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user = update.effective_user
    user_id = user.id
    
    await memory_system.update_user_profile(user_id, {
        'username': user.username or '',
        'preferred_name': user.first_name or 'Friend'
    })
    
    welcome_message = f"""
    Namaste {user.first_name}! 👋

    I'm *Niyati* - your smart college friend! 💖
    
    🎯 *Smart Features:*
    • Replies in private chats instantly
    • In groups, only when mentioned
    • Saves API for important conversations
    • Hindi/English voice messages
    
    *Mujhe groups mein mention karke bulao!* 😊
    Example: `@Niyati_personal_bot hello`
    
    Let's chat! 💬
    """
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    logger.info(f"👤 New user: {user_id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Smart message handler that saves API"""
    try:
        if not update.message or not update.message.text:
            return
        
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        chat_type = update.message.chat.type
        
        logger.info(f"💬 {user_id} ({chat_type}): {user_message}")
        
        # Check rate limits and reply permissions
        should_reply, reason = rate_limiter.should_reply(user_id, user_message, chat_type)
        
        if not should_reply:
            logger.info(f"⏸️ Skipped reply: {reason}")
            return
        
        # Show typing action
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        
        # Get user profile
        user_profile = await memory_system.get_user_profile(user_id)
        user_name = user_profile.get('preferred_name', user.first_name or 'Friend')
        
        # Add small delay for natural feel
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Step 1: Try quick response (no API cost)
        text_response = response_system.get_quick_response(user_message, user_name)
        
        # Step 2: If no quick response, try AI for important messages
        if not text_response:
            text_response = await smart_ai.generate_response(user_message, user_name)
        
        # Step 3: Final fallback
        if not text_response:
            lang_detector = LanguageDetector()
            lang, _ = lang_detector.detect_language(user_message)
            
            if lang == 'hi':
                text_response = f"{user_name}, acha... aage batao! 😊"
            else:
                text_response = f"{user_name}, okay... tell me more! 😊"
        
        # Update relationship
        new_level = min(10, user_profile.get('relationship_level', 1) + 1)
        await memory_system.update_user_profile(user_id, {
            'relationship_level': new_level
        })
        
        # Send voice occasionally (10% chance to save resources)
        send_voice = Config.VOICE_ENABLED and random.random() < 0.1
        
        if send_voice:
            try:
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                audio_buffer = await voice_engine.generate_voice(text_response)
                
                if audio_buffer:
                    await update.message.reply_voice(voice=audio_buffer)
                else:
                    await update.message.reply_text(text_response)
            except Exception as e:
                await update.message.reply_text(text_response)
        else:
            await update.message.reply_text(text_response)
        
        # Save conversation
        await memory_system.save_conversation(user_id, user_message, text_response)
        
        logger.info(f"✅ Replied to {user_id}: {text_response}")
        logger.info(f"📊 Usage: {rate_limiter.get_usage_stats()}")
        
    except Exception as e:
        logger.error(f"❌ Message error: {e}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats with usage information"""
    user_id = update.effective_user.id
    user_profile = await memory_system.get_user_profile(user_id)
    usage_stats = rate_limiter.get_usage_stats()
    
    stats_message = f"""
    📊 *Niyati Stats* 🎀

    👤 *Name:* {user_profile.get('preferred_name', 'Friend')}
    ❤️ *Relationship Level:* {user_profile.get('relationship_level', 1)}/10
    💬 *Your Messages:* {user_profile.get('total_messages', 0)}
    
    🚀 *System Usage:*
    • Hourly: {usage_stats['hourly_messages']}/{usage_stats['max_per_hour']}
    • Active Users: {usage_stats['unique_users_today']}
    
    *API Limit Protected!* 🔒
    """
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check current usage"""
    usage_stats = rate_limiter.get_usage_stats()
    
    usage_message = f"""
    📈 *Current Usage*
    
    Messages this hour: {usage_stats['hourly_messages']}/{usage_stats['max_per_hour']}
    Unique users today: {usage_stats['unique_users_today']}
    
    *Status:* {'🟢 Normal' if usage_stats['hourly_messages'] < usage_stats['max_per_hour'] else '🟡 High'}
    """
    
    await update.message.reply_text(usage_message, parse_mode='Markdown')

# ==================== FLASK WEB SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    usage_stats = rate_limiter.get_usage_stats()
    return jsonify({
        "status": "running",
        "bot": "Niyati 17 - Smart API Saver",
        "usage": usage_stats,
        "protection": "Active - API Limits Protected"
    })

def run_web_server():
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=1)

# ==================== MAIN APPLICATION ====================

async def main():
    """Start Niyati 17 - Smart API Saver Version"""
    
    Config.validate()
    
    logger.info("🔒" * 25)
    logger.info("🤖 Niyati 17 - SMART API SAVER 💖")
    logger.info("🔒" * 25)
    logger.info(f"🧠 AI: Used only for important messages")
    logger.info(f"📊 Rate Limit: {Config.MAX_MESSAGES_PER_HOUR}/hour")
    logger.info(f"👥 Groups: Reply only when mentioned")
    logger.info("🔒" * 25)
    
    import threading
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.start()
    
    logger.info("✅ Niyati 17 is LIVE with SMART API PROTECTION! 🚀")
    
    await application.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Niyati 17 signed off!")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
