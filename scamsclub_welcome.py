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

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# 👋 Handle new members joining the group
@dp.message_handler(content_types=types.ContentType.NEW_CHAT_MEMBERS)
async def on_user_joined(message: types.Message):
    if message.chat.id != FREE_GROUP_ID:
        return

    for user in message.new_chat_members:
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
        await message.answer(welcome_text, reply_markup=keyboard)

# 💬 Handle /welcome command in private DM
@dp.message_handler(commands=["welcome"])
async def welcome_command(message: types.Message):
    await message.answer(
        "👋 Thanks for joining Scam’s Club Store 🏪\n\n"
        "You now have access to:\n"
        "📚 /methods – Explore simulated guides\n"
        "🛠 /tools – OTP bots, spoofers, etc.\n"
        "💳 /banklogs – Walkthroughs and log shops\n"
        "🎓 /mentorship – Learn 1-on-1 (mock)\n"
        "🧠 /faq – Learn the language\n"
        "📜 /terms – Simulation disclaimer\n\n"
        "DM @ScamsClub_Store if you need help."
    )

# 🚀 Launch the bot
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
