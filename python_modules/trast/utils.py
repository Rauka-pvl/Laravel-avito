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
    LOG_DIR
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
    
    Args:
        soup: BeautifulSoup объект страницы
        page_source: Исходный HTML страницы (строка)
        
    Returns:
        dict: {"blocked": bool, "reason": str | None}
    """
    page_source_lower = page_source.lower() if page_source else ""
    
    blocker_keywords = [
        "cloudflare", "attention required", "checking your browser", "just a moment",
        "access denied", "forbidden", "service temporarily unavailable",
        "temporarily unavailable", "maintenance", "запрос отклонен",
        "доступ запрещен", "ошибка 403", "ошибка 503", "error 403", "error 503",
        "captcha", "please enable javascript", "varnish cache server",
        "bad gateway", "gateway timeout",
    ]
    
    for keyword in blocker_keywords:
        if keyword in page_source_lower:
            return {"blocked": True, "reason": keyword}
    
    if not has_catalog_structure(soup):
        return {"blocked": True, "reason": "no_catalog_structure"}
    
    return {"blocked": False, "reason": None}


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
    Парсит товары со страницы.
    
    Args:
        soup: BeautifulSoup объект страницы
        
    Returns:
        tuple: (список товаров в наличии, количество товаров в наличии, общее количество товаров)
    """
    results = []
    cards = soup.select("div.product.product-plate")
    total_products = len(cards)
    
    for card in cards:
        # Проверяем наличие товара в наличии
        stock_badge = card.select_one("div.product-badge.product-stock.instock")
        if not stock_badge or "В наличии" not in stock_badge.text.strip():  # Check for "In stock" text
            continue  # Пропускаем товары не в наличии
        
        # Извлекаем данные
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
            "price": clean_price
        }
        results.append(product)
        logger.info(f"Product added: {product}")
    
    return results, len(results), total_products


def create_driver(proxy: Optional[Dict] = None, use_chrome: bool = True) -> Optional[webdriver.Remote]:
    """
    Создает Chrome или Firefox драйвер с улучшенным обходом Cloudflare.
    
    Args:
        proxy: Словарь с прокси {"ip": str, "port": int, "protocol": str}
        use_chrome: Использовать Chrome (True) или Firefox (False)
        
    Returns:
        WebDriver объект или None при ошибке
    """
    # Проверяем тип прокси - если SOCKS, используем Firefox
    if proxy:
        protocol = proxy.get('protocol', 'http').lower()
        if protocol in ['socks4', 'socks5']:
            logger.info(f"Proxy {protocol.upper()} - using Firefox (Chrome does not support SOCKS)")
            use_chrome = False
    
    # Пробуем Chrome с undetected-chromedriver
    if use_chrome and HAS_UNDETECTED_CHROME:
        try:
            return _create_chrome_driver(proxy)
        except Exception as e:
            logger.warning(f"Chrome not available: {e}, trying Firefox...")
    
    # Fallback на Firefox
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
        time.sleep(5)
        
        # Метод 1: Ищем через Selenium WebDriverWait (самый надежный для динамического контента)
        total_pages = None
        
        try:
            wait = WebDriverWait(driver, 30)  # Увеличено до 30 секунд
            # Сначала ждем появления пагинации
            pagination_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".facetwp-pager")))
            logger.debug("Pagination found via WebDriverWait")
            
            # Пробуем найти элемент .last
            try:
                last_page_element = driver.find_element(By.CSS_SELECTOR, ".facetwp-pager .facetwp-page.last")
                if last_page_element:
                    data_page = last_page_element.get_attribute("data-page")
                    if data_page:
                        total_pages = int(data_page)
                        logger.info(f"[OK] Found {total_pages} pages for parsing (via Selenium .last)")
                        return total_pages
            except:
                pass
            
            # Если .last не найден, ищем все элементы пагинации и берем максимальный номер
            try:
                page_elements = driver.find_elements(By.CSS_SELECTOR, ".facetwp-pager .facetwp-page")
                logger.debug(f"Found pagination elements: {len(page_elements)}")
                if page_elements:
                    max_page = 0
                    found_pages = []
                    for page_el in page_elements:
                        data_page = page_el.get_attribute("data-page")
                        if data_page:
                            try:
                                page_num = int(data_page)
                                found_pages.append(page_num)
                                if page_num > max_page:
                                    max_page = page_num
                            except:
                                pass
                    logger.debug(f"Found page numbers: {found_pages}")
                    if max_page > 0:
                        total_pages = max_page
                        logger.info(f"[OK] Found {total_pages} pages for parsing (via Selenium, max number from {len(found_pages)} elements)")
                        return total_pages
                    else:
                        logger.warning(f"[WARNING] Found {len(page_elements)} pagination elements, but failed to extract page numbers")
            except Exception as find_error:
                logger.debug(f"Error searching for all pagination elements: {find_error}")
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
        
        # Проверяем наличие товаров и пагинации
        has_products = bool(soup.select("div.product.product-plate"))
        has_pagination_any = bool(soup.select(".facetwp-pager .facetwp-page"))
        
        if not has_products and not has_pagination_any:
            logger.warning("[WARNING] Catalog does not contain cards and pagination — page may be blocked")
            raise PaginationNotDetectedError("Pagination not found: missing cards and pagination")
        
        # Ищем пагинацию через BeautifulSoup
        last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
        
        if last_page_el and last_page_el.has_attr("data-page"):
            total_pages = int(last_page_el["data-page"])
            logger.info(f"[OK] Found {total_pages} pages for parsing (via BeautifulSoup .last)")
            return total_pages
        
        # Пробуем альтернативные селекторы
        if not last_page_el:
            last_page_el = soup.select_one(".facetwp-page.last")
        if not last_page_el:
            last_page_els = soup.select(".facetwp-pager .facetwp-page")
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

