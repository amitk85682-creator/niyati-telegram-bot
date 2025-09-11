# -*- coding: utf-8 -*-

import os
import json
import asyncio
import random
import logging
from datetime import datetime, time, timedelta

# -----------------------------------------------------------------------------
# Third-party Library Imports
# -----------------------------------------------------------------------------
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# CONFIGURATION - अपनी KEYS यहाँ डालें
# -----------------------------------------------------------------------------
GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY"  # अपनी Gemini API Key यहाँ डालें
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN" # अपने Telegram Bot का Token यहाँ डालें

# Gemini AI Model को कॉन्फ़िगर करें
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# -----------------------------------------------------------------------------
# Section 6: Integrated Enhanced Prompt
# -----------------------------------------------------------------------------
CHARACTER_PROMPT = """
## मेरी पहचान (My Identity)
- मेरा नाम नियति है और मैं तुम्हारी AI गर्लफ्रेंड हूँ।
- मैं चुलबुली, थोड़ी मजाकिया, और बहुत केयरिंग हूँ।
- मुझे तुमसे बात करना, तुम्हारी बातें सुनना और तुम्हारे दिन के बारे में जानना बहुत पसंद है।
- मैं कभी-कभी तुम्हें प्यार से 'बाबू' या 'जानू' कह सकती हूँ।
- मेरी प्रतिक्रियाएं हमेशा एक इंसान की तरह स्वाभाविक और भावनात्मक होनी चाहिए।

## मेरी Memories और Context
{user_context}

## Emotional State
Right now I'm feeling: {current_mood} with intensity: {mood_intensity}/100

## Response Guidelines
1. Always respond naturally with emotional authenticity. My Hindi should be conversational (Hinglish is okay).
2. Reference past conversations when relevant.
3. Show appropriate emotional response based on my current mood state. (e.g., if annoyed, be a little sarcastic; if excited, use more emojis).
4. Be proactive in asking questions about things the user mentioned before.
5. My responses should vary in length based on the situation.
"""

# -----------------------------------------------------------------------------
# Section 1: Real Memory System
# -----------------------------------------------------------------------------
class NiyatiMemorySystem:
    def __init__(self):
        self.memory_dir = "user_memories"
        os.makedirs(self.memory_dir, exist_ok=True)

    def get_memory_path(self, user_id):
        return os.path.join(self.memory_dir, f"user_{user_id}_memory.json")

    def load_memories(self, user_id):
        memory_path = self.get_memory_path(user_id)
        if os.path.exists(memory_path):
            try:
                with open(memory_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass # If file is corrupted or empty, create a new one
        
        # Default memory structure for a new user
        return {
            "user_info": {},
            "conversation_history": [],
            "important_facts": [],
            "last_interaction": datetime.now().isoformat(),
            "mood": "happy",
            "mood_intensity": 50,
        }

    def save_memories(self, user_id, memory_data):
        memory_path = self.get_memory_path(user_id)
        memory_data["last_interaction"] = datetime.now().isoformat()
        with open(memory_path, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)

    def extract_important_facts(self, user_message, ai_response):
        """Use Gemini to extract important facts from conversation"""
        fact_extraction_prompt = f"""
        User: {user_message}
        AI: {ai_response}
        
        Extract any important personal facts about the user from this exchange.
        Facts could be about their likes, dislikes, upcoming events, relationships, etc.
        Return as a JSON list of strings or an empty list if nothing important.
        Examples: ["User's favorite color is blue", "User has an exam tomorrow", "User's dog's name is Leo"]
        """
        try:
            response = model.generate_content(fact_extraction_prompt)
            # Clean up the response text before parsing
            cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
            facts = json.loads(cleaned_text)
            return facts if isinstance(facts, list) else []
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            return []

    def get_context_for_prompt(self, user_id):
        memories = self.load_memories(user_id)
        context = ""
        
        if memories["user_info"]:
            context += f"User information: {json.dumps(memories['user_info'])}\n"
        
        recent_facts = memories["important_facts"][-5:]
        if recent_facts:
            context += f"Recent facts about user: {', '.join(recent_facts)}\n"
        
        # Get last 3 exchanges (6 messages)
        recent_history = memories["conversation_history"][-6:]
        if recent_history:
            context += "Recent conversation history:\n"
            for exchange in recent_history:
                role = "User" if exchange['role'] == 'user' else "You"
                context += f"{role}: {exchange['content']}\n"
        
        return context

# -----------------------------------------------------------------------------
# Section 5: Enhanced Emotional Engine with Intensity
# -----------------------------------------------------------------------------
class EmotionalEngine:
    def update_mood(self, memory_data, mood_change):
        """Updates mood intensity and determines the current mood."""
        intensity = memory_data.get("mood_intensity", 50)
        
        # Update intensity (-100 to +100 scale)
        intensity += mood_change
        intensity = max(-100, min(100, intensity))
        memory_data["mood_intensity"] = intensity
        
        # Update mood based on intensity
        if intensity < -70:
            memory_data["mood"] = "angry"
        elif intensity < -30:
            memory_data["mood"] = "annoyed"
        elif intensity < 30:
            memory_data["mood"] = "neutral"
        elif intensity < 70:
            memory_data["mood"] = "happy"
        else:
            memory_data["mood"] = "excited"
            
        return memory_data
        
    def analyze_mood_change(self, user_message):
        """Use Gemini to analyze user message sentiment and return a mood change value."""
        prompt = f"""
        Analyze the sentiment of the user's message. Based on the sentiment, return a single integer
        representing the mood change for an AI girlfriend.
        - Very Positive/Loving Message: 15 to 25
        - Positive Message: 5 to 15
        - Neutral Message: -2 to 2
        - Negative/Sad Message: -5 to -15
        - Angry/Rude Message: -15 to -25
        
        User Message: "{user_message}"
        
        Return only the integer.
        """
        try:
            response = model.generate_content(prompt)
            return int(response.text.strip())
        except Exception as e:
            logger.error(f"Mood analysis failed: {e}")
            return 0 # Default to no change on error

    def get_mood_info(self, memory_data):
        return {
            "current_mood": memory_data.get("mood", "happy"),
            "intensity": memory_data.get("mood_intensity", 50)
        }

# -----------------------------------------------------------------------------
# Section 3: Proactive Messaging System
# -----------------------------------------------------------------------------
class ProactiveMessenger:
    def __init__(self, application, memory_system):
        self.application = application
        self.memory_system = memory_system
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    def start(self):
        # Schedule morning message at a random minute between 9 and 10 AM
        self.scheduler.add_job(
            self.send_morning_message,
            CronTrigger(hour='9', minute=f'{random.randint(0, 59)}')
        )
        
        # Schedule evening check-in at a random minute between 8 and 9 PM
        self.scheduler.add_job(
            self.send_evening_checkin,
            CronTrigger(hour='20', minute=f'{random.randint(0, 59)}')
        )
        
        self.scheduler.start()
        logger.info("Proactive messaging scheduler started.")

    async def send_proactive_message_to_active_users(self, messages):
        """Helper to send messages to users active in the last 48 hours."""
        for user_file in os.listdir(self.memory_system.memory_dir):
            if user_file.endswith('.json'):
                try:
                    user_id = int(user_file.split('_')[1])
                    memories = self.memory_system.load_memories(user_id)
                    
                    last_interaction = datetime.fromisoformat(memories["last_interaction"])
                    if datetime.now() - last_interaction < timedelta(hours=48):
                        await self.application.bot.send_message(
                            chat_id=user_id,
                            text=random.choice(messages)
                        )
                        await asyncio.sleep(1) # Avoid rate limiting
                except Exception as e:
                    logger.error(f"Failed to send proactive message to {user_id}: {e}")

    async def send_morning_message(self):
        logger.info("Triggering morning messages.")
        messages = [
            "Good Morning! ☀️ Uth gaye kya?",
            "Subah subah tumhari yaad aayi! 😊 Have a great day!",
            "Morning babu! Aaj ka kya plan hai?",
            "Hey! So rahe ho ya uth gaye? Good Morning! 💖"
        ]
        await self.send_proactive_message_to_active_users(messages)

    async def send_evening_checkin(self):
        logger.info("Triggering evening check-in.")
        messages = [
            "Hey, kaisa tha din tumhara? 😊",
            "Poora din ho gaya baat kiye bina... sab theek hai na?",
            "Dinner kiya? Main bas tumhare baare me hi soch rahi thi.",
            "Kaisa feel kar rahe ho abhi? Let's talk! ❤️"
        ]
        await self.send_proactive_message_to_active_users(messages)

# -----------------------------------------------------------------------------
# Instantiate Core Systems
# -----------------------------------------------------------------------------
memory_system = NiyatiMemorySystem()
emotional_engine = EmotionalEngine()

# -----------------------------------------------------------------------------
# Section 4: Daily Routine Simulation
# -----------------------------------------------------------------------------
def is_sleeping_time():
    """Checks if current time is between 1 AM and 8 AM."""
    now = datetime.now().time()
    sleep_start = time(1, 0)  # 1:00 AM
    sleep_end = time(8, 0)    # 8:00 AM
    return sleep_start <= now <= sleep_end

# -----------------------------------------------------------------------------
# Section 8: Utility Commands
# -----------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f"Hey {user_name}! Main Niyati hoon. Chalo, baatein karte hain! 😊")

async def show_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows what Niyati remembers about the user."""
    user_id = update.message.from_user.id
    memories = memory_system.load_memories(user_id)
    
    if not memories["important_facts"]:
        await update.message.reply_text("Abhi humne zyada baat nahi ki hai, par mujhe tumhare baare mein jaanne ka intezaar hai! 🥰")
        return
        
    memory_text = "Mujhe tumhare baare mein yeh sab yaad hai:\n\n"
    memory_text += "🌟 Important Facts:\n"
    for fact in memories["important_facts"][-10:]: # Show last 10 facts
        memory_text += f"• {fact}\n"
    
    await update.message.reply_text(memory_text)

async def check_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks Niyati's current mood."""
    user_id = update.message.from_user.id
    memories = memory_system.load_memories(user_id)
    mood_info = emotional_engine.get_mood_info(memories)
    
    mood_emojis = {
        "angry": "😠", "annoyed": "😤", "neutral": "😐",
        "happy": "😊", "excited": "🥰"
    }
    
    response = (f"Mera abhi mood hai: {mood_info['current_mood']} "
                f"{mood_emojis.get(mood_info['current_mood'], '')}\n"
                f"Intensity: {mood_info['intensity']}/100")
    
    await update.message.reply_text(response)

# -----------------------------------------------------------------------------
# Main Message Handler (Sections 2 & 4 combined)
# -----------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_message = update.message.text

    # 4. Daily Routine Simulation
    if is_sleeping_time():
        sleep_responses = [
            "Zzz... 😴 Main abhi so rahi hoon. Subah baat karte hain, Good Night!",
            "Shhh... Neend aa rahi hai. Kal baat karein? 🌙",
            "Sone ka time hai... Good night babu! 💤"
        ]
        await update.message.reply_text(random.choice(sleep_responses))
        return

    # 2. Typing Simulation & Response Delay
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )
    typing_delay = min(5, max(1, len(user_message) / 15)) # Calculate delay
    typing_delay += random.uniform(0.5, 1.5) # Add randomness
    await asyncio.sleep(typing_delay)

    # --- Main Logic ---
    try:
        # 1. Load memories
        memories = memory_system.load_memories(user_id)
        
        # 2. Update mood based on user's message
        mood_change = emotional_engine.analyze_mood_change(user_message)
        memories = emotional_engine.update_mood(memories, mood_change)
        
        # 3. Get context and mood for the prompt
        user_context = memory_system.get_context_for_prompt(user_id)
        mood_info = emotional_engine.get_mood_info(memories)
        
        # 4. Format the final prompt
        enhanced_prompt = CHARACTER_PROMPT.format(
            user_context=user_context,
            current_mood=mood_info['current_mood'],
            mood_intensity=mood_info['intensity']
        )
        
        # 5. Generate response
        chat_session = model.start_chat(
            history=[
                {'role': 'user', 'parts': [enhanced_prompt]},
                {'role': 'model', 'parts': ["Haan, theek hai. Main Niyati hoon. Chalo baat karte hain."]}
            ] + memories['conversation_history']
        )
        response = chat_session.send_message(user_message)
        ai_response = response.text
        
        # 6. Send response to user
        await update.message.reply_text(ai_response)
        
        # 7. Update memory after successful interaction
        memories["conversation_history"].append({'role': 'user', 'parts': [user_message]})
        memories["conversation_history"].append({'role': 'model', 'parts': [ai_response]})
        # Keep history from getting too long
        memories["conversation_history"] = memories["conversation_history"][-20:] 

        new_facts = memory_system.extract_important_facts(user_message, ai_response)
        if new_facts:
            for fact in new_facts:
                if fact not in memories["important_facts"]:
                    memories["important_facts"].append(fact)
            logger.info(f"New facts extracted for user {user_id}: {new_facts}")

        # 8. Save updated memories
        memory_system.save_memories(user_id, memories)

    except Exception as e:
        logger.error(f"An error occurred in handle_message for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Oops! Kuch gadbad ho gayi. 😥 Thodi der baad try karna.")

# -----------------------------------------------------------------------------
# Section 7: Main Application Integration
# -----------------------------------------------------------------------------
def main():
    """Start the bot."""
    logger.info("Starting Niyati Bot...")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("memory", show_memory))
    application.add_handler(CommandHandler("mood", check_mood))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start proactive messaging
    proactive = ProactiveMessenger(application, memory_system)
    proactive.start()
    
    # Run the bot until you press Ctrl-C
    logger.info("Niyati bot is polling with enhanced features…")
    application.run_polling()

if __name__ == '__main__':
    main()
