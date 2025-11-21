import asyncio
import subprocess
import os
import time
import logging
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
import psutil
from log_manager import get_latest_log_tail, cleanup_old_logs
import html
from database_manager import *
from user_state import set_user_state, get_user_state, clear_user_state
from scheduler import router as schedule_router, handle_schedule_time_input

# === Настройки ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = os.getenv("TELEGRAM_USER_IDS", "").split(",")

# === Сканирование скриптов ===
SCRIPTS = {}
for item in os.listdir(BASE_DIR):
    if item in ["notification", "price_photo_update", "bz_telebot"]:
        continue
    full_path = os.path.join(BASE_DIR, item, "main.py")
    if os.path.isfile(full_path):
        SCRIPTS[item] = full_path

AUTOSTART_CONFIG_KEY = "bz_telebot.autostart_scripts"


def collect_running_script_processes():
    running = {}
    script_items = list(SCRIPTS.items())
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if not cmdline:
                continue
            joined = " ".join(cmdline)
            for name, path in script_items:
                if path in joined:
                    running.setdefault(name, []).append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return running


def stop_running_scripts(process_map: dict):
    stopped = []
    errors = []
    for name, processes in process_map.items():
        alive = []
        for proc in processes:
            try:
                proc.terminate()
                alive.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                errors.append(f"{name} (PID {proc.pid}): {exc}")
        if not alive:
            continue
        gone, still_alive = psutil.wait_procs(alive, timeout=5)
        for proc in still_alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                errors.append(f"{name} (PID {proc.pid}) force kill: {exc}")
        set_script_end(name, status="stopped")
        stopped.append(name)
    return stopped, errors


def remember_autostart_scripts(script_names):
    if script_names:
        try:
            set_config(AUTOSTART_CONFIG_KEY, json.dumps(script_names))
        except Exception as exc:
            logging.error(f"Не удалось сохранить список автозапускаемых скриптов: {exc}")
    else:
        delete_config_key(AUTOSTART_CONFIG_KEY)


async def restore_autostart_scripts():
    raw = get_config(AUTOSTART_CONFIG_KEY)
    if not raw:
        return
    delete_config_key(AUTOSTART_CONFIG_KEY)
    try:
        scripts_to_start = json.loads(raw)
        if not isinstance(scripts_to_start, list):
            scripts_to_start = []
    except json.JSONDecodeError:
        scripts_to_start = [item.strip() for item in raw.split(",") if item.strip()]

    if not scripts_to_start:
        return

    started = []
    failed = []
    for name in scripts_to_start:
        script_path = SCRIPTS.get(name)
        if not script_path or not os.path.exists(script_path):
            failed.append(f"{name} (нет файла)")
            continue
        try:
            set_script_start(name)
            subprocess.Popen(
                ["nohup", "python3", script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp
            )
            started.append(name)
        except Exception as exc:
            failed.append(f"{name}: {exc}")

    if not started and not failed:
        return

    summary_lines = []
    if started:
        summary_lines.append(f"♻️ Автозапущены скрипты: {', '.join(started)}")
    if failed:
        summary_lines.append("⚠️ Не удалось запустить: " + ", ".join(failed))

    for uid in ADMIN_IDS:
        uid = uid.strip()
        if not uid:
            continue
        try:
            await bot.send_message(uid, "\n".join(summary_lines))
        except Exception as exc:
            logging.warning(f"Не удалось отправить уведомление {uid}: {exc}")

# === Telegram setup ===
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)
dp.include_router(schedule_router)

# === Клавиатура ===
def get_main_keyboard():
    keyboard = [
        [KeyboardButton(text="📂 Службы"), KeyboardButton(text="📊 Статус")],
        [KeyboardButton(text="⏰ Расписание"), KeyboardButton(text="🔄 Обновить/перезапустить бота")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@router.message(F.text == "🔄 Обновить/перезапустить бота")
async def handle_git_pull(message: types.Message):
    repo_dir = BASE_DIR
    restart_script = os.path.join(repo_dir, "bot_start.sh")

    try:
        running_processes = collect_running_script_processes()
        if running_processes:
            stopped_scripts, stop_errors = stop_running_scripts(running_processes)
            remember_autostart_scripts(stopped_scripts)
            if stopped_scripts:
                await message.reply(
                    "⏹ Остановлены скрипты: " + ", ".join(stopped_scripts),
                    parse_mode="HTML"
                )
            if stop_errors:
                await message.reply(
                    "⚠️ Ошибки при остановке:\n" + "\n".join(stop_errors[:10]),
                    parse_mode="HTML"
                )
        else:
            remember_autostart_scripts([])
            await message.reply("ℹ️ Активных скриптов не найдено.", parse_mode="HTML")

        # Выполняем git pull и ждём завершения
        result = subprocess.run(
            ["git", "-C", repo_dir, "pull"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20
        )
        output = result.stdout + result.stderr
        if not output.strip():
            output = "✅ Update выполнен, но нет вывода."

        # Отправляем результат pull пользователю
        await message.reply(
            f"<b>Результат:</b>\n<pre>{html.escape(output.strip())}</pre>",
            parse_mode="HTML"
        )

        # После отправки — перезапуск
        if os.path.exists(restart_script):
            subprocess.Popen(
                ["bash", restart_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp
            )
        else:
            await message.reply("⚠️ <code>bot_start.sh</code> не найден", parse_mode="HTML")

    except Exception as e:
        await message.reply(
            f"❌ Ошибка при git pull:\n<code>{html.escape(str(e))}</code>",
            parse_mode="HTML"
        )


def get_script_keyboard(script_name):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"🚀 Запустить: {script_name}"), KeyboardButton(text=f"📄 Лог: {script_name}")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

# === Утилиты ===
def format_script_info(name):
    info = get_script_info(name)
    status = info['status'] or "unknown"
    start = info['start_time']
    end = info['end_time']
    duration = info['duration']

    status_emoji = {
        "running": "🟢 Работает",
        "done": "✅ Завершён",
        "failed": "❌ Ошибка",
        "stopped": "🟡 Остановлен",
        "unknown": "⚪ Неизвестно"
    }.get(status, status)

    duration_text = "–"
    if duration:
        minutes = int(duration) // 60
        seconds = int(duration) % 60
        duration_text = f"{minutes} мин {seconds} сек" if minutes > 0 else f"{seconds} сек"

    last_run_fmt = "–"
    if start:
        try:
            last_run_fmt = datetime.fromisoformat(start).strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass

    tail = get_latest_log_tail(name)
    return {
        "text": f"{name}\nПоследний запуск: {last_run_fmt}\nСтатус: {status_emoji}\nВремя выполнения: {duration_text}",
        "tail": html.escape(tail) if tail else None
    }

# === Хендлеры ===
@router.message(F.text == "/start")
async def show_menu(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return await message.reply("⛔️ Доступ запрещен")
    await message.reply("Главное меню:", reply_markup=get_main_keyboard())

@router.message(F.text == "📂 Службы")
async def show_scripts(message: types.Message):
    script_names = sorted(SCRIPTS.keys())
    keyboard = []
    for i in range(0, len(script_names), 2):
        row = [KeyboardButton(text=script_names[i])]
        if i + 1 < len(script_names):
            row.append(KeyboardButton(text=script_names[i + 1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="🔙 Назад")])
    await message.reply("Выберите скрипт:", reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True))

@router.message(F.text == "🔙 Назад")
async def go_back(message: types.Message):
    await message.reply("Главное меню:", reply_markup=get_main_keyboard())

@router.message(F.text == "📊 Статус")
async def show_status(message: types.Message):
    lines = []
    for name in SCRIPTS:
        info = format_script_info(name)
        text = info["text"]
        tail = info["tail"]
        if tail:
            text += f"\n\n📄 Последние строки лога:\n{tail}"
        lines.append(text)
    if not lines:
        await message.reply("Нет данных о статусах скриптов", reply_markup=get_main_keyboard())
    else:
        await message.reply("\n\n".join(lines), reply_markup=get_main_keyboard(), parse_mode=None)

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
    try:
        set_script_start(script_name)
        subprocess.Popen(
            ["nohup", "python3", script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp
        )
        await message.reply(f"✅ Скрипт {script_name} запущен", reply_markup=get_script_keyboard(script_name))
    except Exception as e:
        logging.exception(f"Ошибка запуска скрипта {script_name}")
        set_script_end(script_name, status="failed")
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

# === Фоновый запуск по расписанию (из config с cron) ===
from croniter import croniter

def get_due_schedules(now: datetime) -> list:
    result = []
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        query = "SELECT name, value FROM config WHERE name LIKE %s" if DB_TYPE == "mysql" else "SELECT name, value FROM config WHERE name LIKE ?"
        like_pattern = "%.schedule.%" if DB_TYPE == "mysql" else "%.schedule.%"
        cursor.execute(query, (like_pattern,))
        for name, cron_expr in cursor.fetchall():
            try:
                script_name = name.split(".")[0]
                base_time = now.replace(second=0, microsecond=0)
                itr = croniter(cron_expr, base_time - timedelta(minutes=1))
                next_time = itr.get_next(datetime)
                if next_time == base_time:
                    result.append({"script_name": script_name, "cron_expr": cron_expr})
            except Exception as e:
                logging.warning(f"Некорректный cron-выражение '{cron_expr}' для '{name}': {e}")
    finally:
        cursor.close()
        conn.close()
    return result

def periodic_schedule_runner(interval_seconds=60):
    async def _loop():
        await asyncio.sleep(5)
        while True:
            now = datetime.now()
            due = get_due_schedules(now)
            for task in due:
                script_name = task["script_name"]
                script_path = SCRIPTS.get(script_name)
                if script_path and os.path.exists(script_path):
                    # Проверяем, запущен ли уже экземпляр скрипта через проверку реальных процессов
                    running_processes = collect_running_script_processes()
                    is_running = script_name in running_processes and len(running_processes[script_name]) > 0
                    
                    if is_running:
                        # Скрипт уже работает, пропускаем плановый запуск
                        logging.info(f"[SCHEDULE] Пропущен плановый запуск {script_name} - скрипт уже работает")
                        notification_text = f"⏭️ Плановый запуск скрипта <b>{script_name}</b> пропущен\n" \
                                          f"Причина: скрипт уже работает (статус: Работает)"
                        
                        # Отправляем уведомление всем администраторам
                        for uid in ADMIN_IDS:
                            uid = uid.strip()
                            if not uid:
                                continue
                            try:
                                await bot.send_message(uid, notification_text, parse_mode="HTML")
                            except Exception as exc:
                                logging.warning(f"Не удалось отправить уведомление {uid}: {exc}")
                    else:
                        # Скрипт не работает, запускаем по расписанию
                        logging.info(f"[SCHEDULE] Запуск по cron: {script_name} ({task['cron_expr']})")
                        set_script_start(script_name)
                        subprocess.Popen(
                            ["nohup", "python3", script_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            preexec_fn=os.setpgrp
                        )
            await asyncio.sleep(interval_seconds)
    return _loop()

# === Запуск ===
async def main():
    init_db()
    await restore_autostart_scripts()
    for uid in ADMIN_IDS:
        try:
            await bot.send_message(uid.strip(), "🤖 Бот запущен", reply_markup=get_main_keyboard())
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение {uid}: {e}")
    asyncio.create_task(periodic_log_cleanup())
    asyncio.create_task(periodic_schedule_runner())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
