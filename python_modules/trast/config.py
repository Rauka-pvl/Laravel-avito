"""
Configuration module for Trast parser.

Centralized configuration management for all parser settings.
"""

import os
from typing import List, Dict, Any

class TrastConfig:
    """Centralized configuration for Trast parser."""
    
    # Script directory
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # Target URLs
    BASE_URL = "https://trast-zapchast.ru"
    SHOP_URL = f"{BASE_URL}/shop/"
    FIRST_PAGE_URL = f"{SHOP_URL}?_paged=1"
    
    # Pagination selector
    PAGINATION_SELECTOR = "a.facetwp-page.last"
    PAGE_COUNT_ATTRIBUTE = "data-page"
    
    # Proxy files
    PROXY_FILES = [
        os.path.join(SCRIPT_DIR, "68f0af05c9bf6.txt"),
        os.path.join(SCRIPT_DIR, "proxies (1).json")
    ]
    
    # TOR configuration
    TOR_SOCKS_HOST = "127.0.0.1"
    TOR_SOCKS_PORT = 9050
    TOR_CONTROL_PORT = 9051
    TOR_PROXY_URL = f"socks5://{TOR_SOCKS_HOST}:{TOR_SOCKS_PORT}"
    
    # WARP configuration
    WARP_SOCKS_HOST = "127.0.0.1"
    WARP_SOCKS_PORT = 40000
    WARP_PROXY_URL = f"socks5://{WARP_SOCKS_HOST}:{WARP_SOCKS_PORT}"
    WARP_ALTERNATIVE_PORTS = [40000, 40001, 40002, 40003, 40004]
    
    # Connection testing
    TEST_URL = "https://httpbin.org/ip"
    CONNECTION_TIMEOUT = 5
    MAX_CONNECTION_ATTEMPTS = 3
    
    # Request settings
    REQUEST_TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    RETRY_BACKOFF_FACTOR = 2
    
    # User agents for rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0'
    ]
    
    # Headers
    DEFAULT_HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache',
    }
    
    # Selenium settings
    SELENIUM_TIMEOUT = 30
    SELENIUM_IMPLICIT_WAIT = 10
    SELENIUM_PAGE_LOAD_TIMEOUT = 30
    SELENIUM_HEADLESS = True
    
    # Browser options
    CHROME_OPTIONS = [
        '--headless',
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-plugins',
        '--disable-images',
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor',
        '--memory-pressure-off',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-background-networking',
        '--aggressive-cache-discard',
        '--disable-blink-features=AutomationControlled'
    ]
    
    FIREFOX_OPTIONS = [
        '--headless',
        '--no-sandbox',
        '--disable-gpu'
    ]
    
    # Delays and timing
    HUMAN_DELAY_MIN = 2
    HUMAN_DELAY_MAX = 5
    CLOUDFLARE_WAIT_MIN = 10
    CLOUDFLARE_WAIT_MAX = 20
    
    # Cloudflare detection patterns
    CLOUDFLARE_INDICATORS = [
        'checking your browser',
        'cloudflare',
        'ddos protection',
        'cf-browser-verification',
        'cf-challenge',
        'access denied',
        'blocked'
    ]
    
    # Output paths
    LOG_DIR = os.path.join(SCRIPT_DIR, "..", "..", "storage", "app", "public", "output", "logs-trast")
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "..", "storage", "app", "public", "output")
    
    # Logging
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    LOG_ENCODING = 'utf-8-sig'
    LOG_LEVEL = 'INFO'
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist."""
        os.makedirs(cls.LOG_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)
    
    @classmethod
    def get_random_user_agent(cls) -> str:
        """Get a random user agent."""
        import random
        return random.choice(cls.USER_AGENTS)
    
    @classmethod
    def get_headers_with_user_agent(cls) -> Dict[str, str]:
        """Get headers with random user agent."""
        headers = cls.DEFAULT_HEADERS.copy()
        headers['User-Agent'] = cls.get_random_user_agent()
        return headers
