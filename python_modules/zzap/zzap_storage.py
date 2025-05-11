# zzap/zzap_storage.py
import os
import json
import hashlib
import shutil
import sys
from datetime import datetime


# === Импорт конфигурации из avito ===
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_ZZAP, LOG_DIR, BASE_DIR, OUTPUT_ROOT

# Папки
CACHE_DIR = os.path.join(OUTPUT_ROOT, "zzap_cache")
HASH_FILE = os.path.join(CACHE_DIR, ".zzap_hashes.json")
BACKUP_PATH = os.path.join(OUTPUT_ROOT, "zzap_backup.xml")


# Убедимся, что директории существуют
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(COMBINED_ZZAP), exist_ok=True)

def url_to_filename(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12] + ".xml"

def get_file_hash(filepath: str) -> str | None:
    if not os.path.exists(HASH_FILE):
        return None
    with open(HASH_FILE, "r", encoding="utf-8") as f:
        hashes = json.load(f)
    return hashes.get(os.path.basename(filepath))

def save_file_hash(filepath: str, hash_str: str):
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r", encoding="utf-8") as f:
            hashes = json.load(f)
    else:
        hashes = {}
    hashes[os.path.basename(filepath)] = hash_str
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2)

def backup_combined_yml():
    if os.path.exists(COMBINED_ZZAP):
        shutil.copy2(COMBINED_ZZAP, BACKUP_PATH)
        return True
    return False
