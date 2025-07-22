# main.py (With Single and Range Batch Save)
import os
import re
import logging
import asyncio
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors.rpcerrorlist import MessageIdInvalidError

# --- Configuration ---
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)

# --- Read All Configuration from Environment Variables ---
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASHSESSION_STRING = os.environ.get("SESSION_STRING")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    OWNER_ID = int(os.environ.get("OWNER_ID"))
except (TypeError, ValueError) as e:
    logging.critical(f"ERROR: A required environment variable is missing or invalid: {e}")
    exit(1)

# --- Initialize BOTH clients ---
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


# ==============================================================================
# === HELPER FUNCTION TO PROCESS A SINGLE MESSAGE ===
# ==============================================================================
async def process_message(message_id, chat_id, reply_msg):
    """Fetches, saves, and sends a single message by its ID."""
    try:
        message = await user_client.get_messages(chat_id, ids=message_id)
        if not message:
            raise ValueError("Message not found (might have been deleted).")

        if message.media:
            file_path = await user_client.download_media(message)
            try:
                await bot_client.send_file(OWNER_ID, file=file_path, caption=message.text)
            finally:
                os.remove(file_path)
        elif message.text:
            await bot_client.send_message(OWNER_ID, message.text)
        else:
            return False # Skip empty messages
        
        return True # Success
        
    except MessageIdInvalidError:
        logging.warning(f"Message ID {message_id} is invalid or deleted. Skipping.")
        return False # This ID doesn't exist, so we skip it.
    except Exception as e:
        logging.error(f"Failed to process message {message_id}: {e}")
        await bot_client.send_message(OWNER_ID, f"❌ Failed to save message `{message_id}`\n**Reason:** {e}")
        return False


# ==============================================================================
# === MAIN BOT HANDLER ===
# ==============================================================================

@bot_client.on(events.NewMessage(pattern='/start', from_users=OWNER_ID))
async def bot_start_handler(event):
    await event.reply(
        "**Restricted Content Saver Bot**\n\n"
        "I can save posts in two ways:\n\n"
        "**1. Single Mode:**\n"
        "Send me one Telegram message link to save that specific post.\n\n"
        "**2. Range Batch Mode:**\n"
        "Send me a message containing exactly **two links** (the start and end message). I will download everything between them (inclusive)."
    )

@bot_client.on(events.NewMessage(pattern=r'https?://t\.me/.*', from_users=OWNER_ID))
async def bot_save_handler(event):
    links = re.findall(r'https?://t\.me/\S+', event.raw_text)
    if not links:
        return

    reply_msg = await event.reply("⏳ `Analyzing links...`")

    # --- SINGLE LINK MODE ---
    if len(links) == 1:
        await bot_client.edit_message(reply_msg, "Processing single link...")
        match = re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', links[0])
        if not match:
            await bot_client.edit_message(reply_msg, "❌ Invalid link format.")
            return

        is_private, chat_id_str, msg_id_str = match.groups()
        chat_id = int(f"-100{chat_id_str}") if is_private else chat_id_str
        msg_id = int(msg_id_str)
        
        await process_message(msg_id, chat_id, reply_msg)
        await bot_client.delete_messages(event.chat_id, reply_msg)

    # --- RANGE BATCH MODE ---
    elif len(links) == 2:
        try:
            # Parse start link
            start_match = re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', links[0])
            # Parse end link
            end_match = re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', links[1])

            if not start_match or not end_match:
                raise ValueError("One or both links have an invalid format.")

            start_is_private, start_chat_str, start_id_str = start_match.groups()
            end_is_private, end_chat_str, end_id_str = end_match.groups()
            
            # Ensure links are from the same chat
            if start_chat_str != end_chat_str:
                raise ValueError("Links are from different chats. Batch mode requires both links to be from the same chat.")

            chat_id = int(f"-100{start_chat_str}") if start_is_private else start_chat_str
            start_id = int(start_id_str)
            end_id = int(end_id_str)

            # Ensure start ID is less than end ID
            if start_id > end_id:
                start_id, end_id = end_id, start_id # Swap them

            total_messages = (end_id - start_id) + 1
            await bot_client.edit_message(reply_msg, f"✅ Range detected. Starting batch save for {total_messages} messages...")
            
            success_count = 0
            # Iterate through the entire range of message IDs
            for i, current_msg_id in enumerate(range(start_id, end_id + 1), 1):
                await bot_client.edit_message(reply_msg, f"Processing message {i}/{total_messages} (ID: `{current_msg_id}`)...")
                if await process_message(current_msg_id, chat_id, reply_msg):
                    success_count += 1
                
                # Add a delay to prevent flooding Telegram's API
                await asyncio.sleep(3)

            await bot_client.edit_message(reply_msg, f"✅ **Batch Complete!**\nSaved {success_count}/{total_messages} messages.")

        except ValueError as e:
            await bot_client.edit_message(reply_msg, f"❌ **Error:** {e}")
        except Exception as e:
            await bot_client.edit_message(reply_msg, f"❌ **An unexpected error occurred:**\n`{e}`")

    # --- INVALID NUMBER OF LINKS ---
    else:
        await bot_client.edit_message(reply_msg, "Please send either 1 link for a single save, or 2 links for a range batch save.")


# ==============================================================================
# === MAIN EXECUTION BLOCK ===
# ==============================================================================
async def main():
    await user_client.start()
    user_me = await user_client.get_me()
    bot_me = await bot_client.get_me()
    
    logging.info(f"User-Bot logged in as: {user_me.first_name}")
    logging.info(f"Saver Bot running as: @{bot_me.username}")
    logging.info("System is live. Send /start to your bot.")
    
    await user_client.run_until_disconnected()
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())