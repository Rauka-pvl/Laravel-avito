import os
import re
import time
import random
import logging
import requests
import shutil
import threading
from time import sleep
from datetime import datetime
from bs4 import BeautifulSoup
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from openpyxl import Workbook, load_workbook
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import geckodriver_autoinstaller
import sys
import csv
from bz_telebot.database_manager import set_script_start, set_script_end
from proxy_manager import ProxyManager

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

def create_driver(proxy=None, proxy_manager=None):
    """Создает Firefox драйвер с улучшенным обходом Cloudflare"""
    geckodriver_autoinstaller.install()
    
    options = Options()
    
    # Базовые настройки
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    
    # Обход Cloudflare - отключение автоматизации
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    # Случайный User-Agent
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    options.set_preference("general.useragent.override", random.choice(user_agents))
    
    # Случайные платформы
    platforms = ["Win32", "MacIntel", "Linux x86_64"]
    options.set_preference("general.platform.override", random.choice(platforms))
    
    # Отключение WebRTC для предотвращения утечек IP
    options.set_preference("media.peerconnection.enabled", False)
    options.set_preference("media.navigator.enabled", False)
    
    # Увеличенные таймауты
    options.set_preference("network.http.connection-timeout", 30)
    options.set_preference("network.http.response.timeout", 30)
    options.set_preference("network.http.keep-alive.timeout", 30)
    
    # Отключение различных функций
    options.set_preference("dom.disable_beforeunload", True)
    options.set_preference("dom.disable_window_open_feature", True)
    options.set_preference("dom.disable_window_move_resize", True)
    options.set_preference("dom.disable_window_flip", True)
    options.set_preference("dom.disable_window_crash_reporter", True)
    
    # Настройка прокси
    if proxy:
        protocol = proxy.get('protocol', 'http').lower()
        ip = proxy['ip']
        port = proxy['port']
        
        if protocol in ['http', 'https']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", ip)
            options.set_preference("network.proxy.http_port", int(port))
            options.set_preference("network.proxy.ssl", ip)
            options.set_preference("network.proxy.ssl_port", int(port))
            options.set_preference("network.proxy.share_proxy_settings", True)
        elif protocol in ['socks4', 'socks5']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", ip)
            options.set_preference("network.proxy.socks_port", int(port))
            if protocol == 'socks5':
                options.set_preference("network.proxy.socks_version", 5)
            else:
                options.set_preference("network.proxy.socks_version", 4)
            options.set_preference("network.proxy.socks_remote_dns", True)
    
    # Создание драйвера
    service = Service()
    driver = webdriver.Firefox(service=service, options=options)
    
    # Дополнительные скрипты для обхода
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def get_pages_count_with_driver(driver, url="https://trast-zapchast.ru/shop/"):
    driver.get(url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
    if last_page_el and last_page_el.has_attr("data-page"):
        return int(last_page_el["data-page"])
    return 1

def get_products_from_page_soup(soup):
    results = []
    cards = soup.select("div.product.product-plate")
    for card in cards:
        stock_badge = card.select_one("div.product-badge.product-stock.instock")
        if not stock_badge or "В наличии" not in stock_badge.text.strip():
            continue

        title_el = card.select_one("a.product-title")
        article_el = card.select_one("div.product-attributes .item:nth-child(1) .value")
        manufacturer_el = card.select_one("div.product-attributes .item:nth-child(2) .value")
        price_el = card.select_one("div.product-price .woocommerce-Price-amount.amount")

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
    return results

def get_driver_with_working_proxy(proxy_manager, start_from_index=0):
    """Получает драйвер с рабочим прокси"""
    max_attempts = 100
    attempt = 0
    
    while attempt < max_attempts:
        try:
            if attempt == 0:
                # Первая попытка - ищем первый рабочий прокси
                proxy = proxy_manager.get_first_working_proxy(max_attempts=100)
            else:
                # Последующие попытки - ищем следующий рабочий прокси
                proxy, start_from_index = proxy_manager.get_next_working_proxy(start_from_index, max_attempts=50)
            
            if not proxy:
                logger.error("Не удалось найти рабочий прокси")
                return None, start_from_index
            
            logger.info(f"Создаем драйвер с прокси {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()})")
            
            driver = create_driver(proxy, proxy_manager)
            
            # Проверяем внешний IP
            try:
                driver.get("https://api.ipify.org")
                time.sleep(2)
                external_ip = driver.page_source.strip()
                if external_ip and len(external_ip) < 20:  # Простая проверка IP
                    logger.info(f"Внешний IP через прокси: {external_ip}")
                else:
                    logger.warning(f"Не удалось получить внешний IP: {external_ip}")
            except Exception as e:
                logger.warning(f"Не удалось проверить внешний IP: {e}")
            
            return driver, start_from_index
            
        except Exception as e:
            logger.error(f"Ошибка при создании драйвера: {e}")
            attempt += 1
            if attempt < max_attempts:
                logger.info(f"Попытка {attempt + 1}/{max_attempts}")
                time.sleep(2)
    
    logger.error("Не удалось создать драйвер после всех попыток")
    return None, start_from_index

def get_pages_count_with_driver(driver, url="https://trast-zapchast.ru/shop/"):
    """Получает количество страниц с улучшенной обработкой Cloudflare"""
    try:
        logger.info("Получаем количество страниц для парсинга...")
        driver.get(url)
        time.sleep(5)  # Увеличиваем время ожидания для Cloudflare
        
        # Проверяем, не заблокированы ли мы
        if "cloudflare" in driver.page_source.lower() or "checking your browser" in driver.page_source.lower():
            logger.warning("Обнаружена страница Cloudflare, ждем...")
            time.sleep(10)
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
        if last_page_el and last_page_el.has_attr("data-page"):
            total_pages = int(last_page_el["data-page"])
            logger.info(f"Найдено {total_pages} страниц для парсинга")
            return total_pages
        else:
            logger.warning("Не удалось найти информацию о количестве страниц, используем 1")
            return 1
    except Exception as e:
        logger.error(f"Ошибка при получении количества страниц: {e}")
        raise

def producer(proxy_manager, first_proxy=None):
    """Основная функция парсинга с поддержкой прокси и умной остановкой"""
    thread_name = "MainThread"
    logger.info(f"[{thread_name}] Starting producer with fast proxy search")
    
    # Используем уже найденный прокси или ищем новый
    if first_proxy:
        logger.info(f"Используем уже найденный прокси: {first_proxy['ip']}:{first_proxy['port']} ({first_proxy.get('protocol', 'http').upper()})")
        driver = create_driver(first_proxy, proxy_manager)
        start_from_index = 0
    else:
        driver, start_from_index = get_driver_with_working_proxy(proxy_manager)
        if not driver:
            logger.error("Не удалось получить драйвер с рабочим прокси")
            return 0
    
    total_collected = 0
    empty_pages_count = 0
    max_empty_pages = 3
    
    try:
        logger.info(f"Начинаем парсинг с прокси: {first_proxy['ip'] if first_proxy else 'unknown'}")
        
        # Получаем количество страниц
        total_pages = get_pages_count_with_driver(driver)
        
        for page_num in range(1, total_pages + 1):
            try:
                page_url = f"https://trast-zapchast.ru/shop/?_paged={page_num}"
                logger.info(f"[{thread_name}] Parsing page {page_num}/{total_pages}")
                
                driver.get(page_url)
                time.sleep(random.uniform(3, 6))  # Увеличиваем время ожидания
                
                # Проверяем на блокировку
                if "cloudflare" in driver.page_source.lower() or "checking your browser" in driver.page_source.lower():
                    logger.warning(f"Страница {page_num} заблокирована Cloudflare, пробуем другой прокси...")
                    driver.quit()
                    driver, start_from_index = get_driver_with_working_proxy(proxy_manager, start_from_index)
                    if not driver:
                        logger.error("Не удалось получить новый драйвер")
                        break
                    continue
                
                soup = BeautifulSoup(driver.page_source, "html.parser")
                products = get_products_from_page_soup(soup)
                
                if products:
                    append_to_excel(OUTPUT_FILE, products)
                    append_to_csv(CSV_FILE, products)
                    logger.info(f"[{thread_name}] Page {page_num}: added {len(products)} products")
                    total_collected += len(products)
                    empty_pages_count = 0  # Сбрасываем счетчик пустых страниц
                else:
                    empty_pages_count += 1
                    logger.warning(f"[{thread_name}] Page {page_num}: no products found (empty pages: {empty_pages_count})")
                    
                    # Умная остановка: если 3 страницы подряд пустые
                    if empty_pages_count >= max_empty_pages:
                        logger.info(f"Найдено {max_empty_pages} пустых страниц подряд. Останавливаем парсинг.")
                        break
                
                # Случайная пауза между страницами
                time.sleep(random.uniform(2, 4))
                
            except Exception as e:
                logger.error(f"Ошибка при парсинге страницы {page_num}: {e}")
                # Пробуем другой прокси при ошибке
                try:
                    driver.quit()
                except:
                    pass
                driver, start_from_index = get_driver_with_working_proxy(proxy_manager, start_from_index)
                if not driver:
                    logger.error("Не удалось получить новый драйвер после ошибки")
                    break
                
    finally:
        try:
            driver.quit()
        except:
            pass
    
    return total_collected

def producer_old():
    """Старая функция producer без прокси (для совместимости)"""
    thread_name = "MainThread"
    logger.info(f"[{thread_name}] Starting producer")
    driver = create_driver()
    total_collected = 0
    try:
        total_pages = get_pages_count_with_driver(driver)
        for page_num in range(1, total_pages + 1):
            page_url = f"https://trast-zapchast.ru/shop/?_paged={page_num}/"
            logger.info(f"[{thread_name}] Parsing page {page_num}/{total_pages}")
            driver.get(page_url)
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            products = get_products_from_page_soup(soup)
            if products:
                append_to_excel(OUTPUT_FILE, products)
                append_to_csv(CSV_FILE, products)
                logger.info(f"[{thread_name}] Page {page_num}: added {len(products)} products")
                total_collected += len(products)
            else:
                logger.warning(f"[{thread_name}] Page {page_num}: no products found")
            time.sleep(random.uniform(1, 2))
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
    logger.info("=== TRAST PARSER STARTED ===")
    logger.info(f"Target URL: https://trast-zapchast.ru/shop/?_paged=1")
    logger.info(f"Start time: {datetime.now()}")
    
    start_time = datetime.now()
    set_script_start(script_name)

    create_new_excel(OUTPUT_FILE)
    create_new_csv(CSV_FILE)

    # Инициализируем прокси менеджер
    logger.info("Step 1: Updating proxy list...")
    proxy_manager = ProxyManager()
    
    # Ищем первый рабочий прокси
    logger.info("Ищем первый рабочий прокси для быстрого старта...")
    first_proxy = proxy_manager.get_first_working_proxy(max_attempts=3000)
    
    if not first_proxy:
        logger.error("Не удалось найти рабочий прокси. Завершаем работу.")
        set_script_end(script_name, status='error')
        exit(1)
    
    logger.info(f"Готовы к быстрому старту парсинга!")
    logger.info("Запуск парсинга с поддержкой прокси и умной остановкой")
    logger.info("============================================================")
    
    # Запускаем парсинг с прокси
    total_products = producer(proxy_manager, first_proxy)

    status = 'done'
    try:
        if total_products >= 100:
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

    logger.info("============================================================")
    logger.info(f"Парсинг завершен! Всего собрано товаров: {total_products}")
    logger.info(f"Время выполнения: {round(duration, 2)} секунд")
    logger.info(f"Статус: {status}")
    logger.info(f"Товаров собрано: {total_products}")
    logger.info("============================================================")
