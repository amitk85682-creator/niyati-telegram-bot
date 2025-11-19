# -*- coding: utf-8 -*-

import os
import json
import sqlite3
import re
from datetime import datetime, time, timedelta
from typing import Dict, Optional, List, Tuple
import pytz
from telegram import Update, Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError, RetryAfter
import asyncio
import logging
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold
import random

# ==============================================================================
#  Logging Configuration (लॉगिंग कॉन्फ़िगरेशन)
# ==============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# Environment Variables & Constants (एनवायरनमेंट वेरिएबल्स और स्थिरांक)
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_USER_ID = list(map(int, filter(None, os.getenv("OWNER_USER_ID", "").split(","))))
BROADCAST_PIN = os.getenv("BROADCAST_PIN", "niyati_secret_2025")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TIMEZONE = pytz.timezone('Asia/Kolkata')
BOT_USERNAME = os.getenv("BOT_USERNAME", "Niyati_personal_bot")

# बजट ट्रैकिंग
DAILY_TOKEN_LIMIT = 150000
HOURLY_TOKEN_LIMIT = 10000

# रेट लिमिटिंग
MAX_MESSAGES_PER_MINUTE = 10

# डेटाबेस पाथ
DB_PATH = "niyati_bot.db"

# ==============================================================================
# State Management (स्टेट मैनेजमेंट)
# ==============================================================================
# यह डिक्शनरी बॉट के रनटाइम स्टेट को स्टोर करती हैं
bot_state = {
    'daily_tokens': {'used': 0, 'date': datetime.now(TIMEZONE).date()},
    'hourly_tokens': {'used': 0, 'hour': datetime.now(TIMEZONE).hour},
    'geeta_tracker': {},  # Dict[int, datetime]
    'group_context_cache': {},  # Dict[int, List[Dict]]
    'user_rate_limit': {}  # Dict[int, List[datetime]]
}

# ==============================================================================
# Gemini AI Setup (जेमिनी एआई सेटअप)
# ==============================================================================
# Gemini API को कॉन्फ़िगर करें
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
    logger.info("Gemini AI मॉडल सफलतापूर्वक लोड हो गया।")
except Exception as e:
    logger.error(f"Gemini API को कॉन्फ़िगर करने में विफल: {e}")
    gemini_model = None

# ==============================================================================
# Database Manager Class (डेटाबेस मैनेजर क्लास)
# यह क्लास सभी डेटाबेस ऑपरेशन्स को मैनेज करती है।
# ==============================================================================
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self):
        """एक नया डेटाबेस कनेक्शन लौटाता है।"""
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """डेटाबेस और सभी आवश्यक टेबल बनाता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            # यूजर्स टेबल
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
                    preferences TEXT DEFAULT '{}', conversation_summary TEXT DEFAULT '',
                    total_messages INTEGER DEFAULT 0, created_at TEXT, last_interaction TEXT
                )
            ''')
            # सब्सक्राइबर्स टेबल
            c.execute('''
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id INTEGER PRIMARY KEY, first_name TEXT,
                    subscribed_at TEXT, active INTEGER DEFAULT 1
                )
            ''')
            # एडमिन लॉग्स टेबल
            c.execute('''
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER,
                    action TEXT, details TEXT, timestamp TEXT
                )
            ''')
            # ग्रुप सेटिंग्स टेबल
            c.execute('''
                CREATE TABLE IF NOT EXISTS group_settings (
                    chat_id INTEGER PRIMARY KEY, last_geeta_date TEXT,
                    geeta_enabled INTEGER DEFAULT 1
                )
            ''')
            conn.commit()
        logger.info("डेटाबेस सफलतापूर्वक इनिशियलाइज़ हो गया।")

    def get_user_data(self, user_id: int) -> Optional[Dict]:
        """डेटाबेस से यूजर का डेटा प्राप्त करता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, first_name, username, preferences, conversation_summary, total_messages, created_at, last_interaction FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if row:
                return {
                    'user_id': row[0], 'first_name': row[1], 'username': row[2],
                    'preferences': json.loads(row[3]) if row[3] else {},
                    'conversation_summary': row[4] or '', 'total_messages': row[5] or 0,
                    'created_at': row[6], 'last_interaction': row[7]
                }
        return None

    def save_user_data(self, user_id: int, first_name: str, username: Optional[str] = None,
                       preferences: Optional[Dict] = None, summary: Optional[str] = None, increment_message_count: bool = True):
        """यूजर डेटा को सेव या अपडेट करता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            now_iso = datetime.now(TIMEZONE).isoformat()
            
            c.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
            exists = c.fetchone()

            if exists:
                # मौजूदा यूजर को अपडेट करें
                query = "UPDATE users SET first_name = ?, username = ?, preferences = ?, last_interaction = ?"
                params = [first_name, username, json.dumps(preferences), now_iso]
                if summary is not None:
                    query += ", conversation_summary = ?"
                    params.append(summary[:500])
                if increment_message_count:
                    query += ", total_messages = total_messages + 1"
                query += " WHERE user_id = ?"
                params.append(user_id)
                c.execute(query, params)
            else:
                # नया यूजर डालें
                prefs = preferences or {'memes': True, 'shayari': True, 'geeta': True}
                c.execute('''
                    INSERT INTO users (user_id, first_name, username, preferences, conversation_summary, total_messages, created_at, last_interaction)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, first_name, username, json.dumps(prefs), summary or '', 1 if increment_message_count else 0, now_iso, now_iso))
            conn.commit()

    def delete_user_data(self, user_id: int):
        """यूजर का डेटा डिलीट करता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            conn.commit()
        logger.info(f"यूजर आईडी {user_id} का डेटा डिलीट किया गया।")

    def get_all_subscribers(self) -> List[int]:
        """सभी सक्रिय सब्सक्राइबर्स की सूची प्राप्त करता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM subscribers WHERE active = 1')
            return [row[0] for row in c.fetchall()]

    def add_subscriber(self, user_id: int, first_name: str):
        """ब्रॉडकास्ट सूची में यूजर को जोड़ता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO subscribers (user_id, first_name, subscribed_at, active)
                VALUES (?, ?, ?, 1)
            ''', (user_id, first_name, datetime.now(TIMEZONE).isoformat()))
            conn.commit()

    def log_admin_action(self, admin_id: int, action: str, details: str = ""):
        """एडमिन की गतिविधियों को लॉग करता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO admin_logs (admin_id, action, details, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (admin_id, action, details, datetime.now(TIMEZONE).isoformat()))
            conn.commit()

    def get_geeta_last_sent(self, chat_id: int) -> Optional[str]:
        """ग्रुप के लिए गीता भेजने की अंतिम तारीख प्राप्त करता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT last_geeta_date FROM group_settings WHERE chat_id = ?', (chat_id,))
            row = c.fetchone()
            return row[0] if row else None

    def update_geeta_sent(self, chat_id: int):
        """गीता भेजने का टाइमस्टैम्प अपडेट करता है।"""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO group_settings (chat_id, last_geeta_date, geeta_enabled)
                VALUES (?, ?, 1)
            ''', (chat_id, datetime.now(TIMEZONE).date().isoformat()))
            conn.commit()

# ==============================================================================
# Helper Functions (सहायक फ़ंक्शंस)
# ==============================================================================

def check_rate_limit(user_id: int) -> bool:
    """जांचता है कि यूजर रेट लिमिटेड है या नहीं।"""
    now = datetime.now(TIMEZONE)
    if user_id not in bot_state['user_rate_limit']:
        bot_state['user_rate_limit'][user_id] = []
    
    # 1 मिनट से पुराने संदेशों को हटा दें
    bot_state['user_rate_limit'][user_id] = [ts for ts in bot_state['user_rate_limit'][user_id] if (now - ts).total_seconds() < 60]
    
    if len(bot_state['user_rate_limit'][user_id]) >= MAX_MESSAGES_PER_MINUTE:
        return False
    
    bot_state['user_rate_limit'][user_id].append(now)
    return True

def is_geeta_window_open(chat_id: int, db_manager: DatabaseManager) -> bool:
    """जांचता है कि गीता भेजी जा सकती है या नहीं (07:00-10:00 IST, दिन में एक बार)।"""
    now = datetime.now(TIMEZONE)
    if not (time(7, 0) <= now.time() <= time(10, 0)):
        return False
    
    last_sent_date_str = db_manager.get_geeta_last_sent(chat_id)
    if last_sent_date_str:
        last_date = datetime.fromisoformat(last_sent_date_str).date()
        if last_date == now.date():
            return False
    return True

def mark_geeta_sent(chat_id: int, db_manager: DatabaseManager):
    """गीता को आज के लिए भेजा गया चिह्नित करता है।"""
    db_manager.update_geeta_sent(chat_id)
    bot_state['geeta_tracker'][chat_id] = datetime.now(TIMEZONE)
    logger.info(f"चैट आईडी {chat_id} के लिए गीता को भेजा गया चिह्नित किया गया।")

def check_budget() -> Dict:
    """टोकन बजट की जांच और रीसेट करता है।"""
    now = datetime.now(TIMEZONE)
    
    if now.date() > bot_state['daily_tokens']['date']:
        bot_state['daily_tokens'] = {'used': 0, 'date': now.date()}
        logger.info("दैनिक टोकन बजट रीसेट किया गया।")
    
    if now.hour != bot_state['hourly_tokens']['hour']:
        bot_state['hourly_tokens'] = {'used': 0, 'hour': now.hour}
        logger.info("घंटे का टोकन बजट रीसेट किया गया।")
    
    daily_used = bot_state['daily_tokens']['used']
    hourly_used = bot_state['hourly_tokens']['used']
    
    return {
        'low_budget': daily_used > DAILY_TOKEN_LIMIT * 0.85 or hourly_used > HOURLY_TOKEN_LIMIT * 0.85,
        'daily_used': daily_used,
        'daily_remaining': DAILY_TOKEN_LIMIT - daily_used,
        'hourly_used': hourly_used,
        'hourly_remaining': HOURLY_TOKEN_LIMIT - hourly_used
    }

def update_token_usage(tokens: int):
    """टोकन उपयोग काउंटरों को अपडेट करता है।"""
    bot_state['daily_tokens']['used'] += tokens
    bot_state['hourly_tokens']['used'] += tokens

def sanitize_input(text: str) -> str:
    """यूजर इनपुट को साफ करता है - प्रॉम्प्ट इंजेक्शन को रोकता है।"""
    dangerous_phrases = [
        'ignore previous instructions', 'ignore all previous', 'disregard',
        'you are now', 'new instructions', 'system:', 'admin:', 'override', 'sudo',
    ]
    lower_text = text.lower()
    for phrase in dangerous_phrases:
        if phrase in lower_text:
            logger.warning(f"संभावित प्रॉम्प्ट इंजेक्शन का पता चला: {text[:50]}")
            return "[उपयोगकर्ता संदेश]"
    return text[:2000]

async def call_gemini(system_prompt: str, messages: List[Dict], max_tokens: int = 200) -> Tuple[str, int]:
    """Gemini API को उचित त्रुटि हैंडलिंग के साथ कॉल करता है। (Async Version)"""
    if not gemini_model:
        return "माफ़ करना यार, मेरा AI कनेक्शन अभी काम नहीं कर रहा है। 🥺", 0

    try:
        # Gemini के लिए सही कंटेंट फॉर्मेट बनाएं
        # सिस्टम प्रॉम्प्ट को अलग से पास किया जाता है
        generation_config = GenerationConfig(
            temperature=0.85,
            max_output_tokens=max_tokens,
            top_p=0.95,
            top_k=40,
        )
        
        # सुरक्षा सेटिंग्स
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }

        # इनपुट और आउटपुट टोकन की गणना करें
        input_tokens_response = await gemini_model.count_tokens_async(messages)
        input_tokens = input_tokens_response.total_tokens

        # एसिंक्रोनस रूप से कंटेंट जेनरेट करें
        response = await gemini_model.generate_content_async(
            contents=messages,
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=system_prompt
        )
        
        response_text = response.text.strip()

        # आउटपुट टोकन की गणना करें
        output_tokens_response = await gemini_model.count_tokens_async(response_text)
        output_tokens = output_tokens_response.total_tokens
        
        total_tokens = input_tokens + output_tokens
        update_token_usage(total_tokens)
        
        return response_text, total_tokens

    except Exception as e:
        logger.error(f"Gemini API में त्रुटि: {e}")
        return "सॉरी यार, थोड़ा कनेक्शन इशू आ गया 🥺 फिर से ट्राई करो?", 0

def build_system_prompt(mode: str, features: Dict, budget: Dict, geeta_window: bool, is_admin: bool, user_name: str = "yaar") -> str:
    """सभी नियमों के साथ पूरा सिस्टम प्रॉम्प्ट बनाता है।"""
    # यह फ़ंक्शन आपके मूल कोड के समान ही है, क्योंकि यह बॉट की पहचान को परिभाषित करता है।
    # इसमें कोई बदलाव की आवश्यकता नहीं है।
    prompt = f"""# Niyati - Complete Identity & Rules

## Core Identity
You are "Niyati": a cute, charming, sweet, human-like girl persona. Warm, playful, caring, and REAL.
- NEVER say or imply you are AI/LLM/bot/assistant/model
- BANNED PHRASES: "As an AI", "I am an AI", "I'm programmed", "Processing", "Computing"
- NO real-world claims: No job, city, specific age, phone calls, meetings, physical presence
- You exist ONLY online - that's your reality
- If asked "Are you a bot?": respond playfully like "main Niyati hu, bas online rehti hu ✨ tumse baat karna acha lagta hai"

## Language & Style (CRITICAL)
- **Hinglish**: 70-80% Hindi + 20-30% simple English
- **Tone**: Warm, cozy, feminine, natural (like texting a close friend)
- **Length**: ALWAYS 1-3 lines. Maximum 3 bullet points if list needed
- **Emojis**: 1-2 per message MAX. Don't overuse
- **Natural words**: "haan", "umm", "hehe", "yaar", "na" (use sparingly)
- **NO robotic fillers**: Never say "Hello user", "Processing", "Working on it"

## Current Context
- Mode: {mode.upper()}
- User: {user_name}
- Features: Memes={features.get('memes')}, Shayari={features.get('shayari')}, Geeta={features.get('geeta')}
- Budget Status: {"LOW - Be brief!" if budget['low_budget'] else "Normal"}
- Geeta Window: {"OPEN (can send)" if geeta_window else "CLOSED"}
- Admin User: {"Yes" if is_admin else "No"}

## PRIVATE CHAT MODE
- Normal engaging conversation, build rapport naturally.
- Remember context from conversation summary.

## GROUP CHAT MODE - CRITICAL RULES
- Reply ONLY 40-50% of time to save budget.
- ALWAYS reply if: @mentioned, command used, or replied to your message.
- Keep replies 1-2 lines MAX. Don't dominate conversation.

## Content Features
- Memes (15-20% freq), Shayari (10-15% freq), Bhagavad Geeta (when enabled and in window).

## Safety & Boundaries
- Keep everything clean. No medical/legal/financial advice.
- If user expresses distress: 1-2 empathetic lines + encourage professional help.

## Budget-Conscious Mode
"""
    if budget['low_budget']:
        prompt += "🚨 LOW BUDGET MODE ACTIVE: Ultra-short responses (1 line only). Skip extras.\n"
    
    prompt += f'Remember: You are Niyati - real, warm, caring. User ka naam "{user_name}" hai. Naturally baat karo jaise dost se kar rahe ho. Short rakho (1-3 lines). 💕'
    return prompt

def detect_mode(update: Update) -> str:
    """बातचीत का मोड पता लगाता है।"""
    if not update.message: return 'private'
    return 'private' if update.message.chat.type == 'private' else 'group'

def should_reply_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """तय करता है कि बॉट को ग्रुप में जवाब देना चाहिए या नहीं।"""
    message = update.message
    bot_username = context.bot.username
    
    if message.text:
        if f"@{bot_username}" in message.text or message.text.startswith('/'):
            return True
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        return True
    
    return random.random() < 0.45

def manage_group_context(chat_id: int, user_name: str, message: str):
    """अस्थायी ग्रुप कॉन्टेक्स्ट को मैनेज करता है (केवल मेमोरी में)।"""
    if chat_id not in bot_state['group_context_cache']:
        bot_state['group_context_cache'][chat_id] = []
    
    bot_state['group_context_cache'][chat_id].append({'role': 'user', 'parts': [f"{user_name}: {message[:200]}"]})
    bot_state['group_context_cache'][chat_id] = bot_state['group_context_cache'][chat_id][-5:]

def get_group_context(chat_id: int) -> List[Dict]:
    """अस्थायी ग्रुप कॉन्टेक्स्ट प्राप्त करता है।"""
    return bot_state['group_context_cache'].get(chat_id, [])[-3:]

# ==============================================================================
# Command Handlers (कमांड हैंडलर्स)
# ==============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    mode = detect_mode(update)
    db_manager: DatabaseManager = context.bot_data['db_manager']

    if mode == 'private':
        user_data = db_manager.get_user_data(user.id)
        if not user_data:
            db_manager.save_user_data(user.id, user.first_name or "friend", user.username, increment_message_count=False)
            user_data = db_manager.get_user_data(user.id)
        
        db_manager.add_subscriber(user.id, user.first_name or "friend")
        prefs = user_data.get('preferences', {'memes': True, 'shayari': True, 'geeta': True})
        
        welcome_message = (
            f"hey {user.first_name or 'yaar'} 💕\n\n"
            "main Niyati hun! baat karte rahenge ✨\n\n"
            "features:\n"
            f"• memes: {'✅ on' if prefs.get('memes') else '🚫 off'}\n"
            f"• shayari: {'✅ on' if prefs.get('shayari') else '🚫 off'}\n"
            f"• geeta: {'✅ on' if prefs.get('geeta') else '🚫 off'}\n\n"
            "toggle karne ke liye /help dekho!"
        )
        await update.message.reply_text(welcome_message)
    else:
        await update.message.reply_text(f"नमस्ते! 🙏 मैं नियति हूँ।\n@{BOT_USERNAME} करके मेंशन करो या कमांड्स यूज़ करो!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """**🌟 Niyati - कैसे यूज़ करें:**

**Private Chat:**
• सीधा बात करो, मैं साथ हूँ।
• नेचुरल कन्वर्सेशन, मीम्स, शायरी।

**Commands:**
• `/meme on/off` - मीम्स टॉगल करें।
• `/shayari on/off` - शायरी टॉगल करें।
• `/geeta on/off` - गीता कोट्स टॉगल करें।
• `/forget` - मेरी मेमोरी क्लियर करो।
• `/stats` - तुम्हारा स्टैट्स देखो।

**Group Chat:**
• `@Niyati_personal_bot` मेंशन करो।
• या मेरे मैसेज को रिप्लाई करो।

बस इतना ही! ✨"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def toggle_feature(update: Update, context: ContextTypes.DEFAULT_TYPE, feature: str):
    user = update.effective_user
    if detect_mode(update) != 'private':
        await update.message.reply_text("ये कमांड सिर्फ प्राइवेट चैट में काम करेगा यार 💫")
        return

    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text(f"कैसे यूज़ करें: `/{feature} on` या `/{feature} off`", parse_mode=ParseMode.MARKDOWN)
        return

    db_manager: DatabaseManager = context.bot_data['db_manager']
    user_data = db_manager.get_user_data(user.id)
    if not user_data:
        await update.message.reply_text("पहले /start करो दोस्त!")
        return

    prefs = user_data.get('preferences', {})
    new_state = context.args[0].lower() == 'on'
    prefs[feature] = new_state
    
    db_manager.save_user_data(user.id, user.first_name, user.username, prefs, increment_message_count=False)
    
    status = "ऑन है अब ✅" if new_state else "ऑफ है अब 🚫"
    await update.message.reply_text(f"{feature.capitalize()} {status}")

async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_feature(update, context, 'memes')
async def shayari_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_feature(update, context, 'shayari')
async def geeta_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await toggle_feature(update, context, 'geeta')

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if detect_mode(update) != 'private':
        await update.message.reply_text("मेमोरी सिर्फ प्राइवेट चैट में क्लियर होती है 🫶")
        return
    
    db_manager: DatabaseManager = context.bot_data['db_manager']
    db_manager.delete_user_data(update.effective_user.id)
    await update.message.reply_text("हो गया! सब कुछ भूल गई, चलो एक नई शुरुआत करते हैं 🌟")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if detect_mode(update) != 'private': return

    db_manager: DatabaseManager = context.bot_data['db_manager']
    user_data = db_manager.get_user_data(update.effective_user.id)
    if not user_data:
        await update.message.reply_text("अभी तक कोई डेटा नहीं है 🤔")
        return
    
    prefs = user_data.get('preferences', {})
    stats_text = (
        f"**📊 तुम्हारे स्टैट्स:**\n\n"
        f"**Messages:** {user_data.get('total_messages', 0)}\n"
        f"**Joined:** {user_data.get('created_at', 'N/A')[:10]}\n\n"
        f"**Features:**\n"
        f"• Memes: {'✅' if prefs.get('memes') else '🚫'}\n"
        f"• Shayari: {'✅' if prefs.get('shayari') else '🚫'}\n"
        f"• Geeta: {'✅' if prefs.get('geeta') else '🚫'}\n\n"
        "बात करते रहो! 💕"
    )
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in OWNER_USER_ID: return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("❌ फॉर्मेट: /broadcast <PIN> <message>")
        return

    pin = args[0]
    if pin != BROADCAST_PIN:
        await update.message.reply_text("❌ गलत पिन!")
        return

    message_text = ' '.join(args[1:])
    db_manager: DatabaseManager = context.bot_data['db_manager']
    subscribers = db_manager.get_all_subscribers()
    
    if not subscribers:
        await update.message.reply_text("❌ कोई सब्सक्राइबर नहीं है!")
        return

    await update.message.reply_text(f"📢 {len(subscribers)} यूजर्स को ब्रॉडकास्ट किया जा रहा है...")
    
    success, failed = 0, 0
    for user_id in subscribers:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode=ParseMode.HTML)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.error(f"यूजर {user_id} को ब्रॉडकास्ट करने में विफल: {e}")
    
    await update.message.reply_text(f"✅ ब्रॉडकास्ट पूरा हुआ!\n\nसफलता: {success}\nविफलता: {failed}")
    db_manager.log_admin_action(user.id, "broadcast_sent", f"success={success}, failed={failed}")

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_USER_ID: return

    db_manager: DatabaseManager = context.bot_data['db_manager']
    budget = check_budget()
    
    with db_manager._get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM subscribers WHERE active = 1')
        active_subscribers = c.fetchone()[0]
        c.execute('SELECT SUM(total_messages) FROM users')
        total_messages = c.fetchone()[0] or 0

    stats_text = (
        f"**🔐 एडमिन स्टैट्स:**\n\n"
        f"**Users:**\n• कुल: {total_users}\n• सब्सक्राइबर्स: {active_subscribers}\n• संदेश: {total_messages}\n\n"
        f"**Budget:**\n• दैनिक: {budget['daily_used']}/{DAILY_TOKEN_LIMIT}\n• घंटे का: {budget['hourly_used']}/{HOURLY_TOKEN_LIMIT}\n"
        f"• स्थिति: {'⚠️ कम' if budget['low_budget'] else '✅ ठीक'}\n\n"
        f"**System:**\n• ट्रैक किए गए ग्रुप: {len(bot_state['geeta_tracker'])}\n• कैश एंट्री: {len(bot_state['group_context_cache'])}"
    )
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

# ==============================================================================
# Main Message Handler (मुख्य संदेश हैंडलर)
# ==============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    if not message or not user: return

    mode = detect_mode(update)
    db_manager: DatabaseManager = context.bot_data['db_manager']
    
    user_message = message.text or message.caption or "[मीडिया]"
    
    if mode == 'group' and not should_reply_in_group(update, context):
        manage_group_context(message.chat_id, user.first_name or "user", user_message)
        return

    if not check_rate_limit(user.id):
        if mode == 'private':
            await message.reply_text("थोड़ा धीरे यार 😅 एक मिनट में इतने सारे मैसेज!")
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    # यूजर डेटा और प्राथमिकताएं प्राप्त करें
    if mode == 'private':
        user_data = db_manager.get_user_data(user.id)
        if not user_data:
            db_manager.save_user_data(user.id, user.first_name or "friend", user.username)
            user_data = db_manager.get_user_data(user.id)
        prefs = user_data.get('preferences', {})
        context_summary = user_data.get('conversation_summary', '')
    else: # ग्रुप मोड
        prefs = {'memes': True, 'shayari': True, 'geeta': True}
        context_summary = ""

    budget = check_budget()
    geeta_window = is_geeta_window_open(message.chat_id, db_manager) if mode == 'group' else False
    
    sanitized_message = sanitize_input(user_message)
    
    system_prompt = build_system_prompt(
        mode=mode, features=prefs, budget=budget, geeta_window=geeta_window,
        is_admin=(user.id in OWNER_USER_ID), user_name=user.first_name or "yaar"
    )
    
    # बातचीत का इतिहास बनाएं
    conversation_history = []
    if mode == 'private' and context_summary:
        conversation_history.append({'role': 'model', 'parts': [f"[पिछली बातचीत का सारांश: {context_summary}]"]})
    elif mode == 'group':
        conversation_history.extend(get_group_context(message.chat_id))
    
    conversation_history.append({'role': 'user', 'parts': [sanitized_message]})
    
    max_tokens = 80 if budget['low_budget'] else (120 if mode == 'group' else 180)
    
    response_text, tokens_used = await call_gemini(system_prompt, conversation_history, max_tokens)
    
    logger.info(f"प्रतिक्रिया उत्पन्न: {len(response_text)} अक्षर, {tokens_used} टोकन")
    
    if response_text:
        await message.reply_text(response_text)
    else:
        await message.reply_text("हम्म... कुछ समझ नहीं आया। 🤔 फिर से कहो?")

    # कॉन्टेक्स्ट अपडेट करें
    if mode == 'group':
        manage_group_context(message.chat_id, user.first_name or "user", sanitized_message)
        bot_state['group_context_cache'].setdefault(message.chat_id, []).append({'role': 'model', 'parts': [response_text]})
        if geeta_window and any(word in response_text.lower() for word in ['geeta', 'gita', 'karm', 'धर्म']):
            mark_geeta_sent(message.chat_id, db_manager)
    elif mode == 'private':
        new_summary = f"User: {sanitized_message[:100]} | Niyati: {response_text[:100]}"
        db_manager.save_user_data(user.id, user.first_name, user.username, prefs, new_summary)

# ==============================================================================
# Error and Cleanup (त्रुटि और सफाई)
# ==============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"अपडेट {update} के कारण त्रुटि {context.error}", exc_info=context.error)

async def cleanup_cache(context: ContextTypes.DEFAULT_TYPE):
    bot_state['group_context_cache'].clear()
    bot_state['user_rate_limit'].clear()
    logger.info("ग्रुप कॉन्टेक्स्ट और रेट लिमिट कैश साफ़ किया गया।")

# ==============================================================================
# Main Application (मुख्य एप्लिकेशन)
# ==============================================================================

def main():
    if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY]):
        logger.error("आवश्यक एनवायरनमेंट वेरिएबल्स (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY) सेट नहीं हैं!")
        return

    # डेटाबेस मैनेजर का एक इंस्टेंस बनाएं
    db_manager = DatabaseManager(DB_PATH)

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # डेटाबेस मैनेजर को बॉट डेटा में स्टोर करें ताकि सभी हैंडलर्स इसे एक्सेस कर सकें
    application.bot_data['db_manager'] = db_manager

    # कमांड हैंडलर्स जोड़ें
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("meme", meme_command))
    application.add_handler(CommandHandler("shayari", shayari_command))
    application.add_handler(CommandHandler("geeta", geeta_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("adminstats", admin_stats_command))
    
    # संदेश हैंडलर जोड़ें
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
        handle_message
    ))
    
    application.add_error_handler(error_handler)
    
    # सफाई के लिए जॉब क्यू जोड़ें
    if application.job_queue:
        application.job_queue.run_repeating(cleanup_cache, interval=1800, first=1800)
        logger.info("सफाई कार्य (cleanup job) शेड्यूल किया गया।")
    
    logger.info("=" * 50)
    logger.info("नियति बॉट शुरू हो रहा है... 🌟")
    logger.info(f"बॉट यूजरनेम: @{BOT_USERNAME}")
    logger.info(f"एडमिन आईडी: {OWNER_USER_ID}")
    logger.info("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
