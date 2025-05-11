# zzap/main.py
import logging
from zzap_downloader import download_all
from zzap_merger import merge_yml_files, save_merged_xml
from zzap_processor import process_combined_yml

from datetime import datetime
import sys
import os

# Подключение конфигурации
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import LOG_DIR, BASE_DIR

# Настройка логов
LOG_DIR = os.path.join(BASE_DIR, "..", "..", "storage", "app", "public", "output", "logs-zzap")
os.makedirs(LOG_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = os.path.join(LOG_DIR, f"zzap_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
with open(log_path, "w", encoding="utf-8-sig") as f:
    f.write("")
logger = logging.getLogger("zzap")

def main():
    logger.info("=== Старт обновления zzap ===")

    updated_files = download_all()
    if not updated_files:
        logger.info("Нет обновлённых YML-файлов. Выход.")
        return

    tree = merge_yml_files(updated_files)
    save_merged_xml(tree)
    process_combined_yml()

    logger.info("=== Обновление zzap завершено ===")

if __name__ == "__main__":
    main()
