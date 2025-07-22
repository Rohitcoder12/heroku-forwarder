# main.py (Restricted Content Saver ONLY)
import os
import re
import logging
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession

# --- Configuration ---
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)

# --- Read All Configuration from Environment Variables ---
try:
    # User-Bot credentials (to access restricted content)
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    
    # Regular Bot credentials (the user interface)
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    
    # Bot Owner (for security, only you can use it)
    OWNER_ID = int(os.environ.get("OWNER_ID"))

except (TypeError, ValueError) as e:
    logging.critical(f"ERROR: A required environment variable is missing or invalid: {e}")
    exit(1)

# --- Initialize BOTH clients ---
# The user-bot client (does the heavy lifting)
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

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
        "**Restricted Content Saver Bot**\n\n"
        "I am ready to save content for you.\n\n"
        "**Usage:**\n"
        "Just send me a link to a private/restricted Telegram post, and I will send it back to you.\n\n"
        "**Command:**\n"
        "`/save <message_link>`"
    )

# This handler now accepts any message that looks like a Telegram link,
# in addition to the /save command for ease of use.
@bot_client.on(events.NewMessage(pattern=r'(?i).*/save|https?://t\.me/.*', from_users=OWNER_ID))
async def bot_save_handler(event):
    # Find the link in the message text
    link_match = re.search(r'https?://t\.me/\S+', event.raw_text)
    if not link_match:
        await event.reply("Please send me a valid Telegram message link.")
        return
        
    link = link_match.group(0)
    
    # Acknowledge the request
    reply_msg = await event.reply("⏳ `Processing link... Please wait.`")
    
    try:
        # Regex to parse the link
        match = re.match(r'https://t.me/(c/)?(\w+)/(\d+)', link)
        if not match:
            await bot_client.edit_message(reply_msg, "❌ **Invalid Link Format.** Please provide a direct link to a message.")
            return

        is_private, chat_id_str, msg_id = match.groups()
        # For private channels (e.g., t.me/c/12345...), the chat ID is prefixed with -100
        chat = int(f"-100{chat_id_str}") if is_private else chat_id_str
        
        # The user_client does the fetching from the restricted channel
        message_to_save = await user_client.get_messages(chat, ids=int(msg_id))
        
        if not message_to_save:
            raise ValueError("Message not found. Make sure the link is correct and your account has access.")

        # The user_client sends the saved message to the OWNER_ID (you)
        await user_client.send_message(OWNER_ID, message_to_save)
        
        # Confirm completion in the bot chat
        await bot_client.edit_message(reply_msg, "✅ **Post Saved!** I've sent it to your private chat with me.")

    except Exception as e:
        logging.error(f"Error processing link {link}: {e}")
        await bot_client.edit_message(reply_msg, f"❌ **An error occurred:**\n`{e}`")


# ==============================================================================
# === MAIN EXECUTION BLOCK ===
# ==============================================================================
async def main():
    # Start the user client first
    await user_client.start()
    
    # The bot_client is already started when it was initialized
    
    user_me = await user_client.get_me()
    bot_me = await bot_client.get_me()
    
    logging.info(f"User-Bot logged in as: {user_me.first_name}")
    logging.info(f"Saver Bot running as: @{bot_me.username}")
    logging.info("System is live. Send /start to your bot.")
    
    # Run both clients until they are disconnected
    await user_client.run_until_disconnected()
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())