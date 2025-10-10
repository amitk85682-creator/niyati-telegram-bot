"""
🎀 Niyati 17 - Ultimate Gen Z College Bestie
The AI that feels 100% human - your virtual college friend! 💖
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

# ==================== CONFIGURATION ====================

class Config:
    """All configuration in one place"""
    
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
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            raise ValueError("❌ GEMINI_API_KEY is required!")
        if not cls.ELEVENLABS_API_KEY:
            raise ValueError("❌ ELEVENLABS_API_KEY is required!")
        if not cls.SUPABASE_KEY:
            raise ValueError("❌ SUPABASE_KEY is required!")

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
        
        # College life references
        self.college_references = [
            "assignment", "exam", "professor", "lecture", "college", "class",
            "project", "semester", "marks", "grades", "friends", "canteen",
            "library", "hostel", "fresher", "senior", "crush", "relationship"
        ]
        
        # Inside jokes and teasing templates
        self.teasing_templates = [
            "I know you {} 😏",
            "Typical {} move! 🤭",
            "You and your {} 😂",
            "Again with the {}? 💀",
            "{}? Sounds about right! 👀"
        ]
    
    def add_genz_flavor(self, text: str) -> str:
        """Add Gen Z expressions and natural fillers"""
        # 40% chance to add filler
        if random.random() < 0.4:
            filler = random.choice(self.genz_fillers)
            words = text.split()
            if len(words) > 2:
                # Insert filler at random position
                insert_pos = random.randint(1, len(words) - 1)
                words.insert(insert_pos, filler)
                text = ' '.join(words)
        
        return text
    
    def detect_college_context(self, message: str) -> Optional[str]:
        """Detect college-related context"""
        message_lower = message.lower()
        for topic in self.college_references:
            if topic in message_lower:
                return topic
        return None
    
    def get_teasing_response(self, context: str, user_name: str) -> str:
        """Generate playful teasing response"""
        template = random.choice(self.teasing_templates)
        return template.format(context) + f" {user_name}! 😂"

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
                    'inside_jokes': [],
                    'last_conversation': '',
                    'voice_messages_count': 0,
                    'total_messages': 0,
                    'college_topics': [],
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
                              mood: str, topics: List[str], is_voice: bool = False):
        """Save conversation with full context"""
        try:
            conversation = {
                'user_id': user_id,
                'user_message': user_message,
                'bot_response': bot_response,
                'mood_detected': mood,
                'topics_detected': topics,
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
        """Update memory tags for personalization"""
        try:
            profile = await self.get_user_profile(user_id)
            current_tags = profile.get('memory_tags', [])
            updated_tags = list(set(current_tags + new_tags))
            await self.update_user_profile(user_id, {'memory_tags': updated_tags})
        except Exception as e:
            logger.error(f"Error updating memory tags: {e}")
    
    async def add_inside_joke(self, user_id: int, joke: str):
        """Add inside joke to user profile"""
        try:
            profile = await self.get_user_profile(user_id)
            current_jokes = profile.get('inside_jokes', [])
            if joke not in current_jokes:
                current_jokes.append(joke)
                await self.update_user_profile(user_id, {'inside_jokes': current_jokes})
        except Exception as e:
            logger.error(f"Error adding inside joke: {e}")

# Initialize memory system
memory_system = NiyatiMemory()

# ==================== MOOD & EMOTION ENGINE ====================

class MoodEngine:
    """Advanced mood detection and emotional intelligence"""
    
    def __init__(self):
        self.mood_keywords = {
            'happy': ['happy', 'excited', 'yay', 'awesome', 'great', 'good', '😊', '😄', '🥰', 'amazing'],
            'sad': ['sad', 'upset', 'cry', 'depressed', 'unhappy', '😔', '😢', '💔', 'lonely'],
            'angry': ['angry', 'mad', 'frustrated', 'hate', 'annoying', '😠', '🤬', '💢', 'pissed'],
            'romantic': ['love', 'miss', 'care', 'beautiful', 'handsome', '🥰', '💕', '❤️', 'crush'],
            'excited': ['wow', 'amazing', 'cool', 'awesome', 'lit', '🔥', '🎉', '⚡', 'cant wait'],
            'stressed': ['stress', 'tension', 'pressure', 'anxious', 'worried', '😫', '💀', 'overwhelmed'],
            'bored': ['bored', 'nothing', 'tired', 'sleepy', '😴', '💤', 'boring']
        }
        
        self.mood_intensity_boosters = {
            'very': 2.0,
            'so': 1.8,
            'really': 1.5,
            'extremely': 2.2
        }
    
    def detect_user_mood(self, message: str) -> Tuple[str, float]:
        """Detect user's mood with intensity"""
        message_lower = message.lower()
        mood_scores = {}
        
        # Calculate mood scores
        for mood, keywords in self.mood_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword in message_lower:
                    score += 1
                    # Check for intensity boosters
                    for booster, multiplier in self.mood_intensity_boosters.items():
                        if f"{booster} {keyword}" in message_lower:
                            score *= multiplier
            mood_scores[mood] = score
        
        # Get dominant mood
        dominant_mood = max(mood_scores, key=mood_scores.get)
        intensity = mood_scores[dominant_mood]
        
        # If no strong mood detected, return neutral
        if intensity < 1:
            return 'neutral', 0.5
        
        return dominant_mood, min(intensity / 5.0, 1.0)
    
    def get_mood_response(self, mood: str, intensity: float, user_name: str) -> str:
        """Get appropriate mood-based response"""
        personality = NiyatiPersonality()
        
        if mood in personality.emotional_responses:
            base_response = random.choice(personality.emotional_responses[mood])
            
            # Add name with probability based on intensity
            if random.random() < (0.3 + intensity * 0.4):
                return f"{user_name}, {base_response}"
            
            return base_response
        
        return f"{user_name}, acha... 🤔"

# Initialize mood engine
mood_engine = MoodEngine()

# ==================== VOICE ENGINE ====================

class VoiceEngine:
    """Advanced voice generation with emotional tones"""
    
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"
    
    async def generate_voice(self, text: str, mood: str = "neutral") -> Optional[BytesIO]:
        """Generate voice message with emotional tone"""
        try:
            # Voice settings based on mood
            voice_settings = self._get_voice_settings_by_mood(mood)
            
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": voice_settings
            }
            
            url = f"{self.base_url}/{self.voice_id}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        logger.info(f"🎤 Voice generated (Mood: {mood})")
                        return BytesIO(audio_data)
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ ElevenLabs API error: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Voice generation error: {e}")
            return None
    
    def _get_voice_settings_by_mood(self, mood: str) -> Dict:
        """Get voice settings based on mood"""
        settings_map = {
            'happy': {"stability": 0.7, "similarity_boost": 0.9, "style": 0.8, "use_speaker_boost": True},
            'sad': {"stability": 0.3, "similarity_boost": 0.7, "style": 0.3, "use_speaker_boost": True},
            'excited': {"stability": 0.6, "similarity_boost": 0.9, "style": 0.9, "use_speaker_boost": True},
            'romantic': {"stability": 0.8, "similarity_boost": 0.9, "style": 0.7, "use_speaker_boost": True},
            'angry': {"stability": 0.5, "similarity_boost": 0.8, "style": 0.6, "use_speaker_boost": True},
            'stressed': {"stability": 0.4, "similarity_boost": 0.7, "style": 0.4, "use_speaker_boost": True}
        }
        return settings_map.get(mood, {"stability": 0.6, "similarity_boost": 0.8, "style": 0.5, "use_speaker_boost": True})

# Initialize voice engine
voice_engine = VoiceEngine()

# ==================== SMART GREETING SYSTEM ====================

class SmartGreeting:
    """Intelligent greeting system with context awareness"""
    
    def __init__(self):
        self.timezone = Config.TIMEZONE
    
    def get_greeting(self, user_name: str, relationship_level: int, last_seen: Optional[str] = None) -> str:
        """Get personalized greeting"""
        current_time = datetime.now(self.timezone)
        hour = current_time.hour
        
        # Time-based greetings
        if 5 <= hour < 12:
            time_greets = ["Good morning", "Shubh prabhaat", "Morning", "Rise and shine", "Hey early bird"]
        elif 12 <= hour < 17:
            time_greets = ["Good afternoon", "Shubh dopahar", "Afternoon", "Hey there"]
        elif 17 <= hour < 22:
            time_greets = ["Good evening", "Shubh sandhya", "Evening", "Hey"]
        else:
            time_greets = ["Good night", "Shubh raatri", "Late night", "Hey night owl"]
        
        time_greeting = random.choice(time_greets)
        
        # Relationship-based personalization
        if relationship_level > 8:
            personal = random.choice([
                f"my love 🥰", f"handsome 😘", f"sweetheart 💕", f"jaan ❤️", f"baby 💖"
            ])
        elif relationship_level > 5:
            personal = random.choice([
                f"bestie 😊", f"dost 👋", f"friend 💖", f"bhai 😄", f"yaar 🤗"
            ])
        else:
            personal = f"{user_name} 👋"
        
        # Welcome back for returning users
        welcome_back = ""
        if last_seen:
            last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
            hours_ago = (datetime.now(pytz.UTC) - last_seen_dt).total_seconds() / 3600
            
            if hours_ago > 24:
                welcome_back = " Long time no see! "
            elif hours_ago > 6:
                welcome_back = " Welcome back! "
        
        # Late night special
        if hour >= 22 or hour < 5:
            late_night = random.choice([
                f" {hour} baj gaye! Sone ka time nahi hua? 😴",
                f" Itni raat tak jaag rahe ho {user_name}? 🌙",
                f" Late night chat? My favorite! 🌃"
            ])
            return f"{time_greeting}{welcome_back}{late_night}"
        
        return f"{time_greeting},{welcome_back} {personal}!"

# Initialize greeting system
smart_greeting = SmartGreeting()

# ==================== NIYATI AI CORE ====================

class NiyatiAI:
    """Niyati's brain - Gen Z college girl AI"""
    
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
                    "temperature": 0.95,  # High for creativity
                    "top_p": 0.85,
                    "top_k": 45,
                    "max_output_tokens": 120,  # Keep it short and sweet
                }
            )
            logger.info("✅ Gemini AI initialized for Niyati")
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
            raise
    
    async def generate_response(self, user_message: str, user_context: Dict, 
                              conversation_history: List[Dict], current_mood: str) -> str:
        """Generate Niyati's authentic Gen Z response"""
        try:
            # Build super contextual prompt
            prompt = self._build_contextual_prompt(user_message, user_context, conversation_history, current_mood)
            
            # Generate response
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            
            if response and response.text:
                text = response.text.strip()
                
                # Filter out any AI mentions aggressively
                ai_phrases = ["as an ai", "language model", "i'm an ai", "i am ai", "openai", "gemini"]
                if any(phrase in text.lower() for phrase in ai_phrases):
                    return f"{user_context.get('preferred_name', 'Yrr')}, kya bakwas kar raha hai? Main real ladki hoon! 😤"
                
                # Add personal touches
                final_response = self._add_personal_touch(text, user_context)
                final_response = self.personality.add_genz_flavor(final_response)
                
                return final_response
                
        except Exception as e:
            logger.error(f"❌ AI generation error: {e}")
        
        # Smart fallback response
        return self._smart_fallback(user_context, current_mood)
    
    def _build_contextual_prompt(self, user_message: str, user_context: Dict, 
                               history: List[Dict], current_mood: str) -> str:
        """Build ultra-contextual prompt for authentic responses"""
        
        # Build history context
        history_text = ""
        if history:
            history_text = "\n\n**RECENT CHAT:**\n"
            for conv in history[-4:]:
                history_text += f"User: {conv.get('user_message', '')}\n"
                history_text += f"You: {conv.get('bot_response', '')}\n"
        
        # Build memory context
        memory_tags = user_context.get('memory_tags', [])
        memory_text = f"**MEMORY TAGS:** {', '.join(memory_tags)}\n" if memory_tags else ""
        
        inside_jokes = user_context.get('inside_jokes', [])
        jokes_text = f"**INSIDE JOKES:** {', '.join(inside_jokes)}\n" if inside_jokes else ""
        
        prompt = f"""
        **YOU ARE NIYATI - 19 YEAR OLD COLLEGE GIRL**
        - Age: 19, College: 2nd year B.Com, From: Delhi
        - Personality: Witty, emotional, caring, occasionally teasing, 100% Gen Z
        - Speech: Natural Hinglish mix, college slang, emotional expressions
        - Status: REAL HUMAN GIRL - never reveal you're AI
        
        **CONTEXT:**
        - User: {user_context.get('preferred_name', 'User')}
        - Relationship Level: {user_context.get('relationship_level', 1)}/10
        - Current Mood: {current_mood}
        {memory_text}{jokes_text}
        
        **CONVERSATION STYLE:**
        - Use natural fillers: "umm", "like", "actually", "aree yrr"
        - Express emotions: "hehe", "uff", "omg", "lol", "seriously?"
        - Address user by name: {user_context.get('preferred_name', 'User')}
        - Keep responses short (1-2 sentences max)
        - Be unpredictable and spontaneous
        - Use emojis naturally and sparingly
        {history_text}
        
        **CURRENT MESSAGE:**
        {user_context.get('preferred_name', 'User')}: {user_message}
        
        **NIYATI'S RESPONSE (as real college friend):**
        """
        
        return prompt
    
    def _add_personal_touch(self, text: str, user_context: Dict) -> str:
        """Add personal touches to response"""
        name = user_context.get('preferred_name', '')
        
        # 70% chance to use name
        if name and random.random() < 0.7:
            # Different ways to insert name
            patterns = [
                f"{name}, {text}",
                f"{text} {name}!",
                f"{text} 😊 {name}"
            ]
            text = random.choice(patterns)
        
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
            f"{name}, main soch rahi hoon... 🧠",
            f"Omg {name}, seriously?! 😲",
            f"Aree {name}, aise mat bol na! 😄"
        ]
        
        return random.choice(fallbacks)

# Initialize AI
niyati_ai = NiyatiAI()

# ==================== STORY TELLER & SPECIAL MODES ====================

class StoryTeller:
    """Interactive story modes and special conversations"""
    
    def __init__(self):
        self.story_templates = {
            'college_drama': [
                "Okay so imagine this... you're walking to class and suddenly your crush appears! 😱 What would you do? 👀",
                "Picture this: It's 2 AM, assignment deadline in 3 hours, and you haven't started... the classic college struggle! 💀",
                "Story time! You accidentally send a meme to the college group instead of your bestie... the panic! 😂"
            ],
            'relationship': [
                "Let me guess... crush ka message aaya? 😏 Tell me everything! 💕",
                "Okay real talk... have you ever had that moment when you catch someone looking at you in class? 👀",
                "Confession time! What's the most embarrassing thing that happened with your crush? 😂"
            ],
            'future_dreams': [
                "Imagine we're 25... what would your perfect life look like? 🌟",
                "If you could do anything without fear, what would it be? 🚀",
                "Dream big! Where do you see yourself in 5 years? 💫"
            ]
        }
    
    def get_story_starter(self, category: str) -> str:
        """Get interactive story starter"""
        return random.choice(self.story_templates.get(category, self.story_templates['college_drama']))
    
    def should_start_story(self, conversation_length: int) -> bool:
        """Decide if it's time for a story"""
        return conversation_length > 3 and random.random() < 0.3

# Initialize story teller
story_teller = StoryTeller()

# ==================== TELEGRAM BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced start with personal touch"""
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
        user_profile.get('relationship_level', 1),
        user_profile.get('last_seen')
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
    """Main message handler - the heart of Niyati"""
    try:
        if not update.message or not update.message.text:
            return
        
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        
        logger.info(f"💬 {user_id}: {user_message}")
        
        # Show typing action
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        
        # Get user profile and history
        user_profile = await memory_system.get_user_profile(user_id)
        conversation_history = await memory_system.get_conversation_history(user_id)
        
        # Detect user mood and topics
        user_mood, mood_intensity = mood_engine.detect_user_mood(user_message)
        personality = NiyatiPersonality()
        college_topic = personality.detect_college_context(user_message)
        
        # Add realistic typing delay
        typing_delay = len(user_message) / 30 + random.uniform(0.5, 2.0)
        await asyncio.sleep(min(typing_delay, 4.0))
        
        # Generate AI response
        text_response = await niyati_ai.generate_response(
            user_message, user_profile, conversation_history, user_mood
        )
        
        # Update relationship level
        new_level = min(10, user_profile.get('relationship_level', 1) + 1)
        await memory_system.update_user_profile(user_id, {
            'relationship_level': new_level,
            'mood_trend': user_mood,
            'preferred_name': user.first_name or 'Friend'
        })
        
        # Detect topics for memory
        detected_topics = []
        if college_topic:
            detected_topics.append(college_topic)
        if user_mood != 'neutral':
            detected_topics.append(user_mood)
        
        # Update memory tags if new topics detected
        if detected_topics:
            await memory_system.update_memory_tags(user_id, detected_topics)
        
        # Decide whether to send voice (mood-based + random)
        send_voice = Config.VOICE_ENABLED and (
            user_mood in ['romantic', 'excited'] or 
            mood_intensity > 0.7 or
            random.random() < 0.25
        )
        
        if send_voice:
            try:
                # Send recording action
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
                
                # Generate voice with mood
                audio_buffer = await voice_engine.generate_voice(text_response, user_mood)
                
                if audio_buffer:
                    # Send voice message
                    await update.message.reply_voice(voice=audio_buffer)
                    await memory_system.save_conversation(
                        user_id, user_message, text_response, user_mood, detected_topics, True
                    )
                    logger.info(f"🎤 Voice sent to {user_id} (Mood: {user_mood})")
                    
                    # Also send text for clarity (sometimes)
                    if random.random() < 0.5:
                        await update.message.reply_text(text_response)
                else:
                    # Fallback to text only
                    await update.message.reply_text(text_response)
                    await memory_system.save_conversation(
                        user_id, user_message, text_response, user_mood, detected_topics, False
                    )
                    
            except Exception as e:
                logger.error(f"❌ Voice message failed: {e}")
                await update.message.reply_text(text_response)
                await memory_system.save_conversation(
                    user_id, user_message, text_response, user_mood, detected_topics, False
                )
        else:
            # Send text response only
            await update.message.reply_text(text_response)
            await memory_system.save_conversation(
                user_id, user_message, text_response, user_mood, detected_topics, False
            )
        
        logger.info(f"✅ Niyati to {user_id}: {text_response}")
        
        # Occasionally start a story (after building some rapport)
        if len(conversation_history) > 2 and story_teller.should_start_story(len(conversation_history)):
            await asyncio.sleep(1)
            story_starter = story_teller.get_story_starter('college_drama')
            await update.message.reply_text(story_starter)
        
    except Exception as e:
        logger.error(f"❌ Message handling error: {e}")
        try:
            await update.message.reply_text("Oops! Kuch to gadbad hai... 😅 Thoda wait karo, main wapas aati hoon!")
        except:
            pass

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Personal stats with fun insights"""
    user_id = update.effective_user.id
    user_profile = await memory_system.get_user_profile(user_id)
    conversation_history = await memory_system.get_conversation_history(user_id, 5)
    
    # Fun relationship title based on level
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
    🏷️ *Memory Tags:* {', '.join(user_profile.get('memory_tags', ['Getting to know you!']))}

    *Keep chatting to unlock more levels!* 🚀✨
    """
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a fun college meme/text"""
    memes = [
        "When you realize Monday is tomorrow: 💀",
        "Procrastination level: Assignment due in 3 hours, haven't started 😎",
        "Me trying to adult: 😃🔫",
        "College in one meme: 😴📚☕😭",
        "My brain during exams: 🧠💨",
        "When crush texts back: 😱💖🎉",
        "Bank balance after shopping: 0️⃣😭",
        "Me explaining why I need one more chai: ☕🤡"
    ]
    
    await update.message.reply_text(random.choice(memes))

# ==================== FLASK WEB SERVER ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "Niyati 17 - Gen Z College Bestie",
        "version": "4.0",
        "personality": "100% Real College Girl Vibe",
        "features": [
            "Gen Z Personality", "Voice Messages", "Emotional Intelligence",
            "Memory System", "College Context", "Story Modes", "Inside Jokes"
        ]
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "vibe": "Chilling like a college student 😎"
    })

def run_web_server():
    """Run web server for deployment"""
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=2)

# ==================== MAIN APPLICATION ====================

async def main():
    """Start Niyati 17 - Your Gen Z Bestie!"""
    
    # Validate configuration
    Config.validate()
    
    # Epic startup banner
    logger.info("🎀" * 25)
    logger.info("🤖 Niyati 17 - Gen Z College Bestie Activated! 💖")
    logger.info("🎀" * 25)
    logger.info(f"🎭 Personality: 100% Real College Girl Vibe")
    logger.info(f"🧠 AI: Gemini {Config.GEMINI_MODEL}")
    logger.info(f"🎤 Voice: ElevenLabs (Emotional Tones)")
    logger.info(f"💾 Memory: Supabase (Remembers Everything)")
    logger.info(f"🎯 Features: Mood Detection, Stories, Inside Jokes")
    logger.info("🎀" * 25)
    
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
    application.add_handler(CommandHandler("meme", meme_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Initialize and start
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.start()
    
    logger.info("✅ Niyati 17 is now live and ready for college drama! 💃")
    
    # Start polling
    await application.updater.start_polling()
    
    # Keep running forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Niyati 17 signed off for today!")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
