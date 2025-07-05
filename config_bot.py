# config_bot.py (FINAL DIAGNOSTIC VERSION)
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
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID'))
API_ID = int(os.environ.get('API_ID'))
API_HASH = os.environ.get('API_HASH')
KOYEB_API_TOKEN = os.environ.get('KOYEB_API_TOKEN')
TARGET_SERVICE_ID = os.environ.get('TARGET_SERVICE_ID')

KOYEB_API_URL = f"https://app.koyeb.com/v1/services/{TARGET_SERVICE_ID}"
KOYEB_HEADERS = {"Authorization": f"Bearer {KOYEB_API_TOKEN}", "Content-Type": "application/json"}

app = Client("config_bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
admin_filter = filters.user(ADMIN_ID)

# --- Bot Command Handlers ---

# NEW DIAGNOSTIC COMMAND - NO FILTER
@app.on_message(filters.command("id"))
async def id_command(client, message: Message):
    sender_id = message.from_user.id
    sender_id_type = type(sender_id).__name__
    admin_id_from_env = ADMIN_ID
    admin_id_type = type(admin_id_from_env).__name__
    is_match = sender_id == admin_id_from_env

    reply_text = (
        "🔬 **Diagnostic Report** 🔬\n\n"
        f"**The bot sees YOUR User ID as:**\n`{sender_id}` (Type: `{sender_id_type}`)\n\n"
        f"**The bot has this ADMIN_ID configured:**\n`{admin_id_from_env}` (Type: `{admin_id_type}`)\n\n"
        f"**Do they match exactly?** -> **{is_match}**"
    )
    await message.reply_text(reply_text)

@app.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text("👋 **Forwarder Config Manager**\n\nCommands: /getconfig, /setconfig, /redeploy")

# (The rest of your /getconfig, /setconfig commands go here)
# ...

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Config Manager Bot...")
    app.run()