import os
import re
import time
import random
import logging
import requests
import shutil
import threading
import subprocess
import traceback
import json
import glob
import pickle
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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import csv
from bz_telebot.database_manager import set_script_start, set_script_end

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from notification.main import TelegramNotifier

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_XML, LOG_DIR, BASE_DIR

# Все пути относительно папки trast
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROXIES_FILE_JSON = os.path.join(SCRIPT_DIR, 'proxies (1).json')
PROXIES_FILE_TXT = os.path.join(SCRIPT_DIR, '68f0af05c9bf6.txt')
SESSION_COOKIES_FILE = os.path.join(SCRIPT_DIR, 'trast_session.pkl')
BACKUP_DIR = os.path.join(SCRIPT_DIR, 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)

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

# Загрузка прокси из обоих файлов
def load_proxies_from_json():
    """Загружает прокси из JSON файла"""
    try:
        with open(PROXIES_FILE_JSON, 'r', encoding='utf-8') as f:
            proxies_data = json.load(f)
            proxies = [f"{p['ip_address']}:{p['port']}" for p in proxies_data]
            logger.info(f"Загружено {len(proxies)} прокси из JSON файла")
            return proxies
    except Exception as e:
        logger.error(f"Ошибка загрузки JSON прокси: {e}")
        return []

def load_proxies_from_txt():
    """Загружает прокси из TXT файла"""
    try:
        proxies = []
        with open(PROXIES_FILE_TXT, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    proxies.append(line)
        logger.info(f"Загружено {len(proxies)} прокси из TXT файла")
        return proxies
    except Exception as e:
        logger.error(f"Ошибка загрузки TXT прокси: {e}")
        return []

def load_all_proxies():
    """Загружает прокси из всех доступных файлов"""
    json_proxies = load_proxies_from_json()
    txt_proxies = load_proxies_from_txt()
    
    all_proxies = json_proxies + txt_proxies
    logger.info(f"Всего загружено {len(all_proxies)} прокси")
    return all_proxies

PROXY_LIST = load_all_proxies()

# Умная ротация прокси
current_proxy_index = 0
failed_proxies = set()
proxy_success_count = {}

def get_next_working_proxy():
    global current_proxy_index
    attempts = 0
    max_attempts = min(50, len(PROXY_LIST))
    
    while attempts < max_attempts:
        proxy = PROXY_LIST[current_proxy_index]
        current_proxy_index = (current_proxy_index + 1) % len(PROXY_LIST)
        
        if proxy in failed_proxies:
            attempts += 1
            continue
        
        success, protocol = test_proxy_quick(proxy)
        if success:
            logger.info(f"Используем прокси: {proxy} (протокол: {protocol})")
            return proxy, protocol
        else:
            failed_proxies.add(proxy)
            attempts += 1
    
    logger.warning("Рабочие прокси не найдены, прямое подключение")
    return None, None

def mark_proxy_success(proxy):
    if proxy:
        proxy_success_count[proxy] = proxy_success_count.get(proxy, 0) + 1
        if proxy in failed_proxies and proxy_success_count[proxy] > 3:
            failed_proxies.remove(proxy)

def mark_proxy_failure(proxy):
    if proxy:
        failed_proxies.add(proxy)
        if proxy in proxy_success_count:
            del proxy_success_count[proxy]

def test_proxy_quick(proxy, timeout=5):
    """Тестирует прокси с автоматическим определением протокола"""
    protocols = ['http', 'https', 'socks4', 'socks5']
    
    for protocol in protocols:
        try:
            if protocol.startswith('socks'):
                # Для SOCKS прокси используем специальный формат
                proxy_url = f"{protocol}://{proxy}"
            else:
                proxy_url = f"{protocol}://{proxy}"
            
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            response = requests.get(
                'https://httpbin.org/ip', 
                proxies=proxies, 
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            
            if response.status_code == 200:
                logger.debug(f"Прокси {proxy} работает с протоколом {protocol}")
                return True, protocol
                
        except Exception as e:
            logger.debug(f"Прокси {proxy} не работает с {protocol}: {e}")
            continue
    
    return False, None

# Продвинутая ротация User-Agent
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/134.0.0.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/134.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15'
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

# Сохранение куков между сессиями
def save_session_cookies(driver):
    try:
        cookies = driver.get_cookies()
        with open(SESSION_COOKIES_FILE, 'wb') as f:
            pickle.dump(cookies, f)
        logger.debug("Куки сохранены в trast/")
    except Exception as e:
        logger.error(f"Ошибка сохранения куков: {e}")

def load_session_cookies(driver):
    try:
        if os.path.exists(SESSION_COOKIES_FILE):
            with open(SESSION_COOKIES_FILE, 'rb') as f:
                cookies = pickle.load(f)
            driver.get("https://trast-zapchast.ru/")
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except:
                    pass
            logger.debug("Куки загружены из trast/")
    except Exception as e:
        logger.error(f"Ошибка загрузки куков: {e}")

# Stealth драйвер с прокси
def create_stealth_driver(proxy=None, protocol=None):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    
    if proxy and protocol:
        if protocol.startswith('socks'):
            options.add_argument(f"--proxy-server={protocol}://{proxy}")
        else:
            options.add_argument(f"--proxy-server={protocol}://{proxy}")
        logger.info(f"Настроен прокси: {protocol}://{proxy}")
    
    user_agent = get_random_user_agent()
    options.add_argument(f"user-agent={user_agent}")
    
    width = random.randint(1366, 1920)
    height = random.randint(768, 1080)
    options.add_argument(f"--window-size={width},{height}")
    
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    options.add_argument("--disable-images")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en']});
            window.chrome = {runtime: {}};
        """
    })
    
    return driver

# Умная система задержек
def smart_delay(page_num, had_error=False):
    if had_error:
        delay = random.uniform(15, 30)
    elif page_num % 10 == 0:
        delay = random.uniform(10, 20)
    else:
        delay = random.uniform(5, 10)
    
    logger.debug(f"Задержка {delay:.1f}с перед следующим запросом")
    time.sleep(delay)

# Механизм повторных попыток
def fetch_page_with_retry(driver, url, current_proxy, max_retries=3):
    for attempt in range(max_retries):
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.product.product-plate"))
            )
            mark_proxy_success(current_proxy)
            return True, driver, current_proxy
        except Exception as e:
            wait_time = (2 ** attempt) * 5
            logger.warning(f"Попытка {attempt+1}/{max_retries} неудачна, ждем {wait_time}с")
            time.sleep(wait_time)
            
            if attempt < max_retries - 1:
                mark_proxy_failure(current_proxy)
                driver.quit()
                new_proxy, new_protocol = get_next_working_proxy()
                driver = create_stealth_driver(new_proxy, new_protocol)
                current_proxy = new_proxy
    
    return False, driver, current_proxy

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

# Система умных бэкапов
def create_backup_with_metadata(excel_file, csv_file, product_count, pages_processed):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    backup_excel = os.path.join(BACKUP_DIR, f"trast_backup_{timestamp}.xlsx")
    backup_csv = os.path.join(BACKUP_DIR, f"trast_backup_{timestamp}.csv")
    
    if os.path.exists(excel_file):
        shutil.copy2(excel_file, backup_excel)
    if os.path.exists(csv_file):
        shutil.copy2(csv_file, backup_csv)
    
    metadata = {
        'timestamp': timestamp,
        'product_count': product_count,
        'pages_processed': pages_processed,
        'excel_file': backup_excel,
        'csv_file': backup_csv,
        'excel_size': os.path.getsize(backup_excel) if os.path.exists(backup_excel) else 0,
        'csv_size': os.path.getsize(backup_csv) if os.path.exists(backup_csv) else 0
    }
    
    metadata_file = os.path.join(BACKUP_DIR, f"metadata_{timestamp}.json")
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Бэкап создан в trast/backups/: {product_count} товаров")
    return metadata

def get_best_backup():
    metadata_files = glob.glob(os.path.join(BACKUP_DIR, "metadata_*.json"))
    
    if not metadata_files:
        return None
    
    best_backup = None
    max_products = 0
    
    for meta_file in metadata_files:
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                if metadata['product_count'] > max_products:
                    max_products = metadata['product_count']
                    best_backup = metadata
        except Exception as e:
            logger.error(f"Ошибка чтения метаданных: {e}")
    
    return best_backup

def smart_restore(current_product_count, threshold_percent=80):
    best_backup = get_best_backup()
    
    if not best_backup:
        logger.info("Нет бэкапов для сравнения")
        return False
    
    best_count = best_backup['product_count']
    threshold = best_count * (threshold_percent / 100)
    
    logger.info(f"Сравнение: Текущий={current_product_count}, Лучший={best_count}, Порог={threshold:.0f}")
    
    if current_product_count < threshold:
        logger.warning(f"Текущий результат ниже порога, восстановление...")
        
        if os.path.exists(best_backup['excel_file']):
            shutil.copy2(best_backup['excel_file'], OUTPUT_FILE)
            logger.info(f"Excel восстановлен из trast/backups/")
        
        if os.path.exists(best_backup['csv_file']):
            shutil.copy2(best_backup['csv_file'], CSV_FILE)
            logger.info(f"CSV восстановлен из trast/backups/")
        
        TelegramNotifier.notify(
            f"⚠️ Trast: Автовосстановление\n"
            f"Текущий: {current_product_count}\n"
            f"Восстановлен: {best_count} ({best_backup['timestamp']})"
        )
        
        return True
    else:
        logger.info("Текущий результат приемлем")
        return False

def incremental_backup(session_num, total_collected, pages_processed):
    logger.info(f"Инкрементный бэкап после сессии {session_num}")
    create_backup_with_metadata(OUTPUT_FILE, CSV_FILE, total_collected, pages_processed)

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

# Оптимизация: попытка получить все данные за один запрос
def try_bulk_data_fetch(driver):
    """Пытается получить все данные за один запрос через API или специальные параметры"""
    try:
        # Попробуем разные варианты bulk запросов
        bulk_urls = [
            "https://trast-zapchast.ru/shop/?per_page=9999",  # Все товары на одной странице
            "https://trast-zapchast.ru/shop/?posts_per_page=9999",
            "https://trast-zapchast.ru/shop/?limit=9999",
            "https://trast-zapchast.ru/shop/?show_all=1",
            "https://trast-zapchast.ru/shop/?all_products=1"
        ]
        
        for bulk_url in bulk_urls:
            try:
                logger.info(f"Пробуем bulk запрос: {bulk_url}")
                driver.get(bulk_url)
                time.sleep(5)  # Даем время на загрузку
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                products = get_products_from_page_soup(soup)
                
                if len(products) > 100:  # Если получили много товаров
                    logger.info(f"✅ Bulk запрос успешен! Получено {len(products)} товаров")
                    return products
                    
            except Exception as e:
                logger.debug(f"Bulk запрос {bulk_url} не сработал: {e}")
                continue
        
        logger.info("Bulk запросы не сработали, используем обычный парсинг")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка в bulk запросе: {e}")
        return None

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
    
    logger.info("=== STEALTH MODE (прокси + анти-детект) ===")
    current_proxy, current_protocol = get_next_working_proxy()
    driver = create_stealth_driver(current_proxy, current_protocol)
    load_session_cookies(driver)
    
    total_collected = 0
    proxy_failures = 0
    max_proxy_failures = 3
    
    # Early exit optimization
    empty_pages_count = 0
    max_empty_pages = 10  # Увеличили с 3 до 10
    last_productive_page = 0
    
    # Детекция разреженных страниц
    sparse_threshold = 5
    consecutive_sparse = 0
    max_consecutive_sparse = 20
    
    try:
        # Сначала попробуем получить все данные за один запрос
        logger.info(f"[{thread_name}] Пробуем bulk запрос для получения всех данных...")
        bulk_products = try_bulk_data_fetch(driver)
        
        if bulk_products and len(bulk_products) > 100:
            logger.info(f"[{thread_name}] ✅ Bulk запрос успешен! Получено {len(bulk_products)} товаров")
            append_to_excel(OUTPUT_FILE, bulk_products)
            append_to_csv(CSV_FILE, bulk_products)
            total_collected = len(bulk_products)
            logger.info(f"[{thread_name}] Все товары получены за один запрос!")
            return total_collected
        
        # Если bulk не сработал, используем обычный парсинг
        logger.info(f"[{thread_name}] Bulk запрос не сработал, переходим к обычному парсингу...")
        total_pages = get_pages_count_with_driver(driver)
        logger.info(f"[{thread_name}] Total pages to parse: {total_pages}")
        
        # Session-based parsing for rate limiting
        pages_per_session = 20  # Увеличили для оптимизации
        sessions_needed = (total_pages + pages_per_session - 1) // pages_per_session
        
        logger.info(f"[{thread_name}] Will parse in {sessions_needed} sessions of {pages_per_session} pages each")
        
        for session in range(sessions_needed):
            session_start_page = session * pages_per_session + 1
            session_end_page = min((session + 1) * pages_per_session, total_pages)
            
            logger.info(f"[{thread_name}] Session {session + 1}/{sessions_needed}: pages {session_start_page}-{session_end_page}")
            
            for page_num in range(session_start_page, session_end_page + 1):
                try:
                    url = f"https://trast-zapchast.ru/shop/?_paged={page_num}"
                    logger.info(f"[{thread_name}] Parsing page {page_num}/{total_pages}")
                    
                    # Используем механизм повторных попыток
                    success, driver, current_proxy = fetch_page_with_retry(driver, url, current_proxy)
                    
                    if not success:
                        logger.error(f"[{thread_name}] Failed to load page {page_num} after retries")
                        proxy_failures += 1
                        continue
                    
                    # Парсим продукты
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    products = get_products_from_page_soup(soup)
                    
                    if products:
                        logger.info(f"[{thread_name}] Page {page_num}: found {len(products)} products")
                        append_to_excel(OUTPUT_FILE, products)
                        append_to_csv(CSV_FILE, products)
                        total_collected += len(products)
                        empty_pages_count = 0
                        last_productive_page = page_num
                        
                        # Сброс счетчика разреженных страниц
                        if len(products) >= sparse_threshold:
                            consecutive_sparse = 0
                        else:
                            consecutive_sparse += 1
                    else:
                        logger.warning(f"[{thread_name}] Page {page_num}: no products found")
                        empty_pages_count += 1
                        consecutive_sparse += 1
                    
                    # Проверка на ранний выход
                    if empty_pages_count >= max_empty_pages:
                        logger.warning(f"[{thread_name}] Stopping early: {empty_pages_count} consecutive empty pages")
                        break
                    
                    if consecutive_sparse >= max_consecutive_sparse:
                        logger.warning(f"[{thread_name}] Stopping early: {consecutive_sparse} consecutive sparse pages")
                        break
                    
                    # Умные задержки
                    smart_delay(page_num, had_error=False)
                    
                    # Сохраняем куки каждые 50 страниц
                    if page_num % 50 == 0:
                        save_session_cookies(driver)
                    
                except Exception as e:
                    logger.error(f"[{thread_name}] Error on page {page_num}: {e}")
                    proxy_failures += 1
                    smart_delay(page_num, had_error=True)
                    
                    # Check if we need to switch proxy
                    if proxy_failures >= max_proxy_failures:
                        logger.warning(f"[{thread_name}] Too many failures ({proxy_failures}), switching proxy...")
                        driver.quit()
                        logger.info("🔄 Recreating Chrome with new proxy...")
                        current_proxy, current_protocol = get_next_working_proxy()
                        driver = create_stealth_driver(current_proxy, current_protocol)
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
                logger.info("🔄 Recreating Chrome with proxy for new session...")
                current_proxy, current_protocol = get_next_working_proxy()
                driver = create_stealth_driver(current_proxy, current_protocol)
                
                # Инкрементный бэкап после каждой сессии
                incremental_backup(session + 1, total_collected, page_num)
        
        logger.info(f"[{thread_name}] Parsing completed. Total products collected: {total_collected}")
        logger.info(f"[{thread_name}] Last productive page: {last_productive_page}")
        logger.info(f"[{thread_name}] Empty pages count: {empty_pages_count}")
        logger.info(f"[{thread_name}] Consecutive sparse pages: {consecutive_sparse}")
        
    except Exception as e:
        logger.error(f"[{thread_name}] Critical error in producer: {e}")
        logger.error(f"[{thread_name}] Traceback: {traceback.format_exc()}")
        
    finally:
        driver.quit()
    
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

    logger.info("=== ФАЗА ИНИЦИАЛИЗАЦИИ ===")
    logger.info(f"Загружено {len(PROXY_LIST)} прокси")
    logger.info(f"Бэкапы: {BACKUP_DIR}")

    create_new_excel(OUTPUT_FILE)
    create_new_csv(CSV_FILE)

    logger.info("Запуск парсинга в однопоточном режиме")
    total_products = producer()
    
    # Создать финальный бэкап если есть товары
    if total_products > 0:
        create_backup_with_metadata(OUTPUT_FILE, CSV_FILE, total_products, 0)
        
        # Умное восстановление
        if not smart_restore(total_products, threshold_percent=80):
            logger.info("Текущий результат приемлем, восстановление не требуется")
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    logger.info(f"Парсинг завершен за {duration}")
    logger.info(f"Всего товаров: {total_products}")
    
    if total_products > 0:
        logger.info("✅ Парсинг успешен")
        TelegramNotifier.notify(f"✅ Trast parsing completed\nТоваров: {total_products}\nВремя: {duration}")
        set_script_end(script_name, "completed")
    else:
        logger.error("❌ Недостаточно данных: 0 товаров")
        TelegramNotifier.notify("❌ Trast parsing failed: 0 товаров")
        set_script_end(script_name, "insufficient_data")
        
        # Попытка восстановления из бэкапа
        if os.path.exists(BACKUP_FILE):
            shutil.copy2(BACKUP_FILE, OUTPUT_FILE)
            logger.info("Excel восстановлен из бэкапа")
        if os.path.exists(BACKUP_CSV):
            shutil.copy2(BACKUP_CSV, CSV_FILE)
            logger.info("CSV восстановлен из бэкапа")
