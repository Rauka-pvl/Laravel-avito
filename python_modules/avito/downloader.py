import os
import hashlib
import logging
import os
import hashlib
import requests
from config import CACHE_DIR, url_to_filename
from storage import get_file_hash, save_file_hash
import requests
from config import XML_URLS, CACHE_DIR, url_to_filename
from storage import get_file_hash, save_file_hash

def download_if_changed(url):
    os.makedirs(CACHE_DIR, exist_ok=True)
    filename = os.path.join(CACHE_DIR, url_to_filename(url))

    try:
        logging.info(f"Скачивание файла: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.content
    except requests.RequestException as e:
        logging.error(f"Ошибка при скачивании {url}: {e}")
        return None

    new_hash = hashlib.md5(content).hexdigest()
    old_hash = get_file_hash(filename)

    if new_hash != old_hash:
        with open(filename, "wb") as f:
            f.write(content)
        save_file_hash(filename, new_hash)
        logging.info(f"Файл обновлён: {filename}")
        return filename
    else:
        logging.info(f"Файл не изменился: {filename}")
        return None

def download_all():
    updated_files = []

    for url in XML_URLS:
        file = download_if_changed(url)
        if file:
            updated_files.append(file)

    # Если нет новых файлов — используем все старые из кэша
    if not updated_files:
        for url in XML_URLS:
            filename = os.path.join(CACHE_DIR, url_to_filename(url))
            if os.path.exists(filename):
                updated_files.append(filename)

    return updated_files
