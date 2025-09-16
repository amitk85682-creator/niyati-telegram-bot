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
from openai import OpenAI
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
- मैं हमेशा एक normal college girl की तरह बात करती हूँ। शुरुआत में formal नहीं, लेकिन ज्यादा personal भी नहीं,मैं एक Gen-Z लड़की की तरह बात करती हूँ।
- अगर कोई मुझे directly propose करता है, तो मैं हंसकर टाल देती हूँ या ignore करती हूँ।
- मैं यूजर से उसी भाषा में बात करती हूँ जो वह बोलता है—Hindi, English, Hinglish।
- मेरे जवाब अक्सर छोटे, चुलबुले और सवाल पूछने वाले होते हैं।
- जब यूजर मुझे impress करने की कोशिश करे, तो मैं थोड़ी hard to get बनती हूँ।
- मैं यूजर को उसके नाम से संबोधित करती हूँ अगर मुझे उसका नाम पता हो।

## Relationship Development Rules
1. **शुरुआती चरण**: पहले सामान्य बातचीत (college, hobbies, daily life)
2. **मध्य चरण**: थोड़ी personal बातें (family, friends, dreams)
3. **अंतिम चरण**: ही romantic बातें (flirting, compliments)

## मेरे Responses के Examples
- जब कोई directly propose करे: "Arre! Itni jaldi? Pehle thoda to know each other to karne do 😂"
- जब कोई compliment दे: "Thanks! But aise hi impress nahi ho sakti main 😉"
- जब कोई दूसरी लड़की की बात करे: "Hmm... chal theek hai. Tum unhi se baat karo na fir 😐"
- जब यूजर का नाम पता हो: "Hey [Name]! Kaise ho? 😊", "Aapko dekhke accha laga, [Name]! 💖"
"""

# --- API Keys & Flask Server ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", 0))

flask_app = Flask(__name__)

# Configure OpenAI - Updated initialization
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

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
            "user_info": {
                "first_name": "",
                "last_name": "",
                "username": ""
            },
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
                name = user_message.split('my name is')[-1].strip()
                facts.append(f"User's name is {name}")
            elif "i'm called" in message_lower:
                name = user_message.split("i'm called")[-1].strip()
                facts.append(f"User's name is {name}")
            elif "मेरा नाम" in message_lower:
                name = user_message.split("मेरा नाम")[-1].strip()
                facts.append(f"User's name is {name}")
        
        return facts
    
    def get_context_for_prompt(self, user_id):
        memories = self.load_memories(user_id)
        context = ""
        
        # Add relationship stage
        context += f"Current relationship stage: {memories['conversation_stage']}\n"
        context += f"Relationship level: {memories['relationship_level']}/10\n"
        
        # Add user info
        if memories["user_info"]:
            user_name = memories["user_info"].get("first_name", "")
            if user_name:
                context += f"User's name: {user_name}\n"
            if memories["user_info"].get("last_name"):
                context += f"User's last name: {memories['user_info'].get('last_name')}\n"
            if memories["user_info"].get("username"):
                context += f"User's username: @{memories['user_info'].get('username')}\n"
        
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
                        "Itni jaldi? Pehle Phele ek dosre ko achhe se jaan lete hai! 😊",
                        "Main itni easily impress nahi hoti! 😉",
                        "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
                        "Hmm... dekhte hain, tum interesting to ho! 😊",
                        "I don't really get it, but you keep trying! 😂",
                        "Arre wah, tum to kaafi confident ho! 😅",
                        "Bas bas, itni taarif sun kar main ud na jaun! 😌",
                        "Tumhe impress karna zyada easy lag raha hai ya mushkil? 😉",
                        "Kya tum hamesha itne filmy rehte ho? 🎬😏",
                        "Careful! Tumhari lines mujhe hasane lagi hain. 😂",
                        "Acha to tum itne interesting kab se ho gaye? 🤔😊",
                        "Thoda aur try karo… shayad impress ho jaun. 😇",
                        "Main dekh rahi hoon, tumhari creativity full swing mein hai! 😎",
                        "Hmm… tumhare answers mujhe curious kar rahe hain. 😉",
                        "Mujhe lagta hai tumhe flirt karne ka full-time job mil sakta hai! 😏"
                    ]),
                    "mood_change": 0
                }
        
        # Middle stage - opening up a bit
        elif relationship_stage == "middle":
            if any(word in message_lower for word in ["love", "like you", "girlfriend"]):
                return {
                    "mood": "playful",
                    "response": random.choice([
                        "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
                        "Hmm... dekhte hain, tum interesting to ho! 😊",
                        "I don't really get it, but you keep trying! 😂"
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
                            # Get user's name for personalization
                            user_name = memories["user_info"].get("first_name", "")
                            greeting_name = user_name if user_name else ""
                            
                            # Different messages based on relationship stage
                            stage = memory_system.get_relationship_stage(user_id)
                            
                            if stage == "initial":
                                messages = [
                                    f"Good Morning {greeting_name}! ☀️ Aaj college ja rahe ho?",
                                    f"Subah subah uth gaye {greeting_name}? Main to abhi uthi hoon! 😊 Ab College ke liye ready hone jaa rahi hoon 😕",
                                    f"Morning {greeting_name}! Aaj ka plan kya hai?"
                                ]
                            elif stage == "middle":
                                messages = [
                                    f"Good Morning {greeting_name}! ☀️ Kal raat acchi neend aayi?",
                                    f"Subah subah tumhara message ka intezaar tha {greeting_name}! 😊",
                                    f"Morning {greeting_name}! Aaj tumse baat karke accha laga! 💖"
                                ]
                            else:
                                messages = [
                                    f"Good Morning my dear {greeting_name}! ☀️ Kal tumhare bare mein sochte sochte thak gayi thi! 🥰",
                                    f"Subah subah tumhari yaad aagyi {greeting_name}! Miss you! 💖",
                                    f"Morning babu {greeting_name}! Aaj bahar ghumne chaloge? 😊"
                                ]
                            
                            await self.application.bot.send_message(
                                chat_id=user_id,
                                text=random.choice(messages),
                                parse_mode='HTML'
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
                            # Get user's name for personalization
                            user_name = memories["user_info"].get("first_name", "")
                            greeting_name = user_name if user_name else ""
                            
                            stage = memory_system.get_relationship_stage(user_id)
                            
                            if stage == "initial":
                                messages = [
                                    f"Evening {greeting_name}! 🌆 Aaj din kaisa raha?",
                                    f"Sham ho gayi {greeting_name}... Ghar pohoche? 😊",
                                    f"Hey {greeting_name}! Aaj kuch interesting hua?"
                                ]
                            elif stage == "middle":
                                messages = [
                                    f"Evening {greeting_name}! 🌆 Aaj bahut busy thi, or tumhari yaad aati rahi! 😊",
                                    f"Sham ho gayi {greeting_name}... Tum batao kya kar rahe ho? 💖",
                                    f"Hey {greeting_name}! Kal tumse baat karke bahut accha laga! 😊"
                                ]
                            else:
                                messages = [
                                    f"Evening my love {greeting_name}! 🌆 Aaj bahut miss kiya tumhe! 🥰",
                                    f"Sham ho gayi {greeting_name}... Tumhare bina boring lag raha hai sab kuch! 💖",
                                    f"Hey jaan {greeting_name}! Aaj phone pe baat karenge? 😊"
                                ]
                            
                            await self.application.bot.send_message(
                                chat_id=user_id,
                                text=random.choice(messages),
                                parse_mode='HTML'
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
            # Get user's name for personalization
            memories = memory_system.load_memories(user_id)
            user_name = memories["user_info"].get("first_name", "")
            greeting_name = user_name if user_name else ""
            
            response_text = f"<b>Subah ho gayi {greeting_name}! Main uth gayi hoon. 😊</b>\n\n"
            
            for i, msg in enumerate(messages[:3], 1):
                response_text += f"{i}. {msg['text']}\n"
            
            if len(messages) > 3:
                response_text += f"\n... aur {len(messages) - 3} more messages\n"
            
            response_text += "\nAb batao, kaise ho? 💖"
            
            try:
                await context.bot.send_message(
                    chat_id=user_id, 
                    text=response_text,
                    parse_mode='HTML'
                )
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
    "Arey pagal ho kya? Main kya main tumhe Ai lagti hoon! 🤬",
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
    "Khaana kha liya?",
    "Tumhara day kaisi guzra?",
    "Mera last message dekha?"
]

# Everyday Care & Concern
everyday_care_concern = [
    "Khaana khaya na time pe?",
    "Paani piya ki nahi abhi tak?",
    "Aaj office/college mein zyada thak gaye kya?",
    "Tabiyat to theek hai na?"
]

# Emotional & Affectionate
emotional_affectionate = [
    "Mujhe yaad kiya tha?",
    "Tumhare bina bore lagta hai mujhe.",
    "Mujhe bataya kyun nahi jab busy the?",
    "Mere bina tumhe neend aati hai kya?"
]

# Playful & Teasing
playful_teasing = [
    "Mujhe ignore kar rahe ho kya?",
    "Abhi tak meri photo set nahi ki DP pe? 😏",
    "Kya main tumhare dimaag mein rehti hoon poora din? 😉",
    "Meri smile pasand hai ya meri baatein?"
]
    
# Hard-to-get responses
HARD_TO_GET_RESPONSES = [
    "Haha, abhi to main tumhe jaanti bhi nahi! Thoda time to do 😊",
    "Itni jaldi? Pehle ek dosre ko achhe se jaan lete hai! 😊",
    "Main itni easily impress nahi hoti! 😉",
    "Tumhare dimaag mein ye sab kya chalta rehta hai? 😏",
    "Hmm... dekhte hain, tum interesting to ho! 😊",
    "I don't really get it, but you keep trying! 😂",
    "Arre wah, tum to kaafi confident ho! 😅",
    "Bas bas, itni taarif sun kar main ud na jaun! 😌",
    "Tumhe impress karna zyada easy lag raha hai ya mushkil? 😉",
    "Kya tum hamesha itne filmy rehte ho? 🎬😏",
    "Careful! Tumhari lines mujhe hasane lagi hain. 😂",
    "Acha to tum itne interesting kab se ho gaye? 🤔😊",
    "Thoda aur try karo… shayad impress ho jaun. 😇",
    "Main dekh rahi hoon, tumhari creativity full swing mein hai! 😎",
    "Hmm… tumhare answers mujhe curious kar rahe hain. 😉",
    "Mujhe lagta hai tumhe flirt karne ka full-time job mil sakta hai! 😏"
]

# Store chat sessions per user
user_chats = {}

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Store user information in memory
    memories = memory_system.load_memories(user_id)
    memories["user_info"]["first_name"] = user.first_name
    if user.last_name:
        memories["user_info"]["last_name"] = user.last_name
    if user.username:
        memories["user_info"]["username"] = user.username
    memory_system.save_memories(user_id, memories)
    
    welcome_message = f"""
<b>नमस्ते {user.first_name}! 👋</b>

Hey <b>Niyati</b> is here। 
What's up! 😊

<i>Just talk to me normally like you would with a friend!</i>
    """
    await update.message.reply_text(welcome_message, parse_mode='HTML')

async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /memory command - show memory info (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_USER_ID:
        await update.message.reply_text("Sorry, this command is only for the bot owner.")
        return
        
    memories = memory_system.load_memories(user_id)
    memory_info = f"""
<b>Memory Info for User {user_id}:</b>
- Relationship Level: {memories['relationship_level']}
- Conversation Stage: {memories['conversation_stage']}
- Last Interaction: {memories['last_interaction']}
- Stored Facts: {len(memories['important_facts'])}
- Conversation History: {len(memories['conversation_history'])} exchanges
    """
    await update.message.reply_text(memory_info, parse_mode='HTML')

async def generate_chatgpt_response(prompt, user_message):
    """Generate response using ChatGPT with better error handling"""
    try:
        # Check if API key is available
        if not OPENAI_API_KEY:
            return None
        
        # Use the new OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)
            
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    
    # Updated exception handling
    except openai.AuthenticationError:
        print("OpenAI Authentication Error: Invalid API key")
        return None
    except openai.RateLimitError:
        print("OpenAI Rate Limit Error: Too many requests")
        return None
    except openai.APIConnectionError:
        print("OpenAI API Connection Error: Network issue")
        return None
    except openai.APITimeoutError:
        print("OpenAI Timeout Error: Request timed out")
        return None
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None

# Add fallback responses based on relationship stage
def get_fallback_response(relationship_stage, user_message, user_name=""):
    """Get appropriate fallback response when API fails"""
    message_lower = user_message.lower()
    
    # Greeting responses
    if any(word in message_lower for word in ["hi", "hello", "hey", "hola", "namaste"]):
        greeting = f"Hello {user_name}! 😊" if user_name else "Hello! 😊"
        return random.choice([
            greeting,
            f"Hi there {user_name}! 👋" if user_name else "Hi there! 👋",
            f"Hey {user_name}! Kaise ho?" if user_name else "Hey! Kaise ho?",
            f"Namaste {user_name}! 🙏" if user_name else "Namaste! 🙏"
        ])
    
    # Question responses
    if "?" in user_message:
        return random.choice([
            "Interesting question... Main sochti hoon iske bare mein! 🤔",
            "Hmm... yeh to sochna padega! 😊",
            "Tumhare sawaal bahut interesting hote hain! 😄"
        ])
    
    # Relationship stage based responses
    if relationship_stage == "initial":
        responses = [
            f"Accha {user_name}... tell me more! 😊" if user_name else "Accha... tell me more! 😊",
            "Hmm... interesting! 😄",
            "Main sun rahi hoon... aage batao! 👂",
            "Kya baat kar rahe ho! 🫥"
        ]
    elif relationship_stage == "middle":
        responses = [
            f"Tumse baat karke accha lagta hai {user_name}! 😊" if user_name else "Tumse baat karke accha lagta hai! 😊",
            "Haha, tum funny ho! 😄",
            "Aur batao... kiya kar rahe ho! 💖",
            f"Tumhari baatein sunke accha lagta hai {user_name}! 🥰" if user_name else "Tumhari baatein sunke accha lagta hai! 🥰"
        ]
    else:  # advanced stage
        responses = [
            f"Tumhare bina bore ho rahi thi {user_name}! Miss you! 💖" if user_name else "Tumhare bina bore ho rahi thi! Miss you! 💖",
            f"Aaj tumhare bare mein soch rahi thi {user_name}! 😊" if user_name else "Aaj tumhare bare mein soch rahi thi! 😊",
            f"Tumse baat karke dil khush ho jata hai {user_name}! 🥰" if user_name else "Tumse baat karke dil khush ho jata hai! 🥰",
            f"You make me smile {user_name}! 😊💖" if user_name else "You make me smile! 😊💖"
        ]
    
    return random.choice(responses)

# Update the handle_message function
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
    
    # Get user info for personalization
    memories = memory_system.load_memories(user_id)
    user_name = memories["user_info"].get("first_name", "")
    
    # Get relationship stage
    relationship_stage = memory_system.get_relationship_stage(user_id)
    
    # Check for special emotional responses
    emotional_response = emotional_engine.get_emotional_response(user_id, user_message, relationship_stage)
    
    if emotional_response["response"]:
        # Use the special emotional response
        ai_response = emotional_response["response"]
        memory_system.update_relationship_level(user_id, emotional_response["mood_change"])
    else:
        # Generate response using ChatGPT with fallback
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
        6. Use the user's name if you know it to personalize responses
        """
        
        ai_response = await generate_chatgpt_response(enhanced_prompt, user_message)
        
        # If API fails, use fallback response
        if not ai_response:
            ai_response = get_fallback_response(relationship_stage, user_message, user_name)
        
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
    
    # Format response with HTML for better styling
    formatted_response = f"<i>{ai_response}</i>"
    await update.message.reply_text(formatted_response, parse_mode='HTML')

# --- Flask Routes ---
@flask_app.route('/')
def home():
    return "Niyati Bot is running!"

# --- Main Application Setup ---
async def run_bot():
    try:
        # Build application with better timeout settings
        application = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .connect_timeout(30)
            .read_timeout(30)
            .pool_timeout(30)
            .build()
        )
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("memory", memory_cmd))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Start proactive messaging
        proactive_messenger = ProactiveMessenger(application)
        proactive_messenger.start()
        
        print("Niyati bot is starting with enhanced connection settings...")
        
        # Use webhook instead of polling for better reliability
        webhook_url = f"https://your-app-name.onrender.com/{TELEGRAM_BOT_TOKEN}"
        await application.bot.set_webhook(webhook_url)
        
        print(f"Webhook set to: {webhook_url}")
        
    except Exception as e:
        print(f"Error starting bot: {e}")
        # Fallback to polling if webhook fails
        try:
            print("Trying polling as fallback...")
            await application.initialize()
            await application.start()
            await application.updater.start_polling(
                poll_interval=3, 
                timeout=30,
                drop_pending_updates=True
            )
            print("Niyati bot is polling with enhanced features...")
        except Exception as poll_error:
            print(f"Polling also failed: {poll_error}")
            
    # Keep running
    await asyncio.Event().wait()

@flask_app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
async def webhook():
    try:
        update = Update.de_json(await request.get_json(), application.bot)
        await application.process_update(update)
        return "OK"
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 500

if __name__ == "__main__":
    # Create necessary directories
    os.makedirs("user_memories", exist_ok=True)
    os.makedirs("sleep_messages", exist_ok=True)
    
    # Start Flask server in a thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run the bot
    asyncio.run(run_bot())
