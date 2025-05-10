import os
import json
from config import HASH_FILE, CACHE_DIR

def _load_hashes():
    if not os.path.exists(HASH_FILE):
        return {}
    with open(HASH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_hashes(hashes):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=2, ensure_ascii=False)

def get_file_hash(filepath):
    hashes = _load_hashes()
    return hashes.get(os.path.basename(filepath))

def save_file_hash(filepath, hash_value):
    hashes = _load_hashes()
    hashes[os.path.basename(filepath)] = hash_value
    _save_hashes(hashes)
