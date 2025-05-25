import os
import glob
import logging
from datetime import datetime


LOGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "app", "public", "output"))
MAX_LOG_FILES = 30
BOT_LOG_DIR = os.path.join(LOGS_DIR, "logs-telebot")

# Настройка логирования
os.makedirs(BOT_LOG_DIR, exist_ok=True)
log_filename = os.path.join(BOT_LOG_DIR, datetime.now().strftime("%Y-%m-%d_%H-%M-%S.log"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename, encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def get_latest_log_tail(script_key: str, lines: int = 10) -> str:
    log_folder = os.path.join(LOGS_DIR, f"logs-{script_key}")
    if not os.path.isdir(log_folder):
        return "Логов не найдено."

    log_files = sorted(glob.glob(os.path.join(log_folder, "*")), key=os.path.getmtime, reverse=True)
    if not log_files:
        return "Лог-файлы отсутствуют."

    latest_file = log_files[0]
    try:
        with open(latest_file, 'r', encoding='utf-8', errors='ignore') as f:
            return "\n".join(f.readlines()[-lines:])
    except Exception as e:
        return f"Ошибка чтения лога: {str(e)}"


def cleanup_old_logs():
    for entry in os.listdir(LOGS_DIR):
        folder_path = os.path.join(LOGS_DIR, entry)
        if not os.path.isdir(folder_path):
            continue
        if not entry.startswith("logs-"):
            continue

        log_files = sorted(glob.glob(os.path.join(folder_path, "*")), key=os.path.getmtime)
        if len(log_files) > MAX_LOG_FILES:
            to_delete = log_files[:len(log_files) - MAX_LOG_FILES]
            for f in to_delete:
                try:
                    os.remove(f)
                    logger.info(f"Удалён старый лог: {f}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить {f}: {e}")


if __name__ == "__main__":
    print("📁 Статус логов:")
    for entry in sorted(os.listdir(LOGS_DIR)):
        folder_path = os.path.join(LOGS_DIR, entry)
        if os.path.isdir(folder_path) and entry.startswith("logs-"):
            count = len(glob.glob(os.path.join(folder_path, "*")))
            print(f"{entry}: {count} файлов")