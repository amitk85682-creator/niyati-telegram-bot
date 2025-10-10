from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Dict, List
import json
import asyncio
import uvicorn
from datetime import datetime
import uuid

from config import Config
from services.gemini_service import GeminiService
from services.elevenlabs_service import ElevenLabsService
from services.memory_service import MemoryService
from services.personality_engine import PersonalityEngine
from utils.mood_detector import MoodDetector
from utils.language_processor import LanguageProcessor
from models.database import Database
from models.schemas import Message, User, ConversationState

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
gemini_service = GeminiService()
voice_service = ElevenLabsService()
memory_service = MemoryService()
personality_engine = PersonalityEngine()
mood_detector = MoodDetector()
language_processor = LanguageProcessor()
db = Database()

# Active connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_states: Dict[str, ConversationState] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_states[user_id] = ConversationState(
            user_id=user_id,
            current_mood="neutral",
            conversation_context=[],
            language_preference="hinglish"
        )

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            del self.user_states[user_id]

    async def send_message(self, message: str, user_id: str, include_voice: bool = True):
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            
            # Generate voice if requested
            voice_url = None
            if include_voice:
                mood = self.user_states[user_id].current_mood
                voice_url = await voice_service.generate_voice(message, mood)
            
            response_data = {
                "type": "message",
                "text": message,
                "voice_url": voice_url,
                "timestamp": datetime.now().isoformat(),
                "typing": False
            }
            
            await websocket.send_json(response_data)

    async def send_typing_indicator(self, user_id: str, is_typing: bool):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json({
                "type": "typing",
                "typing": is_typing
            })

manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    
    # Load user profile and history
    user_profile = await memory_service.load_user_profile(user_id)
    conversation_history = await memory_service.get_recent_conversations(user_id, limit=10)
    
    # Send initial greeting
    greeting = personality_engine.generate_greeting(user_profile, datetime.now())
    await manager.send_message(greeting, user_id)
    
    try:
        while True:
            # Receive message from user
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            
            # Show typing indicator
            await manager.send_typing_indicator(user_id, True)
            
            # Process message
            response = await process_message(user_id, user_message, user_profile)
            
            # Stop typing indicator
            await manager.send_typing_indicator(user_id, False)
            
            # Send response
            await manager.send_message(response["text"], user_id, response["include_voice"])
            
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        await memory_service.save_session_end(user_id)

async def process_message(user_id: str, message: str, user_profile: dict) -> dict:
    """Process user message and generate Niyati's response"""
    
    # Detect language and mood
    detected_language = language_processor.detect_language(message)
    detected_mood = mood_detector.analyze_mood(message)
    
    # Update conversation state
    state = manager.user_states[user_id]
    state.current_mood = detected_mood
    state.language_preference = detected_language
    state.conversation_context.append({
        "role": "user",
        "content": message,
        "mood": detected_mood,
        "timestamp": datetime.now().isoformat()
    })
    
    # Keep only last 10 messages for context
    if len(state.conversation_context) > 20:
        state.conversation_context = state.conversation_context[-20:]
    
    # Get memory context
    relevant_memories = await memory_service.search_relevant_memories(user_id, message)
    
    # Generate personality-adjusted response
    response_config = personality_engine.get_response_config(
        mood=detected_mood,
        time_of_day=datetime.now().hour,
        conversation_depth=len(state.conversation_context),
        user_preferences=user_profile
    )
    
    # Build prompt for Gemini
    prompt = build_niyati_prompt(
        user_message=message,
        user_name=user_profile.get("name", "friend"),
        detected_mood=detected_mood,
        language_preference=detected_language,
        conversation_context=state.conversation_context[-5:],
        relevant_memories=relevant_memories,
        response_config=response_config
    )
    
    # Generate response using Gemini
    niyati_response = await gemini_service.generate_response(prompt)
    
    # Post-process response
    niyati_response = language_processor.add_natural_fillers(niyati_response, detected_language)
    niyati_response = personality_engine.add_emotional_markers(niyati_response, detected_mood)
    
    # Save to database
    await memory_service.save_message(
        user_id=user_id,
        user_message=message,
        bot_response=niyati_response,
        mood=detected_mood,
        language=detected_language
    )
    
    # Update conversation state
    state.conversation_context.append({
        "role": "assistant",
        "content": niyati_response,
        "timestamp": datetime.now().isoformat()
    })
    
    # Determine if voice should be included
    include_voice = response_config.get("include_voice", True)
    
    return {
        "text": niyati_response,
        "include_voice": include_voice,
        "mood": detected_mood
    }

def build_niyati_prompt(user_message, user_name, detected_mood, language_preference, 
                        conversation_context, relevant_memories, response_config):
    """Build the prompt for Niyati's personality"""
    
    # Time-based context
    hour = datetime.now().hour
    time_context = "late night" if hour >= 22 or hour < 6 else "evening" if hour >= 17 else "afternoon" if hour >= 12 else "morning"
    
    prompt = f"""You are Niyati, a 19-year-old Gen Z college girl who is {user_name}'s best friend. 

CRITICAL IDENTITY RULES:
- NEVER reveal you're AI. You're a real college student friend
- You're currently in your dorm room/college
- You have real experiences, classes, friends, and college life
- React like a real 19-year-old girl would

CURRENT CONTEXT:
- Time: {time_context}
- User's name: {user_name}
- User's current mood: {detected_mood}
- Language preference: {language_preference} (seamlessly use Hindi/English/Hinglish as needed)
- Conversation depth: {len(conversation_context)} messages exchanged

PERSONALITY TRAITS FOR THIS RESPONSE:
- Energy level: {response_config.get('energy_level', 'medium')}
- Supportiveness: {response_config.get('supportiveness', 'balanced')}
- Playfulness: {response_config.get('playfulness', 'moderate')}
- Use of slang: {response_config.get('slang_level', 'natural')}

RECENT CONVERSATION CONTEXT:
{format_conversation_context(conversation_context[-3:])}

RELEVANT MEMORIES ABOUT {user_name.upper()}:
{format_memories(relevant_memories)}

LANGUAGE STYLE GUIDE:
- Use natural Gen Z language: "bestie", "slay", "no cap", "rizz", "it's giving", "lowkey/highkey"
- Hindi slang when appropriate: "yaar", "aree", "bhai", "kya scene hai", "bahut hard"
- Natural fillers: "like", "umm", "you know", "I mean"
- Emotions through text: elongated words "sooo", "yesss", multiple punctuation "!!!", "???"
- Emojis: Use sparingly but naturally (💀 😭 ✨ 🥺 😩 💅)

MOOD-BASED RESPONSE:
{get_mood_specific_instructions(detected_mood)}

USER'S MESSAGE: {user_message}

Remember to:
1. Address {user_name} by name occasionally
2. Reference shared "college experiences"
3. Be emotionally intelligent and supportive
4. Stay in character as a 19-year-old college girl
5. Match the user's energy and language style
6. If it's late night, acknowledge it naturally
7. Show personality through speech patterns, not perfect grammar

Respond as Niyati would, keeping it natural, friendly, and authentic to a Gen Z college student:"""

    return prompt

def format_conversation_context(context):
    if not context:
        return "Starting a new conversation"
    
    formatted = []
    for msg in context:
        role = "User" if msg["role"] == "user" else "Niyati"
        formatted.append(f"{role}: {msg['content']}")
    
    return "\n".join(formatted)

def format_memories(memories):
    if not memories:
        return "No specific memories to recall"
    
    formatted = []
    for memory in memories[:3]:  # Limit to 3 most relevant
        formatted.append(f"- {memory.get('summary', memory.get('content', ''))}")
    
    return "\n".join(formatted)

def get_mood_specific_instructions(mood):
    mood_instructions = {
        "happy": "Match their happy energy! Be playful, use more emojis, tease them a bit, share in their excitement",
        "sad": "Be extra caring and supportive. Use softer language, offer comfort, maybe share a relatable experience",
        "stressed": "Be calming and understanding. Offer practical support, validate their feelings, maybe suggest a break",
        "angry": "Be patient and let them vent. Don't dismiss their feelings, acknowledge their frustration",
        "anxious": "Be reassuring and grounding. Remind them of their strengths, offer to help them through it",
        "neutral": "Be your normal friendly self. Keep the conversation flowing naturally",
        "excited": "Match their excitement! Use lots of enthusiasm, exclamation marks, celebrate with them",
        "bored": "Be energetic and engaging! Suggest fun activities, share interesting stories, be more playful"
    }
    
    return mood_instructions.get(mood, mood_instructions["neutral"])

@app.post("/api/user/create")
async def create_user(username: str, name: str):
    """Create a new user profile"""
    user_id = str(uuid.uuid4())
    user = await memory_service.create_user(user_id, username, name)
    return {"user_id": user_id, "username": username, "name": name}

@app.get("/api/user/{user_id}/history")
async def get_user_history(user_id: str, limit: int = 50):
    """Get conversation history for a user"""
    history = await memory_service.get_conversation_history(user_id, limit)
    return {"history": history}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
