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

# === 🔐 CONFIG ===
BOT_TOKEN = "8497059006:AAGwlC2Rg4XcVdakNZ15WG2abNuwsPkaZmM"
ADMIN_ID = 6967780222
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

# === MEMORY ===
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"nowbot": [], "devbot": []}
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(mem):
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=2)

def append_memory(bot_key, role, content):
    mem = load_memory()
    mem[bot_key].append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })
    mem[bot_key] = mem[bot_key][-10:]
    save_memory(mem)

# === GITHUB ===
def get_file(owner, repo, filepath):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GITHUB_PAT}"}
    res = requests.get(url, headers=headers).json()
    return b64decode(res["content"]).decode(), res["sha"]

def push_file(owner, repo, filepath, new_code, sha):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GITHUB_PAT}"}
    payload = {
        "message": "Auto update from Dev Assistant",
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

# === GPT WRAPPERS ===
async def ask_gpt_code(bot_key, current_code, prompt):
    memory = load_memory()[bot_key][-6:]
    messages = [
        {"role": "system", "content": f"You're a senior Python developer working on {bot_key}. ONLY return raw .py code. No markdown or comments."},
        *[{"role": m["role"], "content": m["content"]} for m in memory],
        {"role": "user", "content": f"This is the code:\n\n{current_code}\n\nMake this change:\n\n{prompt}"}
    ]
    res = openai.chat.completions.create(model="gpt-4", messages=messages, temperature=0.3)
    raw = res.choices[0].message.content
    lines = raw.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("import")), 0)
    cleaned = "\n".join(lines[start:])
    return cleaned

async def ask_gpt_chat(prompt, history):
    messages = [
        {"role": "system", "content": "You are a helpful dev assistant."},
        *[{"role": m["role"], "content": m["content"]} for m in history[-10:]],
        {"role": "user", "content": prompt}
    ]
    res = openai.chat.completions.create(model="gpt-4", messages=messages, temperature=0.7)
    return res.choices[0].message.content

# === DEV INSTRUCTION ===
async def handle_code_edit_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    target, prompt = text.split(":", 1)
    target, prompt = target.strip().lower(), prompt.strip()
    config = repo_map[target]
    current_code, sha = get_file(config["repo_owner"], config["repo_name"], config["target_file"])
    new_code = await ask_gpt_code(target, current_code, prompt)

    if "import" not in new_code or "def " not in new_code:
        await update.message.reply_text("🚨 GPT output doesn't look like code. Aborted.")
        return

    diff = list(difflib.unified_diff(current_code.splitlines(), new_code.splitlines(), fromfile="before.py", tofile="after.py", lineterm=""))
    preview = "\n".join(diff[:40]) + ("\n... (truncated)" if len(diff) > 40 else "")
    pending_changes[update.effective_user.id] = {
        "code": new_code, "sha": sha, "config": config,
        "prompt": prompt, "bot_key": target
    }

    await update.message.reply_text(
        f"🧠 *Diff Preview:*\n```diff\n{preview}\n```",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Push & Deploy", callback_data="push_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="push_cancel")]
        ])
    )

# === CHAT MODE ===
async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Unauthorized.")
        return
    await update.message.reply_text("🤔 Thinking...")
    mem = load_memory()
    reply = await ask_gpt_chat(prompt, mem["devbot"])
    append_memory("devbot", "user", prompt)
    append_memory("devbot", "assistant", reply)
    await update.message.reply_text(reply[:4096])

# === BUTTON CONFIRM ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = pending_changes.get(query.from_user.id)
    if not data:
        await query.edit_message_text("❌ No pending change.")
        return

    if query.data == "push_cancel":
        del pending_changes[query.from_user.id]
        await query.edit_message_text("❌ Cancelled.")
        return

    if query.data == "push_confirm":
        pushed = push_file(data["config"]["repo_owner"], data["config"]["repo_name"], data["config"]["target_file"], data["code"], data["sha"])
        deployed = deploy(data["config"]["railway_url"])
        status = "✅ Pushed and " + ("deployed!" if deployed else "failed to deploy.")
        append_memory(data["bot_key"], "user", data["prompt"])
        append_memory(data["bot_key"], "assistant", "Code updated and deployed.")
        del pending_changes[query.from_user.id]
        await query.edit_message_text(f"{status}\n📂 `{data['config']['target_file']}`\n📝 {data['prompt']}", parse_mode="Markdown")

# === DEBUG CRASHED BOT ===
async def debug_nowbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔️ Unauthorized.")

    await update.message.reply_text("🛠 Reading crash log...")
    try:
        current_code, sha = get_file("marquisem505", "scams-plus-subscription-bot", "now_bot.py")
        if not os.path.exists("error_log.txt"):
            return await update.message.reply_text("✅ No crash log found.")

        with open("error_log.txt", "r") as f:
            error_log = f.read()

        gpt = openai.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You're a Python bug fixer. Return only the corrected code starting with import. No explanation."},
                {"role": "user", "content": f"""Here is broken code:\n\n{current_code}\n\nError:\n\n{error_log}"""}
            ]
        )
        raw = gpt.choices[0].message.content
        lines = raw.splitlines()
        start = next((i for i, l in enumerate(lines) if l.strip().startswith("import")), 0)
        new_code = "\n".join(lines[start:])

        if "import" not in new_code or "def " not in new_code:
            return await update.message.reply_text("🚨 GPT output is invalid. Aborting.")

        diff = list(difflib.unified_diff(current_code.splitlines(), new_code.splitlines(), fromfile="before.py", tofile="after.py", lineterm=""))
        preview = "\n".join(diff[:40]) + ("\n... (truncated)" if len(diff) > 40 else "")

        pending_changes[update.effective_user.id] = {
            "code": new_code, "sha": sha,
            "config": repo_map["nowbot"],
            "prompt": "🔥 Auto-fix from crash log",
            "bot_key": "nowbot"
        }

        await update.message.reply_text(
            f"🚑 *Auto-Fix Suggestion:*\n```diff\n{preview}\n```",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Push Fix", callback_data="push_confirm")],
                [InlineKeyboardButton("❌ Cancel", callback_data="push_cancel")]
            ])
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Debug failed: {e}")

# === MEMORY CHECK ===
async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mem = load_memory()
    out = ""
    for bot, entries in mem.items():
        out += f"🧠 *{bot} memory:*\n"
        for m in entries[-3:]:
            out += f"• {m['role']}: {m['content'][:100]}\n"
        out += "\n"
    await update.message.reply_text(out[:4096], parse_mode="Markdown")

# === MAIN ROUTER ===
async def main_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔️ Unauthorized.")

    if ":" in text and text.split(":")[0].lower() in repo_map:
        await handle_code_edit_instruction(update, context, text)
    else:
        await handle_conversation(update, context, text)

# === /hello ===
async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Dev Assistant is online and ready.")

# === INIT ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(CommandHandler("debug", debug_nowbot))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_router))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
