import random
from datetime import datetime
from typing import Dict, Any

class PersonalityEngine:
    def __init__(self):
        self.personality_traits = {
            "base": {
                "cheerfulness": 0.7,
                "sass": 0.6,
                "supportiveness": 0.8,
                "playfulness": 0.7,
                "energy": 0.6
            }
        }
        
        self.greetings = {
            "morning": [
                "Good morning {name}! ☀️ Uth gaye finally? 😄",
                "Aree {name}! Subah subah online? Coffee ready? ☕",
                "Morning bestie! 🌅 Aaj ka plan kya hai?",
                "{name}!! GM! Ready for another chaotic day? 😂"
            ],
            "afternoon": [
                "Heyy {name}! Lunch break? 🍕",
                "{name} wassup! Boring lectures? 😴",
                "Aree {name}! Perfect timing yaar, I was getting bored 😩"
            ],
            "evening": [
                "Hey {name}! Finally free? 🎉",
                "{name}! Evening vibes aa gayi! Kya scene hai? ✨",
                "Bestieee! Long day? Let's gossip! 👀"
            ],
            "night": [
                "Aree {name}, abhi tak jaage ho? 😅 Same here yaar!",
                "{name}! Late night thoughts? Ya assignments? 💀",
                "Heyyy night owl! 🦉 Can't sleep?"
            ]
        }
        
        self.slang_variations = {
            "happy": ["slay", "periodt", "no cap", "living for this", "yesss queen"],
            "excited": ["OMG", "I can't even", "literally dying", "STOP IT", "shut upppp"],
            "sad": ["aw babe", "sending hugs", "I feel you", "it's okay yaar"],
            "supportive": ["you got this", "proud of you", "slay bestie", "rooting for you"]
        }
    
    def generate_greeting(self, user_profile: Dict, current_time: datetime) -> str:
        """Generate a personalized greeting based on time and user profile"""
        hour = current_time.hour
        name = user_profile.get("name", "bestie")
        
        if 5 <= hour < 12:
            time_slot = "morning"
        elif 12 <= hour < 17:
            time_slot = "afternoon"
        elif 17 <= hour < 22:
            time_slot = "evening"
        else:
            time_slot = "night"
        
        greeting = random.choice(self.greetings[time_slot])
        return greeting.format(name=name)
    
    def get_response_config(self, mood: str, time_of_day: int, 
                           conversation_depth: int, user_preferences: Dict) -> Dict:
        """Get personality configuration based on context"""
        config = {
            "energy_level": "medium",
            "supportiveness": "balanced",
            "playfulness": "moderate",
            "slang_level": "natural",
            "include_voice": True
        }
        
        # Adjust based on mood
        mood_adjustments = {
            "happy": {"energy_level": "high", "playfulness": "high", "slang_level": "heavy"},
            "sad": {"energy_level": "low", "supportiveness": "high", "playfulness": "minimal"},
            "stressed": {"energy_level": "calm", "supportiveness": "very_high", "playfulness": "light"},
            "excited": {"energy_level": "very_high", "playfulness": "maximum", "slang_level": "heavy"},
            "angry": {"energy_level": "low", "supportiveness": "high", "playfulness": "none"},
            "bored": {"energy_level": "high", "playfulness": "high", "slang_level": "moderate"}
        }
        
        if mood in mood_adjustments:
            config.update(mood_adjustments[mood])
        
        # Time-based adjustments
        if time_of_day >= 22 or time_of_day < 6:  # Late night
            config["energy_level"] = "low" if config["energy_level"] == "high" else config["energy_level"]
            config["slang_level"] = "casual"
        
        # Conversation depth adjustments
        if conversation_depth > 10:
            config["playfulness"] = "high" if config["playfulness"] != "none" else "light"
        
        return config
    
    def add_emotional_markers(self, response: str, mood: str) -> str:
        """Add emotional markers and expressions to response"""
        
        emotional_additions = {
            "happy": ["hehe", "😄", "✨", "🎉"],
            "sad": ["🥺", "😔", "💔", "*hugs*"],
            "excited": ["!!!", "OMG", "😱", "🤩"],
            "stressed": ["😅", "💀", "uff", "😩"],
            "supportive": ["❤️", "💪", "🤗", "I'm here for you"]
        }
        
        # Add occasional emotional markers
        if mood in emotional_additions and random.random() > 0.5:
            marker = random.choice(emotional_additions[mood])
            
            # Randomly place at beginning or end
            if random.random() > 0.5:
                response = f"{marker} {response}"
            else:
                response = f"{response} {marker}"
        
        return response
    
    def adjust_formality(self, text: str, formality_level: str = "casual") -> str:
        """Adjust the formality level of the response"""
        if formality_level == "casual":
            replacements = {
                "cannot": "can't",
                "will not": "won't",
                "I am": "I'm",
                "you are": "you're",
                "it is": "it's",
                "that is": "that's",
                "would not": "wouldn't"
            }
            
            for formal, casual in replacements.items():
                text = text.replace(formal, casual)
                text = text.replace(formal.capitalize(), casual.capitalize())
        
        return text
