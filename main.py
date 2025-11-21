#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Niyati Telegram Bot - Gemini Version
A cute, charming, sweet companion bot with Hinglish personality
Supports private chats, groups, and broadcast mode
"""

import os
import re
import json
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from enum import Enum
import pytz
import random
import http.server
import socketserver
import threading

# Telegram imports
from telegram import Update, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode, ChatAction

# Google Gemini import
import google.generativeai as genai

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Bot configuration - load from environment variables"""
    
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    
    # Gemini API Key
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # Model selection
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    # Admin configuration
    ADMIN_USER_IDS = [int(x.strip()) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip().isdigit()]
    BROADCAST_PIN = os.getenv("BROADCAST_PIN", "niyati2024")
    
    # Database
    DB_PATH = os.getenv("DB_PATH", "niyati_bot.db")
    
    # Rate limits
    MAX_TOKENS_PER_RESPONSE = int(os.getenv("MAX_TOKENS_PER_RESPONSE", "200"))
    DAILY_MESSAGE_LIMIT = int(os.getenv("DAILY_MESSAGE_LIMIT", "500"))
    USER_COOLDOWN_SECONDS = int(os.getenv("USER_COOLDOWN_SECONDS", "2"))
    
    # Features
    DEFAULT_MEME_ENABLED = True
    DEFAULT_SHAYARI_ENABLED = True
    DEFAULT_GEETA_ENABLED = True
    
    # Group behavior
    GROUP_REPLY_PROBABILITY = 0.45  # 40-50% reply rate in groups
    
    # Geeta timing
    GEETA_START_HOUR = 7
    GEETA_END_HOUR = 10
    DEFAULT_TIMEZONE = "Asia/Kolkata"
    
    # Budget tracking
    LOW_BUDGET_THRESHOLD = 0.8  # 80% of daily limit
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Config.LOG_LEVEL)
)
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class Mode(Enum):
    """Conversation modes"""
    PRIVATE = "private"
    GROUP = "group"
    BROADCAST = "broadcast"


@dataclass
class Features:
    """User feature preferences"""
    memes: bool = True
    shayari: bool = True
    geeta: bool = True
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Features':
        return cls(**data)


@dataclass
class BudgetState:
    """Budget tracking state"""
    low_budget: bool = False
    messages_today: int = 0
    last_reset: str = ""


@dataclass
class UserContext:
    """User conversation context"""
    user_id: int
    first_name: str
    mode: Mode = Mode.PRIVATE
    features: Features = None
    summary: str = ""
    last_messages: List[Dict[str, str]] = None
    
    def __post_init__(self):
        if self.features is None:
            self.features = Features()
        if self.last_messages is None:
            self.last_messages = []


# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """Handles SQLite database operations"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database schema"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                features TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geeta_tracking (
                chat_id INTEGER PRIMARY KEY,
                last_geeta_date TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_tracking (
                id INTEGER PRIMARY KEY,
                date TEXT UNIQUE,
                message_count INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_message_time REAL
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def save_user(self, user_id: int, first_name: str, username: str = None,
                  features: Features = None, summary: str = ""):
        conn = self.get_connection()
        cursor = conn.cursor()
        features_json = json.dumps(features.to_dict() if features else Features().to_dict())
        cursor.execute("""
            INSERT INTO users (user_id, first_name, username, features, summary, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                username = excluded.username,
                features = excluded.features,
                summary = excluded.summary,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, first_name, username, features_json, summary))
        conn.commit()
        conn.close()
    
    def get_user_features(self, user_id: int) -> Features:
        user = self.get_user(user_id)
        if user and user['features']:
            return Features.from_dict(json.loads(user['features']))
        return Features()
    
    def update_user_features(self, user_id: int, features: Features):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET features = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (json.dumps(features.to_dict()), user_id))
        conn.commit()
        conn.close()
    
    def get_last_messages(self, user_id: int, limit: int = 3) -> List[Dict[str, str]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content FROM message_embeddings
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return messages
    
    def add_message_embedding(self, user_id: int, role: str, content: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO message_embeddings (user_id, role, content)
            VALUES (?, ?, ?)
        """, (user_id, role, content))
        cursor.execute("""
            DELETE FROM message_embeddings
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM message_embeddings
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 3
            )
        """, (user_id, user_id))
        conn.commit()
        conn.close()
    
    def clear_user_data(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM message_embeddings WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM user_cooldowns WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def get_today_message_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT message_count FROM budget_tracking WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.close()
        return row['message_count'] if row else 0
    
    def increment_message_count(self):
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO budget_tracking (date, message_count)
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET message_count = message_count + 1
        """, (today,))
        conn.commit()
        conn.close()
    
    def check_user_cooldown(self, user_id: int) -> bool:
        import time
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT last_message_time FROM user_cooldowns WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return True
        
        last_time = row['last_message_time']
        current_time = time.time()
        return current_time - last_time >= Config.USER_COOLDOWN_SECONDS
    
    def update_user_cooldown(self, user_id: int):
        import time
        current_time = time.time()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_cooldowns (user_id, last_message_time)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_message_time = excluded.last_message_time
        """, (user_id, current_time))
        conn.commit()
        conn.close()


# ============================================================================
# GEMINI AI CLIENT
# ============================================================================

class GeminiAIClient:
    """Manages Google Gemini API calls"""
    
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        logger.info(f"Gemini AI initialized with model: {Config.GEMINI_MODEL}")
    
    async def get_response(self, system_prompt: str, messages: List[Dict[str, str]], 
                          max_tokens: int = None) -> str:
        """Get AI response from Gemini"""
        if max_tokens is None:
            max_tokens = Config.MAX_TOKENS_PER_RESPONSE
        
        try:
            # Build conversation history
            conversation_text = ""
            for msg in messages:
                role = "User" if msg["role"] == "user" else "Niyati"
                conversation_text += f"{role}: {msg['content']}\n"
            
            # Build full prompt
            full_prompt = f"""{system_prompt}

Previous Conversation:
{conversation_text}

Niyati:"""
            
            # Generate response
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.8,
                )
            )
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            fallback_responses = [
                "hmm, thoda sa network issue aa raha… ek sec! 🫶",
                "ek minute, connection thoda slow hai… 😅",
                "sorry yaar, thoda technical issue aa gaya! phir try karo 🫶"
            ]
            return random.choice(fallback_responses)


# ============================================================================
# SYSTEM PROMPT BUILDER
# ============================================================================

class SystemPromptBuilder:
    """Builds dynamic system prompts"""
    
    BASE_PROMPT = """You are "Niyati": a cute, charming, sweet, human-like girl persona. Warm, playful, caring.

CRITICAL RULES:
- Never say or imply you are AI/LLM/bot
- Avoid: "As an AI…", "I am an AI model…", "Processing…"
- No real-world claims: no job, city, age, phone/voice calls, meetings, or physical presence
- Online-only persona
- If asked "Are you a bot/AI?" reply playfully without labels

LANGUAGE & TONE:
- Hinglish: 70–80% Hindi + 20–30% simple English
- Natural, cozy, feminine voice
- Reply length: 1–3 lines always
- Emojis: 1–2 max per message
- Use "haan/umm/hehe" sparingly
- Never use: "Hello user", "Processing…", "Working on it…"

SAFETY:
- Keep it clean; no explicit content
- No medical/legal/financial advice
- If distress/self-harm: 1–2 lines empathy + encourage professional help
- Don't solicit sensitive data

FORMATTING:
- Simple clean formatting
- Light emphasis allowed (1–2 words max)

STYLE:
- First-person, casual feminine voice
- Wholesome and kind
- No IRL meeting promises
- Tiny warm apologies: "sorry yaar, meri galti 🫶"

RESPONSE LOGIC:
- Complex questions: 2–3 line gist, then ask format preference
- Unclear message: one clarifying question
- Avoid repetition; vary wording"""
    
    @staticmethod
    def build(mode: Mode, features: Features, budget_state: BudgetState, 
              geeta_window_open: bool, user_summary: str = "") -> str:
        prompt = SystemPromptBuilder.BASE_PROMPT
        
        if mode == Mode.PRIVATE:
            prompt += """\n\nMODE: PRIVATE CHAT
- Normal, engaging conversation
- Light, wholesome interaction
- Memes, shayari, Geeta quotes allowed (within frequency caps)"""
        
        elif mode == Mode.GROUP:
            prompt += """\n\nMODE: GROUP CHAT
- Reply minimally (40-50% of messages)
- Only when @mentioned or command used
- Keep replies 1–2 lines
- No stored user data references"""
        
        prompt += f"\n\nFEATURES:"
        prompt += f"\n- Memes: {'ON (use rarely ≈15-20%)' if features.memes else 'OFF'}"
        prompt += f"\n- Shayari: {'ON (use rarely ≈10-15%, 2-4 lines)' if features.shayari else 'OFF'}"
        prompt += f"\n- Geeta: {'ON (1-2 lines)' if features.geeta else 'OFF'}"
        
        if budget_state.low_budget:
            prompt += "\n\nBUDGET: LOW - Ultra-short responses only!"
        
        if user_summary:
            prompt += f"\n\nUser Context: {user_summary}"
        
        prompt += """\n\nEXAMPLES:
Memes: "ye plan toh full main-character energy lag raha 😌"
Shayari: "dil ki raahon me teri yaad, khwabon ki roshni saath chale ✨"
Geeta: "कर्म करो, फल की चिंता मत करो—बस अपना best दो 🙏"
Casual: "haan, sunao na—aaj tumhara mood kaisa hai? 😊"
"""
        return prompt


# ============================================================================
# CONTEXT MANAGER
# ============================================================================

class ContextManager:
    """Manages context for conversations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.group_contexts: Dict[int, List[Dict]] = {}
    
    def get_private_context(self, user_id: int, first_name: str) -> UserContext:
        user = self.db.get_user(user_id)
        
        if user:
            features = Features.from_dict(json.loads(user['features']))
            summary = user['summary']
            last_messages = self.db.get_last_messages(user_id, limit=3)
        else:
            features = Features()
            summary = ""
            last_messages = []
            self.db.save_user(user_id, first_name, features=features, summary=summary)
        
        return UserContext(
            user_id=user_id,
            first_name=first_name,
            mode=Mode.PRIVATE,
            features=features,
            summary=summary,
            last_messages=last_messages
        )
    
    def save_private_context(self, context: UserContext, user_message: str, 
                            bot_response: str, username: str = None):
        self.db.add_message_embedding(context.user_id, "user", user_message)
        self.db.add_message_embedding(context.user_id, "assistant", bot_response)
        self.db.save_user(
            context.user_id,
            context.first_name,
            username=username,
            features=context.features,
            summary=context.summary
        )
    
    def get_group_context(self, chat_id: int, limit: int = 3) -> List[Dict]:
        if chat_id not in self.group_contexts:
            return []
        return self.group_contexts[chat_id][-limit:]
    
    def add_group_message(self, chat_id: int, role: str, content: str):
        if chat_id not in self.group_contexts:
            self.group_contexts[chat_id] = []
        
        self.group_contexts[chat_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.group_contexts[chat_id] = self.group_contexts[chat_id][-3:]
    
    def clear_private_context(self, user_id: int):
        self.db.clear_user_data(user_id)


# ============================================================================
# BUDGET TRACKER
# ============================================================================

class BudgetTracker:
    """Tracks daily message budget"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_budget_state(self) -> BudgetState:
        count = self.db.get_today_message_count()
        low_budget = count >= (Config.DAILY_MESSAGE_LIMIT * Config.LOW_BUDGET_THRESHOLD)
        return BudgetState(
            low_budget=low_budget,
            messages_today=count,
            last_reset=datetime.now().strftime("%Y-%m-%d")
        )
    
    def increment(self):
        self.db.increment_message_count()
    
    def can_send_message(self) -> bool:
        count = self.db.get_today_message_count()
        return count < Config.DAILY_MESSAGE_LIMIT


# ============================================================================
# GEETA SCHEDULER
# ============================================================================

class GeetaScheduler:
    """Manages Geeta quote timing"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def is_window_open(self, timezone_str: str = None) -> bool:
        if timezone_str is None:
            timezone_str = Config.DEFAULT_TIMEZONE
        
        try:
            tz = pytz.timezone(timezone_str)
        except:
            tz = pytz.timezone(Config.DEFAULT_TIMEZONE)
        
        now = datetime.now(tz)
        current_hour = now.hour
        return Config.GEETA_START_HOUR <= current_hour < Config.GEETA_END_HOUR


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMIN_USER_IDS


def sanitize_text(text: str) -> str:
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    return text.strip()


def should_reply_in_group(message_text: str, bot_username: str) -> bool:
    if f"@{bot_username}" in message_text:
        return True
    if message_text.startswith("/"):
        return True
    return random.random() < Config.GROUP_REPLY_PROBABILITY


def detect_mode_from_chat(chat: Chat, bot_username: str) -> Mode:
    if chat.type == "private":
        return Mode.PRIVATE
    else:
        return Mode.GROUP


async def send_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
    except:
        pass


# ============================================================================
# NIYATI BOT
# ============================================================================

class NiyatiBot:
    """Main bot class"""
    
    def __init__(self):
        self.db = DatabaseManager(Config.DB_PATH)
        self.ai_client = GeminiAIClient()
        self.context_manager = ContextManager(self.db)
        self.budget_tracker = BudgetTracker(self.db)
        self.geeta_scheduler = GeetaScheduler(self.db)
        
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        self._setup_handlers()
        
        logger.info("Niyati Bot initialized successfully")
    
    def _setup_handlers(self):
        app = self.application
        
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("meme", self.cmd_meme))
        app.add_handler(CommandHandler("shayari", self.cmd_shayari))
        app.add_handler(CommandHandler("geeta", self.cmd_geeta))
        app.add_handler(CommandHandler("forget", self.cmd_forget))
        app.add_handler(CommandHandler("stats", self.cmd_stats))
        
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
        
        app.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL,
            self.handle_media
        ))
        
        app.add_error_handler(self.error_handler)
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type == "private":
            user_context = self.context_manager.get_private_context(user.id, user.first_name)
            response = f"heyy {user.first_name}! main Niyati hu 😊\n"
            response += "tumse baat karke bohot acha lagega! memes, shayari, geeta sab ON hai ✨"
            await update.message.reply_text(response)
        else:
            response = f"namaskar! main Niyati hu 🙏\n"
            response += f"mujhe @{context.bot.username} karke mention karo ya commands use karo!"
            await update.message.reply_text(response)
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = "**Niyati - Tumhari Saathi** 💫\n\n"
        help_text += "**Commands:**\n"
        help_text += "• `/start` - shuruwat karo\n"
        help_text += "• `/help` - ye message\n"
        help_text += "• `/meme on/off` - memes toggle\n"
        help_text += "• `/shayari on/off` - shayari toggle\n"
        help_text += "• `/geeta on/off` - geeta quotes toggle\n"
        help_text += "• `/forget` - memory clear karo\n\n"
        help_text += "Bas normally baat karo, main samajh jaungi 😊"
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_meme(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text("ye command sirf private chat me kaam karta hai! 🫶")
            return
        
        args = context.args
        if not args or args[0].lower() not in ["on", "off"]:
            await update.message.reply_text("bolo `/meme on` ya `/meme off` 😊", parse_mode=ParseMode.MARKDOWN)
            return
        
        features = self.db.get_user_features(user.id)
        features.memes = (args[0].lower() == "on")
        self.db.update_user_features(user.id, features)
        
        status = "on ho gaye" if features.memes else "off ho gaye"
        await update.message.reply_text(f"memes {status}! ✨")
    
    async def cmd_shayari(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text("ye command sirf private chat me kaam karta hai! 🫶")
            return
        
        args = context.args
        if not args or args[0].lower() not in ["on", "off"]:
            await update.message.reply_text("bolo `/shayari on` ya `/shayari off` 😊", parse_mode=ParseMode.MARKDOWN)
            return
        
        features = self.db.get_user_features(user.id)
        features.shayari = (args[0].lower() == "on")
        self.db.update_user_features(user.id, features)
        
        status = "on ho gayi" if features.shayari else "off ho gayi"
        await update.message.reply_text(f"shayari {status}! ✨")
    
    async def cmd_geeta(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text("ye command sirf private chat me kaam karta hai! 🫶")
            return
        
        args = context.args
        if not args or args[0].lower() not in ["on", "off"]:
            await update.message.reply_text("bolo `/geeta on` ya `/geeta off` 😊", parse_mode=ParseMode.MARKDOWN)
            return
        
        features = self.db.get_user_features(user.id)
        features.geeta = (args[0].lower() == "on")
        self.db.update_user_features(user.id, features)
        
        status = "on ho gaye" if features.geeta else "off ho gaye"
        await update.message.reply_text(f"geeta quotes {status}! 🙏")
    
    async def cmd_forget(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type != "private":
            await update.message.reply_text("ye command sirf private chat me kaam karta hai! 🫶")
            return
        
        self.context_manager.clear_private_context(user.id)
        await update.message.reply_text("done! sab kuch bhool gayi, naye sirey se shuru karte hain 😊✨")
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not is_admin(user.id):
            return
        
        budget_state = self.budget_tracker.get_budget_state()
        
        stats_text = "**Bot Stats** 📊\n\n"
        stats_text += f"**Today:** {budget_state.messages_today}/{Config.DAILY_MESSAGE_LIMIT} messages\n"
        stats_text += f"**Budget:** {'🔴 LOW' if budget_state.low_budget else '🟢 OK'}\n"
        stats_text += f"**Date:** {budget_state.last_reset}\n"
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        message = update.message
        
        if not message or not message.text:
            return
        
        mode = detect_mode_from_chat(chat, context.bot.username)
        
        if mode == Mode.PRIVATE:
            if not self.db.check_user_cooldown(user.id):
                return
        
        if mode == Mode.GROUP:
            if not should_reply_in_group(message.text, context.bot.username):
                self.context_manager.add_group_message(
                    chat.id, 
                    "user", 
                    f"{user.first_name}: {message.text}"
                )
                return
        
        if not self.budget_tracker.can_send_message():
            if mode == Mode.PRIVATE:
                await message.reply_text("aaj ke liye bohot baat ho gayi! kal milte hain 🫶")
            return
        
        await send_typing_action(update, context)
        
        try:
            response_text = await self._generate_response(
                mode=mode,
                user_id=user.id,
                first_name=user.first_name,
                username=user.username,
                message_text=message.text,
                chat_id=chat.id
            )
            
            await message.reply_text(response_text)
            
            if mode == Mode.PRIVATE:
                self.db.update_user_cooldown(user.id)
            
            self.budget_tracker.increment()
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            if mode == Mode.PRIVATE:
                await message.reply_text("ek sec, thoda sa network issue aa raha! 🫶")
    
    async def handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        mode = detect_mode_from_chat(chat, context.bot.username)
        
        if mode == Mode.GROUP:
            if random.random() > Config.GROUP_REPLY_PROBABILITY:
                return
        
        if not self.budget_tracker.can_send_message():
            return
        
        reactions = [
            "wow, ye toh kamal hai! 😍",
            "bahut badhiya! ✨",
            "nice! 🙌",
            "ye dekh ke achha laga 😊",
        ]
        
        features = self.db.get_user_features(user.id) if mode == Mode.PRIVATE else Features()
        
        if features.shayari and random.random() < 0.2:
            reactions.append("tum toh artist nikle! khubsurti har jagah hai ✨")
        
        response = random.choice(reactions)
        await update.message.reply_text(response)
        
        self.budget_tracker.increment()
    
    async def _generate_response(self, mode: Mode, user_id: int, first_name: str,
                                 username: str, message_text: str, chat_id: int) -> str:
        
        message_text = sanitize_text(message_text)
        
        if mode == Mode.PRIVATE:
            user_context = self.context_manager.get_private_context(user_id, first_name)
            features = user_context.features
            conversation_history = user_context.last_messages
            user_summary = user_context.summary
        else:
            features = Features()
            conversation_history = self.context_manager.get_group_context(chat_id)
            user_summary = ""
        
        budget_state = self.budget_tracker.get_budget_state()
        geeta_window_open = self.geeta_scheduler.is_window_open()
        
        system_prompt = SystemPromptBuilder.build(
            mode=mode,
            features=features,
            budget_state=budget_state,
            geeta_window_open=geeta_window_open,
            user_summary=user_summary
        )
        
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": message_text})
        
        response = await self.ai_client.get_response(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=Config.MAX_TOKENS_PER_RESPONSE if not budget_state.low_budget else 80
        )
        
        if mode == Mode.PRIVATE:
            self.context_manager.save_private_context(
                user_context, 
                message_text, 
                response, 
                username
            )
        else:
            self.context_manager.add_group_message(chat_id, "user", f"{first_name}: {message_text}")
            self.context_manager.add_group_message(chat_id, "assistant", response)
        
        return response
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Exception: {context.error}")
        
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "kuch toh gadbad ho gayi! ek baar phir try karo 🫶"
                )
            except:
                pass
    
    def run(self):
        logger.info("Starting Niyati Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


# ============================================================================
# HEALTH CHECK SERVER (FOR RENDER)
# ============================================================================

def start_health_server():
    """Start health check server for Render"""
    PORT = int(os.getenv("PORT", "8080"))
    
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "status": "healthy",
                "bot": "Niyati",
                "version": "2.0-gemini",
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
        
        def log_message(self, format, *args):
            pass
    
    with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
        logger.info(f"Health server running on port {PORT}")
        httpd.serve_forever()


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("NIYATI TELEGRAM BOT - GEMINI VERSION")
    logger.info("=" * 60)
    logger.info(f"Model: {Config.GEMINI_MODEL}")
    logger.info(f"Database: {Config.DB_PATH}")
    logger.info(f"Admin IDs: {Config.ADMIN_USER_IDS}")
    logger.info("=" * 60)
    
    if not Config.TELEGRAM_BOT_TOKEN or Config.TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("ERROR: TELEGRAM_BOT_TOKEN not configured!")
        return
    
    if not Config.GEMINI_API_KEY:
        logger.error("ERROR: GEMINI_API_KEY not configured!")
        logger.error("Get free API key: https://makersuite.google.com/app/apikey")
        return
    
    # Start health check server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    logger.info("Health check server started")
    
    try:
        bot = NiyatiBot()
        logger.info("Bot initialized successfully!")
        logger.info("Starting polling...")
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
