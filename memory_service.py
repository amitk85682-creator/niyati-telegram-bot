from supabase import create_client, Client
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json
from config import Config

class MemoryService:
    def __init__(self):
        self.supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    
    async def create_user(self, user_id: str, username: str, name: str) -> Dict:
        """Create a new user profile"""
        user_data = {
            "user_id": user_id,
            "username": username,
            "name": name,
            "preferred_language": "hinglish",
            "created_at": datetime.now().isoformat()
        }
        
        result = self.supabase.table("users").insert(user_data).execute()
        return result.data if result.data else user_data
    
    async def load_user_profile(self, user_id: str) -> Dict:
        """Load user profile from database"""
        result = self.supabase.table("users").select("*").eq("user_id", user_id).execute()
        
        if result.data:
            return result.data
        else:
            # Create default profile if not exists
            return await self.create_user(user_id, f"user_{user_id[:8]}", "Friend")
    
    async def save_message(self, user_id: str, user_message: str, bot_response: str, 
                          mood: str, language: str) -> None:
        """Save conversation message to database"""
        message_data = {
            "user_id": user_id,
            "user_message": user_message,
            "bot_response": bot_response,
            "detected_mood": mood,
            "language": language,
            "timestamp": datetime.now().isoformat()
        }
        
        self.supabase.table("conversations").insert(message_data).execute()
    
    async def get_recent_conversations(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get recent conversation history"""
        result = self.supabase.table("conversations")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("timestamp", desc=True)\
            .limit(limit)\
            .execute()
        
        return result.data if result.data else []
    
    async def search_relevant_memories(self, user_id: str, query: str) -> List[Dict]:
        """Search for relevant memories based on current conversation"""
        # Get conversations with similar topics/keywords
        result = self.supabase.table("conversations")\
            .select("*")\
            .eq("user_id", user_id)\
            .text_search("user_message", query, type="websearch")\
            .limit(5)\
            .execute()
        
        memories = []
        if result.data:
            for conv in result.data:
                memories.append({
                    "content": conv["user_message"],
                    "response": conv["bot_response"],
                    "mood": conv["detected_mood"],
                    "timestamp": conv["timestamp"]
                })
        
        return memories
    
    async def get_user_preferences(self, user_id: str) -> Dict:
        """Get user preferences"""
        result = self.supabase.table("user_preferences")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        preferences = {}
        if result.data:
            for pref in result.data:
                preferences[pref["preference_type"]] = pref["preference_value"]
        
        return preferences
    
    async def update_user_preference(self, user_id: str, preference_type: str, 
                                    preference_value: Any) -> None:
        """Update user preference"""
        data = {
            "user_id": user_id,
            "preference_type": preference_type,
            "preference_value": json.dumps(preference_value) if isinstance(preference_value, (dict, list)) else str(preference_value),
            "updated_at": datetime.now().isoformat()
        }
        
        # Upsert the preference
        self.supabase.table("user_preferences").upsert(data).execute()
    
    async def get_conversation_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get full conversation history"""
        result = self.supabase.table("conversations")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("timestamp", desc=False)\
            .limit(limit)\
            .execute()
        
        return result.data if result.data else []
    
    async def save_session_end(self, user_id: str) -> None:
        """Save session end timestamp"""
        data = {
            "user_id": user_id,
            "event_type": "session_end",
            "timestamp": datetime.now().isoformat()
        }
        
        self.supabase.table("user_events").insert(data).execute()
    
    async def get_user_patterns(self, user_id: str) -> Dict:
        """Analyze user conversation patterns"""
        # Get last 30 days of conversations
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        result = self.supabase.table("conversations")\
            .select("detected_mood, timestamp")\
            .eq("user_id", user_id)\
            .gte("timestamp", thirty_days_ago)\
            .execute()
        
        patterns = {
            "common_moods": {},
            "active_times": {},
            "conversation_frequency": 0
        }
        
        if result.data:
            for conv in result.data:
                # Track moods
                mood = conv["detected_mood"]
                patterns["common_moods"][mood] = patterns["common_moods"].get(mood, 0) + 1
                
                # Track active times
                hour = datetime.fromisoformat(conv["timestamp"]).hour
                patterns["active_times"][hour] = patterns["active_times"].get(hour, 0) + 1
            
            patterns["conversation_frequency"] = len(result.data)
        
        return patterns
