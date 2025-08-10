import os
import io
import zipfile
import json
import requests
from telegram import Update, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

API_TIMEOUT = 10
API_URL = "https://gpt-3-5.apis-bj-devs.workers.dev/"
BOT_TOKEN = "7405849363:AAH3-6QuSUb2bJvTkpWfqoSlVKeYn-ERfpo"

RULES_FOLDER = "group_rules"
os.makedirs(RULES_FOLDER, exist_ok=True)

async def is_user_admin(chat: Chat, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await chat.get_member(user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

def load_rules(chat_id: int):
    path = os.path.join(RULES_FOLDER, f"{chat_id}.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_rules(chat_id: int, rules: dict):
    path = os.path.join(RULES_FOLDER, f"{chat_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)

def analyze_illegal_message(text: str) -> bool:
    keywords = ['buy', 'sell', 'number', 'account', 'contact']
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)

def analyze_with_api(text: str) -> bool:
    try:
        response = requests.get(API_URL, params={"prompt": text}, timeout=API_TIMEOUT)
        data = response.json()
        return data.get("status", False)
    except Exception:
        return False

def append_rules(chat_id: int, new_rule: str):
    rules_data = load_rules(chat_id)
    old_rules = rules_data.get("rules", "")
    if old_rules:
        # پہلے والے رولز کے ساتھ نیا رول شامل کر دو، new line کے ساتھ
        updated_rules = old_rules + "\n" + new_rule
    else:
        updated_rules = new_rule
    rules_data["rules"] = updated_rules
    save_rules(chat_id, rules_data)

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat = message.chat
    user = message.from_user

    # اگر sender admin ہے تو چیک نہ کریں
    if await is_user_admin(chat, user.id, context):
        return

    # اگر میسج میں لنک یا مینشن ہے یا فارورڈڈ ہے تو فوراً ایکشن کریں
    if message.entities:
        for ent in message.entities:
            if ent.type in ['url', 'mention', 'text_mention']:
                await message.reply_text("/action", reply_to_message_id=message.message_id)
                return
    if message.forward_date:
        await message.reply_text("/action", reply_to_message_id=message.message_id)
        return

    # رولز چیک کریں
    rules = load_rules(chat.id)
    if rules:
        if analyze_illegal_message(message.text) or analyze_with_api(message.text):
            await message.reply_text("/action", reply_to_message_id=message.message_id)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm your AI board. Use /setrules to set group rules.\n\n"
        "Usage:\n"
        "/setrules @groupusername <rules text>"
    )

async def setrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    args = context.args

    if len(args) < 2:
        await message.reply_text("Usage: /setrules @groupusername <rules>")
        return

    group_username = args[0]
    rules_text = " ".join(args[1:])

    if not group_username.startswith("@"):
        await message.reply_text("Please provide a valid group username starting with '@'")
        return

    try:
        chat = await context.bot.get_chat(group_username)
    except Exception:
        await message.reply_text(f"Invalid group username: {group_username}")
        return

    if not await is_user_admin(chat, message.from_user.id, context):
        await message.reply_text("You must be an admin of the group to set rules.")
        return

    if not await is_user_admin(chat, context.bot.id, context):
        await message.reply_text("Bot must be admin in the group to save rules.")
        return

    # پہلے سے موجود رولز لوڈ کریں
    existing_rules_data = load_rules(chat.id)
    existing_rules = existing_rules_data.get("rules", "")

    # اگر رولز پہلے سے موجود ہیں تو نئے رول کو نئی لائن کے ساتھ جوڑ دیں
    if existing_rules:
        updated_rules = existing_rules + "\n" + rules_text
    else:
        updated_rules = rules_text

    # اپڈیٹڈ رولز کو سیو کریں
    save_rules(chat.id, {"rules": updated_rules})

    await message.reply_text(f"Rules updated for group {chat.title}.")

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()

    # اگر میسج کمانڈ نہ ہو تو AI سے جواب لو
    if text.startswith("/"):
        await message.reply_text("Unknown command. Use /start or /setrules.")
        return

    try:
        response = requests.get(API_URL, params={"prompt": text}, timeout=API_TIMEOUT)
        data = response.json()
        ai_reply = data.get("result", "I couldn't understand that.")
    except Exception as e:
        ai_reply = f"Error: {e}"

    await message.reply_text(ai_reply)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if update.effective_chat.type != 'private':
        await message.reply_text("Backup command only works in private chat.")
        return

    rules_folder = RULES_FOLDER  # group_rules فولڈر
    bot_file = "bot.py"  # بوٹ ڈاٹ پی فائل

    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # group_rules فولڈر کی فائلز شامل کریں
        for root, dirs, files in os.walk(rules_folder):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, start=os.path.dirname(rules_folder))
                zf.write(filepath, arcname)

        # bot.py فائل شامل کریں اگر موجود ہو
        if os.path.isfile(bot_file):
            zf.write(bot_file, arcname=os.path.basename(bot_file))

    mem_zip.seek(0)
    await message.reply_document(document=mem_zip, filename="backup.zip", caption="Here's your backup.")

def main():
    application = Application.builder() \
        .token(BOT_TOKEN) \
        .read_timeout(API_TIMEOUT) \
        .write_timeout(API_TIMEOUT) \
        .connect_timeout(API_TIMEOUT) \
        .pool_timeout(API_TIMEOUT) \
        .get_updates_read_timeout(API_TIMEOUT) \
        .build()

    application.add_handler(CommandHandler("start", start_command, filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("setrules", setrules_command, filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("backup", backup_command, filters.ChatType.PRIVATE))

    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
        handle_private_message
    ))

    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        handle_group_message
    ))

    print("Bot is starting...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()