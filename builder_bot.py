# builder_bot.py (Advanced Version)
import os
import asyncio
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger('ConfigBuilderBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Config Builder Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID'))

if not BOT_TOKEN or not ADMIN_ID:
    logger.critical("FATAL: BOT_TOKEN and ADMIN_ID must be set!")
    exit()

# --- Bot and State Management ---
app = Client("config_builder_bot", bot_token=BOT_TOKEN, in_memory=True)
admin_filter = filters.user(ADMIN_ID)
builder_state = {} # Holds the configuration being built

# --- Helper Functions & Keyboards ---
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("/addrule"), KeyboardButton("/deleterule")],
        [KeyboardButton("/view"), KeyboardButton("/finish")]
    ],
    resize_keyboard=True
)

SKIP_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("/skip")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

def format_json_for_telegram(data):
    """Formats JSON and wraps it in a code block for easy copying."""
    pretty_json = json.dumps(data, indent=2)
    return f"<code>{pretty_json}</code>"

# --- Command Handlers ---
@app.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    # Initialize state for the user
    builder_state[ADMIN_ID] = {"rules": [], "state": "idle"}
    await message.reply_text(
        "👋 **Welcome to the Advanced Config Builder!**\n\n"
        "Use the buttons below to create your `CONFIG_JSON` for the forwarder bot.",
        reply_markup=MAIN_KEYBOARD
    )

@app.on_message(filters.command("addrule") & admin_filter)
async def add_rule_command(client, message: Message):
    if ADMIN_ID not in builder_state:
        await start_command(client, message) # Re-initialize if state is lost
    
    state = builder_state[ADMIN_ID]
    state["state"] = "awaiting_rule_name"
    await message.reply_text(
        "**Step 1: Rule Name**\n\n"
        "Please enter a unique name for this new rule (e.g., `crypto_news`). No spaces.",
        reply_markup=ReplyKeyboardRemove() # Remove the main keyboard
    )

@app.on_message(filters.command("deleterule") & admin_filter)
async def delete_rule_command(client, message: Message):
    state = builder_state.get(ADMIN_ID, {})
    rules = state.get("rules", [])
    
    if not rules:
        await message.reply_text("No rules to delete yet.", reply_markup=MAIN_KEYBOARD)
        return
        
    rule_names = [rule.get("name") for rule in rules]
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(name)] for name in rule_names],
        resize_keyboard=True, one_time_keyboard=True
    )
    state["state"] = "awaiting_deletion"
    await message.reply_text("Which rule would you like to delete?", reply_markup=keyboard)


@app.on_message(filters.command("view") & admin_filter)
async def view_command(client, message: Message):
    state = builder_state.get(ADMIN_ID, {})
    rules = state.get("rules", [])
    
    if not rules:
        await message.reply_text("You haven't built any rules yet.", reply_markup=MAIN_KEYBOARD)
        return
        
    final_json = {"rules": rules}
    await message.reply_text(format_json_for_telegram(final_json), reply_markup=MAIN_KEYBOARD)

@app.on_message(filters.command("finish") & admin_filter)
async def finish_command(client, message: Message):
    state = builder_state.get(ADMIN_ID, {})
    rules = state.get("rules", [])

    if not rules:
        await message.reply_text("You haven't built any rules yet.", reply_markup=MAIN_KEYBOARD)
        return

    final_json = {"rules": rules}
    await message.reply_text(
        "🎉 **Configuration Complete!**\n\n"
        "Copy the JSON below and paste it into the `CONFIG_JSON` environment variable for your forwarder bot.",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.reply_text(format_json_for_telegram(final_json))
    del builder_state[ADMIN_ID] # Clean up state

# --- Main Handler for Building Steps ---
@app.on_message(filters.private & admin_filter & ~filters.command(["start"]))
async def handle_builder_steps(client, message: Message):
    if ADMIN_ID not in builder_state: return
    
    state = builder_state[ADMIN_ID]
    current_state = state.get("state")
    user_input = message.text

    # Handle /skip command
    if user_input.lower() == '/skip':
        if current_state == "awaiting_keywords":
            state["state"] = "awaiting_replacements"
            await message.reply_text(
                "**Step 5: Replacements (Optional)**\n\n"
                "To replace text/links/emojis, send them in this format (one per line):\n"
                "`old text==new text`\n\n"
                "Press /skip to ignore.",
                reply_markup=SKIP_KEYBOARD
            )
        elif current_state == "awaiting_replacements":
            state["rules"].append(state["current_rule"])
            state["current_rule"] = {}
            state["state"] = "idle"
            await message.reply_text(
                "✅ **Rule Saved!**\n\nUse the menu to add another rule or finish.",
                reply_markup=MAIN_KEYBOARD
            )
        return

    # FSM (Finite State Machine) for building a rule
    if current_state == "awaiting_rule_name":
        state["current_rule"] = {"name": user_input} # Add name to the rule
        state["state"] = "awaiting_sources"
        await message.reply_text(
            "**Step 2: Sources**\n\nSend the chat IDs to forward **FROM**, separated by spaces."
        )
    elif current_state == "awaiting_sources":
        try:
            state["current_rule"]["from_chats"] = [int(i) for i in user_input.split()]
            state["state"] = "awaiting_destinations"
            await message.reply_text(
                "**Step 3: Destinations**\n\nSend the chat IDs to forward **TO**, separated by spaces."
            )
        except ValueError:
            await message.reply_text("❌ Invalid ID. Please send only numbers separated by spaces.")
    
    elif current_state == "awaiting_destinations":
        try:
            state["current_rule"]["to_chats"] = [int(i) for i in user_input.split()]
            state["state"] = "awaiting_keywords"
            await message.reply_text(
                "**Step 4: Keywords (Optional)**\n\n"
                "To only forward messages with specific words, send them separated by a comma.\n"
                "Example: `event, urgent`\n\n"
                "Press /skip to ignore.",
                reply_markup=SKIP_KEYBOARD
            )
        except ValueError:
            await message.reply_text("❌ Invalid ID. Please send only numbers separated by spaces.")

    elif current_state == "awaiting_keywords":
        state["current_rule"]["keywords"] = [k.strip() for k in user_input.split(',')]
        state["state"] = "awaiting_replacements"
        await message.reply_text(
            "**Step 5: Replacements (Optional)**\n\n"
            "To replace text/links/emojis, send them in this format (one per line):\n"
            "`old text==new text`\n"
            "`😢==😊`\n\n"
            "Press /skip to ignore.",
            reply_markup=SKIP_KEYBOARD
        )
    
    elif current_state == "awaiting_replacements":
        replacements = {}
        for line in user_input.split('\n'):
            if '==' in line:
                old, new = line.split('==', 1)
                replacements[old.strip()] = new.strip()
        state["current_rule"]["replacements"] = replacements
        
        state["rules"].append(state["current_rule"])
        state["current_rule"] = {}
        state["state"] = "idle"
        await message.reply_text(
            f"✅ **Rule '{state['rules'][-1]['name']}' Saved!**\n\nUse the menu to add another rule or finish.",
            reply_markup=MAIN_KEYBOARD
        )
    
    elif current_state == "awaiting_deletion":
        rule_to_delete = user_input
        # Find the rule and remove it
        state["rules"] = [rule for rule in state["rules"] if rule.get("name") != rule_to_delete]
        state["state"] = "idle"
        await message.reply_text(f"Rule '{rule_to_delete}' has been deleted.", reply_markup=MAIN_KEYBOARD)


# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Starting Config Builder Bot...")
    app.run()
