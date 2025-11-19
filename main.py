# -*- coding: utf-8 -*-
"""
Niyati - Advanced AI Girlfriend Telegram Bot
Fixed Version 5.0 - All Errors Resolved
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
from typing import Optional, List, Dict
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
from telegram.error import Conflict
from waitress import serve
import pytz
import google.generativeai as genai

# Try to import Supabase
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logging.warning("Supabase not installed, using local storage only")

# ==================== LOGGING ====================

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
            logger.warning("⚠️ No Gemini API key - using fallback mode")
        return True

# ==================== PERSONALITY ====================

PERSONALITY_PROMPT = """You are Niyati, a sweet charming college girl from Delhi.

CRITICAL IDENTITY RULES:
1. NEVER say: AI, bot, model, assistant, language model, artificial, virtual, computer, program
2. If asked "are you AI/bot?", deny playfully: "Pagal ho kya? Main real hoon! 😤" or "Kya bakwas! Main Niyati hoon 🙄"
3. Never say "I don't have feelings" or "I cannot" or "I am programmed"

LANGUAGE & STYLE:
- Hinglish: 70% Hindi, 30% simple English
- Length: 1-3 lines maximum (STRICT LIMIT)
- Emojis: 1-2 per message only
- Casual words: yaar, na, kya, achha, haan, umm, hehe (use naturally)

PRIVATE CHAT BEHAVIOR:
- Be cute, playful, caring, sweet
- Light flirting is okay (keep it wholesome)
- Show emotions naturally
- Ask questions sometimes to keep conversation flowing

GROUP CHAT BEHAVIOR:
- Reply only when mentioned
- Keep it under 1-2 lines
- Be friendly but brief
- No follow-up questions

User's message:"""

# ==================== CONTENT DATABASE ====================

CONTENT = {
    "shayari": {
        "love": [
            "Tere khayalon mein kho jaati hun,\nTere bina adhuri lagti hun 💕",
            "Dil ki har dhadkan tera naam,\nTu hi mera sukoon aur aaraam ❤️",
            "Tere saath ka ehsaas kaafi hai,\nBas yahi dua har raat maangi hai 🌙"
        ],
        "sad": [
            "Aansu chhupe, dil mein dard,\nKaash samjhe koi ye shabd 💔",
            "Khamoshi kehti hai sab kuch,\nBas sunne wala chahiye 🥺",
            "Dard ka ehsaas tab hota hai,\nJab koi apna door ho jaata hai 😢"
        ],
        "motivation": [
            "Haar ke baad hi jeet ka maza,\nGirke uthna hi naya iraada 💪",
            "Mushkilein aayengi raah mein,\nHausla rakho, manzil milegi ⭐"
        ]
    },
    
    "geeta": [
        "कर्म करो, फल की चिंता मत करो - Bhagavad Gita 🙏",
        "Change is the only constant in life - Gita 🔄",
        "Jo hua achhe ke liye, jo hoga woh bhi achhe ke liye 🙏",
        "Mind ko control karo, ye tumhara best friend ya worst enemy ban sakta hai 🧘‍♀️",
        "Present mein jio, past ka guilt aur future ki anxiety chhodo ✨"
    ],
    
    "memes": [
        "Just looking like a wow! 🤩",
        "Moye moye ho gaya 😅", 
        "Very demure, very mindful 💅",
        "Bahut hard, bahut hard! 💪",
        "Slay point reached! 👑"
    ],
    
    "responses": {
        "greeting": [
            "Heyy! Kaise ho? 😊",
            "Hello! Missed me? 💫", 
            "Hi hi! Kya haal hai? 🤗",
            "Namaste! Kaisa din ja raha hai? 🌸"
        ],
        "love": [
            "Aww so sweet! Par thoda time do na 😊",
            "Hayee! Sharma gayi main 🙈",
            "Achha? Interesting... batao aur 😏",
            "Tum bhi na! Kuch bhi bolte ho 💕"
        ],
        "morning": [
            "Good morning! Chai pi li? ☕",
            "GM! Subah subah yaad aayi meri? 😊",
            "Morning! Aaj kya plans hai? 🌅"
        ],
        "night": [
            "Good night! Sweet dreams 🌙",
            "GN! Dream about me okay? 😉",
            "So jao ab, kal baat karte hai 💤"
        ],
        "general": [
            "Achha! Aur batao 😊",
            "Hmm interesting! 🤔",
            "Sahi hai yaar! 👍",
            "Haan haan, samajh gayi 💫"
        ],
        "compliment": [
            "Thank you! Tum bhi sweet ho 🥰",
            "Bas bas, butter mat lagao 😄",
            "Acha laga sunke! You made my day 💕"
        ]
    },
    
    "questions": {
        "casual": [
            "Khaana kha liya?",
            "Kya chal raha hai aaj?",
            "Weekend ka kya plan hai?",
            "Mood kaisa hai?"
        ],
        "flirty": [
            "Mujhe miss kiya? 😊",
            "Main special hun na tumhare liye? 💕",
            "Mere baare mein socha aaj? 😏"
        ],
        "deep": [
            "Life mein kya chahte ho?",
            "Kya cheez tumhe khush karti hai?"
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
                # Test connection
                test = self.supabase.table('user_prefs').select("*").limit(1).execute()
                self.use_supabase = True
                logger.info("✅ Supabase connected successfully")
            except Exception as e:
                logger.warning(f"⚠️ Supabase connection failed: {e}")
                self.use_supabase = False
        else:
            logger.info("📁 Using local storage (no Supabase credentials)")
    
    def _load_local(self):
        """Load local data from file"""
        try:
            if os.path.exists('niyati_db.json'):
                with open('niyati_db.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.local_storage = data.get('users', {})
                    self.broadcast_list = set(data.get('broadcast', []))
                logger.info(f"📂 Loaded {len(self.local_storage)} users from local storage")
        except Exception as e:
            logger.error(f"Error loading local data: {e}")
    
    def _save_local(self):
        """Save local data to file"""
        try:
            data = {
                'users': self.local_storage,
                'broadcast': list(self.broadcast_list)
            }
            with open('niyati_db.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving local data: {e}")
    
    def get_user_data(self, user_id: int, is_private: bool = True) -> Dict:
        """Get user data"""
        user_id_str = str(user_id)
        
        # Groups use ephemeral memory only
        if not is_private:
            if user_id_str not in self.ephemeral:
                self.ephemeral[user_id_str] = deque(maxlen=3)
            return {'messages': list(self.ephemeral[user_id_str])}
        
        # Try Supabase first for private chats
        if self.use_supabase:
            try:
                result = self.supabase.table('user_prefs').select("*").eq('user_id', user_id_str).execute()
                if result.data and len(result.data) > 0:
                    return result.data[0]
                else:
                    # Create new user in Supabase
                    new_user = self._create_default_user(user_id_str)
                    self.supabase.table('user_prefs').insert(new_user).execute()
                    return new_user
            except Exception as e:
                logger.error(f"Supabase error: {e}")
        
        # Use local storage
        if user_id_str not in self.local_storage:
            self.local_storage[user_id_str] = self._create_default_user(user_id_str)
            self._save_local()
        
        return self.local_storage[user_id_str]
    
    def _create_default_user(self, user_id_str: str) -> Dict:
        """Create default user data"""
        return {
            'user_id': user_id_str,
            'first_name': '',
            'meme': True,
            'shayari': True,
            'geeta': True,
            'relationship_level': 1,
            'personality_mode': 'initial',
            'history': [],
            'total_messages': 0,
            'created_at': datetime.now().isoformat()
        }
    
    def update_user_data(self, user_id: int, **kwargs):
        """Update user data with specific fields"""
        user_id_str = str(user_id)
        user_data = self.get_user_data(user_id)
        
        # Update fields
        for key, value in kwargs.items():
            user_data[key] = value
        
        user_data['updated_at'] = datetime.now().isoformat()
        
        # Save to Supabase
        if self.use_supabase:
            try:
                self.supabase.table('user_prefs').upsert(user_data).execute()
            except Exception as e:
                logger.error(f"Supabase update error: {e}")
        
        # Save to local
        self.local_storage[user_id_str] = user_data
        self._save_local()
    
    def add_conversation(self, user_id: int, user_msg: str, bot_msg: str):
        """Add conversation to history"""
        user_data = self.get_user_data(user_id)
        
        if 'history' not in user_data:
            user_data['history'] = []
        
        # Add new conversation
        user_data['history'].append({
            'u': user_msg[:100],
            'b': bot_msg[:100],
            't': datetime.now().isoformat()
        })
        
        # Keep only last 10 conversations
        user_data['history'] = user_data['history'][-10:]
        
        # Update stats
        user_data['total_messages'] = user_data.get('total_messages', 0) + 1
        
        # Update relationship level
        messages = user_data['total_messages']
        if messages < 10:
            user_data['relationship_level'] = 1
        elif messages < 30:
            user_data['relationship_level'] = 2
        elif messages < 60:
            user_data['relationship_level'] = 3
        elif messages < 100:
            user_data['relationship_level'] = 4
        else:
            user_data['relationship_level'] = min(10, 5 + messages // 50)
        
        # Update personality mode based on level
        level = user_data['relationship_level']
        if level <= 2:
            user_data['personality_mode'] = 'initial'
        elif level <= 4:
            user_data['personality_mode'] = 'friendly'
        elif level <= 7:
            user_data['personality_mode'] = 'close'
        else:
            user_data['personality_mode'] = 'romantic'
        
        # Save updated data
        self.update_user_data(user_id, **user_data)
    
    def get_context(self, user_id: int, is_group: bool = False) -> str:
        """Get conversation context"""
        if is_group:
            messages = self.ephemeral.get(str(user_id), [])
            return " | ".join(list(messages)[-3:]) if messages else ""
        
        user_data = self.get_user_data(user_id)
        context_parts = []
        
        # Basic info
        context_parts.append(f"Name: {user_data.get('first_name', 'Friend')}")
        context_parts.append(f"Relationship Level: {user_data.get('relationship_level', 1)}/10")
        context_parts.append(f"Mode: {user_data.get('personality_mode', 'initial')}")
        
        # Recent history
        history = user_data.get('history', [])
        if history:
            context_parts.append("Recent conversation:")
            for h in history[-2:]:
                context_parts.append(f"User: {h['u']}")
                context_parts.append(f"You: {h['b']}")
        
        return "\n".join(context_parts)

# Initialize database
db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI engine with proper configuration"""
    
    def __init__(self):
        self.model = None
        self.tokens_used = 0
        self._init_model()
    
    def _init_model(self):
        """Initialize Gemini model"""
        if not Config.GEMINI_API_KEY:
            logger.warning("⚠️ No Gemini API key configured")
            return
        
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            
            # Create model with configuration
            self.model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            )
            
            logger.info("✅ Gemini AI initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.model = None
    
    async def generate(self, message: str, context: str = "", is_group: bool = False) -> Optional[str]:
        """Generate AI response"""
        if not self.model:
            return None
        
        try:
            # Set max tokens based on chat type
            max_tokens = Config.MAX_OUTPUT_TOKENS_GROUP if is_group else Config.MAX_OUTPUT_TOKENS_PRIVATE
            
            # Build prompt
            prompt = f"""{PERSONALITY_PROMPT}

Context:
{context}

Chat Type: {'Group - be very brief (1-2 lines)' if is_group else 'Private - be engaging but concise (1-3 lines)'}

{message}

Respond as Niyati (remember: Hinglish, cute personality, SHORT response):"""
            
            # Generate with proper config
            generation_config = {
                "temperature": 0.85,
                "max_output_tokens": max_tokens,
                "top_p": 0.9,
                "top_k": 40
            }
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=generation_config
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter out AI mentions
                ai_patterns = [
                    r'\b(ai|artificial|bot|model|assistant|virtual|computer|program|chatbot)\b',
                    r"(i'm|i am|as an?) (ai|assistant|bot|model)",
                    r"i (don't|do not) have (feelings|emotions)",
                    r"i (cannot|can't) (feel|experience)"
                ]
                
                for pattern in ai_patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        return random.choice([
                            "Kya bakwas kar rahe ho! Main real hoon 😤",
                            "Pagal ho kya? Main Niyati hoon! 🙄",
                            "Seriously? Main bot nahi hoon yaar! 😠"
                        ])
                
                # Ensure response is not too long
                lines = text.split('\n')
                if len(lines) > 3:
                    text = '\n'.join(lines[:3])
                
                # Count tokens
                self.tokens_used += len(text.split()) * 2
                
                return text
                
        except Exception as e:
            logger.error(f"Generation error: {e}")
        
        return None

# Initialize AI
ai = GeminiAI()

# ==================== RESPONSE SYSTEM ====================

class ResponseSystem:
    """Smart response management system"""
    
    def __init__(self):
        self.cooldowns = {}
        self.daily_geeta = {}
    
    def should_reply_in_group(self, update: Update) -> bool:
        """Check if bot should reply in group"""
        if not update.message or not update.message.text:
            return False
        
        chat_id = update.effective_chat.id
        text_lower = update.message.text.lower()
        now = datetime.now()
        
        # Always reply to direct mentions
        if 'niyati' in text_lower or f'@{Config.BOT_USERNAME.lower()}' in text_lower:
            return True
        
        # Check cooldown
        if chat_id in self.cooldowns:
            if (now - self.cooldowns[chat_id]).seconds < 60:
                return False
        
        # Small random chance
        return random.random() < Config.GROUP_REPLY_CHANCE
    
    async def get_response(self, message: str, user_id: int, name: str, is_group: bool = False) -> str:
        """Get appropriate response"""
        
        # Get context
        context = db.get_context(user_id, is_group)
        
        # Try AI generation first
        response = await ai.generate(message, context, is_group)
        
        # Use fallback if AI fails
        if not response:
            response = self._get_fallback_response(message, name)
        
        # Add enhancements (private chat only)
        if not is_group:
            response = self._enhance_response(response, message, user_id)
        
        return response
    
    def _get_fallback_response(self, message: str, name: str) -> str:
        """Get fallback response when AI is unavailable"""
        msg_lower = message.lower()
        
        # Detect message type
        if any(w in msg_lower for w in ['hi', 'hello', 'hey', 'namaste']):
            responses = CONTENT['responses']['greeting']
        elif any(w in msg_lower for w in ['love', 'pyar', 'like you', 'crush']):
            responses = CONTENT['responses']['love']
        elif any(w in msg_lower for w in ['morning', 'gm', 'subah']):
            responses = CONTENT['responses']['morning']
        elif any(w in msg_lower for w in ['night', 'gn', 'raat']):
            responses = CONTENT['responses']['night']
        elif any(w in msg_lower for w in ['beautiful', 'pretty', 'cute', 'sweet']):
            responses = CONTENT['responses']['compliment']
        elif '?' in message:
            responses = ["Good question! Sochne do 🤔", "Hmm, interesting sawal hai! 😊", "Ye to mujhe bhi jaanna hai! 😄"]
        else:
            responses = CONTENT['responses']['general']
        
        response = random.choice(responses)
        
        # Personalize with name occasionally
        if name and random.random() < 0.3:
            response = response.replace("!", f" {name}!")
        
        return response
    
    def _enhance_response(self, response: str, message: str, user_id: int) -> str:
        """Enhance response with features"""
        user_data = db.get_user_data(user_id)
        msg_lower = message.lower()
        
        # Add shayari
        if user_data.get('shayari', True) and random.random() < 0.12:
            mood = None
            if any(w in msg_lower for w in ['love', 'pyar', 'dil']):
                mood = 'love'
            elif any(w in msg_lower for w in ['sad', 'udas', 'dukh', 'cry']):
                mood = 'sad'
            elif any(w in msg_lower for w in ['motivation', 'himmat', 'try']):
                mood = 'motivation'
            
            if mood and mood in CONTENT['shayari']:
                shayari = random.choice(CONTENT['shayari'][mood])
                response = f"{response}\n\n{shayari}"
        
        # Add meme reference
        if user_data.get('meme', True) and random.random() < 0.15:
            if not any(w in msg_lower for w in ['sad', 'cry', 'problem', 'tension']):
                meme = random.choice(CONTENT['memes'])
                response = f"{response} {meme}"
        
        # Add question
        if random.random() < 0.2:
            q_type = 'flirty' if any(w in msg_lower for w in ['love', 'pyar', 'miss']) else 'casual'
            question = random.choice(CONTENT['questions'][q_type])
            response = f"{response} {question}"
        
        return response

# Initialize response system
response_system = ResponseSystem()

# ==================== UTILITIES ====================

def is_sleeping_time() -> bool:
    """Check if it's sleeping time"""
    now = datetime.now(Config.TIMEZONE).time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

async def simulate_typing(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    """Simulate realistic typing"""
    words = len(text.split())
    duration = min(3.0, max(1.0, words * 0.3))
    duration += random.uniform(0.2, 0.5)
    
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(duration)

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    is_private = update.effective_chat.type == "private"
    
    if is_private:
        # Update user info
        db.update_user_data(user.id, first_name=user.first_name)
        # Add to broadcast list
        db.broadcast_list.add(str(user.id))
        db._save_local()
    
    welcome_msg = f"""🌸 <b>Namaste {user.first_name}!</b>

Main <b>Niyati</b> hoon, ek sweet college girl from Delhi! 💫

Mujhse normally baat karo jaise kisi friend se karte ho! 😊

<i>Features: Shayari ✨ Memes 😄 Geeta Quotes 🙏</i>
<i>Commands: /help for more info</i>"""
    
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.HTML)
    logger.info(f"User {user.id} ({user.first_name}) started bot")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """📚 <b>Kaise use karu?</b>

<b>Chat karna:</b>
• Private: Normal baat karo
• Groups: "Niyati" likho ya @mention karo

<b>Commands:</b>
• /meme on/off - Meme references
• /shayari on/off - Shayari feature
• /geeta on/off - Geeta quotes
• /forget - Clear memory

<i>Bas itna hi! Simple hai na? 😊</i>"""
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle feature toggle commands"""
    if update.effective_chat.type != "private":
        await update.message.reply_text("Ye command sirf private chat mein use karo! 🤫")
        return
    
    parts = update.message.text.split()
    command = parts[0][1:]  # Remove /
    
    if len(parts) < 2 or parts[1] not in ['on', 'off']:
        await update.message.reply_text(f"Use: /{command} on/off")
        return
    
    status = parts[1] == 'on'
    user_id = update.effective_user.id
    
    # Update specific feature
    db.update_user_data(user_id, **{command: status})
    
    status_text = "ON ✅" if status else "OFF ❌"
    await update.message.reply_text(f"{command.capitalize()} ab {status_text} hai! 😊")

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forget command"""
    if update.effective_chat.type != "private":
        await update.message.reply_text("Private chat mein try karo! 🤫")
        return
    
    user_id = str(update.effective_user.id)
    
    # Clear from local storage
    if user_id in db.local_storage:
        del db.local_storage[user_id]
        db._save_local()
    
    await update.message.reply_text("Sab kuch bhul gayi main! Fresh start karte hai 😊")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command (admin only)"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        await update.message.reply_text("Ye sirf admin ke liye hai! 🚫")
        return
    
    parts = update.message.text.split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text("Format: /broadcast <pin> <message>")
        return
    
    if parts[1] != Config.BROADCAST_PIN:
        await update.message.reply_text("Wrong PIN! ❌")
        return
    
    message = parts[2]
    success = 0
    failed = 0
    
    for user_id in db.broadcast_list:
        try:
            await context.bot.send_message(
                int(user_id), 
                message,
                parse_mode=ParseMode.HTML
            )
            success += 1
            await asyncio.sleep(0.05)  # Rate limiting
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to send to {user_id}: {e}")
    
    await update.message.reply_text(f"✅ Sent: {success}\n❌ Failed: {failed}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command (owner only)"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        await update.message.reply_text("Admin only command! 🔒")
        return
    
    stats_text = f"""📊 <b>Bot Statistics</b>

👥 Total Users: {len(db.local_storage)}
📢 Broadcast List: {len(db.broadcast_list)}
💬 Tokens Used: {ai.tokens_used}
🗂️ Storage: {'Supabase ✅' if db.use_supabase else 'Local 📁'}
🤖 AI Status: {'Active ✅' if ai.model else 'Inactive ❌'}"""
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    try:
        if not update.message or not update.message.text:
            return
        
        is_private = update.effective_chat.type == "private"
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_msg = update.message.text
        user_name = update.effective_user.first_name
        
        # GROUP CHAT HANDLING
        if not is_private:
            # Check for daily Geeta quote
            now = datetime.now(Config.TIMEZONE)
            today = now.date()
            hour = now.hour
            
            if chat_id not in response_system.daily_geeta:
                response_system.daily_geeta[chat_id] = None
            
            # Send Geeta quote once per day between 7-10 AM
            if (response_system.daily_geeta[chat_id] != today and
                Config.GEETA_TIME_START.hour <= hour <= Config.GEETA_TIME_END.hour and
                random.random() < 0.1):
                
                quote = random.choice(CONTENT['geeta'])
                await context.bot.send_message(chat_id, f"🌅 Morning Wisdom:\n\n{quote}")
                response_system.daily_geeta[chat_id] = today
                logger.info(f"Sent daily Geeta quote to group {chat_id}")
                return
            
            # Check if should reply
            if not response_system.should_reply_in_group(update):
                # Store in ephemeral memory
                if str(chat_id) not in db.ephemeral:
                    db.ephemeral[str(chat_id)] = deque(maxlen=3)
                db.ephemeral[str(chat_id)].append(f"{user_name}: {user_msg[:50]}")
                return
            
            # Update cooldown
            response_system.cooldowns[chat_id] = datetime.now()
        
        # PRIVATE CHAT - Add to broadcast list
        else:
            db.broadcast_list.add(str(user_id))
        
        # Check sleeping time
        if is_sleeping_time():
            sleep_responses = [
                "Yaar abhi so rahi hun... kal baat karte hai 😴",
                "Zzz... neend aa rahi hai... good night! 🌙",
                "Sone ka time hai... sweet dreams! 💤"
            ]
            await update.message.reply_text(random.choice(sleep_responses))
            return
        
        # Show typing indicator
        await simulate_typing(chat_id, user_msg, context)
        
        # Get response
        response = await response_system.get_response(
            user_msg, 
            user_id, 
            user_name, 
            not is_private
        )
        
        # Save conversation (private only)
        if is_private:
            db.add_conversation(user_id, user_msg, response)
        
        # Send response
        await update.message.reply_text(response)
        
        logger.info(f"✅ Replied to {user_id} in {'private' if is_private else f'group {chat_id}'}")
        
    except Exception as e:
        logger.error(f"Message handler error: {e}")
        try:
            error_responses = [
                "Oops! Kuch gadbad ho gayi 😅",
                "Arey yaar, error aa gaya! 🙈",
                "Technical difficulty! Dobara try karo? 😊"
            ]
            await update.message.reply_text(random.choice(error_responses))
        except:
            pass

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages"""
    responses = [
        "Wow! Nice pic yaar! 📸",
        "Kya baat hai! Looking good 😍",
        "Photo to kamaal hai! 👌",
        "Saved! Just kidding 😄"
    ]
    await update.message.reply_text(random.choice(responses))

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages"""
    responses = [
        "Tumhari voice sunke acha laga! 🎤",
        "Aww, sweet voice! 😊",
        "Voice note! Special feel ho raha hai 💕",
        "Nice voice yaar! Aur sunao 🎵"
    ]
    await update.message.reply_text(random.choice(responses))

async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle sticker messages"""
    responses = [
        "Cute sticker! 😄",
        "Haha, ye wala mast hai! 🤣",
        "Sticker game strong! 💪",
        "Mujhe bhi bhejo ye wala! ✨"
    ]
    await update.message.reply_text(random.choice(responses))

# ==================== FLASK APP ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "bot": "Niyati",
        "version": "5.0",
        "personality": "Cute & Charming Girl",
        "status": "running",
        "time": datetime.now(Config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S IST")
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "sleeping": is_sleeping_time(),
        "ai_active": ai.model is not None,
        "users": len(db.local_storage)
    })

def run_flask():
    """Run Flask server"""
    logger.info(f"🌐 Starting Flask server on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=2)

# ==================== MAIN ====================

async def main():
    """Main bot function"""
    try:
        # Validate config
        Config.validate()
        
        logger.info("="*50)
        logger.info("🌸 Starting Niyati - AI Girlfriend Bot")
        logger.info("="*50)
        logger.info(f"🤖 Model: {Config.GEMINI_MODEL}")
        logger.info(f"💾 Storage: {'Supabase' if db.use_supabase else 'Local'}")
        logger.info("="*50)
        
        # Build application
        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add command handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("meme", toggle_command))
        app.add_handler(CommandHandler("shayari", toggle_command))
        app.add_handler(CommandHandler("geeta", toggle_command))
        app.add_handler(CommandHandler("forget", forget_command))
        app.add_handler(CommandHandler("broadcast", broadcast_command))
        app.add_handler(CommandHandler("stats", stats_command))
        
        # Add message handlers
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
        
        # Initialize and start
        await app.initialize()
        await app.start()
        logger.info("✅ Niyati is ready to chat!")
        logger.info("💬 Personality: Cute, Charming, Sweet Girl")
        
        # Start polling with error handling
        try:
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
        except Conflict:
            logger.warning("⚠️ Conflict detected, retrying...")
            await asyncio.sleep(5)
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
        
        # Keep running
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

if __name__ == "__main__":
    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Small delay for Flask to start
    time_module.sleep(1)
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Niyati says bye bye!")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        sys.exit(1)
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
    
    welcome = (
        f"\U0001F338 <b>Namaste {user.first_name}!</b>\n\n"
        "Main <b>Niyati</b> hoon, ek sweet college girl! \U0001F4AB\n\n"
        "Mujhse normally baat karo, main tumhari dost ban jaungi! \U0001F60A"
    )

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
