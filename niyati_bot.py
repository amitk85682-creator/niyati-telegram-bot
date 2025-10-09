"""
Niyati Bot - Your Gen Z College Bestie 💖
Complete implementation in a single file
"""

import os
import re
import json
import random
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

# Third-party imports
import google.generativeai as genai
from elevenlabs import generate, set_api_key as set_elevenlabs_key
from supabase import create_client, Client
import nltk
from textblob import TextBlob
import numpy as np
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ================== CONFIGURATION ==================
# Load from environment or set directly for testing
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-key-here')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', 'your-elevenlabs-key-here')
SUPABASE_URL = os.getenv('SUPABASE_URL', 'your-supabase-url-here')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'your-supabase-key-here')

# Configure APIs
genai.configure(api_key=GEMINI_API_KEY)
set_elevenlabs_key(ELEVENLABS_API_KEY)

# Download NLTK data
try:
    nltk.download('vader_lexicon', quiet=True)
    from nltk.sentiment import SentimentIntensityAnalyzer
except:
    print("NLTK download failed, sentiment analysis will be limited")

# ================== DATA MODELS ==================

class MoodType(Enum):
    HAPPY = "happy"
    SAD = "sad"
    STRESSED = "stressed"
    BORED = "bored"
    EXCITED = "excited"
    ANGRY = "angry"
    ROMANTIC = "romantic"
    STUDIOUS = "studious"
    PLAYFUL = "playful"
    TIRED = "tired"
    NEUTRAL = "neutral"

@dataclass
class UserContext:
    user_id: str
    name: str
    mood: MoodType
    language_preference: str
    last_topics: List[str]
    relationship_level: int
    conversation_history: List[Dict]
    preferences: Dict
    memory_tags: Dict

# ================== MOOD ENGINE ==================

class MoodEngine:
    """Advanced mood detection and emotional intelligence"""
    
    def __init__(self):
        try:
            self.sia = SentimentIntensityAnalyzer()
        except:
            self.sia = None
            
        self.mood_patterns = {
            'stressed': {
                'keywords': ['exam', 'test', 'deadline', 'assignment', 'project', 
                           'tension', 'pressure', 'worried', 'anxiety', 'stress'],
                'hindi': ['pareshan', 'chinta', 'tension', 'darr', 'pareshani'],
                'emojis': ['😰', '😓', '😫', '💀', '😵'],
                'phrases': ['killing me', 'so much work', 'cant handle', 'too much']
            },
            'happy': {
                'keywords': ['happy', 'excited', 'amazing', 'awesome', 'great', 'yay', 'love'],
                'hindi': ['khushi', 'maza', 'badhiya', 'accha', 'khush'],
                'emojis': ['😊', '😄', '🎉', '✨', '💖', '🥰'],
                'phrases': ['so happy', 'best day', 'love this', 'feeling good']
            },
            'romantic': {
                'keywords': ['crush', 'love', 'date', 'cute', 'heart', 'miss', 'like'],
                'hindi': ['pyaar', 'ishq', 'mohabbat', 'dil'],
                'emojis': ['❤️', '💕', '😍', '🥰', '💑'],
                'phrases': ['in love', 'my crush', 'asked out', 'she said yes']
            },
            'sad': {
                'keywords': ['sad', 'depressed', 'crying', 'hurt', 'lonely', 'broken', 'down'],
                'hindi': ['dukh', 'rona', 'udaas', 'tanha', 'dukhi'],
                'emojis': ['😢', '😔', '💔', '😭'],
                'phrases': ['feeling down', 'not okay', 'want to cry', 'feeling low']
            },
            'bored': {
                'keywords': ['bored', 'boring', 'nothing', 'meh', 'ugh', 'dull'],
                'hindi': ['bore', 'bakwas', 'kuch nahi'],
                'emojis': ['😑', '😴', '🥱'],
                'phrases': ['nothing to do', 'so boring', 'kill time']
            }
        }
    
    def analyze_mood(self, text: str, conversation_history: List[str] = None) -> Dict:
        """Comprehensive mood analysis"""
        
        # Basic sentiment analysis
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
        except:
            polarity = 0.0
        
        # VADER sentiment
        if self.sia:
            vader_scores = self.sia.polarity_scores(text)
        else:
            vader_scores = {'compound': 0.0, 'pos': 0.0, 'neu': 0.5, 'neg': 0.0}
        
        # Pattern matching
        detected_moods = self._pattern_matching(text)
        
        # Combine all signals
        mood_result = self._combine_mood_signals(polarity, vader_scores, detected_moods)
        
        return mood_result
    
    def _pattern_matching(self, text: str) -> Dict[str, float]:
        """Match text against mood patterns"""
        
        text_lower = text.lower()
        mood_scores = {}
        
        for mood, patterns in self.mood_patterns.items():
            score = 0
            
            # Check keywords
            for keyword in patterns['keywords']:
                if keyword in text_lower:
                    score += 2
            
            # Check Hindi keywords
            for keyword in patterns.get('hindi', []):
                if keyword in text_lower:
                    score += 2
            
            # Check emojis
            for emoji in patterns.get('emojis', []):
                if emoji in text:
                    score += 3
            
            # Check phrases
            for phrase in patterns.get('phrases', []):
                if phrase in text_lower:
                    score += 4
            
            mood_scores[mood] = score
        
        # Normalize scores
        total = sum(mood_scores.values()) or 1
        return {k: v/total for k, v in mood_scores.items()}
    
    def _combine_mood_signals(self, polarity, vader, pattern_moods) -> Dict:
        """Combine all mood signals into final mood assessment"""
        
        # Determine primary mood
        if pattern_moods:
            primary_mood = max(pattern_moods, key=pattern_moods.get)
            if pattern_moods[primary_mood] == 0:
                primary_mood = 'neutral'
        else:
            if polarity > 0.3:
                primary_mood = 'happy'
            elif polarity < -0.3:
                primary_mood = 'sad'
            else:
                primary_mood = 'neutral'
        
        # Calculate confidence
        confidence = 0.5
        if pattern_moods and pattern_moods.get(primary_mood, 0) > 0.4:
            confidence += 0.3
        if abs(polarity) > 0.5:
            confidence += 0.2
        
        return {
            'primary_mood': primary_mood,
            'confidence': min(confidence, 1.0),
            'polarity': polarity,
            'vader_scores': vader,
            'pattern_scores': pattern_moods
        }

# ================== MEMORY SYSTEM ==================

class MemorySystem:
    """Niyati's memory and context management system"""
    
    def __init__(self, supabase_client: Client = None):
        self.db = supabase_client
        self.short_term_memory = {}
        self.working_memory = defaultdict(list)
        self.long_term_patterns = {}
        
        # In-memory storage if no database
        self.local_storage = {
            'users': {},
            'conversations': defaultdict(list),
            'preferences': defaultdict(dict),
            'memories': defaultdict(list)
        }
    
    async def remember_user(self, user_id: str) -> Dict:
        """Retrieve all memories about a user"""
        
        if self.db:
            try:
                # Get from database
                user_data = self.db.table('users').select("*").eq('user_id', user_id).single().execute()
                recent_convos = self.db.table('conversation_history')\
                    .select("*").eq('user_id', user_id)\
                    .order('timestamp', desc=True).limit(50).execute()
                preferences = self.db.table('user_preferences')\
                    .select("*").eq('user_id', user_id).execute()
                memories = self.db.table('special_memories')\
                    .select("*").eq('user_id', user_id).execute()
                
                return {
                    'profile': user_data.data if user_data else {},
                    'recent_conversations': recent_convos.data if recent_convos else [],
                    'preferences': self._process_preferences(preferences.data if preferences else []),
                    'special_memories': memories.data if memories else [],
                    'patterns': await self._analyze_patterns(user_id)
                }
            except Exception as e:
                print(f"Database error: {e}")
        
        # Fallback to local storage
        return {
            'profile': self.local_storage['users'].get(user_id, {}),
            'recent_conversations': self.local_storage['conversations'][user_id][-50:],
            'preferences': self.local_storage['preferences'][user_id],
            'special_memories': self.local_storage['memories'][user_id],
            'patterns': {}
        }
    
    async def create_memory(self, user_id: str, memory_type: str, content: Dict):
        """Create a new memory"""
        
        memory_data = {
            'user_id': user_id,
            'type': memory_type,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'importance': self._calculate_importance(memory_type, content)
        }
        
        if self.db:
            try:
                if memory_type == 'special':
                    self.db.table('special_memories').insert(memory_data).execute()
            except Exception as e:
                print(f"Memory storage error: {e}")
        
        # Local storage
        self.local_storage['memories'][user_id].append(memory_data)
        
        # Update working memory
        self.working_memory[user_id].append({
            'type': memory_type,
            'content': content,
            'time': datetime.now()
        })
        
        self._cleanup_working_memory(user_id)
    
    def _calculate_importance(self, memory_type: str, content: Dict) -> int:
        """Calculate memory importance score (1-10)"""
        
        importance_factors = {
            'special': 8,
            'emotional': 7,
            'preference': 5,
            'routine': 3,
            'casual': 2
        }
        
        base_importance = importance_factors.get(memory_type, 3)
        
        if 'emotion_intensity' in content:
            base_importance += content['emotion_intensity'] // 3
        
        return min(10, base_importance)
    
    def _process_preferences(self, preferences_data: List) -> Dict:
        """Process and organize user preferences"""
        
        organized = defaultdict(dict)
        
        for pref in preferences_data:
            category = pref.get('preference_type', 'general')
            key = pref.get('preference_key')
            value = pref.get('preference_value')
            weight = pref.get('weight', 1.0)
            
            organized[category][key] = {
                'value': value,
                'weight': weight,
                'last_updated': pref.get('updated_at')
            }
        
        return dict(organized)
    
    async def _analyze_patterns(self, user_id: str) -> Dict:
        """Analyze user behavior patterns"""
        
        conversations = self.local_storage['conversations'][user_id][-30:]
        
        if not conversations:
            return {}
        
        patterns = {
            'chat_times': self._analyze_chat_times(conversations),
            'mood_patterns': self._analyze_mood_patterns(conversations)
        }
        
        return patterns
    
    def _analyze_chat_times(self, conversations: List) -> Dict:
        """Analyze when user typically chats"""
        
        time_slots = defaultdict(int)
        
        for conv in conversations:
            if isinstance(conv, dict) and 'timestamp' in conv:
                try:
                    timestamp = datetime.fromisoformat(conv['timestamp'])
                    hour = timestamp.hour
                    
                    if 5 <= hour < 12:
                        time_slots['morning'] += 1
                    elif 12 <= hour < 17:
                        time_slots['afternoon'] += 1
                    elif 17 <= hour < 21:
                        time_slots['evening'] += 1
                    else:
                        time_slots['night'] += 1
                except:
                    pass
        
        return dict(time_slots)
    
    def _analyze_mood_patterns(self, conversations: List) -> Dict:
        """Analyze mood patterns over time"""
        
        mood_frequency = defaultdict(int)
        
        for conv in conversations:
            if isinstance(conv, dict) and 'mood' in conv:
                mood_frequency[conv['mood']] += 1
        
        return {'frequency': dict(mood_frequency)}
    
    def _cleanup_working_memory(self, user_id: str):
        """Remove old items from working memory"""
        
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        self.working_memory[user_id] = [
            mem for mem in self.working_memory[user_id]
            if mem['time'] > cutoff_time
        ]

# ================== NIYATI BRAIN (MAIN BOT) ==================

class NiyatiBrain:
    """Main brain of Niyati - Your Gen Z College Bestie"""
    
    def __init__(self):
        self.personality = self._initialize_personality()
        self.supabase = self._initialize_database()
        self.gemini_model = genai.GenerativeModel('gemini-pro')
        self.voice_id = "ni6cdqyS9wBvic5LPA7M"
        self.mood_engine = MoodEngine()
        self.memory_system = MemorySystem(self.supabase)
        
        # Personality traits
        self.expressions = {
            'happy': ['😊', '😄', '🎉', '✨', '💖', '🥰', 'hehe', 'yay!'],
            'sad': ['😔', '🥺', '😢', '💔', 'oh no...'],
            'teasing': ['😏', '🤭', '😜', '👀', 'hehe', 'lol'],
            'supportive': ['🤗', '💪', '❤️', '🫂', "you got this!"],
            'shocked': ['😱', '😲', '💀', 'OMG!', 'WHAT?!'],
            'thinking': ['🤔', '🧐', '💭', 'hmm...', 'let me think...']
        }
        
        self.fillers = {
            'hindi': ['aree', 'yaar', 'matlab', 'acha', 'toh', 'bas', 'na'],
            'english': ['like', 'umm', 'basically', 'literally', 'so', 'actually'],
            'hinglish': ['yaar', 'na', 'kya', 'hai na', 'chal', 'aree']
        }
        
        self.time_greetings = {
            'morning': [
                "Good morning sunshine! ☀️ Coffee pi ya nahi?",
                "Uth gaye finally! 😄 Kitne baje soye the?",
                "Morning! Ready for another day of drama? 😂",
                "GM! Breakfast kya hai aaj? 🥞"
            ],
            'afternoon': [
                "Lunch break? Ya class bunk? 😏",
                "Afternoon laziness hitting hard? Same yaar! 😴",
                "Kya chal raha hai? Boring lectures? 💀",
                "Bhook lagi? Let's order something! 🍕"
            ],
            'evening': [
                "Shaam ki chai ready? ☕",
                "Finally free? Let's gossip! 👀",
                "Evening plans? Ya Netflix and chill? 😌",
                "Sunset dekhne chalein? 🌅"
            ],
            'night': [
                "Late night confession time? 🌙",
                "Sleep is for the weak, right? 😂",
                "2 AM and still awake? Kya scene hai? 👀",
                "Insomnia gang! 🦉"
            ]
        }
        
        # Response templates for different moods
        self.response_templates = {
            'happy': [
                "OMG {name}! That's so amazing! 🎉",
                "Yaar this makes me so happy! 😊",
                "Aww {name}, you're literally glowing today! ✨"
            ],
            'sad': [
                "Oh {name} 🥺 Come here, virtual hug! 🤗",
                "I'm here for you, always remember that 💖",
                "Want to talk about it? Or should I distract you with memes? 🫂"
            ],
            'stressed': [
                "{name}, breathe! In... out... 🧘‍♀️",
                "You've got this! Remember how you handled last time? 💪",
                "Break lelo thoda, world won't end promise! 😌"
            ],
            'bored': [
                "Uff same! Let's do something fun? 🎮",
                "Want to hear some college gossip? 👀",
                "Truth or dare khelein? 😏"
            ]
        }
    
    def _initialize_personality(self) -> Dict:
        """Initialize Niyati's core personality"""
        return {
            'name': 'Niyati',
            'age': 19,
            'personality_traits': [
                'witty', 'caring', 'playful', 'emotional',
                'supportive', 'teasing', 'dramatic', 'loyal',
                'spontaneous', 'empathetic'
            ],
            'interests': [
                'college gossip', 'relationships', 'memes',
                'bollywood', 'food', 'fashion', 'anime',
                'k-dramas', 'music', 'photography'
            ],
            'speaking_style': 'casual_genZ_hinglish',
            'emotional_range': 'high',
            'sarcasm_level': 7,
            'empathy_level': 9,
            'humor_level': 8
        }
    
    def _initialize_database(self) -> Optional[Client]:
        """Initialize Supabase connection"""
        try:
            if SUPABASE_URL and SUPABASE_KEY:
                return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"Database initialization failed: {e}")
        return None
    
    async def detect_mood(self, message: str, context: UserContext) -> MoodType:
        """Detect user's mood from message and context"""
        
        # Use mood engine for analysis
        mood_analysis = self.mood_engine.analyze_mood(message)
        primary_mood = mood_analysis['primary_mood']
        
        # Map to MoodType enum
        mood_map = {
            'happy': MoodType.HAPPY,
            'sad': MoodType.SAD,
            'stressed': MoodType.STRESSED,
            'bored': MoodType.BORED,
            'angry': MoodType.ANGRY,
            'romantic': MoodType.ROMANTIC,
            'neutral': MoodType.NEUTRAL
        }
        
        return mood_map.get(primary_mood, MoodType.NEUTRAL)
    
    def get_personality_mode(self, mood: MoodType, time_of_day: str) -> Dict:
        """Adjust personality based on mood and time"""
        
        personality_modes = {
            MoodType.HAPPY: {
                'energy': 'high',
                'teasing_level': 8,
                'emoji_frequency': 'high',
                'response_style': 'playful_excited'
            },
            MoodType.SAD: {
                'energy': 'gentle',
                'teasing_level': 2,
                'emoji_frequency': 'medium',
                'response_style': 'caring_supportive'
            },
            MoodType.STRESSED: {
                'energy': 'calm',
                'teasing_level': 3,
                'emoji_frequency': 'medium',
                'response_style': 'understanding_helpful'
            },
            MoodType.BORED: {
                'energy': 'energetic',
                'teasing_level': 7,
                'emoji_frequency': 'high',
                'response_style': 'entertaining_engaging'
            },
            MoodType.ROMANTIC: {
                'energy': 'playful',
                'teasing_level': 9,
                'emoji_frequency': 'high',
                'response_style': 'teasing_supportive'
            }
        }
        
        mode = personality_modes.get(mood, personality_modes[MoodType.NEUTRAL])
        
        # Time-based adjustments
        if time_of_day == 'night':
            mode['energy'] = 'chill'
            mode['response_style'] += '_intimate'
        elif time_of_day == 'morning':
            mode['energy'] = 'fresh' if mode['energy'] != 'gentle' else 'gentle'
        
        return mode
    
    async def generate_response(self, 
                                message: str, 
                                context: UserContext) -> Tuple[str, Optional[bytes], Dict]:
        """Generate Niyati's response with text and voice"""
        
        # Detect mood
        mood = await self.detect_mood(message, context)
        
        # Get current time period
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_period = 'morning'
        elif 12 <= hour < 17:
            time_period = 'afternoon'
        elif 17 <= hour < 21:
            time_period = 'evening'
        else:
            time_period = 'night'
        
        # Get personality mode
        personality_mode = self.get_personality_mode(mood, time_period)
        
        # Check for special greetings
        if any(greeting in message.lower() for greeting in ['hi', 'hello', 'hey', 'sup']):
            text_response = random.choice(self.time_greetings[time_period])
        else:
            # Build and generate response
            prompt = self._build_prompt(message, context, mood, personality_mode, time_period)
            
            try:
                response = self.gemini_model.generate_content(prompt)
                text_response = response.text
            except Exception as e:
                print(f"Gemini error: {e}")
                # Fallback response
                text_response = self._get_fallback_response(mood, context.name)
        
        # Add natural elements
        text_response = self._add_natural_elements(text_response, context.language_preference)
        
        # Generate voice (optional)
        voice_audio = None
        if ELEVENLABS_API_KEY and ELEVENLABS_API_KEY != 'your-elevenlabs-key-here':
            voice_audio = await self._generate_voice(text_response, mood)
        
        # Update memory
        await self.memory_system.create_memory(
            context.user_id,
            'conversation',
            {
                'user_message': message,
                'bot_response': text_response,
                'mood': mood.value,
                'timestamp': datetime.now().isoformat()
            }
        )
        
        return text_response, voice_audio, {
            'mood': mood.value,
            'personality_mode': personality_mode,
            'time_period': time_period
        }
    
    def _build_prompt(self, 
                      message: str, 
                      context: UserContext, 
                      mood: MoodType,
                      personality_mode: Dict,
                      time_period: str) -> str:
        """Build the prompt for Gemini"""
        
        recent_history = context.conversation_history[-5:] if context.conversation_history else []
        history_text = "\n".join([f"{h.get('role', 'User')}: {h.get('message', '')}" for h in recent_history])
        
        prompt = f"""
        You are Niyati, a 19-year-old college girl and the user's best friend. 
        
        PERSONALITY:
        - Age: 19, Gen-Z college student
        - Style: {personality_mode['response_style']}
        - Current mood response: {mood.value}
        - Energy level: {personality_mode['energy']}
        - Teasing level: {personality_mode['teasing_level']}/10
        - Time: {time_period}
        
        USER CONTEXT:
        - Name: {context.name}
        - Their mood: {mood.value}
        - Language preference: {context.language_preference}
        - Relationship level: {context.relationship_level}/10
        
        RECENT CONVERSATION:
        {history_text}
        
        USER MESSAGE: {message}
        
        RESPONSE RULES:
        1. Be a real college friend, not an AI
        2. Use {context.language_preference} naturally
        3. Mix Hindi/English if Hinglish preferred
        4. Add expressions like "yaar", "aree", "uff" naturally
        5. Reference shared college experiences
        6. Use 1-2 emojis naturally
        7. Be {personality_mode['response_style']}
        8. Keep it casual and friend-like
        9. Never say you're an AI or assistant
        10. Be spontaneous and genuine
        
        Generate a natural, friendly response as Niyati:
        """
        
        return prompt
    
    def _get_fallback_response(self, mood: MoodType, name: str) -> str:
        """Get fallback response when API fails"""
        
        templates = self.response_templates.get(
            mood.value,
            ["Hey {name}! Tell me more! 😊"]
        )
        
        response = random.choice(templates)
        return response.format(name=name)
    
    def _add_natural_elements(self, response: str, language: str) -> str:
        """Add natural speaking elements to response"""
        
        # Add random fillers
        fillers = self.fillers.get(language, self.fillers['hinglish'])
        
        # Randomly insert fillers
        words = response.split()
        if len(words) > 10 and random.random() > 0.5:
            insert_pos = random.randint(3, min(len(words)-3, 10))
            filler = random.choice(fillers)
            words.insert(insert_pos, filler)
            response = ' '.join(words)
        
        # Add thinking pauses
        if '?' in response and random.random() > 0.6:
            response = response.replace('?', '? 🤔', 1)
        
        return response
    
    async def _generate_voice(self, text: str, mood: MoodType) -> Optional[bytes]:
        """Generate voice using ElevenLabs"""
        
        voice_settings = {
            MoodType.HAPPY: {"stability": 0.5, "similarity_boost": 0.75},
            MoodType.SAD: {"stability": 0.8, "similarity_boost": 0.75},
            MoodType.EXCITED: {"stability": 0.3, "similarity_boost": 0.75},
            MoodType.STRESSED: {"stability": 0.9, "similarity_boost": 0.75}
        }
        
        settings = voice_settings.get(mood, {"stability": 0.5, "similarity_boost": 0.75})
        
        try:
            audio = generate(
                text=text,
                voice=self.voice_id,
                model="eleven_monolingual_v1",
                **settings
            )
            return audio
        except Exception as e:
            print(f"Voice generation error: {e}")
            return None

# ================== API ENDPOINTS ==================

app = FastAPI(title="Niyati Bot API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize bot
niyati_bot = NiyatiBrain()

# Pydantic models for API
class ChatMessage(BaseModel):
    user_id: str
    message: str
    user_name: Optional[str] = "friend"
    language_preference: Optional[str] = "hinglish"

class ChatResponse(BaseModel):
    text: str
    mood: str
    typing_time: float
    suggestions: Optional[List[str]]

# ================== WEBSOCKET ENDPOINT ==================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat"""
    
    await websocket.accept()
    user_id = str(uuid.uuid4())
    
    # Send welcome message
    await websocket.send_json({
        "type": "system",
        "message": "Niyati connected! 💖",
        "text": "Heyy! Finally someone interesting! Kya chal raha hai? 😄"
    })
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            # Show typing indicator
            await websocket.send_json({
                "type": "typing",
                "status": True
            })
            
            # Simulate typing delay
            typing_time = random.uniform(1.0, 3.0)
            await asyncio.sleep(typing_time)
            
            # Create user context
            user_context = UserContext(
                user_id=data.get('user_id', user_id),
                name=data.get('name', 'friend'),
                mood=MoodType.NEUTRAL,
                language_preference=data.get('language', 'hinglish'),
                last_topics=[],
                relationship_level=5,
                conversation_history=[],
                preferences={},
                memory_tags={}
            )
            
            # Generate response
            text_response, voice_audio, metadata = await niyati_bot.generate_response(
                data['message'],
                user_context
            )
            
            # Get suggestions
            suggestions = get_suggestions(metadata['mood'])
            
            # Send response
            await websocket.send_json({
                "type": "message",
                "text": text_response,
                "mood": metadata['mood'],
                "timestamp": datetime.now().isoformat(),
                "suggestions": suggestions
            })
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

# ================== REST ENDPOINTS ==================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Niyati Bot API is running! 💖",
        "status": "active",
        "personality": "Your Gen Z College Bestie",
        "endpoints": {
            "websocket": "/ws",
            "chat": "/chat",
            "health": "/health"
        }
    }

@app.post("/chat")
async def chat_endpoint(message: ChatMessage) -> ChatResponse:
    """REST endpoint for chat"""
    
    # Create user context
    user_context = UserContext(
        user_id=message.user_id,
        name=message.user_name,
        mood=MoodType.NEUTRAL,
        language_preference=message.language_preference,
        last_topics=[],
        relationship_level=5,
        conversation_history=[],
        preferences={},
        memory_tags={}
    )
    
    # Generate response
    text_response, voice_audio, metadata = await niyati_bot.generate_response(
        message.message,
        user_context
    )
    
    # Get suggestions
    suggestions = get_suggestions(metadata['mood'])
    
    return ChatResponse(
        text=text_response,
        mood=metadata['mood'],
        typing_time=random.uniform(1.0, 3.0),
        suggestions=suggestions
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot_name": "Niyati",
        "version": "1.0.0"
    }

# ================== HELPER FUNCTIONS ==================

def get_suggestions(mood: str) -> List[str]:
    """Generate contextual suggestions for quick replies"""
    
    suggestions_map = {
        'happy': [
            "Tell me more! 😄",
            "That's amazing! 🎉",
            "Haha same! 😂",
            "Yay! So happy for you! ✨"
        ],
        'sad': [
            "Want to talk about it? 🫂",
            "I'm here for you 💖",
            "Let's do something fun?",
            "Sending virtual hugs! 🤗"
        ],
        'stressed': [
            "Take a break na 🧘‍♀️",
            "You got this! 💪",
            "Want some tips?",
            "Deep breaths! It'll be okay 💙"
        ],
        'bored': [
            "Let's play something! 🎮",
            "Wanna hear gossip? 👀",
            "Movie recommendations?",
            "Truth or dare? 😏"
        ],
        'romantic': [
            "OMG tell me everything! 😍",
            "Ship ship ship! 💕",
            "Aww that's so cute! 🥰",
            "Details please! 👀"
        ],
        'neutral': [
            "Tell me more!",
            "Interesting! 🤔",
            "And then?",
            "Hmm, go on..."
        ]
    }
    
    return suggestions_map.get(mood, suggestions_map['neutral'])

# ================== MAIN EXECUTION ==================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════╗
    ║     🎓 NIYATI BOT - STARTING UP! 🎓    ║
    ║    Your Gen Z College Bestie 💖       ║
    ╚══════════════════════════════════════╝
    """)
    
    print("✨ Initializing Niyati's personality...")
    print("🧠 Loading mood detection engine...")
    print("💾 Setting up memory system...")
    print("🌐 Starting API server...")
    print("\n📱 Access the bot at: http://localhost:8000")
    print("🔌 WebSocket endpoint: ws://localhost:8000/ws")
    print("\n✅ Niyati is ready to chat! 💬\n")
    
    # Run the FastAPI server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
