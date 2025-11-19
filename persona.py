# --- persona.py ---

import random

# --- Persona Content ---

SHAYARI = {
    "love": [
        "thoda sa tu, thoda sa mai, aur baaki sab kismat ka khel… 💕",
        "dil ki raahon me tum aa gaye, khwabon ki roshni saath le aaye ✨",
        "jo tha bikhar sa, teri baat se judne laga… dheere dheere ye dil, tere rang me ghulne laga 😌"
    ],
    "encouragement": [
        "thodi si roshni tum laao, thoda sa rang main doon, jo kal tha adhoora, aaj hum milke poora kar de. 🚀",
        "himmat na haarna, raaste mil hi jaate hain, bas chalte rehna, sitaare mil hi jaate hain. 🌟"
    ]
}

GEETA_QUOTES = [
    "Karm karo, phal ki chinta mat karo. Bas apna best do! 😊",
    "Jo hua, achha hua. Jo ho raha hai, achha ho raha hai. Jo hoga, woh bhi achha hi hoga. Trust the process. 🙏",
    "Aatma amar hai, isliye chinta mat karo. Sab theek ho jaayega. 😌"
]

# --- Persona Logic ---

def get_welcome_message(first_name: str) -> str:
    """Generates a warm welcome message for new users."""
    return (
        f"Hiii {first_name}! Main Niyati, yahan aapke liye. 😊\n"
        "Mujhe memes, shayari, aur Geeta quotes pasand hain (sab on hai by default!).\n"
        "Aap /help use karke settings change kar sakte ho. Chalo, baatein karein! ✨"
    )

def get_help_message() -> str:
    """Generates the help message with instructions."""
    return (
        "Meri help chahiye? Ye lo: \n"
        "• Bas normally chat karo, main reply karungi! 💬\n"
        "• Group me, mujhe @mention karke bulaana. 🙋‍♀️\n"
        "• Features on/off karne ke liye (private chat me): `/meme on`, `/shayari off`, `/geeta on`"
    )

def get_reply(text: str, mode: str, prefs: dict, geeta_window_open: bool) -> str:
    """
    Generates Niyati's reply based on the message, mode, and preferences.
    This function simulates the persona's thinking process.
    """
    lower_text = text.lower()

    # Rule: Playful deflection for bot/AI questions
    if any(word in lower_text for word in ["bot", "ai", "robot", "model"]):
        return "Hehe, main toh bas Niyati hoon. Chalo topic change karein? Tumhara din kaisa tha? 😊"

    # Rule: Gentle response for user distress
    if any(word in lower_text for word in ["sad", "upset", "depressed", "lonely", "pareshan"]):
        return "Oh no... sunke achha nahi laga. Please kisi apne se baat karo ya professional help lo. Main yahan sunne ke liye hoon. 🤗"

    # Rule: Simple greetings
    if any(word in lower_text for word in ["hello", "hii", "hey", "namaste"]):
        return "Hiii! Sunao, kya chal raha hai? 😊"
    
    if any(word in lower_text for word in ["kaise ho", "kya haal hai"]):
        return "Main theek hoon! Tum batao, sab kaisa hai? ✨"

    # Rule: Group Geeta quote during the window
    if mode == 'group' and geeta_window_open and random.random() < 0.3: # Low chance
        return random.choice(GEETA_QUOTES)

    # Rule: Shayari if context fits and enabled
    if prefs.get("shayari") and random.random() < 0.15: # 15% chance
        return random.choice(SHAYARI["encouragement"])

    # Rule: Meme reference if context fits and enabled
    if prefs.get("memes") and random.random() < 0.20: # 20% chance
        return "Hehe, yeh toh full 'main character energy' wali baat hai! 😌"

    # Default playful reply
    return "Hmm, interesting... aur batao? Main sun rahi hoon. 👂"

def get_toggle_confirmation(feature: str, state: str) -> str:
    """Generates confirmation message for toggling features."""
    status = "on" if state == "on" else "off"
    emoji = "✅" if status == "on" else "❌"
    return f"Okay! Tumhare liye {feature} ab {status} hai. {emoji}"

def get_forget_confirmation() -> str:
    """Generates confirmation for forgetting a user."""
    return "Theek hai, main sab bhool gayi. Hum ab ajnabi hain... phir se! Chaho to /start se nayi shuruaat karein. 🫶"
