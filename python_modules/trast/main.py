import os
import re
import time
import random
import logging
import requests
import shutil
import threading
import subprocess
from time import sleep
from datetime import datetime
from bs4 import BeautifulSoup
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from openpyxl import Workbook, load_workbook
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import sys
import csv
from bz_telebot.database_manager import set_script_start, set_script_end

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from notification.main import TelegramNotifier

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_XML, LOG_DIR, BASE_DIR

LOG_DIR = os.path.join(BASE_DIR, "..", "..", "storage", "app", "public", "output", "logs-trast")
OUTPUT_FILE = os.path.join(LOG_DIR, "..", "trast.xlsx")
BACKUP_FILE = os.path.join(LOG_DIR, "..", "trast_backup.xlsx")
CSV_FILE = os.path.join(LOG_DIR, "..", "trast.csv")
BACKUP_CSV = os.path.join(LOG_DIR, "..", "trast_backup.csv")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("trast")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"trast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), encoding="utf-8-sig"),
        logging.StreamHandler()
    ]
)

total_products = 0

def create_new_excel(path):
    if os.path.exists(path):
        os.remove(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["Manufacturer", "Article", "Description", "Price"])
    wb.save(path)

def create_new_csv(path):
    if os.path.exists(path):
        os.remove(path)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["Manufacturer", "Article", "Description", "Price"])

def append_to_excel(path, product_list):
    global total_products
    if not os.path.exists(path):
        create_new_excel(path)
    try:
        wb = load_workbook(path)
        ws = wb.active
        for p in product_list:
            ws.append([
                p.get("manufacturer", ""),
                p.get("article", ""),
                p.get("description", ""),
                p.get("price", {}).get("price", "")
            ])
        wb.save(path)
        total_products += len(product_list)
    except Exception as e:
        logger.error(f"Error writing to Excel: {e}")
    logger.info(f"Excel updated with {len(product_list)} records, file size: {os.path.getsize(OUTPUT_FILE)} bytes")

def append_to_csv(path, product_list):
    try:
        with open(path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            for p in product_list:
                writer.writerow([
                    p.get("manufacturer", ""),
                    p.get("article", ""),
                    p.get("description", ""),
                    p.get("price", {}).get("price", "")
                ])
    except Exception as e:
        logger.error(f"Error writing to CSV: {e}")

def check_site_protection(url="https://trast-zapchast.ru/shop/"):
    """Проверяем защиту сайта через HTTP заголовки"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://trast-zapchast.ru/',
            'Cache-Control': 'no-cache',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        logger.info(f"HTTP Status: {response.status_code}")
        logger.info(f"Server: {response.headers.get('Server', 'Unknown')}")
        logger.info(f"X-Powered-By: {response.headers.get('X-Powered-By', 'None')}")
        logger.info(f"X-Cache: {response.headers.get('X-Cache', 'None')}")
        logger.info(f"CF-Cache-Status: {response.headers.get('CF-Cache-Status', 'None')}")
        logger.info(f"X-RateLimit: {response.headers.get('X-RateLimit', 'None')}")
        
        # Check for protection indicators
        protection_indicators = []
        if 'cloudflare' in response.headers.get('Server', '').lower():
            protection_indicators.append("Cloudflare detected")
        if 'cf-cache-status' in response.headers:
            protection_indicators.append("Cloudflare CDN")
        if 'x-rate-limit' in response.headers:
            protection_indicators.append("Rate limiting")
        if response.status_code == 403:
            protection_indicators.append("Access forbidden")
        if response.status_code == 429:
            protection_indicators.append("Too many requests")
            
        if protection_indicators:
            logger.warning(f"Protection detected: {', '.join(protection_indicators)}")
        else:
            logger.info("No obvious protection detected")
            
        return response.status_code == 200
        
    except Exception as e:
        logger.error(f"Error checking site protection: {e}")
        return False

# Proxy servers from Chrome extension
PROXY_SERVERS = [
    # Trafflink VPN servers
    "vpn-uk1.trafflink.xyz:443",
    "vpn-uk2.trafflink.xyz:443", 
    "vpn-uk3.trafflink.xyz:443",
    "vpn-de1.trafflink.xyz:443",
    "vpn-de2.trafflink.xyz:443",
    "vpn-nl1.trafflink.xyz:443",
    "vpn-nl2.trafflink.xyz:443",
    "vpn-ca1.trafflink.xyz:443",
    "vpn-ca2.trafflink.xyz:443",
    
    # Trafcfy servers
    "uk22.trafcfy.com:437",
    "uk23.trafcfy.com:437",
    "uk24.trafcfy.com:437",
    "nl41.trafcfy.com:437",
    "nl42.trafcfy.com:437",
    "nl43.trafcfy.com:437",
    "us21.trafcfy.com:437",
    "us22.trafcfy.com:437",
    "us23.trafcfy.com:437",
    
    # HTTP proxies
    "212.113.123.246:42681",
    "194.87.201.123:24645",
    "92.53.127.107:27807",
    "79.137.133.95:40764",
    "176.124.217.180:12048",
    
    # Public proxies (for testing)
    "8.210.83.33:80",
    "47.74.152.29:8888",
    "47.88.3.19:8080",
    "103.152.112.145:80",
    "103.152.112.162:80",
    "185.162.251.76:80",
    "185.162.251.77:80",
    "185.162.251.78:80",
]

# Tor configuration
TOR_SOCKS_PORT = 9050
TOR_CONTROL_PORT = 9051
TOR_PROCESS = None

def start_tor():
    """Запустить Tor процесс"""
    global TOR_PROCESS
    
    try:
        # Проверяем, не запущен ли уже Tor
        if check_tor_connection():
            logger.info("✅ Tor already running")
            return True
            
        logger.info("Starting Tor process...")
        
        # Запускаем Tor в фоновом режиме
        TOR_PROCESS = subprocess.Popen([
            'tor',
            '--SOCKSPort', str(TOR_SOCKS_PORT),
            '--ControlPort', str(TOR_CONTROL_PORT),
            '--DataDirectory', '/tmp/tor_data',
            '--CookieAuthentication', '1',
            '--CookieAuthFile', '/tmp/tor_cookie'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Ждем запуска Tor
        for i in range(30):  # 30 секунд максимум
            if check_tor_connection():
                logger.info("✅ Tor started successfully")
                return True
            time.sleep(1)
            
        logger.error("❌ Failed to start Tor")
        return False
        
    except Exception as e:
        logger.error(f"Error starting Tor: {e}")
        return False

def stop_tor():
    """Остановить Tor процесс"""
    global TOR_PROCESS
    
    if TOR_PROCESS:
        try:
            TOR_PROCESS.terminate()
            TOR_PROCESS.wait(timeout=10)
            logger.info("✅ Tor stopped")
        except Exception as e:
            logger.error(f"Error stopping Tor: {e}")
            TOR_PROCESS.kill()
        finally:
            TOR_PROCESS = None

def check_tor_connection():
    """Проверить доступность Tor"""
    try:
        proxies = {
            'http': f'socks5://127.0.0.1:{TOR_SOCKS_PORT}',
            'https': f'socks5://127.0.0.1:{TOR_SOCKS_PORT}'
        }
        
        response = requests.get(
            'https://httpbin.org/ip',
            proxies=proxies,
            timeout=10
        )
        
        if response.status_code == 200:
            ip_info = response.json()
            logger.info(f"Tor IP: {ip_info.get('origin', 'Unknown')}")
            return True
            
    except Exception as e:
        logger.debug(f"Tor connection check failed: {e}")
        
    return False

def create_firefox_with_tor():
    """Создать Firefox драйвер с Tor"""
    options = FirefoxOptions()
    
    # Основные настройки
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    
    # Anti-detection для Firefox
    options.set_preference("general.useragent.override", 
                         "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0")
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.set_preference("general.platform.override", "Win32")
    options.set_preference("general.oscpu.override", "Windows NT 10.0; Win64; x64")
    
    # Настройки производительности
    options.set_preference("media.autoplay.default", 5)
    options.set_preference("media.autoplay.enabled", False)
    options.set_preference("media.block-autoplay-until-in-foreground", True)
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("browser.cache.offline.enable", False)
    options.set_preference("network.http.use-cache", False)
    
    # Отключение изображений для скорости
    options.set_preference("permissions.default.image", 2)
    options.set_preference("permissions.default.stylesheet", 2)
    
    # Tor proxy настройки
    options.set_preference("network.proxy.type", 1)  # Manual proxy
    options.set_preference("network.proxy.socks", "127.0.0.1")
    options.set_preference("network.proxy.socks_port", TOR_SOCKS_PORT)
    options.set_preference("network.proxy.socks_version", 5)
    options.set_preference("network.proxy.socks_remote_dns", True)
    
    # Отключение DNS через Tor для скорости
    options.set_preference("network.proxy.socks_remote_dns", False)
    
    try:
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        
        # Дополнительные anti-detection меры
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
        
        logger.info("✅ Firefox with Tor created successfully")
        return driver
        
    except Exception as e:
        logger.error(f"Error creating Firefox with Tor: {e}")
        return None

def test_proxy_connection(proxy):
    """Тестируем подключение через прокси с разными протоколами"""
    protocols = ['http', 'https', 'socks5']
    
    for protocol in protocols:
        try:
            proxies = {
                'https': f'{protocol}://{proxy}',
                'http': f'{protocol}://{proxy}'
            }
            
            response = requests.get(
                'https://trast-zapchast.ru/shop/', 
                proxies=proxies, 
                timeout=5,  # Уменьшаем таймаут для быстрого тестирования
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            if response.status_code == 200:
                return True
                
        except Exception:
            continue
    
    return False

def get_random_proxy():
    """Получить случайный прокси сервер"""
    return random.choice(PROXY_SERVERS)

def test_all_proxies():
    """Тестируем все прокси и возвращаем рабочие"""
    logger.info("Testing proxies...")
    working_proxies = []
    
    for proxy in PROXY_SERVERS:
        if test_proxy_connection(proxy):
            working_proxies.append(proxy)
    
    logger.info(f"Found {len(working_proxies)} working proxies out of {len(PROXY_SERVERS)}")
    return working_proxies

def get_working_proxy():
    """Найти рабочий прокси сервер"""
    for proxy in PROXY_SERVERS:
        if test_proxy_connection(proxy):
            logger.info(f"Using proxy: {proxy}")
            return proxy
    
    logger.error("No working proxy found!")
    return None

def create_driver_with_proxy():
    """Создать драйвер с рабочим прокси"""
    proxy = get_working_proxy()
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    
    # Anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
    options.add_argument(f"--window-size={random.randint(1200, 1920)},{random.randint(900, 1080)}")
    
    # Proxy configuration
    if proxy:
        logger.info(f"Using proxy: {proxy}")
        options.add_argument(f"--proxy-server=https://{proxy}")
    else:
        logger.info("Using direct connection (no proxy)")
        # Enhanced anti-detection for direct connection
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--disable-hang-monitor")
        options.add_argument("--disable-prompt-on-repost")
        options.add_argument("--disable-domain-reliability")
        options.add_argument("--disable-component-extensions-with-background-pages")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-permissions-api")
        options.add_argument("--disable-presentation-api")
        options.add_argument("--disable-print-preview")
        options.add_argument("--disable-speech-api")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--mute-audio")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--no-pings")
        options.add_argument("--no-zygote")
        options.add_argument("--single-process")
    
    # Additional anti-detection measures + speed optimizations
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Faster loading, less memory
    options.add_argument("--disable-web-security")  # Reduce overhead
    options.add_argument("--disable-features=VizDisplayCompositor")  # Reduce GPU usage
    options.add_argument("--memory-pressure-off")  # Disable memory pressure
    options.add_argument("--max_old_space_size=2048")  # Limit memory usage
    options.add_argument("--disable-background-timer-throttling")  # Speed up timers
    options.add_argument("--disable-backgrounding-occluded-windows")  # Speed up rendering
    options.add_argument("--disable-renderer-backgrounding")  # Speed up rendering
    options.add_argument("--disable-background-networking")  # Reduce network overhead
    options.add_argument("--aggressive-cache-discard")  # More aggressive caching
    
    # Additional anti-blocking measures
    options.add_argument("--disable-features=TranslateUI")
    options.add_argument("--disable-ipc-flooding-protection")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-prompt-on-repost")
    options.add_argument("--disable-domain-reliability")
    options.add_argument("--disable-component-extensions-with-background-pages")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--mute-audio")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-permissions-api")
    options.add_argument("--disable-presentation-api")
    options.add_argument("--disable-print-preview")
    options.add_argument("--disable-speech-api")
    options.add_argument("--disable-file-system")
    options.add_argument("--disable-notifications")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # Remove webdriver flag and other detection vectors
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    
    return driver, proxy

def create_driver(use_proxy=True):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    
    # Anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
    options.add_argument(f"--window-size={random.randint(1200, 1920)},{random.randint(900, 1080)}")
    
    # Proxy configuration
    if use_proxy:
        proxy = get_random_proxy()
        logger.info(f"Using proxy: {proxy}")
        options.add_argument(f"--proxy-server=https://{proxy}")
    
    # Additional anti-detection measures + speed optimizations
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Faster loading, less memory
    options.add_argument("--disable-web-security")  # Reduce overhead
    options.add_argument("--disable-features=VizDisplayCompositor")  # Reduce GPU usage
    options.add_argument("--memory-pressure-off")  # Disable memory pressure
    options.add_argument("--max_old_space_size=2048")  # Limit memory usage
    options.add_argument("--disable-background-timer-throttling")  # Speed up timers
    options.add_argument("--disable-backgrounding-occluded-windows")  # Speed up rendering
    options.add_argument("--disable-renderer-backgrounding")  # Speed up rendering
    options.add_argument("--disable-background-networking")  # Reduce network overhead
    options.add_argument("--aggressive-cache-discard")  # More aggressive caching
    
    # Additional anti-blocking measures
    options.add_argument("--disable-features=TranslateUI")
    options.add_argument("--disable-ipc-flooding-protection")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-prompt-on-repost")
    options.add_argument("--disable-domain-reliability")
    options.add_argument("--disable-component-extensions-with-background-pages")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--mute-audio")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-permissions-api")
    options.add_argument("--disable-presentation-api")
    options.add_argument("--disable-print-preview")
    options.add_argument("--disable-speech-api")
    options.add_argument("--disable-file-system")
    options.add_argument("--disable-notifications")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # Remove webdriver flag and other detection vectors
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    
    return driver

def get_pages_count_with_driver(driver, url="https://trast-zapchast.ru/shop/"):
    # Try to access main page first to establish session
    try:
        logger.info("Accessing main page first to establish session...")
        driver.get("https://trast-zapchast.ru/")
        time.sleep(3)
        
        # Now try to access shop page
        logger.info("Now accessing shop page...")
        driver.get(url)
    except Exception as e:
        logger.warning(f"Error accessing main page: {e}")
        driver.get(url)
    
    # Ждем загрузки товаров (FacetWP AJAX) - optimized timeout
    try:
        WebDriverWait(driver, 10).until(  # Reduced from 15 to 10 seconds
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.product.product-plate"))
        )
        time.sleep(2)  # Reduced from 3 to 2 seconds
    except Exception as e:
        logger.warning(f"Timeout waiting for products: {e}")
        # Save HTML for debugging
        with open(os.path.join(LOG_DIR, "debug_page.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
    if last_page_el and last_page_el.has_attr("data-page"):
        return int(last_page_el["data-page"])
    return 1

def get_products_from_page_soup(soup):
    results = []
    cards = soup.select("div.product.product-plate")
    total_cards = len(cards)
    available_cards = 0
    
    for card in cards:
        stock_badge = card.select_one("div.product-badge.product-stock.instock")
        if not stock_badge or "В наличии" not in stock_badge.text.strip():
            continue
        
        available_cards += 1
        title_el = card.select_one("a.product-title")
        article_el = card.select_one("div.product-attributes .item:nth-child(1) .value")
        manufacturer_el = card.select_one("div.product-attributes .item:nth-child(2) .value")
        price_el = card.select_one("div.product-price .amount")

        if not (title_el and article_el and manufacturer_el and price_el):
            continue

        title = title_el.text.strip()
        article = article_el.text.strip()
        manufacturer = manufacturer_el.text.strip()
        raw_price = price_el.text.strip().replace("\xa0", " ")
        clean_price = re.sub(r"[^\d\s]", "", raw_price).strip()

        product = {
            "manufacturer": manufacturer,
            "article": article,
            "description": title,
            "price": {"price": clean_price}
        }
        results.append(product)
        logger.info(f"[Product Added] {product}")
    
    logger.info(f"[Page Stats] Total cards: {total_cards}, Available: {available_cards}, Added: {len(results)}")
    return results

def producer():
    thread_name = "MainThread"
    logger.info(f"[{thread_name}] Starting producer")
    
    # Try Tor + Firefox first
    logger.info("=== TOR + FIREFOX MODE ===")
    if start_tor():
        logger.info("✅ Tor started, creating Firefox driver...")
        driver = create_firefox_with_tor()
        
        if driver:
            logger.info("✅ Firefox with Tor created successfully")
            use_tor = True
        else:
            logger.warning("❌ Failed to create Firefox with Tor, falling back to Chrome")
            driver, current_proxy = create_driver_with_proxy()
            use_tor = False
    else:
        logger.warning("❌ Failed to start Tor, using Chrome with proxies")
        driver, current_proxy = create_driver_with_proxy()
        use_tor = False
    
    total_collected = 0
    proxy_failures = 0
    max_proxy_failures = 3
    
    try:
        total_pages = get_pages_count_with_driver(driver)
        logger.info(f"Total pages detected: {total_pages}")
        
        # Rate limiting protection: optimized for 10-hour completion
        pages_per_session = 20  # Increased from 5 to process more pages per session
        sessions_needed = (total_pages + pages_per_session - 1) // pages_per_session
        
        logger.info(f"Server specs: 2 cores, 4GB RAM - optimized for 10-hour completion")
        logger.info(f"Estimated total products: ~{total_pages * 16}")
        logger.info(f"Expected available products: ~{int(total_pages * 16 * 0.4)} (40% in stock)")
        logger.info(f"Estimated total time: ~{sessions_needed * 0.5} hours (optimized)")
        
        for session in range(sessions_needed):
            start_page = session * pages_per_session + 1
            end_page = min(start_page + pages_per_session - 1, total_pages)
            
            logger.info(f"[{thread_name}] Session {session + 1}/{sessions_needed}: pages {start_page}-{end_page}")
            logger.info(f"[{thread_name}] Current proxy: {current_proxy}")
            
            for page_num in range(start_page, end_page + 1):
                page_url = f"https://trast-zapchast.ru/shop/?_paged={page_num}"
                logger.info(f"[{thread_name}] Parsing page {page_num}/{total_pages}")
                
                try:
                    # Try to access main page first if this is the first page of a session
                    if page_num == start_page:
                        logger.info(f"[{thread_name}] Establishing session for page {page_num}")
                        try:
                            driver.get("https://trast-zapchast.ru/")
                            time.sleep(2)
                        except Exception as e:
                            logger.warning(f"Error accessing main page: {e}")
                    
                    driver.get(page_url)
                    
                    # Check if we got blocked
                    if "blocked" in driver.page_source.lower() or "captcha" in driver.page_source.lower():
                        logger.error(f"[{thread_name}] Page {page_num}: Blocked or CAPTCHA detected!")
                        proxy_failures += 1
                        break
                    
                    # Scroll to trigger lazy loading
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                    time.sleep(1)
                    
                    # Wait for products - optimized timeout
                    try:
                        WebDriverWait(driver, 10).until(  # Reduced from 15 to 10 seconds
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div.product.product-plate"))
                        )
                        time.sleep(2)  # Reduced from 3 to 2 seconds
                    except Exception as e:
                        logger.error(f"[{thread_name}] Page {page_num}: timeout - {e}")
                        proxy_failures += 1
                        with open(os.path.join(LOG_DIR, f"debug_page_{page_num}.html"), "w", encoding="utf-8") as f:
                            f.write(driver.page_source)
                    
                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    products = get_products_from_page_soup(soup)
                    
                    if products:
                        append_to_excel(OUTPUT_FILE, products)
                        append_to_csv(CSV_FILE, products)
                        logger.info(f"[{thread_name}] Page {page_num}/{total_pages}: added {len(products)} products")
                        total_collected += len(products)
                        proxy_failures = 0  # Reset failure counter on success
                    else:
                        logger.warning(f"[{thread_name}] Page {page_num}/{total_pages}: no products found")
                        proxy_failures += 1
                    
                    # Progress logging every 10 pages
                    if page_num % 10 == 0:
                        progress_percent = (page_num / total_pages) * 100
                        logger.info(f"[PROGRESS] {page_num}/{total_pages} pages ({progress_percent:.1f}%) - {total_collected} products collected")
                    
                    # Random delay between pages (optimized for speed)
                    time.sleep(random.uniform(3, 6))
                    
                except Exception as e:
                    logger.error(f"[{thread_name}] Page {page_num}: Error - {e}")
                    proxy_failures += 1
                    # If we get blocked, break the session
                    if "blocked" in str(e).lower() or "forbidden" in str(e).lower():
                        logger.error(f"[{thread_name}] Session terminated due to blocking")
                        break
                
                # Check if we need to switch proxy
                if proxy_failures >= max_proxy_failures:
                    logger.warning(f"[{thread_name}] Too many failures ({proxy_failures}), switching proxy...")
                    driver.quit()
                    driver, current_proxy = create_driver_with_proxy()
                    proxy_failures = 0
                    time.sleep(random.uniform(30, 60))  # Wait before continuing
            
            # Session break: restart driver to avoid rate limiting
            if session < sessions_needed - 1:  # Not the last session
                session_progress = ((session + 1) / sessions_needed) * 100
                logger.info(f"[{thread_name}] Session {session + 1}/{sessions_needed} completed ({session_progress:.1f}%)")
                logger.info(f"[{thread_name}] Total collected so far: {total_collected} products")
                logger.info(f"[{thread_name}] Restarting driver to avoid rate limiting...")
                driver.quit()
                time.sleep(random.uniform(30, 60))  # Wait 30-60 seconds between sessions (optimized)
                driver, current_proxy = create_driver_with_proxy()
                
    finally:
        driver.quit()
        if use_tor:
            logger.info("Stopping Tor process...")
            stop_tor()
    
    logger.info(f"[{thread_name}] FINAL STATS:")
    logger.info(f"[{thread_name}] Total pages processed: {total_pages}")
    logger.info(f"[{thread_name}] Total products collected: {total_collected}")
    logger.info(f"[{thread_name}] Average products per page: {total_collected/total_pages:.1f}")
    
    return total_collected

def create_backup():
    try:
        if os.path.exists(OUTPUT_FILE):
            shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
            logger.info(f"Excel backup created: {BACKUP_FILE}")
        if os.path.exists(CSV_FILE):
            shutil.copy2(CSV_FILE, BACKUP_CSV)
            logger.info(f"CSV backup created: {BACKUP_CSV}")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")

if __name__ == "__main__":
    script_name = "trast"
    TelegramNotifier.notify("🚀 Trast parsing start...")
    start_time = datetime.now()
    set_script_start(script_name)

    # Try Tor first, then fallback to proxies
    logger.info("=== CONNECTION TESTING PHASE ===")
    
    # Test Tor connection first
    if check_tor_connection():
        logger.info("✅ Tor is available")
        TelegramNotifier.notify("✅ Using Tor + Firefox")
    else:
        logger.info("⚠️ Tor not available, testing proxies...")
        working_proxies = test_all_proxies()
        
        if not working_proxies:
            logger.warning("⚠️ No working proxies found, using direct connection...")
            TelegramNotifier.notify("⚠️ Using direct connection (no proxies)")
        else:
            logger.info(f"✅ Found {len(working_proxies)} working proxies")
            TelegramNotifier.notify("✅ Proxy connection established")

    create_new_excel(OUTPUT_FILE)
    create_new_csv(CSV_FILE)

    logger.info("Запуск парсинга в однопоточном режиме")
    total_products = producer()  # 👈 теперь просто вызываем функцию

    status = 'done'
    try:
        # Simple threshold - any products collected is success
        if total_products > 0:
            logger.info(f"✅ Собрано {total_products} товаров")
            create_backup()
        else:
            logger.critical(f"❗ Недостаточно данных: {total_products} товаров")
            status = 'insufficient_data'
            if os.path.exists(BACKUP_FILE):
                shutil.copy2(BACKUP_FILE, OUTPUT_FILE)
                logger.info("Excel восстановлен из бэкапа")
            if os.path.exists(BACKUP_CSV):
                shutil.copy2(BACKUP_CSV, CSV_FILE)
                logger.info("CSV восстановлен из бэкапа")
    except Exception as e:
        logger.exception(f"Ошибка при создании бэкапа: {e}")
        status = 'error'

    duration = (datetime.now() - start_time).total_seconds()
    set_script_end(script_name, status=status)

    logger.info(f"Завершено за {round(duration, 2)} секунд.")
    TelegramNotifier.notify(f"✅ Trast parsing completed. Total: {total_products} items")
