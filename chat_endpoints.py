# Add these imports to the top of your chat_endpoints.py file

from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict # Make sure List is imported
import asyncio
import json
import uuid
import random # Add this import
from datetime import datetime # Add this import

# Import classes from your other files
from niyati_brain import NiyatiBrain, UserContext, MoodType
from mood_engine import MoodEngine
from memory_system import MemorySystem

# Your existing code starts here...
app = FastAPI(title="Niyati Bot API")
# ...the rest of your file
from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
import asyncio
import json
import uuid

app = FastAPI(title="Niyati Bot API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize bot
niyati = NiyatiBrain()
mood_engine = MoodEngine()
memory_system = MemorySystem(niyati.supabase)

class ChatMessage(BaseModel):
    user_id: str
    message: str
    user_name: Optional[str] = None
    language_preference: Optional[str] = "hinglish"

class ChatResponse(BaseModel):
    text: str
    voice_url: Optional[str]
    mood: str
    typing_time: float
    suggestions: Optional[List[str]]

@app.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat"""
    
    await websocket.accept()
    user_id = str(uuid.uuid4())
    
    # Send welcome message
    await websocket.send_json({
        "type": "system",
        "message": "Niyati connected! 💖"
    })
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            # Show typing indicator
            await websocket.send_json({
                "type": "typing",
                "status": "typing"
            })
            
            # Simulate typing delay
            await asyncio.sleep(random.uniform(1.0, 3.0))
            
            # Get user context
            context = await memory_system.remember_user(data.get('user_id', user_id))
            user_context = UserContext(
                user_id=data.get('user_id', user_id),
                name=data.get('name', 'friend'),
                mood=MoodType.HAPPY,
                language_preference=data.get('language', 'hinglish'),
                last_topics=[],
                relationship_level=5,
                conversation_history=context.get('recent_conversations', []),
                preferences=context.get('preferences', {}),
                memory_tags={}
            )
            
            # Generate response
            text_response, voice_audio, metadata = await niyati.generate_response(
                data['message'],
                user_context
            )
            
            # Send response
            await websocket.send_json({
                "type": "message",
                "text": text_response,
                "mood": metadata['mood'],
                "voice_available": voice_audio is not None,
                "timestamp": datetime.now().isoformat()
            })
            
            # Send voice if available
            if voice_audio:
                await websocket.send_bytes(voice_audio)
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

@app.post("/chat/message")
async def send_message(message: ChatMessage) -> ChatResponse:
    """REST endpoint for sending messages"""
    
    # Get user context
    context = await memory_system.remember_user(message.user_id)
    
    user_context = UserContext(
        user_id=message.user_id,
        name=message.user_name or "friend",
        mood=MoodType.HAPPY,
        language_preference=message.language_preference,
        last_topics=[],
        relationship_level=5,
        conversation_history=context.get('recent_conversations', []),
        preferences=context.get('preferences', {}),
        memory_tags={}
    )
    
    # Generate response
    text_response, voice_audio, metadata = await niyati.generate_response(
        message.message,
        user_context
    )
    
    # Generate suggestions for next messages
    suggestions = await generate_suggestions(metadata['mood'])
    
    return ChatResponse(
        text=text_response,
        voice_url=None,  # Would need to upload to storage
        mood=metadata['mood'],
        typing_time=random.uniform(1.0, 3.0),
        suggestions=suggestions
    )

async def generate_suggestions(mood: str) -> List[str]:
    """Generate contextual suggestions for quick replies"""
    
    suggestions_map = {
        'happy': [
            "Tell me more! 😄",
            "That's amazing! 🎉",
            "Haha same! 😂"
        ],
        'sad': [
            "Want to talk about it? 🫂",
            "I'm here for you 💖",
            "Let's do something fun?"
        ],
        'stressed': [
            "Take a break na 🧘‍♀️",
            "You got this! 💪",
            "Want some tips?"
        ],
        'bored': [
            "Let's play something! 🎮",
            "Wanna hear gossip? 👀",
            "Movie recommendations?"
        ]
    }
    
    return suggestions_map.get(mood, ["Tell me more!", "Interesting! 🤔", "And then?"])

@app.get("/user/{user_id}/memories")
async def get_user_memories(user_id: str) -> Dict:
    """Get user's memories and context"""
    
    memories = await memory_system.remember_user(user_id)
    return memories

@app.post("/user/{user_id}/preference")
async def update_preference(user_id: str, preference: Dict):
    """Update user preference"""
    
    await memory_system.create_memory(
        user_id,
        'preference',
        preference
    )
    return {"status": "preference updated"}
