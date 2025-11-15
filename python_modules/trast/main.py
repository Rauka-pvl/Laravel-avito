"""
Главный файл парсера trast-zapchast.ru
Однопоточный парсинг с улучшенным обходом Cloudflare
"""
import os
import sys
import time
import random
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from loguru import logger
import cloudscraper

from config import (
    TARGET_URL, MAX_EMPTY_PAGES, MIN_WORKING_PROXIES, MAX_PROXIES_TO_CHECK,
    PREFERRED_COUNTRIES, TEMP_CSV_FILE, OUTPUT_FILE, CSV_FILE,
    MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES,
    MIN_DELAY_AFTER_LOAD, MAX_DELAY_AFTER_LOAD, LOG_DIR
)
from proxy_manager import ProxyManager
from utils import (
    create_driver, get_pages_count_with_driver, get_products_from_page_soup,
    is_page_blocked, is_page_empty, create_new_csv, append_to_csv,
    finalize_output_files, cleanup_temp_files, create_backup
)


# Настройка логирования
LOG_FILE = os.path.join(LOG_DIR, f"trast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logger.add(LOG_FILE, encoding='utf-8', rotation='10 MB', retention='7 days')
logger.add(sys.stderr, level='INFO')


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


def is_proxy_error(error) -> bool:
    """Проверяет, является ли ошибка связанной с прокси"""
    error_msg = str(error).lower()
    return (
        "proxyconnectfailure" in error_msg or
        ("proxy" in error_msg and ("refusing" in error_msg or "connection" in error_msg or "failed" in error_msg)) or
        ("neterror" in error_msg and "proxy" in error_msg)
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
            logger.error(f"[TAB CRASH] Краш вкладки при получении page_source: {e}")
        else:
            logger.warning(f"Ошибка при получении page_source: {e}")
        return None


def reload_page_if_needed(
    driver: webdriver.Remote,
    page_url: str,
    max_retries: int = 1
) -> Tuple[Optional[BeautifulSoup], bool]:
    """
    Перезагружает страницу если нужно (при частичной загрузке или ошибках).
    
    Args:
        driver: WebDriver объект
        page_url: URL страницы для загрузки
        max_retries: Максимальное количество попыток перезагрузки
        
    Returns:
        tuple: (soup, success) - BeautifulSoup объект и флаг успеха
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.info(f"[RETRY] Перезагружаем страницу {page_url} (попытка {attempt + 1}/{max_retries + 1})...")
                time.sleep(random.uniform(1, 2))
            
            driver.set_page_load_timeout(25)
            driver.get(page_url)
            time.sleep(random.uniform(MIN_DELAY_AFTER_LOAD, MAX_DELAY_AFTER_LOAD))
            
            # Ждем загрузки страницы
            try:
                wait = WebDriverWait(driver, 15)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except TimeoutException:
                logger.warning(f"[WARNING] Таймаут при ожидании загрузки страницы {page_url}")
            
            # Проверяем Cloudflare
            page_source = safe_get_page_source(driver)
            if not page_source:
                # Краш вкладки - пробрасываем ошибку
                raise Exception("Tab crashed while getting page_source")
            
            page_source_lower = page_source.lower()
            max_wait = 30
            wait_time = 0
            
            while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or 
                   "just a moment" in page_source_lower) and wait_time < max_wait:
                logger.info(f"Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
                time.sleep(3)
                driver.refresh()
                time.sleep(2)
                page_source = safe_get_page_source(driver)
                if not page_source:
                    raise Exception("Tab crashed during Cloudflare wait")
                page_source_lower = page_source.lower()
                wait_time += 5
            
            if wait_time >= max_wait:
                return None, False
            
            soup = BeautifulSoup(page_source, 'html.parser')
            return soup, True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Проверяем, является ли ошибка связанной с крашем вкладки
            if is_tab_crashed_error(e):
                logger.error(f"[TAB CRASH] Обнаружен краш вкладки при перезагрузке страницы (попытка {attempt + 1}): {e}")
                # Пробрасываем ошибку, чтобы вызвавший код мог пересоздать драйвер
                raise e
            
            # Проверяем, является ли ошибка связанной с прокси
            if is_proxy_error(e):
                logger.warning(f"[WARNING] Прокси отказал в соединении при перезагрузке страницы (попытка {attempt + 1})")
                return None, False
            
            logger.warning(f"[WARNING] Ошибка при перезагрузке страницы (попытка {attempt + 1}): {e}")
            if attempt < max_retries:
                continue
            else:
                # Последняя попытка не удалась
                return None, False
    
    return None, False


def get_cookies_from_selenium(driver: webdriver.Remote) -> Dict[str, str]:
    """Получает cookies из Selenium драйвера"""
    cookies = {}
    for cookie in driver.get_cookies():
        cookies[cookie['name']] = cookie['value']
    return cookies


def parse_page_with_cloudscraper(
    page_url: str,
    cookies: Dict[str, str],
    proxy: Optional[Dict] = None
) -> Tuple[Optional[BeautifulSoup], bool]:
    """
    Парсит страницу через cloudscraper с cookies (быстро)
    
    Returns:
        (soup, success) - BeautifulSoup объект и флаг успеха
    """
    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            },
            delay=15
        )
        
        # Устанавливаем cookies
        scraper.cookies.update(cookies)
        
        # Настраиваем прокси если есть
        proxies = None
        if proxy:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            if protocol in ['http', 'https']:
                proxy_url = f"{protocol}://{ip}:{port}"
                proxies = {'http': proxy_url, 'https': proxy_url}
            elif protocol in ['socks4', 'socks5']:
                proxy_url = f"socks5h://{ip}:{port}" if protocol == 'socks5' else f"socks4://{ip}:{port}"
                proxies = {'http': proxy_url, 'https': proxy_url}
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://trast-zapchast.ru/shop/',
            'Origin': 'https://trast-zapchast.ru'
        }
        
        response = scraper.get(page_url, headers=headers, proxies=proxies, timeout=30)
        
        if response.status_code in [200, 301, 302, 303, 307, 308]:
            # Проверяем что это не Cloudflare challenge
            if 'cloudflare' in response.text.lower() or 'checking your browser' in response.text.lower():
                return None, False
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup, True
        
        return None, False
        
    except Exception as e:
        logger.debug(f"Ошибка при парсинге через cloudscraper: {e}")
        return None, False


def parse_page_with_selenium(
    driver: webdriver.Remote,
    page_url: str
) -> Tuple[Optional[BeautifulSoup], bool]:
    """
    Парсит страницу через Selenium (fallback)
    
    Returns:
        (soup, success) - BeautifulSoup объект и флаг успеха
    """
    try:
        driver.set_page_load_timeout(25)
        driver.get(page_url)
        time.sleep(random.uniform(MIN_DELAY_AFTER_LOAD, MAX_DELAY_AFTER_LOAD))
        
        # Проверяем Cloudflare - используем безопасное получение page_source
        page_source = safe_get_page_source(driver)
        if not page_source:
            # Краш вкладки
            logger.error("[TAB CRASH] Краш вкладки при получении page_source после загрузки")
            return None, False
        
        page_source_lower = page_source.lower()
        max_wait = 30
        wait_time = 0
        
        while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or 
               "just a moment" in page_source_lower) and wait_time < max_wait:
            logger.info(f"Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
            time.sleep(3)
            driver.refresh()
            time.sleep(2)
            page_source = safe_get_page_source(driver)
            if not page_source:
                # Краш вкладки во время ожидания Cloudflare
                logger.error("[TAB CRASH] Краш вкладки во время ожидания Cloudflare")
                return None, False
            page_source_lower = page_source.lower()
            wait_time += 5
        
        if wait_time >= max_wait:
            return None, False
        
        soup = BeautifulSoup(page_source, 'html.parser')
        return soup, True
        
    except Exception as e:
        # Проверяем тип ошибки
        if is_tab_crashed_error(e):
            logger.error(f"[TAB CRASH] Краш вкладки при парсинге через Selenium: {e}")
            # Пробрасываем, чтобы вызвавший код мог пересоздать драйвер
            raise e
        elif is_proxy_error(e):
            logger.warning(f"[PROXY ERROR] Ошибка прокси при парсинге через Selenium: {e}")
        else:
            logger.debug(f"Ошибка при парсинге через Selenium: {e}")
        return None, False


def parse_all_pages(
    proxy_manager: ProxyManager,
    total_pages: int
) -> Tuple[int, Dict]:
    """
    Парсит все страницы последовательно
    
    Returns:
        (total_products, metrics) - количество товаров и метрики
    """
    total_products = 0
    empty_pages_count = 0
    pages_checked = 0
    proxy_switches = 0
    cloudflare_blocks = 0
    
    # Получаем первый рабочий прокси
    working_proxies = proxy_manager.get_working_proxies(
        min_count=MIN_WORKING_PROXIES,
        max_to_check=MAX_PROXIES_TO_CHECK
    )
    
    if not working_proxies:
        logger.error("Не удалось найти рабочие прокси!")
        return 0, {"pages_checked": 0, "proxy_switches": 0, "cloudflare_blocks": 0}
    
    logger.info(f"Найдено {len(working_proxies)} рабочих прокси, начинаем парсинг")
    
    # Получаем cookies через Selenium (один раз)
    # Используем первый прокси из списка для получения cookies
    current_proxy = working_proxies[0] if working_proxies else None
    if not current_proxy:
        logger.error("Нет рабочих прокси для получения cookies!")
        return 0, {"pages_checked": 0, "proxy_switches": 0, "cloudflare_blocks": 0}
    
    logger.info(f"Получаем cookies через прокси {current_proxy['ip']}:{current_proxy['port']}...")
    
    driver = None
    cookies = {}
    
    try:
        protocol = current_proxy.get('protocol', 'http').lower()
        use_chrome = protocol in ['http', 'https']
        
        driver = create_driver(current_proxy, use_chrome=use_chrome)
        if driver:
            driver.set_page_load_timeout(25)
            driver.get(TARGET_URL)
            time.sleep(5)
            
            # Ждем Cloudflare - используем безопасное получение page_source
            page_source = safe_get_page_source(driver)
            if not page_source:
                logger.error("[TAB CRASH] Краш вкладки при получении cookies")
            else:
                page_source_lower = page_source.lower()
                max_wait = 30
                wait_time = 0
                
                while page_source and ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or 
                       "just a moment" in page_source_lower) and wait_time < max_wait:
                    logger.info(f"Cloudflare проверка при получении cookies... ждем {wait_time}/{max_wait} сек")
                    time.sleep(3)
                    driver.refresh()
                    time.sleep(2)
                    page_source = safe_get_page_source(driver)
                    if not page_source:
                        logger.error("[TAB CRASH] Краш вкладки во время ожидания Cloudflare при получении cookies")
                        break
                    page_source_lower = page_source.lower()
                    wait_time += 5
                
                if page_source and wait_time < max_wait:
                    try:
                        cookies = get_cookies_from_selenium(driver)
                        logger.info(f"Получены cookies: {len(cookies)} штук")
                    except Exception as cookie_error:
                        if is_tab_crashed_error(cookie_error):
                            logger.error(f"[TAB CRASH] Краш вкладки при получении cookies: {cookie_error}")
                        else:
                            logger.warning(f"Ошибка при получении cookies: {cookie_error}")
                else:
                    logger.warning("Не удалось получить cookies из-за Cloudflare или краша вкладки")
    except Exception as e:
        if is_tab_crashed_error(e):
            logger.error(f"[TAB CRASH] Краш вкладки при получении cookies: {e}")
        elif is_proxy_error(e):
            logger.warning(f"[PROXY ERROR] Ошибка прокси при получении cookies: {e}")
        else:
            logger.error(f"Ошибка при получении cookies: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    # Буфер для товаров
    products_buffer = []
    BUFFER_SIZE = 50
    
    # Основной цикл парсинга
    current_page = 1
    current_proxy = proxy_manager.get_next_proxy()  # Получаем первый прокси через менеджер
    if not current_proxy:
        current_proxy = working_proxies[0]  # Fallback на первый из списка
    driver = None  # Инициализируем драйвер
    
    while current_page <= total_pages:
        try:
            page_url = f"{TARGET_URL}?_paged={current_page}"
            logger.info(f"Парсинг страницы {current_page}/{total_pages}...")
            
            # Пробуем через cloudscraper (быстро)
            soup = None
            success = False
            
            if cookies:
                soup, success = parse_page_with_cloudscraper(page_url, cookies, current_proxy)
            
            # Fallback на Selenium
            if not success or not soup:
                logger.info(f"Используем Selenium для страницы {current_page}...")
                if not driver:
                    protocol = current_proxy.get('protocol', 'http').lower()
                    use_chrome = protocol in ['http', 'https']
                    driver = create_driver(current_proxy, use_chrome=use_chrome)
                
                if driver:
                    try:
                        soup, success = parse_page_with_selenium(driver, page_url)
                        if success:
                            # Обновляем cookies
                            try:
                                cookies = get_cookies_from_selenium(driver)
                            except Exception as cookie_error:
                                if is_tab_crashed_error(cookie_error):
                                    logger.error(f"[TAB CRASH] Краш вкладки при обновлении cookies: {cookie_error}")
                                    # Пересоздаем драйвер
                                    try:
                                        driver.quit()
                                    except:
                                        pass
                                    driver = None
                                    success = False
                                else:
                                    logger.warning(f"Ошибка при обновлении cookies: {cookie_error}")
                    except Exception as selenium_error:
                        if is_tab_crashed_error(selenium_error):
                            logger.error(f"[TAB CRASH] Краш вкладки при парсинге через Selenium, пересоздаем драйвер...")
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = None
                            success = False
                        elif is_proxy_error(selenium_error):
                            logger.warning(f"[PROXY ERROR] Ошибка прокси при парсинге: {selenium_error}")
                            success = False
                        else:
                            logger.warning(f"Ошибка при парсинге через Selenium: {selenium_error}")
                            success = False
            
            if not success or not soup:
                logger.warning(f"Не удалось загрузить страницу {current_page}, пробуем новый прокси...")
                proxy_switches += 1
                current_proxy = proxy_manager.get_next_proxy()
                if not current_proxy:
                    # Если прокси закончились, получаем новые
                    logger.warning("Рабочие прокси закончились, ищем новые...")
                    new_proxies = proxy_manager.get_working_proxies(min_count=1, max_to_check=20)
                    if new_proxies:
                        working_proxies.extend(new_proxies)
                        current_proxy = working_proxies[0]
                    else:
                        logger.error("Не удалось найти новые рабочие прокси!")
                        break
                
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                driver = None
                cookies = {}  # Сбрасываем cookies
                continue
            
            # Проверяем блокировку
            # Для cloudscraper используем HTML из soup, для Selenium - из driver
            if driver:
                page_source = safe_get_page_source(driver)
                if not page_source:
                    # Краш вкладки при получении page_source
                    logger.error(f"[TAB CRASH] Краш вкладки при получении page_source для страницы {current_page}, пересоздаем драйвер...")
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                    # Пробуем новый прокси
                    proxy_switches += 1
                    current_proxy = proxy_manager.get_next_proxy()
                    if not current_proxy:
                        new_proxies = proxy_manager.get_working_proxies(min_count=1, max_to_check=20)
                        if new_proxies:
                            working_proxies.extend(new_proxies)
                            current_proxy = working_proxies[0]
                        else:
                            logger.error("Не удалось найти новые рабочие прокси!")
                            break
                    cookies = {}
                    continue
            else:
                # Если использовали cloudscraper, получаем HTML из soup
                page_source = str(soup) if soup else ""
            
            if not page_source:
                logger.warning(f"Не удалось получить содержимое страницы {current_page}")
                current_page += 1
                continue
            
            block_check = is_page_blocked(soup, page_source)
            
            if block_check["blocked"]:
                logger.warning(f"Страница {current_page} заблокирована: {block_check['reason']}")
                cloudflare_blocks += 1
                proxy_switches += 1
                current_proxy = proxy_manager.get_next_proxy()
                if not current_proxy:
                    # Если прокси закончились, получаем новые
                    logger.warning("Рабочие прокси закончились, ищем новые...")
                    new_proxies = proxy_manager.get_working_proxies(min_count=1, max_to_check=20)
                    if new_proxies:
                        working_proxies.extend(new_proxies)
                        current_proxy = working_proxies[0]
                    else:
                        logger.error("Не удалось найти новые рабочие прокси!")
                        break
                
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                driver = None
                cookies = {}  # Сбрасываем cookies
                continue
            
            # Парсим товары
            products, products_in_stock, total_products_on_page = get_products_from_page_soup(soup)
            
            # Проверяем статус страницы
            page_status = is_page_empty(soup, page_source, products_in_stock, total_products_on_page)
            
            if page_status["status"] == "normal" and products:
                # Нормальная страница с товарами
                products_buffer.extend(products)
                total_products += len(products)
                empty_pages_count = 0
                
                logger.info(f"Страница {current_page}: добавлено {len(products)} товаров (всего: {total_products})")
                
                # Записываем буфер если заполнен
                if len(products_buffer) >= BUFFER_SIZE:
                    append_to_csv(TEMP_CSV_FILE, products_buffer)
                    products_buffer.clear()
                    
            elif page_status["status"] == "empty":
                # Пустая страница
                empty_pages_count += 1
                logger.warning(f"Страница {current_page}: пустая (пустых подряд: {empty_pages_count})")
                
                # Останавливаемся после 2 пустых страниц подряд
                if empty_pages_count >= MAX_EMPTY_PAGES:
                    logger.info(f"Найдено {MAX_EMPTY_PAGES} пустых страниц подряд. Останавливаем парсинг.")
                    break
                    
            elif page_status["status"] == "partial":
                # Частичная загрузка - пробуем перезагрузить
                logger.warning(f"Страница {current_page}: частичная загрузка, пробуем еще раз...")
                if driver:
                    try:
                        soup, success = reload_page_if_needed(driver, page_url, max_retries=1)
                        if success and soup:
                            products, products_in_stock, total_products_on_page = get_products_from_page_soup(soup)
                            if products:
                                products_buffer.extend(products)
                                total_products += len(products)
                                empty_pages_count = 0
                                logger.info(f"Страница {current_page}: после перезагрузки добавлено {len(products)} товаров")
                    except Exception as reload_error:
                        if is_tab_crashed_error(reload_error):
                            logger.error(f"[TAB CRASH] Краш вкладки при перезагрузке частичной страницы {current_page}, пересоздаем драйвер...")
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = None
                            # Пробуем новый прокси
                            proxy_switches += 1
                            current_proxy = proxy_manager.get_next_proxy()
                            if not current_proxy:
                                new_proxies = proxy_manager.get_working_proxies(min_count=1, max_to_check=20)
                                if new_proxies:
                                    working_proxies.extend(new_proxies)
                                    current_proxy = working_proxies[0]
                                else:
                                    logger.error("Не удалось найти новые рабочие прокси!")
                                    break
                            cookies = {}
                            continue
                        else:
                            logger.warning(f"Ошибка при перезагрузке частичной страницы: {reload_error}")
            
            pages_checked += 1
            current_page += 1
            
            # Задержка между страницами
            time.sleep(random.uniform(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES))
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Проверяем на краш вкладки - это критическая ошибка, требующая пересоздания драйвера
            if is_tab_crashed_error(e):
                logger.error(f"[TAB CRASH] Обнаружен краш вкладки на странице {current_page}, пересоздаем драйвер...")
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                # Получаем новый прокси и пересоздаем драйвер
                proxy_switches += 1
                current_proxy = proxy_manager.get_next_proxy()
                if not current_proxy:
                    new_proxies = proxy_manager.get_working_proxies(min_count=1, max_to_check=20)
                    if new_proxies:
                        working_proxies.extend(new_proxies)
                        current_proxy = working_proxies[0]
                    else:
                        logger.error("Не удалось найти новые рабочие прокси!")
                        break
                cookies = {}
                # Не увеличиваем current_page - попробуем еще раз с новым драйвером
                continue
            
            # Проверяем на ошибку прокси
            elif is_proxy_error(e):
                logger.warning(f"[PROXY ERROR] Ошибка прокси на странице {current_page}: {e}")
                # Пробуем перезагрузить страницу с тем же прокси (один раз)
                if driver:
                    try:
                        soup, success = reload_page_if_needed(driver, page_url, max_retries=1)
                        if success and soup:
                            products, products_in_stock, total_products_on_page = get_products_from_page_soup(soup)
                            if products:
                                products_buffer.extend(products)
                                total_products += len(products)
                                pages_checked += 1
                                current_page += 1
                                time.sleep(random.uniform(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES))
                                continue
                    except Exception as retry_error:
                        if is_tab_crashed_error(retry_error):
                            logger.error(f"[TAB CRASH] Краш вкладки при retry после ошибки прокси")
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = None
                
                # Если retry не помог - получаем новый прокси
                logger.info(f"Получаем новый прокси после ошибки прокси...")
                proxy_switches += 1
                current_proxy = proxy_manager.get_next_proxy()
                if not current_proxy:
                    new_proxies = proxy_manager.get_working_proxies(min_count=1, max_to_check=20)
                    if new_proxies:
                        working_proxies.extend(new_proxies)
                        current_proxy = working_proxies[0]
                    else:
                        logger.error("Не удалось найти новые рабочие прокси!")
                        break
                
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                driver = None
                cookies = {}
                # Не увеличиваем current_page - попробуем еще раз с новым прокси
                continue
            else:
                logger.error(f"Ошибка при парсинге страницы {current_page}: {e}")
                logger.debug(traceback.format_exc())
                current_page += 1
                continue
    
    # Записываем оставшиеся товары
    if products_buffer:
        append_to_csv(TEMP_CSV_FILE, products_buffer)
        products_buffer.clear()
    
    # Закрываем драйвер
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    return total_products, {
        "pages_checked": pages_checked,
        "proxy_switches": proxy_switches,
        "cloudflare_blocks": cloudflare_blocks
    }


def main():
    """Главная функция"""
    logger.info("=" * 80)
    logger.info("=== TRAST PARSER STARTED ===")
    logger.info(f"Target URL: {TARGET_URL}")
    logger.info(f"Start time: {datetime.now()}")
    logger.info("=" * 80)
    
    start_time = datetime.now()
    
    try:
        # Создаем временный CSV файл
        create_new_csv(TEMP_CSV_FILE)
        logger.info("Создан временный CSV файл для записи данных")
    except Exception as e:
        logger.error(f"Ошибка при создании временных файлов: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
    
    # Инициализируем прокси менеджер
    logger.info("Инициализация ProxyManager...")
    try:
        proxy_manager = ProxyManager(country_filter=PREFERRED_COUNTRIES)
        logger.info("ProxyManager инициализирован")
    except Exception as e:
        logger.error(f"Ошибка при инициализации ProxyManager: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
    
    # Обновляем список прокси
    logger.info("Обновляем список прокси...")
    try:
        if not proxy_manager.download_proxies(force_update=True):
            logger.warning("Не удалось обновить список прокси, используем кэшированный")
    except Exception as e:
        logger.warning(f"Ошибка при обновлении прокси: {e}")
    
    # Получаем количество страниц
    logger.info("Получаем количество страниц для парсинга...")
    total_pages = None
    
    working_proxies = proxy_manager.get_working_proxies(
        min_count=1,  # Нужен хотя бы один для получения количества страниц
        max_to_check=50
    )
    
    if not working_proxies:
        logger.error("Не удалось найти рабочие прокси для получения количества страниц!")
        sys.exit(1)
    
    driver = None
    try:
        proxy = working_proxies[0]
        protocol = proxy.get('protocol', 'http').lower()
        use_chrome = protocol in ['http', 'https']
        
        driver = create_driver(proxy, use_chrome=use_chrome)
        if driver:
            total_pages = get_pages_count_with_driver(driver)
            logger.info(f"Найдено {total_pages} страниц для парсинга")
    except Exception as e:
        logger.error(f"Ошибка при получении количества страниц: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    if not total_pages or total_pages <= 0:
        logger.error("Не удалось получить количество страниц")
        sys.exit(1)
    
    # Запускаем парсинг
    logger.info("=" * 80)
    logger.info("Начинаем парсинг страниц...")
    logger.info("=" * 80)
    
    try:
        total_products, metrics = parse_all_pages(proxy_manager, total_pages)
        logger.info(f"Парсинг завершен, собрано товаров: {total_products}")
    except Exception as e:
        logger.error(f"Критическая ошибка при парсинге: {e}")
        logger.error(traceback.format_exc())
        cleanup_temp_files()
        sys.exit(1)
    
    # Финализация
    duration = (datetime.now() - start_time).total_seconds()
    
    if total_products >= 100:
        logger.info(f"Собрано {total_products} товаров - успешно!")
        finalize_output_files()
        logger.info("Основные файлы обновлены успешно")
        status = 'done'
    else:
        logger.warning(f"Недостаточно данных: {total_products} товаров")
        cleanup_temp_files()
        status = 'insufficient_data'
    
    logger.info("=" * 80)
    logger.info(f"Парсинг завершен!")
    logger.info(f"Время выполнения: {round(duration, 2)} секунд")
    logger.info(f"Статус: {status}")
    logger.info(f"Товаров собрано: {total_products}")
    if metrics:
        logger.info(f"Метрики: страниц проверено: {metrics.get('pages_checked', 0)}, "
                   f"переключений прокси: {metrics.get('proxy_switches', 0)}, "
                   f"блокировок Cloudflare: {metrics.get('cloudflare_blocks', 0)}")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

