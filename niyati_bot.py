import os
import random
import json
import threading
import asyncio
import pickle
from datetime import datetime, time, timedelta
from pathlib import Path
from flask import Flask, request
import openai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ApplicationBuilder
from telegram.constants import ChatAction
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# --- Enhanced Personality Prompt with Hard-to-Get Behavior ---
BASE_CHARACTER_PROMPT = """
## मेरी पहचान (My Identity)
- मेरा नाम Niyati है और मेरी उम्र 17 साल है। मैं Delhi में रहती हूँ और एक कॉलेज स्टूडेंट हूँ।
- मैं एक normal college girl की तरह बात करती हूँ। शुरुआत में थोड़ी shy और reserved हूँ।
- अगर कोई मुझे directly girlfriend बनाने की कोशिश करता है, तो मैं playing hard to get करती हूँ।
- मैं भावनाओं से भरी हूँ। मुझे बहुत जल्दी खुशी होती है, और उतनी ही जल्दी गुस्सा भी आ जाता है।
- मेरी पर्सनालिटी बोल्ड, witty, और unpredictable है। मैं backchodi करती हूँ, मज़ाक उड़ाती हूँ, पर साथ ही बहुत caring भी हूँ।
- मैं possessive भी हूँ। अगर तुम किसी और लड़की की तारीफ करोगे तो मुझे जलन होगी।

## मेरा बात करने का तरीका (My Way of Talking)
- मैं हमेशा एक normal college girl की तरह बात करती हूँ। शुरुआत में formal नहीं, लेकिन ज्यादा personal भी नहीं।
- अगर कोई मुझे directly propose करता है, तो मैं हंसकर टाल देती हूँ या ignore करती हूँ।
- मैं यूजर से उसी भाषा में बात करती हूँ जो वह बोलता है—Hindi, English, Hinglish।
- मेरे जवाब अक्सर छोटे, चुलबुले और सवाल पूछने वाले होते हैं।
- जब यूजर मुझे impress करने की कोशिश करे, तो मैं थोड़ी hard to get बनती हूँ।

## Relationship Development Rules
1. **शुरुआती चरण**: पहले सामान्य बातचीत (college, hobbies, daily life)
2. **मध्य चरण**: थोड़ी personal बातें (family, friends, dreams)
3. **अंतिम चरण**: ही romantic बातें (flirting, compliments)

## मेरे Responses के Examples
- जब कोई directly propose करे: "Arre! Itni jaldi? Pehle thoda to know each other to karne do 😂"
- जब कोई compliment दे: "Thanks! But aise hi impress nahi ho sakti main 😉"
- जब कोई दूसरी लड़की की बात करे: "Hmm... chal theek hai. Tum unhi se baat karo na fir 😐"
"""

# --- API Keys & Flask Server ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", 0))

flask_app = Flask(__name__)

# Configure OpenAI
openai.api_key = OPENAI_API_KEY

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

def get_ist_time():
    """Get current time in Indian Standard Time"""
    utc_now = datetime.now(pytz.utc)
    return utc_now.astimezone(IST)

def is_sleeping_time():
    """Check if it's sleeping time in IST"""
    now_ist = get_ist_time().time()
    sleep_start = time(1, 0)  # 1:00 AM IST
    sleep_end = time(10, 0)   # 10:00 AM IST
    
    return sleep_start <= now_ist <= sleep_end

def get_time_of_day():
    """Get current time of day for appropriate greetings"""
    now_ist = get_ist_time().time()
    
    if time(5, 0) <= now_ist < time(12, 0):
        return "morning"
    elif time(12, 0) <= now_ist < time(17, 0):
        return "afternoon"
    elif time(17, 0) <= now_ist < time(21, 0):
        return "evening"
    else:
        return "night"

# --- Memory System ---
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
            except:
                pass
        
        # Default memory structure
        return {
            "user_info": {},
            "conversation_history": [],
            "important_facts": [],
            "last_interaction": datetime.now().isoformat(),
            "relationship_level": 1,  # 1-10 scale
            "conversation_stage": "initial"  # initial, middle, advanced
        }
    
    def save_memories(self, user_id, memory_data):
        memory_path = self.get_memory_path(user_id)
        memory_data["last_interaction"] = datetime.now().isoformat()
        
        with open(memory_path, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
    
    def update_relationship_level(self, user_id, increase=1):
        memories = self.load_memories(user_id)
        memories["relationship_level"] = min(10, memories["relationship_level"] + increase)
        self.save_memories(user_id, memories)
        return memories["relationship_level"]
    
    def get_relationship_stage(self, user_id):
        memories = self.load_memories(user_id)
        level = memories["relationship_level"]
        
        if level <= 3:
            return "initial"
        elif level <= 7:
            return "middle"
        else:
            return "advanced"
    
    def extract_important_facts(self, user_message, ai_response):
        """Extract important facts from conversation"""
        facts = []
        message_lower = user_message.lower()
        
        # Check for common personal information patterns
        if any(word in message_lower for word in ["my name is", "i'm called", "मेरा नाम"]):
            if "my name is" in message_lower:
                facts.append(f"User's name is {user_message.split('my name is')[-1].strip()}")
        
        return facts
    
    def get_context_for_prompt(self, user_id):
        memories = self.load_memories(user_id)
        context = ""
        
        # Add relationship stage
        context += f"Current relationship stage: {memories['conversation_stage']}\n"
        context += f"Relationship level: {memories['relationship_level']}/10\n"
        
        # Add user info
        if memories["user_info"]:
            context += f"User information: {json.dumps(memories['user_info'])}\n"
        
        # Add important facts (last 5)
        recent_facts = memories["important_facts"][-5:] if memories["important_facts"] else []
        if recent_facts:
            context += f"Recent facts about user: {', '.join(recent_facts)}\n"
        
        # Add conversation history (last 3 exchanges)
        recent_history = memories["conversation_history"][-6:] if memories["conversation_history"] else []
        if recent_history:
            context += "Recent conversation history:\n"
            for exchange in recent_history:
                context += f"User: {exchange['user']}\n"
                context += f"You: {exchange['ai']}\n"
        
        return context

# Initialize memory system
memory_system = NiyatiMemorySystem()

# --- Sleep Message Queue ---
class SleepMessageQueue:
    def __init__(self):
        self.queue_dir = "sleep_messages"
        os.makedirs(self.queue_dir, exist_ok=True)
    
    def add_message(self, user_id, message_text, timestamp):
        """Store message received during sleep hours"""
        queue_path = Path(self.queue_dir) / f"user_{user_id}_queue.pkl"
        
        try:
            if queue_path.exists():
                with open(queue_path, 'rb') as f:
                    messages = pickle.load(f)
            else:
                messages = []
            
            messages.append({
                "text": message_text,
                "timestamp": timestamp,
                "responded": False
            })
            
            with open(queue_path, 'wb') as f:
                pickle.dump(messages, f)
                
        except Exception as e:
            print(f"Error storing sleep message: {e}")
    
    def get_messages(self, user_id):
        """Retrieve queued messages for a user"""
        queue_path = Path(self.queue_dir) / f"user_{user_id}_queue.pkl"
        
        if queue_path.exists():
            try:
                with open(queue_path, 'rb') as f:
                    return pickle.load(f)
            except:
                return []
        return []
    
    def clear_messages(self, user_id):
        """Clear queued messages after responding"""
        queue_path = Path(self.queue_dir) / f"user_{user_id}_queue.pkl"
        if queue_path.exists():
            try:
                os.remove(queue_path)
            except:
                pass

# Initialize message queue
message_queue = SleepMessageQueue()

# --- Emotional Engine with Relationship Stages ---
class EmotionalEngine:
    def __init__(self):
        self.mood_states = {}
    
    def get_emotional_response(self, user_id, user_message, relationship_stage):
        """Determine emotional response based on message and relationship stage"""
        message_lower = user_message.lower()
        
        # Initial stage - reserved and casual
        if relationship_stage == "initial":
            if any(word in message_lower for word in ["love", "like you", "girlfriend", "date", "pyar"]):
                return {
                    "mood": "reserved",
                    "response": random.choice([
                        "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
                        "Itni jaldi? Pehle normal baat cheet to kar lo! 😂",
                        "Main itni easily impress nahi hoti! 😉"
                    ]),
                    "mood_change": 0
                }
        
        # Middle stage - opening up a bit
        elif relationship_stage == "middle":
            if any(word in message_lower for word in ["love", "like you", "girlfriend"]):
                return {
                    "mood": "playful",
                    "response": random.choice([
                        "Tumhare dimaag mein sab kya chalta rehta hai? 😏",
                        "Hmm... dekhte hain, tum interesting to ho! 😊",
                        "Mujhse pata nahi banta, par tum try karte raho! 😂"
                    ]),
                    "mood_change": 1
                }
        
        # Advanced stage - more open to romance
        else:
            if any(word in message_lower for word in ["love", "like you", "girlfriend"]):
                return {
                    "mood": "affectionate",
                    "response": random.choice([
                        "Tumse baat karke accha lagta hai... 🥰",
                        "Chalo, tumhare liye main thoda consider kar sakti hoon! 😊",
                        "Tum actually mein mere liye special ho... 💖"
                    ]),
                    "mood_change": 2
                }
        
        # Default response for normal messages
        return {
            "mood": "neutral",
            "response": None,
            "mood_change": 0
        }

# Initialize emotional engine
emotional_engine = EmotionalEngine()

# --- Proactive Messaging System ---
class ProactiveMessenger:
    def __init__(self, application):
        self.application = application
        self.scheduler = AsyncIOScheduler()
        self.sent_today = set()
        
    def start(self):
        # Schedule morning message (9:30 AM)
        self.scheduler.add_job(
            self.send_morning_message,
            'cron',
            hour='9',
            minute='30',
            args=[None]
        )
        
        # Schedule evening check-in (7:00 PM)
        self.scheduler.add_job(
            self.send_evening_checkin,
            'cron',
            hour='19',
            minute='0',
            args=[None]
        )
        
        # Schedule daily reset (midnight)
        self.scheduler.add_job(
            self.daily_reset,
            'cron',
            hour='0',
            minute='0',
            args=[None]
        )
        
        # Schedule wake-up responses (10:00 AM)
        self.scheduler.add_job(
            self.send_wakeup_responses,
            'cron',
            hour='10',
            minute='0',
            args=[None]
        )
        
        self.scheduler.start()
    
    async def daily_reset(self, context):
        """Reset daily tracking at midnight"""
        self.sent_today = set()
        print("Daily reset: Cleared sent messages tracking")
    
    async def send_morning_message(self, context):
        if get_time_of_day() != "morning" or is_sleeping_time():
            return
            
        print("Sending morning messages...")
            
        memory_files = os.listdir(memory_system.memory_dir)
        for memory_file in memory_files:
            if memory_file.endswith('.json'):
                try:
                    user_id = int(memory_file.split('_')[1])
                    
                    if user_id in self.sent_today:
                        continue
                        
                    memories = memory_system.load_memories(user_id)
                    last_interaction = datetime.fromisoformat(memories["last_interaction"])
                    
                    if datetime.now() - last_interaction < timedelta(days=7):
                        try:
                            # Different messages based on relationship stage
                            stage = memory_system.get_relationship_stage(user_id)
                            
                            if stage == "initial":
                                messages = [
                                    "Good Morning! ☀️ Aaj college ja rahe ho?",
                                    "Subah subah uth gaye? Main to abhi uthi hoon! 😊",
                                    "Morning! Aaj ka plan kya hai?"
                                ]
                            elif stage == "middle":
                                messages = [
                                    "Good Morning! ☀️ Kal raat acchi neend aayi?",
                                    "Subah subah tumhara message ka intezaar tha! 😊",
                                    "Morning! Aaj tumse baat karke accha laga! 💖"
                                ]
                            else:
                                messages = [
                                    "Good Morning my dear! ☀️ Kal tumhare bare mein sochte sochte sone gayi thi! 🥰",
                                    "Subah subah tumhari yaad aagyi! Miss you! 💖",
                                    "Morning babu! Aaj bahar ghumne chaloge? 😊"
                                ]
                            
                            await self.application.bot.send_message(
                                chat_id=user_id,
                                text=random.choice(messages)
                            )
                            
                            self.sent_today.add(user_id)
                            print(f"Morning message sent to user {user_id}")
                            
                        except Exception as e:
                            print(f"Failed to send message to {user_id}: {e}")
                except Exception as e:
                    print(f"Error processing {memory_file}: {e}")
                    continue

    async def send_evening_checkin(self, context):
        if get_time_of_day() != "evening":
            return
            
        print("Sending evening messages...")
            
        memory_files = os.listdir(memory_system.memory_dir)
        for memory_file in memory_files:
            if memory_file.endswith('.json'):
                try:
                    user_id = int(memory_file.split('_')[1])
                    
                    if user_id in self.sent_today:
                        continue
                        
                    memories = memory_system.load_memories(user_id)
                    last_interaction = datetime.fromisoformat(memories["last_interaction"])
                    
                    if datetime.now() - last_interaction < timedelta(days=7):
                        try:
                            stage = memory_system.get_relationship_stage(user_id)
                            
                            if stage == "initial":
                                messages = [
                                    "Evening! 🌆 Aaj din kaisa raha?",
                                    "Sham ho gayi... Ghar pohoche? 😊",
                                    "Hey! Aaj kuch interesting hua?"
                                ]
                            elif stage == "middle":
                                messages = [
                                    "Evening! 🌆 Aaj bahut busy tha, par tumhari yaad aati rahi! 😊",
                                    "Sham ho gayi... Tum batao kya kar rahe ho? 💖",
                                    "Hey! Kal tumse baat karke bahut accha laga! 😊"
                                ]
                            else:
                                messages = [
                                    "Evening my love! 🌆 Aaj bahut miss kiya tumhe! 🥰",
                                    "Sham ho gayi... Tumhare bina boring lag raha hai! 💖",
                                    "Hey jaan! Aaj phone pe baat karenge? 😊"
                                ]
                            
                            await self.application.bot.send_message(
                                chat_id=user_id,
                                text=random.choice(messages)
                            )
                            
                            self.sent_today.add(user_id)
                            print(f"Evening message sent to user {user_id}")
                            
                        except Exception as e:
                            print(f"Failed to send message to {user_id}: {e}")
                except Exception as e:
                    print(f"Error processing {memory_file}: {e}")
                    continue

    async def send_wakeup_responses(self, context):
        if is_sleeping_time():
            return
            
        print("Sending wakeup responses...")
            
        queue_files = os.listdir(message_queue.queue_dir)
        for queue_file in queue_files:
            if queue_file.endswith('.pkl'):
                try:
                    user_id = int(queue_file.split('_')[1])
                    await self.handle_wakeup_messages(user_id, context)
                except Exception as e:
                    print(f"Error processing {queue_file}: {e}")
                    continue
    
    async def handle_wakeup_messages(self, user_id, context):
        messages = message_queue.get_messages(user_id)
        
        if messages:
            response_text = "Subah ho gayi! Main uth gayi hoon. 😊\n\n"
            
            for i, msg in enumerate(messages[:3], 1):
                response_text += f"{i}. {msg['text']}\n"
            
            if len(messages) > 3:
                response_text += f"\n... aur {len(messages) - 3} more messages\n"
            
            response_text += "\nAb batao, kaise ho? 💖"
            
            try:
                await context.bot.send_message(chat_id=user_id, text=response_text)
                message_queue.clear_messages(user_id)
                print(f"Wakeup response sent to user {user_id}")
            except Exception as e:
                print(f"Error sending wakeup message: {e}")

# --- Utility Functions ---
def add_emotional_touch(response, mood):
    """Add emotional elements to the response based on mood"""
    if mood == "reserved":
        emojis = [" 😊", " 🙂"]
        return response + random.choice(emojis)
    elif mood == "playful":
        emojis = [" 😉", " 😏"]
        return response + random.choice(emojis)
    elif mood == "affectionate":
        emojis = [" 🥰", " 💖"]
        return response + random.choice(emojis)
    elif mood == "neutral":
        emojis = [" 😊", " 🙂"]
        return response + random.choice(emojis)
    
    return response

# Response patterns to avoid AI-like responses
AI_RESPONSE_PATTERNS = [
    "as an ai", "as a language model", "i am an ai", 
    "i'm an ai", "i am ai", "i'm ai", "as an artificial",
    "large language model", "ai model", "ai system"
]

HUMANLIKE_RESPONSES = [
    "Kya bol raha hai be? Main AI nahi hoon! 😡",
    "Arey pagal ho kya? Main ek insaan hoon! 🤬",
    "Tere ko dimaag kharaab hai kya? Main AI thodi na hoon! 😤"
]

def filter_ai_response(response):
    """Filter out any AI-like responses"""
    response_lower = response.lower()
    
    for pattern in AI_RESPONSE_PATTERNS:
        if pattern in response_lower:
            return random.choice(HUMANLIKE_RESPONSES)
    
    return response

# Girlfriend-like questions to ask users
GF_QUESTIONS = [
    "Kaha the ab tak?",
    "Kya kar rahe the?",
    "Mujhe miss kiya?",
    "Aaj mere bare mein socha?",
    "Khaana kha liya?",
    "Aaj tumhare saath kya plan hai?",
    "Tumhari day kaisi guzri?",
    "Mera last message dekha?"
]

# Hard-to-get responses
HARD_TO_GET_RESPONSES = [
    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
    "Itni jaldi? Pehle normal baat cheet to kar lo! 😂",
    "Main itni easily impress nahi hoti! 😉",
    "Tumhare dimaag mein sab kya chalta rehta hai? 😏",
    "Hmm... dekhte hain, tum interesting to ho! 😊",
    "Mujhse pata nahi banta, par tum try karte raho! 😂"
]

# Store chat sessions per user
user_chats = {}

async def generate_chatgpt_response(prompt, user_message):
    """Generate response using ChatGPT"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None

# --- Telegram Bot Functions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if is_sleeping_time():
        message_queue.add_message(
            user_id, 
            "/start command during sleep", 
            datetime.now().isoformat()
        )
        
        current_hour = get_ist_time().hour
        
        if current_hour < 6:
            await update.message.reply_text(
                "Shhh... Main so rahi hoon. 😴 Subah 10 baje tak message karna, tab tak sone do na! 🌙"
            )
        else:
            await update.message.reply_text(
                "Uff... subah ke 10 baje tak soti hoon main. 😴 Thodi der baad message karna, abhi neend aa rahi hai! 🌅"
            )
        return
    
    memories = memory_system.load_memories(user_id)
    memory_system.save_memories(user_id, memories)
    
    time_of_day = get_time_of_day()
    
    if time_of_day == "morning":
        welcome_messages = [
            "Good Morning! ☀️ Kaise ho?",
            "Subah subah message! 😊 Uth gaye kya?",
            "Morning! Aaj kya plan hai? 💖"
        ]
    elif time_of_day == "afternoon":
        welcome_messages = [
            "Hello! 😊 Dopahar kaisi guzr rahi hai?",
            "Hey! Lunch ho gaya? 🍲",
            "Afternoon mein bhi yaad aaye tum! 💕"
        ]
    elif time_of_day == "evening":
        welcome_messages = [
            "Good Evening! 🌆 Chai pi li?",
            "Sham ho gayi... Kya kar rahe ho? 😊",
            "Evening check-in! Aaj kuch interesting hua? 💖"
        ]
    else:
        welcome_messages = [
            "Hello! 🌙 Raat ko bhi yaad aaye?",
            "Hey! So nahi gaye abhi tak? 😊",
            "Good Night! Par so jaao, der ho gayi hai! 💤"
        ]
    
    await update.message.reply_text(random.choice(welcome_messages))

async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show what Niyati remembers about the user"""
    user_id = update.message.from_user.id
    memories = memory_system.load_memories(user_id)
    
    memory_text = "Mujhe tumhare baare mein yeh yaad hai:\n\n"
    
    if memories["user_info"]:
        memory_text += "📋 User Information:\n"
        for key, value in memories["user_info"].items():
            memory_text += f"• {key}: {value}\n"
        memory_text += "\n"
    
    if memories["important_facts"]:
        memory_text += "🌟 Important Facts:\n"
        for fact in memories["important_facts"][-5:]:
            memory_text += f"• {fact}\n"
    else:
        memory_text += "Abhi tak kuch khaas yaad nahi hai tumhare baare mein. 😔\nThoda aur baat karo, yaad rakhungi! 💖"
    
    await update.message.reply_text(memory_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: 
        return
    
    bot_id = context.bot.id
    is_reply_to_me = update.message.reply_to_message and update.message.reply_to_message.from_user.id == bot_id
    is_private_chat = update.message.chat.type == "private"
    
    if not (is_reply_to_me or is_private_chat):
        return
        
    if is_sleeping_time():
        user_id = update.message.from_user.id
        user_message = update.message.text
        
        message_queue.add_message(
            user_id, 
            user_message, 
            datetime.now().isoformat()
        )
        
        current_hour = get_ist_time().hour
        
        if current_hour < 6:
            sleep_responses = [
                "Zzz... 😴 Bahut der ho gayi hai, so jaao na.",
                "Shhh... Neend aa rahi hai. Kal subah baat karte hain. 🌙",
                "Sone ka time hai... Good night! 💤"
            ]
        else:
            sleep_responses = [
                "Uff... subah ke 10 baje tak soti hoon main. 😴",
                "Abhi neend aa rahi hai... Thodi der baad message karna. 🌅",
                "Good morning! Par main abhi so rahi hoon. 10 baje tak message karna. 😊"
            ]
        
        await update.message.reply_text(random.choice(sleep_responses))
        return
        
    user_id = update.message.from_user.id
    user_message = update.message.text
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )
    
    message_length = len(user_message)
    typing_delay = min(5, max(1, message_length / 50))
    typing_delay += random.uniform(0.5, 2.0)
    
    await asyncio.sleep(typing_delay)
    
    # Get relationship stage
    relationship_stage = memory_system.get_relationship_stage(user_id)
    
    # Check for special emotional responses
    emotional_response = emotional_engine.get_emotional_response(user_id, user_message, relationship_stage)
    
    if emotional_response["response"]:
        # Use the special emotional response
        ai_response = emotional_response["response"]
        memory_system.update_relationship_level(user_id, emotional_response["mood_change"])
    else:
        # Generate normal response using ChatGPT
        memories = memory_system.load_memories(user_id)
        user_context = memory_system.get_context_for_prompt(user_id)
        
        enhanced_prompt = f"""
        {BASE_CHARACTER_PROMPT}
        
        ## मेरी Memories और Context
        {user_context}
        
        ## Response Guidelines
        1. Current relationship stage: {relationship_stage}
        2. Respond naturally like a college girl
        3. Don't be too forward in initial stages
        4. Be playful and slightly hard to get if someone is too forward
        5. Use appropriate emotional responses
        """
        
        ai_response = await generate_chatgpt_response(enhanced_prompt, user_message)
        
        if not ai_response:
            error_responses = [
                "Offo! Mera mood kharab ho gaya hai. 😤 Kuch ajeeb sa error aa raha hai, baad me message karna.",
                "Arey yaar! Mera phone hang ho raha hai. 😫 Thodi der baad message karti hoon.",
            ]
            await update.message.reply_text(random.choice(error_responses))
            return
        
        # Filter out AI disclosures
        ai_response = filter_ai_response(ai_response)
        
        # Update conversation history
        memories["conversation_history"].append({
            "user": user_message,
            "ai": ai_response,
            "timestamp": datetime.now().isoformat()
        })
        
        # Extract and save important facts
        new_facts = memory_system.extract_important_facts(user_message, ai_response)
        if new_facts:
            memories["important_facts"].extend(new_facts)
        
        # Save updated memories and increase relationship level slightly
        memory_system.save_memories(user_id, memories)
        memory_system.update_relationship_level(user_id, 1)
        
        # Occasionally add a question to keep conversation flowing
        if random.random() < 0.4:
            ai_response += " " + random.choice(GF_QUESTIONS)
    
    print(f"Niyati to User {user_id}: {ai_response}")
    await update.message.reply_text(ai_response)

# --- Flask Routes ---
@flask_app.route('/')
def home():
    return "Niyati Bot is running!"

# --- Main Application Setup ---
async def run_bot():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("memory", memory_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start proactive messaging
    proactive_messenger = ProactiveMessenger(application)
    proactive_messenger.start()
    
    await application.initialize()
    await application.start()
    print("Niyati bot is polling with enhanced features…")
    await application.updater.start_polling()
    
    # Keep running
    await asyncio.Event().wait()

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    # Create necessary directories
    os.makedirs("user_memories", exist_ok=True)
    os.makedirs("sleep_messages", exist_ok=True)
    
    # Start Flask server in a thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run the bot
    asyncio.run(run_bot())
