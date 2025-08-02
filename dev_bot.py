import os
import json
import difflib
import requests
from base64 import b64decode, b64encode
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
import openai

# === 🔐 ENVIRONMENT VARIABLES ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GITHUB_PAT = os.getenv("GITHUB_PAT")
REPO_OWNER = os.getenv("REPO_OWNER")
REPO_NAME = os.getenv("REPO_NAME")
TARGET_FILE = os.getenv("TARGET_FILE", "now_bot.py")
BRANCH = os.getenv("BRANCH", "main")
RAILWAY_DEPLOY_URL = "https://devbotassistant.up.railway.app"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === 📁 FILE PATHS ===
MEMORY_PATH = "memory.json"
LOG_PATH = "deploy_log.json"
ERROR_LOG = "error_log.txt"
BACKUP_DIR = "backups"

# ✅ Ensure backups is a real folder
if os.path.exists(BACKUP_DIR) and not os.path.isdir(BACKUP_DIR):
    os.remove(BACKUP_DIR)  # Remove the file if it's not a directory
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

# === 🧠 MEMORY FUNCTIONS ===
def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH) as f:
            return json.load(f)
    return {}

def save_memory(mem):
    with open(MEMORY_PATH, "w") as f:
        json.dump(mem, f, indent=2)

# === 📜 DEPLOY LOGGING ===
def log_event(event, summary, file=TARGET_FILE, by="system"):
    log = {}
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH) as f:
            log = json.load(f)
    log[datetime.utcnow().isoformat()] = {
        "event": event,
        "file": file,
        "summary": summary,
        "by": by
    }
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

# === 💾 FILE SNAPSHOT ===
def snapshot(code):
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    path = f"{BACKUP_DIR}/{timestamp}_{TARGET_FILE}"
    with open(path, "w") as f:
        f.write(code)
    return path

# === 🤖 GPT EDITOR ===
async def ask_gpt(prompt):
    openai.api_key = OPENAI_API_KEY
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Return raw Python code only. No markdown."},
            {"role": "user", "content": prompt}
        ]
    )
    content = response.choices[0].message.content
    lines = content.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("import")), 0)
    return "\n".join(lines[start:])

# === 📥 GITHUB INTEGRATION ===
def get_file_contents():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_FILE}"
    headers = {"Authorization": f"Bearer {GITHUB_PAT}"}
    r = requests.get(url, headers=headers)
    return b64decode(r.json()["content"]).decode(), r.json()["sha"]

def push_to_github(new_code, sha):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_FILE}"
    headers = {"Authorization": f"Bearer {GITHUB_PAT}"}
    body = {
        "message": "Auto update via dev_bot",
        "content": b64encode(new_code.encode()).decode(),
        "sha": sha,
        "branch": BRANCH
    }
    return requests.put(url, headers=headers, json=body).status_code == 200

def trigger_deploy():
    try:
        res = requests.post(f"{RAILWAY_DEPLOY_URL}/__rebuild", timeout=10)
        return res.status_code in [200, 204]
    except:
        return False

# === 🧠 GPT INSTRUCTION HANDLER ===
pending_diffs = {}

async def handle_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Not authorized.")
    prompt = update.message.text.strip()
    old_code, sha = get_file_contents()
    snapshot(old_code)

    memory = load_memory()
    history = memory.get("nowbot", {}).get("history", [])
    full_prompt = f"{old_code}\n\nUpdate this according to:\n{prompt}\n\nHistory:\n{json.dumps(history[-5:], indent=2)}"
    new_code = await ask_gpt(full_prompt)

    diff = difflib.unified_diff(
        old_code.splitlines(), new_code.splitlines(),
        fromfile="before", tofile="after", lineterm=""
    )
    diff_text = "\n".join(list(diff)[:50])

    message = await update.message.reply_text(
        f"🧠 Diff preview:\n\n<pre>{diff_text}</pre>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Push", callback_data="confirm_push"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel_push")]
        ])
    )
    pending_diffs[str(update.effective_user.id)] = {
        "new_code": new_code,
        "sha": sha,
        "summary": prompt,
        "msg_id": message.message_id
    }

# === 🔄 CALLBACK ===
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    if uid not in pending_diffs:
        return await query.edit_message_text("⚠️ No pending diff.")
    diff = pending_diffs[uid]

    if query.data == "confirm_push":
        push_to_github(diff["new_code"], diff["sha"])
        trigger_deploy()
        log_event("push", diff["summary"], by="admin")
        await query.edit_message_text("✅ Pushed & deployed.")
    else:
        await query.edit_message_text("❌ Push cancelled.")
    del pending_diffs[uid]

# === 🛠 DEBUG FROM ERROR LOG ===
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(ERROR_LOG):
        return await update.message.reply_text("No error log found.")
    with open(ERROR_LOG) as f:
        log = f.read()
    if not log.strip():
        return await update.message.reply_text("✅ No crash logs.")
    code, sha = get_file_contents()
    prompt = f"{code}\n\nFix this error:\n{log[-1000:]}"
    new_code = await ask_gpt(prompt)
    push_to_github(new_code, sha)
    trigger_deploy()
    log_event("debug", "Crash fix via GPT", by="admin")
    await update.message.reply_text("✅ Debugged, pushed & deployed.")

# === 🧱 SNAPSHOT + ROLLBACK ===
async def rollback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.strip().split(" ")
    if len(parts) != 2:
        return await update.message.reply_text("Usage: /rollback filename")
    file = os.path.join(BACKUP_DIR, parts[1])
    if not os.path.exists(file):
        return await update.message.reply_text("❌ File not found.")
    with open(file) as f:
        rollback_code = f.read()
    _, sha = get_file_contents()
    push_to_github(rollback_code, sha)
    trigger_deploy()
    log_event("rollback", f"Rollback from {parts[1]}")
    await update.message.reply_text("✅ Rolled back and deployed.")

async def snapshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code, _ = get_file_contents()
    path = snapshot(code)
    await update.message.reply_text(f"📦 Snapshot saved to `{path}`", parse_mode="Markdown")

# === ✅ LOG + HEALTH ===
async def deploylog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(LOG_PATH):
        return await update.message.reply_text("No logs.")
    with open(LOG_PATH) as f:
        logs = json.load(f)
    lines = [f"{k} - {v['event']} by {v['by']}: {v['summary']}" for k, v in list(logs.items())[-5:]]
    await update.message.reply_text("\n".join(lines))

async def healthcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(ERROR_LOG):
        with open(ERROR_LOG) as f:
            err = f.read()
        if err.strip():
            return await update.message.reply_text(f"⚠️ Crash:\n\n{err[-1000:]}")
    await update.message.reply_text("✅ dev_bot healthy")

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Dev Assistant ready.")

# === 🏁 LAUNCH ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("rollback", rollback))
    app.add_handler(CommandHandler("snapshot", snapshot_cmd))
    app.add_handler(CommandHandler("deploylog", deploylog))
    app.add_handler(CommandHandler("healthcheck", healthcheck))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instruction))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()
