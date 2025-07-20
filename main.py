# main.py (Unified Bot + User-Bot)
import os
import json
import re
import logging
from telethon.sync import TelegramClient, events

# --- Configuration ---
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)

# --- Read All Configuration from Environment Variables ---
try:
    # User-Bot credentials
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    
    # Regular Bot credentials
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    
    # Bot Owner and Control
    OWNER_ID = int(os.environ.get("OWNER_ID"))
    
    # Forwarding task persistence
    FORWARDING_CONFIG_JSON = os.environ.get("FORWARDING_CONFIG_JSON", "{}")

except (TypeError, ValueError) as e:
    logging.critical(f"ERROR: A required environment variable is missing or invalid: {e}")
    exit(1)

# --- In-memory storage for forwarding tasks ---
forwarding_tasks = {}

def load_config():
    """Loads forwarding tasks from the environment variable."""
    global forwarding_tasks
    try:
        tasks = json.loads(FORWARDING_CONFIG_JSON)
        forwarding_tasks = {int(k): v for k, v in tasks.items()}
        logging.info(f"Configuration loaded with {len(forwarding_tasks)} tasks.")
    except json.JSONDecodeError:
        logging.error("Could not decode FORWARDING_CONFIG_JSON. Starting with empty config.")
        forwarding_tasks = {}

# --- Initialize BOTH clients ---
# The user-bot client (does the heavy lifting)
user_client = TelegramClient(SESSION_STRING, API_ID, API_HASH)

# The regular bot client (the user interface)
bot_client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


# ==============================================================================
# === REGULAR BOT HANDLERS (Your User Interface) ===
# This section defines how you interact with your regular bot.
# It only accepts commands from YOU (the OWNER_ID).
# ==============================================================================

@bot_client.on(events.NewMessage(pattern='/start', from_users=OWNER_ID))
async def bot_start_handler(event):
    await event.reply(
        "**Restricted Content Saver & Forwarder**\n\n"
        "This is your command interface. The user-bot is working in the background.\n\n"
        "**Commands:**\n"
        "`/save <message_link>` - Save a single post.\n"
        "`/add <source> <destination>` - Add a forwarding task.\n"
        "`/remove <source>` - Remove a forwarding task.\n"
        "`/list` - List all active tasks.\n\n"
        "**IMPORTANT (Heroku):** Use `/add` or `/remove` will give you a new config string. You must update it in Heroku for the changes to be permanent."
    )

@bot_client.on(events.NewMessage(pattern=r'/save (.+)', from_users=OWNER_ID))
async def bot_save_handler(event):
    link = event.pattern_match.group(1)
    await event.reply("⏳ `Processing link... Please wait.`")
    
    try:
        # Use the user_client to process the link
        match = re.match(r'https://t.me/(c/)?(\w+)/(\d+)', link)
        if not match:
            await event.reply("❌ **Invalid Link.**")
            return

        is_private, chat_id_str, msg_id = match.groups()
        chat = int(f"-100{chat_id_str}") if is_private else chat_id_str
        
        # The user_client does the fetching
        message_to_save = await user_client.get_messages(chat, ids=int(msg_id))
        
        if not message_to_save:
            raise ValueError("Message not found or I can't access it.")

        # The user_client sends the saved message to the OWNER_ID (you)
        await user_client.send_message(OWNER_ID, message_to_save)
        await event.respond("✅ **Post Saved!** I've sent it to you.")

    except Exception as e:
        await event.reply(f"❌ **An unexpected error occurred:**\n`{e}`")

@bot_client.on(events.NewMessage(pattern=r'/add (-?\d+|\S+) (-?\d+|\S+)', from_users=OWNER_ID))
async def bot_add_handler(event):
    try:
        source_input = event.pattern_match.group(1)
        dest_input = event.pattern_match.group(2)
        
        # Use the user_client to verify entities
        source_entity = await user_client.get_entity(source_input if not source_input.lstrip('-').isnumeric() else int(source_input))
        dest_entity = await user_client.get_entity(dest_input if not dest_input.lstrip('-').isnumeric() else int(dest_input))

        forwarding_tasks[source_entity.id] = dest_entity.id
        new_config_json = json.dumps(forwarding_tasks, indent=4)
        
        await event.reply(
            f"✅ **Task Added to current session!**\n\n"
            f"To make this permanent, update your `FORWARDING_CONFIG_JSON` in Heroku with the value below:\n\n"
            f"```json\n{new_config_json}\n```"
        )
    except Exception as e:
        await event.reply(f"❌ **Error:** Could not add task. `{e}`")

@bot_client.on(events.NewMessage(pattern=r'/remove (-?\d+|\S+)', from_users=OWNER_ID))
async def bot_remove_handler(event):
    try:
        source_input = event.pattern_match.group(1)
        source_entity = await user_client.get_entity(source_input if not source_input.lstrip('-').isnumeric() else int(source_input))
        
        if source_entity.id in forwarding_tasks:
            del forwarding_tasks[source_entity.id]
            new_config_json = json.dumps(forwarding_tasks, indent=4)
            await event.reply(
                f"🗑️ **Task Removed from current session!**\n\n"
                f"Update `FORWARDING_CONFIG_JSON` in Heroku with the value below:\n\n"
                f"```json\n{new_config_json}\n```"
            )
        else:
            await event.reply("🤔 **Task not found.**")
    except Exception as e:
        await event.reply(f"❌ **Error:** `{e}`")

@bot_client.on(events.NewMessage(pattern=r'/list', from_users=OWNER_ID))
async def bot_list_handler(event):
    if not forwarding_tasks:
        await event.reply("No forwarding tasks are configured.")
        return
    message = "**Active Forwarding Tasks:**\n\n"
    for source_id, dest_id in forwarding_tasks.items():
        try:
            source = await user_client.get_entity(source_id)
            dest = await user_client.get_entity(dest_id)
            message += f"➡️ From: **{source.title}** (`{source_id}`)\n   To: **{dest.title}** (`{dest_id}`)\n\n"
        except Exception:
            message += f"➡️ From: ID `{source_id}`\n   To: ID `{dest_id}`\n\n"
    await event.reply(message)


# ==============================================================================
# === USER-BOT HANDLER (The Worker) ===
# This section listens for new messages in the source channels
# and performs the auto-forwarding.
# ==============================================================================

@user_client.on(events.NewMessage)
async def userbot_forwarder_handler(event):
    chat_id = event.chat_id
    if chat_id in forwarding_tasks:
        # Prevent forwarding loops
        if chat_id in forwarding_tasks.values(): return
        
        destination_id = forwarding_tasks[chat_id]
        await user_client.send_message(destination_id, event.message)
        logging.info(f"Auto-forwarded message from {chat_id} to {destination_id}")


# ==============================================================================
# === MAIN EXECUTION BLOCK ===
# ==============================================================================
async def main():
    # Load the config first
    load_config()
    
    # Start the user client
    await user_client.start()
    
    # The bot_client is already started when initialized
    
    user_me = await user_client.get_me()
    bot_me = await bot_client.get_me()
    
    logging.info(f"User-Bot logged in as: {user_me.first_name}")
    logging.info(f"Regular Bot running as: @{bot_me.username}")
    logging.info("System is live. Send /start to your bot.")
    
    # Run both clients until they are disconnected
    await user_client.run_until_disconnected()
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())
