"""Configuration for Trast Parser V2"""

import os
from pathlib import Path
from typing import List

# Base directory
BASE_DIR = Path(__file__).parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage" / "app" / "public" / "output"

# Target website
TARGET_URL = "https://trast-zapchast.ru"
SHOP_URL = f"{TARGET_URL}/shop/"
SHOP_PAGE_URL = f"{SHOP_URL}?_paged={{page}}"

# Output files
LOG_DIR = STORAGE_DIR / "logs-trast"
OUTPUT_EXCEL = STORAGE_DIR / "trast.xlsx"
OUTPUT_CSV = STORAGE_DIR / "trast.csv"
TEMP_EXCEL = STORAGE_DIR / "trast_temp.xlsx"
TEMP_CSV = STORAGE_DIR / "trast_temp.csv"
BACKUP_EXCEL = STORAGE_DIR / "trast_backup.xlsx"
BACKUP_CSV = STORAGE_DIR / "trast_backup.csv"

# Aliases for compatibility
EXCEL_FILE = OUTPUT_EXCEL
CSV_FILE = OUTPUT_CSV

# Proxy configuration
PROXY_CACHE_DIR = Path(__file__).parent / "proxy_cache"
PROXY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROXY_FILE = PROXY_CACHE_DIR / "proxies.json"
SUCCESSFUL_PROXIES_FILE = PROXY_CACHE_DIR / "successful_proxies.json"
LAST_UPDATE_FILE = PROXY_CACHE_DIR / "last_update.txt"

# Proxy countries filter
CIS_COUNTRIES = ["RU", "BY", "KZ", "AM", "AZ", "GE", "KG", "MD", "TJ", "TM", "UZ", "UA"]
EUROPE_COUNTRIES = ["PL", "LT", "LV", "EE", "FI", "CZ", "SK", "HU", "RO", "BG", "DE", "NL", "SE", "FR"]
ASIA_COUNTRIES = ["CN", "MN"]
PROXY_COUNTRIES = CIS_COUNTRIES + EUROPE_COUNTRIES + ASIA_COUNTRIES

# Proxy sources
PROXIFLY_BASE_URL = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies"
PROXYMANIA_BASE_URL = "https://proxymania.su/free-proxy"

# Browser configuration
HEADLESS = True
CHROME_PREFERRED = True  # Prefer Chrome over Firefox when possible
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
]

# Timeouts (seconds)
PAGE_LOAD_TIMEOUT = 25
DRIVER_CREATION_TIMEOUT = 30
PROXY_VALIDATION_TIMEOUT = 60
CLOUDFLARE_WAIT_TIMEOUT = 30

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2.0
RETRY_BACKOFF = 2.0

# Threading configuration
NUM_WORKER_THREADS = 3
PROXY_SEARCH_THREADS = 3
MAX_PROXY_ATTEMPTS_PER_THREAD = 50

# Parsing configuration
BUFFER_SIZE = 50  # Products buffer before writing to file
EMPTY_PAGES_THRESHOLD = 3  # Stop after N empty pages
MIN_PRODUCTS_FOR_SUCCESS = 100  # Minimum products for successful run

# Delays (seconds)
MIN_PAGE_DELAY = 2
MAX_PAGE_DELAY = 4
MIN_PROXY_DELAY = 1
MAX_PROXY_DELAY = 2

# VPS external IP (for proxy verification)
VPS_EXTERNAL_IP = os.getenv("VPS_EXTERNAL_IP", "31.172.69.102")

# IP check services
IP_CHECK_SERVICES = [
    "https://ifconfig.me/ip",
]

# Database (optional)
DB_SCRIPT_NAME = "trast"

# Telegram notifications (optional)
TELEGRAM_ENABLED = True

# Ensure directories exist
LOG_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

