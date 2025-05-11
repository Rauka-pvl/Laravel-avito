# xml_updater/config.py
import os
import hashlib
from datetime import datetime

# Корень проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import os
import hashlib
from datetime import datetime

# Корень проекта (где config.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Папка, где всё будет сохраняться (../storage/app/public/output)
OUTPUT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "storage", "app", "public", "output"))

# Пути
CACHE_DIR = os.path.join(OUTPUT_ROOT, "xml_data")
LOG_DIR = os.path.join(OUTPUT_ROOT, "logs-avito")
HASH_FILE = os.path.join(CACHE_DIR, ".hashes.json")
COMBINED_XML = os.path.join(OUTPUT_ROOT, "avito.xml")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
FROZA_DID = os.path.join(BASE_DIR, "logs-froza")

# Гарантируем наличие всех папок
for path in [CACHE_DIR, LOG_DIR, os.path.dirname(COMBINED_XML), ARCHIVE_DIR, FROZA_DID]:
    os.makedirs(path, exist_ok=True)


# Временная метка
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOG_DIR ,f"avito_update_{timestamp}.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Ссылки
XML_URLS = [
    "https://prdownload.nodacdn.net/dfiles/b6fc0d6b-296828-e63b6d87/articles.xml",
    "https://prdownload.nodacdn.net/dfiles/7da749ad-284074-7b2184d7/articles.xml",
]

YML_URLS = [
    "https://www.buszap.ru/get_price?p=219a76583bbd4991ade213a8b15b5808&FranchiseeId=9117065",
    "https://www.buszap.ru/get_price?p=3dbb37d4f12242068faf72c2cf839c82&FranchiseeId=9117065"
]


def url_to_filename(url: str) -> str:
    """Создаёт уникальное имя файла на основе URL."""
    name = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"{name}.xml"