import os
import re
import json
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import google.generativeai as genai
from elevenlabs import generate, set_api_key
from supabase import create_client, Client
import asyncio
from dataclasses import dataclass
from enum import Enum

# Configuration
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
set_api_key(os.getenv('ELEVENLABS_API_KEY'))

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

@dataclass
class UserContext:
    user_id: str
    name: str
    mood: MoodType
    language_preference: str
    last_topics: List[str]
    relationship_level: int  # 1-10 friendship level
    conversation_history: List[Dict]
    preferences: Dict
    memory_tags: Dict

class NiyatiBrain:
    """Main brain of Niyati - Your Gen Z College Bestie"""
    
    def __init__(self):
        self.personality = self._initialize_personality()
        self.supabase = self._initialize_database()
        self.gemini_model = genai.GenerativeModel('gemini-pro')
        self.voice_id = "ni6cdqyS9wBvic5LPA7M"  # ElevenLabs voice
        self.typing_delay = (0.5, 2.0)  # Simulate typing
        
        # Personality traits
        self.expressions = {
            'happy': ['😊', '😄', '🎉', '✨', '💖', '🥰'],
            'sad': ['😔', '🥺', '😢', '💔'],
            'teasing': ['😏', '🤭', '😜', '👀'],
            'supportive': ['🤗', '💪', '❤️', '🫂'],
            'shocked': ['😱', '😲', '💀', 'OMG!'],
            'thinking': ['🤔', '🧐', '💭', 'hmm...']
        }
        
        self.fillers = {
            'hindi': ['aree', 'yaar', 'matlab', 'acha', 'toh', 'bas'],
            'english': ['like', 'umm', 'basically', 'literally', 'so'],
            'hinglish': ['yaar', 'na', 'kya', 'hai na', 'chal']
        }
        
        self.time_greetings = {
            'morning': [
                "Good morning sunshine! ☀️ Coffee pi ya nahi?",
                "Uth gaye finally! 😄 Kitne baje soye the?",
                "Morning! Ready for another day of drama? 😂"
            ],
            'afternoon': [
                "Lunch break? Ya class bunk? 😏",
                "Afternoon laziness hitting hard? Same yaar! 😴",
                "Kya chal raha hai? Boring lectures? 💀"
            ],
            'evening': [
                "Shaam ki chai ready? ☕",
                "Finally free? Let's gossip! 👀",
                "Evening plans? Ya Netflix and chill? 😌"
            ],
            'night': [
                "Late night confession time? 🌙",
                "Sleep is for the weak, right? 😂",
                "2 AM and still awake? Kya scene hai? 👀"
            ]
        }
    
    def _initialize_personality(self) -> Dict:
        """Initialize Niyati's core personality"""
        return {
            'name': 'Niyati',
            'age': 19,
            'personality_traits': [
                'witty', 'caring', 'playful', 'emotional',
                'supportive', 'teasing', 'dramatic', 'loyal'
            ],
            'interests': [
                'college gossip', 'relationships', 'memes',
                'bollywood', 'food', 'fashion', 'anime'
            ],
            'speaking_style': 'casual_genZ_hinglish',
            'emotional_range': 'high',
            'sarcasm_level': 7,
            'empathy_level': 9
        }
    
    def _initialize_database(self) -> Client:
        """Initialize Supabase connection"""
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        return create_client(url, key)
    
    async def detect_mood(self, message: str, context: UserContext) -> MoodType:
        """Detect user's mood from message and context"""
        mood_indicators = {
            MoodType.HAPPY: ['haha', 'lol', 'yay', 'excited', 'amazing', '😊', '😄'],
            MoodType.SAD: ['sad', 'upset', 'crying', 'depressed', 'down', '😢', '😔'],
            MoodType.STRESSED: ['stressed', 'exam', 'deadline', 'pressure', 'worried'],
            MoodType.BORED: ['bored', 'boring', 'nothing', 'meh', 'ugh'],
            MoodType.ANGRY: ['angry', 'mad', 'frustrated', 'hate', 'annoying'],
            MoodType.ROMANTIC: ['crush', 'love', 'date', 'cute', 'relationship'],
            MoodType.TIRED: ['tired', 'sleepy', 'exhausted', 'yawn']
        }
        
        message_lower = message.lower()
        mood_scores = {}
        
        for mood, indicators in mood_indicators.items():
            score = sum(1 for indicator in indicators if indicator in message_lower)
            mood_scores[mood] = score
        
        # Get mood with highest score, default to context mood if no clear indicator
        detected_mood = max(mood_scores, key=mood_scores.get)
        
        if mood_scores[detected_mood] == 0:
            # Use AI for better mood detection
            prompt = f"Detect mood from: '{message}'. Return one: happy/sad/stressed/bored/angry/romantic/tired"
            response = self.gemini_model.generate_content(prompt)
            mood_text = response.text.strip().lower()
            
            for mood in MoodType:
                if mood.value in mood_text:
                    return mood
            
            return context.mood  # Default to previous mood
        
        return detected_mood
    
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
            }
        }
        
        mode = personality_modes.get(mood, personality_modes[MoodType.HAPPY])
        
        # Adjust for time
        if time_of_day == 'night':
            mode['energy'] = 'chill'
            mode['response_style'] += '_intimate'
        elif time_of_day == 'morning':
            mode['energy'] = 'fresh' if mode['energy'] != 'gentle' else 'gentle'
        
        return mode
    
    async def generate_response(self, 
                                message: str, 
                                context: UserContext) -> Tuple[str, str, Dict]:
        """Generate Niyati's response with text and voice"""
        
        # Detect mood
        mood = await self.detect_mood(message, context)
        
        # Get current time greeting
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
        
        # Build conversation prompt
        prompt = self._build_prompt(message, context, mood, personality_mode, time_period)
        
        # Generate response using Gemini
        response = self.gemini_model.generate_content(prompt)
        text_response = response.text
        
        # Add natural elements
        text_response = self._add_natural_elements(text_response, context.language_preference)
        
        # Generate voice
        voice_audio = await self._generate_voice(text_response, mood)
        
        # Update conversation history
        await self._update_memory(context, message, text_response, mood)
        
        return text_response, voice_audio, {'mood': mood.value, 'personality_mode': personality_mode}
    
    def _build_prompt(self, 
                      message: str, 
                      context: UserContext, 
                      mood: MoodType,
                      personality_mode: Dict,
                      time_period: str) -> str:
        """Build the prompt for Gemini"""
        
        # Get recent conversation context
        recent_history = context.conversation_history[-5:] if context.conversation_history else []
        history_text = "\n".join([f"{h['role']}: {h['message']}" for h in recent_history])
        
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
        - Recent topics: {', '.join(context.last_topics[:3]) if context.last_topics else 'none'}
        
        RECENT CONVERSATION:
        {history_text}
        
        USER MESSAGE: {message}
        
        RESPONSE RULES:
        1. Be a real college friend, not an AI
        2. Use {context.language_preference} naturally
        3. Mix Hindi/English if Hinglish preferred
        4. Add expressions like "yaar", "aree", "uff" naturally
        5. Reference shared college experiences
        6. Use 1-2 emojis naturally (not too many)
        7. Be {personality_mode['response_style']}
        8. Show you remember past conversations
        9. Match the user's energy and mood
        10. Keep it casual and friend-like
        
        Generate a natural, friendly response as Niyati:
        """
        
        return prompt
    
    def _add_natural_elements(self, response: str, language: str) -> str:
        """Add natural speaking elements to response"""
        
        # Add random fillers
        fillers = self.fillers.get(language, self.fillers['hinglish'])
        
        # Randomly insert fillers
        words = response.split()
        if len(words) > 10 and random.random() > 0.5:
            insert_pos = random.randint(3, len(words)-3)
            filler = random.choice(fillers)
            words.insert(insert_pos, filler)
            response = ' '.join(words)
        
        # Add thinking pauses
        if '?' in response and random.random() > 0.6:
            response = response.replace('?', '? 🤔', 1)
        
        # Add dramatic pauses with "..."
        if random.random() > 0.7:
            sentences = response.split('.')
            if len(sentences) > 2:
                sentences[1] += '..'
                response = '.'.join(sentences)
        
        return response
    
    async def _generate_voice(self, text: str, mood: MoodType) -> bytes:
        """Generate voice using ElevenLabs"""
        
        # Set voice parameters based on mood
        voice_settings = {
            MoodType.HAPPY: {"stability": 0.5, "similarity_boost": 0.75, "pitch": 1.1},
            MoodType.SAD: {"stability": 0.8, "similarity_boost": 0.75, "pitch": 0.9},
            MoodType.EXCITED: {"stability": 0.3, "similarity_boost": 0.75, "pitch": 1.2},
            MoodType.STRESSED: {"stability": 0.9, "similarity_boost": 0.75, "pitch": 1.0}
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
    
    async def _update_memory(self, 
                            context: UserContext, 
                            user_message: str,
                            bot_response: str,
                            mood: MoodType):
        """Update conversation memory in Supabase"""
        
        try:
            # Store in conversation history
            self.supabase.table('conversation_history').insert({
                'user_id': context.user_id,
                'user_message': user_message,
                'niyati_response': bot_response,
                'detected_mood': mood.value,
                'timestamp': datetime.now().isoformat()
            }).execute()
            
            # Update user mood
            self.supabase.table('users').update({
                'last_mood': mood.value,
                'last_active': datetime.now().isoformat()
            }).eq('user_id', context.user_id).execute()
            
        except Exception as e:
            print(f"Memory update error: {e}")

import nltk
from textblob import TextBlob
import numpy as np
from typing import Dict, List
import re

class MoodEngine:
    """Advanced mood detection and emotional intelligence"""
    
    def __init__(self):
        # Download required NLTK data
        nltk.download('vader_lexicon', quiet=True)
        from nltk.sentiment import SentimentIntensityAnalyzer
        self.sia = SentimentIntensityAnalyzer()
        
        # Mood patterns in different languages
        self.mood_patterns = {
            'stressed': {
                'keywords': ['exam', 'test', 'deadline', 'assignment', 'project', 
                           'tension', 'pressure', 'worried', 'anxiety'],
                'hindi': ['pareshan', 'chinta', 'tension', 'darr'],
                'emojis': ['😰', '😓', '😫', '💀', '😵'],
                'phrases': ['killing me', 'so much work', 'cant handle']
            },
            'happy': {
                'keywords': ['happy', 'excited', 'amazing', 'awesome', 'great', 'yay'],
                'hindi': ['khushi', 'maza', 'badhiya', 'accha'],
                'emojis': ['😊', '😄', '🎉', '✨', '💖', '🥰'],
                'phrases': ['so happy', 'best day', 'love this']
            },
            'romantic': {
                'keywords': ['crush', 'love', 'date', 'cute', 'heart', 'miss'],
                'hindi': ['pyaar', 'ishq', 'mohabbat', 'dil'],
                'emojis': ['❤️', '💕', '😍', '🥰', '💑'],
                'phrases': ['in love', 'my crush', 'asked out']
            },
            'sad': {
                'keywords': ['sad', 'depressed', 'crying', 'hurt', 'lonely', 'broken'],
                'hindi': ['dukh', 'rona', 'udaas', 'tanha'],
                'emojis': ['😢', '😔', '💔', '😭'],
                'phrases': ['feeling down', 'not okay', 'want to cry']
            }
        }
        
    def analyze_mood(self, text: str, conversation_history: List[str] = None) -> Dict:
        """Comprehensive mood analysis"""
        
        # Basic sentiment analysis
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        
        # VADER sentiment
        vader_scores = self.sia.polarity_scores(text)
        
        # Pattern matching
        detected_moods = self._pattern_matching(text)
        
        # Context from history
        if conversation_history:
            historical_mood = self._analyze_conversation_trend(conversation_history)
        else:
            historical_mood = None
        
        # Combine all signals
        mood_result = self._combine_mood_signals(
            polarity, vader_scores, detected_moods, historical_mood
        )
        
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
    
    def _analyze_conversation_trend(self, history: List[str]) -> str:
        """Analyze mood trend from conversation history"""
        
        if not history:
            return 'neutral'
        
        # Analyze last 5 messages
        recent = history[-5:] if len(history) >= 5 else history
        
        sentiments = []
        for msg in recent:
            blob = TextBlob(msg)
            sentiments.append(blob.sentiment.polarity)
        
        avg_sentiment = np.mean(sentiments)
        
        if avg_sentiment > 0.3:
            return 'positive_trend'
        elif avg_sentiment < -0.3:
            return 'negative_trend'
        else:
            return 'neutral_trend'
    
    def _combine_mood_signals(self, polarity, vader, pattern_moods, historical) -> Dict:
        """Combine all mood signals into final mood assessment"""
        
        # Determine primary mood
        if pattern_moods:
            primary_mood = max(pattern_moods, key=pattern_moods.get)
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
            'pattern_scores': pattern_moods,
            'historical_trend': historical
        }

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from collections import defaultdict

class MemorySystem:
    """Niyati's memory and context management system"""
    
    def __init__(self, supabase_client):
        self.db = supabase_client
        self.short_term_memory = {}  # Current session
        self.working_memory = defaultdict(list)  # Recent interactions
        self.long_term_patterns = {}  # User patterns
        
    async def remember_user(self, user_id: str) -> Dict:
        """Retrieve all memories about a user"""
        
        # Get user profile
        user_data = self.db.table('users').select("*").eq('user_id', user_id).single().execute()
        
        # Get recent conversations
        recent_convos = self.db.table('conversation_history')\
            .select("*")\
            .eq('user_id', user_id)\
            .order('timestamp', desc=True)\
            .limit(50)\
            .execute()
        
        # Get user preferences
        preferences = self.db.table('user_preferences')\
            .select("*")\
            .eq('user_id', user_id)\
            .execute()
        
        # Get memorable moments
        memories = self.db.table('special_memories')\
            .select("*")\
            .eq('user_id', user_id)\
            .execute()
        
        return {
            'profile': user_data.data,
            'recent_conversations': recent_convos.data,
            'preferences': self._process_preferences(preferences.data),
            'special_memories': memories.data,
            'patterns': await self._analyze_patterns(user_id)
        }
    
    async def create_memory(self, user_id: str, memory_type: str, content: Dict):
        """Create a new memory"""
        
        memory_data = {
            'user_id': user_id,
            'type': memory_type,
            'content': json.dumps(content),
            'timestamp': datetime.now().isoformat(),
            'importance': self._calculate_importance(memory_type, content)
        }
        
        if memory_type == 'special':
            # Store special moments
            self.db.table('special_memories').insert(memory_data).execute()
        elif memory_type == 'preference':
            # Update preferences
            self._update_preference(user_id, content)
        elif memory_type == 'pattern':
            # Store behavioral pattern
            self._store_pattern(user_id, content)
        
        # Update working memory
        self.working_memory[user_id].append({
            'type': memory_type,
            'content': content,
            'time': datetime.now()
        })
        
        # Cleanup old working memory
        self._cleanup_working_memory(user_id)
    
    def _calculate_importance(self, memory_type: str, content: Dict) -> int:
        """Calculate memory importance score (1-10)"""
        
        importance_factors = {
            'special': 8,  # Special moments are important
            'emotional': 7,  # Emotional conversations
            'preference': 5,  # User preferences
            'routine': 3,  # Regular patterns
            'casual': 2  # Casual chat
        }
        
        base_importance = importance_factors.get(memory_type, 3)
        
        # Adjust based on content
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
        
        # Get conversation data from last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        conversations = self.db.table('conversation_history')\
            .select("*")\
            .eq('user_id', user_id)\
            .gte('timestamp', thirty_days_ago)\
            .execute()
        
        if not conversations.data:
            return {}
        
        patterns = {
            'chat_times': self._analyze_chat_times(conversations.data),
            'mood_patterns': self._analyze_mood_patterns(conversations.data),
            'topic_interests': self._analyze_topics(conversations.data),
            'response_preferences': self._analyze_response_style(conversations.data)
        }
        
        return patterns
    
    def _analyze_chat_times(self, conversations: List) -> Dict:
        """Analyze when user typically chats"""
        
        time_slots = defaultdict(int)
        
        for conv in conversations:
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
        
        return dict(time_slots)
    
    def _analyze_mood_patterns(self, conversations: List) -> Dict:
        """Analyze mood patterns over time"""
        
        mood_frequency = defaultdict(int)
        mood_transitions = defaultdict(lambda: defaultdict(int))
        
        prev_mood = None
        for conv in conversations:
            mood = conv.get('detected_mood')
            if mood:
                mood_frequency[mood] += 1
                
                if prev_mood:
                    mood_transitions[prev_mood][mood] += 1
                prev_mood = mood
        
        return {
            'frequency': dict(mood_frequency),
            'transitions': {k: dict(v) for k, v in mood_transitions.items()}
        }
    
    def _cleanup_working_memory(self, user_id: str):
        """Remove old items from working memory"""
        
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        self.working_memory[user_id] = [
            mem for mem in self.working_memory[user_id]
            if mem['time'] > cutoff_time
        ]

from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
import asyncio
import json
import uuid

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
niyati = NiyatiBrain()
mood_engine = MoodEngine()
memory_system = MemorySystem(niyati.supabase)

class ChatMessage(BaseModel):
    user_id: str
    message: str
    user_name: Optional[str] = None
    language_preference: Optional[str] = "hinglish"

class ChatResponse(BaseModel):
    text: str
    voice_url: Optional[str]
    mood: str
    typing_time: float
    suggestions: Optional[List[str]]

@app.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat"""
    
    await websocket.accept()
    user_id = str(uuid.uuid4())
    
    # Send welcome message
    await websocket.send_json({
        "type": "system",
        "message": "Niyati connected! 💖"
    })
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            # Show typing indicator
            await websocket.send_json({
                "type": "typing",
                "status": "typing"
            })
            
            # Simulate typing delay
            await asyncio.sleep(random.uniform(1.0, 3.0))
            
            # Get user context
            context = await memory_system.remember_user(data.get('user_id', user_id))
            user_context = UserContext(
                user_id=data.get('user_id', user_id),
                name=data.get('name', 'friend'),
                mood=MoodType.HAPPY,
                language_preference=data.get('language', 'hinglish'),
                last_topics=[],
                relationship_level=5,
                conversation_history=context.get('recent_conversations', []),
                preferences=context.get('preferences', {}),
                memory_tags={}
            )
            
            # Generate response
            text_response, voice_audio, metadata = await niyati.generate_response(
                data['message'],
                user_context
            )
            
            # Send response
            await websocket.send_json({
                "type": "message",
                "text": text_response,
                "mood": metadata['mood'],
                "voice_available": voice_audio is not None,
                "timestamp": datetime.now().isoformat()
            })
            
            # Send voice if available
            if voice_audio:
                await websocket.send_bytes(voice_audio)
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

@app.post("/chat/message")
async def send_message(message: ChatMessage) -> ChatResponse:
    """REST endpoint for sending messages"""
    
    # Get user context
    context = await memory_system.remember_user(message.user_id)
    
    user_context = UserContext(
        user_id=message.user_id,
        name=message.user_name or "friend",
        mood=MoodType.HAPPY,
        language_preference=message.language_preference,
        last_topics=[],
        relationship_level=5,
        conversation_history=context.get('recent_conversations', []),
        preferences=context.get('preferences', {}),
        memory_tags={}
    )
    
    # Generate response
    text_response, voice_audio, metadata = await niyati.generate_response(
        message.message,
        user_context
    )
    
    # Generate suggestions for next messages
    suggestions = await generate_suggestions(metadata['mood'])
    
    return ChatResponse(
        text=text_response,
        voice_url=None,  # Would need to upload to storage
        mood=metadata['mood'],
        typing_time=random.uniform(1.0, 3.0),
        suggestions=suggestions
    )

async def generate_suggestions(mood: str) -> List[str]:
    """Generate contextual suggestions for quick replies"""
    
    suggestions_map = {
        'happy': [
            "Tell me more! 😄",
            "That's amazing! 🎉",
            "Haha same! 😂"
        ],
        'sad': [
            "Want to talk about it? 🫂",
            "I'm here for you 💖",
            "Let's do something fun?"
        ],
        'stressed': [
            "Take a break na 🧘‍♀️",
            "You got this! 💪",
            "Want some tips?"
        ],
        'bored': [
            "Let's play something! 🎮",
            "Wanna hear gossip? 👀",
            "Movie recommendations?"
        ]
    }
    
    return suggestions_map.get(mood, ["Tell me more!", "Interesting! 🤔", "And then?"])

@app.get("/user/{user_id}/memories")
async def get_user_memories(user_id: str) -> Dict:
    """Get user's memories and context"""
    
    memories = await memory_system.remember_user(user_id)
    return memories

@app.post("/user/{user_id}/preference")
async def update_preference(user_id: str, preference: Dict):
    """Update user preference"""
    
    await memory_system.create_memory(
        user_id,
        'preference',
        preference
    )
    return {"status": "preference updated"}

-- Supabase Schema for Niyati Bot

-- Users table
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100),
    full_name VARCHAR(200),
    preferred_language VARCHAR(20) DEFAULT 'hinglish',
    relationship_level INTEGER DEFAULT 1,
    last_mood VARCHAR(50),
    last_active TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Conversation history
CREATE TABLE conversation_history (
    message_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    user_message TEXT,
    niyati_response TEXT,
    detected_mood VARCHAR(50),
    topics TEXT[],
    emotion_intensity INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User preferences
CREATE TABLE user_preferences (
    preference_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    preference_type VARCHAR(50),
    preference_key VARCHAR(100),
    preference_value TEXT,
    weight FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Special memories (important moments)
CREATE TABLE special_memories (
    memory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    type VARCHAR(50),
    content JSONB,
    importance INTEGER DEFAULT 5,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Behavioral patterns
CREATE TABLE user_patterns (
    pattern_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    pattern_type VARCHAR(50),
    pattern_data JSONB,
    confidence FLOAT,
    last_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Inside jokes and references
CREATE TABLE inside_jokes (
    joke_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    joke_key VARCHAR(100),
    joke_content TEXT,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_conversation_user ON conversation_history(user_id);
CREATE INDEX idx_conversation_timestamp ON conversation_history(timestamp);
CREATE INDEX idx_preferences_user ON user_preferences(user_id);
CREATE INDEX idx_memories_user ON special_memories(user_id);

# docker-compose.yml
version: '3.8'

services:
  niyati-backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_KEY=${SUPABASE_KEY}
    volumes:
      - ./backend:/app
    command: uvicorn src.api.chat_endpoints:app --host 0.0.0.0 --port 8000 --reload
    depends_on:
      - redis

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./frontend:/usr/share/nginx/html
    depends_on:
      - niyati-backend
