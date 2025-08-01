# main.py (Definitive version with correct Album/Single/Range handling and clean logging)
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
# === CORE HELPER FUNCTION: To send a clean copy of any message ===
# ==============================================================================
async def send_clean_copy(message, destination_id):
    """
    Intelligently handles sending a clean copy of a message.
    It detects albums and sends them correctly.
    """
    if not message:
        return

    album_messages = []
    # 1. Check if the message is part of an album
    if message.grouped_id:
        # Fetch all messages that share the same group ID
        album_messages = await user_client.get_messages(message.chat, ids=message.grouped_id)
        if not album_messages: # Safety check
             album_messages = [message]
    else:
        # It's a single message
        album_messages = [message]

    media_to_send = []
    paths_to_clean = []
    caption = album_messages[0].text # Use caption from the first item
    
    try:
        # 2. Download all media in the message/album
        for msg in album_messages:
            if msg and msg.media:
                path = await msg.download_media(file=f"downloads/{msg.id}")
                media_to_send.append(path)
                paths_to_clean.append(path)
        
        # 3. Send the content
        if media_to_send:
            # send_file with a list of paths automatically creates an album
            await bot_client.send_file(destination_id, file=media_to_send, caption=caption)
        elif caption: # Handle text-only messages
             await bot_client.send_message(destination_id, caption)

    finally:
        # 4. Clean up all downloaded temporary files
        for path in paths_to_clean:
            if os.path.exists(path):
                os.remove(path)

# ==============================================================================
# === MAIN BOT HANDLER ===
# ==============================================================================
@bot_client.on(events.NewMessage(pattern='/start', from_users=OWNER_ID))
async def bot_start_handler(event):
    await event.reply(
        "**Advanced Content Saver**\n\n"
        "• **Single Post/Album:** Send 1 link.\n"
        "• **Batch Range:** Send 2 links to save everything in between."
    )

@bot_client.on(events.NewMessage(pattern=r'https?://t\.me/.*', from_users=OWNER_ID))
async def main_link_handler(event):
    links = re.findall(r'https?://t\.me/\S+', event.raw_text)
    if not links: return

    reply_msg = await event.reply("⏳ `Processing...`")
    
    try:
        # --- PARSE LINKS AND CHAT PEER ---
        matches = [re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', link) for link in links]
        if not all(matches): raise ValueError("Invalid link format.")
        
        first_chat_str = matches[0].group(2)
        if not all(m.group(2) == first_chat_str for m in matches):
            raise ValueError("All links must be from the same chat.")
            
        chat_peer = await user_client.get_entity(PeerChannel(int(first_chat_str)))

        # --- SINGLE LINK MODE (Handles both single posts and albums) ---
        if len(matches) == 1:
            msg_id = int(matches[0].group(3))
            message = await user_client.get_messages(chat_peer, ids=msg_id)
            if not message: raise ValueError("Message not found.")

            await bot_client.edit_message(reply_msg, "Saving post...")
            await send_clean_copy(message, OWNER_ID)
            if LOG_CHANNEL_ID:
                await send_clean_copy(message, LOG_CHANNEL_ID)

        # --- RANGE BATCH MODE (Processes each item in range individually) ---
        elif len(matches) == 2:
            start_id, end_id = sorted([int(m.group(3)) for m in matches])
            total_count = end_id - start_id + 1
            await bot_client.edit_message(reply_msg, f"Range detected. Processing {total_count} messages...")
            
            processed_groups = set() # To avoid saving the same album multiple times
            for i, msg_id in enumerate(range(start_id, end_id + 1)):
                await bot_client.edit_message(reply_msg, f"Processing {i+1}/{total_count} (ID: `{msg_id}`)...")
                try:
                    message = await user_client.get_messages(chat_peer, ids=msg_id)
                    if not message: continue

                    # If part of an album, check if we already processed this group
                    if message.grouped_id and message.grouped_id in processed_groups:
                        continue
                    
                    # Process and send the message/album
                    await send_clean_copy(message, OWNER_ID)
                    if LOG_CHANNEL_ID:
                        await send_clean_copy(message, LOG_CHANNEL_ID)

                    # If it was an album, mark the group as done
                    if message.grouped_id:
                        processed_groups.add(message.grouped_id)

                    await asyncio.sleep(3) # Prevent flood waits

                except Exception as e:
                    logging.error(f"Error in batch for msg {msg_id}: {e}")
                    continue # Continue to the next message
            
            await bot_client.edit_message(reply_msg, "✅ Batch Complete!")
            return # Don't delete the final status message for batches

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
    logging.info("System is live.")
    await user_client.run_until_disconnected()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())