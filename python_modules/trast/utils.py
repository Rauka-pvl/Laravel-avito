"""
Вспомогательные функции для парсера
"""
import os
import re
import time
import random
import shutil
import csv
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
import geckodriver_autoinstaller
from openpyxl import Workbook
from loguru import logger

try:
    import undetected_chromedriver as uc
    HAS_UNDETECTED_CHROME = True
except ImportError:
    HAS_UNDETECTED_CHROME = False
    try:
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium import webdriver as selenium_webdriver
        HAS_SELENIUM_CHROME = True
    except ImportError:
        HAS_SELENIUM_CHROME = False
    logger.warning("undetected-chromedriver not installed, will use regular Chrome")

from config import (
    PRODUCTS_PER_PAGE,
    PAGE_LOAD_TIMEOUT,
    CLOUDFLARE_WAIT_TIMEOUT,
    MIN_DELAY_BETWEEN_PAGES,
    MAX_DELAY_BETWEEN_PAGES,
    MIN_DELAY_AFTER_LOAD,
    MAX_DELAY_AFTER_LOAD,
    USER_AGENTS,
    OUTPUT_FILE,
    TEMP_OUTPUT_FILE,
    CSV_FILE,
    TEMP_CSV_FILE,
    BACKUP_FILE,
    BACKUP_CSV,
    LOG_DIR,
    CLOUDFLARE_REFRESH_DELAY,
    CLOUDFLARE_REFRESH_WAIT,
    CLOUDFLARE_CHECK_INTERVAL
)


class PaginationNotDetectedError(Exception):
    """Поднимается, когда страница каталога выглядит заблокированной и пагинация недоступна.
    
    Это означает, что прокси не работает для данного сайта и нужно искать другой прокси.
    """
    pass


def is_tab_crashed_error(error) -> bool:
    """Проверяет, является ли ошибка связанной с крашем вкладки Chrome"""
    error_msg = str(error).lower()
    return (
        "tab crashed" in error_msg or
        "session deleted" in error_msg or
        "target frame detached" in error_msg or
        "no such session" in error_msg or
        "chrome not reachable" in error_msg
    )


def safe_get_page_source(driver: webdriver.Remote) -> Optional[str]:
    """
    Безопасно получает page_source с обработкой крашей вкладок
    
    Returns:
        page_source или None при ошибке
    """
    try:
        return driver.page_source
    except Exception as e:
        if is_tab_crashed_error(e):
            logger.error(f"[TAB CRASH] Tab crash while getting page_source: {e}")
        else:
            logger.warning(f"Error getting page_source: {e}")
        return None


def wait_for_cloudflare(
    driver: webdriver.Remote,
    max_wait: int = None,
    thread_name: str = "",
    context: str = ""
) -> Tuple[bool, Optional[str]]:
    """
    Ожидает прохождения Cloudflare проверки.
    
    Args:
        driver: WebDriver объект
        max_wait: Максимальное время ожидания в секундах (по умолчанию из config)
        thread_name: Имя потока для логирования
        context: Контекст для логирования (например, "getting cookies")
        
    Returns:
        tuple: (success: bool, page_source: Optional[str])
        - success: True если Cloudflare прошел, False если таймаут
        - page_source: Исходный HTML страницы или None при ошибке
    """
    if max_wait is None:
        max_wait = CLOUDFLARE_WAIT_TIMEOUT
    
    page_source = safe_get_page_source(driver)
    if not page_source:
        return False, None
    
    page_source_lower = page_source.lower()
    wait_time = 0
    
    log_prefix = f"[{thread_name}] " if thread_name else ""
    context_suffix = f" {context}" if context else ""
    
    while ("cloudflare" in page_source_lower or 
           "checking your browser" in page_source_lower or 
           "just a moment" in page_source_lower) and wait_time < max_wait:
        logger.info(f"{log_prefix}Cloudflare check{context_suffix}... waiting {wait_time}/{max_wait} sec")
        time.sleep(CLOUDFLARE_REFRESH_DELAY)
        try:
            driver.refresh()
            time.sleep(CLOUDFLARE_REFRESH_WAIT)
            page_source = safe_get_page_source(driver)
            if not page_source:
                logger.error(f"{log_prefix}[TAB CRASH] Tab crash during Cloudflare wait{context_suffix}")
                return False, None
            page_source_lower = page_source.lower()
        except Exception as refresh_error:
            logger.warning(f"{log_prefix}Error refreshing page{context_suffix}: {refresh_error}")
            return False, None
        wait_time += CLOUDFLARE_CHECK_INTERVAL
    
    if wait_time >= max_wait:
        logger.warning(f"{log_prefix}Cloudflare check failed{context_suffix} (timeout: {max_wait}s)")
        return False, page_source
    
    return True, page_source


def has_catalog_structure(soup: BeautifulSoup) -> bool:
    """
    Проверяет наличие структуры каталога на странице.
    
    Args:
        soup: BeautifulSoup объект страницы
        
    Returns:
        bool: True если структура каталога присутствует, False иначе
    """
    has_products_grid = bool(soup.select(".products-grid, .products, .shop-container, .woocommerce-products-header"))
    has_pagination = bool(soup.select(".woocommerce-pagination, .page-numbers, .facetwp-pager, .facetwp-pager .facetwp-page"))
    has_menu = bool(soup.select("header, .site-header, .main-navigation, nav, .menu, .navigation"))
    has_footer = bool(soup.select("footer, .site-footer, .footer"))
    has_title = bool(soup.select("title"))
    has_meta = bool(soup.select("meta"))
    
    structure_count = sum([has_products_grid, has_pagination, has_menu, has_footer, has_title, has_meta])
    return structure_count >= 3


def is_page_blocked(soup: BeautifulSoup, page_source: str) -> Dict[str, any]:
    """
    Проверяет, заблокирована ли страница Cloudflare или другими механизмами защиты.
    Улучшенная версия с проверкой на частичную загрузку и альтернативными селекторами.
    
    Args:
        soup: BeautifulSoup объект страницы
        page_source: Исходный HTML страницы (строка)
        
    Returns:
        dict: {"blocked": bool, "reason": str | None, "partial_load": bool}
    """
    page_source_lower = page_source.lower() if page_source else ""
    
    blocker_keywords = [
        "cloudflare", "attention required", "checking your browser", "just a moment",
        "access denied", "forbidden", "service temporarily unavailable",
        "temporarily unavailable", "maintenance", "запрос отклонен",
        "доступ запрещен", "ошибка 403", "ошибка 503", "error 403", "error 503",
        "captcha", "please enable javascript", "varnish cache server",
        "bad gateway", "gateway timeout", "502 bad gateway", "504 gateway timeout",
        "too many requests", "rate limit", "blocked", "banned"
    ]
    
    for keyword in blocker_keywords:
        if keyword in page_source_lower:
            return {"blocked": True, "reason": keyword, "partial_load": False}
    
    # Проверяем структуру каталога с альтернативными селекторами
    has_structure = has_catalog_structure(soup)
    
    # Проверяем наличие товаров с альтернативными селекторами
    product_selectors = [
        "div.product.product-plate",
        ".product.product-plate",
        "div.product",
        ".products-grid .product",
        ".products .product",
        ".shop-container .product",
        ".woocommerce ul.products li.product"
    ]
    
    has_products = False
    for selector in product_selectors:
        if soup.select(selector):
            has_products = True
            break
    
    # Проверяем наличие пагинации с альтернативными селекторами
    pagination_selectors = [
        ".facetwp-pager",
        ".facetwp-pager .facetwp-page",
        ".woocommerce-pagination",
        ".page-numbers",
        ".pagination"
    ]
    
    has_pagination = False
    for selector in pagination_selectors:
        if soup.select(selector):
            has_pagination = True
            break
    
    # Проверяем на частичную загрузку
    # Если есть структура каталога, но нет товаров и пагинации - возможно частичная загрузка
    if has_structure and not has_products and not has_pagination:
        # Проверяем наличие JavaScript-контента (признак динамической загрузки)
        has_scripts = bool(soup.select("script"))
        has_body = bool(soup.select("body"))
        
        if has_scripts and has_body:
            # Возможно частичная загрузка - даем шанс
            return {"blocked": False, "reason": "possible_partial_load", "partial_load": True}
        else:
            # Нет скриптов или body - скорее всего блокировка
            return {"blocked": True, "reason": "no_products_no_pagination_no_scripts", "partial_load": False}
    
    # Если нет структуры каталога - блокировка
    if not has_structure:
        return {"blocked": True, "reason": "no_catalog_structure", "partial_load": False}
    
    # Если есть товары или пагинация - страница не заблокирована
    if has_products or has_pagination:
        return {"blocked": False, "reason": None, "partial_load": False}
    
    # Если ничего не найдено - возможно блокировка
    return {"blocked": True, "reason": "no_products_no_pagination", "partial_load": False}


def is_page_empty(soup: BeautifulSoup, page_source: str, products_in_stock: int, total_products: int = 0) -> Dict[str, any]:
    """
    Определяет статус страницы: пустая (конец данных), заблокированная или частично загруженная.
    
    ВАЖНО: Пустая страница = страница с 16 товарами, но все НЕ в наличии.
    
    Args:
        soup: BeautifulSoup объект страницы
        page_source: Исходный HTML страницы (строка)
        products_in_stock: Количество товаров В НАЛИЧИИ
        total_products: Общее количество товаров на странице (включая не в наличии)
        
    Returns:
        dict: {"status": str, "reason": str | None}
    """
    # Сначала проверяем на блокировку
    block_check = is_page_blocked(soup, page_source)
    if block_check["blocked"]:
        return {"status": "blocked", "reason": block_check["reason"] or "no_dom"}
    
    # Если частичная загрузка - возвращаем специальный статус
    if block_check.get("partial_load", False):
        return {"status": "partial", "reason": "possible_partial_load"}
    
    # Проверяем количество товаров В НАЛИЧИИ
    if products_in_stock == 0:
        # Если есть структура каталога и товары (но не в наличии) - это пустая страница
        if has_catalog_structure(soup) and total_products >= PRODUCTS_PER_PAGE:
            # 16 товаров, но все не в наличии - это пустая страница
            return {"status": "empty", "reason": "all_out_of_stock"}
        elif has_catalog_structure(soup):
            # Есть структура, но нет товаров вообще - это конец данных
            return {"status": "empty", "reason": "no_items"}
        else:
            # Нет структуры - частичная загрузка
            return {"status": "partial", "reason": "partial_dom"}
    elif products_in_stock < 3:
        # Мало товаров в наличии (1-2) - подозрение на частичную загрузку
        return {"status": "partial", "reason": "few_items"}
    else:
        # Товары в наличии есть - страница нормальная
        return {"status": "normal", "reason": None}


def get_products_from_page_soup(soup: BeautifulSoup) -> Tuple[List[Dict], int, int]:
    """
    Парсит товары со страницы с улучшенными селекторами и fallback логикой.
    
    Args:
        soup: BeautifulSoup объект страницы
        
    Returns:
        tuple: (список товаров в наличии, количество товаров в наличии, общее количество товаров)
    """
    results = []
    # Пробуем разные селекторы для карточек товаров
    card_selectors = [
        "div.product.product-plate",
        ".product.product-plate",
        "div.product",
        ".products-grid .product",
        ".products .product"
    ]
    
    cards = []
    for selector in card_selectors:
        cards = soup.select(selector)
        if cards:
            logger.debug(f"Found {len(cards)} products with selector: {selector}")
            break
    
    total_products = len(cards)
    
    for card in cards:
        # Проверяем наличие товара в наличии - пробуем разные селекторы
        stock_selectors = [
            "div.product-badge.product-stock.instock",
            ".product-badge.product-stock.instock",
            "[class*='stock'][class*='instock']",
            "[class*='наличи']"
        ]
        
        stock_badge = None
        for selector in stock_selectors:
            stock_badge = card.select_one(selector)
            if stock_badge:
                break
        
        # Если не нашли через селектор, проверяем по тексту
        if not stock_badge:
            card_text = card.get_text()
            if "В наличии" not in card_text and "в наличии" not in card_text.lower():
                continue  # Пропускаем товары не в наличии
        elif "В наличии" not in stock_badge.get_text() and "в наличии" not in stock_badge.get_text().lower():
            continue  # Пропускаем товары не в наличии
        
        # Извлекаем данные с fallback селекторами
        # Название товара
        title_selectors = [
            "a.product-title",
            ".product-title",
            "a[href*='/product/']",
            "h2 a",
            "h3 a"
        ]
        title_el = None
        for selector in title_selectors:
            title_el = card.select_one(selector)
            if title_el:
                break
        
        # Артикул
        article_selectors = [
            "div.product-attributes .item:nth-child(1) .value",
            ".product-attributes .item:nth-child(1) .value",
            "[class*='article']",
            "[class*='Артикул']"
        ]
        article_el = None
        for selector in article_selectors:
            article_el = card.select_one(selector)
            if article_el:
                break
        
        # Если не нашли через селектор, ищем по тексту
        if not article_el:
            card_text = card.get_text()
            article_match = re.search(r'Артикул[:\s]+([^\n\r]+)', card_text)
            if article_match:
                article_el = type('obj', (object,), {'get_text': lambda: article_match.group(1).strip()})()
        
        # Производитель
        manufacturer_selectors = [
            "div.product-attributes .item:nth-child(2) .value",
            ".product-attributes .item:nth-child(2) .value",
            "[class*='manufacturer']",
            "[class*='Производитель']"
        ]
        manufacturer_el = None
        for selector in manufacturer_selectors:
            manufacturer_el = card.select_one(selector)
            if manufacturer_el:
                break
        
        # Если не нашли через селектор, ищем по тексту
        if not manufacturer_el:
            card_text = card.get_text()
            manufacturer_match = re.search(r'Производитель[:\s]+([^\n\r]+)', card_text)
            if manufacturer_match:
                manufacturer_el = type('obj', (object,), {'get_text': lambda: manufacturer_match.group(1).strip()})()
        
        # Цена
        price_selectors = [
            "div.product-price .woocommerce-Price-amount.amount",
            ".product-price .woocommerce-Price-amount.amount",
            "[class*='price'] .amount",
            "[class*='price']"
        ]
        price_el = None
        for selector in price_selectors:
            price_el = card.select_one(selector)
            if price_el:
                break
        
        # Если не нашли через селектор, ищем по символу рубля
        if not price_el:
            card_text = card.get_text()
            price_match = re.search(r'([\d\s]+)\s*₽', card_text)
            if price_match:
                price_el = type('obj', (object,), {'get_text': lambda: price_match.group(0)})()
        
        # Проверяем, что все необходимые данные найдены
        if not title_el:
            logger.debug("Product skipped: title not found")
            continue
        
        title = title_el.get_text().strip() if hasattr(title_el, 'get_text') else str(title_el).strip()
        
        # Артикул и производитель могут быть необязательными, но желательны
        article = ""
        if article_el:
            article = article_el.get_text().strip() if hasattr(article_el, 'get_text') else str(article_el).strip()
            # Убираем префикс "Артикул:" если есть
            article = re.sub(r'^Артикул[:\s]+', '', article, flags=re.IGNORECASE).strip()
        
        manufacturer = ""
        if manufacturer_el:
            manufacturer = manufacturer_el.get_text().strip() if hasattr(manufacturer_el, 'get_text') else str(manufacturer_el).strip()
            # Убираем префикс "Производитель:" если есть
            manufacturer = re.sub(r'^Производитель[:\s]+', '', manufacturer, flags=re.IGNORECASE).strip()
        
        if not price_el:
            logger.debug(f"Product skipped: price not found for {title[:50]}")
            continue
        
        raw_price = price_el.get_text().strip() if hasattr(price_el, 'get_text') else str(price_el).strip()
        raw_price = raw_price.replace("\xa0", " ").replace("\u00a0", " ")
        clean_price = re.sub(r"[^\d\s]", "", raw_price).strip()
        
        # Если цена не найдена, пропускаем товар
        if not clean_price:
            logger.debug(f"Product skipped: empty price for {title[:50]}")
            continue
        
        product = {
            "manufacturer": manufacturer,
            "article": article,
            "description": title,
            "price": clean_price
        }
        results.append(product)
        logger.debug(f"Product parsed: {title[:60]}... | Art: {article} | Manuf: {manufacturer} | Price: {clean_price}")
    
    return results, len(results), total_products


def create_driver(proxy: Optional[Dict] = None, use_chrome: bool = False) -> Optional[webdriver.Remote]:
    """
    Создает Firefox драйвер с улучшенным обходом Cloudflare.
    Используется только Firefox для поддержки всех типов прокси (включая SOCKS).
    
    Args:
        proxy: Словарь с прокси {"ip": str, "port": int, "protocol": str}
        use_chrome: Игнорируется, всегда используется Firefox
        
    Returns:
        WebDriver объект или None при ошибке
    """
    # Всегда используем Firefox для поддержки всех типов прокси
    logger.debug("Using Firefox driver (supports all proxy types including SOCKS)")
    return _create_firefox_driver(proxy)


def _create_chrome_driver(proxy: Optional[Dict] = None) -> webdriver.Chrome:
    """Создает Chrome драйвер с undetected-chromedriver."""
    if HAS_UNDETECTED_CHROME:
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
        # Игнорируем ошибки SSL-сертификата (для прокси с самоподписанными сертификатами)
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--ignore-certificate-errors-spki-list")
        options.add_argument("--allow-running-insecure-content")
        options.add_argument("--disable-web-security")
        
        selected_ua = random.choice(USER_AGENTS)
        options.add_argument(f"--user-agent={selected_ua}")
        
        # Настройка прокси для Chrome
        if proxy:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            if protocol in ['http', 'https']:
                proxy_arg = f"{protocol}://{ip}:{port}"
                options.add_argument(f"--proxy-server={proxy_arg}")
                logger.debug(f"Chrome proxy configured: {proxy_arg}")
            else:
                raise ValueError(f"Chrome does not support {protocol.upper()} proxy. Use Firefox.")
        
        # Пробуем создать драйвер с автоматическим определением версии
        try:
            # version_main=None позволяет автоматически определить версию Chrome
            driver = uc.Chrome(options=options, version_main=None)
            return driver
        except Exception as e:
            error_msg = str(e).lower()
            # Если ошибка связана с версией ChromeDriver
            if "version" in error_msg and ("chrome" in error_msg or "chromedriver" in error_msg):
                logger.warning(f"ChromeDriver version issue: {e}")
                logger.info("Trying to create driver with use_subprocess=True for automatic update...")
                try:
                    # use_subprocess=True может помочь с автоматическим обновлением ChromeDriver
                    driver = uc.Chrome(options=options, version_main=None, use_subprocess=True)
                    return driver
                except Exception as e2:
                    logger.warning(f"Failed to create driver with use_subprocess: {e2}")
                    logger.info("Recommended to run installation script: python install.py")
                    logger.info("Or update manually: pip install --upgrade --force-reinstall undetected-chromedriver")
                    # Пробрасываем исходную ошибку
                    raise e
            else:
                # Другая ошибка - пробрасываем
                raise
    else:
        # Fallback на обычный Selenium Chrome
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium import webdriver as selenium_webdriver
        from webdriver_manager.chrome import ChromeDriverManager
        
        driver_path = ChromeDriverManager().install()
        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Игнорируем ошибки SSL-сертификата (для прокси с самоподписанными сертификатами)
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--ignore-certificate-errors-spki-list")
        options.add_argument("--allow-running-insecure-content")
        options.add_argument("--disable-web-security")
        
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        selected_ua = random.choice(USER_AGENTS)
        options.add_argument(f"--user-agent={selected_ua}")
        
        if proxy:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            if protocol in ['http', 'https']:
                proxy_arg = f"{protocol}://{ip}:{port}"
                options.add_argument(f"--proxy-server={proxy_arg}")
            else:
                raise ValueError(f"Chrome does not support {protocol.upper()} proxy. Use Firefox.")
        
        service = ChromeService(driver_path)
        driver = selenium_webdriver.Chrome(service=service, options=options)
        
        # Stealth скрипты
        stealth_scripts = """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        window.chrome = { runtime: {} };
        """
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': stealth_scripts})
        
        return driver


def _create_firefox_driver(proxy: Optional[Dict] = None) -> webdriver.Firefox:
    """Создает Firefox драйвер с прокси."""
    try:
        geckodriver_autoinstaller.install()
    except Exception as e:
        logger.warning(f"Error installing geckodriver: {e}, trying to continue...")
    
    options = FirefoxOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Обход Cloudflare
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    selected_ua = random.choice(USER_AGENTS)
    options.set_preference("general.useragent.override", selected_ua)
    
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
        elif protocol in ['socks4', 'socks5']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", ip)
            options.set_preference("network.proxy.socks_port", int(port))
            if protocol == 'socks5':
                options.set_preference("network.proxy.socks_version", 5)
            else:
                options.set_preference("network.proxy.socks_version", 4)
            options.set_preference("network.proxy.socks_remote_dns", True)
    
    try:
        service = Service()
        driver = webdriver.Firefox(service=service, options=options)
        
        # Дополнительные скрипты для обхода детекции
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    except Exception as e:
        error_msg = str(e).lower()
        if "connection refused" in error_msg or "failed to establish" in error_msg:
            logger.error(f"Error connecting to geckodriver: {e}")
            logger.error("geckodriver may not be running or available. Try reinstalling geckodriver.")
        else:
            logger.error(f"Error creating Firefox driver: {e}")
        raise


def get_pages_count_with_driver(driver: webdriver.Remote, url: str = "https://trast-zapchast.ru/shop/") -> Optional[int]:
    """Получает количество страниц с улучшенной обработкой Cloudflare.
    
    Returns:
        int: количество страниц или None при ошибке/блокировке
        None: если страница заблокирована или не удалось определить количество страниц
        
    Raises:
        PaginationNotDetectedError: если страница заблокирована (прокси не работает)
    """
    try:
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        
        logger.info("Getting page count for parsing...")
        
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        try:
            driver.get(url)
        except TimeoutException:
            logger.warning(f"Timeout loading page {url}")
            return None
        except Exception as get_error:
            error_msg = str(get_error).lower()
            if "timeout" in error_msg or "timed out" in error_msg:
                logger.warning(f"Timeout loading page {url}")
                return None
            # Для других ошибок пробрасываем дальше
            raise
        
        # Ждем Cloudflare - используем безопасное получение page_source
        page_source = safe_get_page_source(driver)
        if not page_source:
            logger.error("Failed to get page_source after page load")
            return None
        
        page_source_lower = page_source.lower()
        max_wait = CLOUDFLARE_WAIT_TIMEOUT
        wait_time = 0
        
        while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or 
               "just a moment" in page_source_lower) and wait_time < max_wait:
            logger.info(f"Cloudflare check... waiting {wait_time}/{max_wait} sec")
            time.sleep(3)
            try:
                driver.refresh()
                time.sleep(2)
                page_source = safe_get_page_source(driver)
                if not page_source:
                    logger.error("Tab crash during Cloudflare wait")
                    return None
                page_source_lower = page_source.lower()
            except Exception as refresh_error:
                logger.warning(f"Error refreshing page: {refresh_error}")
                return None
            wait_time += 5
        
        # Скроллим для активации динамического контента (как в старой версии)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(random.uniform(1, 2))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(random.uniform(1, 2))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2, 3))
        
        # Дополнительное ожидание для полной загрузки динамического контента
        time.sleep(8)  # Увеличено с 5 до 8 секунд
        
        # Метод 1: Ищем через Selenium WebDriverWait (самый надежный для динамического контента)
        total_pages = None
        
        try:
            wait = WebDriverWait(driver, 60)  # Увеличено до 60 секунд для медленных прокси
            # Сначала ждем появления товаров или пагинации (более гибкая проверка)
            try:
                # Пробуем дождаться товаров
                products_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.product.product-plate, .products-grid, .products, .shop-container")))
                logger.debug("Products container found via WebDriverWait")
            except:
                logger.debug("Products container not found, trying pagination...")
            
            # Ждем появления пагинации
            pagination_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".facetwp-pager, .woocommerce-pagination, .page-numbers")))
            logger.debug("Pagination found via WebDriverWait")
            
            # Дополнительное ожидание для Firefox (может работать медленнее с SOCKS прокси)
            time.sleep(3)
            
            # Пробуем найти элемент .last с несколькими селекторами
            last_page_element = None
            selectors_to_try = [
                ".facetwp-pager .facetwp-page.last",
                ".facetwp-page.last",
                ".facetwp-pager .last",
                ".woocommerce-pagination .page-numbers .last",
                ".page-numbers .last"
            ]
            
            for selector in selectors_to_try:
                try:
                    # Пробуем через WebDriverWait для надежности
                    last_page_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    if last_page_element:
                        data_page = last_page_element.get_attribute("data-page")
                        if data_page:
                            total_pages = int(data_page)
                            logger.info(f"[OK] Found {total_pages} pages for parsing (via Selenium .last, selector: {selector})")
                            return total_pages
                        # Пробуем получить из текста
                        text_value = last_page_element.text.strip()
                        if text_value.isdigit():
                            total_pages = int(text_value)
                            logger.info(f"[OK] Found {total_pages} pages for parsing (via Selenium .last text, selector: {selector})")
                            return total_pages
                except Exception as selector_error:
                    logger.debug(f"Selector {selector} failed: {selector_error}")
                    continue
            
            # Если .last не найден, ищем все элементы пагинации и берем максимальный номер
            pagination_selectors = [
                ".facetwp-pager .facetwp-page",
                ".facetwp-page",
                ".woocommerce-pagination .page-numbers a",
                ".page-numbers a",
                ".facetwp-pager a"
            ]
            
            for selector in pagination_selectors:
                try:
                    page_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    logger.debug(f"Found {len(page_elements)} pagination elements with selector: {selector}")
                    if page_elements:
                        max_page = 0
                        found_pages = []
                        for page_el in page_elements:
                            # Пробуем data-page атрибут
                            data_page = page_el.get_attribute("data-page")
                            if data_page:
                                try:
                                    page_num = int(data_page)
                                    found_pages.append(page_num)
                                    if page_num > max_page:
                                        max_page = page_num
                                except:
                                    pass
                            else:
                                # Пробуем текст элемента
                                text_value = page_el.text.strip()
                                if text_value.isdigit():
                                    try:
                                        page_num = int(text_value)
                                        found_pages.append(page_num)
                                        if page_num > max_page:
                                            max_page = page_num
                                    except:
                                        pass
                                # Пробуем href для извлечения номера страницы
                                href = page_el.get_attribute("href")
                                if href:
                                    import re
                                    match = re.search(r'[?&]page[=_](\d+)', href)
                                    if match:
                                        try:
                                            page_num = int(match.group(1))
                                            found_pages.append(page_num)
                                            if page_num > max_page:
                                                max_page = page_num
                                        except:
                                            pass
                        
                        logger.debug(f"Found page numbers: {found_pages}")
                        if max_page > 0:
                            total_pages = max_page
                            logger.info(f"[OK] Found {total_pages} pages for parsing (via Selenium, max number from {len(found_pages)} elements, selector: {selector})")
                            return total_pages
                except Exception as find_error:
                    logger.debug(f"Error searching for pagination elements with selector {selector}: {find_error}")
                    continue
        except Exception as wait_error:
            logger.debug(f"WebDriverWait did not help: {wait_error}")
        
        # Метод 2: Пробуем через BeautifulSoup (fallback)
        page_source = safe_get_page_source(driver)
        if not page_source:
            logger.warning("Failed to get page_source for BeautifulSoup")
            return None
        
        page_source_lower = page_source.lower()
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Проверяем на блокировку ПЕРЕД поиском пагинации
        block_indicators = [
            "cloudflare",
            "checking your browser",
            "just a moment",
            "service temporarily unavailable",
            "temporarily unavailable",
            "access denied",
            "ошибка 503",
            "error 503",
            "ошибка 403",
            "error 403",
            "captcha",
            "please enable javascript",
            "attention required",
        ]
        if any(indicator in page_source_lower for indicator in block_indicators):
            logger.warning("[WARNING] Blocking indicators detected on catalog page")
            raise PaginationNotDetectedError("Pagination not found due to blocking or placeholder")
        
        # Проверяем наличие товаров и пагинации с альтернативными селекторами
        product_selectors = [
            "div.product.product-plate",
            ".product.product-plate",
            "div.product",
            ".products-grid .product",
            ".products .product",
            ".shop-container .product"
        ]
        pagination_selectors = [
            ".facetwp-pager .facetwp-page",
            ".facetwp-page",
            ".woocommerce-pagination",
            ".page-numbers",
            ".facetwp-pager"
        ]
        
        has_products = False
        for selector in product_selectors:
            if soup.select(selector):
                has_products = True
                logger.debug(f"Found products with selector: {selector}")
                break
        
        has_pagination_any = False
        for selector in pagination_selectors:
            if soup.select(selector):
                has_pagination_any = True
                logger.debug(f"Found pagination with selector: {selector}")
                break
        
        # Проверяем структуру страницы более тщательно
        has_catalog_structure_check = has_catalog_structure(soup)
        
        if not has_products and not has_pagination_any and not has_catalog_structure_check:
            logger.warning("[WARNING] Catalog does not contain cards and pagination — page may be blocked")
            logger.warning(f"[WARNING] Catalog structure check: {has_catalog_structure_check}")
            raise PaginationNotDetectedError("Pagination not found: missing cards and pagination")
        
        # Если есть структура каталога, но нет товаров/пагинации - возможно частичная загрузка
        if has_catalog_structure_check and not has_products and not has_pagination_any:
            logger.warning("[WARNING] Catalog structure found but no products/pagination - possible partial load")
            # Даем еще одну попытку через дополнительное ожидание
            time.sleep(5)
            page_source = safe_get_page_source(driver)
            if page_source:
                soup = BeautifulSoup(page_source, 'html.parser')
                for selector in product_selectors:
                    if soup.select(selector):
                        has_products = True
                        break
                for selector in pagination_selectors:
                    if soup.select(selector):
                        has_pagination_any = True
                        break
        
        # Ищем пагинацию через BeautifulSoup с альтернативными селекторами
        last_page_selectors = [
            ".facetwp-pager .facetwp-page.last",
            ".facetwp-page.last",
            ".facetwp-pager .last",
            ".woocommerce-pagination .page-numbers .last",
            ".page-numbers .last"
        ]
        
        last_page_el = None
        for selector in last_page_selectors:
            last_page_el = soup.select_one(selector)
            if last_page_el:
                logger.debug(f"Found last page element with selector: {selector}")
                break
        
        if last_page_el and last_page_el.has_attr("data-page"):
            total_pages = int(last_page_el["data-page"])
            logger.info(f"[OK] Found {total_pages} pages for parsing (via BeautifulSoup .last)")
            return total_pages
        
        # Пробуем альтернативные селекторы для всех элементов пагинации
        if not last_page_el:
            pagination_all_selectors = [
                ".facetwp-pager .facetwp-page",
                ".facetwp-page",
                ".woocommerce-pagination .page-numbers a",
                ".page-numbers a",
                ".facetwp-pager a"
            ]
            
            last_page_els = []
            for selector in pagination_all_selectors:
                last_page_els = soup.select(selector)
                if last_page_els:
                    logger.debug(f"Found pagination elements with selector: {selector}")
                    break
            logger.debug(f"Found pagination elements via BeautifulSoup: {len(last_page_els)}")
            if last_page_els:
                # Берем максимальный номер из всех найденных элементов
                max_page = 0
                found_pages = []
                for page_el in last_page_els:
                    data_page = page_el.get("data-page")
                    if data_page:
                        try:
                            page_num = int(data_page)
                            found_pages.append(page_num)
                            if page_num > max_page:
                                max_page = page_num
                        except ValueError:
                            continue
                    else:
                        text_value = page_el.get_text(strip=True)
                        if text_value.isdigit():
                            page_num = int(text_value)
                            found_pages.append(page_num)
                            if page_num > max_page:
                                max_page = page_num
                logger.debug(f"Found page numbers via BeautifulSoup: {found_pages}")
                if max_page > 0:
                    total_pages = max_page
                    logger.info(f"[OK] Found {total_pages} pages for parsing (via BeautifulSoup, max number from {len(found_pages)} elements)")
                    return total_pages
                else:
                    logger.warning(f"[WARNING] Found {len(last_page_els)} pagination elements via BeautifulSoup, but failed to extract page numbers")
        
        if last_page_el and last_page_el.has_attr("data-page"):
            total_pages = int(last_page_el["data-page"])
            logger.info(f"[OK] Found {total_pages} pages for parsing (alternative selector)")
            return total_pages
        
        # Если есть товары, но нет пагинации - это одна страница
        if has_products and not has_pagination_any:
            logger.info("[INFO] Found product cards without pagination — assuming single catalog page")
            return 1
        
        # Если ничего не найдено - это ошибка, прокси не работает
        logger.warning(f"[WARNING] Failed to find page count information")
        logger.warning(f"[WARNING] Page size: {len(page_source)} characters")
        logger.warning(f"[WARNING] Contains 'facetwp': {'facetwp' in page_source_lower}")
        logger.warning(f"[WARNING] Contains 'shop': {'shop' in page_source_lower}")
        logger.warning(f"[WARNING] Has products: {has_products}, has pagination: {has_pagination_any}")
        
        # Сохраняем HTML для отладки
        try:
            debug_file = os.path.join(LOG_DIR, f"debug_pagination_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(page_source)
            logger.warning(f"[WARNING] HTML saved to {debug_file} for debugging")
        except:
            pass
        
        # Если не удалось определить - это блокировка, выбрасываем исключение
        raise PaginationNotDetectedError("Failed to determine page count - page may be blocked")
        
    except PaginationNotDetectedError:
        # Пробрасываем исключение о блокировке
        raise
    except Exception as e:
        logger.error(f"Error getting page count: {e}")
        logger.debug(traceback.format_exc())
        return None


def create_new_csv(csv_path: str):
    """Создает новый CSV файл с заголовками."""
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['Артикул', 'Производитель', 'Описание', 'Цена'])


def append_to_csv(csv_path: str, products: List[Dict]):
    """Добавляет товары в CSV файл."""
    with open(csv_path, 'a', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        for product in products:
            writer.writerow([
                product.get('article', ''),
                product.get('manufacturer', ''),
                product.get('description', ''),
                product.get('price', '')
            ])


def convert_csv_to_excel(csv_path: str, excel_path: str) -> bool:
    """Конвертирует CSV файл в Excel."""
    try:
        if not os.path.exists(csv_path):
            logger.warning(f"CSV file not found: {csv_path}")
            return False
        
        logger.info(f"Converting CSV to Excel: {csv_path} -> {excel_path}")
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Products"
        
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, delimiter=';')
            for row in reader:
                ws.append(row)
        
        wb.save(excel_path)
        file_size = os.path.getsize(excel_path)
        logger.info(f"CSV converted to Excel: {excel_path} (size: {file_size} bytes)")
        return True
        
    except Exception as e:
        logger.error(f"Error converting CSV to Excel: {e}")
        return False


def create_backup():
    """Создает бэкап основных файлов перед обновлением."""
    try:
        if os.path.exists(OUTPUT_FILE):
            shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
            logger.info(f"Excel backup created: {BACKUP_FILE}")
        if os.path.exists(CSV_FILE):
            shutil.copy2(CSV_FILE, BACKUP_CSV)
            logger.info(f"CSV backup created: {BACKUP_CSV}")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")


def finalize_output_files():
    """Финализирует временные файлы - перемещает CSV в основной и конвертирует в Excel."""
    try:
        if os.path.exists(OUTPUT_FILE):
            create_backup()
        
        if os.path.exists(TEMP_CSV_FILE):
            shutil.move(TEMP_CSV_FILE, CSV_FILE)
            logger.info(f"Temporary CSV file moved to main: {CSV_FILE}")
            
            if convert_csv_to_excel(CSV_FILE, OUTPUT_FILE):
                logger.info(f"Excel file created from CSV: {OUTPUT_FILE}")
            else:
                logger.warning("Failed to create Excel file from CSV")
        else:
            logger.warning("Temporary CSV file not found")
            
    except Exception as e:
        logger.error(f"Error finalizing files: {e}")
        raise


def cleanup_temp_files():
    """Удаляет временные файлы в случае ошибки."""
    try:
        if os.path.exists(TEMP_CSV_FILE):
            os.remove(TEMP_CSV_FILE)
            logger.info(f"Temporary CSV file deleted: {TEMP_CSV_FILE}")
        if os.path.exists(TEMP_OUTPUT_FILE):
            os.remove(TEMP_OUTPUT_FILE)
            logger.info(f"Temporary Excel file deleted: {TEMP_OUTPUT_FILE}")
    except Exception as e:
        logger.warning(f"Failed to delete temporary files: {e}")

