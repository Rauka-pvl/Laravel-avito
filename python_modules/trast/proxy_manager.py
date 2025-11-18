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
from collections import Counter
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import TimeoutException

from config import (
    PROXY_CACHE_DIR, PROXIES_FILE, SUCCESSFUL_PROXIES_FILE, LAST_UPDATE_FILE,
    PREFERRED_COUNTRIES, PROXY_SOURCES, PROXY_TEST_TIMEOUT, BASIC_CHECK_TIMEOUT,
    TARGET_URL, PROXY_CHECK_THREADS, PROXY_HEALTH_FILE, PROXY_HEALTH_HISTORY_SIZE,
    PROXY_FAILURE_COOLDOWN_THRESHOLD, PROXY_COOLDOWN_SECONDS, MAX_PROXIES_TO_CHECK,
    PROXY_IP_CHECK_URL, PROXY_PAGE_FAILURE_COOLDOWN
)

from utils import (
    create_driver,
    get_pages_count_with_driver,
    PaginationNotDetectedError,
    is_page_blocked
)


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
        self.proxy_health: Dict[str, Dict] = self._load_proxy_health()
        self.cached_total_pages: Optional[int] = None
        self.cached_total_pages_updated_at: Optional[str] = None
        
        # Thread-safety: блокировка для доступа к критическим данным
        self.lock = threading.Lock()
        
        # Загружаем успешные прокси при инициализации
        self.successful_proxies = self.load_successful_proxies()
        if self.successful_proxies:
            logger.info(f"Loaded {len(self.successful_proxies)} successful proxies from cache")
        
        if self.proxy_health:
            logger.info(f"Loaded proxy health data for {len(self.proxy_health)} proxies")
        
        logger.info(f"ProxyManager initialized with country filter: {', '.join(self.country_filter[:10])}...")
    
    def load_successful_proxies(self) -> List[Dict]:
        """Загружает успешные прокси из файла"""
        try:
            if os.path.exists(SUCCESSFUL_PROXIES_FILE):
                with open(SUCCESSFUL_PROXIES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
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
    
    def _get_proxy_key(self, proxy: Dict) -> str:
        return f"{proxy.get('ip', '')}:{proxy.get('port', '')}"
    
    def _load_proxy_health(self) -> Dict[str, Dict]:
        """Загружает статистику по прокси"""
        try:
            if os.path.exists(PROXY_HEALTH_FILE):
                with open(PROXY_HEALTH_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            logger.warning(f"Failed to load proxy health data: {e}")
        return {}
    
    def _save_proxy_health(self):
        """Сохраняет статистику по прокси"""
        try:
            with open(PROXY_HEALTH_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.proxy_health, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save proxy health data: {e}")
    
    def get_cached_total_pages(self) -> Optional[int]:
        with self.lock:
            return self.cached_total_pages
    
    def set_cached_total_pages(self, total_pages: int):
        with self.lock:
            self.cached_total_pages = total_pages
            self.cached_total_pages_updated_at = datetime.utcnow().isoformat()
    
    def get_health_summary(self, top_n: int = 3) -> Dict[str, any]:
        with self.lock:
            entries = list(self.proxy_health.values())
        
        if not entries:
            return {}
        
        now = datetime.utcnow()
        cooldown_count = 0
        failure_counter = Counter()
        source_counter = Counter()
        
        for entry in entries:
            cooldown_until = entry.get('cooldown_until')
            if cooldown_until:
                try:
                    if datetime.fromisoformat(cooldown_until) > now:
                        cooldown_count += 1
                except Exception:
                    pass
            
            if entry.get('last_failure_reason'):
                failure_counter[entry['last_failure_reason']] += 1
            
            if entry.get('source'):
                source_counter[entry['source']] += 1
        
        return {
            'tracked_proxies': len(entries),
            'cooldown_count': cooldown_count,
            'top_failure_reasons': failure_counter.most_common(top_n),
            'source_distribution': source_counter.most_common(top_n)
        }
    
    def _ensure_health_entry(self, proxy: Dict) -> Dict:
        key = self._get_proxy_key(proxy)
        entry = self.proxy_health.get(key, {})
        entry.setdefault('ip', proxy.get('ip'))
        entry.setdefault('port', proxy.get('port'))
        entry.setdefault('protocol', proxy.get('protocol'))
        entry.setdefault('country', proxy.get('country', ''))
        entry.setdefault('source', proxy.get('source', ''))
        entry.setdefault('consecutive_failures', 0)
        entry.setdefault('total_failures', 0)
        entry.setdefault('total_success', 0)
        entry.setdefault('last_success', None)
        entry.setdefault('last_failure', None)
        entry.setdefault('last_failure_reason', None)
        entry.setdefault('cooldown_until', None)
        entry.setdefault('cooldown_reason', None)
        entry.setdefault('success_counts', {})
        entry.setdefault('failure_counts', {})
        entry.setdefault('events', [])
        self.proxy_health[key] = entry
        return entry
    
    def _append_health_event(self, entry: Dict, event: Dict):
        events = entry.get('events', [])
        events.append(event)
        if len(events) > PROXY_HEALTH_HISTORY_SIZE:
            events = events[-PROXY_HEALTH_HISTORY_SIZE:]
        entry['events'] = events
    
    def _calculate_cooldown(self, reason: str, consecutive_failures: int) -> Optional[int]:
        """
        Рассчитывает длительность охлаждения в секундах для заданной причины
        """
        reason = reason or 'default'
        if reason == 'cloudflare_block':
            return PROXY_COOLDOWN_SECONDS.get(reason, PROXY_COOLDOWN_SECONDS['default'])
        
        if consecutive_failures >= PROXY_FAILURE_COOLDOWN_THRESHOLD:
            return PROXY_COOLDOWN_SECONDS.get(reason, PROXY_COOLDOWN_SECONDS['default'])
        
        return None
    
    def _increment_stage_counter(self, entry: Dict, counter_name: str, stage: str):
        counters = entry.setdefault(counter_name, {})
        counters[stage] = counters.get(stage, 0) + 1
    
    def record_proxy_success(self, proxy: Dict, stage: str, metadata: Optional[Dict] = None, final: bool = False):
        """
        Фиксирует успешное использование прокси
        """
        key = self._get_proxy_key(proxy)
        entry = self._ensure_health_entry(proxy)
        timestamp = datetime.utcnow().isoformat()
        
        event = {
            'timestamp': timestamp,
            'stage': stage,
            'status': 'success',
            'metadata': metadata or {}
        }
        self._append_health_event(entry, event)
        self._increment_stage_counter(entry, 'success_counts', stage)
        
        if final:
            entry['last_success'] = timestamp
            entry['last_result'] = 'success'
            entry['total_success'] += 1
            entry['consecutive_failures'] = 0
            entry['cooldown_until'] = None
            entry['cooldown_reason'] = None
        
        self.proxy_health[key] = entry
        self._save_proxy_health()
    
    def record_proxy_failure(
        self,
        proxy: Dict,
        stage: str,
        reason: str,
        metadata: Optional[Dict] = None
    ):
        """
        Фиксирует неудачную попытку использования прокси
        """
        key = self._get_proxy_key(proxy)
        entry = self._ensure_health_entry(proxy)
        timestamp = datetime.utcnow().isoformat()
        
        entry['last_failure'] = timestamp
        entry['last_failure_reason'] = reason
        entry['last_result'] = 'failure'
        entry['consecutive_failures'] = entry.get('consecutive_failures', 0) + 1
        entry['total_failures'] = entry.get('total_failures', 0) + 1
        
        cooldown_seconds = self._calculate_cooldown(reason, entry['consecutive_failures'])
        if cooldown_seconds:
            cooldown_until = datetime.utcnow() + timedelta(seconds=cooldown_seconds)
            entry['cooldown_until'] = cooldown_until.isoformat()
            entry['cooldown_reason'] = reason
        else:
            entry['cooldown_until'] = None
            entry['cooldown_reason'] = None
        
        event = {
            'timestamp': timestamp,
            'stage': stage,
            'status': 'failure',
            'reason': reason,
            'metadata': metadata or {}
        }
        page_value = (metadata or {}).get('page')
        if page_value is not None:
            entry['last_failed_page'] = page_value
            entry['last_failed_page_at'] = timestamp
            entry['last_failed_page_reason'] = reason
        self._append_health_event(entry, event)
        self._increment_stage_counter(entry, 'failure_counts', stage)
        
        self.proxy_health[key] = entry
        self._save_proxy_health()
    
    def is_proxy_in_cooldown(self, proxy: Dict) -> bool:
        """Проверяет, находится ли прокси в состоянии охлаждения"""
        key = self._get_proxy_key(proxy)
        entry = self.proxy_health.get(key)
        if not entry:
            return False
        
        cooldown_until = entry.get('cooldown_until')
        if not cooldown_until:
            return False
        
        try:
            cooldown_time = datetime.fromisoformat(cooldown_until)
            if datetime.utcnow() < cooldown_time:
                return True
        except Exception:
            return False
        
        return False
    
    def _validate_catalog_page(self, driver: webdriver.Remote, proxy_key: str, page_num: int) -> Tuple[bool, Dict]:
        """
        Дополнительная проверка страницы каталога, чтобы убедиться, что прокси пропускает реальные листинги
        """
        from utils import safe_get_page_source
        
        validation_url = TARGET_URL if page_num <= 1 else f"{TARGET_URL}?_paged={page_num}"
        metadata = {
            'validation_page': page_num,
            'validation_url': validation_url
        }
        
        try:
            logger.debug(f"[{proxy_key}] Validating catalog page {page_num} ({validation_url})...")
            driver.get(validation_url)
            time.sleep(5)
            page_source = safe_get_page_source(driver)
            if not page_source:
                metadata['detail'] = 'validation_empty_page'
                return False, metadata
            
            soup = BeautifulSoup(page_source, 'html.parser')
            block_info = is_page_blocked(soup, page_source)
            metadata['block_check'] = block_info
            
            if block_info.get('blocked'):
                reason = block_info.get('reason', 'catalog_blocked')
                metadata['detail'] = reason
                debug_name = self._reason_with_page(reason, page_num)
                debug_path = self._save_debug_html(proxy_key, page_source, debug_name)
                if debug_path:
                    metadata['debug_html'] = debug_path
                return False, metadata
            
            logger.debug(f"[{proxy_key}] Catalog page {page_num} passed validation")
            return True, metadata
        
        except TimeoutException:
            metadata['detail'] = 'validation_timeout'
            return False, metadata
        except Exception as e:
            metadata['detail'] = 'validation_error'
            metadata['error'] = str(e)
            return False, metadata
    
    def ensure_warm_proxy_pool(self, min_count: int):
        """
        Гарантирует минимальное количество предварительно проверенных прокси
        """
        try:
            with self.lock:
                current_count = len(self.successful_proxies)
            if current_count >= min_count:
                return
            
            logger.info(f"Warm proxy pool below threshold ({current_count}/{min_count}), validating additional proxies...")
            self.get_working_proxies(min_count=min_count, max_to_check=MAX_PROXIES_TO_CHECK, use_parallel=True)
            with self.lock:
                logger.info(f"Warm proxy pool updated: {len(self.successful_proxies)} proxies cached")
        except Exception as e:
            logger.warning(f"Failed to warm proxy pool: {e}")
    
    def should_skip_proxy_for_page(self, proxy: Dict, page: Optional[int]) -> bool:
        """Определяет, стоит ли пропустить прокси для конкретной страницы (если недавно блокировал её)"""
        if page is None:
            return False
        
        key = self._get_proxy_key(proxy)
        with self.lock:
            entry = self.proxy_health.get(key)
            if not entry:
                return False
            last_page = entry.get('last_failed_page')
            last_page_time = entry.get('last_failed_page_at')
            if last_page != page or not last_page_time:
                return False
        
        try:
            last_dt = datetime.fromisoformat(last_page_time)
        except Exception:
            return False
        
        return (datetime.utcnow() - last_dt).total_seconds() < PROXY_PAGE_FAILURE_COOLDOWN
    
    def _proxy_failure_response(
        self,
        proxy: Dict,
        stage: str,
        reason: str,
        metadata: Optional[Dict] = None
    ) -> Tuple[bool, Dict]:
        self.record_proxy_failure(proxy, stage=stage, reason=reason, metadata=metadata or {})
        response = {'reason': reason}
        if metadata:
            response.update(metadata)
        return False, response
    
    def _reason_with_page(self, reason: str, page_context: Optional[int]) -> str:
        if page_context is None:
            return reason
        return f"page_{int(page_context):03d}_{reason}"
    
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
    
    def download_proxies(self, force_update: bool = False) -> bool:
        """Скачивает свежие прокси из всех источников"""
        try:
            if force_update:
                logger.info("Forced proxy list update...")
            
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
            
            # Удаляем дубликаты
            seen = set()
            filtered_proxies = []
            for proxy in all_proxies:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in seen:
                    seen.add(proxy_key)
                    filtered_proxies.append(proxy)
            
            logger.info(f"After removing duplicates: {len(filtered_proxies)} unique proxies")
            
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
        
        stage = "basic"
        endpoint = PROXY_IP_CHECK_URL
        start_time = time.time()
        
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
            
            response = requests.get(endpoint, proxies=proxies, timeout=timeout)
            if response.status_code == 200:
                external_ip = response.text.strip()
                if external_ip and len(external_ip.split('.')) == 4:
                    duration = time.time() - start_time
                    latency_ms = int(duration * 1000)
                    info = {
                        'ip': ip,
                        'port': port,
                        'protocol': protocol,
                        'external_ip': external_ip,
                        'proxies': proxies,
                        'duration': duration,
                        'latency_ms': latency_ms,
                        'endpoint': endpoint
                    }
                    logger.info(f"Proxy {ip}:{port} ({protocol.upper()}) works! IP: {external_ip} ({latency_ms} ms via {endpoint})")
                    self.record_proxy_success(proxy, stage=stage, metadata=info, final=False)
                    return True, info
            
            reason = 'basic_check_failed'
            metadata = {
                'status_code': response.status_code,
                'duration': time.time() - start_time,
                'endpoint': endpoint
            }
            self.record_proxy_failure(proxy, stage=stage, reason=reason, metadata=metadata)
            return False, {'reason': reason, **metadata}
        except requests.exceptions.ConnectTimeout as e:
            reason = 'timeout'
            metadata = {'error': str(e), 'duration': time.time() - start_time, 'endpoint': endpoint}
            logger.debug(f"Proxy {proxy.get('ip', '')}:{proxy.get('port', '')} timeout during basic check: {e}")
            self.record_proxy_failure(proxy, stage=stage, reason=reason, metadata=metadata)
            return False, {'reason': reason, **metadata}
        except requests.exceptions.ProxyError as e:
            reason = 'connection_failure'
            metadata = {'error': str(e), 'duration': time.time() - start_time, 'endpoint': endpoint}
            logger.debug(f"Proxy {proxy.get('ip', '')}:{proxy.get('port', '')} proxy error during basic check: {e}")
            self.record_proxy_failure(proxy, stage=stage, reason=reason, metadata=metadata)
            return False, {'reason': reason, **metadata}
        except Exception as e:
            reason = 'basic_check_failed'
            metadata = {'error': str(e), 'duration': time.time() - start_time, 'endpoint': endpoint}
            logger.debug(f"Proxy {proxy.get('ip', '')}:{proxy.get('port', '')} not working: {e}")
            self.record_proxy_failure(proxy, stage=stage, reason=reason, metadata=metadata)
            return False, {'reason': reason, **metadata}
    
    def validate_proxy_for_trast(self, proxy: Dict, timeout: int = None, page_context: Optional[int] = None) -> Tuple[bool, Dict]:
        """Проверяет прокси на доступность trast-zapchast.ru через Selenium"""
        if timeout is None:
            timeout = PROXY_TEST_TIMEOUT
        
        stage = "selenium"
        driver = None
        proxy_key = f"{proxy.get('ip', '')}:{proxy.get('port', '')}"
        debug_html_path: Optional[str] = None
        start_time = time.time()
        
        def attach_page(metadata: Optional[Dict]) -> Dict:
            metadata = metadata or {}
            if page_context is not None:
                metadata.setdefault('page', page_context)
            return metadata
        
        try:
            logger.debug(f"Checking proxy {proxy_key} on trast-zapchast.ru (timeout: {timeout}s)...")
            
            protocol = proxy.get('protocol', 'http').lower()
            driver = create_driver(proxy)
            if not driver:
                logger.debug(f"Failed to create driver for {proxy_key}")
                metadata = {'detail': 'driver_creation_failed'}
                return self._proxy_failure_response(proxy, stage, 'driver_creation_failed', attach_page(metadata))
            
            driver.set_page_load_timeout(timeout)
            logger.debug(f"Loading page via proxy {proxy_key}...")
            driver.get(TARGET_URL)
            time.sleep(5)  # Ожидание загрузки
            
            # Проверяем Cloudflare
            from utils import safe_get_page_source
            page_source = safe_get_page_source(driver)
            if not page_source:
                logger.warning(f"Failed to get page_source for proxy {proxy_key}")
                metadata = {'detail': 'empty_page_source'}
                return self._proxy_failure_response(proxy, stage, 'no_page_source', attach_page(metadata))
            
            page_source_lower = page_source.lower()
            max_wait = 30
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
                        logger.warning(f"Tab crash during Cloudflare wait for proxy {proxy_key}")
                        metadata = {'detail': 'tab_crash_during_cloudflare'}
                        return self._proxy_failure_response(proxy, stage, 'tab_crash', attach_page(metadata))
                    page_source_lower = page_source.lower()
                except Exception as refresh_error:
                    logger.warning(f"Error refreshing page for proxy {proxy_key}: {refresh_error}")
                    metadata = {'detail': 'cloudflare_refresh_error', 'error': str(refresh_error)}
                    return self._proxy_failure_response(proxy, stage, 'cloudflare_block', attach_page(metadata))
                wait_time += 5
            
            if wait_time >= max_wait:
                logger.warning(f"Cloudflare check failed for proxy {proxy_key}")
                debug_html_path = self._save_debug_html(
                    proxy_key,
                    page_source,
                    self._reason_with_page("cloudflare_timeout", page_context)
                )
                metadata = {
                    'detail': 'cloudflare_timeout',
                    'wait_time': wait_time,
                    'debug_html': debug_html_path
                }
                return self._proxy_failure_response(proxy, stage, 'cloudflare_block', attach_page(metadata))
            
            total_pages = None
            used_cached_pages = False
            cached_total_pages = self.get_cached_total_pages()
            
            if cached_total_pages and cached_total_pages > 0:
                soup = BeautifulSoup(page_source, 'html.parser')
                homepage_block = is_page_blocked(soup, page_source)
                if homepage_block.get('blocked'):
                    reason = homepage_block.get('reason', 'homepage_blocked')
                    debug_html_path = self._save_debug_html(
                        proxy_key,
                        page_source,
                        self._reason_with_page(reason, page_context)
                    )
                    metadata = {
                        'detail': 'homepage_blocked',
                        'block_check': homepage_block,
                        'debug_html': debug_html_path
                    }
                    return self._proxy_failure_response(proxy, stage, 'cloudflare_block', attach_page(metadata))
                
                total_pages = cached_total_pages
                used_cached_pages = True
                logger.debug(f"[{proxy_key}] Using cached total_pages={total_pages}")
            else:
                try:
                    logger.debug(f"Getting page count via proxy {proxy_key}...")
                    total_pages = get_pages_count_with_driver(driver)
                    if total_pages and total_pages > 0:
                        self.set_cached_total_pages(total_pages)
                except PaginationNotDetectedError as e:
                    logger.warning(f"Proxy {proxy_key} blocked on site: {e}")
                    page_source = safe_get_page_source(driver)
                    debug_html_path = self._save_debug_html(
                        proxy_key,
                        page_source or "",
                        self._reason_with_page(f"blocked_{str(e)[:50]}", page_context)
                    ) if page_source else None
                    metadata = {
                        'detail': 'pagination_not_detected',
                        'error': str(e),
                        'debug_html': debug_html_path
                    }
                    return self._proxy_failure_response(proxy, stage, 'cloudflare_block', attach_page(metadata))
                except Exception as e:
                    logger.warning(f"Error getting page count via proxy {proxy_key}: {e}")
                    page_source = safe_get_page_source(driver)
                    debug_html_path = self._save_debug_html(
                        proxy_key,
                        page_source or "",
                        self._reason_with_page(f"error_{type(e).__name__}", page_context)
                    ) if page_source else None
                    metadata = {
                        'detail': 'page_count_error',
                        'error': str(e),
                        'debug_html': debug_html_path
                    }
                    return self._proxy_failure_response(proxy, stage, 'selenium_error', attach_page(metadata))
            
            if total_pages and total_pages > 0:
                duration = time.time() - start_time
                
                validation_page = None
                if total_pages >= 3:
                    validation_page = min(5, total_pages)
                elif total_pages == 2:
                    validation_page = 2
                
                catalog_metadata = {'validation_page': 1, 'validation_url': TARGET_URL}
                if validation_page:
                    catalog_ok, catalog_metadata = self._validate_catalog_page(driver, proxy_key, validation_page)
                    if not catalog_ok:
                        catalog_metadata['total_pages'] = total_pages
                        return self._proxy_failure_response(
                            proxy,
                            stage,
                            'catalog_validation_failed',
                            attach_page(catalog_metadata)
                        )
                
                logger.info(f"[{proxy_key}] PROXY WORKS! Successfully got page count: {total_pages} pages")
                logger.info(f"[{proxy_key}] Ready to start parsing with this proxy!")
                metadata = {
                    'total_pages': total_pages,
                    'duration': duration,
                    'validation_page': catalog_metadata.get('validation_page'),
                    'validation_url': catalog_metadata.get('validation_url'),
                    'page_context': page_context,
                    'total_pages_source': 'cached' if used_cached_pages else 'fresh'
                }
                if catalog_metadata:
                    metadata['catalog_validation'] = catalog_metadata
                self.record_proxy_success(proxy, stage=stage, metadata=metadata, final=True)
                return True, {'total_pages': total_pages}
            
            logger.warning(f"[{proxy_key}] Failed to get page count (returned {total_pages})")
            page_source = safe_get_page_source(driver)
            debug_html_path = self._save_debug_html(
                proxy_key,
                page_source or "",
                self._reason_with_page("no_page_count", page_context)
            ) if page_source else None
            metadata = {
                'detail': 'no_page_count',
                'returned_value': total_pages,
                'debug_html': debug_html_path
            }
            return self._proxy_failure_response(proxy, stage, 'no_page_count', attach_page(metadata))
            
        except TimeoutException as e:
            logger.debug(f"Timeout while checking proxy {proxy_key}: {e}")
            metadata = {'error': str(e)}
            return self._proxy_failure_response(proxy, stage, 'timeout', attach_page(metadata))
        except Exception as e:
            logger.debug(f"Error checking proxy {proxy_key} on trast: {e}")
            page_source = None
            if driver:
                try:
                    from utils import safe_get_page_source
                    page_source = safe_get_page_source(driver)
                except Exception:
                    page_source = None
            if page_source:
                debug_html_path = self._save_debug_html(
                    proxy_key,
                    page_source,
                    self._reason_with_page(f"exception_{type(e).__name__}", page_context)
                )
            metadata = {'error': str(e), 'debug_html': debug_html_path}
            return self._proxy_failure_response(proxy, stage, 'selenium_error', attach_page(metadata))
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def _save_debug_html(self, proxy_key: str, page_source: str, reason: str) -> Optional[str]:
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
            return filepath
        except Exception as e:
            logger.debug(f"Failed to save debug HTML for proxy {proxy_key}: {e}")
        return None
    
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
        if not self.successful_proxies:
            return None
        
        # Простая ротация
        proxy = self.successful_proxies[0]
        self.successful_proxies = self.successful_proxies[1:] + [proxy]
        return proxy

