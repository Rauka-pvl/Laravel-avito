import os
import logging
from config import CACHE_DIR, LOG_DIR, LOG_FILE, COMBINED_XML
from downloader import download_all
from merger import merge_xml
from photo_updater import update_all_photos

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8"
    )
    logging.getLogger().addHandler(logging.StreamHandler())

def clear_cache():
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith(".xml"):
                os.remove(os.path.join(CACHE_DIR, f))
        logging.info("Удалены старые XML-файлы из кэша.")

def main():
    setup_logging()
    logging.info("=== Обновление началось ===")

    clear_cache()

    updated_files = download_all()
    if updated_files:
        merge_xml(updated_files, COMBINED_XML)

    update_all_photos()  # всегда вызывается

    logging.info("=== Обновление завершено ===")

if __name__ == "__main__":
    main()