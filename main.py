# main.py (Final Definitive Fix for Batch Mode and All Features)
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
# === HELPER: Sends a list of messages as a clean copy (album or single) ===
# ==============================================================================
async def send_as_copy(messages_to_send, destination_id):
    if not messages_to_send: return

    paths_to_clean = []
    try:
        media_to_send = []
        caption = messages_to_send[0].text
        
        for msg in messages_to_send:
            if msg and msg.media:
                path = await msg.download_media(file=f"downloads/{msg.id}")
                paths_to_clean.append(path)
                media_to_send.append(path)
        
        if media_to_send:
            await bot_client.send_file(destination_id, file=media_to_send, caption=caption)
        elif caption:
            await bot_client.send_message(destination_id, caption)

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

        # --- SINGLE LINK MODE ---
        if len(matches) == 1:
            msg_id = int(matches[0].group(3))
            message = await user_client.get_messages(chat_peer, ids=msg_id)
            if not message: raise ValueError("Message not found.")

            messages_to_process = []
            if message.grouped_id:
                messages_to_process = await user_client.get_messages(chat_peer, ids=message.grouped_id)
            else:
                messages_to_process = [message]
            
            await send_as_copy(messages_to_process, OWNER_ID)
            if LOG_CHANNEL_ID: await send_as_copy(messages_to_process, LOG_CHANNEL_ID)

        # --- REBUILT RANGE BATCH MODE ---
        elif len(matches) == 2:
            start_id, end_id = sorted([int(m.group(3)) for m in matches])
            
            await bot_client.edit_message(reply_msg, f"Range detected. Fetching all messages from {start_id} to {end_id}...")
            
            all_messages_in_range = await user_client.get_messages(chat_peer, min_id=start_id - 1, max_id=end_id + 1)
            if not all_messages_in_range: raise ValueError("No messages found in the specified range.")
            
            all_messages_in_range.reverse()
            total_count = len(all_messages_in_range)
            
            processed_groups = set()
            for i, message in enumerate(all_messages_in_range, 1):
                if not message: continue

                try:
                    current_grouped_id = message.grouped_id
                    if current_grouped_id and current_grouped_id in processed_groups:
                        continue

                    await bot_client.edit_message(reply_msg, f"Processing {i}/{total_count} (ID: `{message.id}`)...")

                    messages_to_process = []
                    if current_grouped_id:
                        # Find all parts of this album within the list we already fetched
                        messages_to_process = [m for m in all_messages_in_range if m and m.grouped_id == current_grouped_id]
                        processed_groups.add(current_grouped_id)
                    else:
                        messages_to_process = [message]
                    
                    await send_as_copy(messages_to_process, OWNER_ID)
                    if LOG_CHANNEL_ID: await send_as_copy(messages_to_process, LOG_CHANNEL_ID)

                    await asyncio.sleep(4) # A slightly longer delay for batches
                except Exception as e:
                    logging.error(f"Error in batch for msg {message.id}: {e}")
                    await event.respond(f"⚠️ Skipped message `{message.id}` due to an error.")
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