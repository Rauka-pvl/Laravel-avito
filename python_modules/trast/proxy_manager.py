"""
Упрощенный менеджер прокси для парсера trast-zapchast.ru
Без многопоточности - все проверки последовательно
"""
import os
import json
import re
import time
import random
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup
from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import TimeoutException

from config import (
    PROXY_CACHE_DIR, PROXIES_FILE, SUCCESSFUL_PROXIES_FILE, LAST_UPDATE_FILE,
    PREFERRED_COUNTRIES, PROXY_SOURCES, PROXY_TEST_TIMEOUT, BASIC_CHECK_TIMEOUT,
    TARGET_URL
)
from utils import create_driver, get_pages_count_with_driver


class ProxyManager:
    """Упрощенный менеджер прокси без многопоточности"""
    
    def __init__(self, country_filter: Optional[List[str]] = None):
        """
        Инициализация ProxyManager
        
        Args:
            country_filter: Фильтр по странам (список кодов стран)
        """
        self.country_filter = [c.upper() for c in country_filter] if country_filter else PREFERRED_COUNTRIES
        self.failed_proxies = set()
        self.successful_proxies = []
        
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
            
            # Пробуем получить количество страниц
            try:
                total_pages = get_pages_count_with_driver(driver)
                if total_pages and total_pages > 0:
                    logger.info(f"Прокси работает! Найдено {total_pages} страниц")
                    return True, {'total_pages': total_pages}
            except Exception as e:
                logger.debug(f"Не удалось получить количество страниц: {e}")
            
            # Проверяем наличие товаров
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            products = soup.select("div.product.product-plate")
            if products:
                logger.info(f"Прокси работает! Найдено {len(products)} товаров")
                return True, {}
            
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
    
    def get_working_proxies(self, min_count: int = 10, max_to_check: int = 100) -> List[Dict]:
        """
        Получает рабочие прокси (последовательно, без многопоточности)
        
        Args:
            min_count: Минимальное количество рабочих прокси
            max_to_check: Максимальное количество прокси для проверки
            
        Returns:
            Список рабочих прокси
        """
        # Загружаем прокси
        proxies = self._load_proxies()
        if not proxies:
            logger.warning("Нет прокси для проверки, загружаем...")
            if not self.download_proxies(force_update=True):
                return []
            proxies = self._load_proxies()
        
        # Фильтруем уже проверенные
        successful_keys = {f"{p['ip']}:{p['port']}" for p in self.successful_proxies}
        failed_keys = self.failed_proxies
        
        proxies_to_check = []
        for proxy in proxies:
            proxy_key = f"{proxy['ip']}:{proxy['port']}"
            if proxy_key not in successful_keys and proxy_key not in failed_keys:
                proxies_to_check.append(proxy)
        
        if len(proxies_to_check) > max_to_check:
            proxies_to_check = proxies_to_check[:max_to_check]
        
        logger.info(f"Проверяем {len(proxies_to_check)} прокси (нужно минимум {min_count} рабочих)...")
        
        working_proxies = []
        
        # Последовательная проверка
        for i, proxy in enumerate(proxies_to_check, 1):
            if len(working_proxies) >= min_count:
                break
            
            logger.info(f"[{i}/{len(proxies_to_check)}] Проверка прокси {proxy['ip']}:{proxy['port']}...")
            
            # Базовая проверка
            basic_ok, basic_info = self.validate_proxy_basic(proxy)
            if not basic_ok:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
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
                self.successful_proxies.append(working_proxy)
                logger.success(f"✓ Найден рабочий прокси: {proxy['ip']}:{proxy['port']} ({len(working_proxies)}/{min_count})")
            else:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                self.failed_proxies.add(proxy_key)
        
        # Сохраняем успешные прокси
        self.save_successful_proxies()
        
        logger.info(f"Найдено {len(working_proxies)} рабочих прокси")
        return working_proxies
    
    def get_next_proxy(self) -> Optional[Dict]:
        """Получает следующий рабочий прокси из списка"""
        if not self.successful_proxies:
            return None
        
        # Простая ротация
        proxy = self.successful_proxies[0]
        self.successful_proxies = self.successful_proxies[1:] + [proxy]
        return proxy

