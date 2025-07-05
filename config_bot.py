# config_bot.py
import os
import asyncio
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
KOYEB_API_TOKEN = get_env('KOYEB_API_TOKEN', 'KOYEB_API_TOKEN not set!')
TARGET_SERVICE_ID = get_env('TARGET_SERVICE_ID', 'TARGET_SERVICE_ID for the forwarder bot is not set!')

KOYEB_API_URL = f"https://app.koyeb.com/v1/services/{TARGET_SERVICE_ID}"
KOYEB_HEADERS = {"Authorization": f"Bearer {KOYEB_API_TOKEN}", "Content-Type": "application/json"}

# --- Pyrogram Client ---
app = Client("config_bot_session", bot_token=BOT_TOKEN, in_memory=True)
admin_filter = filters.user(ADMIN_ID)

# --- Koyeb API Functions ---
def get_current_definition():
    try:
        response = requests.get(KOYEB_API_URL, headers=KOYEB_HEADERS)
        response.raise_for_status()
        return response.json().get("service", {}).get("definition", {})
    except Exception as e:
        logger.error(f"Failed to get Koyeb service definition: {e}")
        return None

def update_koyeb_env(new_env_vars):
    payload = {"definition": {"env": new_env_vars}}
    try:
        response = requests.patch(KOYEB_API_URL, headers=KOYEB_HEADERS, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to update Koyeb config: {e} - Response: {response.text}")
        return False

# --- Bot Command Handlers ---
@app.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text(
        "👋 **Forwarder Config Manager**\n\n"
        "Use this bot to manage the `CONFIG_JSON` for your main forwarder bot.\n\n"
        "**Commands:**\n"
        "`/getconfig` - View the current JSON config.\n"
        "`/setconfig` - Reply to a JSON message to set it as the new config.\n"
        "`/redeploy` - Manually trigger a redeploy of the forwarder bot."
    )

@app.on_message(filters.command("getconfig") & admin_filter)
async def get_config_command(client, message: Message):
    msg = await message.reply_text("Fetching config from Koyeb...")
    definition = get_current_definition()
    if not definition:
        await msg.edit_text("❌ Failed to fetch service definition."); return

    for env_var in definition.get("env", []):
        if env_var.get("key") == "CONFIG_JSON":
            try:
                # Format the JSON for pretty printing
                pretty_json = json.dumps(json.loads(env_var["value"]), indent=2)
                await msg.edit_text(f"Current `CONFIG_JSON`:\n\n<code>{pretty_json}</code>")
            except json.JSONDecodeError:
                await msg.edit_text(f"Found `CONFIG_JSON` but it contains invalid JSON:\n\n<code>{env_var['value']}</code>")
            return
    await msg.edit_text("`CONFIG_JSON` variable not found on the service.")

@app.on_message(filters.command("setconfig") & admin_filter)
async def set_config_command(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.reply_text("Please reply to a message containing the new JSON configuration."); return

    new_config_str = message.reply_to_message.text
    try:
        # Validate that the new string is valid JSON
        json.loads(new_config_str)
    except json.JSONDecodeError:
        await message.reply_text("❌ The replied message does not contain valid JSON. Please check the format."); return

    msg = await message.reply_text("Fetching current service definition...")
    definition = get_current_definition()
    if not definition:
        await msg.edit_text("❌ Failed to fetch service definition."); return

    env_vars = definition.get("env", [])
    config_found = False
    for i, env_var in enumerate(env_vars):
        if env_var.get("key") == "CONFIG_JSON":
            env_vars[i]["value"] = new_config_str
            config_found = True
            break
    if not config_found:
        env_vars.append({"key": "CONFIG_JSON", "value": new_config_str})
    
    await msg.edit_text("Updating config on Koyeb and triggering redeploy...")
    if update_koyeb_env(env_vars):
        await msg.edit_text("✅ Success! The new configuration has been set. The forwarder bot is now restarting.")
    else:
        await msg.edit_text("❌ Failed to update the configuration on Koyeb.")

@app.on_message(filters.command("redeploy") & admin_filter)
async def redeploy_command(client, message: Message):
    redeploy_url = f"{KOYEB_API_URL}/redeploy"
    try:
        response = requests.post(redeploy_url, headers=KOYEB_HEADERS)
        response.raise_for_status()
        await message.reply_text("✅ Redeploy command sent successfully!")
    except Exception as e:
        await message.reply_text(f"❌ Failed to trigger redeploy: {e}")

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Config Manager Bot...")
    app.run()
