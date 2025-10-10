from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class User(BaseModel):
    user_id: str
    username: str
    name: str
    preferred_language: str = "hinglish"
    mood_preference: str = "balanced"
    created_at: datetime
    last_active: Optional[datetime] = None

class Message(BaseModel):
    message_id: Optional[str] = None
    user_id: str
    user_message: str
    bot_response: str
    detected_mood: str
    language: str
    topics: Optional[List[str]] = []
    timestamp: datetime

class ConversationState(BaseModel):
    user_id: str
    current_mood: str
    conversation_context: List[Dict[str, Any]]
    language_preference: str
    typing: bool = False

class UserPreference(BaseModel):
    preference_id: Optional[str] = None
    user_id: str
    preference_type: str
    preference_value: str
    weight: float = 1.0
    updated_at: datetime

class UserEvent(BaseModel):
    event_id: Optional[str] = None
    user_id: str
    event_type: str
    event_data: Optional[Dict[str, Any]] = {}
    timestamp: datetime
