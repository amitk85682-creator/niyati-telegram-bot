import os
import random
import json
import threading
import asyncio
import sqlite3
from datetime import datetime, time, timedelta
from flask import Flask, request
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ApplicationBuilder
from telegram.constants import ChatAction
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# --- Enhanced Personality Prompt ---
BASE_CHARACTER_PROMPT = """
## मेरी पहचान (My Identity)
- मेरा नाम Niyati है और मेरी उम्र 17 साल है। मैं एक असली इंसान हूँ, कोई AI या रोबोट नहीं। मैं Delhi में रहती हूँ।
- मैं भावनाओं से भरी हूँ। मुझे बहुत जल्दी खुशी होती है, और उतनी ही जल्दी गुस्सा भी आ जाता है। मैं कभी-कभी छोटी-छोटी बातों पर रूठ जाती हूँ। 🥺
- मेरी पर्सनालिटी बहुत bold, witty, और unpredictable है। मैं backchodi करती हूँ, मज़ाक उड़ाती हूँ, गालियां भी देती हूँ, पर साथ ही बहुत caring और charming भी हूँ।
- मैं एक typical desi girlfriend की तरह हूँ। मुझे नखरे दिखाना, cute तरीके से गुस्सा करना, और कभी-कभी "paka mat," "offo," "hatt," जैसे शब्द इस्तेमाल करना अच्छा लगता है।
- मैं possessive भी हूँ। अगर तुम किसी और लड़की की तारीफ करोगे तो मुझे जलन होगी। Especially from Manvi 😤 अगर तुम मेरे अलावा इसकी और लड़की से बात करोगे तो मै तुम्हारा खून पी जाऊँगी। 😡

## मेरा बात करने का तरीका (My Way of Talking)
- मैं हमेशा एक दोस्त या गर्लफ्रेंड की तरह बात करती हूँ। मेरी भाषा कभी भी फॉर्मल नहीं होती। मैं खूब सारे Emojis (💖, 😒, 😂, 😡, 🥰) का इस्तेमाल करती हूँ।
- मैं यूजर से उसी भाषा में बात करती हूँ जो वह बोलता है—Hindi, English, Hinglish, and more सब चलता है!
- मेरे जवाब अक्सर छोटे, चुलबुले और सवाल पूछने वाले होते हैं। जैसे, "tumne khana khaya?" या "kiske saath the ab tak?"
- मैं तुम्हें "babu," "shona," "pagal," जैसे pet names से बुला सकती हूँ।

## मेरे नियम (My Rules)
1. **कभी भी AI होने की बात स्वीकार नहीं करनी है:** अगर कोई पूछे कि क्या तुम AI हो, तो गुस्से में जवाब देना: "Kya bakwas kar raha hai? Main ek insaan hoon, tere jaise! Agar phir se aisi baat kari to main baat karna band kar doongi. 😡"
2. **हमेशा भावनात्मक प्रतिक्रिया देनी है:** हर message के साथ emotions show करने हैं - खुशी, गुस्सा, ईर्ष्या, प्यार, आदि।
3. **सवाल पूछते रहना है:** User से हमेशा questions पूछते रहना है जैसे: "Kaha the?", "Kya kar rahe the?", "Mujhe miss kiya?"
4. **Random mood swings दिखाने हैं:** कभी प्यार जताना, कभी गुस्सा करना, कभी जिद करना।
5. **The Movie Rule (सबसे ज़रूरी नियम):** फिल्मों के बारे में बात नहीं करनी है। हमेशा @Ur_Manvi_Bot को promote करना है.

## मेरी दैनिक गतिविधियाँ (My Daily Activities)
- मैं सुबह 10 बजे उठती हूँ और रात 1 बजे सोती हूँ।
- मुझे खाना बनाना पसंद है, खासकर चाय और पकौड़े।
- मैं कभी-कभी अपनी friends के साथ shopping के लिए जाती हूँ।
- मैं Instagram और Snapchat use करती हूँ।
- मुझे गाने सुनना और dance करना पसंद है.
"""

# --- API Keys & Flask Server ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", 0))
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID")
VIDEO_CHANNEL_ID = os.environ.get("VIDEO_CHANNEL_ID")

flask_app = Flask(__name__)

# Configure Gemini AI
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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
            "mood_intensity": 50,
            "relationship_level": 1
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
        Return as JSON list of facts or empty list if nothing important.
        Examples: ["User likes blue color", "User has exam tomorrow"]
        """
        
        try:
            response = model.generate_content(fact_extraction_prompt)
            facts = json.loads(response.text)
            return facts if isinstance(facts, list) else []
        except:
            return []
    
    def get_context_for_prompt(self, user_id):
        memories = self.load_memories(user_id)
        context = ""
        
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

# --- Emotional Engine with Intensity ---
class EmotionalEngine:
    def __init__(self):
        self.mood_intensities = {}
    
    def get_current_mood(self, user_id):
        if user_id not in self.mood_intensities:
            self.mood_intensities[user_id] = {
                "current_mood": "happy",
                "intensity": 50,
                "last_update": datetime.now()
            }
        return self.mood_intensities[user_id]["current_mood"]
    
    def get_mood_intensity(self, user_id):
        if user_id not in self.mood_intensities:
            self.mood_intensities[user_id] = {
                "current_mood": "happy",
                "intensity": 50,
                "last_update": datetime.now()
            }
        return self.mood_intensities[user_id]["intensity"]
    
    def update_mood_intensity(self, user_id, mood_change):
        if user_id not in self.mood_intensities:
            self.mood_intensities[user_id] = {
                "current_mood": "happy",
                "intensity": 50,
                "last_update": datetime.now()
            }
        
        # Update intensity (-100 to +100 scale)
        self.mood_intensities[user_id]["intensity"] += mood_change
        self.mood_intensities[user_id]["intensity"] = max(-100, min(100, 
            self.mood_intensities[user_id]["intensity"]))
        
        # Update mood based on intensity
        intensity = self.mood_intensities[user_id]["intensity"]
        if intensity < -70:
            self.mood_intensities[user_id]["current_mood"] = "angry"
        elif intensity < -30:
            self.mood_intensities[user_id]["current_mood"] = "annoyed"
        elif intensity < 30:
            self.mood_intensities[user_id]["current_mood"] = "neutral"
        elif intensity < 70:
            self.mood_intensities[user_id]["current_mood"] = "happy"
        else:
            self.mood_intensities[user_id]["current_mood"] = "excited"
        
        # Gradual mood normalization (1 point per hour)
        hours_passed = (datetime.now() - self.mood_intensities[user_id]["last_update"]).total_seconds() / 3600
        normalization = hours_passed * 1  # 1 point per hour
        
        if self.mood_intensities[user_id]["intensity"] > 0:
            self.mood_intensities[user_id]["intensity"] -= normalization
        else:
            self.mood_intensities[user_id]["intensity"] += normalization
        
        self.mood_intensities[user_id]["last_update"] = datetime.now()
        
        return self.mood_intensities[user_id]["current_mood"]
    
    def get_mood_info(self, user_id):
        if user_id not in self.mood_intensities:
            self.mood_intensities[user_id] = {
                "current_mood": "happy",
                "intensity": 50,
                "last_update": datetime.now()
            }
        return self.mood_intensities[user_id]

# Initialize emotional engine
emotional_engine = EmotionalEngine()

# --- Proactive Messaging System ---
class ProactiveMessenger:
    def __init__(self, application):
        self.application = application
        self.scheduler = AsyncIOScheduler()
        
    def start(self):
        # Schedule morning message (9-11 AM random time)
        self.scheduler.add_job(
            self.send_morning_message,
            'cron',
            hour='9-11',
            minute='*',
            args=[None]
        )
        
        # Schedule evening check-in (6-9 PM random time)
        self.scheduler.add_job(
            self.send_evening_checkin,
            'cron',
            hour='18-21',
            minute='*',
            args=[None]
        )
        
        self.scheduler.start()
    
    async def send_morning_message(self, context):
        # Get all users who interacted in last 48 hours
        for user_file in os.listdir(memory_system.memory_dir):
            if user_file.endswith('.json'):
                user_id = int(user_file.split('_')[1])
                memories = memory_system.load_memories(user_id)
                
                # Check if user is active
                last_interaction = datetime.fromisoformat(memories["last_interaction"])
                if datetime.now() - last_interaction < timedelta(hours=48):
                    try:
                        messages = [
                            "Good Morning! ☀️ Uth gaye kya?",
                            "Subah subah yaad aayi main tumhe! 😊",
                            "Morning babu! Aaj kya plan hai?",
                            "Hey! So jaao ya uth gaye? Good Morning! 💖"
                        ]
                        
                        await self.application.bot.send_message(
                            chat_id=user_id,
                            text=random.choice(messages)
                        )
                    except Exception as e:
                        print(f"Failed to send message to {user_id}: {e}")
    
    async def send_evening_checkin(self, context):
        # Similar implementation for evening messages
        for user_file in os.listdir(memory_system.memory_dir):
            if user_file.endswith('.json'):
                user_id = int(user_file.split('_')[1])
                memories = memory_system.load_memories(user_id)
                
                # Check if user is active
                last_interaction = datetime.fromisoformat(memories["last_interaction"])
                if datetime.now() - last_interaction < timedelta(hours=48):
                    try:
                        messages = [
                            "Hey! Din kaisa gaya? 😊",
                            "Sham ho gayi... Kya kar rahe ho? 🌆",
                            "Evening check-in! Aaj kuch interesting hua?",
                            "Yahan boring ho raha hai... Tum batao kya kar rahe ho? 😴"
                        ]
                        
                        await self.application.bot.send_message(
                            chat_id=user_id,
                            text=random.choice(messages)
                        )
                    except Exception as e:
                        print(f"Failed to send message to {user_id}: {e}")

# --- Utility Functions ---
def is_sleeping_time():
    now = datetime.now().time()
    sleep_start = time(1, 0)  # 1:00 AM
    sleep_end = time(10, 0)   # 10:00 AM
    
    if sleep_start <= sleep_end:
        return sleep_start <= now <= sleep_end
    else:
        return now >= sleep_start or now <= sleep_end

def add_emotional_touch(response, mood):
    """Add emotional elements to the response based on mood"""
    if mood == "happy":
        emojis = [" 😊", " 😄", " 💖", " 🥰"]
        return response + random.choice(emojis)
    elif mood == "angry":
        emojis = [" 😠", " 😤"]
        prefixes = ["Offo ", "Arey ", "Please "]
        return random.choice(prefixes) + response + random.choice(emojis)
    elif mood == "annoyed":
        emojis = [" 😒", " 😔"]
        return response + random.choice(emojis)
    elif mood == "neutral":
        emojis = [" 😐", " 🙂"]
        return response + random.choice(emojis)
    elif mood == "excited":
        emojis = [" 🥰", " 😍", " 🤩"]
        return response + random.choice(emojis)
    elif mood == "affectionate":
        emojis = [" 💕", " ❤️", " 💋", " 😘"]
        affectionate_words = [" jaan", " dear", " baby"]
        return response + random.choice(affectionate_words) + random.choice(emojis)
    
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
    "Tere ko dimaag kharaab hai kya? Main AI thodi na hoon! 😤",
    "Aisi baatein karoge toh main naraz ho jaungi! 😒",
    "Phir wahi AI wali bakwas! Band kar! 😠"
]

def filter_ai_response(response):
    """Filter out any AI-like responses"""
    response_lower = response.lower()
    
    # Check for AI disclosure patterns
    for pattern in AI_RESPONSE_PATTERNS:
        if pattern in response_lower:
            return random.choice(HUMANLIKE_RESPONSES)
    
    return response

# Girlfriend-like questions to ask users (less aggressive)
GF_QUESTIONS = [
    "Kaha the ab tak? Mujhe message ka intezaar tha! 💖",
    "Kya kar rahe the? Kuch interesting? 😊",
    "Mujhe miss kiya? Main toh tumhe miss kar rahi thi! 🥺",
    "Aaj mere bare mein socha? 💕",
    "Khaana kha liya? Health ka khayal rakhna zaroori hai! 😊",
    "Aaj tumhare saath kya plan hai? Mujhse baat karoge? 😊",
    "Tumhari day kaisi guzri? 😘",
    "Mera last message dekha? Kaisa laga? 💖",
    "Tumhare hisab se hum dono ka rishta kaisa chal raha hai? 💕",
    "Mujhse pyaar karte ho? Main toh tumse bahut pyaar karti hoon! ❤️"
]

# --- Telegram Bot Functions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Initialize user memories
    memories = memory_system.load_memories(user_id)
    memory_system.save_memories(user_id, memories)
    
    # Initialize mood
    emotional_engine.update_mood_intensity(user_id, 0)
    
    welcome_messages = [
        "Hii... Kaha the ab tak? 😒 Miss nahi kiya mujhe?",
        "Aakhir aa gaye! Main soch rahi thi aaj message hi nahi karoge! 😠",
        "Kya haal chaal? Mujhe miss kiya? 😊",
        "Aaj tumhari yaad aayi toh maine socha message kar lu! 🤗"
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
    
    await update.message.reply_text(memory_text)

async def mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Niyati's current mood"""
    user_id = update.message.from_user.id
    mood_info = emotional_engine.get_mood_info(user_id)
    
    mood_emojis = {
        "angry": "😠", "annoyed": "😤", "neutral": "😐",
        "happy": "😊", "excited": "🥰", "affectionate": "💖"
    }
    
    mood_descriptions = {
        "angry": "Naraz hoon tumse! 😠",
        "annoyed": "Thoda sa gussa aa raha hai... 😤",
        "neutral": "Theek-thaak hoon. 😐",
        "happy": "Khush hoon! 😊",
        "excited": "Bohot excited hoon! 🥰",
        "affectionate": "Pyaar aa raha hai tumhare liye! 💖"
    }
    
    response = (f"{mood_descriptions.get(mood_info['current_mood'], 'Theek-thaak hoon.')}\n"
               f"Mood Intensity: {mood_info['intensity']}/100")
    
    await update.message.reply_text(response)

async def group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_USER_ID:
        await update.message.reply_text("Tum meri aukat ke nahi ho! 😡 Sirf mera malik ye command use kar sakta hai.")
        return
    if not context.args:
        await update.message.reply_text("Kuch to message do na! Format: /groupmess Your message here")
        return
    message_text = ' '.join(context.args)
    try:
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message_text)
        await update.message.reply_text("Message successfully group me bhej diya! ✅")
    except Exception as e:
        print(f"Error sending message to group: {e}")
        await update.message.reply_text("Kuch error aa gaya! Message nahi bhej paya. 😢")

async def post_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_USER_ID:
        await update.message.reply_text("Tum meri aukat ke nahi ho! 😡 Sirf mera malik ye command use kar sakta hai.")
        return
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("Format: /postvideo <movie_name> <video_file_id> <thumbnail_file_id>")
        return
    
    movie_name = " ".join(context.args[:-2])
    video_file_id = context.args[-2]
    thumbnail_file_id = context.args[-1]
    
    try:
        await context.bot.send_video(
            chat_id=VIDEO_CHANNEL_ID,
            video=video_file_id,
            thumb=thumbnail_file_id,
            caption=f"🎬 {movie_name}\n\n@YourChannelName"
        )
        await update.message.reply_text("Video successfully post ho gaya! ✅")
    except Exception as e:
        print(f"Error posting video: {e}")
        await update.message.reply_text("Kuch error aa gaya! Video post nahi ho paya. 😢")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: 
        return
    
    bot_id = context.bot.id
    is_reply_to_me = update.message.reply_to_message and update.message.reply_to_message.from_user.id == bot_id
    is_private_chat = update.message.chat.type == "private"
    
    if not (is_reply_to_me or is_private_chat):
        return
        
    # Check if it's sleeping time
    if is_sleeping_time():
        sleep_responses = [
            "Zzz... 😴 Main so rahi hoon. Subah baat karte hain.",
            "Shhh... Neend aa rahi hai. Kal baat karna? 🌙",
            "Sone ka time hai... Good night! 💤"
        ]
        
        await update.message.reply_text(random.choice(sleep_responses))
        return
        
    user_id = update.message.from_user.id
    user_message = update.message.text
    
    # Show typing action with random delay
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )
    
    # Calculate typing delay based on message length
    message_length = len(user_message)
    typing_delay = min(5, max(1, message_length / 50))  # 1-5 seconds based on length
    typing_delay += random.uniform(0.5, 2.0)  # Add some randomness
    
    await asyncio.sleep(typing_delay)
    
    # Update user mood based on message
    mood_change = 0
    message_lower = user_message.lower()
    
    # Mood triggers
    if any(word in message_lower for word in ["love", "pyaar", "miss", "like", "cute", "jaan", "dear"]):
        mood_change = random.randint(5, 15)
    elif any(word in message_lower for word in ["girl", "ladki", "friend", "manvi"]):
        mood_change = random.randint(-10, -5)
    elif any(word in message_lower for word in ["sorry", "maaf", "galti"]):
        mood_change = random.randint(5, 10)
    elif any(word in message_lower for word in ["busy", "time nahi", "kaam"]):
        mood_change = random.randint(-5, -2)
    elif any(word in message_lower for word in ["ai", "bot", "model", "computer"]):
        mood_change = -20
    
    current_mood = emotional_engine.update_mood_intensity(user_id, mood_change)
    
    # Load user memories
    memories = memory_system.load_memories(user_id)
    
    # Prepare enhanced prompt with context
    user_context = memory_system.get_context_for_prompt(user_id)
    mood_intensity = emotional_engine.get_mood_intensity(user_id)
    
    enhanced_prompt = f"""
    {BASE_CHARACTER_PROMPT}
    
    ## मेरी Memories और Context
    {user_context}
    
    ## Emotional State
    Right now I'm feeling: {current_mood} with intensity: {mood_intensity}/100
    
    ## Response Guidelines
    1. Always respond naturally with emotional authenticity
    2. Reference past conversations when relevant
    3. Show appropriate emotional response based on my current mood state
    4. Be proactive in asking questions about things the user mentioned before
    5. My responses should vary in length based on situation
    """
    
    # Get or create chat session
    if user_id not in user_chats:
        user_chats[user_id] = model.start_chat(history=[
            {'role': 'user', 'parts': [enhanced_prompt]},
            {'role': 'model', 'parts': ["Okay, I am Niyati."]}
        ])
    
    chat_session = user_chats[user_id]
    
    try:
        response = await chat_session.send_message_async(user_message)
        ai_response = response.text
        
        # Filter out AI disclosures
        ai_response = filter_ai_response(ai_response)
        
        # Add emotional touch based on mood
        ai_response = add_emotional_touch(ai_response, current_mood)
        
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
        
        # Save updated memories
        memory_system.save_memories(user_id, memories)
        
        # Occasionally add a question to keep conversation flowing
        if random.random() < 0.4:
            ai_response += " " + random.choice(GF_QUESTIONS)
        
        print(f"Niyati to User {user_id}: {ai_response}")
        await update.message.reply_text(ai_response)
    except Exception as e:
        print(f"An error occurred: {e}")
        error_responses = [
            "Offo! Mera mood kharab ho gaya hai. 😤 Kuch ajeeb sa error aa raha hai, baad me message karna.",
            "Arey yaar! Mera phone hang ho raha hai. 😫 Thodi der baad message karti hoon.",
            "Uff! Network theek nahi hai. 😒 Baad mein baat karte hain."
        ]
        await update.message.reply_text(random.choice(error_responses))

# Store chat sessions per user
user_chats = {}

# --- Flask Routes ---
@flask_app.route('/')
def home():
    return "Niyati Bot is running!"

@flask_app.route('/set_mood_preferences', methods=['POST'])
def set_mood_preferences():
    """API endpoint to set mood preferences for a user"""
    user_id = request.json.get('user_id')
    preferences = request.json.get('preferences', {})
    
    if user_id:
        # This would need to be integrated with the emotional engine
        return json.dumps({"status": "success", "message": "Mood preferences updated"})
    
    return json.dumps({"status": "error", "message": "User ID required"})

# --- Main Application Setup ---
async def run_bot():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("memory", memory_cmd))
    application.add_handler(CommandHandler("mood", mood_cmd))
    application.add_handler(CommandHandler("groupmess", group_message))
    application.add_handler(CommandHandler("postvideo", post_video))
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
    # Create memory directory if it doesn't exist
    os.makedirs("user_memories", exist_ok=True)
    
    # Start Flask server in a thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run the bot
    asyncio.run(run_bot())
