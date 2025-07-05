# config_bot.py (Corrected for Render)
import os
import threading
import json
import logging
import requests
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger('ConfigBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Config Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
def get_env(name, message, required=True, cast=str):
    val = os.environ.get(name)
    if val: return cast(val)
    if required: logging.critical(message); exit(1)
    return None

BOT_TOKEN = get_env('BOT_TOKEN', 'BOT_TOKEN not set!')
ADMIN_ID = get_env('ADMIN_ID', 'ADMIN_ID not set!', cast=int)
API_ID = get_env('API_ID', 'API_ID not set!', cast=int)     # <--- ADDED
API_HASH = get_env('API_HASH', 'API_HASH not set!')       # <--- ADDED
KOYEB_API_TOKEN = get_env('KOYEB_API_TOKEN', 'KOYEB_API_TOKEN not set!')
TARGET_SERVICE_ID = get_env('TARGET_SERVICE_ID', 'TARGET_SERVICE_ID for the forwarder bot is not set!')

KOYEB_API_URL = f"https://app.koyeb.com/v1/services/{TARGET_SERVICE_ID}"
KOYEB_HEADERS = {"Authorization": f"Bearer {KOYEB_API_TOKEN}", "Content-Type": "application/json"}

# --- Pyrogram Client ---
# THIS IS THE CORRECTED INITIALIZATION
app = Client(
    "config_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)
admin_filter = filters.user(ADMIN_ID)

# (The rest of the code is unchanged and can remain as it was)
# ... /start, /getconfig, /setconfig handlers ...

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Config Manager Bot...")
    app.run()