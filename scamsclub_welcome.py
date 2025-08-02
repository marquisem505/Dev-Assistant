import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# Logging
logging.basicConfig(level=logging.INFO)

# ENV variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
FREE_GROUP_ID = int(os.getenv("FREE_GROUP_ID"))

# Bot & Dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# ✅ Trigger when new user joins group
@dp.chat_join_request_handler()
async def handle_join_request(join_request: types.ChatJoinRequest):
    user = join_request.from_user

    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("📩 Start Here", url="https://t.me/ScamsClub_Bot?start=welcome")
    )

    await bot.send_message(
        chat_id=user.id,
        text=f"👋 Welcome <b>{user.full_name}</b> to <b>Scam’s Club 🏪</b>!\n\n"
             "Tap below to learn about Scam’s Club Plus access:",
        reply_markup=keyboard
    )

# Auto Accept Join Request
#    await bot.approve_chat_join_request(chat_id=join_request.chat.id, user_id=user.id

# DM-only /welcome handler
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    if message.chat.type == "private":
        # Parse argument like "/start welcome"
        args = message.get_args()
        if args == "welcome":
            await message.delete()  # delete the /start message (optional)
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

# 🚀 Launch
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
