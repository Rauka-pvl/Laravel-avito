import asyncio
import sqlite3
import subprocess
import os
import time
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
import psutil
from log_manager import get_latest_log_tail, cleanup_old_logs
import html

# === Настройки ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = os.getenv("TELEGRAM_USER_IDS", "").split(",")
DB_PATH = os.path.join(BASE_DIR, "scripts_status.db")

# === Сканирование скриптов ===
SCRIPTS = {}
for item in os.listdir(BASE_DIR):
    if item in ["notification", "price_photo_update", "telebot"]:
        continue
    full_path = os.path.join(BASE_DIR, item, "main.py")
    if os.path.isfile(full_path):
        SCRIPTS[item] = full_path

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


def is_script_running_and_duration(name: str):
    script_path = SCRIPTS.get(name)
    running = False
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = " ".join(proc.info['cmdline'])
            if script_path and script_path in cmdline:
                running = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
            continue

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT last_run, duration FROM script_status WHERE name = ?", (name,))
        row = c.fetchone()

    if row:
        last_run_str, last_duration = row
        if running:
            try:
                last_run_dt = datetime.fromisoformat(last_run_str)
                duration = (datetime.now() - last_run_dt).total_seconds()
                return True, duration, last_run_str
            except Exception:
                return True, 0.0, last_run_str
        else:
            return False, last_duration, last_run_str
    return False, 0.0, None


def get_status():
    enriched = []
    for name in SCRIPTS:
        try:
            script_path = SCRIPTS.get(name)
            running = False
            for proc in psutil.process_iter(['cmdline']):
                cmdline = proc.info.get('cmdline') or []
                full_cmd = " ".join(cmdline)
                if full_cmd.endswith(script_path):
                    running = True
                    break

            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT last_run, duration FROM script_status WHERE name = ?", (name,))
                row = c.fetchone()

            if row:
                last_run_str, last_duration = row
                if running:
                    try:
                        last_run_dt = datetime.fromisoformat(last_run_str)
                        duration = (datetime.now() - last_run_dt).total_seconds()
                    except Exception:
                        duration = 0.0
                    success = False
                else:
                    try:
                        last_run_dt = datetime.fromisoformat(last_run_str)
                        now = datetime.now()
                        approx_duration = (now - last_run_dt).total_seconds()
                        if approx_duration > last_duration and approx_duration < 86400:
                            last_duration = approx_duration
                            update_status(name, True, last_duration)
                    except Exception:
                        pass
                    duration = last_duration
                    success = True
            else:
                last_run_str = None
                duration = 0.0
                success = not running

            enriched.append((name, last_run_str, success, duration, running))
        except Exception:
            enriched.append((name, None, False, 0.0, False))
    return enriched


@router.message(F.text == "📊 Статус")
async def show_status(message: types.Message):
    rows = get_status()
    if not rows:
        return await message.reply("Нет данных о статусах скриптов", reply_markup=get_main_keyboard())

    lines = []
    for name, last_run, success, duration, running in rows:
        status = "🟢 Работает" if running else ("✅ Завершён" if success else "❌ Ошибка")
        duration_text = f"{duration:.2f} сек." if duration else "–"
        last_run_fmt = datetime.fromisoformat(last_run).strftime("%Y-%m-%d %H:%M:%S") if last_run else "–"
        tail = get_latest_log_tail(name) if not success else ""
        if tail:
            tail = html.escape(tail)
        block = f"{name}\nПоследний запуск: {last_run_fmt}\nСтатус: {status}\nВремя выполнения: {duration_text}"
        if tail:
            block += f"\n\n📄 Последние строки лога:\n{tail}"
        lines.append(block)

    await message.reply("\n\n".join(lines), reply_markup=get_main_keyboard(), parse_mode=None)

# === Клавиатура ===
def get_main_keyboard():
    keyboard = [
        [KeyboardButton(text="📂 Службы"), KeyboardButton(text="📊 Статус")],
        [KeyboardButton(text="⏰ Расписание")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_script_keyboard(script_name):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"🚀 Запустить: {script_name}"), KeyboardButton(text=f"📄 Лог: {script_name}")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

# === Хендлеры ===
@router.message(F.text == "/start")
async def show_menu(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return await message.reply("⛔️ Доступ запрещен")
    await message.reply("Главное меню:", reply_markup=get_main_keyboard())


@router.message(F.text == "📂 Службы")
async def show_scripts(message: types.Message):
    keyboard = [
        [KeyboardButton(text=name)] for name in sorted(SCRIPTS.keys())
    ]
    keyboard.append([KeyboardButton(text="🔙 Назад")])
    await message.reply("Выберите скрипт:", reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True))



@router.message(F.text == "⏰ Расписание")
async def show_schedule_placeholder(message: types.Message):
    await message.reply("⏳ Настройка расписания будет доступна позже", reply_markup=get_main_keyboard())


@router.message(F.text == "🔙 Назад")
async def go_back(message: types.Message):
    await message.reply("Главное меню:", reply_markup=get_main_keyboard())


@router.message(F.text.in_(SCRIPTS.keys()))
async def show_script_controls(message: types.Message):
    await message.reply(f"Действия для {message.text}:", reply_markup=get_script_keyboard(message.text))


@router.message(F.text.startswith("🚀 Запустить: "))
async def run_script(message: types.Message):
    script_name = message.text.replace("🚀 Запустить: ", "")
    script_path = SCRIPTS.get(script_name)

    if not script_path or not os.path.isfile(script_path):
        await message.reply(f"❌ Скрипт {script_name} не найден по пути: {script_path}")
        return

    await message.reply(f"⏳ Запуск скрипта: {script_name}\n🧩 Путь: {script_path}")
    logging.info(f"Запуск скрипта '{script_name}' по пути: {script_path}")
    start_time = time.time()
    try:
        subprocess.Popen(
            ["nohup", "python3", script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp
        )
        duration = time.time() - start_time
        update_status(script_name, True, duration)
        await message.reply(f"✅ Скрипт {script_name} запущен", reply_markup=get_script_keyboard(script_name))
    except Exception as e:
        logging.exception(f"Ошибка запуска скрипта {script_name}")
        update_status(script_name, False, 0)
        await message.reply(f"❌ Ошибка запуска {script_name}: {str(e)}", reply_markup=get_script_keyboard(script_name))


@router.message(F.text.startswith("📄 Лог: "))
async def show_log_tail(message: types.Message):
    script_name = message.text.replace("📄 Лог: ", "")
    tail = get_latest_log_tail(script_name)
    reply = f"""📄 Последние строки лога {script_name}:
{tail}""" if tail else "Лог отсутствует."
    await message.reply(reply, reply_markup=get_script_keyboard(script_name))


# === Фоновая очистка логов ===
def periodic_log_cleanup(interval_seconds=1800):
    async def _loop():
        while True:
            cleanup_old_logs()
            await asyncio.sleep(interval_seconds)
    return _loop()


# === Запуск ===
async def main():
    init_db()
    for uid in ADMIN_IDS:
        try:
            await bot.send_message(uid.strip(), "🤖 Бот запущен", reply_markup=get_main_keyboard())
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение {uid}: {e}")
    asyncio.create_task(periodic_log_cleanup())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
