# zzap/main.py
import logging
import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))

from zzap_downloader import download_all
from zzap_merger import merge_yml_files, save_merged_xml
from zzap_processor import process_combined_yml
from zzap_storage import backup_combined_yml, COMBINED_ZZAP

from notification.main import TelegramNotifier
from config import LOG_DIR, BASE_DIR
from bz_telebot.database_manager import set_script_start, set_script_end

# Logging setup
LOG_DIR = os.path.join(BASE_DIR, "..", "..", "storage", "app", "public", "output", "logs-zzap")
os.makedirs(LOG_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = os.path.join(LOG_DIR, f"zzap_{timestamp}.log")

with open(log_path, "w", encoding="utf-8-sig") as f:
    f.write("")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("zzap")

def main():
    script_name = "zzap"
    start_time = datetime.now()
    set_script_start(script_name)
    logger.info("Starting zzap update...")
    TelegramNotifier.notify("[ZZAP] Update started")

    try:
        if backup_combined_yml():
            logger.info(f"Backup created: {COMBINED_ZZAP}")
        else:
            if not os.path.exists(COMBINED_ZZAP):
                logger.info("Combined YML not found. Creating an empty file.")
                with open(COMBINED_ZZAP, "w", encoding="utf-8") as f:
                    f.write('<?xml version="1.0" encoding="utf-8"?><yml_catalog date="{}"><shop><offers></offers></shop></yml_catalog>'.format(datetime.now().isoformat()))

        updated_files = download_all()
        if not updated_files:
            logger.info("No updated YML files found. Exiting.")
            set_script_end(script_name, status="done")
            return

        tree = merge_yml_files(updated_files)
        save_merged_xml(tree)
        process_combined_yml()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        set_script_end(script_name, status="done")
        logger.info("ZZAP update completed.")
        TelegramNotifier.notify(f"[ZZAP] Update completed successfully — Duration: {duration:.2f}s")

    except Exception as e:
        logger.exception("Error during ZZAP update:")
        set_script_end(script_name, status="failed")
        TelegramNotifier.notify(f"[ZZAP] Update failed — <code>{str(e)}</code>")

if __name__ == "__main__":
    main()