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
