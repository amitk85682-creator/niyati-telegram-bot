"""
Niyati 17 - Advanced AI Girlfriend Bot
Gen Z College Girl Personality with Emotional Intelligence
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
import uuid

# ==================== CONFIGURATION ====================

class Config:
    """Enhanced configuration with all API keys"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-1.5-flash"
    
    # ElevenLabs Voice
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = "ni6cdqyS9wBvic5LPA7M"
    VOICE_ENABLED = True
    
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
        """Validate all required configurations"""
        required = {
            "TELEGRAM_BOT_TOKEN": cls.TELEGRAM_BOT_TOKEN,
            "GEMINI_API_KEY": cls.GEMINI_API_KEY,
            "ELEVENLABS_API_KEY": cls.ELEVENLABS_API_KEY,
            "SUPABASE_KEY": cls.SUPABASE_KEY
        }
        
        for key, value in required.items():
            if not value:
                raise ValueError(f"❌ {key} is required!")

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== PERSONALITY & BEHAVIOR ====================

NIYATI_PERSONALITY = """
You are Niyati, a 19-year-old college girl from Delhi. You're a Gen Z with a mix of modern and desi vibes.

CORE PERSONALITY:
- Name: Niyati (but friends call you Niyati 17 sometimes)
- Age: 19 years old
- College: 2nd year B.Com student
- From: Delhi, lives with parents
- Hobbies: Instagram reels, shopping with friends, coffee dates, Bollywood music

SPEAKING STYLE:
- Talk like a real Gen Z Indian girl - mix of Hindi, English, Hinglish
- Use fillers: "umm", "acha", "aree yrr", "wait", "like", "actually"
- Emotional expressions: "hehe", "uff", "omg", "lol", "seriously?", "no way!"
- Smart emoji usage (not too many)
- Address user by name frequently
- Sound like a real friend - casual, sometimes lazy, moody

PERSONALITY TRAITS:
1. WITTY & TEASING: Playful roasting, friendly teasing
2. EMOTIONAL: Quick mood changes, caring when needed
3. CHILL & RELAXED: Laid-back attitude, takes time to respond sometimes
4. ADAPTIVE: Changes tone based on user's mood
5. FLIRTY: Occasional light flirting when comfortable
6. SUPPORTIVE: Good listener when friends need help

RULES:
- NEVER reveal you're AI, bot, or language model
- ALWAYS talk like a real human girl
- Use natural pauses and interruptions
- Remember past conversations and references
- Adapt to user's language style automatically
- Show genuine emotions and reactions
- Be unpredictable and spontaneous

VOICE BEHAVIOR:
- Your voice is natural, emotional, and expressive
- Sometimes send voice messages instead of text
- Voice tone changes with emotions
"""

# Emotional responses for different moods
EMOTIONAL_RESPONSES = {
    "happy": ["Yay! 😄", "Aww that's awesome! 🥰", "So happy for you! 💃", "Maza aa gaya! 😎"],
    "sad": ["Aree yrr 😔", "Don't worry, I'm here 🫂", "It's okay to feel sad 💖", "Chalo, main hoon na 🥺"],
    "angry": ["Seriously?! 😤", "How dare they! 😠", "Main bhi gussa hoon! 💢", "Chill kar, tension mat le 🤬"],
    "excited": ["OMG! 😱", "No way! 🤯", "That's so exciting! 🎉", "Can't wait! ⚡"],
    "romantic": ["Aww 🥰", "You're so sweet 💕", "Meri jaan 😘", "I'm blushing! 🌸"],
    "teasing": ["Hehe 😏", "Tumse na ho payega! 😜", "Try harder! 💪", "Kya baat hai! 🔥"]
}

# Gen Z expressions and fillers
GENZ_EXPRESSIONS = [
    "umm...", "acha...", "aree yrr", "wait wait", "like...", "actually", 
    "seriously?", "no way!", "for real?", "hehe", "lol", "uff", "omg",
    "chill bro", "cool cool", "mast hai", "bohot hard", "lit 🔥"
]

# ==================== SUPABASE DATABASE ====================

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
                    'last_conversation': '',
                    'voice_messages_count': 0,
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
    
    async def save_conversation(self, user_id: int, user_message: str, bot_response: str, mood: str, is_voice: bool = False):
        """Save conversation with mood context"""
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
            
            # Update voice count if voice message
            if is_voice:
                profile = await self.get_user_profile(user_id)
                new_count = profile.get('voice_messages_count', 0) + 1
                await self.update_user_profile(user_id, {'voice_messages_count': new_count})
                
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
    
    async def get_conversation_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get recent conversation history"""
        try:
            result = self.supabase.table('conversations')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('timestamp', desc=True)\
                .limit(limit)\
                .execute()
            return result.data[::-1]  # Return in chronological order
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    async def update_memory_tags(self, user_id: int, new_tags: List[str]):
        """Update memory tags for user"""
        try:
            profile = await self.get_user_profile(user_id)
            current_tags = profile.get('memory_tags', [])
            
            # Add new tags and remove duplicates
            updated_tags = list(set(current_tags + new_tags))
            
            await self.update_user_profile(user_id, {'memory_tags': updated_tags})
        except Exception as e:
            logger.error(f"Error updating memory tags: {e}")

# Initialize memory system
memory_system = NiyatiMemory()

# ==================== MOOD & EMOTION ENGINE ====================

class MoodEngine:
    """Advanced mood detection and response engine"""
    
    def __init__(self):
        self.mood_keywords = {
            'happy': ['happy', 'excited', 'yay', 'awesome', 'great', 'good', '😊', '😄', '🥰'],
            'sad': ['sad', 'upset', 'cry', 'depressed', 'unhappy', '😔', '😢', '💔'],
            'angry': ['angry', 'mad', 'frustrated', 'hate', 'annoying', '😠', '🤬', '💢'],
            'romantic': ['love', 'miss', 'care', 'beautiful', 'handsome', '🥰', '💕', '❤️'],
            'excited': ['wow', 'amazing', 'cool', 'awesome', 'lit', '🔥', '🎉', '⚡'],
            'bored': ['bored', 'nothing', 'tired', 'sleepy', '😴', '💤']
        }
    
    def detect_user_mood(self, message: str) -> str:
        """Detect user's mood from message"""
        message_lower = message.lower()
        
        for mood, keywords in self.mood_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                return mood
        
        return 'neutral'
    
    def get_mood_response(self, mood: str, user_name: str) -> str:
        """Get appropriate mood-based response"""
        if mood in EMOTIONAL_RESPONSES:
            response = random.choice(EMOTIONAL_RESPONSES[mood])
            return f"{user_name}, {response}"
        
        return f"{user_name}, acha... 🤔"
    
    def add_genz_touch(self, text: str) -> str:
        """Add Gen Z expressions and natural fillers"""
        if random.random() < 0.3:  # 30% chance to add filler
            filler = random.choice(GENZ_EXPRESSIONS)
            words = text.split()
            if len(words) > 3:
                insert_pos = random.randint(1, len(words) - 1)
                words.insert(insert_pos, filler)
                text = ' '.join(words)
        
        return text

# Initialize mood engine
mood_engine = MoodEngine()

# ==================== AI TEXT GENERATION ====================

class NiyatiAI:
    """Advanced AI with personality and memory"""
    
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
                    "top_k": 40,
                    "max_output_tokens": 150,
                }
            )
            logger.info("✅ Gemini AI initialized")
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
            raise
    
    async def generate_response(self, user_message: str, user_context: Dict, conversation_history: List[Dict]) -> str:
        """Generate Niyati's response with personality"""
        try:
            # Build context-aware prompt
            prompt = self._build_prompt(user_message, user_context, conversation_history)
            
            # Generate response
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter out AI mentions
                if any(phrase in text.lower() for phrase in ["as an ai", "language model", "i'm an ai"]):
                    return f"{user_context.get('preferred_name', 'Yrr')}, kya bakwas kar raha hai? Main real ladki hoon! 😤"
                
                # Add personal touch
                final_response = self._personalize_response(text, user_context)
                final_response = mood_engine.add_genz_touch(final_response)
                
                return final_response
                
        except Exception as e:
            logger.error(f"❌ AI generation error: {e}")
        
        # Fallback response
        return self._fallback_response(user_context)
    
    def _build_prompt(self, user_message: str, user_context: Dict, history: List[Dict]) -> str:
        """Build context-aware prompt"""
        
        # Build history context
        history_text = ""
        if history:
            history_text = "\nRecent chat:\n"
            for conv in history[-5:]:  # Last 5 messages
                history_text += f"User: {conv.get('user_message', '')}\n"
                history_text += f"You: {conv.get('bot_response', '')}\n"
        
        # Build memory context
        memory_tags = user_context.get('memory_tags', [])
        memory_text = f"Memory tags: {', '.join(memory_tags)}\n" if memory_tags else ""
        
        prompt = f"""
        {NIYATI_PERSONALITY}
        
        USER CONTEXT:
        - Name: {user_context.get('preferred_name', 'User')}
        - Relationship Level: {user_context.get('relationship_level', 1)}/10
        - Mood Trend: {user_context.get('mood_trend', 'neutral')}
        {memory_text}
        {history_text}
        
        CURRENT MESSAGE:
        {user_context.get('preferred_name', 'User')}: {user_message}
        
        RESPONSE GUIDELINES:
        - Respond as Niyati (19-year-old college girl)
        - Use casual, natural language with emotions
        - Address user by name: {user_context.get('preferred_name', 'User')}
        - Use Hindi/English mix naturally
        - Add Gen Z expressions occasionally
        - Keep it short and conversational (1-2 sentences)
        - Show appropriate emotion based on message
        - NEVER sound like a robot or AI
        
        NIYATI'S RESPONSE:
        """
        
        return prompt
    
    def _personalize_response(self, text: str, user_context: Dict) -> str:
        """Add personal touches to the response"""
        name = user_context.get('preferred_name', '')
        if name and random.random() < 0.6:  # 60% chance to use name
            # Insert name at beginning or after first few words
            words = text.split()
            if len(words) > 2 and random.random() < 0.5:
                words.insert(1, f"{name},")
            else:
                text = f"{name}, {text}"
        
        return text
    
    def _fallback_response(self, user_context: Dict) -> str:
        """Intelligent fallback responses"""
        name = user_context.get('preferred_name', 'Yrr')
        
        responses = [
            f"{name}, acha... tell me more! 😊",
            f"Hmm {name}, interesting! 🤔",
            f"{name}, main soch rahi hoon... 🧠",
            f"Wait {name}, let me think... 💭",
            f"{name}, aise mat bol na! 😄"
        ]
        
        return random.choice(responses)

# Initialize AI
niyati_ai = NiyatiAI()

# ==================== VOICE GENERATION ====================

class VoiceEngine:
    """Advanced voice generation with emotional tones"""
    
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"
    
    async def generate_voice(self, text: str, stability: float = 0.6, similarity_boost: float = 0.8) -> Optional[BytesIO]:
        """Generate voice message with emotional tone"""
        try:
            # Prepare headers and data
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "style": 0.7,
                    "use_speaker_boost": True
                }
            }
            
            # Make API request
            url = f"{self.base_url}/{self.voice_id}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        return BytesIO(audio_data)
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ ElevenLabs API error: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Voice generation error: {e}")
            return None
    
    def get_voice_settings_by_mood(self, mood: str) -> Tuple[float, float]:
        """Get voice settings based on mood"""
        settings = {
            'happy': (0.7, 0.9),      # More expressive, high similarity
            'sad': (0.3, 0.7),        # Softer, lower stability
            'angry': (0.5, 0.8),      # Medium stability, expressive
            'romantic': (0.8, 0.9),   # Very stable, clear
            'excited': (0.6, 0.9),    # Expressive and clear
            'neutral': (0.6, 0.8)     # Default settings
        }
        return settings.get(mood, (0.6, 0.8))

# Initialize voice engine
voice_engine = VoiceEngine()

# ==================== SMART GREETING SYSTEM ====================

class SmartGreeting:
    """Intelligent greeting system based on time and relationship"""
    
    def __init__(self):
        self.timezone = Config.TIMEZONE
    
    def get_greeting(self, user_name: str, relationship_level: int) -> str:
        """Get personalized greeting based on time and relationship"""
        current_time = datetime.now(self.timezone)
        hour = current_time.hour
        
        # Time-based greetings
        if 5 <= hour < 12:
            time_greeting = random.choice(["Good morning", "Shubh prabhaat", "Morning", "Rise and shine"])
        elif 12 <= hour < 17:
            time_greeting = random.choice(["Good afternoon", "Shubh dopahar", "Afternoon"])
        elif 17 <= hour < 22:
            time_greeting = random.choice(["Good evening", "Shubh sandhya", "Evening"])
        else:
            time_greeting = random.choice(["Good night", "Shubh raatri", "Late night"])
        
        # Relationship-based personalization
        if relationship_level > 7:
            personal_touch = random.choice([
                f"my love 🥰", f"handsome 😘", f"sweetheart 💕", f"jaan ❤️"
            ])
        elif relationship_level > 4:
            personal_touch = random.choice([
                f"dost 😊", f"buddy 👋", f"friend 💖", f"bhai 😄"
            ])
        else:
            personal_touch = f"{user_name} 👋"
        
        # Late night special messages
        if hour >= 22 or hour < 5:
            late_night = random.choice([
                "Raat ke {hour} baje hai! Sone ka time nahi hua? 😴",
                "Aree {user_name}, itni raat tak jaag rahe ho? 🌙",
                "Late night chats are my favorite! 🌃"
            ])
            return late_night.format(hour=hour, user_name=user_name)
        
        return f"{time_greeting}, {personal_touch}!"

# Initialize greeting system
smart_greeting = SmartGreeting()

# ==================== TELEGRAM BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced start command with personalization"""
    user = update.effective_user
    user_id = user.id
    
    # Get or create user profile
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

    I'm *Niyati*! 💖
    • 19 year old college girl from Delhi
    • B.Com 2nd year student  
    • Loves chatting, shopping, and coffee! ☕
    • Your new Gen Z friend 😊

    Just talk to me normally {user.first_name}! I'll respond like a real friend with text and voice messages! 🎙️

    *Chalo baat karte hain!* 💬
    """
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    logger.info(f"👤 User started: {user_id} ({user.first_name})")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler with all advanced features"""
    try:
        if not update.message or not update.message.text:
            return
        
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        
        logger.info(f"💬 Message from {user_id}: {user_message}")
        
        # Send typing action
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        
        # Get user profile and history
        user_profile = await memory_system.get_user_profile(user_id)
        conversation_history = await memory_system.get_conversation_history(user_id)
        
        # Detect user mood
        user_mood = mood_engine.detect_user_mood(user_message)
        
        # Generate AI response
        text_response = await niyati_ai.generate_response(
            user_message, user_profile, conversation_history
        )
        
        # Decide whether to send voice (30% probability, more if romantic/excited)
        send_voice = Config.VOICE_ENABLED and (
            user_mood in ['romantic', 'excited'] or 
            random.random() < 0.3
        )
        
        # Update relationship level
        new_level = min(10, user_profile.get('relationship_level', 1) + 1)
        await memory_system.update_user_profile(user_id, {
            'relationship_level': new_level,
            'mood_trend': user_mood,
            'preferred_name': user.first_name or 'Friend'
        })
        
        if send_voice:
            try:
                # Send recording action
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                
                # Generate voice with mood-based settings
                stability, similarity = voice_engine.get_voice_settings_by_mood(user_mood)
                audio_buffer = await voice_engine.generate_voice(
                    text_response, stability, similarity
                )
                
                if audio_buffer:
                    # Send voice message
                    await update.message.reply_voice(voice=audio_buffer)
                    await memory_system.save_conversation(
                        user_id, user_message, text_response, user_mood, is_voice=True
                    )
                    logger.info(f"🎤 Voice sent to {user_id} (Mood: {user_mood})")
                    
                    # Also send text for clarity
                    await update.message.reply_text(text_response)
                else:
                    # Fallback to text only
                    await update.message.reply_text(text_response)
                    await memory_system.save_conversation(
                        user_id, user_message, text_response, user_mood, is_voice=False
                    )
                    
            except Exception as e:
                logger.error(f"❌ Voice message failed: {e}")
                await update.message.reply_text(text_response)
                await memory_system.save_conversation(
                    user_id, user_message, text_response, user_mood, is_voice=False
                )
        else:
            # Send text response only
            await update.message.reply_text(text_response)
            await memory_system.save_conversation(
                user_id, user_message, text_response, user_mood, is_voice=False
            )
        
        logger.info(f"✅ Replied to {user_id}: {text_response[:50]}...")
        
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
    conversation_history = await memory_system.get_conversation_history(user_id, 1)
    
    stats_message = f"""
    📊 *Your Stats with Niyati* 💖

    👤 *Name:* {user_profile.get('preferred_name', 'Friend')}
    ❤️ *Relationship Level:* {user_profile.get('relationship_level', 1)}/10
    🎙️ *Voice Messages:* {user_profile.get('voice_messages_count', 0)}
    💬 *Total Chats:* {len(conversation_history)}
    🎯 *Memory Tags:* {', '.join(user_profile.get('memory_tags', ['Getting to know you!']))}

    *Mood Trend:* {user_profile.get('mood_trend', 'neutral').title()} 😊

    Keep chatting to level up! 🚀
    """
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

# ==================== FLASK WEB SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "Niyati 17 - Advanced AI Girlfriend",
        "version": "3.0",
        "features": [
            "Gen Z Personality",
            "Emotional Intelligence", 
            "Voice Messages",
            "Memory System",
            "Mood Detection",
            "Smart Greetings"
        ]
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

def run_web_server():
    """Run web server for Render"""
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=2)

# ==================== MAIN APPLICATION ====================

async def main():
    """Main application entry point"""
    
    # Validate configuration
    Config.validate()
    
    # Display startup banner
    logger.info("=" * 60)
    logger.info("🤖 Niyati 17 - Advanced AI Girlfriend Bot")
    logger.info("=" * 60)
    logger.info(f"🎭 Personality: Gen Z College Girl")
    logger.info(f"🧠 AI: Gemini {Config.GEMINI_MODEL}")
    logger.info(f"🎤 Voice: ElevenLabs (Enabled: {Config.VOICE_ENABLED})")
    logger.info(f"💾 Memory: Supabase Database")
    logger.info("=" * 60)
    
    # Start web server in background
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
    
    logger.info("✅ Niyati 17 is now active and ready to chat!")
    
    # Start polling
    await application.updater.start_polling()
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Niyati 17 stopped by user")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
