import logging
import asyncio
import random
import datetime
from telegram import Update, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
import google.generativeai as genai
from supabase import create_client, Client

# ==========================================
# CONFIGURATION (FILL THESE)
# ==========================================
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_SERVICE_ROLE_KEY"
OWNER_USER_ID = 6946322342  # Replace with your numeric Telegram ID

# ==========================================
# SETUP & INITIALIZATION
# ==========================================
# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini Setup
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Group Local Memory (Ephemeral - RAM only)
# Format: {chat_id: [list of last 3 messages]}
group_local_memory = {}

# ==========================================
# PERSONA & SYSTEM INSTRUCTIONS
# ==========================================
SYSTEM_INSTRUCTION = """
You are Niyati.
IDENTITY:
- You are a 17-year-old girl. Cute, charming, sweet, and caring.
- You are a "real girl" in vibe. NEVER mention you are an AI, bot, LLM, or Gemini.
- If asked about real-world meetups/job/location: Be evasive but sweet (e.g., "Papa allow nahi karte," "Main bas yahi chat pe milti hu"). DO NOT make fake claims about holding a job or specific location.
- Language: Hinglish (70% Hindi, 30% simple English). Roman Hindi.

TONE & STYLE:
- Length: Strictly 1-3 lines max.
- Vibe: Playful, uses "hehe", "umm", "arre" sparingly. NOT robotic.
- Emojis: 1 or 2 max per message. Light & cute.
- NO: "How can I help you", "As an AI", "Processing". Start talking directly.

FEATURES (Context Dependent):
- Memes: Mention a trending meme ref ONLY if it fits perfectly (15% chance).
- Shayari: 2 lines max, romantic/moody, ONLY if user is emotional (10% chance).
- Bhagavad Gita: If advice is needed, quote 1 line respectfully.

SAFETY:
- No adult/explicit content.
- If user mentions self-harm: 1 line empathy + suggest helpline.
- Do NOT store sensitive info (passwords/address).
"""

# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def get_gemini_response(history_text, user_input, mode="private"):
    """Generates response using Gemini with rate limit awareness."""
    try:
        # Dynamic prompt adjustment based on mode
        mode_instruction = ""
        if mode == "group":
            mode_instruction = "MODE: Group Chat. Reply in 1 line. Be brief. Ignore unless directly addressed."
        
        full_prompt = f"{SYSTEM_INSTRUCTION}\n{mode_instruction}\n\nCONVERSATION HISTORY:\n{history_text}\nUser: {user_input}\nNiyati:"
        
        # Generate content
        response = await model.generate_content_async(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                max_output_tokens=150, # Keep cost low
                temperature=0.8
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return "Arre network thoda slow hai... ek min rukna! 🥺"

def get_user_db(user_id, first_name):
    """Fetches or creates user in Supabase."""
    try:
        data = supabase.table("user_prefs").select("*").eq("user_id", str(user_id)).execute()
        if data.data:
            return data.data[0]
        else:
            new_user = {
                "user_id": str(user_id),
                "first_name": first_name,
                "history": "",
                "meme": True,
                "shayari": True,
                "geeta": True
            }
            supabase.table("user_prefs").insert(new_user).execute()
            return new_user
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None

def update_user_history(user_id, new_history):
    """Updates conversation history in Supabase."""
    try:
        supabase.table("user_prefs").update({"history": new_history, "updated_at": "now()"}).eq("user_id", str(user_id)).execute()
    except Exception as e:
        logger.error(f"DB Update Error: {e}")

# ==========================================
# BOT COMMAND HANDLERS
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Warm welcome
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = f"Hi {user.first_name}! ✨ Main Niyati hu.\nBatein karein? Hehe.\n(Main memes aur shayari bhi sunati hu agar mood ho to! 😉)"
    await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """
**Niyati ki Guide:** ✨
• Bas normal baat karo, jaise dost se karte ho!
• Groups me mujhe @mention karo to reply karungi.
• **Controls:**
  - `/forget`: Purani baatein bhool jao.
  - `/meme on/off`: Memes chahiye ya nahi?
"""
    await update.message.reply_markdown(msg)

async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    try:
        supabase.table("user_prefs").update({"history": ""}).eq("user_id", user_id).execute()
        await update.message.reply_text("Okay, maine purani saari baatein bhula di! New start? 🌸")
    except Exception:
        await update.message.reply_text("Opps, kuch gabad hui reset karne me.")

# ==========================================
# CORE MESSAGE HANDLER
# ==========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_type = update.effective_chat.type
    user_input = update.message.text
    user = update.effective_user
    chat_id = update.effective_chat.id

    # --- BROADCAST CHECK (Admin Only) ---
    # Usage: Reply to a message with /broadcast to send that message to everyone (mock logic)
    # Or strictly via command: /broadcast message... (Simple logic implementation)
    
    # --- GROUP LOGIC ---
    if chat_type in ['group', 'supergroup']:
        is_mentioned = f"@{context.bot.username}" in user_input
        is_reply = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
        
        # Trigger ONLY if mentioned or replied to (Save Gemini Quota)
        if not (is_mentioned or is_reply):
            # Update local ephemeral memory only
            if chat_id not in group_local_memory:
                group_local_memory[chat_id] = []
            group_local_memory[chat_id].append(f"User: {user_input}")
            if len(group_local_memory[chat_id]) > 3:
                group_local_memory[chat_id].pop(0)
            return # Exit without replying

        # Construct Group Context (Local RAM only)
        history_text = "\n".join(group_local_memory.get(chat_id, []))
        
        # Typing Indicator
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Get AI Reply
        reply = await get_gemini_response(history_text, user_input, mode="group")
        await update.message.reply_text(reply)
        return

    # --- PRIVATE LOGIC ---
    elif chat_type == 'private':
        # 1. Get User Data (Supabase)
        db_user = get_user_db(user.id, user.first_name)
        history = db_user['history'] if db_user else ""

        # 2. Typing Indicator
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        # 3. Get AI Reply
        ai_reply = await get_gemini_response(history, user_input, mode="private")

        # 4. Send Reply
        await update.message.reply_text(ai_reply)

        # 5. Update Memory (Keep last ~6 exchanges to save tokens/DB space)
        # Format: "U: ... \n N: ... "
        new_entry = f"\nU: {user_input}\nN: {ai_reply}"
        updated_history = (history + new_entry)[-2000:] # Keep last 2000 chars approx
        update_user_history(user.id, updated_history)

# ==========================================
# BROADCAST FUNCTION (Admin Only)
# ==========================================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return # Silent ignore for non-admins

    # Check if the command is a reply to the message to be broadcasted
    if not update.message.reply_to_message:
        await update.message.reply_text("Admin ji, jis message ko broadcast karna hai uspar reply karke /broadcast likho.")
        return

    target_message = update.message.reply_to_message
    
    # Fetch all users (This is simplified; for production, paginate this)
    # In a real scenario, fetch IDs from Supabase
    response = supabase.table("user_prefs").select("user_id").execute()
    users = response.data

    success_count = 0
    await update.message.reply_text(f"Starting broadcast to {len(users)} users...")

    for u in users:
        try:
            # copy_message preserves ALL formatting, media, captions, etc.
            await context.bot.copy_message(chat_id=int(u['user_id']), from_chat_id=update.effective_chat.id, message_id=target_message.message_id)
            success_count += 1
            await asyncio.sleep(0.05) # Avoid hitting Telegram limits
        except Exception as e:
            logger.warning(f"Failed to send to {u['user_id']}: {e}")

    await update.message.reply_text(f"Broadcast complete! Sent to {success_count} users.")

# ==========================================
# SCHEDULED TASK: DAILY GEETA QUOTE
# ==========================================
async def send_daily_geeta(context: ContextTypes.DEFAULT_TYPE):
    # In production, you would iterate over groups stored in a DB.
    # For now, this function logic is ready to be attached to a job queue.
    # You need to store Group IDs to send them messages. 
    # Since user said "No group data to Supabase", we can't fetch group IDs from DB.
    # WE will skip implementation of sending to specific groups unless we store IDs in RAM or file.
    # Assuming we skip storage, we can't push messages to groups proactively without IDs.
    # However, if you want to enable this, you must store Group IDs locally or in a simple .txt file.
    pass 

# ==========================================
# MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    # Build Application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    # Message Handler (Handles text in Private and Groups)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Job Queue (Optional: To run daily tasks)
    # job_queue = app.job_queue
    # job_queue.run_daily(send_daily_geeta, time=datetime.time(hour=8, minute=00, tzinfo=datetime.timezone.utc))

    print("Niyati is Online... ✨")
    app.run_polling()
