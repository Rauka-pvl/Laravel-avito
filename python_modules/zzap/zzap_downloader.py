# zzap/zzap_downloader.py
import os
import hashlib
import requests

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import YML_URLS, CACHE_DIR, url_to_filename
from zzap_storage import save_file_hash  # Обновили импорт на zzap_storage

def download_and_save(url):
    os.makedirs(CACHE_DIR, exist_ok=True)
    filename = os.path.join(CACHE_DIR, url_to_filename(url))

    response = requests.get(url)
    response.raise_for_status()
    content = response.content

    # Сохраняем файл заново (всегда)
    with open(filename, "wb") as f:
        f.write(content)

    # Сохраняем хэш — просто для истории
    file_hash = hashlib.md5(content).hexdigest()
    save_file_hash(filename, file_hash)

    return filename

def download_all():
    downloaded_files = []
    for url in YML_URLS:
        try:
            file = download_and_save(url)
            downloaded_files.append(file)
        except Exception as e:
            print(f"Ошибка при загрузке {url}: {e}")
    return downloaded_files
