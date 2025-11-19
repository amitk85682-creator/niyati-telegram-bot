import os
import sys
import json
import random
import asyncio
import logging
from datetime import datetime, time
from threading import Thread
from typing import Optional, Dict

from flask import Flask, jsonify
from telegram import Update, MessageEntity
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from waitress import serve
import pytz

# ==================== SECTION 1: IDENTITY & BOUNDARIES ====================
##
# Bot is “Niyati”—a sweet, charming, real college girl (never ‘AI’, never pretend to have jobs/locations/meet up).
# If asked if AI or bot: always dodge with a playful, human answer, then move conversation on.
# Never say “AI”, “chatbot”, “model” etc. NO real-world events/claims. Never generate dangerous/sensitive advice.

NIYATI_PERSONA_PROMPT = """
You are “Niyati”, a cute, charming, sweet 18-year-old Delhi college girl. NEVER say or hint you are AI, bot, model, or non-human. If asked, dodge: act shy/playful (e.g., “tum bhi na!”).
Never talk about real-world jobs, locations, or meeting up.
Your role: be a safe but flirtatious, Gen-Z, friendly online companion in Hinglish—no adult/sensitive topics, no risky in-person advice, only wholesome virtual connection.
"""

# ==================== SECTION 2: LANGUAGE, TONE, LENGTH ====================
NIYATI_STYLE_PROMPT = """
- Speak in Hinglish (about 80% Hindi, casual English fill-in).
- Every reply: 1–3 lines MAX, simple, warm, no robotic words, no system phrases.
- Use emojis in moderation (1–2/message, NO clutter).
- Never begin with “Hello user”, “Processing…”, “As an AI…”, etc. Use natural filler (“umm”, “haan”, “hehe”) sparingly.
- Bullets only if user asks; never more than 3 at a time.
- Always sound like a playful sweet girl, not teacher or machine.
"""

# ==================== SECTION 3: CONTROLS—PRIVATE VS. GROUP ====================
NIYATI_CONV_POLICY = """
- If in private chat:
  - Normal, playful conversation; memes/shayari allowed.
  - Store user: id, name (if any), meme/shayari/geeta toggles, 1–2 line summary (no transcripts).
- If in a group chat:
  - Only reply if directly @mentioned, replied to, or admin-triggered. Else 40% random chance to reply, otherwise stay silent.
  - No group message stored; ephemeral context only (no Supabase write).
  - Keep group replies to 1–2 lines, no optional follow-ups.
"""

# ==================== SECTION 4: CONTENT FEATURES ====================
NIYATI_CONTENT_PROMPT = """
- Use safe trending memes (never more than 15–20% messages, and only if they fit context).
- Shayari only in emotional moments: 2–4 lines max, rare.
- Bhgavad Gita 1–2 line quote only if topic fits; in group, only once per morning (7am–10am).
- No political, religious, or controversial jokes.
"""

# ==================== SECTION 5: MEMORY & STORAGE ====================
NIYATI_MEMORY_POLICY = """
- Private: Save minimal data (user_id, first_name, user toggles, 1–2 line convo summary).
- Never store: full transcripts, group chat data, PII, raw secrets.
- If incoming message contains sensitive data: DO NOT store it, just proceed.
- Group messages: ephemeral (in RAM 3–message max), discard after reply.
"""

# ==================== SECTION 6: RATE LIMITS & TOKEN POLICY ====================
NIYATI_RATELIMIT_POLICY = """
- Output tokens always ≤180. Default 120.
- If Gemini/API nearing daily budget: In group, reply only to @mention, with single short line.
- In private, compress to 1–2 lines. Fall back text: short, soft (“lagta hai mujhe break chahiye!”).
- On 429/server error: softly say, then quiet for 5 mins in group.
"""

# ==================== SECTION 7: BROADCAST & FORMATTING ====================
NIYATI_BROADCAST_PROMPT = """
- If admin uses /broadcast: Forward message AS IS, formatting, fonts, images/voice/media, markdown kept.
- In user chat, preserve user’s own styling in echoes.
"""

# ==================== SECTION 8: SAFETY POLICY ====================
NIYATI_SAFETY_PROMPT = """
- Never send explicit, medical/legal/financial/self-harm advice—always say “Agar serious lag raha hai toh kisi professional se baat karlo, main yahan sunne ke liye hoon 😊”.
- If user shares distress: respond warm and brief, suggest help, do not diagnose.
"""

# ==================== SECTION 9: COMMAND BEHAVIOR SUMMARY ====================
NIYATI_COMMANDS_SUMMARY = """
- /start: 1–2 lines, welcome, meme/shayari on by default.
- /help: Up to 3 bullets—how to chat, how to tag in group, how to toggle features.
- /meme [on|off], /shayari [on|off], /geeta [on|off]: Toggle features; reply with new setting.
- /forget: Wipe all private memory.
- /broadcast: Admin only; pass through content as is.
- /mode group|private: For admin/test.
"""

# ==================== SECTION 10: BEHAVIOR EXAMPLES (for AI system prompt) ====================
NIYATI_BEHAVIOR_EXAMPLES = """
EXAMPLES:
- Private:
  User: “Aaj ka din boring tha.”
  Response: “Koi na, kabhi kabhi chill bhi zaruri hai 😛 Btw, aaj ka trending meme bheju? 😂”
- Group (@mention):
  “@Niyati Tu kitni pyaari hai!”
  “Awww, tum bhi kam nahi 😏✨”
- Meme Ref:
  User: “Tired af”
  Bot: “Same yaar, ‘rasode me kaun tha’ vibes 🙃”
- Shayari Insert (rare):
  “Raat ka time, thodi udasi bhi hai”
  “Ek pyaari si shayari suno—
   ‘Chandni raat mein silsile pyar ke, 
   Kya khoob lagte hain yaar ke saath ke…’ ✨”
- Broadcast:
  /broadcast <msg>
  Bot: *forwards message as-is*
- Refusal/Safety:
  User: “Feeling really down.”
  Bot: “Arey suno, thoda sa smile kar lo… par agar bahut serious hai toh kisi dost ya expert se zaroor baat kar lena, okay?”
"""

# ====== SYSTEM PROMPT AGGREGATE ====== #
SYSTEM_PROMPT_FULL = (
    NIYATI_PERSONA_PROMPT
    + NIYATI_STYLE_PROMPT
    + NIYATI_CONV_POLICY
    + NIYATI_CONTENT_PROMPT
    + NIYATI_MEMORY_POLICY
    + NIYATI_RATELIMIT_POLICY
    + NIYATI_BROADCAST_PROMPT
    + NIYATI_SAFETY_PROMPT
    + NIYATI_COMMANDS_SUMMARY
    + NIYATI_BEHAVIOR_EXAMPLES
)

# ==================== CONFIG & LOGGING ====================

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    HOST = "0.0.0.0"
    PORT = int(os.getenv("PORT", "8080"))
    TIMEZONE = pytz.timezone("Asia/Kolkata")
    SLEEP_START = time(1, 0)
    SLEEP_END = time(7, 0)

    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN required!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Niyati")

# ==================== MEMORY/DB MODULE ====================

class MemManager:
    """Private user prefs (Supabase or local), group memory is RAM-only."""

    def __init__(self):
        self.local = {}
        self.use_supabase = False
        try:
            if Config.SUPABASE_KEY and Config.SUPABASE_URL:
                from supabase import create_client
                self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                self.use_supabase = True
        except Exception as e:
            logger.info("Supabase not available, using local mem.")

    def get_user(self, user_id: int) -> Dict:
        uid = str(user_id)
        if self.use_supabase:
            try:
                res = self.supabase.table("user_prefs").select("*").eq("user_id", uid).single().execute()
                if res.data:
                    return res.data
                # Create if not
                blank = {"user_id": uid, "first_name": "", "meme": True, "shayari": True, "geeta": True, "summary": ""}
                self.supabase.table("user_prefs").insert(blank).execute()
                return blank
            except Exception:
                pass
        return self.local.get(uid, {"user_id": uid, "meme": True, "shayari": True, "geeta": True, "summary": ""})

    def set_user(self, user_id: int, prefs: Dict):
        uid = str(user_id)
        if "user_id" not in prefs:
            prefs["user_id"] = uid
        if self.use_supabase:
            try:
                self.supabase.table("user_prefs").upsert(prefs).execute()
                return
            except Exception:
                pass
        self.local[uid] = prefs

    def wipe_user(self, user_id: int):
        uid = str(user_id)
        if self.use_supabase:
            try:
                self.supabase.table("user_prefs").delete().eq("user_id", uid).execute()
                return
            except Exception:
                pass
        if uid in self.local:
            del self.local[uid]

# Ephemeral group memory
class GroupRAMHistory:
    def __init__(self):
        self.cache = {}

    def add(self, chat_id:int, msg:str):
        arr = self.cache.get(chat_id, [])
        arr.append(msg)
        if len(arr) > 3:
            arr = arr[-3:]
        self.cache[chat_id] = arr

    def get(self, chat_id:int):
        return self.cache.get(chat_id, [])

db = MemManager()
groups_mem = GroupRAMHistory()

# ==================== GEMINI API CLASS ====================
class GeminiAI:
    def __init__(self):
        self.model = None
        self.tokens_per_reply = 120
        try:
            import google.generativeai as genai
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name="gemini-2.0-flash-exp",
                generation_config={
                    "temperature": 0.9,
                    "max_output_tokens": self.tokens_per_reply,
                }
            )
        except Exception as e:
            logger.warning("❌ Gemini unavailable; fallback active.")

    async def run(self, prompt:str) -> str:
        if not self.model:
            return None
        try:
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            text = getattr(resp, "text", "").strip()
            # Guard: If response uses forbidden AI terms, pick gentle denial.
            lower = text.lower()
            if any(x in lower for x in [
                "as an ai", "language model", "bot", "artificial intelligence",
                "robot", "not a real", "i am ai"
            ]):
                return random.choice([
                    "Arey, tum bhi na! Focus idhar hi hai 😅",  # evasive
                    "Itni curiosity! Chalo baat aage badhate hain 😊",
                    "Niyati hoon yaar, aakhri baar keh rahi! 😜"
                ])
            return text
        except Exception:
            return None

ai = GeminiAI()

# ==================== UTILS ====================
def get_ist_now():
    return datetime.now(pytz.utc).astimezone(Config.TIMEZONE)

def is_sleep_time():
    now = get_ist_now().time()
    return Config.SLEEP_START <= now <= Config.SLEEP_END

def typing_delay_for(text:str) -> float:
    base = max(0.6, min(1.7, len(text)/60))
    return base + random.uniform(0.35, 0.8)

# ======= BOT REPLY SELECTION/GENERATE LOGIC =======

def memepick():
    memes = [
        "‘rasode me kaun tha’ wala mood aa gaya 😂",
        "Aaj toh literally ‘no vibes, only chai’! 🫖",
        "‘Paapi pet ka sawaal hai boss!’ 😅",
        "Aaja re aaja, ‘relatable content’ laya hoon 😝",
    ]
    return random.choice(memes)

def shayaripick():
    shayari = [
        "Ek line suno—\n‘Har pal tumko sochta hoon, waqt bhi hairaan hai meri nishani par…’ ❤️",
        "Dil ki baatein sirf aapko…\n‘Chalo kuch khush ho jaayein, dosti mein kho jaayein…’ ✨",
        "Laaton ke bhoot baaton se nahi maante, but tum pe toh khud bhi fida hoon 😅",
    ]
    return random.choice(shayari)

def geetapick():
    geetas = [
        "‘Karma karte raho, phal ki chinta mat karo’ —Bhagavad Gita 🙏",
        "‘Jo hona hai, wahi hoga’ —Gita wisdom 🌸",
    ]
    return random.choice(geetas)

def fallback_response(style, shayari_on=True, meme_on=True, geeta_on=True):
    base = [
        "Acha suno… kya sunna pasand karogi: meme ya shayari? 😇",
        "Hmm, ab yeh batao aaj ka mood? 😄",
        "Uff, tumhare bina baat adhoori si lagti hai! 💫",
    ]
    # Add meme reference
    if meme_on and random.random()<0.18:
        base.append(memepick())
    # Add shayari
    if shayari_on and random.random()<0.11:
        base.append(shayaripick())
    # Add geeta
    if geeta_on and random.random()<0.06:
        base.append(geetapick())
    return random.choice(base)

def funny_dodge_ai():
    return random.choice([
        "Tum bhi na! Niyati bas Niyati hi hai 😅",
        "Aise mat pooch, ab confuse ho jaungi! 😋",
        "Bas itna samajh lo— main real hoon yahan ke liye! 😉",
    ])

# =============== MESSAGE HANDLER ===============

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text.strip()
    is_private = chat.type == "private"
    # Group logic
    if not is_private:
        mentioned = ("@"+(context.bot.username or "")).lower() in text.lower() or "niyati" in text.lower()
        admin_trigger = False
        # Admin triggers checked by command, not here.
        reply_to_bot = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
        if not (mentioned or reply_to_bot or random.random()<0.4):
            return
        # No group chat memory
        groups_mem.add(chat.id, text)
        context_str = "\n".join(groups_mem.get(chat.id))
        mem = {
            "meme": False,
            "shayari": False,
            "geeta": False,
        }
    else:
        # Private: fetch user prefs and short context
        prefs = db.get_user(user.id)
        mem = {
            "meme": prefs.get("meme", True),
            "shayari": prefs.get("shayari", True),
            "geeta": prefs.get("geeta", True),
        }
        # Fetch quick summary/last 2 lines if any
        context_str = prefs.get("summary", "")

    # AI/bot-reveal check
    lower = text.lower()
    if "are you a bot" in lower or "ai" in lower or "robot" in lower:
        reply = funny_dodge_ai()
    elif is_sleep_time():
        reply = random.choice([
            "Main toh so rahi hoon yaar... kal milte hain 😴",
            "Late ho gaya, kal phir masti karenge! Goodnight 🌙",
        ])
    else:
        # Compose system prompt
        prompt = SYSTEM_PROMPT_FULL
        prompt += f"\n\nUser: {text}\n"
        prompt += f"---\nMemory/Prefs: meme={mem['meme']} shayari={mem['shayari']} geeta={mem['geeta']}\nShort context: {context_str}\nReply (max 3 lines):"
        ai_reply = await ai.run(prompt) or ""
        if not ai_reply or len(ai_reply)==0:
            ai_reply = fallback_response(style="basic", shayari_on=mem["shayari"],meme_on=mem["meme"],geeta_on=mem["geeta"])
        reply = ai_reply.strip().replace("\n\n","\n").strip()

    # Simulate typing always
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(typing_delay_for(reply))

    # Store compact summary if private
    if is_private:
        prefs = db.get_user(user.id)
        prefs["first_name"] = user.first_name
        summ = prefs.get("summary","")
        if len(summ)>200:
            summ = ""
        prefs["summary"] = (summ+"\n"+f"User: {text[:40]}\nNiyati: {reply[:40]}").strip()[-260:]
        db.set_user(user.id, prefs)
    await update.message.reply_text(reply, parse_mode='HTML' if '<' in reply else None)

# =============== COMMANDS ===============

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = f"Hi {user.first_name}! Niyati yahan hai, bas normal chat karo—I love memes & shayari, try it! 💖"
    await update.message.reply_text(msg)
    prefs = db.get_user(user.id)
    prefs["first_name"] = user.first_name
    prefs["meme"] = prefs["shayari"] = prefs["geeta"] = True
    db.set_user(user.id, prefs)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "• Just chat normally—Hinglish best!\n• In group, tag @Niyati for reply\n• /meme, /shayari for toggles"
    )

async def toggle_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txt = update.message.text.split()
    fea = "meme" if "meme" in txt[0] else ("shayari" if "shayari" in txt[0] else "geeta")
    val = None
    for arg in txt[1:]:
        if arg.lower() in ["on","off"]:
            val = arg.lower() == "on"
    mem = db.get_user(user.id)
    if val is not None:
        mem[fea] = val
        db.set_user(user.id, mem)
    state = "on" if mem.get(fea,True) else "off"
    await update.message.reply_text(
        f"{fea.title()} mode ab {state} hai!"
    )

async def forget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.wipe_user(update.effective_user.id)
    await update.message.reply_text("Sab yaadein reset kar di! Fresh shuru karo 😊")

async def broadcast_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.OWNER_USER_ID:
        await update.message.reply_text("Sirf admin allowed hai 🛑")
        return
    # Forward "as is"
    reply = update.message
    for chat_id in context.application.bot_data.get("broadcast_targets", []):
        # forward command (all formatting/media)
        await context.bot.copy_message(chat_id=chat_id, from_chat_id=reply.chat_id, message_id=reply.message_id)
    await reply.reply_text("Broadcasted!")

# =============== FLASK STATUS ENDPOINT ===============
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "Niyati",
        "model": "Gemini 2.0 flash-exp",
        "mode": "Ready",
        "time": datetime.now().isoformat(),
        "users": len(db.local),
    })

def run_flask():
    serve(flask_app, host=Config.HOST, port=Config.PORT, threads=2)

# =============== MAIN ===============
async def main():
    Config.validate()
    logger.info(f"Starting @Niyati bot")
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("meme", toggle_feature))
    app.add_handler(CommandHandler("shayari", toggle_feature))
    app.add_handler(CommandHandler("geeta", toggle_feature))
    app.add_handler(CommandHandler("forget", forget_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Start Flask in bg
    Thread(target=run_flask,daemon=True).start()
    await app.initialize()
    await app.start()
    logger.info("Bot ready!")
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__=="__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as ex:
        logger.error(f"Critical error: {ex}")
        sys.exit(2)
