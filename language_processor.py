import random
import re
from typing import List, Tuple

class LanguageProcessor:
    def __init__(self):
        self.hindi_keywords = [
            "yaar", "kya", "hai", "nahi", "accha", "theek", "kaise", "kyun",
            "abhi", "aur", "bas", "mat", "kar", "tha", "gaya", "aaya"
        ]
        
        self.english_slang = [
            "like", "literally", "basically", "actually", "honestly",
            "lowkey", "highkey", "no cap", "fr fr", "ngl"
        ]
        
        self.fillers = {
            "english": ["um", "uh", "like", "you know", "I mean", "basically", "actually"],
            "hindi": ["matlab", "wo kya hai", "aree", "achha", "toh"],
            "hinglish": ["like", "matlab", "basically", "yaar", "na"]
        }
        
        self.sentence_starters = {
            "english": ["So", "Okay so", "Wait", "Omg", "Honestly", "Actually"],
            "hindi": ["Aree", "Achha", "Toh", "Dekh", "Sun"],
            "hinglish": ["Okay so", "Aree yaar", "Listen na", "Actually", "Basically"]
        }
    
    def detect_language(self, text: str) -> str:
        """Detect the primary language of the text"""
        text_lower = text.lower()
        
        # Count Hindi words
        hindi_count = sum(1 for word in self.hindi_keywords if word in text_lower.split())
        
        # Check for Devanagari script
        devanagari_pattern = re.compile(r'[\u0900-\u097F]')
        has_devanagari = bool(devanagari_pattern.search(text))
        
        # Determine language
        total_words = len(text_lower.split())
        
        if has_devanagari or hindi_count > total_words * 0.5:
            return "hindi"
        elif hindi_count > 0:
            return "hinglish"
        else:
            return "english"
    
    def add_natural_fillers(self, text: str, language: str = "hinglish") -> str:
        """Add natural fillers and speech patterns"""
        
        sentences = text.split('. ')
        processed_sentences = []
        
        for i, sentence in enumerate(sentences):
            # Randomly add fillers (30% chance)
            if random.random() < 0.3 and len(sentence.split()) > 3:
                filler = random.choice(self.fillers[language])
                
                # Insert filler at a natural position
                words = sentence.split()
                if len(words) > 4:
                    position = random.randint(2, len(words) - 2)
                    words.insert(position, filler)
                    sentence = ' '.join(words)
            
            # Add sentence starters (20% chance)
            if random.random() < 0.2 and i > 0:
                starter = random.choice(self.sentence_starters[language])
                sentence = f"{starter}, {sentence.lower()}"
            
            processed_sentences.append(sentence)
        
        return '. '.join(processed_sentences)
    
    def add_code_switching(self, text: str) -> str:
        """Add natural code-switching between Hindi and English"""
        
        code_switch_phrases = {
            "what": ["kya", "what"],
            "yes": ["haan", "yes"],
            "no": ["nahi", "no"],
            "okay": ["theek hai", "okay"],
            "friend": ["dost", "friend"],
            "good": ["accha", "good"],
            "very": ["bahut", "very"]
        }
        
        for english, options in code_switch_phrases.items():
            if english in text.lower():
                # 40% chance to switch
                if random.random() < 0.4:
                    replacement = random.choice(options)
                    text = re.sub(rf'\b{english}\b', replacement, text, flags=re.IGNORECASE)
        
        return text
    
    def add_elongation(self, text: str, mood: str) -> str:
        """Add elongation for emphasis based on mood"""
        
        if mood in ["excited", "happy", "bored"]:
            elongation_words = {
                "yes": "yesss",
                "no": "nooo",
                "so": "sooo",
                "very": "veryy",
                "please": "pleaseee",
                "what": "whattt",
                "oh": "ohhh"
            }
            
            for word, elongated in elongation_words.items():
                if word in text.lower() and random.random() < 0.3:
                    text = re.sub(rf'\b{word}\b', elongated, text, flags=re.IGNORECASE)
        
        return text
    
    def add_punctuation_emphasis(self, text: str, mood: str) -> str:
        """Add punctuation for emphasis"""
        
        if mood == "excited":
            # Add multiple exclamation marks
            text = re.sub(r'!', '!!!', text)
            text = re.sub(r'\?', '??', text)
        elif mood == "confused":
            text = re.sub(r'\?', '???', text)
        elif mood == "happy":
            if not text.endswith(('!', '?', '.')):
                text += "!"
        
        return text
