import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import os

# Enable logs
logging.basicConfig(level=logging.INFO)

# Use environment variable or fallback
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
FREE_GROUP_ID = int(os.getenv("FREE_GROUP_ID", "-1002019911042"))  # Scams Club
PAID_LINK = "https://t.me/ScamsClub_Bot?start=welcome"

bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# 🔔 When someone joins the free group, DM them or send welcome in group
@dp.chat_member_handler()
async def welcome_free_members(event: types.ChatMemberUpdated):
    if event.chat.id == FREE_GROUP_ID and event.new_chat_member.status == "member":
        user = event.new_chat_member.user

        welcome_text = (
            f"👋 Welcome <b>{user.full_name}</b> to <b>Scams Club</b> (invite-only community).\n\n"
            "This free group is just the beginning...\n\n"
            "<b>Scams Club Plus 🏪</b> gives you full access to:\n"
            "📚 Private guides & walkthroughs\n"
            "🛠 Premium OTP bots & spoofers\n"
            "🎓 Weekly mentorship sessions (mock)\n"
            "💳 Tools for digital simulations\n\n"
            "To join Scams Club Plus, pay with BTC and get auto-added after confirmation:"
        )

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                text="💳 Join Scams Club Plus",
                url=PAID_LINK
            )
        )

        await bot.send_message(chat_id=event.chat.id, text=welcome_text, reply_markup=keyboard)

# ✅ Optional: /welcome command in DM (if user presses button)
@dp.message_handler(commands=["welcome"])
async def handle_welcome(message: types.Message):
    await message.answer(
        "👋 Thanks for your interest in Scams Club Plus 🏪\n\n"
        "You’re just one step away from unlocking:\n"
        "📚 /methods – Private guides\n"
        "🛠 /tools – OTP bots, spoofers\n"
        "🎓 /mentorship – Weekly 1-on-1s\n"
        "💳 /banklogs – Full walkthroughs\n"
        "🧠 /faq – Learn the lingo\n"
        "📜 /terms – Legal disclaimer\n\n"
        "To join, click below and complete your BTC payment. You’ll be added automatically.",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("💸 Join Now", url=PAID_LINK)
        )
    )

# Run the bot
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
