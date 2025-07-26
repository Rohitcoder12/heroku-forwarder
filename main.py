# main.py (With Automatic Real-time Saver)
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
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    OWNER_ID = int(os.environ.get("OWNER_ID"))
    
    # Optional: The ID of your private log channel
    LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID")
    if LOG_CHANNEL_ID:
        LOG_CHANNEL_ID = int(LOG_CHANNEL_ID)

    # NEW: The ID or username of the source bot to monitor
    # Optional. If not set, this feature is disabled.
    SOURCE_BOT_ID = os.environ.get("SOURCE_BOT_ID")
    if SOURCE_BOT_ID and SOURCE_BOT_ID.lstrip('-').isnumeric():
        SOURCE_BOT_ID = int(SOURCE_BOT_ID)

except (TypeError, ValueError) as e:
    logging.critical(f"ERROR: A required environment variable is missing or invalid: {e}")
    exit(1)

# --- Initialize BOTH clients ---
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


# ==============================================================================
# === AUTOMATIC REAL-TIME SAVER ===
# This handler runs on the user_client to see messages from the source bot
# ==============================================================================
if SOURCE_BOT_ID and LOG_CHANNEL_ID:
    @user_client.on(events.NewMessage(from_users=SOURCE_BOT_ID))
    async def auto_saver_handler(event):
        """Monitors the source bot and auto-saves new videos to the log channel."""
        logging.info(f"New message received from source bot: {SOURCE_BOT_ID}")

        # Check if the message contains a video
        # Some bots send videos as documents, so we check the mime_type
        is_video = event.message.video or (
            event.message.document and 'video' in getattr(event.message.document, 'mime_type', '')
        )

        if is_video:
            logging.info("Video detected! Starting automatic save process...")
            try:
                # Use the reliable download-to-file and re-upload method
                file_path = await user_client.download_media(event.message)
                try:
                    await bot_client.send_file(
                        LOG_CHANNEL_ID,
                        file=file_path,
                        caption=event.message.text
                    )
                    logging.info(f"Successfully saved video from {SOURCE_BOT_ID} to log channel {LOG_CHANNEL_ID}")
                finally:
                    os.remove(file_path) # Clean up the temporary file
            except Exception as e:
                logging.error(f"Auto-save failed: {e}")
        else:
            logging.info("Message is not a video, ignoring.")

# ==============================================================================
# === MANUAL SAVER (Triggered by you via links) ===
# This section remains unchanged and will continue to work.
# ==============================================================================

@bot_client.on(events.NewMessage(pattern='/start', from_users=OWNER_ID))
async def bot_start_handler(event):
    await event.reply(
        "**Restricted Content Saver Bot**\n\n"
        "**Automatic Mode:** I am monitoring the source bot for new videos.\n"
        "**Manual Mode:** Send me links to save content manually."
    )

# The rest of the manual link-handling code is the same...
# (Helper function and link handler)

async def process_and_log_message(message_id, chat_id):
    try:
        message = await user_client.get_messages(chat_id, ids=message_id)
        if not message: raise ValueError("Message not found.")
        sent_message = None
        if message.media:
            file_path = await user_client.download_media(message)
            try:
                sent_message = await bot_client.send_file(OWNER_ID, file=file_path, caption=message.text)
            finally:
                os.remove(file_path)
        elif message.text:
            sent_message = await bot_client.send_message(OWNER_ID, message.text)
        else:
            return False
        if LOG_CHANNEL_ID and sent_message:
            await bot_client.forward_messages(entity=LOG_CHANNEL_ID, messages=sent_message)
        return True
    except Exception as e:
        logging.error(f"Manual save failed for message {message_id}: {e}")
        await bot_client.send_message(OWNER_ID, f"❌ Failed to save message `{message_id}`\n**Reason:** {e}")
        return False

@bot_client.on(events.NewMessage(pattern=r'https?://t\.me/.*', from_users=OWNER_ID))
async def main_link_handler(event):
    links = re.findall(r'https?://t\.me/\S+', event.raw_text)
    if not links: return
    reply_msg = await event.reply("⏳ `Analyzing links...`")
    if len(links) == 1:
        # ... single link logic ...
        await bot_client.edit_message(reply_msg, "Processing single link...")
        match = re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', links[0])
        if not match: await bot_client.edit_message(reply_msg, "❌ Invalid link format."); return
        is_private, chat_id_str, msg_id_str = match.groups()
        chat_id = int(f"-100{chat_id_str}") if is_private else chat_id_str
        msg_id = int(msg_id_str)
        await process_and_log_message(msg_id, chat_id)
        await bot_client.delete_messages(event.chat_id, reply_msg)
    elif len(links) == 2:
        # ... range batch logic ...
        try:
            start_match = re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', links[0])
            end_match = re.match(r'https?://t\.me/(c/)?(\w+)/(\d+)', links[1])
            if not start_match or not end_match: raise ValueError("Invalid link format.")
            start_chat_str = start_match.group(2)
            end_chat_str = end_match.group(2)
            if start_chat_str != end_chat_str: raise ValueError("Links must be from the same chat.")
            chat_id = int(f"-100{start_chat_str}") if start_match.group(1) else start_chat_str
            start_id, end_id = sorted([int(start_match.group(3)), int(end_match.group(3))])
            total_messages = (end_id - start_id) + 1
            await bot_client.edit_message(reply_msg, f"✅ Range detected. Saving {total_messages} messages...")
            success_count = 0
            for i, current_msg_id in enumerate(range(start_id, end_id + 1), 1):
                await bot_client.edit_message(reply_msg, f"Processing {i}/{total_messages}...")
                if await process_and_log_message(current_msg_id, chat_id):
                    success_count += 1
                await asyncio.sleep(3)
            await bot_client.edit_message(reply_msg, f"✅ **Batch Complete!** Saved {success_count}/{total_messages}.")
        except Exception as e:
            await bot_client.edit_message(reply_msg, f"❌ **Error:** {e}")
    else:
        await bot_client.edit_message(reply_msg, "Please send 1 or 2 links for manual save.")

# ==============================================================================
# === MAIN EXECUTION BLOCK ===
# ==============================================================================
async def main():
    await user_client.start()
    logging.info(f"User-Bot logged in as: {(await user_client.get_me()).first_name}")
    logging.info(f"Saver Bot running as: @{(await bot_client.get_me()).username}")
    if SOURCE_BOT_ID:
        logging.info(f"Auto-saver activated for source: {SOURCE_BOT_ID}")
    else:
        logging.info("Auto-saver is disabled (SOURCE_BOT_ID not set).")
    if LOG_CHANNEL_ID:
        logging.info(f"Logging enabled to channel: {LOG_CHANNEL_ID}")
    logging.info("System is live.")
    await user_client.run_until_disconnected()
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    user_client.loop.run_until_complete(main())