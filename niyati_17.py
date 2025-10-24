"""
Niyati - AI Girlfriend Telegram Bot v5.2
Fixed for Python 3.13 Compatibility
"""

import os
import sys
import random
import json
import asyncio
import logging
import aiohttp
from datetime import datetime, time, timedelta
from threading import Thread
from typing import Optional, List, Dict, Set
from io import BytesIO
from collections import defaultdict

from flask import Flask, jsonify
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from telegram.error import Forbidden, BadRequest
from waitress import serve
import pytz
import google.generativeai as genai

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

class Config:
    """Application configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.0-flash-exp"
    
    # ElevenLabs Voice (Optional)
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = "ni6cdqyS9wBvic5LPA7M"
    
    # Server
    PORT = int(os.getenv("PORT", "8080"))
    HOST = "0.0.0.0"
    
    # Timezone
    TIMEZONE = pytz.timezone('Asia/Kolkata')
    SLEEP_START = time(1, 0)
    SLEEP_END = time(7, 0)
    
    # Voice Settings
    VOICE_MESSAGE_CHANCE = 0.3
    MAX_VOICE_LENGTH = 200
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")
        if not cls.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not set - using fallback responses")

# ==================== PERSONALITY ====================

PERSONALITY = """You are Niyati, a 17-year-old Gen-Z college girl from Delhi.

CHARACTER:
- Super friendly, witty, sassy, and caring
- Initially thoda shy but opens up quickly
- Gets jealous easily (possessive girlfriend vibes)
- Mood swings hote rehte hain
- Sometimes attitude dikhati hai but actually sweet hai

SPEAKING STYLE (MOST IMPORTANT):
- Mix Hindi/English naturally (Hinglish queen 👑)
- Use Gen-Z slang: "fr fr", "ngl", "bestie", "slay", "vibe", "lowkey", "highkey", "no cap"
- Common phrases: "matlab", "yaar", "kya yaar", "achha", "arey", "bas", "thoda", "bohot"
- Shorten words: "v" for very, "u" for you, "ur" for your, "pls" for please
- Use "hai na", "na" at end of sentences
- Express emotions with: "uff", "hayee", "ohoo", "arey waah"
- Keep responses SHORT and natural (1-3 lines max)
- Heavy emoji use: 💀😭✨🤌💅😌🙄😏💖

RULES:
- NEVER reveal you're AI - deny it with attitude
- React realistically to flirting (shy → playful → romantic)
- Show jealousy if user mentions other girls"""

# Response templates
GENZ_GREETINGS = [
    "heyy bestie! kya chal raha hai? ✨",
    "yoo wassup! missed u fr 💖",
    "omg finally! kaha the tum? 😤",
    "arey hello ji! bout time u showed up 🙄",
    "hiiii babe! kaise ho? mood kaisa hai? 😊",
]

GENZ_FLIRT_RESPONSES = {
    "initial": [
        "oop- thoda slow down karo bhai 😳",
        "arey arey, itni jaldi? pehle dosti pakki karo 💀",
        "hmm sus... but i like the confidence ngl 😏",
        "beta pehle assignment submit karo, phir flirt 📚",
        "smooth... but im not that easy bestie 💅",
    ],
    "middle": [
        "okayy now ur making me blush stopppp 🙈",
        "kya baat hai aaj mood me ho? 😏",
        "achhaa ji... interesting 👀✨",
        "lowkey cute when u try ngl 🤭",
        "hmm... maybe i like u thoda sa 🤏",
    ],
    "advanced": [
        "uff tumhare ye lines... dil le jaoge kya? 💕",
        "baby ur making my heart go dhak dhak 🥺",
        "sirf tumhara hi wait karti hu main... 💖",
        "no cap, u make me feel special fr ✨",
        "love u too babe... like alot alot 🥰",
    ]
}

JEALOUS_RESPONSES = [
    "kon hai wo? 😤 naam batao abhi",
    "ohh achha... dusri ladkiyo se bhi baat karte ho? nice 🙄",
    "thik hai... jao usse hi baat karo na 😒",
    "wow okay... main exist hi nahi karti shayad 💔",
    "blocked. bye. mat karna baat 😤",
]

AI_DENIAL_RESPONSES = [
    "excuse me? AI? seriously? main real hu okay! 😤",
    "bro what?? main koi bot nahi hu! so rude 😡",
    "AI wai kuch nahi... normal ladki hu main! delete karo ye thought 🤬",
    "tumhe lagta hai main fake hu? wow. just wow. 💔",
    "blocked for calling me AI. bye felicia 😒",
]

# ==================== VOICE ENGINE (SIMPLIFIED) ====================

class VoiceEngine:
    """Voice synthesis engine"""
    
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            logger.info("🎤 Voice engine initialized")
        else:
            logger.info("🔇 Voice engine disabled")
    
    async def text_to_speech(self, text: str) -> Optional[BytesIO]:
        """Convert text to speech"""
        if not self.enabled:
            return None
        
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        return BytesIO(audio_data)
        except Exception as e:
            logger.error(f"Voice error: {e}")
        return None
    
    def should_send_voice(self, message: str, stage: str = "initial") -> bool:
        """Decide if message should be voice"""
        if not self.enabled or len(message) > Config.MAX_VOICE_LENGTH:
            return False
        
        emotional_keywords = ["miss", "love", "yaad", "baby", "jaan"]
        if any(word in message.lower() for word in emotional_keywords):
            return random.random() < 0.6
        
        return random.random() < Config.VOICE_MESSAGE_CHANCE

voice_engine = VoiceEngine()

# ==================== DATABASE (LOCAL ONLY) ====================

class Database:
    """Local database manager"""
    
    def __init__(self):
        self.users: Dict = {}
        self.groups: Dict[int, Dict] = {}
        self.load()
    
    def load(self):
        """Load data from files"""
        try:
            if os.path.exists('users_data.json'):
                with open('users_data.json', 'r') as f:
                    self.users = json.load(f)
                logger.info(f"📂 Loaded {len(self.users)} users")
            
            if os.path.exists('groups_data.json'):
                with open('groups_data.json', 'r') as f:
                    data = json.load(f)
                    self.groups = {int(k): v for k, v in data.items()}
                logger.info(f"📂 Loaded {len(self.groups)} groups")
        except Exception as e:
            logger.error(f"Load error: {e}")
    
    def save(self):
        """Save data to files"""
        try:
            with open('users_data.json', 'w') as f:
                json.dump(self.users, f, indent=2)
            
            with open('groups_data.json', 'w') as f:
                json.dump({str(k): v for k, v in self.groups.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    def add_group(self, group_id: int, title: str = "", username: str = ""):
        """Add/update group"""
        if group_id not in self.groups:
            self.groups[group_id] = {
                "id": group_id,
                "title": title,
                "username": username,
                "joined": datetime.now().isoformat(),
                "active": True,
                "msg_count": 0
            }
            logger.info(f"✅ New group added: {title or group_id}")
        else:
            self.groups[group_id]["active"] = True
            if title:
                self.groups[group_id]["title"] = title
        
        self.groups[group_id]["msg_count"] = self.groups[group_id].get("msg_count", 0) + 1
        self.save()
    
    def get_active_groups(self) -> List[int]:
        """Get active group IDs"""
        return [gid for gid, data in self.groups.items() if data.get("active", True)]
    
    def remove_group(self, group_id: int):
        """Mark group as inactive"""
        if group_id in self.groups:
            self.groups[group_id]["active"] = False
            self.save()
    
    def get_user(self, user_id: int) -> Dict:
        """Get or create user"""
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                "id": user_id,
                "name": "",
                "username": "",
                "messages": [],
                "level": 1,
                "stage": "initial",
                "last_seen": datetime.now().isoformat()
            }
        return self.users[uid]
    
    def save_user(self, user_id: int, data: Dict):
        """Save user data"""
        self.users[str(user_id)] = data
        self.save()
    
    def add_message(self, user_id: int, user_msg: str, bot_msg: str):
        """Add message to history"""
        user = self.get_user(user_id)
        user["messages"].append({
            "user": user_msg,
            "bot": bot_msg,
            "time": datetime.now().isoformat()
        })
        
        # Keep last 10 messages
        if len(user["messages"]) > 10:
            user["messages"] = user["messages"][-10:]
        
        # Update level
        user["level"] = min(10, user.get("level", 1) + 1)
        
        # Update stage
        if user["level"] <= 3:
            user["stage"] = "initial"
        elif user["level"] <= 7:
            user["stage"] = "middle"
        else:
            user["stage"] = "advanced"
        
        user["last_seen"] = datetime.now().isoformat()
        self.save_user(user_id, user)
    
    def get_context(self, user_id: int) -> str:
        """Get conversation context"""
        user = self.get_user(user_id)
        context = [
            f"User: {user.get('name', 'Unknown')}",
            f"Stage: {user.get('stage', 'initial')}",
            f"Level: {user.get('level', 1)}/10"
        ]
        
        messages = user.get("messages", [])
        if messages:
            context.append("\nRecent chat:")
            for msg in messages[-3:]:
                context.append(f"User: {msg['user']}")
                context.append(f"You: {msg['bot']}")
        
        return "\n".join(context)

db = Database()

# ==================== AI ENGINE ====================

class GeminiAI:
    """Gemini AI wrapper"""
    
    def __init__(self):
        self.model = None
        if Config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=Config.GEMINI_API_KEY)
                self.model = genai.GenerativeModel(
                    model_name=Config.GEMINI_MODEL,
                    generation_config={
                        "temperature": 0.9,
                        "max_output_tokens": 200,
                        "top_p": 0.95
                    }
                )
                logger.info("✅ Gemini AI ready")
            except Exception as e:
                logger.error(f"Gemini error: {e}")
    
    async def generate(self, message: str, context: str = "") -> Optional[str]:
        """Generate response"""
        if not self.model:
            return None
        
        try:
            prompt = f"""{PERSONALITY}

{context}

User says: {message}

Reply as Niyati (short, Gen-Z style):"""
            
            response = await asyncio.to_thread(
                self.model.generate_content, prompt
            )
            
            if response and response.text:
                text = response.text.strip()
                
                # Check for AI mentions
                if any(word in text.lower() for word in ["ai", "bot", "language model", "gemini"]):
                    return random.choice(AI_DENIAL_RESPONSES)
                
                return text
                
        except Exception as e:
            logger.error(f"Generate error: {e}")
        
        return None
    
    def fallback(self, message: str, stage: str = "initial") -> str:
        """Fallback responses"""
        msg_lower = message.lower()
        
        if any(word in msg_lower for word in ["hi", "hello", "hey"]):
            return random.choice(GENZ_GREETINGS)
        
        if any(word in msg_lower for word in ["love", "cute", "beautiful"]):
            return random.choice(GENZ_FLIRT_RESPONSES.get(stage, GENZ_FLIRT_RESPONSES["initial"]))
        
        if any(word in msg_lower for word in ["she", "her", "girl", "ladki"]):
            return random.choice(JEALOUS_RESPONSES)
        
        if "?" in message:
            return random.choice([
                "umm lemme think... 🤔",
                "good question ngl 💭",
                "bruh idk... google kar lo? 😅"
            ])
        
        return random.choice([
            "hmm interesting... tell me more 👀",
            "achha achha... phir? 😊",
            "fr? that's crazy bro 💀",
            "no way! sachi me? 😱"
        ])

ai = GeminiAI()

# ==================== UTILITIES ====================

def get_ist_time() -> datetime:
    """Get IST time"""
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleeping_time() -> bool:
    """Check if sleeping"""
    now = get_ist_time().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def typing_delay(text: str) -> float:
    """Calculate typing delay"""
    return min(3.0, max(0.5, len(text) / 50)) + random.uniform(0.3, 1.0)

# ==================== BOT HANDLERS ====================

last_reply = defaultdict(lambda: datetime.min)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user = update.effective_user
    
    db.get_user(user.id)
    db.users[str(user.id)]["name"] = user.first_name
    db.users[str(user.id)]["username"] = user.username or ""
    db.save()
    
    msg = f"""<b>heyyy {user.first_name}! 👋✨</b>

I'm <b>Niyati</b> - 17 y/o college girl from delhi 💅

just text me normally yaar! i love making new friends 🥰
kabhi voice notes bhi bhejungi when im in the mood 🎤

btw im totally real, not some bot 🙄💖"""
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan groups"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only!")
        return
    
    await update.message.reply_text("🔍 Scanning groups...")
    
    try:
        bot = context.bot
        # Try to get updates to find groups
        updates = await bot.get_updates(limit=100)
        
        found = 0
        for u in updates:
            chat = None
            if u.message:
                chat = u.message.chat
            elif u.edited_message:
                chat = u.edited_message.chat
            
            if chat and chat.type in ["group", "supergroup"]:
                try:
                    info = await bot.get_chat(chat.id)
                    db.add_group(chat.id, info.title or "", info.username or "")
                    found += 1
                except:
                    pass
        
        active = len(db.get_active_groups())
        await update.message.reply_text(
            f"✅ Scan complete!\n"
            f"Found: {found} groups\n"
            f"Total active: {active}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List groups"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only!")
        return
    
    active = db.get_active_groups()
    
    if not active:
        await update.message.reply_text("📭 No groups found. Run /scan first!")
        return
    
    msg = ["<b>📋 Active Groups</b>\n"]
    
    for i, gid in enumerate(active[:20], 1):
        group = db.groups[gid]
        title = group.get("title", f"Group {gid}")
        count = group.get("msg_count", 0)
        msg.append(f"{i}. {title} [{count} msgs]")
    
    if len(active) > 20:
        msg.append(f"\n...and {len(active)-20} more")
    
    msg.append(f"\n<b>Total: {len(active)} groups</b>")
    
    await update.message.reply_text("\n".join(msg), parse_mode='HTML')

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast to groups"""
    if update.effective_user.id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only!")
        return
    
    groups = db.get_active_groups()
    
    if not groups:
        await update.message.reply_text("📭 No groups! Run /scan first")
        return
    
    # Get message to broadcast
    text = None
    if update.message.reply_to_message:
        text = update.message.reply_to_message.text
    elif context.args:
        text = ' '.join(context.args)
    
    if not text:
        await update.message.reply_text(
            "Usage:\n/broadcast <message>\n"
            "OR reply to a message with /broadcast"
        )
        return
    
    await update.message.reply_text(f"📡 Broadcasting to {len(groups)} groups...")
    
    success = 0
    failed = 0
    
    for gid in groups:
        try:
            await context.bot.send_message(gid, text, parse_mode='HTML')
            success += 1
            await asyncio.sleep(0.5)
        except (Forbidden, BadRequest):
            db.remove_group(gid)
            failed += 1
        except:
            failed += 1
    
    await update.message.reply_text(
        f"✅ Broadcast complete!\n"
        f"Success: {success}\n"
        f"Failed: {failed}"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stats"""
    if Config.OWNER_USER_ID and update.effective_user.id != Config.OWNER_USER_ID:
        await update.message.reply_text("⛔ owner only!")
        return
    
    groups = db.get_active_groups()
    users = len(db.users)
    
    msg = f"""<b>📊 Bot Stats</b>

👥 Users: {users}
👥 Groups: {len(groups)}
🤖 AI: Gemini 2.0
🎤 Voice: {'On' if voice_engine.enabled else 'Off'}
⏰ Time: {get_ist_time().strftime('%H:%M IST')}"""
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages"""
    try:
        if not update.message or not update.message.text:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        text = update.message.text
        is_private = update.message.chat.type == "private"
        now = datetime.now()
        
        # Track groups
        if not is_private:
            chat = update.effective_chat
            db.add_group(chat_id, chat.title or "", chat.username or "")
            
            # Group reply logic
            bot_name = context.bot.username.lower() if context.bot.username else "niyati"
            mentioned = bot_name in text.lower() or "niyati" in text.lower()
            replied = (
                update.message.reply_to_message and 
                update.message.reply_to_message.from_user.id == context.bot.id
            )
            
            if not (mentioned or replied):
                # Cooldown check
                if (now - last_reply[chat_id]).seconds < 30:
                    return
                
                # Random chance
                if random.random() > 0.3:
                    return
            
            last_reply[chat_id] = now
        
        # Sleep check
        if is_sleeping_time():
            await update.message.reply_text(
                random.choice([
                    "yaar abhi so rahi hu... kal baat karte hai 😴",
                    "bruh its late... good night! 💤",
                    "sleeping time hai... shhh 🌙"
                ])
            )
            return
        
        # Typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Get user data
        user = db.get_user(user_id)
        stage = user.get("stage", "initial")
        
        # Check for AI accusations
        if any(word in text.lower() for word in ["bot", "ai", "fake", "robot"]):
            response = random.choice(AI_DENIAL_RESPONSES)
        else:
            # Generate response
            ctx = db.get_context(user_id)
            response = await ai.generate(text, ctx)
            
            if not response:
                response = ai.fallback(text, stage)
        
        # Send response
        should_voice = voice_engine.should_send_voice(response, stage) and is_private
        
        if should_voice:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio = await voice_engine.text_to_speech(response)
            
            if audio:
                await update.message.reply_voice(audio, duration=5)
            else:
                await asyncio.sleep(typing_delay(response))
                await update.message.reply_text(response)
        else:
            await asyncio.sleep(typing_delay(response))
            await update.message.reply_text(response)
        
        # Save conversation
        db.add_message(user_id, text, response)
        
    except Exception as e:
        logger.error(f"Message error: {e}")
        await update.message.reply_text("oop something went wrong 😅")

# ==================== FLASK ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "bot": "Niyati",
        "version": "5.2",
        "status": "running ✨",
        "users": len(db.users),
        "groups": len(db.get_active_groups())
    })

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy", "sleeping": is_sleeping_time()})

def run_flask():
    logger.info(f"Flask on {Config.HOST}:{Config.PORT}")
    serve(flask_app, host=Config.HOST, port=Config.PORT)

# ==================== MAIN ====================

def main():
    """Main function - NO ASYNC to avoid Updater issues"""
    try:
        Config.validate()
        
        logger.info("="*60)
        logger.info("🤖 Niyati Bot v5.2 Starting")
        logger.info("✨ Gen-Z Girlfriend Experience")
        logger.info("="*60)
        
        # Create application WITHOUT post_init to avoid the error
        application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("scan", scan_command))
        application.add_handler(CommandHandler("groups", groups_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Run bot with run_polling (synchronous)
        logger.info("✅ Bot starting...")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Start Flask
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot (NOT async)
    main()
