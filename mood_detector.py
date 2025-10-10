import re
from typing import List, Dict

class MoodDetector:
    def __init__(self):
        self.mood_keywords = {
            "happy": [
                "happy", "yay", "awesome", "great", "amazing", "love", "excited",
                "khushi", "maza", "badhiya", "sahi", "perfect", "best", "😊", "😄", "🎉"
            ],
            "sad": [
                "sad", "upset", "cry", "depress", "lonely", "miss", "hurt", "pain",
                "dukh", "rona", "udas", "alone", "broken", "😢", "😔", "💔"
            ],
            "angry": [
                "angry", "mad", "furious", "pissed", "annoying", "hate", "frustrated",
                "gussa", "naraz", "irritate", "bekaar", "😠", "😤", "🤬"
            ],
            "stressed": [
                "stress", "anxious", "worried", "tense", "pressure", "exam", "deadline",
                "tension", "pareshan", "chinta", "nervous", "scared", "😰", "😩"
            ],
            "excited": [
                "excited", "can't wait", "omg", "finally", "yesss", "party", "celebration",
                "josh", "excitement", "energy", "🎊", "🤩", "✨"
            ],
            "bored": [
                "bored", "boring", "nothing", "meh", "whatever", "timepass", "lazy",
                "bore", "aalas", "kuch nahi", "😴", "😑", "🥱"
            ]
        }
        
        self.mood_phrases = {
            "happy": ["feeling good", "in a good mood", "having fun", "living my best life"],
            "sad": ["feeling down", "not okay", "having a bad day", "feeling low"],
            "stressed": ["freaking out", "losing my mind", "can't handle", "too much"],
            "excited": ["so pumped", "can't contain", "super excited", "over the moon"]
        }
    
    def analyze_mood(self, text: str) -> str:
        """Analyze the mood of the text"""
        text_lower = text.lower()
        
        mood_scores = {mood: 0 for mood in self.mood_keywords.keys()}
        
        # Check for keywords
        for mood, keywords in self.mood_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    mood_scores[mood] += 1
        
        # Check for phrases
        for mood, phrases in self.mood_phrases.items():
            for phrase in phrases:
                if phrase in text_lower:
                    mood_scores[mood] += 2  # Phrases are stronger indicators
        
        # Analyze emoji intensity
        emoji_count = len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿☀-⛿✀-➿]', text))
        if emoji_count > 2:
            mood_scores["excited"] += 1
        
        # Check for exclamation marks
        exclamation_count = text.count('!')
        if exclamation_count > 2:
            if "happy" in max(mood_scores, key=mood_scores.get):
                mood_scores["excited"] += 2
            else:
                mood_scores["stressed"] += 1
        
        # Get the mood with highest score
        detected_mood = max(mood_scores, key=mood_scores.get)
        
        # Default to neutral if no clear mood
        if mood_scores[detected_mood] == 0:
            return "neutral"
        
        return detected_mood
    
    def get_mood_intensity(self, text: str, mood: str) -> float:
        """Get the intensity of the detected mood (0.0 to 1.0)"""
        indicators = {
            "low": 0.3,
            "medium": 0.6,
            "high": 0.9
        }
        
        # Count intensity indicators
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        exclamation_ratio = text.count('!') / max(len(text.split()), 1)
        emoji_count = len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿☀-⛿✀-➿]', text))
        
        intensity_score = (caps_ratio * 2) + (exclamation_ratio * 3) + (emoji_count * 0.1)
        
        if intensity_score < 0.3:
            return indicators["low"]
        elif intensity_score < 0.7:
            return indicators["medium"]
        else:
            return indicators["high"]
