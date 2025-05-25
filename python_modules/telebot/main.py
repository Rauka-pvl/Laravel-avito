import asyncio
import sqlite3
import subprocess
import os
import time
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
import psutil

# === Настройки ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = os.getenv("TELEGRAM_USER_IDS", "").split(",")
DB_PATH = os.path.join(BASE_DIR, "scripts_status.db")

# === Сканирование скриптов ===
SCRIPTS = {}
for item in os.listdir(BASE_DIR):
    full_path = os.path.join(BASE_DIR, item, "main.py")
    if os.path.isfile(full_path):
        emoji = "✅"
        display_name = f"{emoji} {item}"
        SCRIPTS[display_name] = full_path

# === Telegram setup ===
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# === База данных и статус ===
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS script_status (
                name TEXT PRIMARY KEY,
                last_run TEXT,
                success INTEGER,
                duration REAL
            )
        """)
        conn.commit()


def is_script_running(script_path: str) -> bool:
    for proc in psutil.process_iter(['cmdline']):
        try:
            if proc.info['cmdline'] and script_path in " ".join(proc.info['cmdline']):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def get_script_runtime(script_path: str) -> float:
    for proc in psutil.process_iter(['create_time', 'cmdline']):
        try:
            if proc.info['cmdline'] and script_path in " ".join(proc.info['cmdline']):
                start_time = datetime.fromtimestamp(proc.info['create_time'])
                return (datetime.now() - start_time).total_seconds()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return 0.0


def update_status(name, success, duration):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO script_status (name, last_run, success, duration)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                last_run=excluded.last_run,
                success=excluded.success,
                duration=excluded.duration
        """, (name, datetime.now().isoformat(), int(success), duration))
        conn.commit()


def get_status():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM script_status")
        rows = c.fetchall()

    enriched = []
    for name, last_run, success, duration in rows:
        script_path = SCRIPTS.get(name)
        running = is_script_running(script_path) if script_path else False
        live_duration = get_script_runtime(script_path) if running else duration
        enriched.append((name, last_run, success, live_duration, running))
    return enriched

# === Клавиатуры ===
def get_inline_keyboard():
    builder = InlineKeyboardBuilder()
    for name in SCRIPTS:
        builder.button(text=name, callback_data=name)
    builder.adjust(1)
    return builder.as_markup()


def get_reply_keyboard():
    keyboard = [[
        KeyboardButton(text="📋 Меню"),
        KeyboardButton(text="📊 Статус")
    ]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# === Хендлеры ===
@router.message(F.text.in_(["/start", "📋 Меню"]))
async def show_menu(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return await message.reply("⛔️ Доступ запрещен", reply_markup=get_reply_keyboard())
    await message.reply("Выберите действие:", reply_markup=get_inline_keyboard())


@router.message(F.text.in_(["/status", "📊 Статус"]))
async def show_status(message: types.Message):
    rows = get_status()
    if not rows:
        return await message.reply("Нет данных о статусах скриптов", reply_markup=get_reply_keyboard())

    lines = []
    for name, last_run, success, duration, running in rows:
        status = "🟢 Работает" if running else ("✅ Завершён" if success else "❌ Ошибка")
        duration_text = f"{duration:.2f} сек." if duration else "–"
        last_run_fmt = datetime.fromisoformat(last_run).strftime("%Y-%m-%d %H:%M:%S") if last_run else "–"
        lines.append(f"{name}\nПоследний запуск: {last_run_fmt}\nСтатус: {status}\nВремя выполнения: {duration_text}\n")

    await message.reply("\n\n".join(lines), reply_markup=get_reply_keyboard())


@router.callback_query(lambda c: c.data in SCRIPTS)
async def run_script(callback: types.CallbackQuery):
    script_name = callback.data
    script_path = SCRIPTS[script_name]

    await callback.message.edit_text(f"⏳ Запуск скрипта: {script_name}")
    start_time = time.time()
    try:
        subprocess.Popen(["nohup", "python3", script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        duration = time.time() - start_time
        update_status(script_name, True, duration)
        await callback.message.edit_text(f"✅ Скрипт {script_name} запущен", reply_markup=get_inline_keyboard())
    except Exception as e:
        update_status(script_name, False, 0)
        await callback.message.edit_text(f"❌ Ошибка запуска {script_name}: {str(e)}", reply_markup=get_inline_keyboard())


# === Запуск ===
async def main():
    init_db()
    for uid in ADMIN_IDS:
        try:
            await bot.send_message(uid.strip(), "🤖 Бот запущен", reply_markup=get_reply_keyboard())
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение {uid}: {e}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
