# main.py (Definitive Fix for Large Chat ID and All Features)
import os
import re
import logging
import asyncio
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel

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
except (TypeError, ValueError) as e:
    logging.critical(f"ERROR: A required environment variable is missing or invalid: {e}")
    exit(1)

# --- Initialize Clients ---
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


# ==============================================================================
# === HELPER FUNCTIONS ===
# ==============================================================================
async def log_message(message_to_log):
    if LOG_CHANNEL_ID and message_to_log:
        try:
            if isinstance(message_to_log, list): await bot_client.forward_messages(entity=LOG_CHANNEL_ID, messages=message_to_log)
            else: await bot_client.forward_messages(entity=LOG_CHANNEL_ID, messages=[message_to_log])
        except Exception as e: logging.error(f"Failed to log message: {e}")

# ==============================================================================
# === MANUAL SAVER HANDLER ===
# ==============================================================================
@bot_client.on(events.NewMessage(pattern='/start', from_users=OWNER_ID))
async def bot_start_handler(event):
    await event.reply("Album-Aware Saver Bot is running. Send me 1 or 2 message links.")

@bot_client.on(events.NewMessage(pattern=r'https?://t\.me/.*', from_users=OWNER_ID))
async def main_link_handler(event):
    links = re.findall(r'https?://t\.me/\S+', event.raw_text)
    if not links: return

    reply_msg = await event.reply("⏳ `Processing...`")
    
    try:
        # --- PARSE LINKS AND CHAT ID ---
        matches = [re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', link) for link in links]
        if not all(matches): raise ValueError("One or more links have an invalid format.")

        # Ensure all links are from the same chat for simplicity
        first_chat_str = matches[0].group(2)
        if not all(m.group(2) == first_chat_str for m in matches):
            raise ValueError("All links must be from the same chat.")

        # ================== THE DEFINITIVE FIX ==================
        # Construct the peer using a method that supports large numbers
        # A private channel link t.me/c/123... has an ID of 123...
        # Telethon represents this as PeerChannel(channel_id=123...)
        # We don't need to add the -100 prefix ourselves.
        chat_peer = await user_client.get_entity(PeerChannel(int(first_chat_str)))
        # ========================================================

        # --- SINGLE LINK / ALBUM MODE ---
        if len(matches) == 1:
            msg_id = int(matches[0].group(3))
            message = await user_client.get_messages(chat_peer, ids=msg_id)
            if not message: raise ValueError("Message not found.")

            album_messages = []
            if message.grouped_id:
                await bot_client.edit_message(reply_msg, f"Album detected. Fetching group...")
                album_messages = await user_client.get_messages(chat_peer, ids=message.grouped_id)
            else:
                album_messages = [message]
            
            await bot_client.edit_message(reply_msg, f"Downloading {len(album_messages)} item(s)...")

        # --- RANGE BATCH MODE ---
        elif len(matches) == 2:
            start_id, end_id = sorted([int(m.group(3)) for m in matches])
            total_count = end_id - start_id + 1
            await bot_client.edit_message(reply_msg, f"Range detected. Fetching {total_count} messages...")
            # Fetch all messages in the range at once
            album_messages = await user_client.get_messages(chat_peer, min_id=start_id-1, max_id=end_id+1, limit=total_count)
            album_messages.reverse() # a-z
        else:
            raise ValueError("Please send either 1 link or 2 links.")

        # --- COMMON PROCESSING FOR ALL MODES ---
        media_to_send = []; paths_to_clean = []
        try:
            for i, msg in enumerate(album_messages):
                if not msg or not msg.media: continue # Skip text-only or empty messages in albums/ranges
                await bot_client.edit_message(reply_msg, f"Downloading item {i+1}/{len(album_messages)}...")
                path = await msg.download_media(file=f"downloads/{msg.id}")
                media_to_send.append(path); paths_to_clean.append(path)

            if not media_to_send:
                raise ValueError("No media found in the specified message(s).")
                
            await bot_client.edit_message(reply_msg, f"Uploading {len(media_to_send)} item(s)...")
            
            # Send as a grouped album
            sent_messages = await bot_client.send_file(
                OWNER_ID,
                file=media_to_send,
                caption=album_messages[0].text if album_messages else ""
            )
            await log_message(sent_messages)

        finally:
            for path in paths_to_clean:
                if os.path.exists(path): os.remove(path)

        await bot_client.delete_messages(event.chat_id, reply_msg)

    except Exception as e:
        logging.error(f"Handler failed: {e}")
        await bot_client.edit_message(reply_msg, f"❌ **Error:** {e}")

# ==============================================================================
# === MAIN EXECUTION BLOCK ===
# ==============================================================================
async def main():
    if not os.path.isdir('downloads'): os.makedirs('downloads')
    await user_client.start()
    logging.info(f"User-Bot logged in as: {(await user_client.get_me()).first_name}")
    logging.info(f"Saver Bot running as: @{(await bot_client.get_me()).username}")
    if LOG_CHANNEL_ID: logging.info(f"Logging enabled to channel: {LOG_CHANNEL_ID}")
    logging.info("System is live.")
    await user_client.run_until_disconnected()
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())