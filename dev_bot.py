import os
import json
import requests
import openai
import difflib
from base64 import b64encode, b64decode
from datetime import datetime
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

MEMORY_FILE = "memory.json"

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

pending_changes = {}

# === 🔁 Memory Helpers ===
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"nowbot": [], "devbot": []}
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def append_memory(bot_key, role, content):
    memory = load_memory()
    memory[bot_key].append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })
    memory[bot_key] = memory[bot_key][-10:]  # Keep last 10
    save_memory(memory)

# === 🔌 GPT for Code Updates ===
async def ask_gpt_code(bot_key, current_code, prompt):
    openai.api_key = OPENAI_API_KEY
    memory = load_memory()[bot_key][-6:]

    messages = [
        {"role": "system", "content": f"You are a Python developer assistant working on {bot_key}. Only return raw .py code. No markdown."},
        *[{"role": m["role"], "content": m["content"]} for m in memory],
        {"role": "user", "content": f"This is the full file:\n\n{current_code}\n\nUpdate it to:\n\n{prompt}"}
    ]

    res = openai.chat.completions.create(
        model="gpt-4",
        temperature=0.2,
        messages=messages
    )
    return res.choices[0].message.content

# === 💬 GPT for Conversations ===
async def ask_gpt_chat(prompt, history):
    openai.api_key = OPENAI_API_KEY
    messages = [
        {"role": "system", "content": "You are a helpful and expert developer assistant. Answer clearly, concisely, and in plain English."},
        *[{"role": m["role"], "content": m["content"]} for m in history[-10:]],
        {"role": "user", "content": prompt}
    ]

    res = openai.chat.completions.create(
        model="gpt-4",
        temperature=0.7,
        messages=messages
    )
    return res.choices[0].message.content

# === GitHub Helpers ===
def get_file(owner, repo, filepath):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GITHUB_PAT}"}
    res = requests.get(url, headers=headers).json()
    return b64decode(res["content"]).decode(), res["sha"]

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

def deploy(railway_url):
    try:
        res = requests.post(f"{railway_url}/__rebuild", timeout=10)
        return res.status_code in [200, 204]
    except:
        return False

# === Dev Instruction Handler ===
async def handle_code_edit_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    target, prompt = text.split(":", 1)
    target = target.lower().strip()
    prompt = prompt.strip()
    config = repo_map.get(target)

    if not config:
        await update.message.reply_text("❌ Unknown bot target.")
        return

    await update.message.reply_text("✍️ Generating code update...")

    current_code, sha = get_file(config["repo_owner"], config["repo_name"], config["target_file"])
    new_code = await ask_gpt_code(target, current_code, prompt)

    diff = list(difflib.unified_diff(
        current_code.splitlines(), new_code.splitlines(),
        fromfile="before.py", tofile="after.py", lineterm=""
    ))
    diff_preview = "\n".join(diff[:40]) + ("\n... (truncated)" if len(diff) > 40 else "")

    pending_changes[update.effective_user.id] = {
        "code": new_code,
        "sha": sha,
        "config": config,
        "prompt": prompt,
        "bot_key": target
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

# === Button Handler ===
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

        append_memory(data["bot_key"], "user", data["prompt"])
        append_memory(data["bot_key"], "assistant", f"Code updated for: {data['prompt']}")

        status = "✅ Pushed and " + ("deployed!" if deployed else "deploy failed.")
        await query.edit_message_text(
            f"{status}\n\n📂 `{data['config']['target_file']}`\n📝 {data['prompt']}",
            parse_mode="Markdown"
        )

# === Chat Memory Mode ===
async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Not authorized.")
        return

    await update.message.reply_text("🤔 Thinking...")
    memory = load_memory()
    history = memory["devbot"]  # Use devbot memory for chat
    reply = await ask_gpt_chat(prompt, history)

    append_memory("devbot", "user", prompt)
    append_memory("devbot", "assistant", reply)
    await update.message.reply_text(reply[:4096])

# === /memory Command ===
async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory = load_memory()
    reply = ""
    for bot, messages in memory.items():
        reply += f"🧠 *{bot} memory:*\n"
        for m in messages[-3:]:
            reply += f"• {m['role']}: {m['content'][:100]}\n"
        reply += "\n"
    await update.message.reply_text(reply[:4096], parse_mode="Markdown")

# === Router ===
async def main_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Unauthorized.")
        return

    if ":" in text and text.split(":")[0].lower() in repo_map:
        await handle_code_edit_instruction(update, context, text)
    else:
        await handle_conversation(update, context, text)

# === /hello ===
async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Dev Assistant with memory is online.")

# === Start Bot ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_router))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
