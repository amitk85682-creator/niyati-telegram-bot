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
