import os
import json
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from keep_alive import keep_alive
from dotenv import load_dotenv

# ==================== Загрузка токена ====================
load_dotenv()
TOKEN = os.getenv("TOKEN")   # токен теперь берём из Secrets
if not TOKEN:
    raise ValueError("❌ Токен не найден! Добавь его в Secrets Replit с ключом TOKEN")

OWNER_ID = 7322925570
ADMINS = set([7322925570])
BROADCAST_FILE = "broadcasts.json"

broadcast_tasks = {}
broadcast_enabled = True

# ==================== Логирование ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ==================== Утилиты ====================
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def save_broadcasts():
    data = {}
    for (chat_id, thread_id), info in broadcast_tasks.items():
        data[f"{chat_id}_{thread_id}"] = {
            "text": info["text"],
            "interval": info["interval"],
            "enabled": info["enabled"]
        }
    with open(BROADCAST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_broadcasts():
    if not os.path.exists(BROADCAST_FILE):
        return {}
    with open(BROADCAST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    for key, info in data.items():
        chat_id, thread_id = map(int, key.split("_"))
        result[(chat_id, thread_id)] = info
    return result

# ==================== Команды ====================
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Нет прав.")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /add_admin <user_id>")
        return
    new_admin = int(context.args[0])
    ADMINS.add(new_admin)
    await update.message.reply_text(f"✅ Пользователь {new_admin} добавлен как админ.")

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None, thread_id=None, interval=None, text=None):
    global broadcast_tasks

    if chat_id is None:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("Нет прав.")
            return
        if len(context.args) < 2:
            await update.message.reply_text("Использование: /start_broadcast <chat_id> [thread_id] <минуты> <текст>")
            return

        chat_id = int(context.args[0])
        if len(context.args) > 2 and context.args[1].isdigit():
            thread_id = int(context.args[1])
            interval = int(context.args[2])
            text = " ".join(context.args[3:])
        else:
            thread_id = 0
            interval = int(context.args[1])
            text = " ".join(context.args[2:])

    key = (chat_id, thread_id)
    if key in broadcast_tasks and broadcast_tasks[key]["task"]:
        broadcast_tasks[key]["task"].cancel()

    async def broadcast_loop(bot):
        try:
            while True:
                if broadcast_enabled:
                    if thread_id > 0:
                        await bot.send_message(chat_id=chat_id, text=text, message_thread_id=thread_id)
                    else:
                        await bot.send_message(chat_id=chat_id, text=text)
                await asyncio.sleep(interval * 60)
        except asyncio.CancelledError:
            logging.info(f"Рассылка для чата {chat_id}, темы {thread_id} остановлена.")

    task = asyncio.create_task(broadcast_loop(context.bot))
    broadcast_tasks[key] = {"text": text, "interval": interval, "task": task, "enabled": True}
    save_broadcasts()
    if update:
        target = f"чата {chat_id}" if thread_id == 0 else f"чата {chat_id}, темы {thread_id}"
        await update.message.reply_text(f"✅ Рассылка запущена для {target} с интервалом {interval} минут.")

async def stop_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Нет прав.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /stop_broadcast <chat_id> [thread_id]")
        return

    chat_id = int(context.args[0])
    thread_id = int(context.args[1]) if len(context.args) > 1 else 0

    key = (chat_id, thread_id)
    if key in broadcast_tasks:
        broadcast_tasks[key]["task"].cancel()
        del broadcast_tasks[key]
        save_broadcasts()
        target = f"чата {chat_id}" if thread_id == 0 else f"чата {chat_id}, темы {thread_id}"
        await update.message.reply_text(f"🛑 Рассылка для {target} остановлена.")
    else:
        await update.message.reply_text("Рассылка не найдена.")

async def toggle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global broadcast_enabled
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Нет прав.")
        return
    broadcast_enabled = not broadcast_enabled
    status = "включены ✅" if broadcast_enabled else "выключены ❌"
    await update.message.reply_text(f"Все рассылки {status}.")

async def send_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Нет прав.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /send_now <chat_id> [thread_id] <текст>")
        return

    chat_id = int(context.args[0])
    if len(context.args) > 1 and context.args[1].isdigit():
        thread_id = int(context.args[1])
        text = " ".join(context.args[2:])
    else:
        thread_id = 0
        text = " ".join(context.args[1:])

    if thread_id > 0:
        await context.bot.send_message(chat_id=chat_id, text=text, message_thread_id=thread_id)
    else:
        await context.bot.send_message(chat_id=chat_id, text=text)

    target = f"чата {chat_id}" if thread_id == 0 else f"чата {chat_id}, темы {thread_id}"
    await update.message.reply_text(f"📨 Сообщение отправлено в {target}.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await update.message.reply_text("✅ Бот работает!")

async def dante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Нет прав.")
        return

    help_text = (
        "📌 Команды:\n\n"
        "/add_admin <user_id>\n"
        "/start_broadcast <chat_id> [thread_id] <минуты> <текст>\n"
        "/stop_broadcast <chat_id> [thread_id]\n"
        "/toggle_broadcast\n"
        "/send_now <chat_id> [thread_id] <текст>\n"
        "/ping\n"
        "/threadid\n"
        "/dante\n\n"
        "Активные рассылки:\n"
    )

    if broadcast_tasks:
        for (chat_id, thread_id), data in broadcast_tasks.items():
            status = "Вкл ✅" if data["enabled"] else "Выкл ❌"
            target = f"Чат {chat_id}" if thread_id == 0 else f"Чат {chat_id}, Тема {thread_id}"
            help_text += f"{target}, Интервал {data['interval']} мин, Статус: {status}\n"
    else:
        help_text += "Нет активных рассылок."

    await update.message.reply_text(help_text)

async def threadid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Нет прав.")
        return
    thread = getattr(update.message, "message_thread_id", None)
    if thread:
        await update.message.reply_text(f"Thread ID: {thread}")
    else:
        await update.message.reply_text("Это обычный чат (thread_id отсутствует).")

# ==================== Запуск бота ====================
def run_bot():
    keep_alive()

    app = ApplicationBuilder().token(TOKEN).build()

    loaded_tasks = load_broadcasts()
    for (chat_id, thread_id), info in loaded_tasks.items():
        asyncio.create_task(start_broadcast(None, type("obj", (), {"bot": app.bot}), chat_id, thread_id, info["interval"], info["text"]))

    app.add_handler(CommandHandler("add_admin", add_admin))
    app.add_handler(CommandHandler("start_broadcast", start_broadcast))
    app.add_handler(CommandHandler("stop_broadcast", stop_broadcast))
    app.add_handler(CommandHandler("toggle_broadcast", toggle_broadcast))
    app.add_handler(CommandHandler("send_now", send_now))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("dante", dante))
    app.add_handler(CommandHandler("threadid", threadid))

    print("🚀 Бот запущен. Работает 24/7 через UptimeRobot")
    app.run_polling()

if __name__ == "__main__":
    run_bot()
