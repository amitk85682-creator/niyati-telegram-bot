import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Keys
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    # ElevenLabs Voice ID for Niyati
    VOICE_ID = 'ni6cdqyS9wBvic5LPA7M'
    
    # WebSocket Configuration
    WS_HOST = '0.0.0.0'
    WS_PORT = 8000
    
    # Personality Settings
    BOT_NAME = "Niyati"
    BOT_AGE = 19
    DEFAULT_LANGUAGE = "hinglish"
