# main.py (Definitive Fix for Range Batch and All Features)
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
    if not message: return

    # Use a try-finally block to ensure cleanup happens
    paths_to_clean = []
    try:
        album_messages = []
        if message.grouped_id:
            album_messages = await user_client.get_messages(message.chat, ids=message.grouped_id)
            if not album_messages: album_messages = [message]
        else:
            album_messages = [message]

        media_to_send = []
        caption = album_messages[0].text
        
        for msg in album_messages:
            if msg and msg.media:
                path = await msg.download_media(file=f"downloads/{msg.id}")
                media_to_send.append(path)
                paths_to_clean.append(path)
        
        if media_to_send:
            await bot_client.send_file(destination_id, file=media_to_send, caption=caption)
        elif caption:
            await bot_client.send_message(destination_id, caption)
        
        # Return the grouped_id if it was an album, for tracking
        return message.grouped_id
    finally:
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
            if LOG_CHANNEL_ID: await send_clean_copy(message, LOG_CHANNEL_ID)

        # --- REBUILT RANGE BATCH MODE ---
        elif len(matches) == 2:
            start_id, end_id = sorted([int(m.group(3)) for m in matches])
            
            await bot_client.edit_message(reply_msg, f"Range detected. Fetching all messages from {start_id} to {end_id}...")
            
            # Fetch all messages in the range in one efficient call
            all_messages = await user_client.get_messages(chat_peer, min_id=start_id - 1, max_id=end_id + 1)
            
            if not all_messages: raise ValueError("No messages found in the specified range.")
            
            all_messages.reverse() # Sort from oldest to newest
            total_count = len(all_messages)
            
            processed_groups = set()
            for i, message in enumerate(all_messages, 1):
                if not message: continue

                # If we are processing an album, skip if we've already done this group
                if message.grouped_id and message.grouped_id in processed_groups:
                    continue

                await bot_client.edit_message(reply_msg, f"Processing {i}/{total_count} (ID: `{message.id}`)...")
                
                try:
                    # The helper function will handle if it's an album or single post
                    processed_group_id = await send_clean_copy(message, OWNER_ID)
                    if LOG_CHANNEL_ID: await send_clean_copy(message, LOG_CHANNEL_ID)

                    # If an album was processed, add its ID to our set
                    if processed_group_id:
                        processed_groups.add(processed_group_id)

                    await asyncio.sleep(3)
                except Exception as e:
                    logging.error(f"Error in batch for msg {message.id}: {e}")
                    await event.respond(f"⚠️ Skipped message `{message.id}` due to error.")
                    continue

            await bot_client.edit_message(reply_msg, "✅ Batch Complete!")
            return

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