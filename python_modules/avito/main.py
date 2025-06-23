import os
import logging
import sys
import shutil
from datetime import datetime

from config import CACHE_DIR, LOG_DIR, LOG_FILE, COMBINED_XML
from downloader import download_all
from merger import merge_xml
from photo_updater import update_all_photos
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bz_telebot.database_manager import set_script_start, set_script_end
from notification.main import TelegramNotifier

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    logging.getLogger().addHandler(console_handler)

    with open(LOG_FILE, "w", encoding="utf-8-sig") as f:
        f.write("")

def clear_cache():
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith(".xml"):
                os.remove(os.path.join(CACHE_DIR, f))
        logging.info("Old XML files have been removed from cache.")

OUTPUT_FILE = os.path.join(LOG_DIR, "..", "avito.xml")
BACKUP_FILE = os.path.join(LOG_DIR, "..", "avito_backup.xml")

def create_backup():
    if os.path.exists(OUTPUT_FILE):
        shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
        logging.info(f"Backup created: {BACKUP_FILE}")

def main():
    script_name = "avito"
    setup_logging()
    logging.info("=== Update started ===")
    TelegramNotifier.notify("Avito update started")

    start_time = datetime.now()
    set_script_start(script_name)

    try:
        create_backup()         # Только копирование
        clear_cache()

        updated_files = download_all()
        if updated_files:
            merge_xml(updated_files, COMBINED_XML)

            # Удаляем старый файл только если новый успешно создан
            if os.path.exists(OUTPUT_FILE):
                os.remove(OUTPUT_FILE)
                logging.info(f"Deleted original output file: {OUTPUT_FILE}")

        update_all_photos()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        set_script_end(script_name, status="done")

        logging.info("=== Update finished successfully ===")
        TelegramNotifier.notify(f"Avito update completed. Duration: {duration:.2f} seconds")

    except Exception as e:
        logging.exception("Error occurred during update:")
        set_script_end(script_name, status="failed")
        TelegramNotifier.notify(f"Avito update failed: {str(e)}")
