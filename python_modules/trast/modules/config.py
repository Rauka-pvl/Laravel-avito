"""
Configuration module for Trast parser.

Centralized configuration management for all parser settings.
"""

import os
from typing import List, Tuple


class TrastConfig:
    """Centralized configuration for Trast parser."""
    
    # File paths
    SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    PROXY_FILES = ['proxies (1).json', '68f0af05c9bf6.txt']
    SESSION_COOKIES_FILE = os.path.join(SCRIPT_DIR, 'trast_session.pkl')
    BACKUP_DIR = os.path.join(SCRIPT_DIR, 'backups')
    
    # Output paths (relative to Laravel storage)
    LOG_DIR = os.path.join(SCRIPT_DIR, "..", "..", "storage", "app", "public", "output", "logs-trast")
    OUTPUT_FILE = os.path.join(LOG_DIR, "..", "trast.xlsx")
    BACKUP_FILE = os.path.join(LOG_DIR, "..", "trast_backup.xlsx")
    CSV_FILE = os.path.join(LOG_DIR, "..", "trast.csv")
    BACKUP_CSV = os.path.join(LOG_DIR, "..", "trast_backup.csv")
    
    # Tor configuration
    TOR_SOCKS_PORT = 9050
    TOR_CONTROL_PORT = 9051
    TOR_DATA_DIR = "/tmp/tor_data"
    TOR_COOKIE_FILE = "/tmp/tor_cookie"
    
    # WARP configuration
    WARP_ENABLED = True
    WARP_PROXY_URL = "socks5://127.0.0.1:40000"  # Default WARP proxy port
    WARP_ALTERNATIVE_PORTS = [40000, 40001, 40002, 40003, 40004]
    
    # Parsing parameters
    PAGES_PER_SESSION = 20
    MAX_EMPTY_PAGES = 10
    MAX_CONSECUTIVE_SPARSE = 20
    SPARSE_THRESHOLD = 5
    MAX_PROXY_FAILURES = 3
    MAX_DRIVER_ATTEMPTS = 5
    
    # Timing and delays
    CLOUDFLARE_DELAY_RANGE = (15, 45)
    EXTRA_DELAY_RANGE = (5, 15)
    SMART_DELAY_RANGE = (5, 10)
    ERROR_DELAY_RANGE = (15, 30)
    SESSION_DELAY_RANGE = (10, 20)
    READING_DELAY_RANGE = (2, 5)
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_TIMEOUT = 20
    PROXY_TEST_TIMEOUT = 5
    
    # Browser configuration
    BROWSER_WIDTH_RANGE = (1366, 1920)
    BROWSER_HEIGHT_RANGE = (768, 1080)
    
    # User agents - Firefox versions for better Tor/WARP compatibility
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0'
    ]
    
    # Browser configuration
    BROWSER_TYPE = "firefox"  # Firefox only for server environment
    GECKODRIVER_PATH = None  # Auto-detect geckodriver path
    
    # Target URLs
    BASE_URL = "https://trast-zapchast.ru"
    MAIN_URL = f"{BASE_URL}/"
    SHOP_URL = f"{BASE_URL}/shop/"
    
    # Pagination pattern
    PAGINATION_PATTERN = "_paged={page}"
    
    # Bulk fetch URLs
    BULK_URLS = [
        f"{SHOP_URL}?per_page=9999",
        f"{SHOP_URL}?posts_per_page=9999",
        f"{SHOP_URL}?limit=9999",
        f"{SHOP_URL}?show_all=1",
        f"{SHOP_URL}?all_products=1"
    ]
    
    # Anti-blocking thresholds
    SUCCESS_THRESHOLD_PERCENT = 80
    PROXY_SUCCESS_THRESHOLD = 3
    
    # Logging
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    LOG_ENCODING = 'utf-8-sig'
    
    @classmethod
    def get_proxy_file_paths(cls) -> List[str]:
        """Get full paths to proxy files."""
        return [os.path.join(cls.SCRIPT_DIR, filename) for filename in cls.PROXY_FILES]
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist."""
        os.makedirs(cls.BACKUP_DIR, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)
    
    @classmethod
    def get_random_user_agent(cls) -> str:
        """Get a random user agent."""
        import random
        return random.choice(cls.USER_AGENTS)
    
    @classmethod
    def get_random_viewport(cls) -> Tuple[int, int]:
        """Get random viewport dimensions."""
        import random
        width = random.randint(*cls.BROWSER_WIDTH_RANGE)
        height = random.randint(*cls.BROWSER_HEIGHT_RANGE)
        return width, height
