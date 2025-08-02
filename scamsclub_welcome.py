import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# Enable logging
logging.basicConfig(level=logging.INFO)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
FREE_GROUP_ID = int(os.getenv("FREE_GROUP_ID"))

# Initialize bot
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# 👋 Handle new members joining the group
@dp.chat_member_handler()
async def handle_new_member(event: types.ChatMemberUpdated):
    if event.chat.id == FREE_GROUP_ID and event.new_chat_member.status == "member":
        user = event.new_chat_member.user

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                text="📩 Start Here",
                url="https://t.me/ScamsClub_Bot?start=welcome"
            )
        )

        welcome_text = (
            f"👋 Welcome <b>{user.full_name}</b> to <b>Scam’s Club 🏪</b>\n\n"
            "We share simulations of tools, walkthroughs, and methods (for educational use only).\n\n"
            "🔒 Want full access to Scam’s Club Plus?\n"
            "Click below to get started:"
        )

        await bot.send_message(chat_id=event.chat.id, text=welcome_text, reply_markup=keyboard)

# 💬 Handle /welcome command in private DM
@dp.message_handler(commands=["ping"])
async def ping(message: types.Message):
    await message.answer("✅ I'm alive and running!")
    

# 🚀 Run bot
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
