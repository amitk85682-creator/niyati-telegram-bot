from supabase import create_client, Client
from config import Config
from typing import Optional
import asyncio

class Database:
    def __init__(self):
        self.supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    
    async def initialize_tables(self):
        """Initialize database tables if they don't exist"""
        # This would typically be done through Supabase dashboard
        # or migration scripts, but here's the structure
        
        tables_sql = """
        -- Users table
        CREATE TABLE IF NOT EXISTS users (
            user_id UUID PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            preferred_language VARCHAR(50) DEFAULT 'hinglish',
            mood_preference VARCHAR(50) DEFAULT 'balanced',
            created_at TIMESTAMP DEFAULT NOW(),
            last_active TIMESTAMP DEFAULT NOW()
        );
        
        -- Conversations table
        CREATE TABLE IF NOT EXISTS conversations (
            message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(user_id),
            user_message TEXT NOT NULL,
            bot_response TEXT NOT NULL,
            detected_mood VARCHAR(50),
            language VARCHAR(50),
            topics TEXT[],
            timestamp TIMESTAMP DEFAULT NOW()
        );
        
        -- User preferences table
        CREATE TABLE IF NOT EXISTS user_preferences (
            preference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(user_id),
            preference_type VARCHAR(100),
            preference_value TEXT,
            weight FLOAT DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT NOW()
        );
        
        -- User events table
        CREATE TABLE IF NOT EXISTS user_events (
            event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(user_id),
            event_type VARCHAR(50),
            event_data JSONB,
            timestamp TIMESTAMP DEFAULT NOW()
        );
        
        -- Create indexes for better performance
        CREATE INDEX idx_conversations_user_id ON conversations(user_id);
        CREATE INDEX idx_conversations_timestamp ON conversations(timestamp);
        CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);
        CREATE INDEX idx_user_events_user_id ON user_events(user_id);
        """
        
        # Note: Execute these through Supabase SQL editor
        print("Database tables structure defined")
