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
    MIN_DELAY_AFTER_LOAD, MAX_DELAY_AFTER_LOAD, LOG_DIR, PARSING_THREADS
)

# Добавляем обработчики логирования после импорта config
LOG_FILE = os.path.join(LOG_DIR, f"trast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logger.add(LOG_FILE, encoding='utf-8', rotation='10 MB', retention='7 days')
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
    safe_get_page_source, is_tab_crashed_error, PaginationNotDetectedError
)

# Импорт Telegram уведомлений
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from notification.main import TelegramNotifier
except ImportError:
    # Если модуль не найден, создаем заглушку
    class TelegramNotifier:
        @classmethod
        def notify(cls, text: str):
            logger.info(f"Telegram notification (not available): {text}")


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
    logger.info(f"[{thread_name}] Запущен поток скачивания прокси")
    
    try:
        # Первоначальная загрузка прокси
        logger.info(f"[{thread_name}] Начинаем скачивание прокси из всех источников...")
        if proxy_manager.download_proxies(force_update=True):
            # Загружаем скачанные прокси
            downloaded_proxies = proxy_manager._load_proxies()
            if downloaded_proxies:
                with proxies_lock:
                    proxies_list.clear()
                    proxies_list.extend(downloaded_proxies)
                    logger.info(f"[{thread_name}] Загружено {len(proxies_list)} прокси в общий список")
            else:
                logger.warning(f"[{thread_name}] Не удалось загрузить прокси из файла")
        else:
            logger.warning(f"[{thread_name}] Не удалось скачать прокси")
        
        # Периодическое обновление (каждые 30 минут)
        update_interval = 1800  # 30 минут
        last_update = time.time()
        
        while not stop_event.is_set():
            time.sleep(60)  # Проверяем каждую минуту
            
            # Проверяем, нужно ли обновить прокси
            if time.time() - last_update >= update_interval:
                logger.info(f"[{thread_name}] Периодическое обновление списка прокси...")
                try:
                    if proxy_manager.download_proxies(force_update=True):
                        downloaded_proxies = proxy_manager._load_proxies()
                        if downloaded_proxies:
                            with proxies_lock:
                                old_count = len(proxies_list)
                                proxies_list.clear()
                                proxies_list.extend(downloaded_proxies)
                                logger.info(f"[{thread_name}] Обновлен список прокси: {old_count} -> {len(proxies_list)}")
                        last_update = time.time()
                except Exception as e:
                    logger.warning(f"[{thread_name}] Ошибка при обновлении прокси: {e}")
    
    except Exception as e:
        logger.error(f"[{thread_name}] Критическая ошибка в потоке скачивания прокси: {e}")
        logger.debug(traceback.format_exc())
    
    logger.info(f"[{thread_name}] Поток скачивания прокси завершен")


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
        logger.warning("[MainThread] Рабочие прокси закончились, ищем новые...")
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
            logger.error("[MainThread] Не удалось найти новые рабочие прокси!")
            return None, None, {}
    
    # Создаем новый драйвер
    protocol = new_proxy.get('protocol', 'http').lower()
    use_chrome = protocol in ['http', 'https']
    
    logger.info(f"Пересоздаем драйвер с новым прокси {new_proxy['ip']}:{new_proxy['port']} ({protocol.upper()})...")
    new_driver = create_driver(new_proxy, use_chrome=use_chrome)
    
    if not new_driver:
        logger.warning(f"Не удалось создать драйвер с прокси {new_proxy['ip']}:{new_proxy['port']}")
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
    logger.info(f"[{thread_name}] === НАЧАЛО РАБОТЫ ПОТОКА {thread_id} ===")
    
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
    logger.info(f"[{thread_name}] Фаза 1: Поиск рабочего прокси...")
    proxy_index = thread_id  # Начинаем с thread_id (0 или 1), затем +2
    max_search_time = 1800  # Максимум 30 минут на поиск прокси
    search_start_time = time.time()
    last_list_size = 0
    consecutive_empty_checks = 0
    
    while True:
        # Проверяем таймаут
        if time.time() - search_start_time >= max_search_time:
            logger.error(f"[{thread_name}] Превышено время поиска прокси ({max_search_time}с), завершаем поток")
            return
        
        # Проверяем, есть ли уже total_pages от другого потока
        with total_pages_lock:
            if total_pages_shared.get('value') and total_pages_shared['value'] > 0:
                total_pages = total_pages_shared['value']
                logger.info(f"[{thread_name}] Используем total_pages={total_pages} от другого потока")
                break
        
        # Получаем прокси из списка
        with proxies_lock:
            current_list_size = len(proxies_list)
            if proxy_index >= current_list_size:
                # Если список не обновился после нескольких проверок - возможно, прокси закончились
                if current_list_size == last_list_size:
                    consecutive_empty_checks += 1
                    if consecutive_empty_checks >= 6:  # 30 секунд ожидания
                        logger.warning(f"[{thread_name}] Список прокси не обновляется, возможно все прокси проверены. Ожидаем обновления...")
                        consecutive_empty_checks = 0
                else:
                    consecutive_empty_checks = 0
                    last_list_size = current_list_size
                
                logger.debug(f"[{thread_name}] Достигнут конец списка прокси (индекс {proxy_index}, размер списка: {current_list_size}), ждем обновления...")
                time.sleep(5)
                continue
            
            consecutive_empty_checks = 0
            last_list_size = current_list_size
            proxy = proxies_list[proxy_index]
            proxy_index += 2  # Следующий прокси для этого потока (четный/нечетный)
        
        proxy_key = f"{proxy['ip']}:{proxy['port']}"
        logger.info(f"[{thread_name}] Проверка прокси {proxy_key} ({proxy.get('protocol', 'http').upper()})...")
        
        # Проверяем прокси
        try:
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
                        logger.info(f"[{thread_name}] ✓ Сохранен total_pages={total_pages} в общий словарь")
                
                logger.info(f"[{thread_name}] ✓ Найден рабочий прокси {proxy_key} с total_pages={total_pages}, переходим к парсингу")
                break
            else:
                logger.debug(f"[{thread_name}] Прокси {proxy_key} не работает, продолжаем поиск...")
        except Exception as e:
            logger.debug(f"[{thread_name}] Ошибка при проверке прокси {proxy_key}: {e}")
            continue
    
    if not total_pages or total_pages <= 0:
        logger.error(f"[{thread_name}] Не удалось получить total_pages, завершаем поток")
        return
    
    # Проверяем, что current_proxy установлен
    if not current_proxy:
        logger.error(f"[{thread_name}] current_proxy не установлен, завершаем поток")
        return
    
    # ФАЗА 2: Парсинг страниц
    logger.info(f"[{thread_name}] Фаза 2: Начинаем парсинг страниц (total_pages={total_pages})...")
    
    # Определяем какие страницы парсить: thread_id 0 = четные (2, 4, 6, ...), thread_id 1 = нечетные (1, 3, 5, ...)
    page_start = 2 - thread_id  # thread_id 0 -> страница 2 (четная), thread_id 1 -> страница 1 (нечетная)
    page_step = 2  # Шаг 2 для чередования
    current_page = page_start
    
    # Создаем драйвер для парсинга
    protocol = current_proxy.get('protocol', 'http').lower()
    use_chrome = protocol in ['http', 'https']
    
    logger.info(f"[{thread_name}] Создаем драйвер для парсинга...")
    driver = create_driver(current_proxy, use_chrome=use_chrome)
    
    if not driver:
        logger.error(f"[{thread_name}] Не удалось создать драйвер, завершаем поток")
        return
    
    # Получаем cookies
    try:
        driver.set_page_load_timeout(25)
        driver.get(TARGET_URL)
        time.sleep(5)
        
        page_source = safe_get_page_source(driver)
        if page_source:
            page_source_lower = page_source.lower()
            max_wait = 30
            wait_time = 0
            
            while page_source and ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or 
                   "just a moment" in page_source_lower) and wait_time < max_wait:
                logger.info(f"[{thread_name}] Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
                time.sleep(3)
                driver.refresh()
                time.sleep(2)
                page_source = safe_get_page_source(driver)
                if not page_source:
                    break
                page_source_lower = page_source.lower()
                wait_time += 5
            
            if page_source and wait_time < max_wait:
                try:
                    cookies = get_cookies_from_selenium(driver)
                    logger.info(f"[{thread_name}] Получены cookies: {len(cookies)} штук")
                except Exception as cookie_error:
                    logger.warning(f"[{thread_name}] Ошибка при получении cookies: {cookie_error}")
    except Exception as e:
        logger.warning(f"[{thread_name}] Ошибка при получении cookies: {e}")
    
    # Основной цикл парсинга
    while current_page <= total_pages:
        try:
            page_url = f"{TARGET_URL}?_paged={current_page}"
            logger.info(f"[{thread_name}] Парсинг страницы {current_page}/{total_pages} ({'четная' if current_page % 2 == 0 else 'нечетная'})...")
            
            # Периодически сохраняем буфер
            if local_buffer and len(local_buffer) >= 10:
                try:
                    with csv_lock:
                        append_to_csv(TEMP_CSV_FILE, local_buffer)
                    local_buffer.clear()
                except Exception as save_error:
                    logger.warning(f"[{thread_name}] Ошибка при сохранении буфера: {save_error}")
            
            # Пробуем через cloudscraper
            soup = None
            success = False
            
            if cookies:
                soup, success = parse_page_with_cloudscraper(page_url, cookies, current_proxy)
            
            # Fallback на Selenium
            if not success or not soup:
                if not driver:
                    # Пересоздаем драйвер
                    driver = create_driver(current_proxy, use_chrome=use_chrome)
                
                if driver:
                    try:
                        soup, success = parse_page_with_selenium(driver, page_url)
                        if success:
                            try:
                                cookies = get_cookies_from_selenium(driver)
                            except:
                                pass
                    except Exception as selenium_error:
                        if is_tab_crashed_error(selenium_error):
                            logger.error(f"[{thread_name}] [TAB CRASH] Краш вкладки, переходим к поиску нового прокси...")
                            driver = None
                            success = False
                        elif is_proxy_error(selenium_error):
                            logger.warning(f"[{thread_name}] [PROXY ERROR] Ошибка прокси, переходим к поиску нового прокси...")
                            driver = None
                            success = False
                        else:
                            logger.warning(f"[{thread_name}] Ошибка при парсинге через Selenium: {selenium_error}")
                            success = False
            
            if not success or not soup:
                # Переходим обратно к фазе поиска прокси
                logger.warning(f"[{thread_name}] Не удалось загрузить страницу {current_page}, ищем новый прокси...")
                proxy_switches += 1
                
                # Закрываем драйвер
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                # Ищем новый прокси (продолжаем с текущего индекса)
                found_new_proxy = False
                proxy_search_start = time.time()
                max_proxy_search_time = 300  # Максимум 5 минут на поиск нового прокси
                
                while not found_new_proxy:
                    if time.time() - proxy_search_start >= max_proxy_search_time:
                        logger.error(f"[{thread_name}] Превышено время поиска нового прокси ({max_proxy_search_time}с), завершаем поток")
                        break
                    
                    with proxies_lock:
                        if proxy_index >= len(proxies_list):
                            logger.debug(f"[{thread_name}] Достигнут конец списка прокси, ждем обновления...")
                            time.sleep(5)
                            continue
                        
                        proxy = proxies_list[proxy_index]
                        proxy_index += 2
                    
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    logger.info(f"[{thread_name}] Проверка нового прокси {proxy_key}...")
                    
                    try:
                        trast_ok, trast_info = proxy_manager.validate_proxy_for_trast(proxy)
                        if trast_ok and 'total_pages' in trast_info and trast_info['total_pages'] > 0:
                            current_proxy = proxy.copy()
                            current_proxy.update(trast_info)
                            driver = create_driver(current_proxy, use_chrome=(current_proxy.get('protocol', 'http').lower() in ['http', 'https']))
                            if driver:
                                found_new_proxy = True
                                logger.info(f"[{thread_name}] ✓ Найден новый рабочий прокси {proxy_key}, продолжаем парсинг со страницы {current_page}")
                                break
                    except Exception as e:
                        logger.debug(f"[{thread_name}] Ошибка при проверке прокси {proxy_key}: {e}")
                        continue
                
                if not found_new_proxy:
                    logger.error(f"[{thread_name}] Не удалось найти новый рабочий прокси, завершаем поток")
                    break
                
                # Продолжаем с той же страницы
                continue
            
            # Получаем page_source для проверки блокировки
            if driver:
                page_source = safe_get_page_source(driver)
            else:
                page_source = str(soup) if soup else ""
            
            if not page_source:
                logger.warning(f"[{thread_name}] Не удалось получить содержимое страницы {current_page}")
                current_page += page_step
                continue
            
            # Проверяем блокировку
            block_check = is_page_blocked(soup, page_source)
            
            if block_check["blocked"]:
                logger.warning(f"[{thread_name}] Страница {current_page} заблокирована: {block_check['reason']} → ищем новый прокси")
                cloudflare_blocks += 1
                proxy_switches += 1
                
                # Закрываем драйвер
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                # Ищем новый прокси
                found_new_proxy = False
                proxy_search_start = time.time()
                max_proxy_search_time = 300  # Максимум 5 минут на поиск нового прокси
                
                while not found_new_proxy:
                    if time.time() - proxy_search_start >= max_proxy_search_time:
                        logger.error(f"[{thread_name}] Превышено время поиска нового прокси ({max_proxy_search_time}с), завершаем поток")
                        break
                    
                    with proxies_lock:
                        if proxy_index >= len(proxies_list):
                            logger.debug(f"[{thread_name}] Достигнут конец списка прокси, ждем обновления...")
                            time.sleep(5)
                            continue
                        
                        proxy = proxies_list[proxy_index]
                        proxy_index += 2
                    
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    logger.info(f"[{thread_name}] Проверка нового прокси {proxy_key} после блокировки...")
                    
                    try:
                        trast_ok, trast_info = proxy_manager.validate_proxy_for_trast(proxy)
                        if trast_ok and 'total_pages' in trast_info and trast_info['total_pages'] > 0:
                            current_proxy = proxy.copy()
                            current_proxy.update(trast_info)
                            driver = create_driver(current_proxy, use_chrome=(current_proxy.get('protocol', 'http').lower() in ['http', 'https']))
                            if driver:
                                found_new_proxy = True
                                logger.info(f"[{thread_name}] ✓ Найден новый рабочий прокси {proxy_key}, продолжаем парсинг со страницы {current_page}")
                                break
                    except Exception as e:
                        logger.debug(f"[{thread_name}] Ошибка при проверке прокси {proxy_key}: {e}")
                        continue
                
                if not found_new_proxy:
                    logger.error(f"[{thread_name}] Не удалось найти новый рабочий прокси, завершаем поток")
                    break
                
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
                
                logger.info(f"[{thread_name}] Страница {current_page}: добавлено {len(products)} товаров (всего: {products_collected})")
                
                # Записываем буфер если заполнен
                if len(local_buffer) >= BUFFER_SIZE:
                    try:
                        with csv_lock:
                            append_to_csv(TEMP_CSV_FILE, local_buffer)
                        local_buffer.clear()
                    except Exception as save_error:
                        logger.warning(f"[{thread_name}] Ошибка при записи буфера: {save_error}")
                
            elif page_status["status"] == "empty":
                # Пустая страница = страница БЕЗ товаров В НАЛИЧИИ
                if products_in_stock == 0:
                    empty_pages_count += 1
                    logger.warning(f"[{thread_name}] Страница {current_page}: нет товаров В НАЛИЧИИ (пустых подряд: {empty_pages_count})")
                    
                    # Останавливаемся после 2 пустых страниц подряд
                    if empty_pages_count >= MAX_EMPTY_PAGES:
                        logger.info(f"[{thread_name}] Найдено {MAX_EMPTY_PAGES} страниц подряд без товаров В НАЛИЧИИ. Останавливаем парсинг.")
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
                logger.error(f"[{thread_name}] [TAB CRASH] Краш вкладки на странице {current_page}, ищем новый прокси...")
                proxy_switches += 1
                
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                # Ищем новый прокси
                found_new_proxy = False
                proxy_search_start = time.time()
                max_proxy_search_time = 300  # Максимум 5 минут на поиск нового прокси
                
                while not found_new_proxy:
                    if time.time() - proxy_search_start >= max_proxy_search_time:
                        logger.error(f"[{thread_name}] Превышено время поиска нового прокси ({max_proxy_search_time}с), завершаем поток")
                        break
                    
                    with proxies_lock:
                        if proxy_index >= len(proxies_list):
                            logger.debug(f"[{thread_name}] Достигнут конец списка прокси, ждем обновления...")
                            time.sleep(5)
                            continue
                        
                        proxy = proxies_list[proxy_index]
                        proxy_index += 2
                    
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    logger.info(f"[{thread_name}] Проверка нового прокси {proxy_key} после краша...")
                    
                    try:
                        trast_ok, trast_info = proxy_manager.validate_proxy_for_trast(proxy)
                        if trast_ok and 'total_pages' in trast_info and trast_info['total_pages'] > 0:
                            current_proxy = proxy.copy()
                            current_proxy.update(trast_info)
                            driver = create_driver(current_proxy, use_chrome=(current_proxy.get('protocol', 'http').lower() in ['http', 'https']))
                            if driver:
                                found_new_proxy = True
                                logger.info(f"[{thread_name}] ✓ Найден новый рабочий прокси {proxy_key}, продолжаем парсинг со страницы {current_page}")
                                break
                    except Exception as e2:
                        logger.debug(f"[{thread_name}] Ошибка при проверке прокси {proxy_key}: {e2}")
                        continue
                
                if not found_new_proxy:
                    logger.error(f"[{thread_name}] Не удалось найти новый рабочий прокси, завершаем поток")
                    break
                
                continue
            elif is_proxy_error(e):
                logger.warning(f"[{thread_name}] [PROXY ERROR] Ошибка прокси на странице {current_page}: {e}")
                # Ищем новый прокси (аналогично выше)
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                found_new_proxy = False
                proxy_search_start = time.time()
                max_proxy_search_time = 300  # Максимум 5 минут на поиск нового прокси
                
                while not found_new_proxy:
                    if time.time() - proxy_search_start >= max_proxy_search_time:
                        logger.error(f"[{thread_name}] Превышено время поиска нового прокси ({max_proxy_search_time}с), завершаем поток")
                        break
                    
                    with proxies_lock:
                        if proxy_index >= len(proxies_list):
                            logger.debug(f"[{thread_name}] Достигнут конец списка прокси, ждем обновления...")
                            time.sleep(5)
                            continue
                        
                        proxy = proxies_list[proxy_index]
                        proxy_index += 2
                    
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    logger.info(f"[{thread_name}] Проверка нового прокси {proxy_key} после ошибки прокси...")
                    
                    try:
                        trast_ok, trast_info = proxy_manager.validate_proxy_for_trast(proxy)
                        if trast_ok and 'total_pages' in trast_info and trast_info['total_pages'] > 0:
                            current_proxy = proxy.copy()
                            current_proxy.update(trast_info)
                            driver = create_driver(current_proxy, use_chrome=(current_proxy.get('protocol', 'http').lower() in ['http', 'https']))
                            if driver:
                                found_new_proxy = True
                                logger.info(f"[{thread_name}] ✓ Найден новый рабочий прокси {proxy_key}, продолжаем парсинг со страницы {current_page}")
                                break
                    except Exception as e2:
                        logger.debug(f"[{thread_name}] Ошибка при проверке прокси {proxy_key}: {e2}")
                        continue
                
                if not found_new_proxy:
                    logger.error(f"[{thread_name}] Не удалось найти новый рабочий прокси, завершаем поток")
                    break
                
                continue
            else:
                logger.error(f"[{thread_name}] Ошибка при парсинге страницы {current_page}: {e}")
                logger.debug(traceback.format_exc())
                current_page += page_step
                continue
    
    # Записываем оставшиеся товары из буфера
    if local_buffer:
        try:
            with csv_lock:
                append_to_csv(TEMP_CSV_FILE, local_buffer)
            logger.info(f"[{thread_name}] Записаны оставшиеся товары из буфера: {len(local_buffer)}")
            local_buffer.clear()
        except Exception as buffer_error:
            logger.error(f"[{thread_name}] Ошибка при записи оставшихся товаров: {buffer_error}")
    
    # Закрываем драйвер
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    logger.info(f"[{thread_name}] Парсинг завершен: собрано {products_collected} товаров, проверено {pages_parsed} страниц, переключений прокси: {proxy_switches}, блокировок: {cloudflare_blocks}")


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
        logger.info(f"[{thread_name}] Используем начальный прокси {initial_proxy['ip']}:{initial_proxy['port']} для начала парсинга")
        working_proxies = [initial_proxy]
        # В фоне ищем дополнительные прокси (но не блокируем парсинг)
        logger.info(f"[{thread_name}] Запускаем фоновый поиск дополнительных прокси (минимум {MIN_WORKING_PROXIES})...")
    else:
        # Получаем первый рабочий прокси (минимум 1 для начала)
        logger.info(f"[{thread_name}] Ищем рабочие прокси для парсинга...")
        working_proxies = proxy_manager.get_working_proxies(
            min_count=1,  # Начинаем с 1 прокси, не ждем 10
            max_to_check=MAX_PROXIES_TO_CHECK
        )
    
    if not working_proxies:
        logger.error(f"[{thread_name}] Не удалось найти рабочие прокси!")
        return 0, {"pages_checked": 0, "proxy_switches": 0, "cloudflare_blocks": 0}
    
    logger.info(f"[{thread_name}] Найдено {len(working_proxies)} рабочих прокси, начинаем парсинг")
    
    # Используем список для thread-safe доступа (если будет фоновый поиск)
    working_proxies_list = working_proxies.copy()  # Копируем в список для thread-safe доступа
    proxies_lock = None  # Будет создан, если нужен фоновый поиск
    
    if len(working_proxies_list) < MIN_WORKING_PROXIES:
        logger.info(f"[{thread_name}] У нас {len(working_proxies_list)} прокси, нужно {MIN_WORKING_PROXIES}. Запускаем фоновый поиск...")
        # Запускаем поиск в фоне, но не блокируем парсинг
        proxies_lock = threading.Lock()
        
        def background_proxy_search():
            bg_thread_name = "BackgroundProxySearch"
            logger.info(f"[{bg_thread_name}] Запущен фоновый поиск дополнительных прокси...")
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
                    logger.info(f"[{bg_thread_name}] Фоновый поиск завершен: добавлено {len(additional_proxies)} прокси (всего: {current_count})")
                else:
                    logger.warning(f"[{bg_thread_name}] Фоновый поиск не нашел дополнительных прокси")
            except Exception as e:
                logger.error(f"[{bg_thread_name}] Ошибка в фоновом поиске прокси: {e}")
        
        bg_thread = threading.Thread(target=background_proxy_search, daemon=True, name="BackgroundProxySearch")
        bg_thread.start()
        logger.info(f"[{thread_name}] Фоновый поиск прокси запущен, продолжаем парсинг с имеющимися прокси")
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
        logger.error(f"[{thread_name}] Нет рабочих прокси для получения cookies!")
        return 0, {"pages_checked": 0, "proxy_switches": 0, "cloudflare_blocks": 0}
    
    logger.info(f"[{thread_name}] Получаем cookies через прокси {current_proxy['ip']}:{current_proxy['port']}...")
    
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
            logger.info(f"[{thread_name}] Парсинг страницы {current_page}/{total_pages}...")
            
            # Периодически сохраняем буфер для защиты от потери данных
            if products_buffer and len(products_buffer) >= 10:
                try:
                    append_to_csv(TEMP_CSV_FILE, products_buffer)
                    products_buffer.clear()
                except Exception as save_error:
                    logger.warning(f"Ошибка при периодическом сохранении буфера: {save_error}")
            
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
                
                # Пересоздаем драйвер с новым прокси
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Не удалось пересоздать драйвер после ошибки загрузки!")
                    break
                
                logger.info(f"Драйвер пересоздан, продолжаем со страницы {current_page}")
                # Продолжаем с той же страницы (не увеличиваем current_page)
                continue
            
            # Проверяем блокировку
            # Для cloudscraper используем HTML из soup, для Selenium - из driver
            if driver:
                page_source = safe_get_page_source(driver)
                if not page_source:
                    # Краш вкладки при получении page_source - пересоздаем драйвер с новым прокси
                    logger.error(f"[TAB CRASH] Краш вкладки при получении page_source для страницы {current_page}, пересоздаем драйвер...")
                    proxy_switches += 1
                    
                    driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                        proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                    )
                    
                    if not driver or not current_proxy:
                        logger.error("Не удалось пересоздать драйвер после краша вкладки!")
                        break
                    
                    logger.info(f"[TAB CRASH] Драйвер пересоздан, продолжаем со страницы {current_page}")
                    # Продолжаем с той же страницы (не увеличиваем current_page)
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
                logger.warning(f"Страница {current_page} заблокирована: {block_check['reason']} → переключаем прокси")
                cloudflare_blocks += 1
                proxy_switches += 1
                
                # Пересоздаем драйвер с новым прокси
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Не удалось пересоздать драйвер с новым прокси!")
                    break
                
                logger.info(f"Драйвер пересоздан с новым прокси, продолжаем со страницы {current_page}")
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
                
                logger.info(f"Страница {current_page}: добавлено {len(products)} товаров (всего: {total_products})")
                
                # Записываем буфер если заполнен
                if len(products_buffer) >= BUFFER_SIZE:
                    append_to_csv(TEMP_CSV_FILE, products_buffer)
                    products_buffer.clear()
                    
            elif page_status["status"] == "empty":
                # Пустая страница = страница БЕЗ товаров В НАЛИЧИИ (но может быть структура каталога)
                # Увеличиваем счетчик только если действительно нет товаров в наличии
                if products_in_stock == 0:
                    empty_pages_count += 1
                    logger.warning(f"Страница {current_page}: нет товаров В НАЛИЧИИ (пустых подряд: {empty_pages_count})")
                    
                    # Останавливаемся после 2 пустых страниц подряд (без товаров в наличии)
                    if empty_pages_count >= MAX_EMPTY_PAGES:
                        logger.info(f"Найдено {MAX_EMPTY_PAGES} страниц подряд без товаров В НАЛИЧИИ. Останавливаем парсинг.")
                        break
                else:
                    # Если есть товары в наличии, но статус empty - это странно, сбрасываем счетчик
                    empty_pages_count = 0
                    
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
                            proxy_switches += 1
                            
                            driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                                proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                            )
                            
                            if not driver or not current_proxy:
                                logger.error("Не удалось пересоздать драйвер после краша вкладки при перезагрузке!")
                                break
                            
                            logger.info(f"[TAB CRASH] Драйвер пересоздан, продолжаем со страницы {current_page}")
                            # Продолжаем с той же страницы
                            continue
                        else:
                            logger.warning(f"Ошибка при перезагрузке частичной страницы: {reload_error}")
            
            elif page_status["status"] == "blocked":
                # Блокировка - получаем новый прокси
                logger.warning(f"Страница {current_page}: заблокирована (статус blocked) → переключаем прокси")
                cloudflare_blocks += 1
                proxy_switches += 1
                
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Не удалось пересоздать драйвер после блокировки!")
                    break
                
                logger.info(f"Драйвер пересоздан с новым прокси, продолжаем со страницы {current_page}")
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
                logger.error(f"[TAB CRASH] Обнаружен краш вкладки на странице {current_page}, пересоздаем драйвер...")
                proxy_switches += 1
                
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Не удалось пересоздать драйвер после краша вкладки!")
                    break
                
                logger.info(f"[TAB CRASH] Драйвер пересоздан, продолжаем со страницы {current_page}")
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
                            proxy_switches += 1
                            
                            driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                                proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                            )
                            
                            if not driver or not current_proxy:
                                logger.error("Не удалось пересоздать драйвер после краша вкладки при retry!")
                                break
                            
                            logger.info(f"[TAB CRASH] Драйвер пересоздан, продолжаем со страницы {current_page}")
                            # Продолжаем с той же страницы
                            continue
                
                # Если retry не помог - получаем новый прокси
                logger.info(f"Получаем новый прокси после ошибки прокси...")
                proxy_switches += 1
                
                driver, current_proxy, cookies = recreate_driver_with_new_proxy(
                    proxy_manager, current_proxy, working_proxies_list, driver, cookies, proxies_lock
                )
                
                if not driver or not current_proxy:
                    logger.error("Не удалось пересоздать драйвер после ошибки прокси!")
                    break
                
                logger.info(f"Драйвер пересоздан с новым прокси, продолжаем со страницы {current_page}")
                # Не увеличиваем current_page - попробуем еще раз с новым прокси
                continue
            else:
                logger.error(f"Ошибка при парсинге страницы {current_page}: {e}")
                logger.debug(traceback.format_exc())
                current_page += 1
                continue
    
    # Записываем оставшиеся товары из буфера
    if products_buffer:
        try:
            append_to_csv(TEMP_CSV_FILE, products_buffer)
            logger.info(f"Записаны оставшиеся товары из буфера: {len(products_buffer)}")
            products_buffer.clear()
        except Exception as buffer_error:
            logger.error(f"Ошибка при записи оставшихся товаров: {buffer_error}")
    
    # Закрываем драйвер
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    logger.info(f"Парсинг завершен: собрано {total_products} товаров, проверено {pages_checked} страниц")
    
    return total_products, {
        "pages_checked": pages_checked,
        "proxy_switches": proxy_switches,
        "cloudflare_blocks": cloudflare_blocks
    }


def main():
    """Главная функция с новой архитектурой: DownloadThread + 2 Worker потока"""
    main_thread_name = "MainThread"
    logger.info("=" * 80)
    logger.info("=== TRAST PARSER STARTED (NEW ARCHITECTURE) ===")
    logger.info(f"Target URL: {TARGET_URL}")
    logger.info(f"Start time: {datetime.now()}")
    logger.info("=" * 80)
    
    # Уведомление о старте
    TelegramNotifier.notify("[Trast] Update started")
    
    start_time = datetime.now()
    error_message = None
    
    try:
        # Создаем временный CSV файл
        create_new_csv(TEMP_CSV_FILE)
        logger.info(f"[{main_thread_name}] Создан временный CSV файл для записи данных")
    except Exception as e:
        logger.error(f"[{main_thread_name}] Ошибка при создании временных файлов: {e}")
        logger.error(traceback.format_exc())
        error_message = str(e)
        TelegramNotifier.notify(f"[Trast] Update failed — <code>{error_message}</code>")
        sys.exit(1)
    
    # Инициализируем прокси менеджер
    logger.info(f"[{main_thread_name}] Инициализация ProxyManager...")
    try:
        proxy_manager = ProxyManager(country_filter=PREFERRED_COUNTRIES)
        logger.info(f"[{main_thread_name}] ProxyManager инициализирован")
    except Exception as e:
        logger.error(f"[{main_thread_name}] Ошибка при инициализации ProxyManager: {e}")
        logger.error(traceback.format_exc())
        error_message = str(e)
        TelegramNotifier.notify(f"[Trast] Update failed — <code>{error_message}</code>")
        sys.exit(1)
    
    # Thread-safe структуры данных
    proxies_list = []  # Общий список прокси для проверки
    proxies_lock = threading.Lock()
    total_pages_shared = {'value': None}  # Общее количество страниц
    total_pages_lock = threading.Lock()
    csv_lock = threading.Lock()  # Lock для записи в CSV
    stop_event = threading.Event()  # Event для остановки потоков
    
    # Запускаем поток скачивания прокси
    logger.info(f"[{main_thread_name}] Запускаем поток скачивания прокси...")
    download_thread = threading.Thread(
        target=download_proxies_thread,
        args=(proxy_manager, proxies_list, proxies_lock, stop_event),
        daemon=False,
        name="DownloadThread"
    )
    download_thread.start()
    logger.info(f"[{main_thread_name}] ✓ Поток скачивания прокси запущен")
    
    # Ждем, пока загрузятся первые прокси (минимум 10)
    logger.info(f"[{main_thread_name}] Ожидаем загрузки прокси...")
    max_wait_time = 300  # Максимум 5 минут
    wait_start = time.time()
    
    while True:
        with proxies_lock:
            proxy_count = len(proxies_list)
        
        if proxy_count >= 10:
            logger.info(f"[{main_thread_name}] Загружено {proxy_count} прокси, запускаем worker потоки")
            break
        
        if time.time() - wait_start >= max_wait_time:
            logger.warning(f"[{main_thread_name}] Превышено время ожидания загрузки прокси ({max_wait_time}с), запускаем с {proxy_count} прокси")
            break
        
        time.sleep(2)
        if int(time.time() - wait_start) % 10 == 0:
            logger.info(f"[{main_thread_name}] Ожидание прокси... (загружено: {proxy_count}, прошло: {int(time.time() - wait_start)}с)")
    
    # Запускаем 2 worker потока
    logger.info(f"[{main_thread_name}] Запускаем 2 worker потока для парсинга...")
    worker_threads = []
    
    for thread_id in range(PARSING_THREADS):
        thread = threading.Thread(
            target=worker_thread,
            args=(thread_id, proxy_manager, proxies_list, proxies_lock, total_pages_shared, total_pages_lock, csv_lock),
            daemon=False,
            name=f"Worker-{thread_id}"
        )
        thread.start()
        worker_threads.append(thread)
        logger.info(f"[{main_thread_name}] ✓ Поток Worker-{thread_id} запущен ({'четные' if thread_id == 0 else 'нечетные'} страницы)")
        time.sleep(0.1)
    
    logger.info(f"[{main_thread_name}] Все потоки запущены, ожидаем завершения...")
    
    # Ждем завершения всех worker потоков
    for i, thread in enumerate(worker_threads):
        thread.join()
        logger.info(f"[{main_thread_name}] Поток Worker-{i} завершен")
    
    logger.info(f"[{main_thread_name}] Все worker потоки завершены")
    
    # Останавливаем поток скачивания прокси
    stop_event.set()
    download_thread.join(timeout=30)
    if download_thread.is_alive():
        logger.warning(f"[{main_thread_name}] Поток скачивания прокси не завершился за 30 секунд")
    else:
        logger.info(f"[{main_thread_name}] Поток скачивания прокси завершен")
    
    # Финализация
    duration = (datetime.now() - start_time).total_seconds()
    
    # Получаем total_pages для логирования
    with total_pages_lock:
        total_pages = total_pages_shared.get('value', 0)
    
    # Подсчитываем количество товаров из CSV файла
    total_products = 0
    try:
        if os.path.exists(TEMP_CSV_FILE) and os.path.getsize(TEMP_CSV_FILE) > 0:
            import csv
            with open(TEMP_CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                total_products = sum(1 for _ in reader)
    except Exception as count_error:
        logger.warning(f"[{main_thread_name}] Не удалось подсчитать товары: {count_error}")
    
    # Проверяем, есть ли данные для сохранения
    try:
        if os.path.exists(TEMP_CSV_FILE) and os.path.getsize(TEMP_CSV_FILE) > 0:
            file_size = os.path.getsize(TEMP_CSV_FILE)
            logger.info(f"[{main_thread_name}] Найдены данные для сохранения (размер файла: {file_size} байт)")
            finalize_output_files()
            logger.info(f"[{main_thread_name}] Данные сохранены успешно")
            status = 'done' if total_products >= 100 else 'insufficient_data'
        else:
            logger.warning(f"[{main_thread_name}] Нет данных для сохранения")
            cleanup_temp_files()
            status = 'insufficient_data'
    except Exception as save_error:
        logger.error(f"[{main_thread_name}] Ошибка при сохранении данных: {save_error}")
        error_message = error_message or str(save_error)
        status = 'error'
    
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
    
    logger.info("=" * 80)
    logger.info(f"[{main_thread_name}] Парсинг завершен!")
    logger.info(f"[{main_thread_name}] Время выполнения: {round(duration, 2)} секунд")
    logger.info(f"[{main_thread_name}] Статус: {status}")
    logger.info(f"[{main_thread_name}] Количество страниц: {total_pages}")
    logger.info(f"[{main_thread_name}] Товаров собрано: {total_products}")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Парсинг прерван пользователем (Ctrl+C)")
        # Сохраняем то, что уже собрано
        try:
            if os.path.exists(TEMP_CSV_FILE) and os.path.getsize(TEMP_CSV_FILE) > 0:
                logger.info("Сохраняем собранные данные...")
                finalize_output_files()
                logger.info("Данные сохранены успешно")
                TelegramNotifier.notify("[Trast] Update interrupted by user — Data saved")
            else:
                TelegramNotifier.notify("[Trast] Update interrupted by user — No data to save")
        except Exception as save_error:
            logger.error(f"Ошибка при сохранении данных: {save_error}")
            TelegramNotifier.notify(f"[Trast] Update interrupted — <code>Save error: {save_error}</code>")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
        TelegramNotifier.notify(f"[Trast] Update failed with critical error — <code>{str(e)}</code>")
        sys.exit(1)

