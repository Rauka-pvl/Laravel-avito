"""
Главный файл парсера trast-zapchast.ru
Однопоточный парсинг с улучшенным обходом Cloudflare
"""
import os
import sys
import time
import random
import traceback
import threading
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from loguru import logger
import cloudscraper

# Настройка логирования ДО импорта других модулей
# Удаляем дефолтный обработчик (id=0) чтобы избежать дублирования
try:
    logger.remove(0)  # Удаляем дефолтный обработчик stderr
except ValueError:
    pass  # Обработчик уже удален или не существует

from config import (
    TARGET_URL, MAX_EMPTY_PAGES, MIN_WORKING_PROXIES, MAX_PROXIES_TO_CHECK,
    PREFERRED_COUNTRIES, TEMP_CSV_FILE, OUTPUT_FILE, CSV_FILE,
    MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES,
    MIN_DELAY_AFTER_LOAD, MAX_DELAY_AFTER_LOAD, LOG_DIR, PARSING_THREADS,
    PROXY_SEARCH_TIMEOUT, PROXY_SEARCH_PROGRESS_LOG_INTERVAL,
    PROXY_LIST_WAIT_DELAY, PROXY_SEARCH_INITIAL_TIMEOUT,
    PAGE_STEP_FOR_THREADS, CSV_BUFFER_SAVE_SIZE, CSV_BUFFER_FULL_SIZE,
    ALLOWED_PROXY_PROTOCOLS
)

# Добавляем обработчики логирования после импорта config
LOG_FILE = os.path.join(LOG_DIR, f"trast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
# Добавляем BOM, чтобы браузеры корректно определяли кодировку (UTF-8 with signature)
logger.add(LOG_FILE, encoding='utf-8-sig', rotation='10 MB', retention='7 days')
# Настраиваем stderr для правильной кодировки UTF-8
if hasattr(sys.stderr, 'encoding') and sys.stderr.encoding != 'utf-8':
    try:
        import io
        # Пытаемся переопределить stderr только если это возможно
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass  # Если не удалось, продолжаем с текущим stderr
logger.add(sys.stderr, level='INFO')
from proxy_manager import ProxyManager
from utils import (
    create_driver, get_pages_count_with_driver, get_products_from_page_soup,
    is_page_blocked, is_page_empty, create_new_csv, append_to_csv,
    finalize_output_files, cleanup_temp_files, create_backup,
    safe_get_page_source, is_tab_crashed_error, PaginationNotDetectedError,
    wait_for_cloudflare
)

# Импорт Telegram уведомлений и БД
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from notification.main import TelegramNotifier
except ImportError:
    # Если модуль не найден, создаем заглушку
    class TelegramNotifier:
        @classmethod
        def notify(cls, text: str):
            logger.info(f"Telegram notification (not available): {text}")

try:
    from bz_telebot.database_manager import set_script_start, set_script_end
except ImportError:
    # Если модуль не найден, создаем заглушки
    def set_script_start(script_name: str):
        logger.debug(f"set_script_start({script_name}) - database module not available")
    
    def set_script_end(script_name: str, status: str = "done"):
        logger.debug(f"set_script_end({script_name}, {status}) - database module not available")


def is_proxy_error(error) -> bool:
    """Проверяет, является ли ошибка связанной с прокси"""
    error_msg = str(error).lower()
    return (
        "proxyconnectfailure" in error_msg or
        ("proxy" in error_msg and ("refusing" in error_msg or "connection" in error_msg or "failed" in error_msg)) or
        ("neterror" in error_msg and "proxy" in error_msg)
    )


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
                logger.info(f"[RETRY] Reloading page {page_url} (attempt {attempt + 1}/{max_retries + 1})...")
                time.sleep(random.uniform(1, 2))
            
            driver.set_page_load_timeout(25)
            driver.get(page_url)
            time.sleep(random.uniform(MIN_DELAY_AFTER_LOAD, MAX_DELAY_AFTER_LOAD))
            
            # Ждем загрузки страницы
            try:
                wait = WebDriverWait(driver, 15)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except TimeoutException:
                logger.warning(f"[WARNING] Timeout waiting for page load {page_url}")
            
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
                logger.info(f"Cloudflare check... waiting {wait_time}/{max_wait} sec")
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
                logger.error(f"[TAB CRASH] Tab crash detected during page reload (attempt {attempt + 1}): {e}")
                # Пробрасываем ошибку, чтобы вызвавший код мог пересоздать драйвер
                raise e
            
            # Проверяем, является ли ошибка связанной с прокси
            if is_proxy_error(e):
                logger.warning(f"[WARNING] Proxy connection refused during page reload (attempt {attempt + 1})")
                return None, False
            
            logger.warning(f"[WARNING] Error reloading page (attempt {attempt + 1}): {e}")
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
        logger.debug(f"Error parsing with cloudscraper: {e}")
        return None, False


def parse_page_with_selenium(
    driver: webdriver.Remote,
    page_url: str,
    wait_for_content: bool = True
) -> Tuple[Optional[BeautifulSoup], bool]:
    """
    Парсит страницу через Selenium (fallback)
    
    Args:
        driver: WebDriver объект
        page_url: URL страницы для парсинга
        wait_for_content: Ждать полной загрузки контента (скролл и ожидание)
    
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
            logger.error("[TAB CRASH] Tab crash while getting page_source after load")
            return None, False
        
        page_source_lower = page_source.lower()
        max_wait = 30
        wait_time = 0
        
        while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or 
               "just a moment" in page_source_lower) and wait_time < max_wait:
            logger.info(f"Cloudflare check... waiting {wait_time}/{max_wait} sec")
            time.sleep(3)
            driver.refresh()
            time.sleep(2)
            page_source = safe_get_page_source(driver)
            if not page_source:
                # Краш вкладки во время ожидания Cloudflare
                logger.error("[TAB CRASH] Tab crash during Cloudflare wait")
                return None, False
            page_source_lower = page_source.lower()
            wait_time += 5
        
        if wait_time >= max_wait:
            return None, False
        
        # Если нужно ждать полной загрузки контента (как при валидации прокси)
        if wait_for_content:
            # Скроллим для активации динамического контента (как в get_pages_count_with_driver)
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                time.sleep(random.uniform(1, 2))
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(random.uniform(1, 2))
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2, 3))
                
                # Дополнительное ожидание для полной загрузки динамического контента
                time.sleep(5)  # Даем время на загрузку товаров через AJAX
                
                # Обновляем page_source после скролла
                page_source = safe_get_page_source(driver)
                if not page_source:
                    logger.error("[TAB CRASH] Tab crash after scroll")
                    return None, False
            except Exception as scroll_error:
                logger.warning(f"Error during scroll: {scroll_error}")
                # Продолжаем с текущим page_source
        
        soup = BeautifulSoup(page_source, 'html.parser')
        return soup, True
        
    except Exception as e:
        # Проверяем тип ошибки
        if is_tab_crashed_error(e):
            logger.error(f"[TAB CRASH] Tab crash while parsing with Selenium: {e}")
            # Пробрасываем, чтобы вызвавший код мог пересоздать драйвер
            raise e
        elif is_proxy_error(e):
            logger.warning(f"[PROXY ERROR] Proxy error while parsing with Selenium: {e}")
        else:
            logger.debug(f"Error parsing with Selenium: {e}")
        return None, False


def prioritize_proxies(proxies: List[Dict]) -> List[Dict]:
    """Сортирует прокси: HTTPS + страны из PREFERRED_COUNTRIES в приоритете"""
    def score(proxy: Dict) -> float:
        protocol = (proxy.get('protocol') or '').lower()
        country = (proxy.get('country') or '').upper()
        value = 0.0
        if country in PREFERRED_COUNTRIES:
            value += 2.0
        if protocol == 'https':
            value += 1.5
        elif protocol == 'http':
            value += 1.0
        elif protocol.startswith('socks'):
            value += 0.5
        return value
    
    return sorted(
        proxies,
        key=lambda proxy: (score(proxy), random.random()),
        reverse=True
    )


def log_proxy_health_summary(proxy_manager: ProxyManager, stage: str, thread_name: str = "MainThread"):
    summary = proxy_manager.get_health_summary()
    if not summary:
        logger.info(f"[{thread_name}] Proxy health summary ({stage}): no tracked proxies yet")
        return
    
    logger.info(f"[{thread_name}] Proxy health summary ({stage}): "
                f"{summary.get('cooldown_count', 0)} in cooldown / "
                f"{summary.get('tracked_proxies', 0)} tracked")
    
    top_failures = summary.get('top_failure_reasons') or []
    if top_failures:
        fail_str = ", ".join(f"{reason}: {count}" for reason, count in top_failures)
        logger.info(f"[{thread_name}]   Top failure reasons: {fail_str}")
    
    top_sources = summary.get('source_distribution') or []
    if top_sources:
        source_str = ", ".join(f"{source or 'unknown'}: {count}" for source, count in top_sources)
        logger.info(f"[{thread_name}]   Source distribution: {source_str}")


def download_proxies_thread(
    proxy_manager: ProxyManager,
    proxies_list: List[Dict],
    proxies_lock: threading.Lock,
    stop_event: threading.Event
):
    """Поток для скачивания прокси из источников
    
    Args:
        proxy_manager: Менеджер прокси
        proxies_list: Общий список прокси для проверки (thread-safe)
        proxies_lock: Lock для доступа к proxies_list
        stop_event: Event для остановки потока
    """
    thread_name = "DownloadThread"
    logger.info(f"[{thread_name}] Proxy download thread started")
    
    try:
        # Первоначальная загрузка прокси
        logger.info(f"[{thread_name}] Starting proxy download from all sources...")
        if proxy_manager.download_proxies(force_update=True):
            # Загружаем скачанные прокси
            downloaded_proxies = proxy_manager._load_proxies()
            if downloaded_proxies:
                with proxies_lock:
                    proxies_list.clear()
                    proxies_list.extend(prioritize_proxies(downloaded_proxies))
                    logger.info(f"[{thread_name}] Loaded {len(proxies_list)} proxies into shared list")
                proxy_manager.ensure_warm_proxy_pool(MIN_WORKING_PROXIES)
            else:
                logger.warning(f"[{thread_name}] Failed to load proxies from file")
            proxy_manager.ensure_warm_proxy_pool(MIN_WORKING_PROXIES)
        else:
            logger.warning(f"[{thread_name}] Failed to download proxies")
        
        # Периодическое обновление (каждые 30 минут)
        update_interval = 1800  # 30 минут
        last_update = time.time()
        
        while not stop_event.is_set():
            time.sleep(60)  # Проверяем каждую минуту
            
            # Проверяем, нужно ли обновить прокси
            if time.time() - last_update >= update_interval:
                logger.info(f"[{thread_name}] Periodic proxy list update...")
                try:
                    if proxy_manager.download_proxies(force_update=True):
                        downloaded_proxies = proxy_manager._load_proxies()
                        if downloaded_proxies:
                            with proxies_lock:
                                old_count = len(proxies_list)
                                proxies_list.clear()
                                proxies_list.extend(prioritize_proxies(downloaded_proxies))
                                logger.info(f"[{thread_name}] Proxy list updated: {old_count} -> {len(proxies_list)}")
                            proxy_manager.ensure_warm_proxy_pool(MIN_WORKING_PROXIES)
                        last_update = time.time()
                except Exception as e:
                    logger.warning(f"[{thread_name}] Error updating proxies: {e}")
    
    except Exception as e:
        logger.error(f"[{thread_name}] Critical error in proxy download thread: {e}")
        logger.debug(traceback.format_exc())
    
    logger.info(f"[{thread_name}] Proxy download thread finished")


def find_new_working_proxy(
    proxy_manager: ProxyManager,
    proxies_list: List[Dict],
    proxies_lock: Optional[threading.Lock],  # Теперь опциональный, для совместимости
    proxy_index: int,
    thread_name: str,
    max_timeout: int = None,
    context: str = ""
) -> Tuple[Optional[Dict], Optional[webdriver.Remote], int, int]:
    """
    Ищет новый рабочий прокси и создает драйвер.
    
    Args:
        proxy_manager: Менеджер прокси
        proxies_list: Список прокси для проверки
        proxies_lock: Lock для thread-safe доступа к списку
        proxy_index: Текущий индекс в списке прокси (будет изменяться)
        thread_name: Имя потока для логирования
        max_timeout: Максимальное время поиска в секундах (по умолчанию из config)
        context: Контекст для логирования (например, "after blocking")
        
    Returns:
        tuple: (proxy: Optional[Dict], driver: Optional[webdriver.Remote], proxies_checked: int, new_index: int)
        - proxy: Найденный рабочий прокси или None
        - driver: Созданный драйвер или None
        - proxies_checked: Количество проверенных прокси
        - new_index: Новый индекс для продолжения поиска
    """
    if max_timeout is None:
        max_timeout = PROXY_SEARCH_TIMEOUT
    
    found_new_proxy = False
    proxy_search_start = time.time()
    proxies_checked = 0
    current_proxy_index = proxy_index
    failures_since_refresh = 0
    refresh_threshold = 15
    cooldown_skips = 0
    consecutive_page_block_failures = 0
    page_block_threshold = 5
    
    page_in_context = None
    if context:
        match = re.search(r'page (\d+)', context)
        if match:
            try:
                page_in_context = int(match.group(1))
            except ValueError:
                page_in_context = None
    
    context_suffix = f" {context}" if context else ""
    logger.info(f"[{thread_name}] Starting proxy search{context_suffix} (timeout: {max_timeout}s, starting index: {current_proxy_index})")
    
    def refresh_proxy_pool(reason: str) -> bool:
        logger.info(f"[{thread_name}] Forcing proxy refresh ({reason})...")
        try:
            if proxy_manager.download_proxies(force_update=True):
                updated_proxies = proxy_manager._load_proxies()
                if updated_proxies:
                    if proxies_lock:
                        with proxies_lock:
                            proxies_list.clear()
                            proxies_list.extend(prioritize_proxies(updated_proxies))
                    else:
                        proxies_list.clear()
                        proxies_list.extend(prioritize_proxies(updated_proxies))
                    logger.info(f"[{thread_name}] Proxy pool refreshed with {len(updated_proxies)} entries")
                    proxy_manager.ensure_warm_proxy_pool(MIN_WORKING_PROXIES)
                    return True
        except Exception as refresh_error:
            logger.warning(f"[{thread_name}] Failed to refresh proxies: {refresh_error}")
        return False
    
    while not found_new_proxy:
        elapsed_time = time.time() - proxy_search_start
        if elapsed_time >= max_timeout:
            logger.error(f"[{thread_name}] New proxy search timeout exceeded ({max_timeout}s, checked {proxies_checked} proxies), terminating thread")
            break
        
        # Логируем прогресс каждые N секунд
        if int(elapsed_time) % PROXY_SEARCH_PROGRESS_LOG_INTERVAL == 0 and int(elapsed_time) > 0:
            logger.info(f"[{thread_name}] Proxy search in progress: {int(elapsed_time)}s elapsed, {proxies_checked} proxies checked")
        
        proxy = None
        list_size = 0
        # Получаем прокси из списка (все типы прокси поддерживаются через Firefox)
        while proxy is None:
            if proxies_lock:
                with proxies_lock:
                    list_size = len(proxies_list)
                    if list_size == 0:
                        logger.debug(f"[{thread_name}] Proxy list is empty, waiting for update...")
                        break
                    if current_proxy_index >= list_size:
                        rotation_offset = random.randint(0, list_size - 1) if list_size > 1 else 0
                        current_proxy_index = rotation_offset
                    proxy_candidate = proxies_list[current_proxy_index]
                    current_proxy_index += 1
            else:
                list_size = len(proxies_list)
                if list_size == 0:
                    logger.debug(f"[{thread_name}] Proxy list is empty, waiting for update...")
                    time.sleep(PROXY_LIST_WAIT_DELAY)
                    break
                if current_proxy_index >= list_size:
                    rotation_offset = random.randint(0, list_size - 1) if list_size > 1 else 0
                    current_proxy_index = rotation_offset
                proxy_candidate = proxies_list[current_proxy_index]
                current_proxy_index += 1
            
            if not proxy_candidate:
                continue
            
            if proxy_manager.is_proxy_in_cooldown(proxy_candidate):
                cooldown_skips += 1
                logger.debug(f"[{thread_name}] Skipping proxy {proxy_candidate.get('ip')}:{proxy_candidate.get('port')} due to cooldown")
                if list_size > 0 and cooldown_skips >= list_size:
                    logger.info(f"[{thread_name}] All proxies are cooling down, waiting {PROXY_LIST_WAIT_DELAY}s for refresh...")
                    cooldown_skips = 0
                    time.sleep(PROXY_LIST_WAIT_DELAY)
                continue
            
            if page_in_context and proxy_manager.should_skip_proxy_for_page(proxy_candidate, page_in_context):
                logger.debug(f"[{thread_name}] Skipping proxy {proxy_candidate.get('ip')}:{proxy_candidate.get('port')} (recently blocked page {page_in_context})")
                continue
            
            proxy = proxy_candidate
            cooldown_skips = 0
        
        if proxy is None:
            time.sleep(PROXY_LIST_WAIT_DELAY)
            continue
        
        proxies_checked += 1
        proxy_key = f"{proxy['ip']}:{proxy['port']}"
        protocol = proxy.get('protocol', 'http').upper()
        
        basic_ok, basic_info = proxy_manager.validate_proxy_basic(proxy)
        if not basic_ok:
            reason = (basic_info or {}).get('reason', 'basic_check_failed')
            logger.debug(f"[{thread_name}] Proxy {proxy_key} skipped after basic check: {reason}")
            failures_since_refresh += 1
            continue
        
        logger.info(f"[{thread_name}] Checking new proxy {proxy_key} ({protocol}){context_suffix} [{proxies_checked} checked, {int(elapsed_time)}s elapsed]...")
        
        try:
            trast_ok, trast_info = proxy_manager.validate_proxy_for_trast(proxy, page_context=page_in_context)
            if trast_ok and 'total_pages' in trast_info and trast_info['total_pages'] > 0:
                current_proxy = proxy.copy()
                current_proxy.update(trast_info)
                logger.debug(f"[{thread_name}] Creating driver with new proxy {proxy_key}...")
                driver = create_driver(current_proxy)
                if driver:
                    found_new_proxy = True
                    logger.info(f"[{thread_name}] Found new working proxy {proxy_key} (total_pages={trast_info['total_pages']}) after checking {proxies_checked} proxies in {int(elapsed_time)}s{context_suffix}")
                    failures_since_refresh = 0
                    consecutive_page_block_failures = 0
                    return current_proxy, driver, proxies_checked, current_proxy_index
                else:
                    logger.warning(f"[{thread_name}] Failed to create driver with proxy {proxy_key}")
                    failures_since_refresh += 1
            else:
                failure_reason = trast_info.get('reason', 'unknown')
                logger.debug(f"[{thread_name}] Proxy {proxy_key} validation failed: reason={failure_reason}, details={trast_info}")
                failures_since_refresh += 1
                if failure_reason == 'cloudflare_block' and page_in_context:
                    consecutive_page_block_failures += 1
                else:
                    consecutive_page_block_failures = 0
        except Exception as e:
            error_type = type(e).__name__
            logger.debug(f"[{thread_name}] Error checking proxy {proxy_key}: {error_type}: {str(e)[:100]}")
            failures_since_refresh += 1
            consecutive_page_block_failures = 0
            continue
        
        if page_in_context and consecutive_page_block_failures >= page_block_threshold:
            if refresh_proxy_pool(f"{consecutive_page_block_failures} cloudflare blocks on page {page_in_context}"):
                current_proxy_index = 0
                failures_since_refresh = 0
                consecutive_page_block_failures = 0
                continue
            consecutive_page_block_failures = 0
        
        if failures_since_refresh >= refresh_threshold:
            if refresh_proxy_pool(f"{failures_since_refresh} consecutive failures"):
                current_proxy_index = 0
                failures_since_refresh = 0
                continue
            failures_since_refresh = 0
            continue
    
    if not found_new_proxy:
        logger.error(f"[{thread_name}] Failed to find new working proxy after checking {proxies_checked} proxies in {int(time.time() - proxy_search_start)}s{context_suffix}")
    
    return None, None, proxies_checked, current_proxy_index


def recreate_driver_with_new_proxy(
    proxy_manager: ProxyManager,
    current_proxy: Optional[Dict],
    working_proxies_list: List[Dict],
    driver: Optional[webdriver.Remote],
    cookies: Dict,
    proxies_lock: Optional[threading.Lock] = None
) -> Tuple[Optional[webdriver.Remote], Optional[Dict], Dict]:
    """
    Пересоздает драйвер с новым прокси.
    
    Returns:
        (new_driver, new_proxy, new_cookies) - новый драйвер, прокси и пустые cookies
    """
    # Закрываем старый драйвер
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    # Получаем новый прокси
    new_proxy = proxy_manager.get_next_proxy()
    if not new_proxy:
        # Если прокси закончились, получаем новые
        logger.warning("[MainThread] Working proxies exhausted, searching for new ones...")
        new_proxies = proxy_manager.get_working_proxies(min_count=1, max_to_check=MAX_PROXIES_TO_CHECK)
        if new_proxies:
            if proxies_lock:
                with proxies_lock:
                    working_proxies_list.extend(new_proxies)
                    new_proxy = working_proxies_list[0] if working_proxies_list else None
            else:
                working_proxies_list.extend(new_proxies)
                new_proxy = working_proxies_list[0] if working_proxies_list else None
        else:
            logger.error("[MainThread] Failed to find new working proxies!")
            return None, None, {}
    
    # Создаем новый драйвер
    protocol = new_proxy.get('protocol', 'http').lower()
    logger.info(f"Recreating driver with new proxy {new_proxy['ip']}:{new_proxy['port']} ({protocol.upper()})...")
    new_driver = create_driver(new_proxy)
    
    if not new_driver:
        logger.warning(f"Failed to create driver with proxy {new_proxy['ip']}:{new_proxy['port']}")
        return None, new_proxy, {}
    
    # Сбрасываем cookies
    new_cookies = {}
    
    return new_driver, new_proxy, new_cookies


def worker_thread(
    thread_id: int,
    proxy_manager: ProxyManager,
    proxies_list: List[Dict],
    proxies_lock: threading.Lock,
    total_pages_shared: Dict,
    total_pages_lock: threading.Lock,
    csv_lock: threading.Lock
):
    """Worker функция для многопоточного парсинга страниц
    
    Args:
        thread_id: ID потока (0 = четные страницы, 1 = нечетные страницы)
        proxy_manager: Менеджер прокси
        proxies_list: Общий список прокси для проверки (thread-safe)
        proxies_lock: Lock для доступа к proxies_list
        total_pages_shared: Общий словарь для total_pages {'value': int} (thread-safe)
        total_pages_lock: Lock для доступа к total_pages_shared
        csv_lock: Lock для thread-safe записи в CSV
    """
    thread_name = f"Worker-{thread_id}"
    logger.info(f"[{thread_name}] === WORKER THREAD {thread_id} STARTED ===")
    
    # Локальные переменные для потока
    local_buffer = []
    BUFFER_SIZE = 50
    empty_pages_count = 0
    pages_parsed = 0
    products_collected = 0
    proxy_switches = 0
    cloudflare_blocks = 0
    
    driver = None
    current_proxy = None
    cookies = {}
    total_pages = None
    
    # ФАЗА 1: Поиск рабочего прокси
    logger.info(f"[{thread_name}] Phase 1: Searching for working proxy...")
    proxy_index = thread_id  # Начинаем с thread_id (0 или 1), затем +PAGE_STEP_FOR_THREADS
    max_search_time = PROXY_SEARCH_INITIAL_TIMEOUT  # Максимум времени на начальный поиск прокси
    search_start_time = time.time()
    last_list_size = 0
    consecutive_empty_checks = 0
    
    while True:
        # Проверяем таймаут - но не останавливаемся, продолжаем пытаться
        elapsed = time.time() - search_start_time
        if elapsed >= max_search_time:
            logger.warning(f"[{thread_name}] Proxy search timeout exceeded ({max_search_time}s), but continuing search...")
            # Сбрасываем таймер, продолжаем поиск
            search_start_time = time.time()
        
        # Проверяем, есть ли уже total_pages от другого потока
        with total_pages_lock:
            if total_pages_shared.get('value') and total_pages_shared['value'] > 0:
                total_pages = total_pages_shared['value']
                logger.info(f"[{thread_name}] Using total_pages={total_pages} from another thread")
                break
        
        # Получаем прокси из списка
        with proxies_lock:
            current_list_size = len(proxies_list)
            if proxy_index >= current_list_size:
                # Если список не обновился после нескольких проверок - возможно, прокси закончились
                if current_list_size == last_list_size:
                    consecutive_empty_checks += 1
                    if consecutive_empty_checks >= 6:  # 30 секунд ожидания
                        logger.warning(f"[{thread_name}] Proxy list not updating, possibly all proxies checked. Waiting for update...")
                        consecutive_empty_checks = 0
                else:
                    consecutive_empty_checks = 0
                    last_list_size = current_list_size
                
                logger.debug(f"[{thread_name}] Reached end of proxy list (index {proxy_index}, list size: {current_list_size}), waiting for update...")
                time.sleep(PROXY_LIST_WAIT_DELAY)
                continue
            
            consecutive_empty_checks = 0
            last_list_size = current_list_size
            proxy = proxies_list[proxy_index]
            proxy_index += PAGE_STEP_FOR_THREADS  # Следующий прокси для этого потока (четный/нечетный)
        
        proxy_key = f"{proxy['ip']}:{proxy['port']}"
        proxies_checked_count += 1
        elapsed = int(time.time() - search_start_time)
        logger.info(f"[{thread_name}] {'-'*60}")
        logger.info(f"[{thread_name}] [{proxies_checked_count}] Checking proxy {proxy_key} ({proxy.get('protocol', 'http').upper()})...")
        logger.info(f"[{thread_name}] Search progress: {elapsed}s elapsed, {proxies_checked_count} proxies checked")
        
        # Проверяем прокси
        try:
            logger.debug(f"[{thread_name}] Validating proxy {proxy_key} ({proxy.get('protocol', 'http').upper()})...")
            trast_ok, trast_info = proxy_manager.validate_proxy_for_trast(proxy)
            if trast_ok and 'total_pages' in trast_info and trast_info['total_pages'] > 0:
                # Найден рабочий прокси!
                current_proxy = proxy.copy()
                current_proxy.update(trast_info)
                total_pages = trast_info['total_pages']
                
                # Сохраняем total_pages в общий словарь
                with total_pages_lock:
                    if not total_pages_shared.get('value'):
                        total_pages_shared['value'] = total_pages
                        logger.info(f"[{thread_name}] Saved total_pages={total_pages} to shared dictionary")
                
                elapsed_search = int(time.time() - search_start_time)
                logger.info(f"[{thread_name}] {'='*60}")
                logger.info(f"[{thread_name}] WORKING PROXY FOUND!")
                logger.info(f"[{thread_name}] Proxy: {proxy_key} ({proxy.get('protocol', 'http').upper()})")
                logger.info(f"[{thread_name}] Total pages: {total_pages}")
                logger.info(f"[{thread_name}] Search time: {elapsed_search}s")
                logger.info(f"[{thread_name}] {'='*60}")
                logger.info(f"[{thread_name}] STARTING PARSING NOW with proxy {proxy_key}...")
                break
            else:
                reason = "validation failed"
                if not trast_ok:
                    reason = "not working"
                elif 'total_pages' not in trast_info:
                    reason = "no page count"
                elif trast_info.get('total_pages', 0) <= 0:
                    reason = f"invalid page count: {trast_info.get('total_pages')}"
                logger.warning(f"[{thread_name}] Proxy {proxy_key} not working ({reason}), continuing search...")
        except Exception as e:
            error_type = type(e).__name__
            logger.warning(f"[{thread_name}] Error checking proxy {proxy_key}: {error_type}: {str(e)[:150]}")
            continue
    
    if not total_pages or total_pages <= 0:
        logger.error(f"[{thread_name}] Failed to get total_pages, terminating thread")
        return
    
    # Проверяем, что current_proxy установлен
    if not current_proxy:
        logger.error(f"[{thread_name}] current_proxy not set, terminating thread")
        return
    
    # ФАЗА 2: Парсинг страниц
    logger.info(f"[{thread_name}] {'='*60}")
    logger.info(f"[{thread_name}] PHASE 2: STARTING PAGE PARSING")
    logger.info(f"[{thread_name}] Total pages to parse: {total_pages}")
    logger.info(f"[{thread_name}] Using proxy: {current_proxy['ip']}:{current_proxy['port']} ({current_proxy.get('protocol', 'http').upper()})")
    logger.info(f"[{thread_name}] {'='*60}")
    
    # Определяем какие страницы парсить: thread_id 0 = четные (2, 4, 6, ...), thread_id 1 = нечетные (1, 3, 5, ...)
    page_start = PAGE_STEP_FOR_THREADS - thread_id  # thread_id 0 -> страница 2 (четная), thread_id 1 -> страница 1 (нечетная)
    page_step = PAGE_STEP_FOR_THREADS  # Шаг для чередования
    current_page = page_start
    
    logger.info(f"[{thread_name}] Will parse pages: {page_start}, {page_start + page_step}, {page_start + page_step*2}, ... (step={page_step})")
    
    # Создаем драйвер для парсинга
    protocol = current_proxy.get('protocol', 'http').lower()
    logger.info(f"[{thread_name}] Creating driver for parsing...")
    driver = create_driver(current_proxy)
    
    if not driver:
        logger.error(f"[{thread_name}] Failed to create driver, terminating thread")
        return
    
    # Получаем cookies
    logger.info(f"[{thread_name}] Getting cookies via proxy {current_proxy['ip']}:{current_proxy['port']}...")
    try:
        driver.set_page_load_timeout(25)
        driver.get(TARGET_URL)
        time.sleep(MIN_DELAY_AFTER_LOAD)
        
        cloudflare_success, page_source = wait_for_cloudflare(driver, thread_name=thread_name, context="getting cookies")
        if cloudflare_success and page_source:
                try:
                    cookies = get_cookies_from_selenium(driver)
                    logger.info(f"[{thread_name}] Got cookies: {len(cookies)} items")
                except Exception as cookie_error:
                    logger.warning(f"[{thread_name}] Error getting cookies: {cookie_error}")
        else:
            logger.warning(f"[{thread_name}] Failed to get cookies (Cloudflare timeout or page crash)")
    except Exception as e:
        logger.warning(f"[{thread_name}] Error getting cookies: {e}")
    
    # Основной цикл парсинга
    logger.info(f"[{thread_name}] Starting main parsing loop (pages {page_start} to {total_pages}, step {page_step})...")
    
    while current_page <= total_pages:
        try:
            page_url = f"{TARGET_URL}?_paged={current_page}"
            logger.info(f"[{thread_name}] {'-'*60}")
            logger.info(f"[{thread_name}] Parsing page {current_page}/{total_pages} ({'even' if current_page % 2 == 0 else 'odd'})...")
            logger.info(f"[{thread_name}] URL: {page_url}")
            
            # Периодически сохраняем буфер
            if local_buffer and len(local_buffer) >= CSV_BUFFER_SAVE_SIZE:
                try:
                    with csv_lock:
                        append_to_csv(TEMP_CSV_FILE, local_buffer)
                    local_buffer.clear()
                except Exception as save_error:
                    logger.warning(f"[{thread_name}] Error saving buffer: {save_error}")
            
            # Пробуем через cloudscraper
            soup = None
            success = False
            
            if cookies:
                logger.debug(f"[{thread_name}] Trying cloudscraper for page {current_page}...")
                soup, success = parse_page_with_cloudscraper(page_url, cookies, current_proxy)
                if success:
                    logger.debug(f"[{thread_name}] Cloudscraper success for page {current_page}")
                else:
                    logger.debug(f"[{thread_name}] Cloudscraper failed for page {current_page}, trying Selenium...")
            
            # Fallback на Selenium
            if not success or not soup:
                if not driver:
                    # Пересоздаем драйвер
                    driver = create_driver(current_proxy)
                
                if driver:
                    try:
                        # Для первых страниц ждем полной загрузки контента (как при валидации)
                        wait_for_content = (current_page <= 3)  # Первые 3 страницы
                        soup, success = parse_page_with_selenium(driver, page_url, wait_for_content=wait_for_content)
                        if success:
                            try:
                                cookies = get_cookies_from_selenium(driver)
                            except:
                                pass
                    except Exception as selenium_error:
                        if is_tab_crashed_error(selenium_error):
                            logger.error(f"[{thread_name}] [TAB CRASH] Tab crash, searching for new proxy...")
                            driver = None
                            success = False
                        elif is_proxy_error(selenium_error):
                            logger.warning(f"[{thread_name}] [PROXY ERROR] Proxy error, searching for new proxy...")
                            driver = None
                            success = False
                        else:
                            logger.warning(f"[{thread_name}] Error parsing with Selenium: {selenium_error}")
                            success = False
            
            if not success or not soup:
                # Переходим обратно к фазе поиска прокси
                logger.warning(f"[{thread_name}] Failed to load page {current_page}, searching for new proxy...")
                logger.debug(f"[{thread_name}] Page load failure details: success={success}, soup={'exists' if soup else 'None'}")
                proxy_switches += 1
                
                # Закрываем драйвер
                if driver:
                    try:
                        driver.quit()
                        logger.debug(f"[{thread_name}] Driver closed after page load failure")
                    except Exception as close_error:
                        logger.debug(f"[{thread_name}] Error closing driver: {close_error}")
                    driver = None
                
                # Ищем новый прокси (продолжаем с текущего индекса)
                new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                    proxy_manager, proxies_list, proxies_lock, proxy_index, thread_name,
                    context=f"after page load failure (page {current_page})"
                )
                
                if not new_proxy or not new_driver:
                    logger.warning(f"[{thread_name}] Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                    # Не останавливаемся, продолжаем пытаться
                    time.sleep(10)  # Небольшая пауза перед следующей попыткой
                    continue
                
                current_proxy = new_proxy
                driver = new_driver
                proxy_index = new_proxy_index  # Обновляем индекс для следующего поиска
                
                # Продолжаем с той же страницы
                continue
            
            # Получаем page_source для проверки блокировки
            if driver:
                page_source = safe_get_page_source(driver)
            else:
                page_source = str(soup) if soup else ""
            
            if not page_source:
                logger.warning(f"[{thread_name}] Failed to get page {current_page} content")
                current_page += page_step
                continue
            
            # Проверяем блокировку
            block_check = is_page_blocked(soup, page_source)
            
            if block_check["blocked"]:
                block_reason = block_check.get('reason', 'unknown')
                partial_load = block_check.get('partial_load', False)
                logger.warning(f"[{thread_name}] Page {current_page} blocked: {block_reason} (partial_load={partial_load}) → searching for new proxy")
                cloudflare_blocks += 1
                proxy_switches += 1
                
                # Закрываем драйвер
                if driver:
                    try:
                        driver.quit()
                        logger.debug(f"[{thread_name}] Driver closed after blocking")
                    except Exception as close_error:
                        logger.debug(f"[{thread_name}] Error closing driver after blocking: {close_error}")
                    driver = None
                
                # Ищем новый прокси
                new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                    proxy_manager, proxies_list, proxies_lock, proxy_index, thread_name,
                    context=f"after blocking (page {current_page}, reason: {block_reason})"
                )
                
                if not new_proxy or not new_driver:
                    logger.warning(f"[{thread_name}] Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                    # Не останавливаемся, продолжаем пытаться
                    time.sleep(10)  # Небольшая пауза перед следующей попыткой
                    continue
                
                current_proxy = new_proxy
                driver = new_driver
                proxy_index = new_proxy_index  # Обновляем индекс для следующего поиска
                
                # Продолжаем с той же страницы
                continue
            
            # Парсим товары
            products, products_in_stock, total_products_on_page = get_products_from_page_soup(soup)
            
            # Проверяем статус страницы
            page_status = is_page_empty(soup, page_source, products_in_stock, total_products_on_page)
            
            if page_status["status"] == "normal" and products:
                # Нормальная страница с товарами
                local_buffer.extend(products)
                products_collected += len(products)
                empty_pages_count = 0
                
                logger.info(f"[{thread_name}] {'='*60}")
                logger.info(f"[{thread_name}] Page {current_page}: SUCCESS! Added {len(products)} products")
                logger.info(f"[{thread_name}] Total products collected so far: {products_collected}")
                logger.info(f"[{thread_name}] Products on this page:")
                for i, product in enumerate(products, 1):
                    logger.info(f"[{thread_name}]   {i}. {product.get('description', 'N/A')[:80]}... | Art: {product.get('article', 'N/A')} | Manuf: {product.get('manufacturer', 'N/A')} | Price: {product.get('price', 'N/A')}")
                logger.info(f"[{thread_name}] {'='*60}")
                
                # Записываем буфер если заполнен
                if len(local_buffer) >= CSV_BUFFER_FULL_SIZE:
                    try:
                        with csv_lock:
                            append_to_csv(TEMP_CSV_FILE, local_buffer)
                        logger.info(f"[{thread_name}] Saved {len(local_buffer)} products to CSV file")
                        local_buffer.clear()
                    except Exception as save_error:
                        logger.warning(f"[{thread_name}] Error writing buffer: {save_error}")
                
            elif page_status["status"] == "empty":
                # Пустая страница = страница БЕЗ товаров В НАЛИЧИИ
                if products_in_stock == 0:
                    empty_pages_count += 1
                    logger.warning(f"[{thread_name}] Page {current_page}: no products IN STOCK (empty in a row: {empty_pages_count})")
                    
                    # Останавливаемся после 2 пустых страниц подряд
                    if empty_pages_count >= MAX_EMPTY_PAGES:
                        logger.info(f"[{thread_name}] Found {MAX_EMPTY_PAGES} consecutive pages without products IN STOCK. Stopping parsing.")
                        break
                else:
                    empty_pages_count = 0
            
            pages_parsed += 1
            current_page += page_step
            
            # Задержка между страницами
            time.sleep(random.uniform(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES))
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if is_tab_crashed_error(e):
                logger.error(f"[{thread_name}] [TAB CRASH] Tab crash on page {current_page}, searching for new proxy...")
                proxy_switches += 1
                
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                # Ищем новый прокси
                new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                    proxy_manager, proxies_list, proxies_lock, proxy_index, thread_name,
                    context=f"after tab crash (page {current_page})"
                )
                
                if not new_proxy or not new_driver:
                    logger.warning(f"[{thread_name}] Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                    # Не останавливаемся, продолжаем пытаться
                    time.sleep(10)  # Небольшая пауза перед следующей попыткой
                    continue
                
                current_proxy = new_proxy
                driver = new_driver
                proxy_index = new_proxy_index  # Обновляем индекс для следующего поиска
                
                continue
            elif is_proxy_error(e):
                logger.warning(f"[{thread_name}] [PROXY ERROR] Proxy error on page {current_page}: {e}")
                # Ищем новый прокси (аналогично выше)
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                # Ищем новый прокси
                new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                    proxy_manager, proxies_list, proxies_lock, proxy_index, thread_name,
                    context=f"after proxy error (page {current_page})"
                )
                
                if not new_proxy or not new_driver:
                    logger.warning(f"[{thread_name}] Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                    # Не останавливаемся, продолжаем пытаться
                    time.sleep(10)  # Небольшая пауза перед следующей попыткой
                    continue
                
                current_proxy = new_proxy
                driver = new_driver
                proxy_index = new_proxy_index  # Обновляем индекс для следующего поиска
                
                continue
            else:
                logger.error(f"[{thread_name}] Error parsing page {current_page}: {e}")
                logger.debug(traceback.format_exc())
                current_page += page_step
                continue
    
    # Записываем оставшиеся товары из буфера
    if local_buffer:
        try:
            with csv_lock:
                append_to_csv(TEMP_CSV_FILE, local_buffer)
            logger.info(f"[{thread_name}] Written remaining {len(local_buffer)} products from buffer to CSV")
            local_buffer.clear()
        except Exception as buffer_error:
            logger.error(f"[{thread_name}] Error writing remaining products: {buffer_error}")
    
    # Закрываем драйвер
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    logger.info(f"[{thread_name}] {'='*60}")
    logger.info(f"[{thread_name}] PARSING COMPLETED")
    logger.info(f"[{thread_name}] Products collected: {products_collected}")
    logger.info(f"[{thread_name}] Pages parsed: {pages_parsed}")
    logger.info(f"[{thread_name}] Proxy switches: {proxy_switches}")
    logger.info(f"[{thread_name}] Cloudflare blocks: {cloudflare_blocks}")
    logger.info(f"[{thread_name}] {'='*60}")


def parse_all_pages_simple(
    proxy_manager: ProxyManager,
    total_pages: int,
    initial_proxy: Dict,
    proxies_list: List[Dict]
) -> Tuple[int, Dict]:
    """
    Упрощенная однопоточная версия парсинга всех страниц
    
    Args:
        proxy_manager: Менеджер прокси
        total_pages: Общее количество страниц
        initial_proxy: Начальный прокси для начала парсинга
        proxies_list: Список всех прокси для поиска новых при необходимости
    
    Returns:
        (total_products, metrics) - количество товаров и метрики
    """
    thread_name = "MainThread"
    total_products = 0
    empty_pages_count = 0
    pages_checked = 0
    proxy_switches = 0
    cloudflare_blocks = 0
    
    current_proxy = initial_proxy
    # Отслеживаем, когда прокси был валидирован (для retry-логики)
    proxy_validation_time = {}  # {proxy_key: timestamp}
    proxy_key = f"{current_proxy['ip']}:{current_proxy['port']}"
    proxy_validation_time[proxy_key] = time.time()  # Начальный прокси только что прошел валидацию
    logger.info(f"[{thread_name}] Using initial proxy {current_proxy['ip']}:{current_proxy['port']} to start parsing")
    
    # Получаем cookies через Selenium (один раз)
    logger.info(f"[{thread_name}] Getting cookies via proxy {current_proxy['ip']}:{current_proxy['port']}...")
    
    driver = None
    cookies = {}
    
    try:
        protocol = current_proxy.get('protocol', 'http').lower()
        driver = create_driver(current_proxy)
        if driver:
            driver.set_page_load_timeout(25)
            driver.get(TARGET_URL)
            time.sleep(MIN_DELAY_AFTER_LOAD)
            
            # Ждем Cloudflare
            page_source = safe_get_page_source(driver)
            if not page_source:
                logger.error("[TAB CRASH] Tab crash while getting cookies")
            else:
                cloudflare_success, page_source = wait_for_cloudflare(driver, thread_name=thread_name, context="getting cookies")
                if cloudflare_success and page_source:
                    try:
                        cookies = get_cookies_from_selenium(driver)
                        logger.info(f"Got cookies: {len(cookies)} items")
                    except Exception as cookie_error:
                        if is_tab_crashed_error(cookie_error):
                            logger.error(f"[TAB CRASH] Tab crash while getting cookies: {cookie_error}")
                        else:
                            logger.warning(f"Error getting cookies: {cookie_error}")
                else:
                    logger.warning("Failed to get cookies due to Cloudflare or tab crash")
    except Exception as e:
        if is_tab_crashed_error(e):
            logger.error(f"[TAB CRASH] Tab crash while getting cookies: {e}")
        elif is_proxy_error(e):
            logger.warning(f"[PROXY ERROR] Proxy error while getting cookies: {e}")
        else:
            logger.error(f"Error getting cookies: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
            driver = None
                
    # Буфер для товаров
    products_buffer = []
    
    # Основной цикл парсинга - парсим страницы последовательно
    current_page = 1
    driver = None  # Инициализируем драйвер
    proxy_index = 0  # Индекс для поиска нового прокси
    
    while current_page <= total_pages:
        try:
            page_url = f"{TARGET_URL}?_paged={current_page}"
            logger.info(f"[{thread_name}] Parsing page {current_page}/{total_pages}...")
            
            # Периодически сохраняем буфер для защиты от потери данных
            if products_buffer and len(products_buffer) >= CSV_BUFFER_SAVE_SIZE:
                try:
                    append_to_csv(TEMP_CSV_FILE, products_buffer)
                    products_buffer.clear()
                except Exception as save_error:
                    logger.warning(f"Error during periodic buffer save: {save_error}")
            
            # Пробуем через cloudscraper (быстро)
            soup = None
            success = False
            
            if cookies:
                soup, success = parse_page_with_cloudscraper(page_url, cookies, current_proxy)
            
            # Fallback на Selenium
            if not success or not soup:
                logger.info(f"Using Selenium for page {current_page}...")
                if not driver:
                    protocol = current_proxy.get('protocol', 'http').lower()
                    driver = create_driver(current_proxy)
                
                if driver:
                    try:
                        # Для первых страниц ждем полной загрузки контента (как при валидации)
                        wait_for_content = (current_page <= 3)  # Первые 3 страницы
                        soup, success = parse_page_with_selenium(driver, page_url, wait_for_content=wait_for_content)
                        if success:
                            # Обновляем cookies
                            try:
                                cookies = get_cookies_from_selenium(driver)
                            except Exception as cookie_error:
                                if is_tab_crashed_error(cookie_error):
                                    logger.error(f"[TAB CRASH] Tab crash while updating cookies: {cookie_error}")
                                    try:
                                        driver.quit()
                                    except:
                                        pass
                                    driver = None
                                    success = False
                                else:
                                    logger.warning(f"Error updating cookies: {cookie_error}")
                    except Exception as selenium_error:
                        if is_tab_crashed_error(selenium_error):
                            logger.error(f"[TAB CRASH] Tab crash while parsing with Selenium, recreating driver...")
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = None
                            success = False
                        elif is_proxy_error(selenium_error):
                            logger.warning(f"[PROXY ERROR] Proxy error while parsing: {selenium_error}")
                            success = False
                        else:
                            logger.warning(f"Error parsing with Selenium: {selenium_error}")
                            success = False
            
            if not success or not soup:
                logger.warning(f"Failed to load page {current_page}, trying new proxy...")
                proxy_switches += 1
                
                # Ищем новый прокси
                new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                    proxy_manager, proxies_list, None, proxy_index, thread_name,
                    context=f"after page load failure (page {current_page})"
                )
                
                if not new_proxy or not new_driver:
                    logger.warning(f"Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                    time.sleep(10)
                    continue
                
                # Закрываем старый драйвер
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                
                current_proxy = new_proxy
                driver = new_driver
                proxy_index = new_proxy_index
                
                # Продолжаем с той же страницы
                continue
                
            # Проверяем блокировку
            if driver:
                page_source = safe_get_page_source(driver)
                if not page_source:
                    logger.error(f"[TAB CRASH] Tab crash while getting page_source for page {current_page}, recreating driver...")
                    proxy_switches += 1
                    
                    new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                        proxy_manager, proxies_list, None, proxy_index, thread_name,
                        context=f"after tab crash (page {current_page})"
                    )
                    
                    if not new_proxy or not new_driver:
                        logger.warning(f"Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                        time.sleep(10)
                        continue
                    
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
                    
                    current_proxy = new_proxy
                    driver = new_driver
                    proxy_index = new_proxy_index
                    # Отмечаем, что новый прокси только что прошел валидацию
                    new_proxy_key = f"{current_proxy['ip']}:{current_proxy['port']}"
                    proxy_validation_time[new_proxy_key] = time.time()
                    continue
            else:
                page_source = str(soup) if soup else ""
            
            if not page_source:
                logger.warning(f"Failed to get page {current_page} content")
                current_page += 1
                continue
            
            block_check = is_page_blocked(soup, page_source)
            
            if block_check["blocked"]:
                # Если прокси только что прошел валидацию и это первые страницы - даем ему несколько попыток
                is_first_pages = current_page <= 5  # Первые 5 страниц
                max_retries_for_validated_proxy = 3  # Количество попыток для валидированного прокси (увеличено до 3)
                validation_timeout = 300  # Прокси считается "недавно валидированным" если валидация была менее 5 минут назад
                
                # Используем атрибут функции для хранения счетчика попыток
                if not hasattr(parse_all_pages_simple, '_proxy_retry_count'):
                    parse_all_pages_simple._proxy_retry_count = {}
                
                proxy_key = f"{current_proxy['ip']}:{current_proxy['port']}"
                if proxy_key not in parse_all_pages_simple._proxy_retry_count:
                    parse_all_pages_simple._proxy_retry_count[proxy_key] = 0
                
                # Проверяем, был ли прокси недавно валидирован
                proxy_was_recently_validated = (
                    proxy_key in proxy_validation_time and 
                    (time.time() - proxy_validation_time[proxy_key]) < validation_timeout
                )
                
                if is_first_pages and proxy_was_recently_validated and parse_all_pages_simple._proxy_retry_count[proxy_key] < max_retries_for_validated_proxy:
                    parse_all_pages_simple._proxy_retry_count[proxy_key] += 1
                    logger.warning(f"Page {current_page} blocked: {block_check['reason']}, but proxy was validated recently. Retry {parse_all_pages_simple._proxy_retry_count[proxy_key]}/{max_retries_for_validated_proxy}...")
                    
                    # Пробуем перезагрузить страницу с ожиданием полной загрузки
                    if driver:
                        try:
                            logger.info(f"Reloading page {current_page} with full content wait...")
                            time.sleep(3)  # Небольшая пауза перед перезагрузкой
                            driver.refresh()
                            time.sleep(5)  # Ожидание после refresh
                            
                            # Скроллим и ждем загрузки
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                            time.sleep(2)
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                            time.sleep(2)
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(5)  # Даем время на загрузку товаров
                            
                            # Получаем обновленный page_source
                            page_source = safe_get_page_source(driver)
                            if page_source:
                                soup = BeautifulSoup(page_source, 'html.parser')
                                block_check = is_page_blocked(soup, page_source)
                                
                                if not block_check["blocked"]:
                                    logger.info(f"Page {current_page} loaded successfully after reload!")
                                    parse_all_pages_simple._proxy_retry_count[proxy_key] = 0  # Сбрасываем счетчик
                                    # Продолжаем парсинг ниже
                                else:
                                    logger.warning(f"Page still blocked after reload: {block_check['reason']}")
                                    # Продолжаем цикл, попробуем еще раз
                                    continue
                            else:
                                logger.warning(f"Failed to get page_source after reload")
                                continue
                        except Exception as reload_error:
                            logger.warning(f"Error reloading page: {reload_error}")
                            continue
                    else:
                        # Если нет драйвера, просто пропускаем эту попытку
                        time.sleep(3)
                        continue
                else:
                    # Исчерпали попытки или это не первые страницы - ищем новый прокси
                    logger.warning(f"Page {current_page} blocked: {block_check['reason']} → switching proxy")
                    parse_all_pages_simple._proxy_retry_count[proxy_key] = 0  # Сбрасываем счетчик
                    cloudflare_blocks += 1
                    proxy_switches += 1
                    
                    new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                        proxy_manager, proxies_list, None, proxy_index, thread_name,
                        context=f"after blocking (page {current_page}, reason: {block_check['reason']})"
                    )
                    
                    if not new_proxy or not new_driver:
                        logger.warning(f"Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                        time.sleep(10)
                        continue
                    
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
                    
                    current_proxy = new_proxy
                    driver = new_driver
                    proxy_index = new_proxy_index
                    # Отмечаем, что новый прокси только что прошел валидацию
                    new_proxy_key = f"{current_proxy['ip']}:{current_proxy['port']}"
                    proxy_validation_time[new_proxy_key] = time.time()
                    continue
            
            # Парсим товары
            products, products_in_stock, total_products_on_page = get_products_from_page_soup(soup)
            
            # Проверяем статус страницы
            page_status = is_page_empty(soup, page_source, products_in_stock, total_products_on_page)
            
            if page_status["status"] == "normal" and products:
                products_buffer.extend(products)
                total_products += len(products)
                empty_pages_count = 0
                
                logger.info(f"[{thread_name}] {'='*60}")
                logger.info(f"[{thread_name}] Page {current_page}: SUCCESS! Added {len(products)} products")
                logger.info(f"[{thread_name}] Total products collected so far: {total_products}")
                logger.info(f"[{thread_name}] Products on this page:")
                for i, product in enumerate(products, 1):
                    logger.info(f"[{thread_name}]   {i}. {product.get('description', 'N/A')[:80]}... | Art: {product.get('article', 'N/A')} | Manuf: {product.get('manufacturer', 'N/A')} | Price: {product.get('price', 'N/A')}")
                logger.info(f"[{thread_name}] {'='*60}")
                
                if len(products_buffer) >= CSV_BUFFER_FULL_SIZE:
                    append_to_csv(TEMP_CSV_FILE, products_buffer)
                    products_buffer.clear()
                    
            elif page_status["status"] == "empty":
                if products_in_stock == 0:
                    empty_pages_count += 1
                    logger.warning(f"Page {current_page}: no products IN STOCK (empty in a row: {empty_pages_count})")
                    
                    if empty_pages_count >= MAX_EMPTY_PAGES:
                        logger.info(f"Found {MAX_EMPTY_PAGES} consecutive pages without products IN STOCK. Stopping parsing.")
                        break
                else:
                    empty_pages_count = 0
            
            pages_checked += 1
            current_page += 1
            
            # Задержка между страницами
            time.sleep(random.uniform(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES))
            
        except Exception as e:
            if is_tab_crashed_error(e):
                logger.error(f"[TAB CRASH] Tab crash detected on page {current_page}, recreating driver...")
                proxy_switches += 1
                
                new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                    proxy_manager, proxies_list, None, proxy_index, thread_name,
                    context=f"after tab crash (page {current_page})"
                )
                
                if not new_proxy or not new_driver:
                    logger.warning(f"Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                    time.sleep(10)
                    continue
                
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                
                current_proxy = new_proxy
                driver = new_driver
                proxy_index = new_proxy_index
                # Отмечаем, что новый прокси только что прошел валидацию
                new_proxy_key = f"{current_proxy['ip']}:{current_proxy['port']}"
                proxy_validation_time[new_proxy_key] = time.time()
                continue
            elif is_proxy_error(e):
                logger.warning(f"[PROXY ERROR] Proxy error on page {current_page}: {e}")
                proxy_switches += 1
                
                new_proxy, new_driver, proxies_checked, new_proxy_index = find_new_working_proxy(
                    proxy_manager, proxies_list, None, proxy_index, thread_name,
                    context=f"after proxy error (page {current_page})"
                )
                
                if not new_proxy or not new_driver:
                    logger.warning(f"Failed to find new working proxy after checking {proxies_checked} proxies, will retry on next iteration")
                    time.sleep(10)
                    continue
                
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                
                current_proxy = new_proxy
                driver = new_driver
                proxy_index = new_proxy_index
                # Отмечаем, что новый прокси только что прошел валидацию
                new_proxy_key = f"{current_proxy['ip']}:{current_proxy['port']}"
                proxy_validation_time[new_proxy_key] = time.time()
                continue
            else:
                logger.error(f"Error parsing page {current_page}: {e}")
                logger.debug(traceback.format_exc())
                current_page += 1
                continue
    
    # Записываем оставшиеся товары из буфера
    if products_buffer:
        try:
            append_to_csv(TEMP_CSV_FILE, products_buffer)
            logger.info(f"Written remaining products from buffer: {len(products_buffer)}")
            products_buffer.clear()
        except Exception as buffer_error:
            logger.error(f"Error writing remaining products: {buffer_error}")
    
    # Закрываем драйвер
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    logger.info(f"Parsing completed: collected {total_products} products, checked {pages_checked} pages")
    
    return total_products, {
        "pages_checked": pages_checked,
        "proxy_switches": proxy_switches,
        "cloudflare_blocks": cloudflare_blocks
    }


def parse_all_pages(
    proxy_manager: ProxyManager,
    total_pages: Optional[int],
    initial_proxy: Optional[Dict] = None
) -> Tuple[int, Dict]:
    """
    Парсит все страницы последовательно
    
    Args:
        proxy_manager: Менеджер прокси
        total_pages: Общее количество страниц
        initial_proxy: Начальный прокси для начала парсинга (опционально)
    
    Returns:
        (total_products, metrics) - количество товаров и метрики
    """
    thread_name = "MainThread"
    total_products = 0
    empty_pages_count = 0
    pages_checked = 0
    proxy_switches = 0
    cloudflare_blocks = 0
    
    # Если передан начальный прокси - используем его, иначе ищем новые
    if initial_proxy:
        logger.info(f"[{thread_name}] Using initial proxy {initial_proxy['ip']}:{initial_proxy['port']} to start parsing")
        working_proxies = [initial_proxy]
        # В фоне ищем дополнительные прокси (но не блокируем парсинг)
        logger.info(f"[{thread_name}] Starting background search for additional proxies (minimum {MIN_WORKING_PROXIES})...")
    else:
        # Получаем первый рабочий прокси (минимум 1 для начала)
        logger.info(f"[{thread_name}] Searching for working proxies for parsing...")
        working_proxies = proxy_manager.get_working_proxies(
            min_count=1,  # Начинаем с 1 прокси, не ждем 10
            max_to_check=MAX_PROXIES_TO_CHECK
        )
    
    if not working_proxies:
        logger.error(f"[{thread_name}] Failed to find working proxies!")
        return 0, {"pages_checked": 0, "proxy_switches": 0, "cloudflare_blocks": 0}
    
    logger.info(f"[{thread_name}] Found {len(working_proxies)} working proxies, starting parsing")
    
    # Используем список для thread-safe доступа (если будет фоновый поиск)
    working_proxies_list = working_proxies.copy()  # Копируем в список для thread-safe доступа
    proxies_lock = None  # Будет создан, если нужен фоновый поиск
    
    if len(working_proxies_list) < MIN_WORKING_PROXIES:
        logger.info(f"[{thread_name}] We have {len(working_proxies_list)} proxies, need {MIN_WORKING_PROXIES}. Starting background search...")
        # Запускаем поиск в фоне, но не блокируем парсинг
        proxies_lock = threading.Lock()
        
        def background_proxy_search():
            bg_thread_name = "BackgroundProxySearch"
            logger.info(f"[{bg_thread_name}] Background search for additional proxies started...")
            try:
                additional_proxies = proxy_manager.get_working_proxies(
                    min_count=MIN_WORKING_PROXIES - len(working_proxies_list),
                    max_to_check=MAX_PROXIES_TO_CHECK,
                    use_parallel=True
                )
                if additional_proxies:
                    with proxies_lock:
                        working_proxies_list.extend(additional_proxies)
                        current_count = len(working_proxies_list)
                    logger.info(f"[{bg_thread_name}] Background search completed: added {len(additional_proxies)} proxies (total: {current_count})")
                else:
                    logger.warning(f"[{bg_thread_name}] Background search found no additional proxies")
            except Exception as e:
                logger.error(f"[{bg_thread_name}] Error in background proxy search: {e}")
        
        bg_thread = threading.Thread(target=background_proxy_search, daemon=True, name="BackgroundProxySearch")
        bg_thread.start()
        logger.info(f"[{thread_name}] Background proxy search started, continuing parsing with available proxies")
    else:
        proxies_lock = None  # Не нужен, если не запускаем фоновый поиск
    
    # Получаем cookies через Selenium (один раз)
    # Используем первый прокси из списка для получения cookies
    if proxies_lock:
        with proxies_lock:
            current_proxy = working_proxies_list[0] if working_proxies_list else None
    else:
        current_proxy = working_proxies_list[0] if working_proxies_list else None
    if not current_proxy:
        logger.error(f"[{thread_name}] No working proxies for getting cookies!")
        return 0, {"pages_checked": 0, "proxy_switches": 0, "cloudflare_blocks": 0}
    
    logger.info(f"[{thread_name}] Getting cookies via proxy {current_proxy['ip']}:{current_proxy['port']}...")
    
    driver = None
    cookies = {}
    
    try:
        protocol = current_proxy.get('protocol', 'http').lower()
        driver = create_driver(current_proxy)
        if driver:
            driver.set_page_load_timeout(25)
            driver.get(TARGET_URL)
            time.sleep(MIN_DELAY_AFTER_LOAD)
            
            # Ждем Cloudflare - используем безопасное получение page_source
            page_source = safe_get_page_source(driver)
            if not page_source:
                logger.error("[TAB CRASH] Tab crash while getting cookies")
            else:
                cloudflare_success, page_source = wait_for_cloudflare(driver, thread_name=thread_name, context="getting cookies")
                if cloudflare_success and page_source:
                    try:
                        cookies = get_cookies_from_selenium(driver)
                        logger.info(f"Got cookies: {len(cookies)} items")
                    except Exception as cookie_error:
                        if is_tab_crashed_error(cookie_error):
                            logger.error(f"[TAB CRASH] Tab crash while getting cookies: {cookie_error}")
                        else:
                            logger.warning(f"Error getting cookies: {cookie_error}")
                else:
                    logger.warning("Failed to get cookies due to Cloudflare or tab crash")
    except Exception as e:
        if is_tab_crashed_error(e):
            logger.error(f"[TAB CRASH] Tab crash while getting cookies: {e}")
        elif is_proxy_error(e):
            logger.warning(f"[PROXY ERROR] Proxy error while getting cookies: {e}")
        else:
            logger.error(f"Error getting cookies: {e}")
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
    # Используем working_proxies_list для доступа к прокси (может обновляться в фоне)
    if proxies_lock:
        with proxies_lock:
            current_proxy = working_proxies_list[0] if working_proxies_list else None
    else:
        current_proxy = working_proxies_list[0] if working_proxies_list else None
    
    if not current_proxy:
        current_proxy = proxy_manager.get_next_proxy()  # Fallback через менеджер
    
    driver = None  # Инициализируем драйвер
    
    while current_page <= total_pages:
        try:
            page_url = f"{TARGET_URL}?_paged={current_page}"
            logger.info(f"[{thread_name}] Parsing page {current_page}/{total_pages}...")
            
            # Периодически сохраняем буфер для защиты от потери данных
            if products_buffer and len(products_buffer) >= CSV_BUFFER_SAVE_SIZE:
                try:
                    append_to_csv(TEMP_CSV_FILE, products_buffer)
                    products_buffer.clear()
                except Exception as save_error:
                    logger.warning(f"Error during periodic buffer save: {save_error}")
            
            # Пробуем через cloudscraper (быстро)
            soup = None
            success = False
            
            if cookies:
                soup, success = parse_page_with_cloudscraper(page_url, cookies, current_proxy)
            
            # Fallback на Selenium
            if not success or not soup:
                logger.info(f"Using Selenium for page {current_page}...")
                if not driver:
                    protocol = current_proxy.get('protocol', 'http').lower()
                    driver = create_driver(current_proxy)
                
                if driver:
                    try:
                        # Для первых страниц ждем полной загрузки контента (как при валидации)
                        wait_for_content = (current_page <= 3)  # Первые 3 страницы
                        soup, success = parse_page_with_selenium(driver, page_url, wait_for_content=wait_for_content)
                        if success:
                            # Обновляем cookies
                            try:
                                cookies = get_cookies_from_selenium(driver)
                            except Exception as cookie_error:
                                if is_tab_crashed_error(cookie_error):
                                    logger.error(f"[TAB CRASH] Tab crash while updating cookies: {cookie_error}")
                                    # Пересоздаем драйвер
                                    try:
                                        driver.quit()
                                    except:
                                        pass
                                    driver = None
                                    success = False
                                else:
                                    logger.warning(f"Error updating cookies: {cookie_error}")
                    except Exception as selenium_error:
                        if is_tab_crashed_error(selenium_error):
                            logger.error(f"[TAB CRASH] Tab crash while parsing with Selenium, recreating driver...")
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = None
                            success = False
                        elif is_proxy_error(selenium_error):
                            logger.warning(f"[PROXY ERROR] Proxy error while parsing: {selenium_error}")
                            success = False
                        else:
                            logger.warning(f"Error parsing with Selenium: {selenium_error}")
                            success = False
            
            if not success or not soup:
                logger.warning(f"Failed to load page {current_page}, trying new proxy...")
                proxy_switches += 1
                
                # Пересоздаем драйвер с новым прокси
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Failed to recreate driver after load error!")
                    break
                
                logger.info(f"Driver recreated, continuing from page {current_page}")
                # Продолжаем с той же страницы (не увеличиваем current_page)
                continue
            
            # Проверяем блокировку
            # Для cloudscraper используем HTML из soup, для Selenium - из driver
            if driver:
                page_source = safe_get_page_source(driver)
                if not page_source:
                    # Краш вкладки при получении page_source - пересоздаем драйвер с новым прокси
                    logger.error(f"[TAB CRASH] Tab crash while getting page_source for page {current_page}, recreating driver...")
                    proxy_switches += 1
                    
                    driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                        proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                    )
                    
                    if not driver or not current_proxy:
                        logger.error("Failed to recreate driver after tab crash!")
                        break
                    
                    logger.info(f"[TAB CRASH] Driver recreated, continuing from page {current_page}")
                    # Продолжаем с той же страницы (не увеличиваем current_page)
                    continue
            else:
                # Если использовали cloudscraper, получаем HTML из soup
                page_source = str(soup) if soup else ""
            
            if not page_source:
                logger.warning(f"Failed to get page {current_page} content")
                current_page += 1
                continue
            
            block_check = is_page_blocked(soup, page_source)
            
            if block_check["blocked"]:
                logger.warning(f"Page {current_page} blocked: {block_check['reason']} → switching proxy")
                cloudflare_blocks += 1
                proxy_switches += 1
                
                # Пересоздаем драйвер с новым прокси
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Failed to recreate driver with new proxy!")
                    break
                
                logger.info(f"Driver recreated with new proxy, continuing from page {current_page}")
                # Продолжаем с той же страницы (не увеличиваем current_page)
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
                
                logger.info(f"Page {current_page}: added {len(products)} products (total: {total_products})")
                
                # Записываем буфер если заполнен
                if len(products_buffer) >= CSV_BUFFER_FULL_SIZE:
                    append_to_csv(TEMP_CSV_FILE, products_buffer)
                    products_buffer.clear()
                    
            elif page_status["status"] == "empty":
                # Пустая страница = страница БЕЗ товаров В НАЛИЧИИ (но может быть структура каталога)
                # Увеличиваем счетчик только если действительно нет товаров в наличии
                if products_in_stock == 0:
                    empty_pages_count += 1
                    logger.warning(f"Page {current_page}: no products IN STOCK (empty in a row: {empty_pages_count})")
                    
                    # Останавливаемся после 2 пустых страниц подряд (без товаров в наличии)
                    if empty_pages_count >= MAX_EMPTY_PAGES:
                        logger.info(f"Found {MAX_EMPTY_PAGES} consecutive pages without products IN STOCK. Stopping parsing.")
                        break
                else:
                    # Если есть товары в наличии, но статус empty - это странно, сбрасываем счетчик
                    empty_pages_count = 0
                    
            elif page_status["status"] == "partial":
                # Частичная загрузка - пробуем перезагрузить
                logger.warning(f"Page {current_page}: partial load, trying again...")
                if driver:
                    try:
                        soup, success = reload_page_if_needed(driver, page_url, max_retries=1)
                        if success and soup:
                            products, products_in_stock, total_products_on_page = get_products_from_page_soup(soup)
                            if products:
                                products_buffer.extend(products)
                                total_products += len(products)
                                empty_pages_count = 0
                                logger.info(f"Page {current_page}: after reload added {len(products)} products")
                    except Exception as reload_error:
                        if is_tab_crashed_error(reload_error):
                            logger.error(f"[TAB CRASH] Tab crash while reloading partial page {current_page}, recreating driver...")
                            proxy_switches += 1
                            
                            driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                                proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                            )
                            
                            if not driver or not current_proxy:
                                logger.error("Failed to recreate driver after tab crash during reload!")
                                break
                            
                            logger.info(f"[TAB CRASH] Driver recreated, continuing from page {current_page}")
                            # Продолжаем с той же страницы
                            continue
                        else:
                            logger.warning(f"Error reloading partial page: {reload_error}")
            
            elif page_status["status"] == "blocked":
                # Блокировка - получаем новый прокси
                logger.warning(f"Page {current_page}: blocked (status blocked) → switching proxy")
                cloudflare_blocks += 1
                proxy_switches += 1
                
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Failed to recreate driver after blocking!")
                    break
                
                logger.info(f"Driver recreated with new proxy, continuing from page {current_page}")
                # Продолжаем с той же страницы
                continue
            
            pages_checked += 1
            current_page += 1
            
            # Задержка между страницами
            time.sleep(random.uniform(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES))
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Проверяем на краш вкладки - это критическая ошибка, требующая пересоздания драйвера
            if is_tab_crashed_error(e):
                logger.error(f"[TAB CRASH] Tab crash detected on page {current_page}, recreating driver...")
                proxy_switches += 1
                
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Failed to recreate driver after tab crash!")
                    break
                
                logger.info(f"[TAB CRASH] Driver recreated, continuing from page {current_page}")
                # Не увеличиваем current_page - попробуем еще раз с новым драйвером
                continue
            
            # Проверяем на ошибку прокси
            elif is_proxy_error(e):
                logger.warning(f"[PROXY ERROR] Proxy error on page {current_page}: {e}")
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
                            logger.error(f"[TAB CRASH] Tab crash during retry after proxy error")
                            proxy_switches += 1
                            
                            driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                                proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                            )
                            
                            if not driver or not current_proxy:
                                logger.error("Failed to recreate driver after tab crash during retry!")
                                break
                            
                            logger.info(f"[TAB CRASH] Driver recreated, continuing from page {current_page}")
                            # Продолжаем с той же страницы
                            continue
                
                # Если retry не помог - получаем новый прокси
                logger.info(f"Getting new proxy after proxy error...")
                proxy_switches += 1
                
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Failed to recreate driver after proxy error!")
                    break
                
                logger.info(f"Driver recreated with new proxy, continuing from page {current_page}")
                # Не увеличиваем current_page - попробуем еще раз с новым прокси
                continue
            else:
                logger.error(f"Error parsing page {current_page}: {e}")
                logger.debug(traceback.format_exc())
                current_page += 1
                continue
    
    # Записываем оставшиеся товары из буфера
    if products_buffer:
        try:
            append_to_csv(TEMP_CSV_FILE, products_buffer)
            logger.info(f"Written remaining products from buffer: {len(products_buffer)}")
            products_buffer.clear()
        except Exception as buffer_error:
            logger.error(f"Error writing remaining products: {buffer_error}")
    
    # Закрываем драйвер
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    logger.info(f"Parsing completed: collected {total_products} products, checked {pages_checked} pages")
    
    return total_products, {
        "pages_checked": pages_checked,
        "proxy_switches": proxy_switches,
        "cloudflare_blocks": cloudflare_blocks
    }


def main():
    """Главная функция - однопоточный парсинг"""
    script_name = "trast"
    main_thread_name = "MainThread"
    logger.info("=" * 80)
    logger.info("=== TRAST PARSER STARTED (SINGLE-THREADED) ===")
    logger.info(f"Target URL: {TARGET_URL}")
    logger.info(f"Start time: {datetime.now()}")
    logger.info("=" * 80)
    
    # Уведомление о старте
    TelegramNotifier.notify("[Trast] Update started")
    
    # Записываем старт скрипта в БД
    try:
        set_script_start(script_name)
        logger.info(f"[{main_thread_name}] Database connection successful")
    except Exception as db_error:
        logger.warning(f"[{main_thread_name}] Database connection failed: {db_error}, continuing without DB...")
        # Продолжаем без БД
    
    start_time = datetime.now()
    error_message = None
    total_pages = None
    total_products = 0
    
    try:
        # Создаем временный CSV файл
        create_new_csv(TEMP_CSV_FILE)
        logger.info(f"[{main_thread_name}] Temporary CSV file created for data writing")
    except Exception as e:
        logger.error(f"[{main_thread_name}] Error creating temporary files: {e}")
        logger.error(traceback.format_exc())
        error_message = str(e)
        TelegramNotifier.notify(f"[Trast] Update failed — <code>{error_message}</code>")
        sys.exit(1)
    
    # Инициализируем прокси менеджер
    logger.info(f"[{main_thread_name}] Initializing ProxyManager...")
    try:
        proxy_manager = ProxyManager(country_filter=PREFERRED_COUNTRIES)
        logger.info(f"[{main_thread_name}] ProxyManager initialized")
        log_proxy_health_summary(proxy_manager, "startup", main_thread_name)
    except Exception as e:
        logger.error(f"[{main_thread_name}] Error initializing ProxyManager: {e}")
        logger.error(traceback.format_exc())
        error_message = str(e)
        TelegramNotifier.notify(f"[Trast] Update failed — <code>{error_message}</code>")
        sys.exit(1)
    
    # Загружаем прокси синхронно
    logger.info(f"[{main_thread_name}] Downloading proxies from all sources...")
    try:
        if proxy_manager.download_proxies(force_update=True):
            downloaded_proxies = proxy_manager._load_proxies()
            logger.info(f"[{main_thread_name}] Loaded {len(downloaded_proxies) if downloaded_proxies else 0} proxies")
        else:
            logger.warning(f"[{main_thread_name}] Failed to download proxies, using cached")
            downloaded_proxies = proxy_manager._load_proxies()
    except Exception as e:
        logger.warning(f"[{main_thread_name}] Error downloading proxies: {e}, using cached")
        downloaded_proxies = proxy_manager._load_proxies()
    
    if not downloaded_proxies:
        logger.error(f"[{main_thread_name}] No proxies available!")
        error_message = "No proxies available"
        TelegramNotifier.notify(f"[Trast] Update failed — <code>{error_message}</code>")
        sys.exit(1)
    
    # Приоритизируем прокси и прогреваем пул
    logger.info(f"[{main_thread_name}] Prioritizing proxies and warming up pool...")
    downloaded_proxies = prioritize_proxies(downloaded_proxies)
    try:
        proxy_manager.ensure_warm_proxy_pool(MIN_WORKING_PROXIES)
        logger.info(f"[{main_thread_name}] Proxy pool warmed up")
    except Exception as e:
        logger.warning(f"[{main_thread_name}] Failed to warm up proxy pool: {e}, continuing...")
    
    # Ищем рабочий прокси и получаем количество страниц
    logger.info(f"[{main_thread_name}] Searching for working proxy...")
    current_proxy = None
    proxy_index = 0
    max_search_time = PROXY_SEARCH_INITIAL_TIMEOUT
    search_start_time = time.time()
    failures_since_refresh = 0
    refresh_threshold = 15
    cooldown_skips = 0
    
    def refresh_proxy_pool_local(reason: str) -> bool:
        """Локальная функция для обновления пула прокси"""
        logger.info(f"[{main_thread_name}] Forcing proxy refresh ({reason})...")
        try:
            if proxy_manager.download_proxies(force_update=True):
                updated_proxies = proxy_manager._load_proxies()
                if updated_proxies:
                    downloaded_proxies.clear()
                    downloaded_proxies.extend(prioritize_proxies(updated_proxies))
                    logger.info(f"[{main_thread_name}] Proxy pool refreshed with {len(updated_proxies)} entries")
                    try:
                        proxy_manager.ensure_warm_proxy_pool(MIN_WORKING_PROXIES)
                    except Exception as e:
                        logger.warning(f"[{main_thread_name}] Failed to warm up after refresh: {e}")
                    return True
        except Exception as refresh_error:
            logger.warning(f"[{main_thread_name}] Failed to refresh proxies: {refresh_error}")
        return False
    
    while True:
        elapsed = time.time() - search_start_time
        if elapsed >= max_search_time:
            logger.warning(f"[{main_thread_name}] Proxy search timeout exceeded ({max_search_time}s), but continuing search...")
            search_start_time = time.time()
        
        if proxy_index >= len(downloaded_proxies):
            logger.debug(f"[{main_thread_name}] Reached end of proxy list, waiting for update...")
            time.sleep(PROXY_LIST_WAIT_DELAY)
            # Попробуем обновить список прокси
            if refresh_proxy_pool_local("end of list reached"):
                proxy_index = 0
                continue
        
        # Пропускаем прокси в cooldown
        proxy_candidate = downloaded_proxies[proxy_index]
        if proxy_manager.is_proxy_in_cooldown(proxy_candidate):
            cooldown_skips += 1
            proxy_index += 1
            if len(downloaded_proxies) > 0 and cooldown_skips >= len(downloaded_proxies):
                logger.info(f"[{main_thread_name}] All proxies are cooling down, waiting {PROXY_LIST_WAIT_DELAY}s for refresh...")
                cooldown_skips = 0
                time.sleep(PROXY_LIST_WAIT_DELAY)
                if refresh_proxy_pool_local("all proxies in cooldown"):
                    proxy_index = 0
            continue
        
        proxy = proxy_candidate
        proxy_index += 1
        cooldown_skips = 0
        proxy_key = f"{proxy['ip']}:{proxy['port']}"
        elapsed_search = int(time.time() - search_start_time)
        
        # Сначала базовая проверка
        basic_ok, basic_info = proxy_manager.validate_proxy_basic(proxy)
        if not basic_ok:
            reason = (basic_info or {}).get('reason', 'basic_check_failed')
            logger.debug(f"[{main_thread_name}] Proxy {proxy_key} basic validation failed: reason={reason}")
            failures_since_refresh += 1
            if failures_since_refresh >= refresh_threshold:
                if refresh_proxy_pool_local(f"{failures_since_refresh} consecutive failures"):
                    proxy_index = 0
                    failures_since_refresh = 0
                    continue
                failures_since_refresh = 0
            continue
        
        logger.info(f"[{main_thread_name}] [{proxy_index}] Checking proxy {proxy_key} ({proxy.get('protocol', 'http').upper()})...")
        logger.info(f"[{main_thread_name}] Search progress: {elapsed_search}s elapsed, {proxy_index} proxies checked")
        
        try:
            trast_ok, trast_info = proxy_manager.validate_proxy_for_trast(proxy)
            if trast_ok and 'total_pages' in trast_info and trast_info['total_pages'] > 0:
                current_proxy = proxy.copy()
                current_proxy.update(trast_info)
                total_pages = trast_info['total_pages']
                
                elapsed_search = int(time.time() - search_start_time)
                logger.info(f"[{main_thread_name}] {'='*60}")
                logger.info(f"[{main_thread_name}] WORKING PROXY FOUND!")
                logger.info(f"[{main_thread_name}] Proxy: {proxy_key} ({proxy.get('protocol', 'http').upper()})")
                logger.info(f"[{main_thread_name}] Total pages: {total_pages}")
                logger.info(f"[{main_thread_name}] Search time: {elapsed_search}s")
                logger.info(f"[{main_thread_name}] {'='*60}")
                logger.info(f"[{main_thread_name}] STARTING PARSING NOW with proxy {proxy_key}...")
                break
            else:
                reason = "validation failed"
                if not trast_ok:
                    reason = trast_info.get('reason', 'not working')
                elif 'total_pages' not in trast_info:
                    reason = "no page count"
                elif trast_info.get('total_pages', 0) <= 0:
                    reason = f"invalid page count: {trast_info.get('total_pages')}"
                logger.warning(f"[{main_thread_name}] Proxy {proxy_key} not working ({reason}), continuing search...")
                failures_since_refresh += 1
                if failures_since_refresh >= refresh_threshold:
                    if refresh_proxy_pool_local(f"{failures_since_refresh} consecutive failures"):
                        proxy_index = 0
                        failures_since_refresh = 0
                        continue
                    failures_since_refresh = 0
        except Exception as e:
            error_type = type(e).__name__
            logger.warning(f"[{main_thread_name}] Error checking proxy {proxy_key}: {error_type}: {str(e)[:150]}")
            failures_since_refresh += 1
            if failures_since_refresh >= refresh_threshold:
                if refresh_proxy_pool_local(f"{failures_since_refresh} consecutive failures"):
                    proxy_index = 0
                    failures_since_refresh = 0
                    continue
                failures_since_refresh = 0
            continue
    
    if not current_proxy or not total_pages or total_pages <= 0:
        logger.error(f"[{main_thread_name}] Failed to find working proxy with page count!")
        error_message = "Failed to find working proxy"
        TelegramNotifier.notify(f"[Trast] Update failed — <code>{error_message}</code>")
        sys.exit(1)
    
    # Запускаем последовательный парсинг
    logger.info(f"[{main_thread_name}] Starting sequential parsing...")
    try:
        total_products, metrics = parse_all_pages_simple(
            proxy_manager=proxy_manager,
            total_pages=total_pages,
            initial_proxy=current_proxy,
            proxies_list=downloaded_proxies
        )
    except Exception as e:
        logger.error(f"[{main_thread_name}] Error during parsing: {e}")
        logger.error(traceback.format_exc())
        error_message = str(e)
    
    # Финализация
    duration = (datetime.now() - start_time).total_seconds()
    
    # Подсчитываем количество товаров из CSV файла
    if total_products == 0:
        try:
            if os.path.exists(TEMP_CSV_FILE) and os.path.getsize(TEMP_CSV_FILE) > 0:
                import csv
                with open(TEMP_CSV_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    total_products = sum(1 for _ in reader)
        except Exception as count_error:
            logger.warning(f"[{main_thread_name}] Failed to count products: {count_error}")
    
    # Проверяем, есть ли данные для сохранения
    try:
        if os.path.exists(TEMP_CSV_FILE) and os.path.getsize(TEMP_CSV_FILE) > 0:
            file_size = os.path.getsize(TEMP_CSV_FILE)
            logger.info(f"[{main_thread_name}] Found data to save (file size: {file_size} bytes)")
            finalize_output_files()
            logger.info(f"[{main_thread_name}] Data saved successfully")
            status = 'done' if total_products >= 100 else 'insufficient_data'
        else:
            logger.warning(f"[{main_thread_name}] No data to save")
            cleanup_temp_files()
            status = 'insufficient_data'
    except Exception as save_error:
        logger.error(f"[{main_thread_name}] Error saving data: {save_error}")
        error_message = error_message or str(save_error)
        status = 'error'
        # При ошибке сохранения удаляем только временные файлы, основной файл не трогаем
        cleanup_temp_files()
        logger.info(f"[{main_thread_name}] Temporary files cleaned up, main file unchanged")
    
    # Формируем метрики для уведомления
    metrics_suffix = ""
    if total_pages:
        metrics_suffix = f" — Pages: {total_pages}"
    
    # Отправляем уведомление в Telegram
    if status == 'done':
        TelegramNotifier.notify(f"[Trast] Update completed successfully — Duration: {duration:.2f}s, Products: {total_products}{metrics_suffix}")
    elif status == 'insufficient_data':
        TelegramNotifier.notify(f"[Trast] Update completed with insufficient data — Duration: {duration:.2f}s, Products: {total_products}{metrics_suffix}")
    else:
        failure_details = error_message or "Unknown error"
        TelegramNotifier.notify(f"[Trast] Update failed — <code>{failure_details}</code>")
    
    # Записываем окончание скрипта в БД
    try:
        set_script_end(script_name, status=status)
    except Exception as db_end_error:
        logger.warning(f"[{main_thread_name}] Error saving script end to database: {db_end_error}")
    
    log_proxy_health_summary(proxy_manager, "finish", main_thread_name)
    logger.info("=" * 80)
    logger.info(f"[{main_thread_name}] Parsing completed!")
    logger.info(f"[{main_thread_name}] Execution time: {round(duration, 2)} seconds")
    logger.info(f"[{main_thread_name}] Status: {status}")
    logger.info(f"[{main_thread_name}] Number of pages: {total_pages}")
    logger.info(f"[{main_thread_name}] Products collected: {total_products}")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Parsing interrupted by user (Ctrl+C)")
        # Сохраняем то, что уже собрано
        try:
            if os.path.exists(TEMP_CSV_FILE) and os.path.getsize(TEMP_CSV_FILE) > 0:
                logger.info("Saving collected data...")
                finalize_output_files()
                logger.info("Data saved successfully")
                TelegramNotifier.notify("[Trast] Update interrupted by user — Data saved")
            else:
                TelegramNotifier.notify("[Trast] Update interrupted by user — No data to save")
        except Exception as save_error:
            logger.error(f"Error saving data: {save_error}")
            TelegramNotifier.notify(f"[Trast] Update interrupted — <code>Save error: {save_error}</code>")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Critical error: {e}")
        logger.error(traceback.format_exc())
        TelegramNotifier.notify(f"[Trast] Update failed with critical error — <code>{str(e)}</code>")
        sys.exit(1)

