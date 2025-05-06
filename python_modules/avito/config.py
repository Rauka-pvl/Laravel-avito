# xml_updater/config.py
import os
import hashlib

# Корень проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Пути
CACHE_DIR = os.path.join(BASE_DIR, "xml_data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
HASH_FILE = os.path.join(CACHE_DIR, ".hashes.json")
COMBINED_XML = os.path.abspath(os.path.join(BASE_DIR, "..","..", "storage", "output", "combined.xml"))
os.makedirs(os.path.dirname(COMBINED_XML), exist_ok=True)
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
LOG_FILE = os.path.join(LOG_DIR, "update.log")

# Ссылки
XML_URLS = [
    "https://prdownload.nodacdn.net/dfiles/b6fc0d6b-296828-e63b6d87/articles.xml",
    "https://prdownload.nodacdn.net/dfiles/7da749ad-284074-7b2184d7/articles.xml",
]

def url_to_filename(url: str) -> str:
    """Создаёт уникальное имя файла на основе URL."""
    name = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"{name}.xml"