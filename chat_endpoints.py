# chat_endpoints.py

from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Optional, Dict
import os

# --- Import Telegram Core Classes ---
import telegram
from telegram.ext import Application, ApplicationBuilder

# --- Import Your Bot's Brain ---
from niyati_brain import NiyatiBrain, UserContext, MoodType
from mood_engine import MoodEngine
from memory_system import MemorySystem

# --- Basic Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL') 

app = FastAPI(title="Niyati Bot API")

# Initialize bot components
niyati = NiyatiBrain()
mood_engine = MoodEngine()
memory_system = MemorySystem(niyati.supabase)

# Define Telegram Update Model
class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[Dict] = None
    edited_message: Optional[Dict] = None

# --- Webhook Endpoint for Telegram ---
@app.post("/webhook")
async def telegram_webhook(update: TelegramUpdate, request: Request):
    """This endpoint receives updates from Telegram."""
    bot: telegram.Bot = request.app.state.bot

    if update.message:
        user_id = str(update.message['from']['id'])
        user_name = update.message['from'].get('first_name', 'friend')
        text = update.message.get('text', '')

        if not text:
            return {"status": "ok, no text"}

        context_data = await memory_system.remember_user(user_id)
        user_context = UserContext(
            user_id=user_id,
            name=user_name,
            mood=MoodType.HAPPY,
            language_preference="hinglish",
            last_topics=[],
            relationship_level=5,
            conversation_history=context_data.get('recent_conversations', []),
            preferences=context_data.get('preferences', {}),
            memory_tags={}
        )

        text_response, voice_audio, metadata = await niyati.generate_response(
            text,
            user_context
        )
        
        await bot.send_message(chat_id=update.message['chat']['id'], text=text_response)

    return {"status": "ok"}

# --- Lifespan events to set and remove webhook ---
@app.on_event("startup")
async def startup_event():
    """On startup, initialize the bot and set the webhook."""
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.state.bot = application.bot
    
    # Set the webhook
    webhook_full_url = f"{WEBHOOK_URL}/webhook"
    await app.state.bot.set_webhook(url=webhook_full_url)
    print(f"Webhook set to {webhook_full_url}")

@app.on_event("shutdown")
async def shutdown_event():
    """On shutdown, remove the webhook."""
    print("Removing webhook...")
    await app.state.bot.delete_webhook()

@app.get("/")
async def root():
    return {"message": "Niyati Bot is running. Webhook is active."}
