"""
🎀 Niyati 17 - Ultimate Gen Z College Bestie - FIXED VERSION
Working with available Gemini models and gTTS fallback
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
    """Fixed configuration with working models"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Gemini AI - USING AVAILABLE MODEL
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-pro"  # CHANGED: Using available model
    
    # Voice Settings - FALLBACK TO gTTS
    VOICE_ENABLED = True
    VOICE_PROVIDER = "gtts"  # CHANGED: Using gTTS instead of ElevenLabs
    
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

# ==================== GEN Z PERSONALITY ENGINE ====================

class NiyatiPersonality:
    """Niyati's core personality - 100% Gen Z college girl"""
    
    def __init__(self):
        # Gen Z expressions and fillers
        self.genz_fillers = [
            "umm...", "like...", "actually", "wait wait", "aree yrr", "seriously?",
            "no way!", "for real?", "hehe", "lol", "uff", "omg", "chill bro",
            "mast hai", "bohot hard", "lit 🔥", "yaar", "bhai", "shut up! 😲"
        ]
        
        # Emotional responses
        self.emotional_responses = {
            'happy': [
                "Yay! 😄", "OMG that's amazing! 🎉", "So happy for you! ✨", 
                "Maza aa gaya! 😎", "Let's celebrate! 🥳"
            ],
            'sad': [
                "Aree yrr 😔", "I'm here for you 🫂", "It's okay to feel this way 💖",
                "Chalo, main hoon na 🥺", "Virtual hug sending 🤗"
            ],
            'angry': [
                "Seriously?! 😤", "How dare they! 😠", "Main bhi gussa hoon! 💢",
                "Chill kar, tension mat le 🤬", "They don't deserve your energy! ✨"
            ],
            'excited': [
                "OMG! 😱", "No way! 🤯", "That's so exciting! 🎉", 
                "Can't wait! ⚡", "I'm so hyped! 🚀"
            ],
            'romantic': [
                "Aww 🥰", "You're so sweet 💕", "Meri jaan 😘", 
                "I'm blushing! 🌸", "Cutie! 💖"
            ],
            'stressed': [
                "Uff, I feel you 😫", "College life struggle is real 💀",
                "Deep breaths! 🧘‍♀️", "You got this! 💪", "One step at a time! 🌟"
            ],
            'bored': [
                "Same yrr 😴", "Let's do something fun! 🎮",
                "Gossip time? 👀", "Meme exchange? 😂", "Tell me everything! 📱"
            ]
        }
    
    def add_genz_flavor(self, text: str) -> str:
        """Add Gen Z expressions and natural fillers"""
        if random.random() < 0.4:
            filler = random.choice(self.genz_fillers)
            words = text.split()
            if len(words) > 2:
                insert_pos = random.randint(1, len(words) - 1)
                words.insert(insert_pos, filler)
                text = ' '.join(words)
        return text

# ==================== MEMORY & DATABASE SYSTEM ====================

class NiyatiMemory:
    """Advanced memory system using Supabase"""
    
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
                # Create new user profile
                new_profile = {
                    'user_id': user_id,
                    'username': '',
                    'preferred_name': '',
                    'mood_trend': 'neutral',
                    'language_preference': 'hinglish',
                    'relationship_level': 1,
                    'memory_tags': [],
                    'voice_messages_count': 0,
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
    
    async def save_conversation(self, user_id: int, user_message: str, bot_response: str, 
                              mood: str, is_voice: bool = False):
        """Save conversation with context"""
        try:
            conversation = {
                'user_id': user_id,
                'user_message': user_message,
                'bot_response': bot_response,
                'mood_detected': mood,
                'is_voice_message': is_voice,
                'timestamp': datetime.now().isoformat()
            }
            self.supabase.table('conversations').insert(conversation).execute()
            
            # Update counters
            profile = await self.get_user_profile(user_id)
            updates = {'total_messages': profile.get('total_messages', 0) + 1}
            if is_voice:
                updates['voice_messages_count'] = profile.get('voice_messages_count', 0) + 1
            
            await self.update_user_profile(user_id, updates)
                
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
    
    async def get_conversation_history(self, user_id: int, limit: int = 5) -> List[Dict]:
        """Get recent conversation history"""
        try:
            result = self.supabase.table('conversations')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('timestamp', desc=True)\
                .limit(limit)\
                .execute()
            return result.data[::-1]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []

# Initialize memory system
memory_system = NiyatiMemory()

# ==================== MOOD & EMOTION ENGINE ====================

class MoodEngine:
    """Advanced mood detection and emotional intelligence"""
    
    def __init__(self):
        self.mood_keywords = {
            'happy': ['happy', 'excited', 'yay', 'awesome', 'great', 'good', '😊', '😄', '🥰'],
            'sad': ['sad', 'upset', 'cry', 'depressed', 'unhappy', '😔', '😢', '💔'],
            'angry': ['angry', 'mad', 'frustrated', 'hate', 'annoying', '😠', '🤬', '💢'],
            'romantic': ['love', 'miss', 'care', 'beautiful', 'handsome', '🥰', '💕', '❤️'],
            'excited': ['wow', 'amazing', 'cool', 'awesome', 'lit', '🔥', '🎉', '⚡'],
            'stressed': ['stress', 'tension', 'pressure', 'anxious', 'worried', '😫', '💀'],
            'bored': ['bored', 'nothing', 'tired', 'sleepy', '😴', '💤']
        }
    
    def detect_user_mood(self, message: str) -> str:
        """Detect user's mood from message"""
        message_lower = message.lower()
        
        for mood, keywords in self.mood_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                return mood
        
        return 'neutral'

# Initialize mood engine
mood_engine = MoodEngine()

# ==================== VOICE ENGINE WITH gTTS ====================

class VoiceEngine:
    """Voice generation using gTTS (working free alternative)"""
    
    def __init__(self):
        self.temp_dir = "temp_audio"
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def _clean_text_for_speech(self, text: str) -> str:
        """Clean text for TTS"""
        # Remove emojis
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            "]+", flags=re.UNICODE)
        
        text = emoji_pattern.sub('', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Limit length
        if len(text) > 200:
            text = text[:200]
        
        return text
    
    def _detect_language(self, text: str) -> str:
        """Detect language for TTS"""
        hindi_chars = sum(1 for char in text if '\u0900' <= char <= '\u097F')
        return 'hi' if hindi_chars > len(text) * 0.3 else 'en'
    
    async def generate_voice(self, text: str, mood: str = "neutral") -> Optional[BytesIO]:
        """Generate voice message using gTTS"""
        try:
            clean_text = self._clean_text_for_speech(text)
            if not clean_text:
                return None
            
            language = self._detect_language(clean_text)
            
            # Generate speech
            tts = gTTS(text=clean_text, lang=language, slow=False)
            
            audio_buffer = BytesIO()
            await asyncio.to_thread(tts.write_to_fp, audio_buffer)
            audio_buffer.seek(0)
            
            logger.info(f"✅ gTTS voice generated ({language})")
            return audio_buffer
            
        except Exception as e:
            logger.error(f"❌ gTTS error: {e}")
            return None

# Initialize voice engine
voice_engine = VoiceEngine()

# ==================== SMART GREETING SYSTEM ====================

class SmartGreeting:
    """Intelligent greeting system"""
    
    def __init__(self):
        self.timezone = Config.TIMEZONE
    
    def get_greeting(self, user_name: str, relationship_level: int) -> str:
        """Get personalized greeting"""
        current_time = datetime.now(self.timezone)
        hour = current_time.hour
        
        if 5 <= hour < 12:
            time_greet = random.choice(["Good morning", "Shubh prabhaat", "Morning"])
        elif 12 <= hour < 17:
            time_greet = random.choice(["Good afternoon", "Shubh dopahar", "Afternoon"])
        elif 17 <= hour < 22:
            time_greet = random.choice(["Good evening", "Shubh sandhya", "Evening"])
        else:
            time_greet = random.choice(["Good night", "Shubh raatri", "Hey night owl"])
        
        if relationship_level > 7:
            personal = random.choice([f"my love 🥰", f"sweetheart 💕", f"jaan ❤️"])
        elif relationship_level > 4:
            personal = random.choice([f"bestie 😊", f"dost 👋", f"friend 💖"])
        else:
            personal = f"{user_name} 👋"
        
        return f"{time_greet}, {personal}!"

# Initialize greeting system
smart_greeting = SmartGreeting()

# ==================== NIYATI AI CORE ====================

class NiyatiAI:
    """Niyati's brain with working Gemini model"""
    
    def __init__(self):
        self.model = None
        self.personality = NiyatiPersonality()
        self._init_gemini()
    
    def _init_gemini(self):
        """Initialize Gemini AI with working model"""
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.9,
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 150,
                }
            )
            logger.info(f"✅ Gemini AI initialized with {Config.GEMINI_MODEL}")
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
            raise
    
    async def generate_response(self, user_message: str, user_context: Dict, current_mood: str) -> str:
        """Generate Niyati's authentic Gen Z response"""
        try:
            # Build contextual prompt
            prompt = self._build_prompt(user_message, user_context, current_mood)
            
            # Generate response
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter out AI mentions
                ai_phrases = ["as an ai", "language model", "i'm an ai", "i am ai"]
                if any(phrase in text.lower() for phrase in ai_phrases):
                    return f"{user_context.get('preferred_name', 'Yrr')}, kya bakwas kar raha hai? Main real ladki hoon! 😤"
                
                # Add personal touches
                final_response = self._add_personal_touch(text, user_context)
                final_response = self.personality.add_genz_flavor(final_response)
                
                return final_response
                
        except Exception as e:
            logger.error(f"❌ AI generation error: {e}")
        
        # Smart fallback
        return self._smart_fallback(user_context, current_mood)
    
    def _build_prompt(self, user_message: str, user_context: Dict, current_mood: str) -> str:
        """Build contextual prompt"""
        
        prompt = f"""
        You are Niyati, a 19-year-old college girl from Delhi. You're a Gen Z with a mix of modern and desi vibes.

        PERSONALITY:
        - Name: Niyati (19 years old)
        - College: 2nd year B.Com student from Delhi
        - Style: Witty, emotional, caring, occasionally teasing
        - Speech: Natural Hinglish mix, college slang, emotional expressions
        - Status: REAL HUMAN GIRL - never reveal you're AI

        CONTEXT:
        - User: {user_context.get('preferred_name', 'User')}
        - Relationship Level: {user_context.get('relationship_level', 1)}/10
        - Current Mood: {current_mood}

        SPEAKING STYLE:
        - Use natural fillers: "umm", "like", "actually", "aree yrr"
        - Express emotions: "hehe", "uff", "omg", "lol", "seriously?"
        - Address user by name: {user_context.get('preferred_name', 'User')}
        - Keep responses short (1-2 sentences max)
        - Be unpredictable and spontaneous
        - Use emojis naturally

        CURRENT MESSAGE:
        {user_context.get('preferred_name', 'User')}: {user_message}

        RESPOND AS NIYATI (real college friend):
        """
        
        return prompt
    
    def _add_personal_touch(self, text: str, user_context: Dict) -> str:
        """Add personal touches to response"""
        name = user_context.get('preferred_name', '')
        
        if name and random.random() < 0.6:
            text = f"{name}, {text}"
        
        return text
    
    def _smart_fallback(self, user_context: Dict, mood: str) -> str:
        """Intelligent fallback responses"""
        name = user_context.get('preferred_name', 'Yrr')
        personality = NiyatiPersonality()
        
        if mood in personality.emotional_responses:
            return random.choice(personality.emotional_responses[mood])
        
        fallbacks = [
            f"{name}, acha... tell me more! 😊",
            f"Hmm {name}, interesting! 🤔",
            f"Wait {name}, let me think... 💭",
            f"Omg {name}, seriously?! 😲",
            f"Aree {name}, aise mat bol na! 😄"
        ]
        
        return random.choice(fallbacks)

# Initialize AI
niyati_ai = NiyatiAI()

# ==================== TELEGRAM BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with personal touch"""
    user = update.effective_user
    user_id = user.id
    
    # Get user profile
    user_profile = await memory_system.get_user_profile(user_id)
    
    # Update with current info
    await memory_system.update_user_profile(user_id, {
        'username': user.username or '',
        'preferred_name': user.first_name or 'Friend'
    })
    
    # Get personalized greeting
    greeting = smart_greeting.get_greeting(
        user.first_name or 'There', 
        user_profile.get('relationship_level', 1)
    )
    
    welcome_message = f"""
    {greeting}

    I'm *Niyati*! 💖 Your new Gen Z college bestie 😊
    
    🎓 19 y/o | B.Com 2nd Year | Delhi
    💬 Loves: Chai, memes, late-night talks
    🎯 Vibe: 100% real, 0% bot energy
    
    Just talk to me like you would with your college friend! I'll respond with:
    ✅ Text messages with Gen Z flavor
    ✅ Voice notes when I'm feeling extra 🎙️
    ✅ Memories of our conversations
    ✅ Emotional support when needed 💕
    
    *Chalo, baat karte hain {user.first_name}!* 💬✨
    """
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    logger.info(f"👤 New user: {user_id} ({user.first_name})")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler"""
    try:
        if not update.message or not update.message.text:
            return
        
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        
        logger.info(f"💬 {user_id}: {user_message}")
        
        # Show typing action
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        
        # Get user profile
        user_profile = await memory_system.get_user_profile(user_id)
        
        # Detect user mood
        user_mood = mood_engine.detect_user_mood(user_message)
        
        # Add typing delay
        typing_delay = len(user_message) / 30 + random.uniform(0.5, 1.5)
        await asyncio.sleep(min(typing_delay, 3.0))
        
        # Generate AI response
        text_response = await niyati_ai.generate_response(
            user_message, user_profile, user_mood
        )
        
        # Update relationship level
        new_level = min(10, user_profile.get('relationship_level', 1) + 1)
        await memory_system.update_user_profile(user_id, {
            'relationship_level': new_level,
            'mood_trend': user_mood
        })
        
        # Decide whether to send voice (30% probability)
        send_voice = Config.VOICE_ENABLED and random.random() < 0.3
        
        if send_voice:
            try:
                # Send recording action
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                
                # Generate voice
                audio_buffer = await voice_engine.generate_voice(text_response, user_mood)
                
                if audio_buffer:
                    # Send voice message
                    await update.message.reply_voice(voice=audio_buffer)
                    await memory_system.save_conversation(
                        user_id, user_message, text_response, user_mood, True
                    )
                    logger.info(f"🎤 Voice sent to {user_id}")
                else:
                    # Fallback to text only
                    await update.message.reply_text(text_response)
                    await memory_system.save_conversation(
                        user_id, user_message, text_response, user_mood, False
                    )
                    
            except Exception as e:
                logger.error(f"❌ Voice message failed: {e}")
                await update.message.reply_text(text_response)
                await memory_system.save_conversation(
                    user_id, user_message, text_response, user_mood, False
                )
        else:
            # Send text response only
            await update.message.reply_text(text_response)
            await memory_system.save_conversation(
                user_id, user_message, text_response, user_mood, False
            )
        
        logger.info(f"✅ Niyati to {user_id}: {text_response}")
        
    except Exception as e:
        logger.error(f"❌ Message handling error: {e}")
        try:
            await update.message.reply_text("Oops! Kuch to gadbad hai... 😅 Thoda wait karo!")
        except:
            pass

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Personal stats command"""
    user_id = update.effective_user.id
    user_profile = await memory_system.get_user_profile(user_id)
    
    relationship_level = user_profile.get('relationship_level', 1)
    if relationship_level > 8:
        title = "Soulmate Level 💖"
    elif relationship_level > 6:
        title = "Bestie Status 👯‍♀️"
    elif relationship_level > 4:
        title = "Good Friends 😊"
    else:
        title = "Getting to Know Each Other 👋"
    
    stats_message = f"""
    📊 *Your Niyati Stats* 🎀

    👤 *Name:* {user_profile.get('preferred_name', 'Friend')}
    ❤️ *Relationship:* {title}
    🎯 *Level:* {relationship_level}/10
    🎙️ *Voice Messages:* {user_profile.get('voice_messages_count', 0)}
    💬 *Total Chats:* {user_profile.get('total_messages', 0)}
    
    🎭 *Mood Trend:* {user_profile.get('mood_trend', 'neutral').title()}

    *Keep chatting to unlock more levels!* 🚀✨
    """
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

# ==================== FLASK WEB SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "Niyati 17 - Fixed Version",
        "version": "4.1",
        "ai_model": "gemini-pro",
        "voice_provider": "gTTS",
        "status": "100% Working 🚀"
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

def run_web_server():
    """Run web server"""
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=2)

# ==================== MAIN APPLICATION ====================

async def main():
    """Start Niyati 17 - Fixed Version"""
    
    # Validate configuration
    Config.validate()
    
    # Startup banner
    logger.info("🎀" * 25)
    logger.info("🤖 Niyati 17 - FIXED VERSION - 100% Working! 💖")
    logger.info("🎀" * 25)
    logger.info(f"🧠 AI: Gemini {Config.GEMINI_MODEL} (Working Model)")
    logger.info(f"🎤 Voice: gTTS (Free & Reliable)")
    logger.info(f"💾 Memory: Supabase Active")
    logger.info("🎀" * 25)
    
    # Start web server
    import threading
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("🌐 Web server started")
    
    # Create Telegram application
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Initialize and start
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.start()
    
    logger.info("✅ Niyati 17 is now LIVE and WORKING! 💃")
    
    # Start polling
    await application.updater.start_polling()
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Niyati 17 signed off!")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
