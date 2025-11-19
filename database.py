# --- database.py ---

import sqlite3
from config import DB_NAME

def init_db():
    """Initializes the database and creates the users table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            meme_pref BOOLEAN NOT NULL DEFAULT 1,
            shayari_pref BOOLEAN NOT NULL DEFAULT 1,
            geeta_pref BOOLEAN NOT NULL DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def get_or_create_user(user_id: int, first_name: str):
    """Gets a user from the DB or creates a new one with default preferences."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", (user_id, first_name))
    conn.commit()
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    return user_data

def get_user_prefs(user_id: int):
    """Retrieves a user's preferences."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT meme_pref, shayari_pref, geeta_pref FROM users WHERE user_id = ?", (user_id,))
    prefs = cursor.fetchone()
    conn.close()
    if prefs:
        return {"memes": bool(prefs[0]), "shayari": bool(prefs[1]), "geeta": bool(prefs[2])}
    return None

def update_user_pref(user_id: int, pref_name: str, value: bool):
    """Updates a user's preference in the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Using f-string safely as pref_name is controlled internally
    query = f"UPDATE users SET {pref_name}_pref = ? WHERE user_id = ?"
    cursor.execute(query, (value, user_id))
    conn.commit()
    conn.close()

def delete_user_data(user_id: int):
    """Deletes a user's data from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_user_ids():
    """Fetches all user IDs for broadcasting."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return user_ids
