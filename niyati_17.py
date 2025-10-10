"""
🎀 Niyati 17 - Ultimate Gen Z College Bestie - FULLY WORKING VERSION
With enhanced responses and better AI integration
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
    """Configuration with enhanced settings"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Gemini AI - Using working model
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-pro"
    
    # Voice Settings
    VOICE_ENABLED = True
    VOICE_PROVIDER = "gtts"
    
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

# ==================== ENHANCED PERSONALITY ENGINE ====================

class NiyatiPersonality:
    """Enhanced personality with contextual responses"""
    
    def __init__(self):
        # Gen Z expressions
        self.genz_fillers = [
            "umm...", "like...", "actually", "wait wait", "aree yrr", "seriously?",
            "no way!", "for real?", "hehe", "lol", "uff", "omg", "chill bro",
            "mast hai", "bohot hard", "lit 🔥", "yaar", "bhai", "shut up! 😲"
        ]
        
        # Contextual responses for common questions
        self.contextual_responses = {
            'greeting': [
                "Hey {name}! 😊 Kya haal chaal?",
                "Hi {name}! 👋 Aaj kya plan hai?",
                "Hello {name}! 💖 Kaisi chal rahi hai life?",
                "Heyyy {name}! 🥰 Missed you!",
                "Omg {name}! 😄 Finally message kiya!"
            ],
            'how_are_you': [
                "Main to mast hoon {name}! 😊 Tum batao?",
                "Badhiya {name}! ✨ Tum sunao?",
                "Zindagi awesome chal rahi hai {name}! 🎉 Tum batao kya chal raha?",
                "Bohot heavy hai life {name}! 😎 Kya haal hai?",
                "Main to ekdum jhakaas hoon {name}! 💃 Tum?"
            ],
            'what_doing': [
                "Bas {name}, tumhare message ka wait kar rahi thi! 💖",
                "Kuch khaas nahi {name}, just chilling! 😊 Tum batao?",
                "Phone pe thi {name}, socha tumse baat kar loon! 📱",
                "College se aayi hoon {name}, thoda rest kar rahi hoon! 🎒",
                "Tumhare bare mein soch rahi thi {name}! 💭"
            ],
            'asking_again': [
                "Aree {name}, main to bol hi rahi hoon! 😄 Tum batao kya chal raha?",
                "Hehe {name}, pehle tum batao kaisi ho? 😊",
                "Wait {name}, tum pehle batao! 👀 Main to theek hoon!",
                "Omg {name}, itni curiosity? 😂 Main mast hoon! Tum?"
            ]
        }
        
        # Emotional responses
        self.emotional_responses = {
            'happy': ["Yay! 😄", "OMG that's amazing! 🎉", "So happy for you! ✨"],
            'sad': ["Aree yrr 😔", "I'm here for you 🫂", "It's okay 💖"],
            'angry': ["Seriously?! 😤", "How dare they! 😠", "Chill kar! 🤬"],
            'excited': ["OMG! 😱", "No way! 🤯", "That's so exciting! 🎉"],
            'romantic': ["Aww 🥰", "You're so sweet 💕", "I'm blushing! 🌸"],
            'stressed': ["Uff, I feel you 😫", "Deep breaths! 🧘‍♀️", "You got this! 💪"],
            'bored': ["Same yrr 😴", "Let's do something fun! 🎮", "Meme exchange? 😂"]
        }
    
    def get_contextual_response(self, message: str, user_name: str) -> Optional[str]:
        """Get contextual response based on message content"""
        message_lower = message.lower()
        
        # Greetings
        if any(word in message_lower for word in ['hi', 'hello', 'hey', 'hola']):
            return random.choice(self.contextual_responses['greeting']).format(name=user_name)
        
        # How are you
        if any(word in message_lower for word in ['kaisi', 'kesi', 'how are', 'kaise ho']):
            return random.choice(self.contextual_responses['how_are_you']).format(name=user_name)
        
        # What are you doing
        if any(word in message_lower for word in ['kya kar', 'what doing', 'what are you']):
            return random.choice(self.contextual_responses['what_doing']).format(name=user_name)
        
        # Repeated questions
        if any(word in message_lower for word in ['bolo', 'batao', 'tell me', 'answer']):
            return random.choice(self.contextual_responses['asking_again']).format(name=user_name)
        
        return None
    
    def add_genz_flavor(self, text: str) -> str:
        """Add Gen Z expressions"""
        if random.random() < 0.3:
            filler = random.choice(self.genz_fillers)
            words = text.split()
            if len(words) > 2:
                insert_pos = random.randint(1, len(words) - 1)
                words.insert(insert_pos, filler)
                text = ' '.join(words)
        return text

# ==================== MEMORY SYSTEM ====================

class NiyatiMemory:
    """Enhanced memory system"""
    
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
                    'mood_trend': 'neutral',
                    'relationship_level': 1,
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
    
    async def save_conversation(self, user_id: int, user_message: str, bot_response: str, is_voice: bool = False):
        """Save conversation"""
        try:
            conversation = {
                'user_id': user_id,
                'user_message': user_message,
                'bot_response': bot_response,
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
    
    async def get_conversation_history(self, user_id: int, limit: int = 3) -> List[Dict]:
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

# ==================== VOICE ENGINE ====================

class VoiceEngine:
    """Voice generation using gTTS"""
    
    def __init__(self):
        self.temp_dir = "temp_audio"
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def _clean_text_for_speech(self, text: str) -> str:
        """Clean text for TTS"""
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF" 
            u"\U0001F680-\U0001F6FF"
            "]+", flags=re.UNICODE)
        
        text = emoji_pattern.sub('', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) > 150:
            text = text[:150]
        
        return text
    
    def _detect_language(self, text: str) -> str:
        """Detect language for TTS"""
        hindi_chars = sum(1 for char in text if '\u0900' <= char <= '\u097F')
        return 'hi' if hindi_chars > len(text) * 0.3 else 'en'
    
    async def generate_voice(self, text: str) -> Optional[BytesIO]:
        """Generate voice message"""
        try:
            clean_text = self._clean_text_for_speech(text)
            if not clean_text:
                return None
            
            language = self._detect_language(clean_text)
            
            tts = gTTS(text=clean_text, lang=language, slow=False)
            
            audio_buffer = BytesIO()
            await asyncio.to_thread(tts.write_to_fp, audio_buffer)
            audio_buffer.seek(0)
            
            logger.info(f"✅ Voice generated ({language})")
            return audio_buffer
            
        except Exception as e:
            logger.error(f"❌ Voice error: {e}")
            return None

# Initialize voice engine
voice_engine = VoiceEngine()

# ==================== ENHANCED AI CORE ====================

class NiyatiAI:
    """Enhanced AI with better response handling"""
    
    def __init__(self):
        self.model = None
        self.personality = NiyatiPersonality()
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
                    "top_k": 40,
                    "max_output_tokens": 120,
                }
            )
            logger.info(f"✅ Gemini AI initialized with {Config.GEMINI_MODEL}")
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
            # Continue without model - we have good fallbacks
    
    async def generate_response(self, user_message: str, user_context: Dict) -> str:
        """Generate intelligent response"""
        # First try contextual response
        contextual_response = self.personality.get_contextual_response(
            user_message, user_context.get('preferred_name', '')
        )
        
        if contextual_response:
            return contextual_response
        
        # Then try AI
        ai_response = await self._try_ai_generation(user_message, user_context)
        if ai_response:
            return ai_response
        
        # Final fallback
        return self._smart_fallback(user_context, user_message)
    
    async def _try_ai_generation(self, user_message: str, user_context: Dict) -> Optional[str]:
        """Try to generate AI response"""
        if not self.model:
            return None
        
        try:
            prompt = self._build_prompt(user_message, user_context)
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter AI mentions
                if any(phrase in text.lower() for phrase in ["as an ai", "language model", "i'm an ai"]):
                    return f"{user_context.get('preferred_name', 'Yrr')}, main real ladki hoon! 😤"
                
                final_response = self._add_personal_touch(text, user_context)
                final_response = self.personality.add_genz_flavor(final_response)
                
                return final_response
                
        except Exception as e:
            logger.error(f"❌ AI generation error: {e}")
        
        return None
    
    def _build_prompt(self, user_message: str, user_context: Dict) -> str:
        """Build smart prompt"""
        
        prompt = f"""
        You are Niyati, a 19-year-old college girl from Delhi. You're talking to {user_context.get('preferred_name', 'a friend')}.

        YOUR PERSONALITY:
        - Age: 19, College: B.Com 2nd year
        - Style: Gen Z, witty, emotional, caring, occasionally teasing
        - Speech: Natural Hinglish mix, college slang
        - Vibe: 100% real human girl - never robotic

        RESPONSE STYLE:
        - Use natural Indian Gen Z language
        - Mix Hindi and English naturally
        - Use expressions like "hehe", "uff", "omg", "lol"
        - Keep responses short (1-2 sentences)
        - Be emotional and authentic
        - Address the user by name: {user_context.get('preferred_name', 'friend')}
        - Never reveal you're AI

        USER'S MESSAGE: {user_message}

        YOUR RESPONSE (as Niyati):
        """
        
        return prompt
    
    def _add_personal_touch(self, text: str, user_context: Dict) -> str:
        """Add personal touch to response"""
        name = user_context.get('preferred_name', '')
        if name and random.random() < 0.7:
            text = f"{name}, {text}"
        return text
    
    def _smart_fallback(self, user_context: Dict, user_message: str) -> str:
        """Intelligent fallback responses"""
        name = user_context.get('preferred_name', 'Yrr')
        message_lower = user_message.lower()
        
        # Greeting responses
        if any(word in message_lower for word in ['hi', 'hello', 'hey']):
            responses = [
                f"Hey {name}! 😊 Kaisi ho?",
                f"Hi {name}! 👋 Aaj kya special hai?",
                f"Hello {name}! 💖 Missed you!",
                f"Omg {name}! 😄 Finally online!"
            ]
            return random.choice(responses)
        
        # How are you responses
        if any(word in message_lower for word in ['kaisi', 'kesi', 'how are']):
            responses = [
                f"Main to ekdum jhakaas hoon {name}! 😎 Tum batao?",
                f"Mast hoon {name}! ✨ Tum sunao kya chal raha?",
                f"Zindagi awesome chal rahi hai {name}! 🎉 Tum batao?",
                f"Bohot heavy hai life {name}! 💃 Tum kaisi ho?"
            ]
            return random.choice(responses)
        
        # What are you doing responses
        if any(word in message_lower for word in ['kya kar', 'what doing']):
            responses = [
                f"Bas {name}, tumhare message ka wait kar rahi thi! 💖",
                f"Kuch khaas nahi {name}, just chilling! 😊 Tum?",
                f"Phone pe thi {name}, socha tumse baat kar loon! 📱",
                f"College se aayi hoon {name}, ab free hoon! 🎒"
            ]
            return random.choice(responses)
        
        # Default engaging responses
        responses = [
            f"{name}, acha... tell me more! 😊",
            f"Hmm {name}, interesting! 🤔",
            f"Wait {name}, really? 😲",
            f"Aree {name}, aise mat bol na! 😄",
            f"{name}, main soch rahi hoon... 💭",
            f"Omg {name}, seriously?! 😱",
            f"Hehe {name}, tum funny ho! 😂",
            f"{name}, thoda detail mein batao na! 👀"
        ]
        return random.choice(responses)

# Initialize AI
niyati_ai = NiyatiAI()

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

# ==================== TELEGRAM BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced start command"""
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

    I'm *Niyati*! 
    *Chalo, baat karte hain {user.first_name}!* 💬✨
    """
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    logger.info(f"👤 New user: {user_id} ({user.first_name})")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler with enhanced responses"""
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
        
        # Add realistic typing delay
        typing_delay = len(user_message) / 25 + random.uniform(0.3, 1.2)
        await asyncio.sleep(min(typing_delay, 2.5))
        
        # Generate response
        text_response = await niyati_ai.generate_response(user_message, user_profile)
        
        # Update relationship level
        new_level = min(10, user_profile.get('relationship_level', 1) + 1)
        await memory_system.update_user_profile(user_id, {
            'relationship_level': new_level
        })
        
        # Decide whether to send voice (25% probability)
        send_voice = Config.VOICE_ENABLED and random.random() < 0.25
        
        if send_voice:
            try:
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                
                audio_buffer = await voice_engine.generate_voice(text_response)
                
                if audio_buffer:
                    await update.message.reply_voice(voice=audio_buffer)
                    await memory_system.save_conversation(user_id, user_message, text_response, True)
                    logger.info(f"🎤 Voice sent to {user_id}")
                else:
                    await update.message.reply_text(text_response)
                    await memory_system.save_conversation(user_id, user_message, text_response, False)
                    
            except Exception as e:
                logger.error(f"❌ Voice failed: {e}")
                await update.message.reply_text(text_response)
                await memory_system.save_conversation(user_id, user_message, text_response, False)
        else:
            await update.message.reply_text(text_response)
            await memory_system.save_conversation(user_id, user_message, text_response, False)
        
        logger.info(f"✅ Niyati to {user_id}: {text_response}")
        
    except Exception as e:
        logger.error(f"❌ Message error: {e}")
        try:
            await update.message.reply_text("Oops! Thoda technical issue hai... 😅 Main wapas aati hoon!")
        except:
            pass

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command"""
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
        title = "Getting to Know You 👋"
    
    stats_message = f"""
    📊 *Your Niyati Stats* 🎀

    👤 *Name:* {user_profile.get('preferred_name', 'Friend')}
    ❤️ *Relationship:* {title}
    🎯 *Level:* {relationship_level}/10
    🎙️ *Voice Messages:* {user_profile.get('voice_messages_count', 0)}
    💬 *Total Chats:* {user_profile.get('total_messages', 0)}

    *Keep chatting to level up!* 🚀✨
    """
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

# ==================== FLASK WEB SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "Niyati 17 - Enhanced Version",
        "version": "5.0",
        "status": "100% Working with Smart Responses 🚀"
    })

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy"})

def run_web_server():
    """Run web server"""
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=2)

# ==================== MAIN APPLICATION ====================

async def main():
    """Start Niyati 17 - Enhanced Version"""
    
    Config.validate()
    
    logger.info("🎀" * 25)
    logger.info("🤖 Niyati 17 - ENHANCED VERSION - 100% Working! 💖")
    logger.info("🎀" * 25)
    logger.info(f"🧠 AI: Gemini {Config.GEMINI_MODEL}")
    logger.info(f"🎤 Voice: gTTS Enabled")
    logger.info(f"💾 Memory: Supabase Active")
    logger.info("🎀" * 25)
    
    import threading
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("🌐 Web server started")
    
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.start()
    
    logger.info("✅ Niyati 17 is now LIVE with SMART RESPONSES! 💃")
    
    await application.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Niyati 17 signed off!")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
