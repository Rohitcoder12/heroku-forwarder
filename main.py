# main.py (Corrected version with manual download/upload)
import os
import re
import logging
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession

# --- Configuration ---
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)

# --- Read All Configuration from Environment Variables ---
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    OWNER_ID = int(os.environ.get("OWNER_ID"))
except (TypeError, ValueError) as e:
    logging.critical(f"ERROR: A required environment variable is missing or invalid: {e}")
    exit(1)

# --- Initialize BOTH clients ---
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


# ==============================================================================
# === REGULAR BOT HANDLERS (Your User Interface) ===
# ==============================================================================

@bot_client.on(events.NewMessage(pattern='/start', from_users=OWNER_ID))
async def bot_start_handler(event):
    await event.reply(
        "**Restricted Content Saver Bot**\n\n"
        "I am ready to save content for you.\n\n"
        "**Usage:**\n"
        "Just send me a link to a private/restricted Telegram post, and I will send it back to you."
    )

@bot_client.on(events.NewMessage(pattern=r'(?i).*/save|https?://t\.me/.*', from_users=OWNER_ID))
async def bot_save_handler(event):
    link_match = re.search(r'https?://t\.me/\S+', event.raw_text)
    if not link_match:
        await event.reply("Please send me a valid Telegram message link.")
        return
        
    link = link_match.group(0)
    reply_msg = await event.reply("⏳ `Processing link...`")
    
    try:
        match = re.match(r'https://t.me/(c/)?(\w+)/(\d+)', link)
        if not match:
            await bot_client.edit_message(reply_msg, "❌ **Invalid Link Format.**")
            return

        is_private, chat_id_str, msg_id = match.groups()
        chat = int(f"-100{chat_id_str}") if is_private else chat_id_str
        
        await bot_client.edit_message(reply_msg, "⏳ `Fetching message details...`")
        message_to_save = await user_client.get_messages(chat, ids=int(msg_id))
        
        if not message_to_save:
            raise ValueError("Message not found or I can't access it.")

        # ================== THE FIX IS HERE ==================
        # Instead of just sending the message object, we check if it has media.
        # If it does, we download it and re-upload it. If not, we just send the text.
        
        if message_to_save.media:
            await bot_client.edit_message(reply_msg, "⏳ `Bypassing restriction... Downloading file...`")
            # Download the media content into memory
            file_content = await user_client.download_media(message_to_save, file=bytes)
            
            await bot_client.edit_message(reply_msg, "⏳ `Uploading to you...`")
            # Send the downloaded content as a new file, with the original caption
            await user_client.send_file(
                OWNER_ID,
                file=file_content,
                caption=message_to_save.text
            )
        elif message_to_save.text:
            # If it's just a text message, send the text directly
            await user_client.send_message(OWNER_ID, message_to_save.text)
        else:
            # If the message is empty for some reason
            await bot_client.edit_message(reply_msg, "🤔 The message seems to be empty or unsupported.")
            return

        # ======================================================

        await bot_client.edit_message(reply_msg, "✅ **Post Saved!** I've sent it to your private chat.")

    except Exception as e:
        logging.error(f"Error processing link {link}: {e}")
        await bot_client.edit_message(reply_msg, f"❌ **An error occurred:**\n`{e}`")


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