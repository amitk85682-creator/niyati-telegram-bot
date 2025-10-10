import aiohttp
import asyncio
from config import Config
import base64
import os
from datetime import datetime
import hashlib

class ElevenLabsService:
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1"
        self.audio_cache = {}  # Simple in-memory cache
        
    async def generate_voice(self, text: str, mood: str = "neutral") -> str:
        """Generate voice audio from text using ElevenLabs"""
        
        # Create cache key
        cache_key = hashlib.md5(f"{text}{mood}".encode()).hexdigest()
        
        # Check cache first
        if cache_key in self.audio_cache:
            return self.audio_cache[cache_key]
        
        try:
            # Adjust voice settings based on mood
            voice_settings = self.get_voice_settings(mood)
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/text-to-speech/{self.voice_id}"
                
                headers = {
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json"
                }
                
                data = {
                    "text": text,
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": voice_settings
                }
                
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_content = await response.read()
                        
                        # Save audio file
                        filename = f"audio_{cache_key}.mp3"
                        filepath = f"static/audio/{filename}"
                        
                        # Ensure directory exists
                        os.makedirs("static/audio", exist_ok=True)
                        
                        with open(filepath, "wb") as f:
                            f.write(audio_content)
                        
                        audio_url = f"/static/audio/{filename}"
                        
                        # Cache the URL
                        self.audio_cache[cache_key] = audio_url
                        
                        return audio_url
                    else:
                        print(f"ElevenLabs API Error: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"Voice generation error: {e}")
            return None
    
    def get_voice_settings(self, mood: str) -> dict:
        """Get voice settings based on mood"""
        
        # Base settings for Niyati's voice
        base_settings = {
            "stability": 0.7,
            "similarity_boost": 0.8,
            "style": 0.5,
            "use_speaker_boost": True
        }
        
        # Mood-based adjustments
        mood_settings = {
            "happy": {
                "stability": 0.6,
                "similarity_boost": 0.85,
                "style": 0.7,  # More expressive
            },
            "sad": {
                "stability": 0.8,
                "similarity_boost": 0.75,
                "style": 0.3,  # Softer
            },
            "excited": {
                "stability": 0.5,
                "similarity_boost": 0.9,
                "style": 0.8,  # Very expressive
            },
            "stressed": {
                "stability": 0.75,
                "similarity_boost": 0.7,
                "style": 0.4,
            },
            "supportive": {
                "stability": 0.85,
                "similarity_boost": 0.8,
                "style": 0.45,  # Warm and caring
            }
        }
        
        if mood in mood_settings:
            base_settings.update(mood_settings[mood])
        
        return base_settings
