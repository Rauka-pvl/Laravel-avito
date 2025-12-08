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
    PROXY_CACHE_DIR,
    PROXIES_FILE,
    SUCCESSFUL_PROXIES_FILE,
    LAST_UPDATE_FILE,
    PREFERRED_COUNTRIES,
    PROXY_SOURCES,
    PROXY_TEST_TIMEOUT,
    BASIC_CHECK_TIMEOUT,
    TARGET_URL,
    PROXY_CHECK_THREADS,
    USE_UNDETECTED_CHROME,
    FORCE_FIREFOX,
    BROWSER_RETRY_DELAY,
)

from utils import create_driver, get_pages_count_with_driver, PaginationNotDetectedError


def is_proxy_connection_error(error: Exception) -> bool:
    """Определяет, относится ли ошибка Selenium к проблемам подключения через прокси."""
    if not error:
        return False
    message = str(error).lower()
    keywords = [
        "err_proxy_connection_failed",
        "err_tunnel_connection_failed",
        "connectionfailure",
        "connection failed",
        "could not establish connection",
    ]
    return any(keyword in message for keyword in keywords)


def filter_proxies_by_country(proxies: List[Dict], country_filter: Optional[List[str]]) -> List[Dict]:
    """
    Фильтрует прокси по странам СНГ.
    
    Args:
        proxies: Список прокси для фильтрации
        country_filter: Список кодов стран для фильтрации (например, ['RU', 'BY', 'KZ'])
        
    Returns:
        Отфильтрованный список прокси
    """
    if not country_filter:
        return proxies
    
    country_filter_upper = [c.upper() for c in country_filter]
    filtered = []
    
    for proxy in proxies:
        country = proxy.get('country', '').upper()
        # Если страна указана и не в фильтре - пропускаем
        if country and country not in country_filter_upper:
            continue
        # Если страна не указана - оставляем (может быть определена позже)
        filtered.append(proxy)
    
    return filtered


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
        self.priority_proxies = []  # Приоритетные прокси из proxies_credentials.json или proxies_data.json
        
        # Thread-safety: блокировка для доступа к критическим данным
        self.lock = threading.Lock()
        
        # Загружаем приоритетные прокси (сначала из proxies_credentials.json, затем из proxies_data.json)
        self.priority_proxies = self.load_priority_proxies()
        if self.priority_proxies:
            logger.info(f"Loaded {len(self.priority_proxies)} priority proxies")
        
        # Загружаем успешные прокси при инициализации (с автоматической очисткой устаревших)
        from config import SUCCESSFUL_PROXY_TTL_HOURS
        self.successful_proxies = self.load_successful_proxies(max_age_hours=SUCCESSFUL_PROXY_TTL_HOURS)
        if self.successful_proxies:
            logger.info(f"Loaded {len(self.successful_proxies)} successful proxies from cache (TTL: {SUCCESSFUL_PROXY_TTL_HOURS}h)")
        
        logger.info(f"ProxyManager initialized with country filter: {', '.join(self.country_filter[:10])}...")
    
    def load_priority_proxies(self) -> List[Dict]:
        """
        Загружает приоритетные прокси из proxies_credentials.json или proxies_data.json.
        Сначала пробует proxies_credentials.json, затем proxies_data.json.
        """
        priority_proxies = []
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Список файлов для проверки (в порядке приоритета)
        proxy_files = [
            ('proxies_credentials.json', 'credentials'),
            ('proxies_data.json', 'hardcoded_proxies.proxies')
        ]
        
        for filename, data_path in proxy_files:
            try:
                file_path = os.path.join(base_dir, filename)
                
                if not os.path.exists(file_path):
                    logger.debug(f"Priority proxies file not found: {file_path}, trying next...")
                    continue
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Извлекаем прокси в зависимости от структуры файла
                if data_path == 'credentials':
                    # Формат proxies_credentials.json: data['credentials']
                    proxy_list = data.get('credentials', [])
                else:
                    # Формат proxies_data.json: data['hardcoded_proxies']['proxies']
                    parts = data_path.split('.')
                    proxy_list = data
                    for part in parts:
                        proxy_list = proxy_list.get(part, [])
                        if not proxy_list:
                            break
                
                if not proxy_list:
                    logger.debug(f"No proxies found in {filename}, trying next file...")
                    continue
                
                # Парсим прокси
                for proxy_data in proxy_list:
                    try:
                        host = proxy_data.get('host', '')
                        port = str(proxy_data.get('port', ''))
                        protocol_raw = proxy_data.get('protocol', 'HTTPS').upper()
                        auth = proxy_data.get('authentication', {})
                        
                        if not host or not port:
                            logger.debug(f"Skipping invalid proxy entry: missing host or port")
                            continue
                        
                        # Преобразуем протокол: HTTPS -> https, PROXY -> http (или https для порта 443)
                        if protocol_raw == 'HTTPS' or port == '443':
                            protocol = 'https'
                        else:
                            protocol = 'http'
                        
                        proxy_dict = {
                            'ip': host,
                            'port': port,
                            'protocol': protocol,
                            'source': f'priority_{filename}',
                            'country': ''  # Страна не указана в данных
                        }
                        
                        # Добавляем аутентификацию, если есть
                        if auth.get('required', False):
                            login = auth.get('login', '')
                            password = auth.get('password', '')
                            if login and password:
                                proxy_dict['login'] = login
                                proxy_dict['password'] = password
                                logger.debug(f"Loaded priority proxy with auth: {host}:{port} ({protocol})")
                            else:
                                logger.debug(f"Loaded priority proxy: {host}:{port} ({protocol})")
                        else:
                            logger.debug(f"Loaded priority proxy: {host}:{port} ({protocol})")
                        
                        priority_proxies.append(proxy_dict)
                        
                    except Exception as e:
                        logger.warning(f"Error parsing priority proxy from {filename}: {e}")
                        continue
                
                if priority_proxies:
                    logger.info(f"Successfully loaded {len(priority_proxies)} priority proxies from {filename}")
                    break  # Успешно загрузили из первого доступного файла
                else:
                    logger.debug(f"No valid proxies found in {filename}, trying next file...")
                    
            except FileNotFoundError:
                logger.debug(f"{filename} not found, trying next file...")
                continue
            except json.JSONDecodeError as e:
                logger.warning(f"Error parsing {filename}: {e}, trying next file...")
                continue
            except Exception as e:
                logger.warning(f"Error loading priority proxies from {filename}: {e}, trying next file...")
                continue
        
        if not priority_proxies:
            logger.debug("No priority proxies loaded from any source file")
        
        return priority_proxies
    
    def load_successful_proxies(self, max_age_hours: int = 24) -> List[Dict]:
        """
        Загружает успешные прокси из файла и удаляет устаревшие (старше max_age_hours).
        
        Args:
            max_age_hours: Максимальный возраст прокси в часах (по умолчанию 24 часа)
            
        Returns:
            Список актуальных успешных прокси
        """
        try:
            if os.path.exists(SUCCESSFUL_PROXIES_FILE):
                with open(SUCCESSFUL_PROXIES_FILE, 'r', encoding='utf-8') as f:
                    proxies = json.load(f)
                    
                    # Фильтруем устаревшие прокси
                    if max_age_hours > 0:
                        current_time = datetime.now()
                        valid_proxies = []
                        removed_count = 0
                        
                        for proxy in proxies:
                            last_verified = proxy.get('last_verified')
                            if last_verified:
                                try:
                                    verified_time = datetime.fromisoformat(last_verified)
                                    age_hours = (current_time - verified_time).total_seconds() / 3600
                                    if age_hours <= max_age_hours:
                                        valid_proxies.append(proxy)
                                    else:
                                        removed_count += 1
                                except (ValueError, TypeError):
                                    # Если не удалось распарсить дату, оставляем прокси (для обратной совместимости)
                                    valid_proxies.append(proxy)
                            else:
                                # Для старых прокси без временной метки добавляем её
                                proxy['last_verified'] = current_time.isoformat()
                                valid_proxies.append(proxy)
                        
                        if removed_count > 0:
                            logger.info(f"Removed {removed_count} expired proxies (older than {max_age_hours}h)")
                            # Сохраняем очищенный список
                            self.successful_proxies = valid_proxies
                            self.save_successful_proxies()
                            return valid_proxies
                        
                        return proxies
                    return proxies
        except Exception as e:
            logger.warning(f"Failed to load successful proxies: {e}")
        return []
    
    def save_successful_proxies(self):
        """Сохраняет успешные прокси в файл"""
        try:
            with open(SUCCESSFUL_PROXIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.successful_proxies, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save successful proxies: {e}")
    
    def record_successful_proxy(self, proxy: Dict):
        """Добавляет прокси в список успешных (без дублей) с временной меткой"""
        if not proxy:
            return
        proxy_key = f"{proxy.get('ip')}:{proxy.get('port')}"
        if not proxy_key:
            return
        with self.lock:
            existing_keys = {f"{p.get('ip')}:{p.get('port')}" for p in self.successful_proxies}
            if proxy_key in existing_keys:
                # Обновляем временную метку для существующего прокси
                for p in self.successful_proxies:
                    if f"{p.get('ip')}:{p.get('port')}" == proxy_key:
                        p['last_verified'] = datetime.now().isoformat()
                        break
                self.save_successful_proxies()
                return
            proxy_copy = {
                'ip': proxy.get('ip'),
                'port': proxy.get('port'),
                'protocol': proxy.get('protocol', 'http'),
                'country': proxy.get('country', ''),
                'source': proxy.get('source', 'unknown'),
                'last_verified': datetime.now().isoformat()  # Временная метка для TTL
            }
            if 'total_pages' in proxy:
                proxy_copy['total_pages'] = proxy['total_pages']
            self.successful_proxies.append(proxy_copy)
            self.save_successful_proxies()
    
    def clean_failed_proxies_from_cache(self, max_to_check: int = 50) -> int:
        """
        Очищает неработающие прокси из кеша successful_proxies.
        Проверяет старые успешные прокси и удаляет те, которые перестали работать.
        
        Args:
            max_to_check: Максимальное количество прокси для проверки за раз
            
        Returns:
            Количество удаленных неработающих прокси
        """
        if not self.successful_proxies:
            return 0
        
        logger.info(f"Cleaning failed proxies from cache (checking up to {max_to_check} of {len(self.successful_proxies)} cached proxies)...")
        
        # Берем первые N прокси для проверки
        proxies_to_check = self.successful_proxies[:max_to_check]
        removed_count = 0
        
        for proxy in proxies_to_check:
            proxy_key = f"{proxy.get('ip')}:{proxy.get('port')}"
            
            # Быстрая базовая проверка
            basic_ok, _ = self.validate_proxy_basic(proxy, timeout=5)
            if not basic_ok:
                logger.warning(f"Removing failed proxy from cache: {proxy_key}")
                with self.lock:
                    self.successful_proxies = [p for p in self.successful_proxies 
                                             if f"{p.get('ip')}:{p.get('port')}" != proxy_key]
                    self.failed_proxies.add(proxy_key)
                    removed_count += 1
        
        if removed_count > 0:
            self.save_successful_proxies()
            logger.info(f"Cleaned {removed_count} failed proxies from cache. Remaining: {len(self.successful_proxies)}")
        else:
            logger.info(f"No failed proxies found in cache. All {len(proxies_to_check)} checked proxies are working.")
        
        return removed_count
    
    def remove_failed_proxy(self, proxy: Dict):
        """
        Удаляет прокси из списка успешных и добавляет в список неработающих.
        
        Args:
            proxy: Прокси для удаления
        """
        if not proxy:
            return
        
        proxy_key = f"{proxy.get('ip')}:{proxy.get('port')}"
        if not proxy_key:
            return
        
        with self.lock:
            # Удаляем из успешных
            before_count = len(self.successful_proxies)
            self.successful_proxies = [p for p in self.successful_proxies 
                                     if f"{p.get('ip')}:{p.get('port')}" != proxy_key]
            after_count = len(self.successful_proxies)
            
            # Добавляем в неработающие
            self.failed_proxies.add(proxy_key)
            
            if before_count != after_count:
                self.save_successful_proxies()
                logger.debug(f"Removed failed proxy {proxy_key} from successful list")
    
    def _parse_proxymania_page(self, page_num: int = 1) -> List[Dict]:
        """Парсит одну страницу прокси с proxymania.su"""
        try:
            # Если есть фильтр по странам, используем его в URL для оптимизации
            country_param = ""
            if self.country_filter and len(self.country_filter) == 1:
                # Если только одна страна, используем фильтр в URL
                country_param = f"&country={self.country_filter[0]}"
            
            url = f"https://proxymania.su/free-proxy?page={page_num}{country_param}"
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
            
            # Пробуем оба варианта селектора (на случай изменения структуры)
            rows = table.select('tbody#resultTable tr') or table.select('tbody tr')
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
                'Azerbaijan': 'AZ', 'Azərbaycan': 'AZ', 'Азербайджан': 'AZ',
                'Kyrgyzstan': 'KG', 'Кыргызстан': 'KG', 'Киргизия': 'KG',
                'Tajikistan': 'TJ', 'Тоҷикистон': 'TJ', 'Таджикистан': 'TJ',
                'Turkmenistan': 'TM', 'Туркменистан': 'TM',
                'Uzbekistan': 'UZ', 'Oʻzbekiston': 'UZ', 'Узбекистан': 'UZ',
                'Russia': 'RU', 'Россия': 'RU',  # Дополнительные варианты
                'Belarus': 'BY', 'Белоруссия': 'BY',  # Дополнительные варианты
                'Ukraine': 'UA', 'Украина': 'UA',  # Дополнительные варианты
                'Moldova': 'MD', 'Молдавия': 'MD',  # Дополнительные варианты
                'Georgia': 'GE', 'Грузия': 'GE',  # Дополнительные варианты
                'Armenia': 'AM', 'Армения': 'AM',  # Дополнительные варианты
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
            logger.warning(f"Error parsing page {page_num} proxymania.su: {e}")
            return []
    
    def _download_proxies_from_proxymania(self) -> List[Dict]:
        """Parses all available proxy pages from proxymania.su"""
        all_proxies = []
        page_num = 1
        consecutive_empty = 0
        max_consecutive_empty = 3  # Stop after 3 empty pages
        
        logger.info("Parsing proxies from proxymania.su...")
        while consecutive_empty < max_consecutive_empty:
            proxies = self._parse_proxymania_page(page_num)
            if not proxies:
                consecutive_empty += 1
            else:
                consecutive_empty = 0
                all_proxies.extend(proxies)
                logger.info(f"Page {page_num}: found {len(proxies)} proxies")
            page_num += 1
            time.sleep(1)  # Delay between pages
        
        logger.info(f"Total received {len(all_proxies)} proxies from proxymania.su")
        return all_proxies
    
    def _download_proxies_from_proxifly(self) -> List[Dict]:
        """Загружает прокси с Proxifly"""
        try:
            logger.info("Loading proxies from Proxifly...")
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
            
            logger.info(f"Received {len(proxies)} proxies from Proxifly")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from Proxifly: {e}")
            return []
    
    def _download_proxies_from_proxyscrape(self) -> List[Dict]:
        """Загружает прокси с ProxyScrape API"""
        try:
            logger.info("Loading proxies from ProxyScrape...")
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
                logger.debug(f"Error loading HTTP proxies from ProxyScrape: {e}")
            
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
                logger.debug(f"Error loading SOCKS4 proxies from ProxyScrape: {e}")
            
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
                logger.debug(f"Error loading SOCKS5 proxies from ProxyScrape: {e}")
            
            # Фильтруем по странам (если указан фильтр, но ProxyScrape не предоставляет страну, пропускаем фильтрацию)
            if self.country_filter:
                # Оставляем только прокси без указания страны или те, которые могут быть из нужных стран
                # Так как ProxyScrape не предоставляет страну, оставляем все
                pass
            
            logger.info(f"Received {len(proxies)} proxies from ProxyScrape")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from ProxyScrape: {e}")
            return []
    
    def _download_proxies_from_spysone(self) -> List[Dict]:
        """Downloads proxies from spys.one"""
        try:
            logger.info("Loading proxies from spys.one...")
            proxies = []
            url = "https://spys.one/en/free-proxy-list/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse proxy table
            table = soup.find('table', {'class': 'spy1x'})
            if table:
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        try:
                            ip_port = cols[0].get_text(strip=True)
                            if ':' in ip_port:
                                ip, port = ip_port.split(':', 1)
                                protocol = 'http'  # Default, can be enhanced
                                
                                # Check country if available
                                country = ''
                                if len(cols) > 3:
                                    country_elem = cols[3]
                                    country = country_elem.get_text(strip=True).upper()
                                
                                if not self.country_filter or country in self.country_filter or not country:
                                    proxies.append({
                                        'ip': ip.strip(),
                                        'port': port.strip(),
                                        'protocol': protocol,
                                        'country': country,
                                        'source': 'spysone'
                                    })
                        except (ValueError, IndexError):
                            continue
            
            logger.info(f"Received {len(proxies)} proxies from spys.one")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from spys.one: {e}")
            return []
    
    def _download_proxies_from_free_proxy_list(self) -> List[Dict]:
        """Downloads proxies from free-proxy-list.net"""
        try:
            logger.info("Loading proxies from free-proxy-list.net...")
            proxies = []
            url = "https://free-proxy-list.net/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse proxy table
            table = soup.find('table', {'id': 'proxylisttable'})
            if table:
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 8:
                        try:
                            ip = cols[0].get_text(strip=True)
                            port = cols[1].get_text(strip=True)
                            code = cols[2].get_text(strip=True).upper()
                            https = cols[6].get_text(strip=True)
                            
                            protocol = 'https' if https == 'yes' else 'http'
                            
                            if not self.country_filter or code in self.country_filter:
                                proxies.append({
                                    'ip': ip,
                                    'port': port,
                                    'protocol': protocol,
                                    'country': code,
                                    'source': 'freeproxylist'
                                })
                        except (ValueError, IndexError):
                            continue
            
            logger.info(f"Received {len(proxies)} proxies from free-proxy-list.net")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from free-proxy-list.net: {e}")
            return []
    
    def _download_proxies_from_geonode(self) -> List[Dict]:
        """Downloads proxies from geonode.com API"""
        try:
            logger.info("Loading proxies from geonode.com...")
            proxies = []
            base_url = "https://proxylist.geonode.com/api/proxy-list"
            
            # Fetch multiple pages
            page = 1
            max_pages = 10  # Limit to prevent too many requests
            consecutive_empty = 0
            max_consecutive_empty = 2
            
            while page <= max_pages and consecutive_empty < max_consecutive_empty:
                url = f"{base_url}?limit=500&page={page}&sort_by=lastChecked&sort_type=desc"
                
                try:
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    
                    if not data.get('data') or len(data.get('data', [])) == 0:
                        consecutive_empty += 1
                        page += 1
                        continue
                    
                    consecutive_empty = 0
                    
                    for item in data.get('data', []):
                        try:
                            ip = item.get('ip')
                            port = str(item.get('port', ''))
                            protocol = item.get('protocols', [])
                            country = item.get('country', '').upper()
                            
                            if not ip or not port:
                                continue
                            
                            # Handle protocol (can be a list)
                            if isinstance(protocol, list) and protocol:
                                protocol_str = protocol[0].lower()
                            elif isinstance(protocol, str):
                                protocol_str = protocol.lower()
                            else:
                                protocol_str = 'http'
                            
                            # Normalize protocol
                            if 'socks5' in protocol_str:
                                protocol_str = 'socks5'
                            elif 'socks4' in protocol_str:
                                protocol_str = 'socks4'
                            elif 'https' in protocol_str:
                                protocol_str = 'https'
                            else:
                                protocol_str = 'http'
                            
                            if not self.country_filter or country in self.country_filter or not country:
                                proxies.append({
                                    'ip': ip,
                                    'port': port,
                                    'protocol': protocol_str,
                                    'country': country,
                                    'source': 'geonode'
                                })
                        except (ValueError, KeyError, TypeError):
                            continue
                    
                    page += 1
                    time.sleep(1)  # Delay between pages
                    
                except Exception as e:
                    logger.debug(f"Error loading page {page} from geonode.com: {e}")
                    consecutive_empty += 1
                    page += 1
            
            logger.info(f"Received {len(proxies)} proxies from geonode.com")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from geonode.com: {e}")
            return []
    
    def _download_proxies_from_proxylist_download(self) -> List[Dict]:
        """Загружает прокси с proxy-list.download"""
        try:
            logger.info("Loading proxies from proxy-list.download...")
            # Пробуем разные типы прокси
            proxies = []
            for proxy_type in ['http', 'https', 'socks4', 'socks5']:
                try:
                    url = f"https://www.proxy-list.download/api/v1/get?type={proxy_type}"
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    lines = response.text.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if ':' in line:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                ip = parts[0].strip()
                                port = parts[1].strip()
                                if ip and port:
                                    proxies.append({
                                        'ip': ip,
                                        'port': port,
                                        'protocol': proxy_type.lower(),
                                        'country': 'UN',
                                        'source': 'proxylist_download'
                                    })
                except:
                    continue
            logger.info(f"Received {len(proxies)} proxies from proxy-list.download")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from proxy-list.download: {e}")
            return []
    
    def _download_proxies_from_proxylist_icu(self) -> List[Dict]:
        """Загружает прокси с proxylist.icu"""
        try:
            logger.info("Loading proxies from proxylist.icu...")
            url = "https://www.proxylist.icu/api/proxies"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            proxies = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        ip = item.get('ip', '')
                        port = item.get('port', '')
                        protocol = item.get('protocol', 'http').lower()
                        country = item.get('country', 'UN').upper()
                        if ip and port and protocol in ['http', 'https', 'socks4', 'socks5']:
                            if not self.country_filter or country in self.country_filter:
                                proxies.append({
                                    'ip': ip,
                                    'port': str(port),
                                    'protocol': protocol,
                                    'country': country,
                                    'source': 'proxylist_icu'
                                })
            logger.info(f"Received {len(proxies)} proxies from proxylist.icu")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from proxylist.icu: {e}")
            return []
    
    def _download_proxies_from_github_text(self, url: str, source_name: str) -> List[Dict]:
        """Загружает прокси из GitHub текстового файла"""
        try:
            logger.info(f"Loading proxies from GitHub ({source_name})...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            lines = response.text.strip().split('\n')
            proxies = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        ip = parts[0].strip()
                        port = parts[1].strip()
                        if ip and port:
                            # По умолчанию HTTP, но можно определить по URL
                            protocol = 'http'
                            if 'socks' in url.lower():
                                protocol = 'socks5' if 'socks5' in url.lower() else 'socks4'
                            elif 'https' in url.lower():
                                protocol = 'https'
                            proxies.append({
                                'ip': ip,
                                'port': port,
                                'protocol': protocol,
                                'country': 'UN',
                                'source': source_name
                            })
            logger.info(f"Received {len(proxies)} proxies from {source_name}")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from {source_name}: {e}")
            return []
    
    def _download_proxies_from_proxylist_me(self) -> List[Dict]:
        """Загружает прокси с proxylist.me"""
        try:
            logger.info("Loading proxies from proxylist.me...")
            proxies = []
            for proxy_type in ['http', 'https', 'socks4', 'socks5']:
                try:
                    url = f"https://www.proxylist.me/api/v1/get?type={proxy_type}"
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    lines = response.text.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if ':' in line:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                ip = parts[0].strip()
                                port = parts[1].strip()
                                if ip and port:
                                    proxies.append({
                                        'ip': ip,
                                        'port': port,
                                        'protocol': proxy_type.lower(),
                                        'country': 'UN',
                                        'source': 'proxylist_me'
                                    })
                except:
                    continue
            logger.info(f"Received {len(proxies)} proxies from proxylist.me")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from proxylist.me: {e}")
            return []
    
    def _download_proxies_from_proxy6(self) -> List[Dict]:
        """Загружает прокси с Proxy6 (требует обход nginx JS challenge)"""
        try:
            logger.info("Loading proxies from Proxy6 (may require JS challenge bypass)...")
            # Proxy6 может требовать JS challenge, используем Selenium если нужно
            from utils import create_driver, wait_for_cloudflare, safe_get_page_source
            from bs4 import BeautifulSoup
            
            url = "https://proxy6.net/free-proxy"
            proxies = []
            
            # Пробуем сначала через requests
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                }
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
            except Exception as req_error:
                # Если requests не работает (nginx JS challenge), используем Selenium
                logger.debug(f"Requests failed for Proxy6, trying Selenium: {req_error}")
                driver = create_driver(prefer_chrome=False)  # Используем Firefox
                if not driver:
                    return []
                try:
                    driver.get(url)
                    wait_for_cloudflare(driver, max_wait=30, context="Proxy6 page")
                    page_source = safe_get_page_source(driver)
                    if not page_source:
                        return []
                    soup = BeautifulSoup(page_source, 'html.parser')
                finally:
                    try:
                        driver.quit()
                    except:
                        pass
            
            # Парсим прокси со страницы (структура может отличаться)
            # Ищем таблицы или списки прокси
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')[1:]  # Пропускаем заголовок
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        try:
                            ip_port = cols[0].get_text(strip=True)
                            if ':' in ip_port:
                                ip, port = ip_port.split(':', 1)
                                country = cols[1].get_text(strip=True).upper() if len(cols) > 1 else 'UN'
                                
                                # Определяем протокол
                                protocol = 'http'
                                if len(cols) > 2:
                                    protocol_text = cols[2].get_text(strip=True).lower()
                                    if 'socks5' in protocol_text:
                                        protocol = 'socks5'
                                    elif 'socks4' in protocol_text:
                                        protocol = 'socks4'
                                    elif 'https' in protocol_text:
                                        protocol = 'https'
                                
                                if self.country_filter and country not in self.country_filter:
                                    continue
                                
                                proxies.append({
                                    'ip': ip.strip(),
                                    'port': port.strip(),
                                    'protocol': protocol,
                                    'country': country,
                                    'source': 'proxy6'
                                })
                        except Exception:
                            continue
            
            logger.info(f"Received {len(proxies)} proxies from Proxy6")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from Proxy6: {e}")
            return []
    
    def _download_proxies_from_proxys_io(self) -> List[Dict]:
        """Загружает прокси с Proxys.io (может требовать обход nginx JS challenge)"""
        try:
            logger.info("Loading proxies from Proxys.io (may require JS challenge bypass)...")
            from utils import create_driver, wait_for_cloudflare, safe_get_page_source
            from bs4 import BeautifulSoup
            
            url = "https://proxys.io/free-proxy-list"
            proxies = []
            
            # Пробуем сначала через requests
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                }
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
            except Exception:
                # Используем Selenium для обхода JS challenge
                driver = create_driver(prefer_chrome=False)
                if not driver:
                    return []
                try:
                    driver.get(url)
                    wait_for_cloudflare(driver, max_wait=30, context="Proxys.io page")
                    page_source = safe_get_page_source(driver)
                    if not page_source:
                        return []
                    soup = BeautifulSoup(page_source, 'html.parser')
                finally:
                    try:
                        driver.quit()
                    except:
                        pass
            
            # Парсим прокси (адаптируем под структуру сайта)
            # Ищем элементы с прокси
            proxy_elements = soup.find_all(['tr', 'div'], class_=lambda x: x and ('proxy' in x.lower() or 'ip' in x.lower()))
            for elem in proxy_elements:
                text = elem.get_text()
                if ':' in text:
                    parts = text.split()
                    for part in parts:
                        if ':' in part and '.' in part:
                            try:
                                ip, port = part.split(':', 1)
                                if ip.count('.') == 3 and port.isdigit():
                                    country = 'UN'
                                    # Пытаемся найти страну в элементе
                                    country_elem = elem.find(['span', 'td'], class_=lambda x: x and 'country' in x.lower() if x else False)
                                    if country_elem:
                                        country = country_elem.get_text(strip=True).upper()[:2]
                                    
                                    if self.country_filter and country not in self.country_filter:
                                        continue
                                    
                                    proxies.append({
                                        'ip': ip.strip(),
                                        'port': port.strip(),
                                        'protocol': 'http',
                                        'country': country,
                                        'source': 'proxys_io'
                                    })
                                    break
                            except Exception:
                                continue
            
            logger.info(f"Received {len(proxies)} proxies from Proxys.io")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from Proxys.io: {e}")
            return []
    
    def _download_proxies_from_proxy_seller(self) -> List[Dict]:
        """Загружает прокси с Proxy-Seller (может требовать обход nginx JS challenge)"""
        try:
            logger.info("Loading proxies from Proxy-Seller (may require JS challenge bypass)...")
            from utils import create_driver, wait_for_cloudflare, safe_get_page_source
            from bs4 import BeautifulSoup
            
            url = "https://proxy-seller.com/free-proxy"
            proxies = []
            
            # Пробуем сначала через requests
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                }
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
            except Exception:
                # Используем Selenium для обхода JS challenge
                driver = create_driver(prefer_chrome=False)
                if not driver:
                    return []
                try:
                    driver.get(url)
                    wait_for_cloudflare(driver, max_wait=30, context="Proxy-Seller page")
                    page_source = safe_get_page_source(driver)
                    if not page_source:
                        return []
                    soup = BeautifulSoup(page_source, 'html.parser')
                finally:
                    try:
                        driver.quit()
                    except:
                        pass
            
            # Парсим прокси (адаптируем под структуру сайта)
            # Ищем таблицы, списки или div-ы с прокси
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        try:
                            ip_port = cols[0].get_text(strip=True)
                            if ':' in ip_port and '.' in ip_port:
                                ip, port = ip_port.split(':', 1)
                                country = cols[1].get_text(strip=True).upper()[:2] if len(cols) > 1 else 'UN'
                                
                                protocol = 'http'
                                if len(cols) > 2:
                                    protocol_text = cols[2].get_text(strip=True).lower()
                                    if 'socks5' in protocol_text:
                                        protocol = 'socks5'
                                    elif 'socks4' in protocol_text:
                                        protocol = 'socks4'
                                    elif 'https' in protocol_text:
                                        protocol = 'https'
                                
                                if self.country_filter and country not in self.country_filter:
                                    continue
                                
                                proxies.append({
                                    'ip': ip.strip(),
                                    'port': port.strip(),
                                    'protocol': protocol,
                                    'country': country,
                                    'source': 'proxy_seller'
                                })
                        except Exception:
                            continue
            
            # Также ищем в div-ах и других элементах
            proxy_divs = soup.find_all(['div', 'span'], class_=lambda x: x and ('proxy' in str(x).lower() or 'ip' in str(x).lower()) if x else False)
            for div in proxy_divs:
                text = div.get_text()
                if ':' in text and '.' in text:
                    parts = text.split()
                    for part in parts:
                        if ':' in part and part.count('.') == 3:
                            try:
                                ip, port = part.split(':', 1)
                                if port.isdigit():
                                    proxies.append({
                                        'ip': ip.strip(),
                                        'port': port.strip(),
                                        'protocol': 'http',
                                        'country': 'UN',
                                        'source': 'proxy_seller'
                                    })
                            except Exception:
                                continue
            
            logger.info(f"Received {len(proxies)} proxies from Proxy-Seller")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from Proxy-Seller: {e}")
            return []
    
    def _download_proxies_from_floppydata(self) -> List[Dict]:
        """Загружает прокси с Floppydata (может требовать обход nginx JS challenge)"""
        try:
            logger.info("Loading proxies from Floppydata (may require JS challenge bypass)...")
            from utils import create_driver, wait_for_cloudflare, safe_get_page_source
            from bs4 import BeautifulSoup
            
            url = "https://floppydata.com/free-proxy"
            proxies = []
            
            # Пробуем сначала через requests
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                }
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
            except Exception:
                # Используем Selenium для обхода JS challenge
                driver = create_driver(prefer_chrome=False)
                if not driver:
                    return []
                try:
                    driver.get(url)
                    wait_for_cloudflare(driver, max_wait=30, context="Floppydata page")
                    page_source = safe_get_page_source(driver)
                    if not page_source:
                        return []
                    soup = BeautifulSoup(page_source, 'html.parser')
                finally:
                    try:
                        driver.quit()
                    except:
                        pass
            
            # Парсим прокси
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        try:
                            ip_port = cols[0].get_text(strip=True)
                            if ':' in ip_port:
                                ip, port = ip_port.split(':', 1)
                                country = cols[1].get_text(strip=True).upper()[:2] if len(cols) > 1 else 'UN'
                                
                                protocol = 'http'
                                if len(cols) > 2:
                                    protocol_text = cols[2].get_text(strip=True).lower()
                                    if 'socks5' in protocol_text:
                                        protocol = 'socks5'
                                    elif 'socks4' in protocol_text:
                                        protocol = 'socks4'
                                    elif 'https' in protocol_text:
                                        protocol = 'https'
                                
                                if self.country_filter and country not in self.country_filter:
                                    continue
                                
                                proxies.append({
                                    'ip': ip.strip(),
                                    'port': port.strip(),
                                    'protocol': protocol,
                                    'country': country,
                                    'source': 'floppydata'
                                })
                        except Exception:
                            continue
            
            logger.info(f"Received {len(proxies)} proxies from Floppydata")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from Floppydata: {e}")
            return []
    
    def _download_proxies_from_prosox(self) -> List[Dict]:
        """Загружает прокси с Prosox (может требовать обход nginx JS challenge)"""
        try:
            logger.info("Loading proxies from Prosox (may require JS challenge bypass)...")
            from utils import create_driver, wait_for_cloudflare, safe_get_page_source
            from bs4 import BeautifulSoup
            
            url = "https://prosox.com/free-proxy"
            proxies = []
            
            # Пробуем сначала через requests
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                }
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
            except Exception:
                # Используем Selenium для обхода JS challenge
                driver = create_driver(prefer_chrome=False)
                if not driver:
                    return []
                try:
                    driver.get(url)
                    wait_for_cloudflare(driver, max_wait=30, context="Prosox page")
                    page_source = safe_get_page_source(driver)
                    if not page_source:
                        return []
                    soup = BeautifulSoup(page_source, 'html.parser')
                finally:
                    try:
                        driver.quit()
                    except:
                        pass
            
            # Парсим прокси
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        try:
                            ip_port = cols[0].get_text(strip=True)
                            if ':' in ip_port:
                                ip, port = ip_port.split(':', 1)
                                country = cols[1].get_text(strip=True).upper()[:2] if len(cols) > 1 else 'UN'
                                
                                protocol = 'http'
                                if len(cols) > 2:
                                    protocol_text = cols[2].get_text(strip=True).lower()
                                    if 'socks5' in protocol_text:
                                        protocol = 'socks5'
                                    elif 'socks4' in protocol_text:
                                        protocol = 'socks4'
                                    elif 'https' in protocol_text:
                                        protocol = 'https'
                                
                                if self.country_filter and country not in self.country_filter:
                                    continue
                                
                                proxies.append({
                                    'ip': ip.strip(),
                                    'port': port.strip(),
                                    'protocol': protocol,
                                    'country': country,
                                    'source': 'prosox'
                                })
                        except Exception:
                            continue
            
            logger.info(f"Received {len(proxies)} proxies from Prosox")
            return proxies
        except Exception as e:
            logger.warning(f"Error loading proxies from Prosox: {e}")
            return []
    
    def download_proxies(self, force_update: bool = False, clean_old: bool = True) -> bool:
        """Скачивает свежие прокси из всех источников"""
        try:
            if force_update:
                logger.info("Forced proxy list update...")
            
            # Очищаем старые неработающие прокси из кеша перед загрузкой новых
            if clean_old and self.successful_proxies:
                logger.info("Cleaning old failed proxies from cache...")
                removed = self.clean_failed_proxies_from_cache(max_to_check=50)
                if removed > 0:
                    logger.info(f"Removed {removed} failed proxies from cache")
            
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
            
            # Загружаем с spys.one
            if PROXY_SOURCES.get('spysone', {}).get('active', False):
                spysone_proxies = self._download_proxies_from_spysone()
                all_proxies.extend(spysone_proxies)
            
            # Загружаем с free-proxy-list.net
            if PROXY_SOURCES.get('freeproxylist', {}).get('active', False):
                freeproxylist_proxies = self._download_proxies_from_free_proxy_list()
                all_proxies.extend(freeproxylist_proxies)
            
            # Загружаем с geonode.com
            if PROXY_SOURCES.get('geonode', {}).get('active', False):
                geonode_proxies = self._download_proxies_from_geonode()
                all_proxies.extend(geonode_proxies)
            
            # Загружаем с proxy-list.download
            if PROXY_SOURCES.get('proxylist_download', {}).get('active', False):
                proxylist_download_proxies = self._download_proxies_from_proxylist_download()
                all_proxies.extend(proxylist_download_proxies)
            
            # Загружаем с proxylist.icu
            if PROXY_SOURCES.get('proxylist_icu', {}).get('active', False):
                proxylist_icu_proxies = self._download_proxies_from_proxylist_icu()
                all_proxies.extend(proxylist_icu_proxies)
            
            # Загружаем с GitHub (clarketm)
            if PROXY_SOURCES.get('github_clarketm', {}).get('active', False):
                github_clarketm_proxies = self._download_proxies_from_github_text(
                    PROXY_SOURCES['github_clarketm']['url'], 'github_clarketm'
                )
                all_proxies.extend(github_clarketm_proxies)
            
            # Загружаем с GitHub (thespeedx)
            if PROXY_SOURCES.get('github_thespeedx', {}).get('active', False):
                github_thespeedx_proxies = self._download_proxies_from_github_text(
                    PROXY_SOURCES['github_thespeedx']['url'], 'github_thespeedx'
                )
                all_proxies.extend(github_thespeedx_proxies)
            
            # Загружаем с GitHub (monosans)
            if PROXY_SOURCES.get('github_monosans', {}).get('active', False):
                github_monosans_proxies = self._download_proxies_from_github_text(
                    PROXY_SOURCES['github_monosans']['url'], 'github_monosans'
                )
                all_proxies.extend(github_monosans_proxies)
            
            # Загружаем с proxylist.me
            if PROXY_SOURCES.get('proxylist_me', {}).get('active', False):
                proxylist_me_proxies = self._download_proxies_from_proxylist_me()
                all_proxies.extend(proxylist_me_proxies)
            
            # Загружаем с Proxy6 (может требовать обход nginx JS challenge)
            if PROXY_SOURCES.get('proxy6', {}).get('active', False):
                proxy6_proxies = self._download_proxies_from_proxy6()
                all_proxies.extend(proxy6_proxies)
            
            # Загружаем с Proxys.io (может требовать обход nginx JS challenge)
            if PROXY_SOURCES.get('proxys_io', {}).get('active', False):
                proxys_io_proxies = self._download_proxies_from_proxys_io()
                all_proxies.extend(proxys_io_proxies)
            
            # Загружаем с Proxy-Seller (может требовать обход nginx JS challenge)
            if PROXY_SOURCES.get('proxy_seller', {}).get('active', False):
                proxy_seller_proxies = self._download_proxies_from_proxy_seller()
                all_proxies.extend(proxy_seller_proxies)
            
            # Загружаем с Floppydata (может требовать обход nginx JS challenge)
            if PROXY_SOURCES.get('floppydata', {}).get('active', False):
                floppydata_proxies = self._download_proxies_from_floppydata()
                all_proxies.extend(floppydata_proxies)
            
            # Загружаем с Prosox (может требовать обход nginx JS challenge)
            if PROXY_SOURCES.get('prosox', {}).get('active', False):
                prosox_proxies = self._download_proxies_from_prosox()
                all_proxies.extend(prosox_proxies)
            
            # Удаляем дубликаты по IP:PORT
            seen = set()
            filtered_proxies = []
            for proxy in all_proxies:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in seen:
                    seen.add(proxy_key)
                    filtered_proxies.append(proxy)
            
            logger.info(f"After removing duplicates: {len(filtered_proxies)} unique proxies")
            
            # Фильтруем по странам СНГ
            if self.country_filter:
                before_filter = len(filtered_proxies)
                filtered_proxies = filter_proxies_by_country(filtered_proxies, self.country_filter)
                after_filter = len(filtered_proxies)
                if before_filter != after_filter:
                    logger.info(f"Filtered proxies by CIS countries: {before_filter} → {after_filter} (removed {before_filter - after_filter})")
            
            # Сохраняем прокси
            with open(PROXIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(filtered_proxies, f, ensure_ascii=False, indent=2)
            
            with open(LAST_UPDATE_FILE, 'w', encoding='utf-8') as f:
                f.write(datetime.now().isoformat())
            
            logger.info(f"Saved {len(filtered_proxies)} proxies to file: {PROXIES_FILE}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading proxies: {e}")
            return False
    
    def _load_proxies(self) -> List[Dict]:
        """Загружает прокси из файла"""
        try:
            if os.path.exists(PROXIES_FILE):
                with open(PROXIES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load proxies: {e}")
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
                    logger.info(f"Proxy {ip}:{port} ({protocol.upper()}) works! IP: {external_ip}")
                    return True, {
                        'ip': ip, 'port': port, 'protocol': protocol,
                        'external_ip': external_ip, 'proxies': proxies
                    }
            
            return False, {}
        except Exception as e:
            logger.debug(f"Proxy {proxy.get('ip', '')}:{proxy.get('port', '')} not working: {e}")
            return False, {}
    
    def _precheck_proxy_connection(self, proxy: Dict, timeout: int = 10) -> Tuple[bool, Optional[str]]:
        """
        Быстрая проверка доступности целевого сайта через SOCKS-прокси до запуска Selenium.
        """
        protocol = proxy.get('protocol', 'http').lower()
        if protocol not in ('socks4', 'socks5'):
            return True, None
        
        ip = proxy.get('ip')
        port = proxy.get('port')
        if not ip or not port:
            return False, "invalid_proxy"
        
        proxy_schema = "socks5h" if protocol == 'socks5' else "socks4"
        proxy_url = f"{proxy_schema}://{ip}:{port}"
        proxies = {'http': proxy_url, 'https': proxy_url}
        
        try:
            response = requests.get(
                TARGET_URL,
                proxies=proxies,
                timeout=timeout,
                verify=False,
                allow_redirects=False
            )
            if response.status_code < 500:
                return True, None
            return False, f"status_{response.status_code}"
        except requests.RequestException as e:
            return False, str(e)
    
    def validate_proxy_for_trast(self, proxy: Dict, timeout: int = None) -> Tuple[bool, Dict]:
        """Проверяет прокси на доступность trast-zapchast.ru через Selenium"""
        if timeout is None:
            timeout = PROXY_TEST_TIMEOUT
        
        proxy_key = f"{proxy.get('ip', '')}:{proxy.get('port', '')}"
        debug_html_saved = False
        
        try:
            protocol = proxy.get('protocol', 'http').lower()
            if protocol in ('socks4', 'socks5'):
                precheck_ok, precheck_reason = self._precheck_proxy_connection(proxy, timeout=8)
                if not precheck_ok:
                    logger.debug(f"[{proxy_key}] SOCKS pre-check failed: {precheck_reason}")
                    return False, {}
            
            prefer_chrome = (
                USE_UNDETECTED_CHROME
                and not FORCE_FIREFOX
                and protocol in ('http', 'https')
            )
            
            attempt_order = []
            if prefer_chrome:
                attempt_order.append("chrome")
            attempt_order.append("firefox")
            
            last_error = None
            from utils import safe_get_page_source
            
            for browser_name in attempt_order:
                driver = None
                try:
                    logger.debug(
                        f"Checking proxy {proxy_key} on trast-zapchast.ru via {browser_name.upper()} "
                        f"(timeout: {timeout}s)..."
                    )
                    driver = create_driver(proxy, prefer_chrome=(browser_name == "chrome"))
                    if not driver:
                        logger.debug(f"Failed to create {browser_name} driver for {proxy_key}")
                        continue
                    
                    driver.set_page_load_timeout(timeout)
                    logger.debug(f"Loading page via proxy {proxy_key} ({browser_name.upper()})...")
                    driver.get(TARGET_URL)
                    time.sleep(5)
                    
                    page_source = safe_get_page_source(driver)
                    if not page_source:
                        logger.warning(f"Failed to get page_source for proxy {proxy_key} ({browser_name})")
                        last_error = RuntimeError("empty_page_source")
                        continue
                    
                    # Используем единую функцию wait_for_cloudflare для обработки защиты
                    from utils import wait_for_cloudflare
                    cloudflare_success, page_source = wait_for_cloudflare(
                        driver, 
                        max_wait=30, 
                        thread_name=f"{browser_name}",
                        context=f"proxy {proxy_key}"
                    )
                    
                    if not cloudflare_success:
                        logger.warning(f"Protection check failed for proxy {proxy_key} ({browser_name})")
                        if page_source:
                            self._save_debug_html(proxy_key, page_source, f"{browser_name}_cloudflare_timeout")
                            debug_html_saved = True
                        last_error = RuntimeError("protection_timeout")
                        continue
                    
                    if not page_source:
                        logger.warning(f"Tab crash during protection wait for proxy {proxy_key}")
                        last_error = RuntimeError("tab_crash_during_cloudflare")
                        continue
                    
                    logger.debug(f"Getting page count via proxy {proxy_key} ({browser_name})...")
                    total_pages = get_pages_count_with_driver(driver)
                    if total_pages and total_pages > 0:
                        logger.info(
                            f"[{proxy_key}] PROXY WORKS via {browser_name.upper()}! "
                            f"Page count: {total_pages}"
                        )
                        return True, {'total_pages': total_pages, 'browser': browser_name}
                    
                    logger.warning(
                        f"[{proxy_key}] Failed to get page count via {browser_name} (returned {total_pages})"
                    )
                    if not debug_html_saved:
                        page_source = safe_get_page_source(driver)
                        if page_source:
                            self._save_debug_html(proxy_key, page_source, f"{browser_name}_no_page_count")
                            debug_html_saved = True
                    return False, {}
                
                except PaginationNotDetectedError as e:
                    logger.warning(f"Proxy {proxy_key} blocked on site via {browser_name}: {e}")
                    if not debug_html_saved:
                        page_source = safe_get_page_source(driver)
                        if page_source:
                            self._save_debug_html(
                                proxy_key, page_source, f"{browser_name}_blocked_{str(e)[:40]}"
                            )
                            debug_html_saved = True
                    return False, {}
                except Exception as e:
                    last_error = e
                    if browser_name == "chrome" and is_proxy_connection_error(e) and not FORCE_FIREFOX:
                        logger.warning(
                            f"[{proxy_key}] Chrome proxy connection failed: {e}. Retrying with Firefox..."
                        )
                        time.sleep(BROWSER_RETRY_DELAY)
                        continue
                    
                    logger.warning(f"Error checking proxy {proxy_key} via {browser_name}: {e}")
                    if driver and not debug_html_saved:
                        page_source = safe_get_page_source(driver)
                        if page_source:
                            self._save_debug_html(
                                proxy_key, page_source, f"{browser_name}_exception_{type(e).__name__}"
                            )
                            debug_html_saved = True
                    return False, {}
                finally:
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
            
            if last_error:
                logger.debug(f"Last error for proxy {proxy_key}: {last_error}")
            return False, {}
        
        except Exception as e:
            logger.debug(f"Error checking proxy {proxy_key} on trast: {e}")
            return False, {}
    
    def _save_debug_html(self, proxy_key: str, page_source: str, reason: str):
        """Сохраняет HTML страницы для отладки при неудачных проверках прокси"""
        try:
            from config import LOG_DIR
            from datetime import datetime
            import os
            
            # Создаем директорию для отладочных HTML если её нет
            debug_dir = os.path.join(LOG_DIR, "debug_proxy_html")
            os.makedirs(debug_dir, exist_ok=True)
            
            # Формируем имя файла
            safe_proxy_key = proxy_key.replace(":", "_").replace("/", "_")
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_reason = reason.replace(" ", "_").replace("/", "_")[:50]
            filename = f"proxy_{safe_proxy_key}_{safe_reason}_{timestamp}.html"
            filepath = os.path.join(debug_dir, filename)
            
            # Сохраняем HTML
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(page_source)
            
            logger.debug(f"Debug HTML saved for proxy {proxy_key}: {filepath} (reason: {reason})")
        except Exception as e:
            logger.debug(f"Failed to save debug HTML for proxy {proxy_key}: {e}")
    
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
        
        logger.info(f"[{thread_name}] Proxy search thread started")
        
        while not stop_event.is_set():
            try:
                # Получаем прокси из очереди с таймаутом
                try:
                    proxy = proxy_queue.get(timeout=1)
                except queue.Empty:
                    # Очередь пуста - завершаем поток
                    logger.info(f"[{thread_name}] Proxy queue empty, terminating thread (checked: {checked_count}, failed: {failed_count})")
                    break
                
                checked_count += 1
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                
                # Проверяем, не нашли ли уже достаточно прокси
                with self.lock:
                    if len(found_proxies) >= min_count:
                        stop_event.set()
                        proxy_queue.task_done()
                        break
                
                logger.info(f"[{thread_name}] Checking proxy {proxy_key} ({proxy.get('protocol', 'http').upper()})...")
                
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
                    logger.info(f"[{thread_name}] Checked {checked_count} proxies (total across all threads: checked {total_checked}, found {total_found}, failed {total_failed})")
                
            except KeyboardInterrupt:
                logger.warning(f"[{thread_name}] Interrupt signal received, terminating thread")
                stop_event.set()
                break
            except Exception as e:
                logger.error(f"[{thread_name}] Error checking proxy: {e}")
                logger.debug(f"[{thread_name}] Traceback: {traceback.format_exc()}")
                try:
                    proxy_queue.task_done()
                except:
                    pass
                continue
        
        logger.info(f"[{thread_name}] Proxy search thread finished (checked: {checked_count}, failed: {failed_count})")
    
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
            logger.warning("No proxies to check, loading...")
            if not self.download_proxies(force_update=True):
                return []
            proxies = self._load_proxies()
        
        working_proxies = []
        
        # ШАГ 1: Сначала проверяем старые успешные прокси (быстро, последовательно)
        with self.lock:
            shuffled_successful = self.successful_proxies.copy()
        
        if shuffled_successful:
            logger.info(f"Checking {len(shuffled_successful)} old successful proxies (priority)...")
            random.shuffle(shuffled_successful)
            
            for proxy in shuffled_successful:
                if len(working_proxies) >= min_count:
                    break
                
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                logger.info(f"Checking old successful proxy: {proxy_key} ({proxy.get('protocol', 'http').upper()})")
                
                # Быстрая проверка на trast (без базовой проверки, т.к. уже был успешным)
                trast_ok, trast_info = self.validate_proxy_for_trast(proxy)
                if trast_ok:
                    logger.info(f"[OK] Old successful proxy works: {proxy_key}")
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
                    logger.warning(f"Old proxy {proxy_key} stopped working")
                    with self.lock:
                        # Удаляем из успешных
                        self.successful_proxies = [p for p in self.successful_proxies 
                                                   if f"{p['ip']}:{p['port']}" != proxy_key]
                        self.failed_proxies.add(proxy_key)
        
        # Если нашли достаточно старых прокси, возвращаем их
        if len(working_proxies) >= min_count:
            logger.info(f"Found enough old successful proxies: {len(working_proxies)}")
            self.save_successful_proxies()
            return working_proxies[:min_count]
        
        # ШАГ 2: Многопоточный поиск новых прокси (если нужно)
        logger.info(f"Not enough old successful proxies ({len(working_proxies)}/{min_count}), starting search for new ones...")
        
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
            logger.info(f"Limit: checking first {max_to_check} of {len(proxies_to_check) + len(successful_keys) + len(failed_keys)} available proxies")
        else:
            logger.info(f"Checking all available proxies: {len(proxies_to_check)} (successful: {len(successful_keys)}, failed: {len(failed_keys)})")
        
        if not proxies_to_check:
            logger.warning("No new proxies to check")
            self.save_successful_proxies()
            return working_proxies
        
        random.shuffle(proxies_to_check)
        
        if use_parallel and num_threads > 1:
            # Многопоточная проверка
            logger.info(f"Starting multi-threaded search in {num_threads} threads...")
            
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
                logger.info(f"Proxy search thread {thread_id} started")
            
            # Ждем завершения всех потоков (с таймаутом для безопасности)
            for i, thread in enumerate(threads):
                thread.join(timeout=300)  # Максимум 5 минут на поток
                if thread.is_alive():
                    logger.warning(f"Thread {i} did not finish within 5 minutes, possibly hung")
                else:
                    logger.debug(f"Thread {i} finished successfully")
            
            logger.info(f"Multi-threaded search completed: found {len(working_proxies)} proxies (checked: {stats['checked']}, failed: {stats['failed']})")
        else:
            # Последовательная проверка (fallback)
            logger.info("Sequential proxy check...")
            
            for i, proxy in enumerate(proxies_to_check, 1):
                # Если уже нашли нужное количество - останавливаемся
                if len(working_proxies) >= min_count:
                    logger.info(f"Found enough working proxies ({len(working_proxies)}/{min_count}), stopping check")
                    break
                
                logger.info(f"[{i}/{len(proxies_to_check)}] Checking proxy {proxy['ip']}:{proxy['port']}...")
                
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
        
        logger.info(f"Total found {len(working_proxies)} working proxies")
        return working_proxies[:min_count] if len(working_proxies) > min_count else working_proxies
    
    def get_next_proxy(self) -> Optional[Dict]:
        """Получает следующий рабочий прокси из списка"""
        with self.lock:
            if not self.successful_proxies:
                return None
            
            proxy = self.successful_proxies[0]
            self.successful_proxies = self.successful_proxies[1:] + [proxy]
            return proxy.copy()

