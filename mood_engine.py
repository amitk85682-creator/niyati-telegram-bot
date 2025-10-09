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
