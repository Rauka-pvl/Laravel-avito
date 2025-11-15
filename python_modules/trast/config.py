"""
Конфигурация парсера trast-zapchast.ru
"""
import os

# Базовые пути (совместимо со старой версией)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "..", "..", "storage", "app", "public", "output", "logs-trast")
OUTPUT_FILE = os.path.join(LOG_DIR, "..", "trast.xlsx")
TEMP_OUTPUT_FILE = os.path.join(LOG_DIR, "..", "trast_temp.xlsx")
CSV_FILE = os.path.join(LOG_DIR, "..", "trast.csv")
TEMP_CSV_FILE = os.path.join(LOG_DIR, "..", "trast_temp.csv")
BACKUP_FILE = os.path.join(LOG_DIR, "..", "trast_backup.xlsx")
BACKUP_CSV = os.path.join(LOG_DIR, "..", "trast_backup.csv")

# Создаем директории если их нет
os.makedirs(LOG_DIR, exist_ok=True)

# Прокси (используем относительный путь от текущего файла)
PROXY_CACHE_DIR = os.path.join(os.path.dirname(__file__), "proxy_cache")
PROXIES_FILE = os.path.join(PROXY_CACHE_DIR, "proxies.json")
SUCCESSFUL_PROXIES_FILE = os.path.join(PROXY_CACHE_DIR, "successful_proxies.json")
LAST_UPDATE_FILE = os.path.join(PROXY_CACHE_DIR, "last_update.txt")

# Создаем директорию для прокси
os.makedirs(PROXY_CACHE_DIR, exist_ok=True)

# Настройки парсинга
TARGET_URL = "https://trast-zapchast.ru/shop/"
MAX_EMPTY_PAGES = 2  # Остановка после 2 пустых страниц подряд
PRODUCTS_PER_PAGE = 16  # Стандартное количество товаров на странице

# Таймауты (в секундах)
PAGE_LOAD_TIMEOUT = 25
CLOUDFLARE_WAIT_TIMEOUT = 30
PROXY_TEST_TIMEOUT = 60
BASIC_CHECK_TIMEOUT = 5

# Настройки прокси
MIN_WORKING_PROXIES = 10  # Минимальное количество рабочих прокси перед началом парсинга
MAX_PROXIES_TO_CHECK = 500  # Максимальное количество прокси для проверки (увеличено для надежности)
PROXY_CHECK_THREADS = 2  # Количество потоков для многопоточной проверки прокси

# Фильтр по странам (приоритетные для российского сайта)
PREFERRED_COUNTRIES = [
    "RU", "BY", "KZ",  # СНГ
    "AM", "AZ", "GE", "KG", "MD", "TJ", "TM", "UZ", "UA",  # Остальные СНГ
    "PL", "LT", "LV", "EE", "FI", "CZ", "SK", "HU", "RO", "BG",  # Европа
    "DE", "NL", "SE", "FR",  # Западная Европа
    "CN", "MN"  # Азия
]

# Источники прокси
PROXY_SOURCES = {
    'proxymania': {
        'url': 'https://proxymania.su/free-proxy',
        'type': 'proxymania',
        'active': True
    },
    'proxifly': {
        'url': 'https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json',
        'type': 'json',
        'active': True
    }
}

# Настройки браузера
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Настройки задержек (в секундах)
MIN_DELAY_BETWEEN_PAGES = 2
MAX_DELAY_BETWEEN_PAGES = 4
MIN_DELAY_AFTER_LOAD = 3
MAX_DELAY_AFTER_LOAD = 6

