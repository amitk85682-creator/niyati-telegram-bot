-- Supabase Schema for Niyati Bot

-- Users table
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100),
    full_name VARCHAR(200),
    preferred_language VARCHAR(20) DEFAULT 'hinglish',
    relationship_level INTEGER DEFAULT 1,
    last_mood VARCHAR(50),
    last_active TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Conversation history
CREATE TABLE conversation_history (
    message_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    user_message TEXT,
    niyati_response TEXT,
    detected_mood VARCHAR(50),
    topics TEXT[],
    emotion_intensity INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User preferences
CREATE TABLE user_preferences (
    preference_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    preference_type VARCHAR(50),
    preference_key VARCHAR(100),
    preference_value TEXT,
    weight FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Special memories (important moments)
CREATE TABLE special_memories (
    memory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    type VARCHAR(50),
    content JSONB,
    importance INTEGER DEFAULT 5,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Behavioral patterns
CREATE TABLE user_patterns (
    pattern_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    pattern_type VARCHAR(50),
    pattern_data JSONB,
    confidence FLOAT,
    last_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Inside jokes and references
CREATE TABLE inside_jokes (
    joke_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),
    joke_key VARCHAR(100),
    joke_content TEXT,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_conversation_user ON conversation_history(user_id);
CREATE INDEX idx_conversation_timestamp ON conversation_history(timestamp);
CREATE INDEX idx_preferences_user ON user_preferences(user_id);
CREATE INDEX idx_memories_user ON special_memories(user_id);
