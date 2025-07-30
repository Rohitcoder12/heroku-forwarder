# main.py (Corrected for large Chat ID integer overflow)
import os
import re
import logging
import asyncio
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors.rpcerrorlist import MessageIdInvalidError

# --- Configuration ---
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)

# --- Read Environment Variables ---
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    OWNER_ID = int(os.environ.get("OWNER_ID"))
    LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID")
    if LOG_CHANNEL_ID: LOG_CHANNEL_ID = int(LOG_CHANNEL_ID)
    SOURCE_BOT_ID = os.environ.get("SOURCE_BOT_ID")
    if SOURCE_BOT_ID and SOURCE_BOT_ID.lstrip('-').isnumeric(): SOURCE_BOT_ID = int(SOURCE_BOT_ID)
except (TypeError, ValueError) as e:
    logging.critical(f"ERROR: A required environment variable is missing or invalid: {e}")
    exit(1)

# --- Initialize Clients ---
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# (The rest of the code is the same as before...)
# ... All helper functions and the auto_saver_handler remain unchanged ...

# ==============================================================================
# === HELPER FUNCTIONS ===
# ==============================================================================

async def log_message(message_to_log):
    if LOG_CHANNEL_ID and message_to_log:
        try:
            if isinstance(message_to_log, list): await bot_client.forward_messages(entity=LOG_CHANNEL_ID, messages=message_to_log)
            else: await bot_client.forward_messages(entity=LOG_CHANNEL_ID, messages=[message_to_log])
        except Exception as e: logging.error(f"Failed to log message: {e}")

async def process_and_send(message, destination):
    if message.media:
        file_path = await user_client.download_media(message, file=f"downloads/{message.id}")
        try:
            sent_message = await bot_client.send_file(destination, file=file_path, caption=message.text)
            return sent_message, file_path
        except Exception: os.remove(file_path); raise
    elif message.text:
        sent_message = await bot_client.send_message(destination, message.text)
        return sent_message, None
    return None, None

# ==============================================================================
# === AUTOMATIC SAVER (Now Album-Aware) ===
# ==============================================================================
if SOURCE_BOT_ID and LOG_CHANNEL_ID:
    processed_groups = set()
    @user_client.on(events.NewMessage(from_users=SOURCE_BOT_ID))
    async def auto_saver_handler(event):
        message = event.message; grouped_id = message.grouped_id
        if grouped_id and grouped_id in processed_groups: return
        if grouped_id: processed_groups.add(grouped_id); await asyncio.sleep(2)
        album_messages = await user_client.get_messages(message.chat_id, ids=grouped_id) if grouped_id else [message]
        logging.info(f"Auto-saving {len(album_messages)} message(s)...")
        media_to_send = []
        try:
            for msg in album_messages:
                downloaded_path = await user_client.download_media(msg, file=f"downloads/{msg.id}")
                media_to_send.append(downloaded_path)
            sent_messages = await bot_client.send_file(LOG_CHANNEL_ID, file=media_to_send, caption=album_messages[0].text if album_messages else "")
            await log_message(sent_messages)
        except Exception as e: logging.error(f"Auto-save failed for group {grouped_id}: {e}")
        finally:
            for path in media_to_send:
                if os.path.exists(path): os.remove(path)
            if grouped_id: await asyncio.sleep(60); processed_groups.discard(grouped_id)

# ==============================================================================
# === MANUAL SAVER (Now Album-Aware and with Large ID Fix) ===
# ==============================================================================
@bot_client.on(events.NewMessage(pattern='/start', from_users=OWNER_ID))
async def bot_start_handler(event):
    await event.reply("Album-Aware Saver Bot is running.")

@bot_client.on(events.NewMessage(pattern=r'https?://t\.me/.*', from_users=OWNER_ID))
async def main_link_handler(event):
    link = re.search(r'https?://t\.me/\S+', event.raw_text).group(0)
    reply_msg = await event.reply("⏳ `Processing link...`")
    
    try:
        match = re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', link)
        if not match: raise ValueError("Invalid link format.")
        
        is_private, chat_str, msg_id = match.groups()

        # ================== THE FIX IS HERE ==================
        # We explicitly handle the chat_id to ensure it's treated as a long integer
        if is_private:
            chat_id = int("-100" + chat_str)
        else:
            chat_id = chat_str # For public channels, it's a username string
        # =====================================================
        
        message = await user_client.get_messages(chat_id, ids=int(msg_id))
        if not message: raise ValueError("Message not found.")

        if message.grouped_id:
            await bot_client.edit_message(reply_msg, f"Album detected. Fetching group {message.grouped_id}...")
            album_messages = await user_client.get_messages(chat_id, ids=message.grouped_id)
        else:
            album_messages = [message]

        await bot_client.edit_message(reply_msg, f"Downloading {len(album_messages)} item(s)...")

        media_to_send = []; paths_to_clean = []
        try:
            for i, msg in enumerate(album_messages):
                path = await user_client.download_media(msg, file=f"downloads/{msg.id}")
                media_to_send.append(path); paths_to_clean.append(path)

            sent_messages = await bot_client.send_file(OWNER_ID, file=media_to_send, caption=album_messages[0].text if album_messages else "")
            await log_message(sent_messages)

        finally:
            for path in paths_to_clean:
                if os.path.exists(path): os.remove(path)

        await bot_client.delete_messages(event.chat_id, reply_msg)

    except Exception as e:
        await bot_client.edit_message(reply_msg, f"❌ **Error:** {e}")

# ==============================================================================
# === MAIN EXECUTION BLOCK ===
# ==============================================================================
async def main():
    if not os.path.isdir('downloads'): os.makedirs('downloads')
    await user_client.start()
    logging.info(f"User-Bot logged in as: {(await user_client.get_me()).first_name}")
    logging.info(f"Saver Bot running as: @{(await bot_client.get_me()).username}")
    if SOURCE_BOT_ID: logging.info(f"Auto-saver activated for source: {SOURCE_BOT_ID}")
    if LOG_CHANNEL_ID: logging.info(f"Logging enabled to channel: {LOG_CHANNEL_ID}")
    logging.info("System is live.")
    await user_client.run_until_disconnected()
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())