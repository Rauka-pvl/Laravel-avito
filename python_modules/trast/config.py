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
PROXY_HEALTH_FILE = os.path.join(PROXY_CACHE_DIR, "proxy_health.json")

# Параметры отслеживания состояния прокси
PROXY_HEALTH_HISTORY_SIZE = 10  # Количество последних событий, сохраняемых для каждого прокси
PROXY_FAILURE_COOLDOWN_THRESHOLD = 3  # После скольких подряд неудач включать охлаждение
PROXY_COOLDOWN_SECONDS = {
    "timeout": 1800,
    "cloudflare_block": 600,
    "connection_failure": 900,
    "no_page_count": 900,
    "basic_check_failed": 600,
    "default": 600
}

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
PROXY_IP_CHECK_URL = "https://api.ipify.org"

# Настройки прокси
MIN_WORKING_PROXIES = 10  # Минимальное количество рабочих прокси перед началом парсинга
MAX_PROXIES_TO_CHECK = 500  # Максимальное количество прокси для проверки (увеличено для надежности)
PROXY_CHECK_THREADS = 2  # Количество потоков для многопоточной проверки прокси
PARSING_THREADS = 1  # Количество потоков для многопоточного парсинга (четные/нечетные страницы)
ALLOWED_PROXY_PROTOCOLS = ['http', 'https', 'socks4', 'socks5']  # Разрешенные типы прокси (все типы, используется только Firefox)
PROXY_PAGE_FAILURE_COOLDOWN = 900  # 15 минут блокировки для конкретной страницы
USE_UNDETECTED_CHROME = True  # Использовать undetected-chrome для HTTP/HTTPS прокси
FORCE_FIREFOX = os.getenv("TRAST_FORCE_FIREFOX", "1").lower() in ("1", "true", "yes", "on")  # Принудительно использовать Firefox (по умолчанию на сервере)

# Настройки мягкой прогрузки первой страницы
FIRST_PAGE_SCROLL_STEPS = 3
FIRST_PAGE_SCROLL_PAUSE = 1.2
FIRST_PAGE_FINAL_WAIT = 5
FIRST_PAGE_RELOAD_DELAY = 2
BROWSER_RETRY_DELAY = 2.5

# Фильтр по странам (только СНГ для российского сайта)
PREFERRED_COUNTRIES = [
    "RU", "BY", "KZ",  # Основные СНГ
    "AM", "AZ", "GE", "KG", "MD", "TJ", "TM", "UZ", "UA",  # Остальные СНГ
]

# TTL для успешных прокси (в часах)
# Прокси старше этого времени будут автоматически удаляться из кеша
SUCCESSFUL_PROXY_TTL_HOURS = 24  # 24 часа по умолчанию

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
    },
    'proxyscrape': {
        'url': 'https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all',
        'type': 'proxyscrape',
        'active': True
    },
    'spysone': {
        'url': 'https://spys.one/en/free-proxy-list/',
        'type': 'spysone',
        'active': True
    },
    'freeproxylist': {
        'url': 'https://free-proxy-list.net/',
        'type': 'freeproxylist',
        'active': True
    },
    'geonode': {
        'url': 'https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc',
        'type': 'geonode',
        'active': True
    },
    'proxylist_download': {
        'url': 'https://www.proxy-list.download/api/v1/get?type=http',
        'type': 'proxylist_download',
        'active': True
    },
    'proxylist_icu': {
        'url': 'https://www.proxylist.icu/api/proxies',
        'type': 'proxylist_icu',
        'active': True
    },
    'github_clarketm': {
        'url': 'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',
        'type': 'github_text',
        'active': True
    },
    'github_thespeedx': {
        'url': 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
        'type': 'github_text',
        'active': True
    },
    'github_monosans': {
        'url': 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
        'type': 'github_text',
        'active': True
    },
    'proxylist_me': {
        'url': 'https://www.proxylist.me/api/v1/get?type=http',
        'type': 'proxylist_me',
        'active': True
    },
    # Новые источники прокси из СНГ (с поддержкой nginx JS challenge)
    'proxy6': {
        'url': 'https://proxy6.net',
        'type': 'proxy6',
        'active': True  # Парсинг с обходом nginx JS challenge
    },
    'proxys_io': {
        'url': 'https://proxys.io',
        'type': 'proxys_io',
        'active': True  # Парсинг с обходом nginx JS challenge
    },
    'proxy_seller': {
        'url': 'https://proxy-seller.com',
        'type': 'proxy_seller',
        'active': True  # Парсинг с обходом nginx JS challenge
    },
    'floppydata': {
        'url': 'https://floppydata.com',
        'type': 'floppydata',
        'active': True  # Парсинг с обходом nginx JS challenge
    },
    'bright_data': {
        'url': 'https://brightdata.com',
        'type': 'bright_data',
        'active': False  # Требует API ключ (платный сервис)
    },
    'prosox': {
        'url': 'https://prosox.com',
        'type': 'prosox',
        'active': True  # Парсинг с обходом nginx JS challenge
    }
}

# Настройки браузера
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Настройки задержек (в секундах)
MIN_DELAY_BETWEEN_PAGES = 3
MAX_DELAY_BETWEEN_PAGES = 6
HUMAN_DELAY_MIN = 6   # Дополнительная пауза перед следующей страницей
HUMAN_DELAY_MAX = 12
HUMAN_LONG_PAUSE_EVERY = 10  # Каждая N-я страница вызывает дополнительный "перерыв"
HUMAN_LONG_PAUSE_MIN = 15
HUMAN_LONG_PAUSE_MAX = 30
MIN_DELAY_AFTER_LOAD = 3
MAX_DELAY_AFTER_LOAD = 6

# Настройки поиска прокси
PROXY_SEARCH_TIMEOUT = 300  # Максимум 5 минут на поиск нового прокси
PROXY_SEARCH_PROGRESS_LOG_INTERVAL = 30  # Интервал логирования прогресса поиска (секунды)
PROXY_LIST_WAIT_DELAY = 5  # Задержка при ожидании обновления списка прокси (секунды)
PROXY_SEARCH_INITIAL_TIMEOUT = 1800  # Максимум 30 минут на начальный поиск прокси

# Настройки потоков парсинга
PAGE_STEP_FOR_THREADS = 2  # Шаг страниц для чередования между потоками (четные/нечетные)
CSV_BUFFER_SAVE_SIZE = 10  # Размер буфера для периодического сохранения в CSV
CSV_BUFFER_FULL_SIZE = 50  # Размер буфера для полного сохранения в CSV

# Настройки ожидания Cloudflare
CLOUDFLARE_REFRESH_DELAY = 3  # Задержка между обновлениями страницы при ожидании Cloudflare
CLOUDFLARE_REFRESH_WAIT = 2  # Задержка после обновления страницы
CLOUDFLARE_CHECK_INTERVAL = 5  # Интервал проверки Cloudflare (секунды)

