import os
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

# Increased timeout for API requests
API_TIMEOUT = 10
API_URL = "https://gpt-3-5.apis-bj-devs.workers.dev/"
BOT_TOKEN = "7405849363:AAH3-6QuSUb2bJvTkpWfqoSlVKeYn-ERfpo"

# فولڈر جہاں گروپ رولز فائلز سیو ہوں گی
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
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_rules(chat_id: int, rules: dict):
    path = os.path.join(RULES_FOLDER, f"{chat_id}.json")
    with open(path, "w") as f:
        json.dump(rules, f, indent=2)

def analyze_illegal_message(text: str) -> bool:
    keywords = ['buy', 'sell', 'number', 'account', 'contact']
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)

import aiohttp

async def analyze_with_api(text: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(API_URL, params={"prompt": text}, timeout=API_TIMEOUT) as resp:
                data = await resp.json()
                return data.get("status", False)
        except Exception as e:
            print("API error:", e)
            return False

# اسی طرح handle_private_message کے اندر بھی
async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    text = message.text or ""
    
    # ... (باقی کوڈ)
    
    # اگر کمانڈ /setrules ہے
    if text.startswith("/setrules"):
        # فارمیٹ: /setrules @groupusername rules here...
        parts = text.split(None, 2)
        if len(parts) < 3:
            await message.reply_text("Usage: /setrules @groupusername <rules>")
            return

        group_username = parts[1]
        rules_text = parts[2]

        # چیک کریں کہ @ لگا ہے
        if not group_username.startswith("@"):
            await message.reply_text("Please provide a valid group username starting with '@'")
            return

        try:
            # یوزر نیم سے گروپ کی ڈیٹیل لیں
            chat = await context.bot.get_chat(group_username)
        except Exception as e:
            await message.reply_text(f"Invalid group username: {group_username}")
            return

        # چیک کریں یوزر گروپ کا ایڈمن ہے
        if not await is_user_admin(chat, message.from_user.id, context):
            await message.reply_text("You must be an admin of the group to set rules.")
            return

        # چیک کریں بوٹ خود بھی گروپ کا ایڈمن ہے
        if not await is_user_admin(chat, context.bot.id, context):
            await message.reply_text("Bot must be admin in the group to save rules.")
            return

        # رولز سیو کریں (گروپ ID کی بنیاد پر)
        save_rules(chat.id, {"rules": rules_text})
        await message.reply_text(f"Rules saved for group {chat.title}.")

        return  # یہاں ختم کر دیں تاکہ نیچے والا AI ریپلائی نہ دے

    # ----- سکرپٹ ڈیٹیکشن -----
    if "\n" in text and len(text.split("\n")) > 3 and any(sym in text for sym in ["{", "}", ";", "=", "(", ")"]):
        try:
            lang = detect(text)
        except:
            lang = "en"

        if lang == "ur":
            reply_text = "بھائی میں سکرپٹیں وغیرہ نہیں، صرف آپ سے بات چیت کر سکتا ہوں اور سوالوں کے جواب دے سکتا ہوں۔"
        else:
            reply_text = "I cannot process scripts. I can only chat with you and answer your questions."

        await message.reply_text(reply_text)
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params={"prompt": text}, timeout=API_TIMEOUT) as resp:
                data = await resp.json()
                ai_reply = data.get("result", "I couldn't understand that.")
    except Exception as e:
        ai_reply = f"Error: {e}"

    await message.reply_text(ai_reply)

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
        
    chat = message.chat
    user = message.from_user

    # اگر sender ایڈمن ہے تو ignore کریں
    if await is_user_admin(chat, user.id, context):
        return

    # اگر میسج لنک، مینشن یا فارورڈڈ ہے تو فوراً ایکشن دے دیں
    if message.entities or message.forward_date:
        # entities میں لنک یا مینشن چیک کریں
        for ent in message.entities or []:
            if ent.type in ['url', 'mention', 'text_mention']:
                await message.reply_text("/mute", reply_to_message_id=message.message_id)
                return
        if message.forward_date:
            await message.reply_text("/mute", reply_to_message_id=message.message_id)
            return

    # باقی میسجز کا AI سے اینالائز کریں
    rules = load_rules(chat.id)

    # اگر رولز موجود ہیں تو ان کی بنیاد پر چیک کریں
    if rules:
        # سادہ کی ورڈ چیک (آپ API call بھی لگا سکتے ہیں)
        if analyze_illegal_message(message.text or "") or analyze_with_api(message.text or ""):
            await message.reply_text("/mute", reply_to_message_id=message.message_id)

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("setrules", "Set group rules"),
    ])
    
from langdetect import detect

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm your AI board. Use /setrules to set group rules."
    )
"""
async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
        
    text = message.text or ""

    # اگر کمانڈ /setrules ہے
    if text.startswith("/setrules"):
        # فارمیٹ: /setrules @groupusername rules here...
        parts = text.split(None, 2)
        if len(parts) < 3:
            await message.reply_text("Usage: /setrules @groupusername <rules>")
            return

        group_username = parts[1]
        rules_text = parts[2]

        # چیک کریں کہ @ لگا ہے
        if not group_username.startswith("@"):
            await message.reply_text("Please provide a valid group username starting with '@'")
            return

        try:
            # یوزر نیم سے گروپ کی ڈیٹیل لیں
            chat = await context.bot.get_chat(group_username)
        except Exception as e:
            await message.reply_text(f"Invalid group username: {group_username}")
            return

        # چیک کریں یوزر گروپ کا ایڈمن ہے
        if not await is_user_admin(chat, message.from_user.id, context):
            await message.reply_text("You must be an admin of the group to set rules.")
            return

        # چیک کریں بوٹ خود بھی گروپ کا ایڈمن ہے
        if not await is_user_admin(chat, context.bot.id, context):
            await message.reply_text("Bot must be admin in the group to save rules.")
            return

        # رولز سیو کریں (گروپ ID کی بنیاد پر)
        save_rules(chat.id, {"rules": rules_text})
        await message.reply_text(f"Rules saved for group {chat.title}.")

        return  # یہاں ختم کر دیں تاکہ نیچے والا AI ریپلائی نہ دے

    # ----- سکرپٹ ڈیٹیکشن -----
    if "\n" in text and len(text.split("\n")) > 3 and any(sym in text for sym in ["{", "}", ";", "=", "(", ")"]):
        try:
            lang = detect(text)
        except:
            lang = "en"

        if lang == "ur":
            reply_text = "بھائی میں سکرپٹیں وغیرہ نہیں، صرف آپ سے بات چیت کر سکتا ہوں اور سوالوں کے جواب دے سکتا ہوں۔"
        else:
            reply_text = "I cannot process scripts. I can only chat with you and answer your questions."

        await message.reply_text(reply_text)
        return

    # ----- باقی نارمل چیٹ -----
    try:
        response = requests.get(API_URL, params={"prompt": text}, timeout=API_TIMEOUT)
        data = response.json()
        ai_reply = data.get("result", "I couldn't understand that.")
    except Exception as e:
        ai_reply = f"Error: {e}"

    await message.reply_text(ai_reply)
"""

def main():
    try:
        application = Application.builder() \
            .token(BOT_TOKEN) \
            .read_timeout(API_TIMEOUT) \
            .write_timeout(API_TIMEOUT) \
            .connect_timeout(API_TIMEOUT) \
            .pool_timeout(API_TIMEOUT) \
            .get_updates_read_timeout(API_TIMEOUT) \
            .post_init(post_init) \
            .build()

        # گروپ ہینڈلر
        application.add_handler(MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            handle_group_message
        ))

        # پرسنل میں /start
        application.add_handler(CommandHandler("start", start_command, filters.ChatType.PRIVATE))

        # پرسنل نارمل چیٹ
        application.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            handle_private_message
        ))

        print("Bot is starting...")
        application.run_polling(
            poll_interval=1.0,
            timeout=API_TIMEOUT,
            drop_pending_updates=True
        )
    except Exception as e:
        print(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()