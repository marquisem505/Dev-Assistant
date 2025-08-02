import os
import requests
import openai
import difflib
from base64 import b64encode, b64decode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# === 🔐 ENV & SETUP ===
BOT_TOKEN = "8497059006:AAGwlC2Rg4XcVdakNZ15WG2abNuwsPkaZmM"
ADMIN_ID = 6967780222  # Set your Telegram user ID
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_PAT = os.getenv("GITHUB_PAT")

# === 🧠 Repo Map ===
repo_map = {
    "nowbot": {
        "repo_owner": "marquisem505",
        "repo_name": "scams-plus-subscription-bot",
        "target_file": "now_bot.py",
        "railway_url": "https://scamsclub.store"
    },
    "devbot": {
        "repo_owner": "marquisem505",
        "repo_name": "scams-plus-dev-bot",
        "target_file": "dev_bot.py",
        "railway_url": "https://your-dev-railway-url.com"
    }
}

# === 🧠 GPT Ask ===
async def ask_gpt(prompt: str) -> str:
    openai.api_key = OPENAI_API_KEY
    res = openai.chat.completions.create(
        model="gpt-4",
        temperature=0.2,
        messages=[
            {"role": "system", "content": "You are a Python developer assistant. ONLY return raw .py file code. No explanations, no markdown, no comments."},
            {"role": "user", "content": prompt}
        ]
    )
    return res.choices[0].message.content

# === 📥 GitHub Get ===
def get_file(owner, repo, filepath):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GITHUB_PAT}"}
    res = requests.get(url, headers=headers).json()
    return b64decode(res["content"]).decode(), res["sha"]

# === 📤 GitHub Push ===
def push_file(owner, repo, filepath, new_code, sha):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GITHUB_PAT}"}
    payload = {
        "message": "Auto update from Dev Assistant Bot",
        "content": b64encode(new_code.encode()).decode(),
        "sha": sha,
        "branch": "main"
    }
    return requests.put(url, headers=headers, json=payload).ok

# === 🚀 Railway Deploy ===
def deploy(railway_url):
    try:
        res = requests.post(f"{railway_url}/__rebuild", timeout=10)
        return res.status_code in [200, 204]
    except:
        return False

# === 🧠 Instruction Handler ===
pending_changes = {}

async def handle_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ You're not allowed.")
        return

    text = update.message.text.strip()
    if ":" not in text:
        await update.message.reply_text("⚠️ Use format: `nowbot: your instruction here`")
        return

    target, prompt = text.split(":", 1)
    target = target.lower().strip()
    prompt = prompt.strip()
    config = repo_map.get(target)

    if not config:
        await update.message.reply_text("❌ Unknown bot target.")
        return

    await update.message.reply_text("✍️ Generating code update...")

    current_code, sha = get_file(config["repo_owner"], config["repo_name"], config["target_file"])
    new_code = await ask_gpt(
        f"""This is the full file for {target}:\n\n{current_code}\n\nUpdate it to:\n\n{prompt}"""
    )

    # 🧾 Show diff
    diff = list(difflib.unified_diff(
        current_code.splitlines(), new_code.splitlines(),
        fromfile="before.py", tofile="after.py", lineterm=""
    ))
    diff_preview = "\n".join(diff[:40]) + ("\n... (truncated)" if len(diff) > 40 else "")

    # 💾 Save pending
    pending_changes[update.effective_user.id] = {
        "code": new_code,
        "sha": sha,
        "config": config,
        "prompt": prompt,
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Push & Deploy", callback_data="push_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="push_cancel")]
    ])

    await update.message.reply_text(
        f"🧠 *Diff Preview:*\n```diff\n{diff_preview}\n```",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ✅ Button Handler ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = pending_changes.get(user_id)

    if not data:
        await query.edit_message_text("⛔️ No pending change.")
        return

    if query.data == "push_cancel":
        del pending_changes[user_id]
        await query.edit_message_text("❌ Cancelled.")
        return

    if query.data == "push_confirm":
        pushed = push_file(
            data["config"]["repo_owner"],
            data["config"]["repo_name"],
            data["config"]["target_file"],
            data["code"],
            data["sha"]
        )
        deployed = deploy(data["config"]["railway_url"])
        del pending_changes[user_id]

        status = "✅ Pushed and " + ("deployed!" if deployed else "deploy failed.")
        await query.edit_message_text(
            f"{status}\n\n📂 `{data['config']['target_file']}`\n📝 {data['prompt']}",
            parse_mode="Markdown"
        )

# === 🔔 Hello Command ===
async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Dev Assistant ready to write code on command.")

# === ▶️ Start Bot ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instruction))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
