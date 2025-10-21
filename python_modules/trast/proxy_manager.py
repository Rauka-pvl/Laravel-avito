import os
import json
import random
import requests
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("trast.proxy_manager")

class ProxyManager:
    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(__file__), "proxy_cache")
        self.proxies_file = os.path.join(self.cache_dir, "proxies.json")
        self.last_update_file = os.path.join(self.cache_dir, "last_update.txt")
        self.current_proxy_index = 0
        self.failed_proxies = set()
        self.proxies = []
        
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def download_proxies(self) -> bool:
        """Скачивает свежие прокси с Proxifly репозитория"""
        try:
            logger.info("Скачивание свежих прокси с Proxifly...")
            
            # URL для получения всех прокси в JSON формате
            url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json"
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            proxies_data = response.json()
            
            # Фильтруем все типы прокси (HTTP, HTTPS, SOCKS4, SOCKS5)
            http_proxies = []
            for proxy in proxies_data:
                protocol = proxy.get('protocol', '').lower()
                if protocol in ['http', 'https', 'socks4', 'socks5']:
                    http_proxies.append({
                        'ip': proxy.get('ip', ''),
                        'port': proxy.get('port', ''),
                        'protocol': protocol,
                        'country': proxy.get('country', ''),
                        'anonymity': proxy.get('anonymity', ''),
                        'speed': proxy.get('speed', 0)
                    })
            
            # Сохраняем прокси в файл
            with open(self.proxies_file, 'w', encoding='utf-8') as f:
                json.dump(http_proxies, f, ensure_ascii=False, indent=2)
            
            # Обновляем время последнего обновления
            with open(self.last_update_file, 'w') as f:
                f.write(datetime.now().isoformat())
            
            logger.info(f"Скачано {len(http_proxies)} прокси всех типов")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании прокси: {e}")
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
                'http://httpbin.org/ip',
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
    
    def validate_proxy_for_site(self, proxy: Dict, site_url: str = "https://trast-zapchast.ru/shop/", timeout: int = 10) -> bool:
        """Проверяет прокси на конкретном сайте"""
        try:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            if protocol in ['http', 'https']:
                proxy_url = f"{protocol}://{ip}:{port}"
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            elif protocol in ['socks4', 'socks5']:
                proxy_url = f"{protocol}://{ip}:{port}"
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            else:
                return False
            
            # Тестируем прокси на целевом сайте
            response = requests.get(
                site_url,
                proxies=proxies,
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            )
            
            if response.status_code == 200:
                # Проверяем, что это не страница ошибки
                if "403" in response.text or "Forbidden" in response.text:
                    logger.debug(f"Прокси {ip}:{port} ({protocol}) заблокирован сайтом (403)")
                    return False
                elif "cloudflare" in response.text.lower():
                    logger.debug(f"Прокси {ip}:{port} ({protocol}) заблокирован Cloudflare")
                    return False
                else:
                    logger.debug(f"Прокси {ip}:{port} ({protocol}) работает на сайте")
                    return True
            else:
                logger.debug(f"Прокси {ip}:{port} ({protocol}) - HTTP статус {response.status_code}")
                return False
                
        except Exception as e:
            logger.debug(f"Прокси {ip}:{port} ({protocol}) - ошибка при проверке сайта: {str(e)}")
            return False
    
    def validate_proxy_batch(self, proxies_batch):
        """Проверяет пакет прокси параллельно"""
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_proxy = {executor.submit(self.validate_proxy_for_site, proxy, 10): proxy for proxy in proxies_batch}
            
            for future in as_completed(future_to_proxy):
                proxy = future_to_proxy[future]
                try:
                    is_working = future.result()
                    if is_working:
                        logger.info(f"✅ Найден рабочий прокси: {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()}) ({proxy.get('country', 'Unknown')})")
                        return proxy  # Возвращаем первый найденный рабочий прокси
                    else:
                        self.failed_proxies.add(f"{proxy['ip']}:{proxy['port']}")
                except Exception as e:
                    logger.debug(f"Ошибка при проверке прокси {proxy['ip']}:{proxy['port']}: {e}")
                    self.failed_proxies.add(f"{proxy['ip']}:{proxy['port']}")
        
        return None

    def get_first_working_proxy(self, max_attempts=3000):
        """Находит первый рабочий прокси для быстрого старта с параллельной проверкой"""
        try:
            # Обновляем прокси если нужно
            if self.should_update_proxies():
                if not self.download_proxies():
                    logger.warning("Не удалось обновить прокси, используем кэшированные")
            
            if not os.path.exists(self.proxies_file):
                logger.warning("Файл прокси не найден")
                return None
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                all_proxies = json.load(f)
            
            # Фильтруем все типы прокси и исключаем неработающие
            available_proxies = []
            for proxy in all_proxies:
                protocol = proxy.get('protocol', '').lower()
                if protocol in ['http', 'https', 'socks4', 'socks5']:
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    if proxy_key not in self.failed_proxies:
                        available_proxies.append(proxy)
            
            # Случайно перемешиваем
            random.shuffle(available_proxies)
            
            logger.info(f"Ищем первый рабочий прокси из {len(available_proxies)} доступных...")
            
            # Статистика по протоколам
            protocol_stats = {}
            for proxy in available_proxies:
                protocol = proxy.get('protocol', 'http').upper()
                protocol_stats[protocol] = protocol_stats.get(protocol, 0) + 1
            
            logger.info(f"Статистика прокси: {protocol_stats}")
            logger.info(f"Проверяем первые {max_attempts} прокси из {len(available_proxies)} доступных")
            
            # Проверяем прокси пакетами по 50 штук
            batch_size = 50
            proxies_to_check = available_proxies[:max_attempts]
            
            for i in range(0, len(proxies_to_check), batch_size):
                batch = proxies_to_check[i:i + batch_size]
                logger.info(f"Проверяем пакет {i//batch_size + 1}/{(len(proxies_to_check) + batch_size - 1)//batch_size}: прокси {i+1}-{min(i+batch_size, len(proxies_to_check))}")
                
                working_proxy = self.validate_proxy_batch(batch)
                if working_proxy:
                    return working_proxy
            
            logger.warning("Не удалось найти рабочий прокси")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске первого прокси: {e}")
            return None
    
    def get_next_working_proxy(self, start_from_index=0, max_attempts=500):
        """Получает следующий рабочий прокси начиная с определенного индекса"""
        try:
            if not os.path.exists(self.proxies_file):
                return None, start_from_index
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                all_proxies = json.load(f)
            
            # Фильтруем все типы прокси и исключаем неработающие
            available_proxies = []
            for proxy in all_proxies:
                protocol = proxy.get('protocol', '').lower()
                if protocol in ['http', 'https', 'socks4', 'socks5']:
                    proxy_key = f"{proxy['ip']}:{proxy['port']}"
                    if proxy_key not in self.failed_proxies:
                        available_proxies.append(proxy)
            
            # Начинаем поиск с указанного индекса
            proxies_to_check = available_proxies[start_from_index:start_from_index + max_attempts]
            
            logger.info(f"Ищем следующий рабочий прокси (начиная с позиции {start_from_index})...")
            
            for i, proxy in enumerate(proxies_to_check):
                logger.info(f"Проверяем прокси {i+1}/{len(proxies_to_check)}: {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()})")
                
                if self.validate_proxy_for_site(proxy, timeout=10):  # Проверяем на целевом сайте
                    logger.info(f"Найден рабочий прокси: {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()}) ({proxy.get('country', 'Unknown')})")
                    return proxy, start_from_index + i + 1  # Возвращаем прокси и следующий индекс
                else:
                    logger.debug(f"Прокси {proxy['ip']}:{proxy['port']} не работает")
                    self.failed_proxies.add(f"{proxy['ip']}:{proxy['port']}")
            
            logger.warning("Не удалось найти рабочий прокси в текущем диапазоне")
            return None, start_from_index + max_attempts
            
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
                logger.info(f"✅ Найден рабочий прокси: {proxy['ip']}:{proxy['port']} ({proxy['country']}) - скорость: {proxy.get('speed', 'Unknown')}ms")
        
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