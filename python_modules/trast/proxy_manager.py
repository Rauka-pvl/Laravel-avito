import os
import json
import random
import re
import requests
import logging
import urllib3
import time
import threading
import queue
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

# Пробуем импортировать cloudscraper для обхода Cloudflare
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
    # logger еще не инициализирован, выведем предупреждение позже

logger = logging.getLogger("trast.proxy_manager")

class ProxyManager:
    def __init__(self, cache_dir: str = None, country_filter = None):
        """
        Инициализация ProxyManager
        
        Args:
            cache_dir: Директория для кэша прокси
            country_filter: Фильтр по странам. Может быть:
                - str: одна страна (например, "RU")
                - list: список стран (например, ["RU", "BY", "KZ"])
                - None: все страны
        """
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(__file__), "proxy_cache")
        self.proxies_file = os.path.join(self.cache_dir, "proxies.json")
        self.last_update_file = os.path.join(self.cache_dir, "last_update.txt")
        self.successful_proxies_file = os.path.join(self.cache_dir, "successful_proxies.json")
        self.current_proxy_index = 0
        self.failed_proxies = set()
        self.proxies = []
        self.successful_proxies = []  # Список успешных прокси в памяти
        self.validation_cache = {}
        
        # Thread-safety: блокировка для доступа к критическим данным
        self.lock = threading.Lock()
        
        # Мапа для закрепления прокси за потоками (thread_id -> proxy)
        self.thread_proxies = {}
        
        # Нормализуем country_filter - всегда список (uppercase)
        if country_filter is None:
            self.country_filter = None
        elif isinstance(country_filter, str):
            self.country_filter = [country_filter.upper()]
        elif isinstance(country_filter, list):
            self.country_filter = [c.upper() for c in country_filter]
        else:
            self.country_filter = None
        
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Загружаем успешные прокси при инициализации
        self.successful_proxies = self.load_successful_proxies()
        self._sort_successful_proxies()
        if self.successful_proxies:
            logger.info(f"Загружено {len(self.successful_proxies)} успешных прокси из кэша")
        
        if self.country_filter:
            countries_str = ", ".join(self.country_filter)
            logger.info(f"ProxyManager инициализирован с фильтром стран: {countries_str}")
        else:
            logger.info("ProxyManager инициализирован без фильтра по стране")
        
    def _parse_proxymania_page(self, page_num: int = 1) -> List[Dict]:
        """Парсит одну страницу прокси с proxymania.su
        
        Args:
            page_num: Номер страницы (начинается с 1)
            
        Returns:
            List[Dict]: Список прокси с этой страницы
        """
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
            
            # Находим таблицу
            table = soup.select_one('table.table_proxychecker')
            if not table:
                logger.debug(f"Таблица не найдена на странице {page_num} proxymania.su")
                return []
            
            # Находим все строки в tbody
            rows = table.select('tbody#resultTable tr')
            proxies = []
            
            # Маппинг названий стран в коды ISO
            country_name_to_code = {
                'Russia': 'RU', 'Russian Federation': 'RU',
                'Poland': 'PL', 'Polska': 'PL',
                'Czech Republic': 'CZ', 'Czechia': 'CZ',
                'Germany': 'DE', 'Deutschland': 'DE',
                'Netherlands': 'NL', 'Holland': 'NL',
                'Sweden': 'SE', 'Sverige': 'SE',
                'France': 'FR', 'France': 'FR',
                'Romania': 'RO', 'România': 'RO',
                'Bulgaria': 'BG', 'България': 'BG',
                'Belarus': 'BY', 'Беларусь': 'BY',
                'Ukraine': 'UA', 'Україна': 'UA',
                'Kazakhstan': 'KZ', 'Казахстан': 'KZ',
                'Moldova': 'MD', 'Молдова': 'MD',
                'Georgia': 'GE', 'საქართველო': 'GE',
                'Armenia': 'AM', 'Հայաստան': 'AM',
                'Azerbaijan': 'AZ', 'Azərbaycan': 'AZ',
                'Lithuania': 'LT', 'Lietuva': 'LT',
                'Latvia': 'LV', 'Latvija': 'LV',
                'Estonia': 'EE', 'Eesti': 'EE',
                'Finland': 'FI', 'Suomi': 'FI',
                'Slovakia': 'SK', 'Slovensko': 'SK',
                'Hungary': 'HU', 'Magyarország': 'HU',
                'China': 'CN', '中国': 'CN',
                'Mongolia': 'MN', 'Монгол': 'MN',
                'United States': 'US', 'USA': 'US',
                'Indonesia': 'ID',
                'Vietnam': 'VN', 'Việt Nam': 'VN',
                'Bangladesh': 'BD',
                'Brazil': 'BR', 'Brasil': 'BR',
                'Singapore': 'SG',
                'Japan': 'JP', '日本': 'JP',
                'South Korea': 'KR', '한국': 'KR',
                'Hong Kong': 'HK',
                'Turkey': 'TR', 'Türkiye': 'TR',
                'Ecuador': 'EC',
                'Peru': 'PE',
                'Colombia': 'CO',
                'Iran': 'IR',
                'United Kingdom': 'GB', 'UK': 'GB',
                'Croatia': 'HR',
                'Spain': 'ES', 'España': 'ES',
                'Kenya': 'KE',
                'Venezuela': 'VE',
                'Costa Rica': 'CR',
                'Argentina': 'AR',
                'India': 'IN',
                'Ghana': 'GH',
                'Canada': 'CA',
                'Montenegro': 'ME',
                'Philippines': 'PH',
            }
            
            for row in rows:
                try:
                    cells = row.select('td')
                    if len(cells) < 5:
                        continue
                    
                    # Прокси (IP:PORT)
                    proxy_cell = cells[0]
                    proxy_text = proxy_cell.get_text(strip=True)
                    if ':' not in proxy_text:
                        continue
                    
                    ip, port = proxy_text.split(':', 1)
                    
                    # Страна
                    country_cell = cells[1]
                    country_name = country_cell.get_text(strip=True)
                    # Убираем флаг и оставляем только название
                    country_name = country_name.strip()
                    country_code = country_name_to_code.get(country_name, country_name[:2].upper() if len(country_name) >= 2 else 'UN')
                    
                    # Тип (SOCKS4, SOCKS5, HTTPS)
                    protocol_text = cells[2].get_text(strip=True).upper()
                    protocol_map = {
                        'SOCKS4': 'socks4',
                        'SOCKS5': 'socks5',
                        'HTTPS': 'https',
                        'HTTP': 'http',
                    }
                    protocol = protocol_map.get(protocol_text, protocol_text.lower())
                    
                    if protocol not in ['http', 'https', 'socks4', 'socks5']:
                        continue
                    
                    # Анонимность
                    anonymity = cells[3].get_text(strip=True)
                    
                    # Скорость (может быть "60 ms" или просто число)
                    speed_text = cells[4].get_text(strip=True)
                    speed = 0
                    try:
                        # Извлекаем число из строки типа "60 ms"
                        speed_match = re.search(r'(\d+)', speed_text)
                        if speed_match:
                            speed = int(speed_match.group(1))
                    except:
                        pass
                    
                    proxies.append({
                        'ip': ip,
                        'port': port,
                        'protocol': protocol,
                        'country': country_code,
                        'anonymity': anonymity,
                        'speed': speed,
                        'source': 'proxymania'
                    })
                    
                except Exception as e:
                    logger.debug(f"Ошибка при парсинге строки прокси с proxymania.su: {e}")
                    continue
            
            logger.debug(f"Страница {page_num} proxymania.su: найдено {len(proxies)} прокси")
            return proxies
            
        except Exception as e:
            logger.warning(f"Ошибка при парсинге страницы {page_num} proxymania.su: {e}")
            return []
    
    def _download_proxies_from_proxymania(self) -> List[Dict]:
        """Парсит все страницы прокси с proxymania.su
        
        Returns:
            List[Dict]: Список всех найденных прокси
        """
        all_proxies = []
        max_pages = 15  # Максимум страниц по информации пользователя
        
        logger.info("Парсинг прокси с proxymania.su...")
        
        # Пробуем определить количество страниц на первой странице
        try:
            url = "https://proxymania.su/free-proxy?page=1"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем пагинацию (например, "Последняя" или номера страниц)
            pagination = soup.select('.pagination a, .pager a, a[href*="page="]')
            if pagination:
                # Пробуем найти максимальный номер страницы
                page_numbers = []
                for link in pagination:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    # Ищем номер страницы в href или тексте
                    page_match = re.search(r'page=(\d+)', href)
                    if page_match:
                        page_numbers.append(int(page_match.group(1)))
                    elif text.isdigit():
                        page_numbers.append(int(text))
                
                if page_numbers:
                    detected_max = max(page_numbers)
                    if detected_max > 0 and detected_max < max_pages:
                        max_pages = detected_max
                        logger.info(f"Обнаружено {max_pages} страниц на proxymania.su")
        except Exception as e:
            logger.debug(f"Не удалось определить количество страниц на proxymania.su, используем максимум {max_pages}: {e}")
        
        for page_num in range(1, max_pages + 1):
            try:
                proxies = self._parse_proxymania_page(page_num)
                if not proxies:
                    # Если страница пустая, возможно достигли конца
                    logger.debug(f"Страница {page_num} пустая, возможно достигли конца")
                    # Проверяем еще одну страницу на всякий случай
                    if page_num < max_pages:
                        next_proxies = self._parse_proxymania_page(page_num + 1)
                        if not next_proxies:
                            logger.debug(f"Следующая страница {page_num + 1} тоже пустая, завершаем парсинг")
                            break
                    else:
                        break
                
                all_proxies.extend(proxies)
                logger.info(f"Страница {page_num}/{max_pages}: добавлено {len(proxies)} прокси, всего: {len(all_proxies)}")
                
                # Небольшая задержка между страницами
                time.sleep(random.uniform(1, 2))
                
            except Exception as e:
                logger.warning(f"Ошибка при парсинге страницы {page_num} proxymania.su: {e}")
                # Если ошибка на первой странице - прекращаем
                if page_num == 1:
                    logger.warning("Ошибка на первой странице proxymania.su, пропускаем этот источник")
                    break
                continue
        
        logger.info(f"С proxymania.su получено {len(all_proxies)} прокси")
        return all_proxies

    def download_proxies(self, force_update=False) -> bool:
        """Скачивает свежие прокси с Proxifly репозитория и proxymania.su
        
        Args:
            force_update: Если True, обновляет прокси даже если они свежие
        """
        try:
            if force_update:
                logger.info("[UPDATE] Принудительное обновление списка прокси...")
            
            all_proxies = []
            
            # 1. Загружаем прокси с Proxifly
            try:
                logger.info("Загрузка прокси с Proxifly...")
                # Страны СНГ
                CIS_COUNTRIES = ["RU", "BY", "KZ", "AM", "AZ", "GE", "KG", "MD", "TJ", "TM", "UZ", "UA"]
                
                # Если фильтр - одна страна из СНГ, можем использовать прямой URL
                # Но для списка стран загружаем все и фильтруем
                if self.country_filter and len(self.country_filter) == 1 and self.country_filter[0] in CIS_COUNTRIES:
                    country = self.country_filter[0]
                    logger.info(f"Скачивание прокси для страны {country} с Proxifly (прямая ссылка)...")
                    url = f"https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/countries/{country}/data.json"
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    proxies_data = response.json()
                else:
                    # Загружаем ВСЕ прокси и фильтруем по списку стран
                    logger.info("Скачивание всех прокси с Proxifly для фильтрации...")
                    url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json"
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    proxies_data = response.json()
                
                # Обрабатываем прокси с Proxifly
                for proxy in proxies_data:
                    protocol = proxy.get('protocol', '').lower()
                    
                    # Извлекаем страну из geolocation или напрямую
                    geolocation = proxy.get('geolocation', {})
                    country = (geolocation.get('country', '') or proxy.get('country', '')).upper()
                    
                    # Фильтр по странам (если задан)
                    if self.country_filter:
                        if country not in self.country_filter:
                            continue
                    
                    # Фильтр по протоколу
                    if protocol not in ['http', 'https', 'socks4', 'socks5']:
                        continue
                    
                    port = proxy.get('port', '')
                    # Преобразуем порт в строку, если это число
                    if isinstance(port, int):
                        port = str(port)
                    
                    all_proxies.append({
                        'ip': proxy.get('ip', ''),
                        'port': port,
                        'protocol': protocol,
                        'country': country,
                        'anonymity': proxy.get('anonymity', ''),
                        'speed': proxy.get('speed', 0),
                        'source': 'proxifly'
                    })
                
                proxifly_count = len(all_proxies)
                logger.info(f"[PROXIFLY] Получено {proxifly_count} прокси с Proxifly")
                
            except Exception as e:
                logger.warning(f"[PROXIFLY] Ошибка при загрузке прокси с Proxifly: {e}")
                proxifly_count = 0
            
            # 2. Загружаем прокси с proxymania.su
            proxymania_count_before_filter = 0
            proxymania_count_after_filter = 0
            try:
                logger.info("[PROXYMANIA] Начинаем парсинг прокси с proxymania.su...")
                proxymania_proxies = self._download_proxies_from_proxymania()
                proxymania_count_before_filter = len(proxymania_proxies)
                logger.info(f"[PROXYMANIA] Спарсено {proxymania_count_before_filter} прокси с proxymania.su (до фильтрации)")
                
                # Фильтруем прокси с proxymania по странам
                for proxy in proxymania_proxies:
                    country = proxy.get('country', '').upper()
                    
                    # Фильтр по странам (если задан)
                    if self.country_filter:
                        if country not in self.country_filter:
                            continue
                    
                    all_proxies.append(proxy)
                    proxymania_count_after_filter += 1
                
                logger.info(f"[PROXYMANIA] Добавлено {proxymania_count_after_filter} прокси с proxymania.su после фильтрации по странам (отфильтровано: {proxymania_count_before_filter - proxymania_count_after_filter})")
                
            except Exception as e:
                logger.warning(f"[PROXYMANIA] Ошибка при загрузке прокси с proxymania.su: {e}")
                import traceback
                logger.debug(f"[PROXYMANIA] Traceback: {traceback.format_exc()}")
            
            # Удаляем дубликаты (по IP:PORT)
            seen = set()
            filtered_proxies = []
            for proxy in all_proxies:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in seen:
                    seen.add(proxy_key)
                    filtered_proxies.append(proxy)
            
            duplicates_removed = len(all_proxies) - len(filtered_proxies)
            logger.info(f"[MERGE] После удаления дубликатов: {len(filtered_proxies)} уникальных прокси (было {len(all_proxies)}, удалено дубликатов: {duplicates_removed})")
            
            # Статистика по странам и протоколам
            country_stats = {}
            protocol_stats = {}
            source_stats = {}
            for p in filtered_proxies:
                country = p['country']
                protocol = p['protocol'].upper()
                source = p.get('source', 'unknown')
                country_stats[country] = country_stats.get(country, 0) + 1
                protocol_stats[protocol] = protocol_stats.get(protocol, 0) + 1
                source_stats[source] = source_stats.get(source, 0) + 1
            
            logger.info("=" * 60)
            logger.info(f"[SUMMARY] ИТОГОВАЯ СТАТИСТИКА ПРОКСИ:")
            logger.info(f"  Всего уникальных прокси: {len(filtered_proxies)}")
            logger.info(f"  По источникам:")
            for source, count in source_stats.items():
                logger.info(f"    - {source}: {count} прокси")
            if self.country_filter:
                top_countries = dict(sorted(country_stats.items(), key=lambda x: x[1], reverse=True)[:15])
                logger.info(f"  Топ-15 стран по количеству прокси:")
                for country, count in top_countries.items():
                    logger.info(f"    - {country}: {count} прокси")
            logger.info(f"  По протоколам:")
            for protocol, count in sorted(protocol_stats.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"    - {protocol}: {count} прокси")
            logger.info("=" * 60)
            
            # Сохраняем прокси в файл
            with open(self.proxies_file, 'w', encoding='utf-8') as f:
                json.dump(filtered_proxies, f, ensure_ascii=False, indent=2)
            
            # Обновляем время последнего обновления
            with open(self.last_update_file, 'w') as f:
                f.write(datetime.now().isoformat())
            
            # Сброс кэша неудачных прокси - новый список нужно пробовать заново
            self.reset_failed_proxies()
            
            logger.info(f"[SAVE] Сохранено {len(filtered_proxies)} прокси в файл: {self.proxies_file}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании прокси: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def load_proxies(self) -> List[Dict]:
        """Загружает прокси из кэша"""
        try:
            if not os.path.exists(self.proxies_file):
                logger.warning("Файл прокси не найден")
                return []
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                proxies = json.load(f)
            
            logger.info(f"Загружено {len(proxies)} прокси из кэша")
            return proxies
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке прокси: {e}")
            return []
    
    def should_update_proxies(self) -> bool:
        """Проверяет, нужно ли обновить прокси (старше 1 часа)"""
        try:
            if not os.path.exists(self.last_update_file):
                return True
            
            with open(self.last_update_file, 'r') as f:
                last_update_str = f.read().strip()
            
            last_update = datetime.fromisoformat(last_update_str)
            return datetime.now() - last_update > timedelta(hours=1)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке времени обновления: {e}")
            return True
    
    def load_successful_proxies(self) -> List[Dict]:
        """Загружает список успешных прокси из файла"""
        try:
            if not os.path.exists(self.successful_proxies_file):
                return []
            
            with open(self.successful_proxies_file, 'r', encoding='utf-8') as f:
                proxies = json.load(f)
            
            # Фильтруем по фильтру стран если задан
            if self.country_filter:
                filtered = []
                for proxy in proxies:
                    country = proxy.get('country', '').upper()
                    if country in self.country_filter:
                        filtered.append(proxy)
                proxies = filtered
            
            proxies.sort(key=self._successful_proxy_sort_key, reverse=True)
            return proxies
            
        except Exception as e:
            logger.warning(f"Ошибка при загрузке успешных прокси: {e}")
            return []
    
    def save_successful_proxy(self, proxy: Dict):
        """Сохраняет успешный прокси в файл (thread-safe)"""
        with self.lock:
            try:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                
                # Проверяем, нет ли уже такого прокси
                for existing in self.successful_proxies:
                    existing_key = f"{existing['ip']}:{existing['port']}"
                    if existing_key == proxy_key:
                        # Обновляем дату последнего успешного использования
                        existing['last_success'] = datetime.now().isoformat()
                        existing['success_count'] = existing.get('success_count', 0) + 1
                        existing['country'] = proxy.get('country', existing.get('country', 'Unknown'))
                        existing['protocol'] = proxy.get('protocol', existing.get('protocol', 'http'))
                        self._sort_successful_proxies()
                        self._write_successful_proxies()
                        return
                
                # Добавляем новый прокси с метаданными
                proxy_with_meta = {
                    'ip': proxy['ip'],
                    'port': proxy['port'],
                    'protocol': proxy.get('protocol', 'http'),
                    'country': proxy.get('country', 'Unknown'),
                    'first_success': datetime.now().isoformat(),
                    'last_success': datetime.now().isoformat(),
                    'success_count': 1
                }
                
                self.successful_proxies.append(proxy_with_meta)
                self._sort_successful_proxies()
                self._write_successful_proxies()
                logger.info(f"Прокси {proxy_key} добавлен в список успешных")
                
            except Exception as e:
                logger.warning(f"Ошибка при сохранении успешного прокси: {e}")
    
    def remove_failed_successful_proxy(self, proxy: Dict):
        """Удаляет неработающий прокси из списка успешных (thread-safe)"""
        with self.lock:
            try:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                
                original_count = len(self.successful_proxies)
                self.successful_proxies = [
                    p for p in self.successful_proxies 
                    if f"{p['ip']}:{p['port']}" != proxy_key
                ]
                
                if len(self.successful_proxies) < original_count:
                    self._write_successful_proxies()
                    logger.info(f"Прокси {proxy_key} удален из списка успешных (перестал работать)")
                
            except Exception as e:
                logger.warning(f"Ошибка при удалении неработающего прокси: {e}")
    
    def _write_successful_proxies(self):
        """Записывает список успешных прокси в файл (вызывается внутри lock)"""
        try:
            self._sort_successful_proxies()
            with open(self.successful_proxies_file, 'w', encoding='utf-8') as f:
                json.dump(self.successful_proxies, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Ошибка при записи успешных прокси: {e}")
    
    def _successful_proxy_sort_key(self, proxy: Dict):
        ts_candidates = [
            proxy.get('last_success'),
            proxy.get('first_success')
        ]
        for ts in ts_candidates:
            if ts:
                try:
                    return datetime.fromisoformat(ts)
                except ValueError:
                    continue
        return datetime.min

    def _sort_successful_proxies(self):
        """Сортирует успешные прокси по дате последнего успеха"""
        if not self.successful_proxies:
            return
        self.successful_proxies.sort(key=self._successful_proxy_sort_key, reverse=True)
    
    def _store_validation_context(self, proxy: Dict, context: Dict):
        """Сохраняет результат последней удачной валидации прокси для дальнейшего использования"""
        try:
            proxy_key = f"{proxy['ip']}:{proxy['port']}"
            enriched_context = {
                "proxy": proxy_key,
                "ip": proxy.get('ip'),
                "port": proxy.get('port'),
                "protocol": proxy.get('protocol'),
                "timestamp": datetime.now().isoformat(),
            }
            if context:
                enriched_context.update({k: v for k, v in context.items() if v is not None})
            self.validation_cache[proxy_key] = enriched_context
        except Exception as e:
            logger.debug(f"Не удалось сохранить контекст валидации для прокси: {e}")
    
    def _analyze_trast_catalog_page(self, html: str) -> Dict[str, Optional[int]]:
        """
        Анализирует HTML страницы каталога Trast на предмет блокировок, наличия карточек и пагинации.
        Возвращает словарь с флагами и извлечённым количеством страниц.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("  [ERROR] BeautifulSoup не установлен — невозможно проанализировать HTML каталога")
            return {
                "is_blocked": True,
                "has_products": False,
                "has_pagination": False,
                "total_pages": None,
                "pagination_items": 0,
            }
        
        soup = BeautifulSoup(html, "html.parser")
        page_source_lower = html.lower()
        
        block_indicators = [
            "cloudflare",
            "checking your browser",
            "just a moment",
            "service temporarily unavailable",
            "temporarily unavailable",
            "temporary unavailable",
            "access denied",
            "ошибка 503",
            "error 503",
            "ошибка 403",
            "error 403",
            "ошибка 404",
            "error 404",
            "forbidden",
            "blocked",
            "captcha",
            "please enable javascript",
            "attention required",
            "временно недоступ",
        ]
        
        is_blocked = any(indicator in page_source_lower for indicator in block_indicators)
        products = soup.select("div.product.product-plate")
        pagination_items = soup.select(".facetwp-pager .facetwp-page")
        has_products = bool(products)
        has_pagination = bool(pagination_items)
        
        total_pages = None
        if pagination_items:
            last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
            if last_page_el and last_page_el.has_attr("data-page"):
                try:
                    total_pages = int(last_page_el["data-page"])
                except (ValueError, TypeError):
                    total_pages = None
            else:
                max_page = 0
                for page_el in pagination_items:
                    data_page = page_el.get("data-page")
                    text_value = page_el.get_text(strip=True)
                    candidate = None
                    if data_page:
                        try:
                            candidate = int(data_page)
                        except ValueError:
                            candidate = None
                    elif text_value.isdigit():
                        candidate = int(text_value)
                    if candidate and candidate > max_page:
                        max_page = candidate
                if max_page > 0:
                    total_pages = max_page
        
        return {
            "is_blocked": is_blocked,
            "has_products": has_products,
            "has_pagination": has_pagination,
            "total_pages": total_pages,
            "pagination_items": len(pagination_items),
        }
    
    def get_proxy_queue_stats(self) -> Dict[str, int]:
        """
        Возвращает статистику очереди прокси:
        - total: всего прокси в кэше после фильтров
        - available: доступно для проверки (не в failed и не в successful)
        - successful: количество успешных прокси в памяти
        - failed: количество прокси, помеченных как неработающие
        """
        stats = {
            "total": 0,
            "available": 0,
            "successful": len(self.successful_proxies),
            "failed": len(self.failed_proxies),
        }
        
        try:
            if not os.path.exists(self.proxies_file):
                return stats
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                all_proxies = json.load(f)
            
            stats["total"] = len(all_proxies)
            successful_keys = {f"{p['ip']}:{p['port']}" for p in self.successful_proxies}
            
            available_count = 0
            for proxy in all_proxies:
                protocol = proxy.get('protocol', '').lower()
                country = proxy.get('country', '').upper()
                if protocol not in ['http', 'https', 'socks4', 'socks5']:
                    continue
                if self.country_filter and country not in self.country_filter:
                    continue
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key in self.failed_proxies or proxy_key in successful_keys:
                    continue
                available_count += 1
            
            stats["available"] = available_count
        except Exception as stats_error:
            logger.debug(f"Не удалось собрать статистику по очереди прокси: {stats_error}")
        
        return stats

    def validate_proxy(self, proxy: Dict, timeout: int = 5) -> bool:
        """Проверяет работоспособность прокси"""
        try:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            if protocol in ['http', 'https']:
                # HTTP/HTTPS прокси
                proxy_url = f"{protocol}://{ip}:{port}"
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            elif protocol in ['socks4', 'socks5']:
                # SOCKS прокси
                proxy_url = f"{protocol}://{ip}:{port}"
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            else:
                logger.debug(f"Прокси {ip}:{port} - неподдерживаемый протокол: {protocol}")
                return False
            
            # Тестируем прокси на простом запросе
            response = requests.get(
                'https://ifconfig.me/ip',
                proxies=proxies,
                timeout=timeout
            )
            
            if response.status_code == 200:
                logger.debug(f"Прокси {ip}:{port} ({protocol}) работает")
                return True
            else:
                logger.debug(f"Прокси {ip}:{port} ({protocol}) - HTTP статус {response.status_code}")
                return False
                
        except requests.exceptions.ConnectTimeout:
            logger.debug(f"Прокси {ip}:{port} ({protocol}) - таймаут подключения")
            return False
        except requests.exceptions.ReadTimeout:
            logger.debug(f"Прокси {ip}:{port} ({protocol}) - таймаут чтения")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.debug(f"Прокси {ip}:{port} ({protocol}) - ошибка подключения: {str(e)}")
            return False
        except requests.exceptions.ProxyError as e:
            logger.debug(f"Прокси {ip}:{port} ({protocol}) - ошибка прокси: {str(e)}")
            return False
        except Exception as e:
            logger.debug(f"Прокси {ip}:{port} ({protocol}) - неизвестная ошибка: {str(e)}")
            return False
    
    def get_external_ip(self, proxies: dict = None, timeout: int = 10) -> str:
        """Получает внешний IP через прокси"""
        try:
            service = "https://ifconfig.me/ip"
            response = requests.get(service, proxies=proxies, timeout=timeout, verify=False)
            if response.status_code == 200:
                return response.text.strip()
            return "Не удалось определить"
        except Exception as e:
            logger.debug(f"Ошибка при получении внешнего IP: {e}")
            return "Ошибка"
    
    def validate_proxy_basic(self, proxy: Dict, timeout: int = 10):
        """
        Базовая проверка работоспособности прокси (этап 1)
        Проверяет, работает ли прокси вообще через тестовые сервисы
        
        Returns:
            (is_working, proxy_info) - работает ли прокси и информация о нем
        """
        try:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            logger.info(f"[ШАГ 1] Базовая проверка прокси {ip}:{port} ({protocol.upper()})...")
            
            if protocol in ['http', 'https']:
                proxy_url = f"{protocol}://{ip}:{port}"
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            elif protocol in ['socks4', 'socks5']:
                proxy_url = f"socks5h://{ip}:{port}" if protocol == 'socks5' else f"socks4://{ip}:{port}"
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            else:
                logger.info(f"Неподдерживаемый протокол: {protocol}")
                return False, {}
            
            # Проверяем через простой тестовый сервис
            test_urls = [
                "https://ifconfig.me/ip"
            ]
            
            working_url = None
            external_ip = None
            
            for test_url in test_urls:
                try:
                    logger.debug(f"   Тестируем через {test_url}...")
                    response = requests.get(test_url, proxies=proxies, timeout=timeout, verify=False)
                    if response.status_code == 200:
                        working_url = test_url
                        # Извлекаем IP из ответа
                        external_ip = response.text.strip()
                        
                        if external_ip and len(external_ip.split('.')) == 4:  # Проверяем что это похоже на IP
                            logger.info(f"   [OK] Прокси РАБОТАЕТ! Внешний IP: {external_ip}")
                            return True, {
                                'ip': ip,
                                'port': port,
                                'protocol': protocol,
                                'external_ip': external_ip,
                                'proxies': proxies
                            }
                        break
                except Exception as e:
                    logger.debug(f"   Не удалось подключиться через {test_url}: {e}")
                    continue
            
            logger.debug(f"   Прокси НЕ РАБОТАЕТ (не смог подключиться к тестовым сервисам)")
            return False, {}
            
        except Exception as e:
            logger.error(f"   [ERROR] Ошибка при базовой проверке прокси: {e}")
            return False, {}
    
    def validate_proxy_for_trast_selenium(self, proxy: Dict, timeout: int = 60, use_chrome: bool = False):
        """Проверяет прокси через Selenium (Firefox или Chrome/Chromium)"""
        context = {
            "total_pages": None,
            "html": None,
            "source": None,
        }
        try:
            from selenium import webdriver
            from bs4 import BeautifulSoup
            import time
            import random
            import traceback
            
            # Пробуем Chrome, если не получилось - Firefox
            if use_chrome:
                try:
                    if self._validate_with_chrome(proxy, timeout, context):
                        context.setdefault("source", "selenium_chrome")
                        return True, context
                except Exception as e:
                    logger.warning(f"  [WARNING]  Chrome не доступен: {str(e)[:200]}")
                    logger.info(f"  Пробуем Firefox...")
                    # Fallback на Firefox
            
            # Используем Firefox
            try:
                if self._validate_with_firefox(proxy, timeout, context):
                    context.setdefault("source", "selenium_firefox")
                    return True, context
            except Exception as e:
                logger.error(f"  [ERROR] Ошибка Firefox: {str(e)}")
                logger.debug(f"  Traceback: {traceback.format_exc()}")
                # Пробуем Chrome как fallback
                try:
                    logger.info(f"  Пробуем Chrome как альтернативу...")
                    if self._validate_with_chrome(proxy, timeout, context):
                        context.setdefault("source", "selenium_chrome")
                        return True, context
                except Exception as chrome_error:
                    logger.error(f"  [ERROR] Chrome тоже не работает: {str(chrome_error)[:200]}")
                    logger.debug(f"  Chrome traceback: {traceback.format_exc()}")
                    return False, context
                    
        except Exception as e:
            logger.error(f"  [ERROR] Критическая ошибка Selenium: {str(e)}")
            logger.debug(f"  Полный traceback: {traceback.format_exc()}")
            return False, context
        
        return False, context
    
    def _validate_with_firefox(self, proxy: Dict, timeout: int, context: Optional[Dict] = None) -> bool:
        """Проверка через Firefox"""
        from selenium import webdriver
        from selenium.webdriver.firefox.service import Service
        from selenium.webdriver.firefox.options import Options
        import geckodriver_autoinstaller
        import time
        import random
        
        protocol = proxy.get('protocol', 'http').lower()
        ip = proxy['ip']
        port = proxy['port']
        
        logger.info(f"  [FIREFOX] Проверка прокси {ip}:{port} ({protocol.upper()})...")
        
        # Устанавливаем geckodriver
        try:
            geckodriver_autoinstaller.install()
        except Exception as e:
            logger.warning(f"  [WARNING]  Ошибка установки geckodriver: {e}")
        
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        # Обход Cloudflare - отключаем автоматизацию ПЕРЕД созданием драйвера
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        options.set_preference("marionette.logging", "FATAL")
        
        # Случайный User-Agent (реалистичные)
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]
        selected_ua = random.choice(user_agents)
        options.set_preference("general.useragent.override", selected_ua)
        logger.debug(f"  User-Agent: {selected_ua}")
        
        # Настройка прокси - ВАЖНО для обхода блокировок
        logger.debug(f"  Настраиваем прокси {ip}:{port} ({protocol.upper()}) в Firefox...")
        if protocol in ['http', 'https']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", ip)
            options.set_preference("network.proxy.http_port", int(port))
            options.set_preference("network.proxy.ssl", ip)
            options.set_preference("network.proxy.ssl_port", int(port))
            options.set_preference("network.proxy.share_proxy_settings", True)
            logger.debug(f"  Прокси настроен: HTTP/HTTPS -> {ip}:{port}")
        elif protocol in ['socks4', 'socks5']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", ip)
            options.set_preference("network.proxy.socks_port", int(port))
            if protocol == 'socks5':
                options.set_preference("network.proxy.socks_version", 5)
            else:
                options.set_preference("network.proxy.socks_version", 4)
            options.set_preference("network.proxy.socks_remote_dns", True)
            logger.debug(f"  Прокси настроен: {protocol.upper()} -> {ip}:{port}")
        else:
            logger.warning(f"  [WARNING]  Неподдерживаемый протокол прокси: {protocol}")
            return False
        
        # Дополнительные настройки скрытия
        options.set_preference("privacy.trackingprotection.enabled", True)
        options.set_preference("media.peerconnection.enabled", False)  # Отключаем WebRTC
        
        # Настройки для обхода детекции
        options.set_preference("browser.safebrowsing.enabled", False)
        options.set_preference("toolkit.telemetry.enabled", False)
        
        # Создаем драйвер
        logger.debug(f"  Создаем Firefox драйвер с прокси...")
        service = Service()
        driver = None
        try:
            driver = webdriver.Firefox(service=service, options=options)
            # НЕ устанавливаем таймауты сразу - пусть драйвер использует дефолтные
            # Таймауты будем устанавливать только при необходимости, но не сразу после создания
            logger.info(f"  [OK] Firefox драйвер создан")
            
            # ПРОВЕРКА: Проверяем, что прокси действительно используется
            logger.debug(f"  [ПРОВЕРКА ПРОКСИ] Проверяем внешний IP через браузер...")
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                import re
                
                ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
                extracted_ip = None
                last_source_preview = ""
                
                for attempt_ip in range(3):
                    driver.get("https://ifconfig.me/ip")
                    try:
                        body_element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                        page_text = body_element.text.strip()
                    except Exception:
                        page_text = driver.page_source.strip()
                    
                    ip_matches = re.findall(ip_pattern, page_text)
                    if ip_matches:
                        extracted_ip = ip_matches[0]
                        break
                    
                    last_source_preview = page_text[:200] + "..." if len(page_text) > 200 else page_text
                    time.sleep(1)
                
                if extracted_ip:
                    logger.info(f"  [OK] Прокси работает! IP браузера: {extracted_ip} (ожидалось: {ip})")
                    if extracted_ip != ip:
                        logger.debug(f"  Примечание: IP браузера ({extracted_ip}) отличается от IP прокси ({ip}) - это нормально")
                else:
                    logger.warning(f"  [WARNING]  Не удалось получить IP через браузер (последний ответ: {last_source_preview})")
            except Exception as ip_check_error:
                logger.warning(f"  [WARNING]  Не удалось проверить IP через браузер: {str(ip_check_error)[:100]}")
            # В Firefox navigator.webdriver нельзя переопределить после создания драйвера
            # Поэтому мы полагаемся на настройки preferences (dom.webdriver.enabled = False)
            # Выполняем только безопасные скрипты, которые не трогают webdriver
            
            # Простые скрипты для улучшения имитации браузера
            safe_scripts = """
            // Добавляем плагины (если возможно)
            try {
                if (!navigator.plugins || navigator.plugins.length === 0) {
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3],
                        configurable: true
                    });
                }
            } catch(e) {}
            
            // Chrome объект (если сайт проверяет)
            if (!window.chrome) {
                window.chrome = {
                    runtime: {}
                };
            }
            """
            
            try:
                driver.execute_script(safe_scripts)
            except:
                pass  # Игнорируем ошибки скриптов
            
            # Имитация человеческого поведения - сначала идем на главную
            logger.info(f"  [SELENIUM] Имитация поведения пользователя...")
            logger.info(f"  [SELENIUM] Шаг 1: Открываем главную страницу...")
            try:
                driver.get("https://trast-zapchast.ru/")
                time.sleep(random.uniform(2, 4))
            except Exception as page_error:
                error_msg = str(page_error).lower()
                # Проверяем на специфичные ошибки подключения
                if "nssfailure" in error_msg or "connection" in error_msg or "interrupted" in error_msg:
                    logger.error(f"  [ERROR] Ошибка подключения к trast-zapchast.ru через прокси: {str(page_error)[:200]}")
                    logger.error(f"  [ERROR] Прокси не может подключиться к целевому сайту")
                    return False
                elif "timeout" in error_msg or "timed out" in error_msg:
                    logger.error(f"  [ERROR] Таймаут при подключении к trast-zapchast.ru: {str(page_error)[:200]}")
                    logger.error(f"  [ERROR] Прокси слишком медленный или недоступен для целевого сайта")
                    return False
                else:
                    # Другие ошибки - пробуем продолжить, но логируем
                    logger.warning(f"  [WARNING]  Ошибка при открытии главной страницы: {str(page_error)[:200]}")
                    # Не возвращаем False сразу, пробуем продолжить
            
            # Скролл
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(random.uniform(1, 2))
            
            # Переходим на shop
            logger.info(f"  [SELENIUM] Шаг 2: Переходим на страницу shop...")
            site_url = "https://trast-zapchast.ru/shop/"
            try:
                driver.get(site_url)
                time.sleep(random.uniform(5, 8))
            except Exception as shop_error:
                error_msg = str(shop_error).lower()
                # Проверяем на специфичные ошибки подключения
                if "nssfailure" in error_msg or "connection" in error_msg or "interrupted" in error_msg:
                    logger.error(f"  [ERROR] Ошибка подключения к shop через прокси: {str(shop_error)[:200]}")
                    logger.error(f"  [ERROR] Прокси не может подключиться к целевому сайту")
                    return False
                elif "timeout" in error_msg or "timed out" in error_msg:
                    logger.error(f"  [ERROR] Таймаут при подключении к shop: {str(shop_error)[:200]}")
                    logger.error(f"  [ERROR] Прокси слишком медленный или недоступен для целевого сайта")
                    return False
                else:
                    logger.error(f"  [ERROR] Ошибка при открытии shop: {str(shop_error)[:200]}")
                    return False
            
            # Имитируем скролл
            driver.execute_script("window.scrollTo(0, 100);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(1)
            
            # Проверяем Cloudflare
            page_source_lower = driver.page_source.lower()
            max_wait = 30
            wait_time = 0
            
            while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or "just a moment" in page_source_lower) and wait_time < max_wait:
                logger.info(f"  [WAIT] Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
                time.sleep(3)
                driver.refresh()
                time.sleep(2)
                page_source_lower = driver.page_source.lower()
                wait_time += 5
            
            if wait_time >= max_wait:
                logger.warning(f"  [ERROR] Cloudflare проверка не пройдена")
                return False
            
            page_source = driver.page_source
            analysis = self._analyze_trast_catalog_page(page_source)
            logger.debug(
                "  [ANALYZE] FIREFOX: blocked=%s, products=%s, pagination=%s, items=%s, total_pages=%s",
                analysis["is_blocked"],
                analysis["has_products"],
                analysis["has_pagination"],
                analysis["pagination_items"],
                analysis["total_pages"],
            )
            
            if context is not None:
                context.setdefault("source", "selenium_firefox")
                context.setdefault("html", page_source)
                if analysis["total_pages"]:
                    context["total_pages"] = analysis["total_pages"]
            
            if analysis["is_blocked"]:
                logger.warning("  [ERROR] FIREFOX: Страница каталога содержит признаки блокировки/заглушки")
                return False
            
            if analysis["total_pages"]:
                logger.info(f"  [OK][OK][OK] FIREFOX УСПЕШНО! Получено количество страниц: {analysis['total_pages']}")
                return True
            
            if analysis["has_products"]:
                logger.info("  [OK] FIREFOX: Найдены карточки товаров, но пагинация отсутствует (будем работать в fallback режиме)")
                return True
            
            logger.warning("  [ERROR] FIREFOX: Страница не содержит карточек и пагинации — считаем прокси заблокированным")
            return False
                    
        except Exception as e:
            import traceback
            logger.error(f"  [ERROR] Ошибка Firefox: {str(e)}")
            logger.debug(f"  Полный traceback:\n{traceback.format_exc()}")
            return False
        finally:
            if driver:
                driver.quit()
    
    def _validate_with_chrome(self, proxy: Dict, timeout: int, context: Optional[Dict] = None) -> bool:
        """Проверка через Chrome/Chromium"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.common.by import By
            import time
            import random
            import traceback
            
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            logger.info(f"  [CHROME] Проверка прокси {ip}:{port} ({protocol.upper()})...")
            
            # Устанавливаем chromedriver
            try:
                driver_path = ChromeDriverManager().install()
                logger.debug(f"  ChromeDriver установлен: {driver_path}")
            except Exception as e:
                logger.error(f"  [ERROR] Ошибка установки ChromeDriver: {e}")
                raise
            
            options = Options()
            options.add_argument("--headless=new")  # Новый headless режим
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")  # КРИТИЧНО для обхода детекции
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Случайный User-Agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ]
            selected_ua = random.choice(user_agents)
            options.add_argument(f"--user-agent={selected_ua}")
            logger.debug(f"  User-Agent: {selected_ua}")
            
            # Настройка прокси для Chrome
            logger.debug(f"  Настраиваем прокси {ip}:{port} ({protocol.upper()}) в Chrome...")
            # ВАЖНО: Chrome имеет проблемы с SOCKS прокси через --proxy-server
            # SOCKS прокси часто вызывают ERR_TUNNEL_CONNECTION_FAILED
            if protocol in ['http', 'https']:
                proxy_arg = f"{protocol}://{ip}:{port}"
            elif protocol in ['socks4', 'socks5']:
                # Chrome может иметь проблемы с SOCKS, но пробуем
                logger.warning(f"  [WARNING]  Chrome может иметь проблемы с {protocol.upper()} прокси (ERR_TUNNEL_CONNECTION_FAILED)")
                proxy_arg = f"socks5://{ip}:{port}" if protocol == 'socks5' else f"socks4://{ip}:{port}"
            else:
                logger.warning(f"  [WARNING]  Неподдерживаемый протокол: {protocol}")
                return False
            
            options.add_argument(f"--proxy-server={proxy_arg}")
            logger.debug(f"  Прокси настроен: {proxy_arg}")
            
            # Создаем драйвер
            logger.debug(f"  Создаем Chrome драйвер...")
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            # НЕ устанавливаем таймауты сразу - пусть драйвер использует дефолтные
            # Таймауты будем устанавливать только при необходимости, но не сразу после создания
            logger.info(f"  [OK] Chrome драйвер создан")
            
            try:
                # Обход детекции через скрипты (Chrome позволяет это делать)
                stealth_scripts = """
                // Скрываем webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });
                
                // Chrome объект
                window.chrome = {
                    runtime: {}
                };
                
                // Permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Плагины
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                    configurable: true
                });
                
                // Languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en-US', 'en'],
                    configurable: true
                });
                """
                driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                    'source': stealth_scripts
                })
                
                # ПРОВЕРКА: Проверяем, что прокси используется
                logger.debug(f"  [ПРОВЕРКА ПРОКСИ] Проверяем внешний IP через Chrome...")
                try:
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    import re
                    
                    ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
                    extracted_ip = None
                    last_source_preview = ""
                    
                    for attempt_ip in range(3):
                        driver.get("https://ifconfig.me/ip")
                        try:
                            page_text = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "body"))
                            ).text.strip()
                        except Exception:
                            page_text = driver.page_source.strip()
                        
                        ip_matches = re.findall(ip_pattern, page_text)
                        if ip_matches:
                            extracted_ip = ip_matches[0]
                            break
                        
                        last_source_preview = page_text[:200] + "..." if len(page_text) > 200 else page_text
                        time.sleep(1)
                    
                    if extracted_ip:
                        logger.info(f"  [OK] Прокси работает! IP Chrome: {extracted_ip} (прокси: {ip})")
                    else:
                        logger.warning(f"  [WARNING]  Не удалось получить IP (последний ответ: {last_source_preview})")
                except Exception as ip_check_error:
                    logger.warning(f"  [WARNING]  Не удалось проверить IP: {str(ip_check_error)[:100]}")
                
                # Имитация человеческого поведения
                logger.info(f"  [CHROME] Имитация поведения пользователя...")
                logger.info(f"  [CHROME] Шаг 1: Открываем главную страницу...")
                try:
                    driver.get("https://trast-zapchast.ru/")
                    time.sleep(random.uniform(2, 4))
                except Exception as page_error:
                    error_msg = str(page_error).lower()
                    # Проверяем на специфичные ошибки подключения
                    if "tunnel_connection_failed" in error_msg or "err_tunnel" in error_msg:
                        logger.error(f"  [ERROR] Ошибка туннельного подключения через прокси: {str(page_error)[:200]}")
                        logger.error(f"  [ERROR] Прокси не может установить туннель к целевому сайту (обычно для SOCKS)")
                        logger.error(f"  [ERROR] Рекомендуется использовать Firefox для SOCKS прокси")
                        return False
                    elif "connection" in error_msg or "net::err_" in error_msg:
                        logger.error(f"  [ERROR] Ошибка подключения к trast-zapchast.ru через прокси: {str(page_error)[:200]}")
                        logger.error(f"  [ERROR] Прокси не может подключиться к целевому сайту")
                        return False
                    elif "timeout" in error_msg or "timed out" in error_msg:
                        logger.error(f"  [ERROR] Таймаут при подключении к trast-zapchast.ru: {str(page_error)[:200]}")
                        logger.error(f"  [ERROR] Прокси слишком медленный или недоступен для целевого сайта")
                        return False
                    else:
                        # Другие ошибки - пробуем продолжить, но логируем
                        logger.warning(f"  [WARNING]  Ошибка при открытии главной страницы: {str(page_error)[:200]}")
                        # Не возвращаем False сразу, пробуем продолжить
                
                # Скролл
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                time.sleep(random.uniform(1, 2))
                
                # Переходим на shop
                logger.info(f"  [CHROME] Шаг 2: Переходим на страницу shop...")
                site_url = "https://trast-zapchast.ru/shop/"
                try:
                    driver.get(site_url)
                    time.sleep(random.uniform(5, 8))
                except Exception as shop_error:
                    error_msg = str(shop_error).lower()
                    # Проверяем на специфичные ошибки подключения
                    if "tunnel_connection_failed" in error_msg or "err_tunnel" in error_msg:
                        # ERR_TUNNEL_CONNECTION_FAILED может быть как для SOCKS, так и для неработающего HTTP прокси
                        logger.error(f"  [ERROR] Ошибка туннельного подключения к shop через прокси: {str(shop_error)[:200]}")
                        logger.error(f"  [ERROR] Прокси не может установить соединение к целевому сайту")
                        if protocol in ['socks4', 'socks5']:
                            logger.error(f"  [ERROR] Рекомендуется использовать Firefox для SOCKS прокси")
                        return False
                    elif "connection" in error_msg or "net::err_" in error_msg:
                        logger.error(f"  [ERROR] Ошибка подключения к shop через прокси: {str(shop_error)[:200]}")
                        logger.error(f"  [ERROR] Прокси не может подключиться к целевому сайту")
                        return False
                    elif "timeout" in error_msg or "timed out" in error_msg:
                        logger.error(f"  [ERROR] Таймаут при подключении к shop: {str(shop_error)[:200]}")
                        logger.error(f"  [ERROR] Прокси слишком медленный или недоступен для целевого сайта")
                        return False
                    else:
                        logger.error(f"  [ERROR] Ошибка при открытии shop: {str(shop_error)[:200]}")
                        return False
                
                # Имитируем скролл
                driver.execute_script("window.scrollTo(0, 100);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 300);")
                time.sleep(1)
                
                # Проверяем Cloudflare
                page_source_lower = driver.page_source.lower()
                max_wait = 30
                wait_time = 0
                
                while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or "just a moment" in page_source_lower) and wait_time < max_wait:
                    logger.info(f"  [WAIT] Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
                    time.sleep(3)
                    driver.refresh()
                    time.sleep(2)
                    page_source_lower = driver.page_source.lower()
                    wait_time += 5
                
                if wait_time >= max_wait:
                    logger.warning(f"  [ERROR] Cloudflare проверка не пройдена")
                    return False
                
                page_source = driver.page_source
                analysis = self._analyze_trast_catalog_page(page_source)
                logger.debug(
                    "  [ANALYZE] CHROME: blocked=%s, products=%s, pagination=%s, items=%s, total_pages=%s",
                    analysis["is_blocked"],
                    analysis["has_products"],
                    analysis["has_pagination"],
                    analysis["pagination_items"],
                    analysis["total_pages"],
                )
                
                if context is not None:
                    context.setdefault("source", "selenium_chrome")
                    context.setdefault("html", page_source)
                    if analysis["total_pages"]:
                        context["total_pages"] = analysis["total_pages"]
                
                if analysis["is_blocked"]:
                    logger.warning("  [ERROR] CHROME: Страница каталога содержит признаки блокировки/заглушки")
                    return False
                
                if analysis["total_pages"]:
                    logger.info(f"  [OK][OK][OK] CHROME УСПЕШНО! Получено количество страниц: {analysis['total_pages']}")
                    return True
                
                if analysis["has_products"]:
                    logger.info("  [OK] CHROME: Найдены карточки товаров, но пагинация отсутствует (fallback режим)")
                    return True
                
                logger.warning("  [ERROR] CHROME: Страница не содержит карточек и пагинации — считаем прокси заблокированным")
                return False
                        
            finally:
                driver.quit()
                
        except Exception as e:
            import traceback
            logger.error(f"  [ERROR] Ошибка Chrome: {str(e)}")
            logger.debug(f"  Полный traceback:\n{traceback.format_exc()}")
            return False
    
    def validate_proxy_for_trast(self, proxy: Dict, timeout: int = 30) -> bool:
        """Проверяет прокси: сначала базовая работоспособность, потом доступ к trast-zapchast.ru"""
        try:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            logger.debug(f"Проверяем прокси {ip}:{port} ({protocol.upper()})")
            
            # ШАГ 1: Базовая проверка работоспособности прокси
            is_basic_working, proxy_info = self.validate_proxy_basic(proxy, timeout=10)
            
            if not is_basic_working:
                logger.debug(f"Прокси {ip}:{port} не прошел базовую проверку")
                return False
            
            # Получаем proxies из базовой проверки
            proxies = proxy_info['proxies']
            external_ip = proxy_info.get('external_ip', 'Unknown')
            
            logger.debug(f"Базовая проверка пройдена! Внешний IP: {external_ip}, проверяем доступ к trast-zapchast.ru...")
            
            validation_context = {
                "total_pages": None,
                "html": None,
                "source": None,
                "external_ip": external_ip,
            }
            
            # СНАЧАЛА пробуем Selenium (самый эффективный способ обхода Cloudflare)
            logger.info(f"  [ШАГ 2.1] Пробуем Selenium (наиболее эффективный обход Cloudflare)...")
            
            # ВАЖНО: Для SOCKS прокси сразу используем Firefox (Chrome имеет проблемы с ERR_TUNNEL_CONNECTION_FAILED)
            protocol = proxy.get('protocol', 'http').lower()
            use_chrome_first = protocol in ['http', 'https']  # Chrome только для HTTP/HTTPS
            
            selenium_result = False
            selenium_context = {}
            if use_chrome_first:
                try:
                    logger.debug(f"  Пробуем Chrome/Chromium...")
                    selenium_result, selenium_context = self.validate_proxy_for_trast_selenium(proxy, timeout=60, use_chrome=True)
                except Exception as chrome_error:
                    logger.debug(f"  Chrome не доступен: {str(chrome_error)[:200]}")
                    selenium_result = False
            
            if not selenium_result:
                if use_chrome_first:
                    logger.debug(f"  Chrome не сработал, пробуем Firefox...")
                else:
                    logger.debug(f"  Для {protocol.upper()} прокси используем Firefox (Chrome не рекомендуется для SOCKS)...")
                selenium_result, selenium_context = self.validate_proxy_for_trast_selenium(proxy, timeout=60, use_chrome=False)
            
            if selenium_result:
                logger.info(f"[SUCCESS] Прокси {ip}:{port} работает через Selenium! Внешний IP: {external_ip}, количество страниц получено!")
                if selenium_context:
                    validation_context.update({k: v for k, v in selenium_context.items() if v is not None})
                validation_context.setdefault("source", selenium_context.get("source", "selenium"))
                self._store_validation_context(proxy, validation_context)
                return True
            
            logger.debug(f"  Selenium не сработал, пробуем cloudscraper/requests...")
            
            # Проверяем доступ к странице shop и пытаемся получить количество страниц
            site_url = "https://trast-zapchast.ru/shop/"
            
            logger.debug(f"Отправляем запрос к {site_url} через прокси {ip}:{port}...")
            
            # Используем cloudscraper для обхода Cloudflare (приоритет)
            if HAS_CLOUDSCRAPER:
                logger.debug(f"  Используем cloudscraper для обхода Cloudflare...")
                try:
                    import ssl
                    import urllib3
                    
                    ssl_context = ssl._create_unverified_context()
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    
                    # Создаем cloudscraper сессию с поддержкой прокси и кастомным SSL
                    scraper = cloudscraper.create_scraper(
                        browser={
                            'browser': 'chrome',
                            'platform': 'windows',
                            'desktop': True
                        },
                        ssl_context=ssl_context,
                        allow_brotli=True
                    )
                    scraper.allow_redirects = True
                    scraper.proxies.update(proxies)
                    scraper.verify = False
                    
                    response = scraper.get(site_url, timeout=timeout)
                    logger.debug(f"  cloudscraper успешно: HTTP {response.status_code}")
                    validation_context.update({
                        "source": "cloudscraper",
                        "html": response.text
                    })
                except Exception as e:
                    logger.debug(f"  Ошибка cloudscraper: {e}")
                    logger.debug(f"  Пробуем обычный requests...")
                    # Fallback на обычный requests
                    session = requests.Session()
                    session.proxies.update(proxies)
                    session.verify = False
                    session.allow_redirects = True
                    
                    # Подробные заголовки для имитации реального браузера
                    user_agents = [
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    ]
                    headers = {
                        'User-Agent': random.choice(user_agents),
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0',
                    }
                    session.headers.update(headers)
                    response = session.get(site_url, timeout=timeout)
                    validation_context.update({
                        "source": "requests",
                        "html": response.text
                    })
            else:
                # Обычный requests с заголовками (fallback если cloudscraper не установлен)
                logger.warning(f"  [WARNING]  cloudscraper не установлен, используем requests с заголовками...")
                logger.info(f"  Рекомендуется установить: pip install cloudscraper")
                session = requests.Session()
                session.proxies.update(proxies)
                session.verify = False
                session.allow_redirects = True
                
                user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                ]
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
                session.headers.update(headers)
                response = session.get(site_url, timeout=timeout)
                validation_context.update({
                    "source": "requests",
                    "html": response.text
                })
            
            logger.debug(f"  HTTP статус: {response.status_code}")
            logger.debug(f"  Размер ответа: {len(response.text)} байт")
            
            # Подробное логирование содержимого ответа
            if response.status_code == 200:
                analysis = self._analyze_trast_catalog_page(response.text)
                logger.debug(
                    "  [ANALYZE] REQUESTS: blocked=%s, products=%s, pagination=%s, items=%s, total_pages=%s",
                    analysis["is_blocked"],
                    analysis["has_products"],
                    analysis["has_pagination"],
                    analysis["pagination_items"],
                    analysis["total_pages"],
                )
                
                if analysis["is_blocked"]:
                    logger.debug("  Ответ содержит признаки блокировки/заглушки — прокси отклонён")
                    validation_context["block_reason"] = "blocked_html"
                    return False
                
                if analysis["total_pages"]:
                    logger.info(f"[SUCCESS] Прокси {ip}:{port} работает на trast-zapchast.ru! Внешний IP: {external_ip}, количество страниц: {analysis['total_pages']}")
                    validation_context["total_pages"] = analysis["total_pages"]
                    self._store_validation_context(proxy, validation_context)
                    return True
                
                if analysis["has_products"] or analysis["has_pagination"]:
                    logger.info(f"[SUCCESS] Прокси {ip}:{port} работает! Внешний IP: {external_ip}, страница каталога загружена (количество страниц не определено)")
                    validation_context.setdefault("total_pages", None)
                    self._store_validation_context(proxy, validation_context)
                    return True
                
                logger.debug("  Ответ не похож на страницу каталога Trast")
                validation_context["block_reason"] = "not_catalog"
                return False
                        
            elif response.status_code == 403:
                logger.debug(f"  Прокси заблокирован (HTTP 403)")
                return False
            elif response.status_code == 429:
                logger.debug(f"  Rate Limit (HTTP 429)")
                return False
            else:
                logger.debug(f"  HTTP статус {response.status_code}")
                return False
                
        except requests.exceptions.ConnectTimeout:
            logger.debug(f"  Таймаут подключения (прокси не отвечает)")
            return False
        except requests.exceptions.ReadTimeout:
            logger.debug(f"  Таймаут чтения (прокси медленно отвечает)")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.debug(f"  Ошибка подключения: {str(e)[:200]}")
            return False
        except requests.exceptions.ProxyError as e:
            logger.debug(f"  Ошибка прокси: {str(e)[:200]}")
            return False
        except Exception as e:
            logger.debug(f"  Неожиданная ошибка при проверке прокси: {str(e)[:200]}")
            return False
    
    def get_proxy_for_thread(self, thread_id: int):
        """Получает прокси для конкретного потока (thread-safe, закрепляет прокси за потоком)"""
        # Проверяем кеш вне lock (быстрая проверка)
        cached_proxy = None
        with self.lock:
            cached_proxy = self.thread_proxies.get(thread_id)
            if cached_proxy:
                # Проверяем, что прокси все еще в списке успешных
                proxy_key = f"{cached_proxy['ip']}:{cached_proxy['port']}"
                successful_keys = {f"{p['ip']}:{p['port']}" for p in self.successful_proxies}
                if proxy_key in successful_keys:
                    return cached_proxy
                else:
                    # Прокси больше не в успешных - удаляем из кеша
                    del self.thread_proxies[thread_id]
        
        # Получаем новый прокси (get_first_working_proxy сам управляет lock)
        proxy = self.get_first_working_proxy(max_attempts=50)
        if proxy:
            with self.lock:
                self.thread_proxies[thread_id] = proxy
        return proxy
    
    def _proxy_search_worker(self, thread_id, proxy_queue, found_proxies, stop_event, stats):
        """Worker функция для многопоточного поиска прокси"""
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
                logger.info(f"[{thread_name}] [ШАГ 1] Базовая проверка прокси {proxy_key} ({proxy.get('protocol', 'http').upper()})...")
                
                # Валидация прокси
                if self.validate_proxy_for_trast(proxy, timeout=30):
                    logger.info(f"[{thread_name}] [SUCCESS] Найден рабочий прокси: {proxy_key} ({proxy.get('protocol', 'http').upper()}) ({proxy.get('country', 'Unknown')})")
                    
                    # Сохраняем в успешные (thread-safe)
                    self.save_successful_proxy(proxy)
                    
                    # Добавляем в список найденных (thread-safe)
                    with self.lock:
                        found_proxies.append(proxy)
                        stats['found'] += 1
                    
                    logger.info(f"[{thread_name}] Прокси добавлен в пул найденных (всего найдено: {len(found_proxies)})")
                    
                    # Если нашли достаточно прокси (3), сигнализируем остановку
                    if len(found_proxies) >= 3:
                        logger.info(f"[{thread_name}] Найдено достаточно прокси (3), сигнализируем остановку")
                        stop_event.set()
                        break
                else:
                    failed_count += 1
                    # Добавляем в failed_proxies (thread-safe)
                    with self.lock:
                        self.failed_proxies.add(proxy_key)
                        stats['failed'] += 1
                    
                    # Выводим статистику каждые 20 прокси
                    if checked_count % 20 == 0:
                        with self.lock:
                            total_checked = stats['checked']
                            total_found = stats['found']
                            total_failed = stats['failed']
                        logger.info(f"[{thread_name}] Проверено {checked_count} прокси (всего по всем потокам: проверено {total_checked}, найдено {total_found}, неуспешных {total_failed})")
                
                # Обновляем общую статистику
                with self.lock:
                    stats['checked'] += 1
                
                proxy_queue.task_done()
                
            except Exception as e:
                logger.error(f"[{thread_name}] Ошибка при проверке прокси: {e}")
                proxy_queue.task_done()
                continue
        
        logger.info(f"[{thread_name}] Поток поиска прокси завершен (проверено: {checked_count}, неуспешных: {failed_count})")
    
    def get_working_proxies_parallel(self, count=3, max_attempts_per_thread=None):
        """Находит несколько рабочих прокси параллельно в 3 потоках
        
        Args:
            count: Количество прокси для поиска (по умолчанию 3)
            max_attempts_per_thread: Максимум попыток на поток (None = без ограничений)
        
        Returns:
            List[Dict]: Список найденных рабочих прокси (до count штук)
        """
        try:
            # Обновляем прокси если нужно
            if self.should_update_proxies():
                if not self.download_proxies():
                    logger.warning("Не удалось обновить прокси, используем кэшированные")
            
            found_proxies = []
            stop_event = threading.Event()
            stats = {'checked': 0, 'found': 0, 'failed': 0}
            
            # ШАГ 1: Сначала проверяем старые успешные прокси (быстро, последовательно)
            shuffled_successful = None
            with self.lock:
                if self.successful_proxies:
                    shuffled_successful = self.successful_proxies.copy()
            
            if shuffled_successful:
                logger.info(f"Проверяем {len(shuffled_successful)} старых успешных прокси (приоритет)...")
                random.shuffle(shuffled_successful)
                
                for proxy in shuffled_successful:
                    if len(found_proxies) >= count:
                        break
                    
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    logger.info(f"Проверяем старый успешный прокси: {proxy_key} ({proxy.get('protocol', 'http').upper()})")
                    
                    if self.validate_proxy_for_trast(proxy, timeout=30):
                        with self.lock:
                            for existing in self.successful_proxies:
                                if f"{existing['ip']}:{existing['port']}" == proxy_key:
                                    existing['last_success'] = datetime.now().isoformat()
                                    existing['success_count'] = existing.get('success_count', 0) + 1
                                    self._write_successful_proxies()
                                    break
                        logger.info(f"[OK] Старый успешный прокси работает: {proxy_key}")
                        found_proxies.append(proxy)
                    else:
                        self.remove_failed_successful_proxy(proxy)
                        logger.warning(f"Старый прокси {proxy_key} перестал работать, удален из списка")
            
            # Если нашли достаточно старых прокси, возвращаем их
            if len(found_proxies) >= count:
                logger.info(f"Найдено достаточно старых успешных прокси: {len(found_proxies)}")
                return found_proxies[:count]
            
            # ШАГ 2: Многопоточный поиск новых прокси
            logger.info(f"Старых успешных прокси недостаточно ({len(found_proxies)}/{count}), запускаем многопоточный поиск...")
            
            if not os.path.exists(self.proxies_file):
                logger.warning("Файл прокси не найден")
                return found_proxies
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                all_proxies = json.load(f)
            
            # Фильтруем прокси
            with self.lock:
                successful_keys = {f"{p['ip']}:{p['port']}" for p in self.successful_proxies}
                failed_proxies_copy = self.failed_proxies.copy()
            
            available_proxies = []
            for proxy in all_proxies:
                protocol = proxy.get('protocol', '').lower()
                country = proxy.get('country', '').upper()
                
                if protocol not in ['http', 'https', 'socks4', 'socks5']:
                    continue
                
                if self.country_filter and country not in self.country_filter:
                    continue
                
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in failed_proxies_copy and proxy_key not in successful_keys:
                    available_proxies.append(proxy)
            
            random.shuffle(available_proxies)
            
            logger.info(f"Ищем {count - len(found_proxies)} рабочих прокси из {len(available_proxies)} доступных (3 потока)...")
            
            # Статистика по протоколам
            protocol_stats = {}
            for proxy in available_proxies:
                protocol = proxy.get('protocol', 'http').upper()
                protocol_stats[protocol] = protocol_stats.get(protocol, 0) + 1
            logger.info(f"Статистика новых прокси: {protocol_stats}")
            
            # Ограничиваем количество прокси для проверки
            if max_attempts_per_thread is not None:
                total_attempts = max_attempts_per_thread * 3
                proxies_to_check = available_proxies[:min(total_attempts, len(available_proxies))]
            else:
                proxies_to_check = available_proxies
            
            logger.info(f"Проверяем {len(proxies_to_check)} новых прокси в 3 потоках")
            
            # Создаем очередь прокси
            proxy_queue = queue.Queue()
            for proxy in proxies_to_check:
                proxy_queue.put(proxy)
            
            # Запускаем 3 потока поиска
            threads = []
            for thread_id in range(3):
                thread = threading.Thread(
                    target=self._proxy_search_worker,
                    args=(thread_id, proxy_queue, found_proxies, stop_event, stats),
                    daemon=False,
                    name=f"ProxySearch-{thread_id}"
                )
                thread.start()
                threads.append(thread)
                logger.info(f"Запущен поток поиска прокси {thread_id}")
            
            # Ждем завершения всех потоков или пока не найдем достаточно прокси
            for thread in threads:
                thread.join()
            
            logger.info(f"Многопоточный поиск завершен: найдено {len(found_proxies)} прокси (проверено: {stats['checked']}, неуспешных: {stats['failed']})")
            
            return found_proxies[:count]
            
        except Exception as e:
            logger.error(f"Ошибка при многопоточном поиске прокси: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return found_proxies
    
    def get_first_working_proxy(self, max_attempts=None):
        """Находит первый рабочий прокси для быстрого старта. Сначала проверяет старые успешные прокси (thread-safe)."""
        # Используем многопоточный поиск для получения одного прокси
        proxies = self.get_working_proxies_parallel(count=1, max_attempts_per_thread=max_attempts)
        return proxies[0] if proxies else None
    
    def get_next_working_proxy(self, start_from_index=0, max_attempts=None):
        """Получает следующий рабочий прокси начиная с определенного индекса. Сначала проверяет старые успешные."""
        try:
            # ШАГ 1: Сначала проверяем старые успешные прокси (если еще не проверяли в этом цикле)
            if self.successful_proxies:
                logger.info(f"Проверяем {len(self.successful_proxies)} старых успешных прокси (приоритет)...")
                
                shuffled_successful = self.successful_proxies.copy()
                random.shuffle(shuffled_successful)
                
                for proxy in shuffled_successful:
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    logger.info(f"Проверяем старый успешный прокси: {proxy_key} ({proxy.get('protocol', 'http').upper()})")
                    
                    if self.validate_proxy_for_trast(proxy, timeout=30):
                        # Обновляем дату последнего успеха
                        proxy['last_success'] = datetime.now().isoformat()
                        proxy['success_count'] = proxy.get('success_count', 0) + 1
                        self._write_successful_proxies()
                        logger.info(f"[OK] Старый успешный прокси работает: {proxy_key}")
                        return proxy, start_from_index
                    else:
                        # Удаляем неработающий прокси из успешных
                        self.remove_failed_successful_proxy(proxy)
                        logger.warning(f"Старый прокси {proxy_key} перестал работать, удален из списка")
            
            # ШАГ 2: Если старые не сработали, проверяем новые прокси
            logger.info("Старые успешные прокси не сработали, проверяем новые...")
            
            if not os.path.exists(self.proxies_file):
                return None, start_from_index
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                all_proxies = json.load(f)
            
            # Фильтруем прокси по протоколу, стране и исключаем неработающие
            available_proxies = []
            successful_keys = {f"{p['ip']}:{p['port']}" for p in self.successful_proxies}
            
            for proxy in all_proxies:
                protocol = proxy.get('protocol', '').lower()
                country = proxy.get('country', '').upper()
                
                # Фильтр по протоколу
                if protocol not in ['http', 'https', 'socks4', 'socks5']:
                    continue
                
                # Фильтр по странам (если задан)
                if self.country_filter and country not in self.country_filter:
                    continue
                
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                # Пропускаем уже проверенные успешные прокси и неработающие
                if proxy_key not in self.failed_proxies and proxy_key not in successful_keys:
                    available_proxies.append(proxy)
            
            total_available = len(available_proxies)
            if total_available == 0:
                logger.warning("Нет доступных новых прокси для проверки")
                return None, start_from_index
            
            if start_from_index >= total_available:
                start_from_index = 0
            
            if max_attempts is not None:
                end_index = min(start_from_index + max_attempts, total_available)
            else:
                end_index = total_available
            
            proxies_to_check = available_proxies[start_from_index:end_index]
            
            logger.info(f"Ищем следующий рабочий прокси (позиции {start_from_index}..{end_index - 1}, всего {total_available})...")
            
            failed_count = 0
            stats_interval = 20  # Выводим статистику каждые 20 прокси
            
            for offset, proxy in enumerate(proxies_to_check):
                if self.validate_proxy_for_trast(proxy, timeout=30):  # Проверяем ТОЛЬКО на trast-zapchast.ru
                    logger.info(f"[SUCCESS] Найден рабочий прокси: {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()}) ({proxy.get('country', 'Unknown')}) (проверено: {offset+1}, неуспешных: {failed_count})")
                    # Сохраняем в успешные
                    self.save_successful_proxy(proxy)
                    return proxy, start_from_index + offset + 1  # Возвращаем прокси и следующий индекс
                else:
                    failed_count += 1
                    self.failed_proxies.add(f"{proxy['ip']}:{proxy['port']}")
                    
                    # Выводим статистику каждые N прокси
                    if (offset + 1) % stats_interval == 0:
                        logger.info(f"Проверено {offset+1}/{len(proxies_to_check)} прокси: успешных 0, неуспешных {failed_count}")
            
            logger.warning(f"Не удалось найти рабочий прокси в текущем диапазоне (проверено: {len(proxies_to_check)}, неуспешных: {failed_count})")
            return None, end_index
            
        except Exception as e:
            logger.error(f"Ошибка при поиске следующего прокси: {e}")
            return None, start_from_index

    def get_working_proxies(self, max_proxies: int = 50) -> List[Dict]:
        """Получает список рабочих прокси (старый метод для совместимости)"""
        # Обновляем прокси если нужно
        if self.should_update_proxies():
            if not self.download_proxies():
                logger.warning("Не удалось обновить прокси, используем кэшированные")
        
        # Загружаем прокси
        all_proxies = self.load_proxies()
        if not all_proxies:
            logger.error("Нет доступных прокси")
            return []
        
        # Фильтруем уже проверенные прокси
        available_proxies = [p for p in all_proxies if f"{p['ip']}:{p['port']}" not in self.failed_proxies]
        
        # Случайно перемешиваем для разнообразия
        random.shuffle(available_proxies)
        
        working_proxies = []
        logger.info(f"Проверка {min(len(available_proxies), max_proxies)} прокси...")
        
        for proxy in available_proxies[:max_proxies]:
            if len(working_proxies) >= 20:  # Ограничиваем количество проверяемых прокси
                break
                
            if self.validate_proxy(proxy):
                working_proxies.append(proxy)
                logger.info(f"[OK] Найден рабочий прокси: {proxy['ip']}:{proxy['port']} ({proxy['country']}) - скорость: {proxy.get('speed', 'Unknown')}ms")
        
        logger.info(f"Найдено {len(working_proxies)} рабочих прокси")
        return working_proxies
    
    def get_next_proxy(self) -> Optional[Dict]:
        """Получает следующий рабочий прокси"""
        if not self.proxies:
            self.proxies = self.get_working_proxies()
        
        if not self.proxies:
            logger.error("Нет доступных рабочих прокси")
            return None
        
        # Если дошли до конца списка, перемешиваем и начинаем заново
        if self.current_proxy_index >= len(self.proxies):
            self.current_proxy_index = 0
            random.shuffle(self.proxies)
        
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index += 1
        
        return proxy
    
    def mark_proxy_failed(self, proxy: Dict):
        """Помечает прокси как неработающий"""
        proxy_key = f"{proxy['ip']}:{proxy['port']}"
        self.failed_proxies.add(proxy_key)
        logger.warning(f"Прокси {proxy_key} помечен как неработающий")
    
    def reset_failed_proxies(self):
        """Сбрасывает список неработающих прокси"""
        self.failed_proxies.clear()
        logger.info("Список неработающих прокси сброшен")