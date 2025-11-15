"""
Менеджер прокси для парсера trast-zapchast.ru
С поддержкой многопоточности для проверки прокси
"""
import os
import json
import re
import time
import random
import requests
import threading
import queue
import traceback
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup
from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import TimeoutException

from config import (
    PROXY_CACHE_DIR, PROXIES_FILE, SUCCESSFUL_PROXIES_FILE, LAST_UPDATE_FILE,
    PREFERRED_COUNTRIES, PROXY_SOURCES, PROXY_TEST_TIMEOUT, BASIC_CHECK_TIMEOUT,
    TARGET_URL, PROXY_CHECK_THREADS
)

from utils import create_driver, get_pages_count_with_driver, PaginationNotDetectedError


class ProxyManager:
    """Менеджер прокси с поддержкой многопоточности для проверки прокси"""
    
    def __init__(self, country_filter: Optional[List[str]] = None):
        """
        Инициализация ProxyManager
        
        Args:
            country_filter: Фильтр по странам (список кодов стран)
        """
        self.country_filter = [c.upper() for c in country_filter] if country_filter else PREFERRED_COUNTRIES
        self.failed_proxies = set()
        self.successful_proxies = []
        
        # Thread-safety: блокировка для доступа к критическим данным
        self.lock = threading.Lock()
        
        # Загружаем успешные прокси при инициализации
        self.successful_proxies = self.load_successful_proxies()
        if self.successful_proxies:
            logger.info(f"Загружено {len(self.successful_proxies)} успешных прокси из кэша")
        
        logger.info(f"ProxyManager инициализирован с фильтром стран: {', '.join(self.country_filter[:10])}...")
    
    def load_successful_proxies(self) -> List[Dict]:
        """Загружает успешные прокси из файла"""
        try:
            if os.path.exists(SUCCESSFUL_PROXIES_FILE):
                with open(SUCCESSFUL_PROXIES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Не удалось загрузить успешные прокси: {e}")
        return []
    
    def save_successful_proxies(self):
        """Сохраняет успешные прокси в файл"""
        try:
            with open(SUCCESSFUL_PROXIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.successful_proxies, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Не удалось сохранить успешные прокси: {e}")
    
    def _parse_proxymania_page(self, page_num: int = 1) -> List[Dict]:
        """Парсит одну страницу прокси с proxymania.su"""
        try:
            url = f"https://proxymania.su/free-proxy?page={page_num}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.select_one('table.table_proxychecker')
            if not table:
                return []
            
            rows = table.select('tbody#resultTable tr')
            proxies = []
            
            country_name_to_code = {
                'Russia': 'RU', 'Russian Federation': 'RU',
                'Poland': 'PL', 'Polska': 'PL',
                'Czech Republic': 'CZ', 'Czechia': 'CZ',
                'Germany': 'DE', 'Deutschland': 'DE',
                'Netherlands': 'NL', 'Holland': 'NL',
                'Sweden': 'SE', 'Sverige': 'SE',
                'France': 'FR',
                'Romania': 'RO', 'România': 'RO',
                'Bulgaria': 'BG', 'България': 'BG',
                'Belarus': 'BY', 'Беларусь': 'BY',
                'Ukraine': 'UA', 'Україна': 'UA',
                'Kazakhstan': 'KZ', 'Казахстан': 'KZ',
                'Moldova': 'MD', 'Молдова': 'MD',
                'Georgia': 'GE', 'საქართველო': 'GE',
                'Armenia': 'AM', 'Հայաստан': 'AM',
                'Azerbaijan': 'AZ', 'Azərbaycan': 'AZ',
                'Lithuania': 'LT', 'Lietuva': 'LT',
                'Latvia': 'LV', 'Latvija': 'LV',
                'Estonia': 'EE', 'Eesti': 'EE',
                'Finland': 'FI', 'Suomi': 'FI',
                'Slovakia': 'SK', 'Slovensko': 'SK',
                'Hungary': 'HU', 'Magyarország': 'HU',
                'China': 'CN', '中国': 'CN',
                'Mongolia': 'MN', 'Монгол': 'MN',
            }
            
            for row in rows:
                try:
                    cells = row.select('td')
                    if len(cells) < 5:
                        continue
                    
                    proxy_text = cells[0].get_text(strip=True)
                    if ':' not in proxy_text:
                        continue
                    
                    ip, port = proxy_text.split(':', 1)
                    country_name = cells[1].get_text(strip=True).strip()
                    country_code = country_name_to_code.get(country_name, country_name[:2].upper() if len(country_name) >= 2 else 'UN')
                    
                    protocol_text = cells[2].get_text(strip=True).upper()
                    protocol_map = {'SOCKS4': 'socks4', 'SOCKS5': 'socks5', 'HTTPS': 'https', 'HTTP': 'http'}
                    protocol = protocol_map.get(protocol_text, protocol_text.lower())
                    
                    if protocol not in ['http', 'https', 'socks4', 'socks5']:
                        continue
                    
                    if self.country_filter and country_code not in self.country_filter:
                        continue
                    
                    proxies.append({
                        'ip': ip,
                        'port': port,
                        'protocol': protocol,
                        'country': country_code,
                        'source': 'proxymania'
                    })
                except Exception:
                    continue
            
            return proxies
        except Exception as e:
            logger.warning(f"Ошибка при парсинге страницы {page_num} proxymania.su: {e}")
            return []
    
    def _download_proxies_from_proxymania(self) -> List[Dict]:
        """Парсит все страницы прокси с proxymania.su"""
        all_proxies = []
        max_pages = 15
        
        logger.info("Парсинг прокси с proxymania.su...")
        for page_num in range(1, max_pages + 1):
            proxies = self._parse_proxymania_page(page_num)
            if not proxies:
                break
            all_proxies.extend(proxies)
            logger.info(f"Страница {page_num}: найдено {len(proxies)} прокси")
            time.sleep(1)  # Задержка между страницами
        
        logger.info(f"Всего получено {len(all_proxies)} прокси с proxymania.su")
        return all_proxies
    
    def _download_proxies_from_proxifly(self) -> List[Dict]:
        """Загружает прокси с Proxifly"""
        try:
            logger.info("Загрузка прокси с Proxifly...")
            url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            proxies_data = response.json()
            
            proxies = []
            for proxy in proxies_data:
                protocol = proxy.get('protocol', '').lower()
                geolocation = proxy.get('geolocation', {})
                country = (geolocation.get('country', '') or proxy.get('country', '')).upper()
                
                if self.country_filter and country not in self.country_filter:
                    continue
                
                if protocol not in ['http', 'https', 'socks4', 'socks5']:
                    continue
                
                port = proxy.get('port', '')
                if isinstance(port, int):
                    port = str(port)
                
                proxies.append({
                    'ip': proxy.get('ip', ''),
                    'port': port,
                    'protocol': protocol,
                    'country': country,
                    'source': 'proxifly'
                })
            
            logger.info(f"Получено {len(proxies)} прокси с Proxifly")
            return proxies
        except Exception as e:
            logger.warning(f"Ошибка при загрузке прокси с Proxifly: {e}")
            return []
    
    def _download_proxies_from_proxyscrape(self) -> List[Dict]:
        """Загружает прокси с ProxyScrape API"""
        try:
            logger.info("Загрузка прокси с ProxyScrape...")
            # Получаем HTTP прокси
            url_http = "https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
            # Получаем SOCKS4 прокси
            url_socks4 = "https://api.proxyscrape.com/v2/?request=get&protocol=socks4&timeout=10000&country=all"
            # Получаем SOCKS5 прокси
            url_socks5 = "https://api.proxyscrape.com/v2/?request=get&protocol=socks5&timeout=10000&country=all"
            
            proxies = []
            
            # Загружаем HTTP/HTTPS прокси
            try:
                response = requests.get(url_http, timeout=30)
                response.raise_for_status()
                text = response.text.strip()
                if text:
                    for line in text.split('\n'):
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        try:
                            ip, port = line.split(':', 1)
                            # HTTP прокси могут использоваться как HTTP и HTTPS
                            for protocol in ['http', 'https']:
                                proxies.append({
                                    'ip': ip.strip(),
                                    'port': port.strip(),
                                    'protocol': protocol,
                                    'country': '',  # ProxyScrape не предоставляет страну в этом формате
                                    'source': 'proxyscrape'
                                })
                        except ValueError:
                            continue
            except Exception as e:
                logger.debug(f"Ошибка при загрузке HTTP прокси с ProxyScrape: {e}")
            
            # Загружаем SOCKS4 прокси
            try:
                response = requests.get(url_socks4, timeout=30)
                response.raise_for_status()
                text = response.text.strip()
                if text:
                    for line in text.split('\n'):
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        try:
                            ip, port = line.split(':', 1)
                            proxies.append({
                                'ip': ip.strip(),
                                'port': port.strip(),
                                'protocol': 'socks4',
                                'country': '',
                                'source': 'proxyscrape'
                            })
                        except ValueError:
                            continue
            except Exception as e:
                logger.debug(f"Ошибка при загрузке SOCKS4 прокси с ProxyScrape: {e}")
            
            # Загружаем SOCKS5 прокси
            try:
                response = requests.get(url_socks5, timeout=30)
                response.raise_for_status()
                text = response.text.strip()
                if text:
                    for line in text.split('\n'):
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        try:
                            ip, port = line.split(':', 1)
                            proxies.append({
                                'ip': ip.strip(),
                                'port': port.strip(),
                                'protocol': 'socks5',
                                'country': '',
                                'source': 'proxyscrape'
                            })
                        except ValueError:
                            continue
            except Exception as e:
                logger.debug(f"Ошибка при загрузке SOCKS5 прокси с ProxyScrape: {e}")
            
            # Фильтруем по странам (если указан фильтр, но ProxyScrape не предоставляет страну, пропускаем фильтрацию)
            if self.country_filter:
                # Оставляем только прокси без указания страны или те, которые могут быть из нужных стран
                # Так как ProxyScrape не предоставляет страну, оставляем все
                pass
            
            logger.info(f"Получено {len(proxies)} прокси с ProxyScrape")
            return proxies
        except Exception as e:
            logger.warning(f"Ошибка при загрузке прокси с ProxyScrape: {e}")
            return []
    
    def download_proxies(self, force_update: bool = False) -> bool:
        """Скачивает свежие прокси из всех источников"""
        try:
            if force_update:
                logger.info("Принудительное обновление списка прокси...")
            
            all_proxies = []
            
            # Загружаем с proxymania
            if PROXY_SOURCES['proxymania']['active']:
                proxymania_proxies = self._download_proxies_from_proxymania()
                all_proxies.extend(proxymania_proxies)
            
            # Загружаем с proxifly
            if PROXY_SOURCES['proxifly']['active']:
                proxifly_proxies = self._download_proxies_from_proxifly()
                all_proxies.extend(proxifly_proxies)
            
            # Загружаем с proxyscrape
            if PROXY_SOURCES.get('proxyscrape', {}).get('active', False):
                proxyscrape_proxies = self._download_proxies_from_proxyscrape()
                all_proxies.extend(proxyscrape_proxies)
            
            # Удаляем дубликаты
            seen = set()
            filtered_proxies = []
            for proxy in all_proxies:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in seen:
                    seen.add(proxy_key)
                    filtered_proxies.append(proxy)
            
            logger.info(f"После удаления дубликатов: {len(filtered_proxies)} уникальных прокси")
            
            # Сохраняем прокси
            with open(PROXIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(filtered_proxies, f, ensure_ascii=False, indent=2)
            
            with open(LAST_UPDATE_FILE, 'w', encoding='utf-8') as f:
                f.write(datetime.now().isoformat())
            
            logger.info(f"Сохранено {len(filtered_proxies)} прокси в файл: {PROXIES_FILE}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке прокси: {e}")
            return False
    
    def _load_proxies(self) -> List[Dict]:
        """Загружает прокси из файла"""
        try:
            if os.path.exists(PROXIES_FILE):
                with open(PROXIES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Не удалось загрузить прокси: {e}")
        return []
    
    def validate_proxy_basic(self, proxy: Dict, timeout: int = None) -> Tuple[bool, Dict]:
        """Базовая проверка работоспособности прокси через ifconfig.me/ip"""
        if timeout is None:
            timeout = BASIC_CHECK_TIMEOUT
        
        try:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            if protocol in ['http', 'https']:
                proxy_url = f"{protocol}://{ip}:{port}"
                proxies = {'http': proxy_url, 'https': proxy_url}
            elif protocol in ['socks4', 'socks5']:
                proxy_url = f"socks5h://{ip}:{port}" if protocol == 'socks5' else f"socks4://{ip}:{port}"
                proxies = {'http': proxy_url, 'https': proxy_url}
            else:
                return False, {}
            
            response = requests.get('https://ifconfig.me/ip', proxies=proxies, timeout=timeout, verify=False)
            if response.status_code == 200:
                external_ip = response.text.strip()
                if external_ip and len(external_ip.split('.')) == 4:
                    logger.info(f"Прокси {ip}:{port} ({protocol.upper()}) работает! IP: {external_ip}")
                    return True, {
                        'ip': ip, 'port': port, 'protocol': protocol,
                        'external_ip': external_ip, 'proxies': proxies
                    }
            
            return False, {}
        except Exception as e:
            logger.debug(f"Прокси {proxy.get('ip', '')}:{proxy.get('port', '')} не работает: {e}")
            return False, {}
    
    def validate_proxy_for_trast(self, proxy: Dict, timeout: int = None) -> Tuple[bool, Dict]:
        """Проверяет прокси на доступность trast-zapchast.ru через Selenium"""
        if timeout is None:
            timeout = PROXY_TEST_TIMEOUT
        
        driver = None
        try:
            logger.info(f"Проверка прокси {proxy['ip']}:{proxy['port']} на trast-zapchast.ru...")
            
            protocol = proxy.get('protocol', 'http').lower()
            use_chrome = protocol in ['http', 'https']
            
            driver = create_driver(proxy, use_chrome=use_chrome)
            if not driver:
                return False, {}
            
            driver.set_page_load_timeout(timeout)
            driver.get(TARGET_URL)
            time.sleep(5)  # Ожидание загрузки
            
            # Проверяем Cloudflare
            page_source_lower = driver.page_source.lower()
            max_wait = 30
            wait_time = 0
            
            while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or 
                   "just a moment" in page_source_lower) and wait_time < max_wait:
                logger.info(f"Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
                time.sleep(3)
                driver.refresh()
                time.sleep(2)
                page_source_lower = driver.page_source.lower()
                wait_time += 5
            
            if wait_time >= max_wait:
                logger.warning("Cloudflare проверка не пройдена")
                return False, {}
            
            # Пробуем получить количество страниц - это ОСНОВНОЙ критерий работоспособности прокси
            try:
                total_pages = get_pages_count_with_driver(driver)
                if total_pages and total_pages > 0:
                    logger.info(f"✓ Прокси работает! Успешно получено количество страниц: {total_pages}")
                    return True, {'total_pages': total_pages}
                else:
                    logger.warning(f"Прокси не смог получить количество страниц (вернул {total_pages})")
                    return False, {}
            except PaginationNotDetectedError as e:
                # Страница заблокирована - прокси не работает
                logger.warning(f"Прокси заблокирован на сайте: {e}")
                return False, {}
            except Exception as e:
                logger.warning(f"Ошибка при получении количества страниц через прокси: {e}")
                return False, {}
            
        except Exception as e:
            logger.debug(f"Ошибка при проверке прокси на trast: {e}")
            return False, {}
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def _proxy_search_worker(self, thread_id: int, proxy_queue: queue.Queue, found_proxies: List[Dict], 
                             stop_event: threading.Event, stats: Dict, min_count: int):
        """Worker функция для многопоточного поиска прокси
        
        Args:
            thread_id: ID потока
            proxy_queue: Очередь прокси для проверки
            found_proxies: Список найденных прокси (thread-safe через lock)
            stop_event: Event для остановки поиска
            stats: Статистика поиска (thread-safe через lock)
            min_count: Минимальное количество прокси для поиска
        """
        thread_name = f"ProxySearch-{thread_id}"
        checked_count = 0
        failed_count = 0
        
        logger.info(f"[{thread_name}] Поток поиска прокси запущен")
        
        while not stop_event.is_set():
            try:
                # Получаем прокси из очереди с таймаутом
                try:
                    proxy = proxy_queue.get(timeout=1)
                except queue.Empty:
                    # Очередь пуста - завершаем поток
                    logger.info(f"[{thread_name}] Очередь прокси пуста, завершаем поток (проверено: {checked_count}, неуспешных: {failed_count})")
                    break
                
                checked_count += 1
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                
                # Проверяем, не нашли ли уже достаточно прокси
                with self.lock:
                    if len(found_proxies) >= min_count:
                        stop_event.set()
                        proxy_queue.task_done()
                        break
                
                logger.info(f"[{thread_name}] Проверка прокси {proxy_key} ({proxy.get('protocol', 'http').upper()})...")
                
                # Базовая проверка
                basic_ok, basic_info = self.validate_proxy_basic(proxy)
                if not basic_ok:
                    with self.lock:
                        self.failed_proxies.add(proxy_key)
                        stats['failed'] += 1
                    proxy_queue.task_done()
                    failed_count += 1
                    continue
                
                # Проверка на trast
                trast_ok, trast_info = self.validate_proxy_for_trast(proxy)
                if trast_ok:
                    working_proxy = {
                        'ip': proxy['ip'],
                        'port': proxy['port'],
                        'protocol': proxy['protocol'],
                        'country': proxy.get('country', ''),
                        'source': proxy.get('source', 'unknown')
                    }
                    working_proxy.update(trast_info)
                    
                    # Thread-safe добавление
                    with self.lock:
                        # Проверяем, не добавили ли уже этот прокси другой поток
                        existing_keys = {f"{p['ip']}:{p['port']}" for p in found_proxies}
                        if proxy_key not in existing_keys:
                            found_proxies.append(working_proxy)
                            self.successful_proxies.append(working_proxy)
                            stats['found'] += 1
                            current_count = len(found_proxies)
                            
                            logger.success(f"[{thread_name}] ✓ Найден рабочий прокси: {proxy_key} ({current_count}/{min_count})")
                            
                            # Если нашли достаточно - сигнализируем остановку
                            if current_count >= min_count:
                                stop_event.set()
                else:
                    with self.lock:
                        self.failed_proxies.add(proxy_key)
                        stats['failed'] += 1
                    failed_count += 1
                
                # Обновляем общую статистику
                with self.lock:
                    stats['checked'] += 1
                
                proxy_queue.task_done()
                
                # Выводим статистику каждые 10 прокси
                if checked_count % 10 == 0:
                    with self.lock:
                        total_checked = stats['checked']
                        total_found = stats['found']
                        total_failed = stats['failed']
                    logger.info(f"[{thread_name}] Проверено {checked_count} прокси (всего по всем потокам: проверено {total_checked}, найдено {total_found}, неуспешных {total_failed})")
                
            except KeyboardInterrupt:
                logger.warning(f"[{thread_name}] Получен сигнал прерывания, завершаем поток")
                stop_event.set()
                break
            except Exception as e:
                logger.error(f"[{thread_name}] Ошибка при проверке прокси: {e}")
                logger.debug(f"[{thread_name}] Traceback: {traceback.format_exc()}")
                try:
                    proxy_queue.task_done()
                except:
                    pass
                continue
        
        logger.info(f"[{thread_name}] Поток поиска прокси завершен (проверено: {checked_count}, неуспешных: {failed_count})")
    
    def get_working_proxies(self, min_count: int = 10, max_to_check: Optional[int] = 100, 
                           use_parallel: bool = True, num_threads: Optional[int] = None) -> List[Dict]:
        """
        Получает рабочие прокси (с поддержкой многопоточности)
        
        Args:
            min_count: Минимальное количество рабочих прокси для поиска
            max_to_check: Максимальное количество прокси для проверки (None = проверять все доступные)
            use_parallel: Использовать многопоточность (по умолчанию True)
            num_threads: Количество потоков для проверки (None = из конфига PROXY_CHECK_THREADS)
            
        Returns:
            Список рабочих прокси
        """
        if num_threads is None:
            num_threads = PROXY_CHECK_THREADS
        
        # Загружаем прокси
        proxies = self._load_proxies()
        if not proxies:
            logger.warning("Нет прокси для проверки, загружаем...")
            if not self.download_proxies(force_update=True):
                return []
            proxies = self._load_proxies()
        
        working_proxies = []
        
        # ШАГ 1: Сначала проверяем старые успешные прокси (быстро, последовательно)
        with self.lock:
            shuffled_successful = self.successful_proxies.copy()
        
        if shuffled_successful:
            logger.info(f"Проверяем {len(shuffled_successful)} старых успешных прокси (приоритет)...")
            random.shuffle(shuffled_successful)
            
            for proxy in shuffled_successful:
                if len(working_proxies) >= min_count:
                    break
                
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                logger.info(f"Проверяем старый успешный прокси: {proxy_key} ({proxy.get('protocol', 'http').upper()})")
                
                # Быстрая проверка на trast (без базовой проверки, т.к. уже был успешным)
                trast_ok, trast_info = self.validate_proxy_for_trast(proxy)
                if trast_ok:
                    logger.info(f"[OK] Старый успешный прокси работает: {proxy_key}")
                    working_proxy = {
                        'ip': proxy['ip'],
                        'port': proxy['port'],
                        'protocol': proxy['protocol'],
                        'country': proxy.get('country', ''),
                        'source': proxy.get('source', 'unknown')
                    }
                    working_proxy.update(trast_info)
                    working_proxies.append(working_proxy)
                else:
                    logger.warning(f"Старый прокси {proxy_key} перестал работать")
                    with self.lock:
                        # Удаляем из успешных
                        self.successful_proxies = [p for p in self.successful_proxies 
                                                   if f"{p['ip']}:{p['port']}" != proxy_key]
                        self.failed_proxies.add(proxy_key)
        
        # Если нашли достаточно старых прокси, возвращаем их
        if len(working_proxies) >= min_count:
            logger.info(f"Найдено достаточно старых успешных прокси: {len(working_proxies)}")
            self.save_successful_proxies()
            return working_proxies[:min_count]
        
        # ШАГ 2: Многопоточный поиск новых прокси (если нужно)
        logger.info(f"Старых успешных прокси недостаточно ({len(working_proxies)}/{min_count}), запускаем поиск новых...")
        
        # Фильтруем уже проверенные
        with self.lock:
            successful_keys = {f"{p['ip']}:{p['port']}" for p in self.successful_proxies}
            failed_keys = self.failed_proxies.copy()
        
        proxies_to_check = []
        for proxy in proxies:
            proxy_key = f"{proxy['ip']}:{proxy['port']}"
            if proxy_key not in successful_keys and proxy_key not in failed_keys:
                proxies_to_check.append(proxy)
        
        # Применяем ограничение max_to_check только если оно указано
        if max_to_check is not None and len(proxies_to_check) > max_to_check:
            proxies_to_check = proxies_to_check[:max_to_check]
            logger.info(f"Ограничение: проверяем первые {max_to_check} из {len(proxies_to_check) + len(successful_keys) + len(failed_keys)} доступных прокси")
        else:
            logger.info(f"Проверяем все доступные прокси: {len(proxies_to_check)} (успешных: {len(successful_keys)}, неудачных: {len(failed_keys)})")
        
        if not proxies_to_check:
            logger.warning("Нет новых прокси для проверки")
            self.save_successful_proxies()
            return working_proxies
        
        random.shuffle(proxies_to_check)
        
        if use_parallel and num_threads > 1:
            # Многопоточная проверка
            logger.info(f"Запускаем многопоточный поиск в {num_threads} потоках...")
            
            stop_event = threading.Event()
            stats = {'checked': 0, 'found': 0, 'failed': 0}
            
            # Создаем очередь прокси
            proxy_queue = queue.Queue()
            for proxy in proxies_to_check:
                proxy_queue.put(proxy)
            
            # Запускаем потоки
            threads = []
            for thread_id in range(num_threads):
                thread = threading.Thread(
                    target=self._proxy_search_worker,
                    args=(thread_id, proxy_queue, working_proxies, stop_event, stats, min_count),
                    daemon=False,
                    name=f"ProxySearch-{thread_id}"
                )
                thread.start()
                threads.append(thread)
                logger.info(f"Запущен поток поиска прокси {thread_id}")
            
            # Ждем завершения всех потоков (с таймаутом для безопасности)
            for i, thread in enumerate(threads):
                thread.join(timeout=300)  # Максимум 5 минут на поток
                if thread.is_alive():
                    logger.warning(f"Поток {i} не завершился за 5 минут, возможно завис")
                else:
                    logger.debug(f"Поток {i} успешно завершен")
            
            logger.info(f"Многопоточный поиск завершен: найдено {len(working_proxies)} прокси (проверено: {stats['checked']}, неуспешных: {stats['failed']})")
        else:
            # Последовательная проверка (fallback)
            logger.info("Последовательная проверка прокси...")
            
            for i, proxy in enumerate(proxies_to_check, 1):
                # Если уже нашли нужное количество - останавливаемся
                if len(working_proxies) >= min_count:
                    logger.info(f"Найдено достаточно рабочих прокси ({len(working_proxies)}/{min_count}), останавливаем проверку")
                    break
                
                logger.info(f"[{i}/{len(proxies_to_check)}] Проверка прокси {proxy['ip']}:{proxy['port']}...")
                
                # Базовая проверка
                basic_ok, basic_info = self.validate_proxy_basic(proxy)
                if not basic_ok:
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    with self.lock:
                        self.failed_proxies.add(proxy_key)
                    continue
                
                # Проверка на trast
                trast_ok, trast_info = self.validate_proxy_for_trast(proxy)
                if trast_ok:
                    working_proxy = {
                        'ip': proxy['ip'],
                        'port': proxy['port'],
                        'protocol': proxy['protocol'],
                        'country': proxy.get('country', ''),
                        'source': proxy.get('source', 'unknown')
                    }
                    working_proxy.update(trast_info)
                    working_proxies.append(working_proxy)
                    with self.lock:
                        self.successful_proxies.append(working_proxy)
                    logger.success(f"✓ Найден рабочий прокси: {proxy['ip']}:{proxy['port']} ({len(working_proxies)}/{min_count})")
                else:
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    with self.lock:
                        self.failed_proxies.add(proxy_key)
        
        # Сохраняем успешные прокси
        self.save_successful_proxies()
        
        logger.info(f"Всего найдено {len(working_proxies)} рабочих прокси")
        return working_proxies[:min_count] if len(working_proxies) > min_count else working_proxies
    
    def get_next_proxy(self) -> Optional[Dict]:
        """Получает следующий рабочий прокси из списка"""
        if not self.successful_proxies:
            return None
        
        # Простая ротация
        proxy = self.successful_proxies[0]
        self.successful_proxies = self.successful_proxies[1:] + [proxy]
        return proxy

