# main.py (Heroku Version)
import os
import json
import re
import logging
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message
from telethon.errors.rpcerrorlist import MessageIdInvalidError

# --- Basic Configuration ---
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)

# --- Read Configuration from Environment Variables ---
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    # This variable will hold our tasks as a JSON string
    FORWARDING_CONFIG_JSON = os.environ.get("FORWARDING_CONFIG_JSON", "{}")
except (TypeError, ValueError):
    logging.critical("ERROR: One or more required environment variables (API_ID, API_HASH, SESSION_STRING) are not set.")
    exit(1)

# --- In-memory storage for forwarding tasks ---
# We load this from the environment variable
forwarding_tasks = {}

def load_config():
    """Loads forwarding tasks from the environment variable."""
    global forwarding_tasks
    try:
        tasks = json.loads(FORWARDING_CONFIG_JSON)
        # JSON keys are strings, so we convert them to integers
        forwarding_tasks = {int(k): v for k, v in tasks.items()}
        logging.info(f"Configuration loaded with {len(forwarding_tasks)} tasks.")
    except json.JSONDecodeError:
        logging.error("Could not decode FORWARDING_CONFIG_JSON. Please check its format in Heroku Config Vars.")
        forwarding_tasks = {}

# --- Initialize the Telegram Client ---
try:
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
except Exception as e:
    logging.error(f"Failed to initialize Telegram client: {e}")
    exit(1)


# --- Command Handlers (Only you can use these) ---
# Note: The handlers are modified to guide the user on how to update the config on Heroku.

@client.on(events.NewMessage(pattern=r'/start', from_users='me'))
async def start_handler(event):
    await event.reply(
        "**Restricted Content Saver & Forwarder (Heroku Version)**\n\n"
        "I am running on your user account.\n\n"
        "**Commands:**\n"
        "`/add <source_id> <destination_id>`\n"
        "`/remove <source_id>`\n"
        "`/list`\n"
        "`/save <message_link>`\n\n"
        "**IMPORTANT:** After using `/add` or `/remove`, I will give you a new configuration string. You must copy it and update the `FORWARDING_CONFIG_JSON` variable in your Heroku app's settings."
    )

@client.on(events.NewMessage(pattern=r'/add (-?\d+|\w+) (-?\d+|\w+)', from_users='me'))
async def add_task_handler(event):
    try:
        source_input = event.pattern_match.group(1)
        dest_input = event.pattern_match.group(2)

        source_entity = await client.get_entity(source_input if not source_input.isnumeric() else int(source_input))
        dest_entity = await client.get_entity(dest_input if not dest_input.isnumeric() else int(dest_input))

        forwarding_tasks[source_entity.id] = dest_entity.id
        
        # Create the new JSON string for the user to copy
        new_config_json = json.dumps(forwarding_tasks, indent=4)
        
        await event.reply(
            f"✅ **Task Added!**\n\n"
            f"Now, please update your Heroku config. Go to your app's 'Settings' -> 'Reveal Config Vars' and set the key `FORWARDING_CONFIG_JSON` to the value below:\n\n"
            f"```json\n{new_config_json}\n```\n\n"
            "The bot will use the new settings after it restarts."
        )
    except Exception as e:
        await event.reply(f"❌ **Error:** Could not add task. `{e}`")

@client.on(events.NewMessage(pattern=r'/remove (-?\d+|\w+)', from_users='me'))
async def remove_task_handler(event):
    try:
        source_input = event.pattern_match.group(1)
        source_entity = await client.get_entity(source_input if not source_input.isnumeric() else int(source_input))

        if source_entity.id in forwarding_tasks:
            del forwarding_tasks[source_entity.id]
            new_config_json = json.dumps(forwarding_tasks, indent=4)
            await event.reply(
                f"🗑️ **Task Removed!**\n\n"
                f"Please update your `FORWARDING_CONFIG_JSON` in Heroku with the value below to make the change permanent:\n\n"
                f"```json\n{new_config_json}\n```"
            )
        else:
            await event.reply("🤔 **Not found:** No forwarding task exists for that source.")
    except Exception as e:
        await event.reply(f"❌ **Error:** Could not process removal. `{e}`")

# The /list, /save, and the main forwarder_handler remain the same as the previous version.
# They are included here for completeness.

@client.on(events.NewMessage(pattern=r'/list', from_users='me'))
async def list_tasks_handler(event):
    if not forwarding_tasks:
        await event.reply("No forwarding tasks are currently configured in `FORWARDING_CONFIG_JSON`.")
        return
    message = "**Active Forwarding Tasks (based on current config):**\n\n"
    for source_id, dest_id in forwarding_tasks.items():
        try:
            source = await client.get_entity(source_id)
            dest = await client.get_entity(dest_id)
            message += f"➡️ From: **{source.title}** (`{source_id}`)\n   To: **{dest.title}** (`{dest_id}`)\n\n"
        except Exception:
            message += f"➡️ From: ID `{source_id}`\n   To: ID `{dest_id}`\n\n"
    await event.reply(message)

@client.on(events.NewMessage(pattern=r'/save (.+)', from_users='me'))
async def save_post_handler(event):
    link = event.pattern_match.group(1)
    await event.edit("⏳ `Processing link...`")
    match = re.match(r'https://t.me/(c/)?(\w+)/(\d+)', link)
    if not match:
        await event.edit("❌ **Invalid Link**")
        return
    is_private, chat_id_str, msg_id = match.groups()
    try:
        chat = int(f"-100{chat_id_str}") if is_private else chat_id_str
        message_to_save = await client.get_messages(chat, ids=int(msg_id))
        if not message_to_save:
            raise ValueError("Message not found.")
        await client.send_message('me', message_to_save)
        await event.edit("✅ **Post Saved!**")
    except Exception as e:
        await event.edit(f"❌ **Error:**\n`{e}`")

@client.on(events.NewMessage)
async def forwarder_handler(event: events.NewMessage.Event):
    chat_id = event.chat_id
    if chat_id in forwarding_tasks:
        if chat_id in forwarding_tasks.values(): return
        destination_id = forwarding_tasks[chat_id]
        await client.send_message(destination_id, event.message)
        logging.info(f"Forwarded message from {chat_id} to {destination_id}")

# --- Main Execution Block ---
async def main():
    logging.info("Bot starting...")
    load_config()
    await client.start()
    me = await client.get_me()
    print(f"Logged in as {me.first_name} (@{me.username})")
    print("Bot is running. Listening for messages...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    client.loop.run_until_complete(main())
