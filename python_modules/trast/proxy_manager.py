import os
import json
import random
import requests
import logging
import urllib3
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        self.current_proxy_index = 0
        self.failed_proxies = set()
        self.proxies = []
        
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
        
        if self.country_filter:
            countries_str = ", ".join(self.country_filter)
            logger.info(f"ProxyManager инициализирован с фильтром стран: {countries_str}")
        else:
            logger.info("ProxyManager инициализирован без фильтра по стране")
        
    def download_proxies(self, force_update=False) -> bool:
        """Скачивает свежие прокси с Proxifly репозитория
        
        Args:
            force_update: Если True, обновляет прокси даже если они свежие
        """
        try:
            if force_update:
                logger.info("🔄 Принудительное обновление списка прокси...")
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
                logger.info("Скачивание всех прокси с Proxifly для фильтрации по странам СНГ...")
                url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json"
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                proxies_data = response.json()
            
            # Обрабатываем прокси
            filtered_proxies = []
            total_proxies = len(proxies_data)
            
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
                
                filtered_proxies.append({
                    'ip': proxy.get('ip', ''),
                    'port': port,
                    'protocol': protocol,
                    'country': country,
                    'anonymity': proxy.get('anonymity', ''),
                    'speed': proxy.get('speed', 0)
                })
            
            # Статистика по странам и протоколам
            country_stats = {}
            protocol_stats = {}
            for p in filtered_proxies:
                country = p['country']
                protocol = p['protocol'].upper()
                country_stats[country] = country_stats.get(country, 0) + 1
                protocol_stats[protocol] = protocol_stats.get(protocol, 0) + 1
            
            logger.info(f"Всего прокси в репозитории: {total_proxies}")
            logger.info(f"Отфильтровано прокси: {len(filtered_proxies)}")
            if self.country_filter:
                logger.info(f"Прокси для страны {self.country_filter}: {country_stats}")
            logger.info(f"Статистика по протоколам: {protocol_stats}")
            
            # Сохраняем прокси в файл
            with open(self.proxies_file, 'w', encoding='utf-8') as f:
                json.dump(filtered_proxies, f, ensure_ascii=False, indent=2)
            
            # Обновляем время последнего обновления
            with open(self.last_update_file, 'w') as f:
                f.write(datetime.now().isoformat())
            
            logger.info(f"Сохранено {len(filtered_proxies)} прокси в файл")
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
    
    def get_external_ip(self, proxies: dict = None, timeout: int = 10) -> str:
        """Получает внешний IP через прокси"""
        try:
            # Пробуем несколько сервисов для получения IP
            ip_services = [
                "https://2ip.ru",
                "https://api.ipify.org",
                "https://httpbin.org/ip"
            ]
            
            for service in ip_services:
                try:
                    response = requests.get(service, proxies=proxies, timeout=timeout, verify=False)
                    if response.status_code == 200:
                        if service == "https://2ip.ru":
                            # 2ip.ru возвращает HTML, нужно извлечь IP
                            import re
                            ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', response.text)
                            if ip_match:
                                return ip_match.group(1)
                        elif service == "https://api.ipify.org":
                            # ipify возвращает чистый IP
                            return response.text.strip()
                        elif service == "https://httpbin.org/ip":
                            # httpbin возвращает JSON
                            data = response.json()
                            return data.get('origin', '').split(',')[0].strip()
                except Exception as e:
                    logger.debug(f"Не удалось получить IP с {service}: {e}")
                    continue
            
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
                "http://httpbin.org/ip",
                "https://api.ipify.org",
                "http://ifconfig.me/ip"
            ]
            
            working_url = None
            external_ip = None
            
            for test_url in test_urls:
                try:
                    logger.info(f"   Тестируем через {test_url}...")
                    response = requests.get(test_url, proxies=proxies, timeout=timeout, verify=False)
                    if response.status_code == 200:
                        working_url = test_url
                        # Извлекаем IP из ответа
                        if test_url == "http://httpbin.org/ip":
                            data = response.json()
                            external_ip = data.get('origin', '').split(',')[0].strip()
                        else:
                            external_ip = response.text.strip()
                        
                        if external_ip and len(external_ip.split('.')) == 4:  # Проверяем что это похоже на IP
                            logger.info(f"   ✅ Прокси РАБОТАЕТ! Внешний IP: {external_ip}")
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
            
            logger.warning(f"   ❌ Прокси НЕ РАБОТАЕТ (не смог подключиться к тестовым сервисам)")
            return False, {}
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка при базовой проверке прокси: {e}")
            return False, {}
    
    def validate_proxy_for_trast_selenium(self, proxy: Dict, timeout: int = 60, use_chrome: bool = False) -> bool:
        """Проверяет прокси через Selenium (Firefox или Chrome/Chromium)"""
        try:
            from selenium import webdriver
            from bs4 import BeautifulSoup
            import time
            import random
            import traceback
            
            # Пробуем Chrome, если не получилось - Firefox
            if use_chrome:
                try:
                    return self._validate_with_chrome(proxy, timeout)
                except Exception as e:
                    logger.warning(f"  ⚠️  Chrome не доступен: {str(e)[:200]}")
                    logger.info(f"  Пробуем Firefox...")
                    # Fallback на Firefox
            
            # Используем Firefox
            try:
                return self._validate_with_firefox(proxy, timeout)
            except Exception as e:
                logger.error(f"  ❌ Ошибка Firefox: {str(e)}")
                logger.debug(f"  Traceback: {traceback.format_exc()}")
                # Пробуем Chrome как fallback
                try:
                    logger.info(f"  Пробуем Chrome как альтернативу...")
                    return self._validate_with_chrome(proxy, timeout)
                except Exception as chrome_error:
                    logger.error(f"  ❌ Chrome тоже не работает: {str(chrome_error)[:200]}")
                    logger.debug(f"  Chrome traceback: {traceback.format_exc()}")
                    return False
                    
        except Exception as e:
            logger.error(f"  ❌ Критическая ошибка Selenium: {str(e)}")
            logger.debug(f"  Полный traceback: {traceback.format_exc()}")
            return False
    
    def _validate_with_firefox(self, proxy: Dict, timeout: int) -> bool:
        """Проверка через Firefox"""
        from selenium import webdriver
        from selenium.webdriver.firefox.service import Service
        from selenium.webdriver.firefox.options import Options
        import geckodriver_autoinstaller
        from bs4 import BeautifulSoup
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
            logger.warning(f"  ⚠️  Ошибка установки geckodriver: {e}")
        
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
            logger.warning(f"  ⚠️  Неподдерживаемый протокол прокси: {protocol}")
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
            logger.info(f"  ✅ Firefox драйвер создан")
            
            # ПРОВЕРКА: Проверяем, что прокси действительно используется
            logger.debug(f"  [ПРОВЕРКА ПРОКСИ] Проверяем внешний IP через браузер...")
            try:
                driver.get("https://api.ipify.org")
                time.sleep(2)
                browser_ip = driver.page_source.strip()
                if browser_ip and len(browser_ip.split('.')) == 4:
                    logger.info(f"  ✅ Прокси работает! IP браузера: {browser_ip} (ожидалось: {ip})")
                    if browser_ip != ip:
                        logger.debug(f"  Примечание: IP браузера ({browser_ip}) отличается от IP прокси ({ip}) - это нормально")
                else:
                    logger.warning(f"  ⚠️  Не удалось получить IP через браузер: {browser_ip}")
            except Exception as ip_check_error:
                logger.warning(f"  ⚠️  Не удалось проверить IP через браузер: {str(ip_check_error)[:100]}")
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
                    logger.error(f"  ❌ Ошибка подключения к trast-zapchast.ru через прокси: {str(page_error)[:200]}")
                    logger.error(f"  ❌ Прокси не может подключиться к целевому сайту")
                    return False
                elif "timeout" in error_msg or "timed out" in error_msg:
                    logger.error(f"  ❌ Таймаут при подключении к trast-zapchast.ru: {str(page_error)[:200]}")
                    logger.error(f"  ❌ Прокси слишком медленный или недоступен для целевого сайта")
                    return False
                else:
                    # Другие ошибки - пробуем продолжить, но логируем
                    logger.warning(f"  ⚠️  Ошибка при открытии главной страницы: {str(page_error)[:200]}")
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
                    logger.error(f"  ❌ Ошибка подключения к shop через прокси: {str(shop_error)[:200]}")
                    logger.error(f"  ❌ Прокси не может подключиться к целевому сайту")
                    return False
                elif "timeout" in error_msg or "timed out" in error_msg:
                    logger.error(f"  ❌ Таймаут при подключении к shop: {str(shop_error)[:200]}")
                    logger.error(f"  ❌ Прокси слишком медленный или недоступен для целевого сайта")
                    return False
                else:
                    logger.error(f"  ❌ Ошибка при открытии shop: {str(shop_error)[:200]}")
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
                logger.info(f"  ⏳ Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
                time.sleep(3)
                driver.refresh()
                time.sleep(2)
                page_source_lower = driver.page_source.lower()
                wait_time += 5
            
            if wait_time >= max_wait:
                logger.warning(f"  ❌ Cloudflare проверка не пройдена")
                return False
            
            # Парсим количество страниц
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
            
            if last_page_el and last_page_el.has_attr("data-page"):
                total_pages = int(last_page_el["data-page"])
                logger.info(f"  ✅✅✅ FIREFOX УСПЕШНО! Получено количество страниц: {total_pages}")
                return True
            else:
                if len(driver.page_source) > 1000 and ("shop" in driver.page_source.lower() or "товар" in driver.page_source.lower()):
                    logger.info(f"  ✅ FIREFOX: Страница загружена")
                    return True
                else:
                    logger.warning(f"  ❌ FIREFOX: Страница не загрузилась корректно")
                    return False
                    
        except Exception as e:
            import traceback
            logger.error(f"  ❌ Ошибка Firefox: {str(e)}")
            logger.debug(f"  Полный traceback:\n{traceback.format_exc()}")
            return False
        finally:
            if driver:
                driver.quit()
    
    def _validate_with_chrome(self, proxy: Dict, timeout: int) -> bool:
        """Проверка через Chrome/Chromium"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.common.by import By
            from bs4 import BeautifulSoup
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
                logger.error(f"  ❌ Ошибка установки ChromeDriver: {e}")
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
                logger.warning(f"  ⚠️  Chrome может иметь проблемы с {protocol.upper()} прокси (ERR_TUNNEL_CONNECTION_FAILED)")
                proxy_arg = f"socks5://{ip}:{port}" if protocol == 'socks5' else f"socks4://{ip}:{port}"
            else:
                logger.warning(f"  ⚠️  Неподдерживаемый протокол: {protocol}")
                return False
            
            options.add_argument(f"--proxy-server={proxy_arg}")
            logger.debug(f"  Прокси настроен: {proxy_arg}")
            
            # Создаем драйвер
            logger.debug(f"  Создаем Chrome драйвер...")
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            # НЕ устанавливаем таймауты сразу - пусть драйвер использует дефолтные
            # Таймауты будем устанавливать только при необходимости, но не сразу после создания
            logger.info(f"  ✅ Chrome драйвер создан")
            
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
                    driver.get("https://api.ipify.org")
                    time.sleep(2)
                    browser_ip = driver.page_source.strip()
                    # Пробуем извлечь IP из HTML через regex
                    import re
                    ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
                    ip_matches = re.findall(ip_pattern, browser_ip)
                    extracted_ip = ip_matches[0] if ip_matches else None
                    
                    if extracted_ip:
                        logger.info(f"  ✅ Прокси работает! IP Chrome: {extracted_ip} (прокси: {ip})")
                    else:
                        # Если не нашли IP, ограничиваем вывод HTML до 200 символов
                        browser_ip_preview = browser_ip[:200] + "..." if len(browser_ip) > 200 else browser_ip
                        logger.warning(f"  ⚠️  Не удалось получить IP (размер ответа: {len(browser_ip)} символов, превью: {browser_ip_preview})")
                except Exception as ip_check_error:
                    logger.warning(f"  ⚠️  Не удалось проверить IP: {str(ip_check_error)[:100]}")
                
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
                        logger.error(f"  ❌ Ошибка туннельного подключения через прокси: {str(page_error)[:200]}")
                        logger.error(f"  ❌ Прокси не может установить туннель к целевому сайту (обычно для SOCKS)")
                        logger.error(f"  ❌ Рекомендуется использовать Firefox для SOCKS прокси")
                        return False
                    elif "connection" in error_msg or "net::err_" in error_msg:
                        logger.error(f"  ❌ Ошибка подключения к trast-zapchast.ru через прокси: {str(page_error)[:200]}")
                        logger.error(f"  ❌ Прокси не может подключиться к целевому сайту")
                        return False
                    elif "timeout" in error_msg or "timed out" in error_msg:
                        logger.error(f"  ❌ Таймаут при подключении к trast-zapchast.ru: {str(page_error)[:200]}")
                        logger.error(f"  ❌ Прокси слишком медленный или недоступен для целевого сайта")
                        return False
                    else:
                        # Другие ошибки - пробуем продолжить, но логируем
                        logger.warning(f"  ⚠️  Ошибка при открытии главной страницы: {str(page_error)[:200]}")
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
                        logger.error(f"  ❌ Ошибка туннельного подключения к shop через прокси: {str(shop_error)[:200]}")
                        logger.error(f"  ❌ Прокси не может установить соединение к целевому сайту")
                        if protocol in ['socks4', 'socks5']:
                            logger.error(f"  ❌ Рекомендуется использовать Firefox для SOCKS прокси")
                        return False
                    elif "connection" in error_msg or "net::err_" in error_msg:
                        logger.error(f"  ❌ Ошибка подключения к shop через прокси: {str(shop_error)[:200]}")
                        logger.error(f"  ❌ Прокси не может подключиться к целевому сайту")
                        return False
                    elif "timeout" in error_msg or "timed out" in error_msg:
                        logger.error(f"  ❌ Таймаут при подключении к shop: {str(shop_error)[:200]}")
                        logger.error(f"  ❌ Прокси слишком медленный или недоступен для целевого сайта")
                        return False
                    else:
                        logger.error(f"  ❌ Ошибка при открытии shop: {str(shop_error)[:200]}")
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
                    logger.info(f"  ⏳ Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
                    time.sleep(3)
                    driver.refresh()
                    time.sleep(2)
                    page_source_lower = driver.page_source.lower()
                    wait_time += 5
                
                if wait_time >= max_wait:
                    logger.warning(f"  ❌ Cloudflare проверка не пройдена")
                    return False
                
                # Парсим количество страниц
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
                
                if last_page_el and last_page_el.has_attr("data-page"):
                    total_pages = int(last_page_el["data-page"])
                    logger.info(f"  ✅✅✅ CHROME УСПЕШНО! Получено количество страниц: {total_pages}")
                    return True
                else:
                    if len(driver.page_source) > 1000 and ("shop" in driver.page_source.lower() or "товар" in driver.page_source.lower()):
                        logger.info(f"  ✅ CHROME: Страница загружена")
                        return True
                    else:
                        logger.warning(f"  ❌ CHROME: Страница не загрузилась корректно")
                        return False
                        
            finally:
                driver.quit()
                
        except Exception as e:
            import traceback
            logger.error(f"  ❌ Ошибка Chrome: {str(e)}")
            logger.debug(f"  Полный traceback:\n{traceback.format_exc()}")
            return False
    
    def validate_proxy_for_trast(self, proxy: Dict, timeout: int = 30) -> bool:
        """Проверяет прокси: сначала базовая работоспособность, потом доступ к trast-zapchast.ru"""
        try:
            protocol = proxy.get('protocol', 'http').lower()
            ip = proxy['ip']
            port = proxy['port']
            
            logger.info(f"Проверяем прокси {ip}:{port} ({protocol.upper()})")
            logger.info(f"=" * 60)
            
            # ШАГ 1: Базовая проверка работоспособности прокси
            is_basic_working, proxy_info = self.validate_proxy_basic(proxy, timeout=10)
            
            if not is_basic_working:
                logger.warning(f"❌ Прокси {ip}:{port} не прошел базовую проверку - пропускаем проверку trast-zapchast.ru")
                return False
            
            # Получаем proxies из базовой проверки
            proxies = proxy_info['proxies']
            external_ip = proxy_info.get('external_ip', 'Unknown')
            
            logger.info(f"✅ Базовая проверка пройдена! Внешний IP: {external_ip}")
            logger.info(f"[ШАГ 2] Теперь проверяем доступ к trast-zapchast.ru...")
            
            # СНАЧАЛА пробуем Selenium (самый эффективный способ обхода Cloudflare)
            logger.info(f"  [ШАГ 2.1] Пробуем Selenium (наиболее эффективный обход Cloudflare)...")
            
            # ВАЖНО: Для SOCKS прокси сразу используем Firefox (Chrome имеет проблемы с ERR_TUNNEL_CONNECTION_FAILED)
            protocol = proxy.get('protocol', 'http').lower()
            use_chrome_first = protocol in ['http', 'https']  # Chrome только для HTTP/HTTPS
            
            selenium_result = False
            if use_chrome_first:
                try:
                    logger.info(f"  Пробуем Chrome/Chromium...")
                    selenium_result = self.validate_proxy_for_trast_selenium(proxy, timeout=60, use_chrome=True)
                except Exception as chrome_error:
                    logger.debug(f"  Chrome не доступен: {str(chrome_error)[:200]}")
                    selenium_result = False
            
            if not selenium_result:
                if use_chrome_first:
                    logger.info(f"  Chrome не сработал, пробуем Firefox...")
                else:
                    logger.info(f"  Для {protocol.upper()} прокси используем Firefox (Chrome не рекомендуется для SOCKS)...")
                selenium_result = self.validate_proxy_for_trast_selenium(proxy, timeout=60, use_chrome=False)
            
            if selenium_result:
                logger.info(f"  ✅✅✅ Прокси работает через Selenium! Количество страниц получено!")
                return True
            
            logger.info(f"  [ШАГ 2.2] Selenium не сработал, пробуем cloudscraper/requests...")
            
            # Проверяем доступ к странице shop и пытаемся получить количество страниц
            site_url = "https://trast-zapchast.ru/shop/"
            
            logger.info(f"Отправляем запрос к {site_url} через прокси {ip}:{port}...")
            logger.info(f"  Цель: получить количество страниц каталога")
            
            # Используем cloudscraper для обхода Cloudflare (приоритет)
            if HAS_CLOUDSCRAPER:
                logger.info(f"  Используем cloudscraper для обхода Cloudflare...")
                try:
                    # Создаем cloudscraper сессию с поддержкой прокси
                    scraper = cloudscraper.create_scraper(
                        browser={
                            'browser': 'chrome',
                            'platform': 'windows',
                            'desktop': True
                        }
                    )
                    scraper.allow_redirects = True
                    
                    # Настраиваем прокси для cloudscraper
                    # cloudscraper использует requests под капотом, поэтому прокси передаем через proxies
                    scraper.proxies.update(proxies)
                    
                    # ВАЖНО: для cloudscraper с SOCKS прокси нужно правильно настроить SSL
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    
                    # Отключаем проверку SSL через настройку адаптера
                    import ssl
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    
                    # Для cloudscraper используем verify=False как параметр
                    # Но сначала проверяем тип прокси
                    if protocol in ['socks4', 'socks5']:
                        # Для SOCKS прокси cloudscraper может не работать корректно
                        # Пробуем, но ожидаем ошибку
                        response = scraper.get(site_url, timeout=timeout, verify=False)
                    else:
                        # Для HTTP/HTTPS прокси должно работать
                        response = scraper.get(site_url, timeout=timeout, verify=False)
                    logger.info(f"  ✅ cloudscraper успешно: HTTP {response.status_code}")
                except Exception as e:
                    logger.warning(f"  ⚠️  Ошибка cloudscraper: {e}")
                    logger.debug(f"  Детали ошибки: {str(e)}")
                    logger.info(f"  Пробуем обычный requests...")
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
            else:
                # Обычный requests с заголовками (fallback если cloudscraper не установлен)
                logger.warning(f"  ⚠️  cloudscraper не установлен, используем requests с заголовками...")
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
            
            logger.debug(f"  HTTP статус: {response.status_code}")
            logger.debug(f"  Размер ответа: {len(response.text)} байт")
            
            # Подробное логирование содержимого ответа
            if response.status_code == 200:
                response_text = response.text.lower()
                
                # Проверяем на различные типы блокировок
                if "403" in response_text or "forbidden" in response_text:
                    logger.warning(f"  ❌ Прокси заблокирован сайтом (403 Forbidden)")
                    logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                    return False
                elif "cloudflare" in response_text:
                    logger.warning(f"  ❌ Прокси заблокирован Cloudflare")
                    logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                    return False
                elif "blocked" in response_text or "access denied" in response_text:
                    logger.warning(f"  ❌ Прокси заблокирован (Access Denied)")
                    logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                    return False
                elif "captcha" in response_text or "challenge" in response_text:
                    logger.warning(f"  ❌ Требуется прохождение капчи")
                    logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                    return False
                else:
                    # Проверяем, что это действительно страница shop и пытаемся получить количество страниц
                    if "shop" in response_text or "товар" in response_text or "product" in response_text or "каталог" in response_text:
                        # Пытаемся найти количество страниц
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Ищем элемент с количеством страниц (как в main.py)
                        last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
                        if last_page_el and last_page_el.has_attr("data-page"):
                            total_pages = int(last_page_el["data-page"])
                            logger.info(f"  ✅ Прокси УСПЕШНО работает на trast-zapchast.ru!")
                            logger.info(f"  ✅ Получено количество страниц: {total_pages}")
                            return True
                        else:
                            # Страница загрузилась, но не нашли количество страниц
                            # Проверяем, что это точно страница shop
                            if len(response_text) > 1000 and ("trast" in response_text or "запчаст" in response_text):
                                logger.info(f"  ✅ Прокси УСПЕШНО работает! Страница shop загружена")
                                logger.info(f"  ⚠️  Не удалось определить количество страниц автоматически, но страница доступна")
                                return True
                            else:
                                logger.warning(f"  ❌ Страница загружена, но не похожа на shop каталог")
                                logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                                return False
                    else:
                        logger.warning(f"  ❌ Прокси получил ответ, но не похож на страницу shop")
                        logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                        return False
                        
            elif response.status_code == 403:
                logger.warning(f"  ❌ Прокси заблокирован (HTTP 403)")
                logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                return False
            elif response.status_code == 429:
                logger.warning(f"  ❌ Rate Limit (HTTP 429)")
                logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                return False
            else:
                logger.warning(f"  ❌ HTTP статус {response.status_code}")
                logger.debug(f"  Первые 500 символов ответа: {response.text[:500]}")
                return False
                
        except requests.exceptions.ConnectTimeout:
            logger.warning(f"  ❌ Таймаут подключения (прокси не отвечает)")
            return False
        except requests.exceptions.ReadTimeout:
            logger.warning(f"  ❌ Таймаут чтения (прокси медленно отвечает)")
            return False
        except requests.exceptions.ConnectionError as e:
            import traceback
            logger.warning(f"  ❌ Ошибка подключения: {str(e)}")
            logger.debug(f"  Traceback:\n{traceback.format_exc()}")
            return False
        except requests.exceptions.ProxyError as e:
            import traceback
            logger.warning(f"  ❌ Ошибка прокси: {str(e)}")
            logger.debug(f"  Traceback:\n{traceback.format_exc()}")
            return False
        except Exception as e:
            import traceback
            logger.error(f"  ❌ Неизвестная ошибка: {str(e)}")
            logger.debug(f"  Полный traceback:\n{traceback.format_exc()}")
            return False
    
    def get_first_working_proxy(self, max_attempts=3000):
        """Находит первый рабочий прокси для быстрого старта"""
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
            
            # Фильтруем прокси по протоколу, стране и исключаем неработающие
            available_proxies = []
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
                if proxy_key not in self.failed_proxies:
                    available_proxies.append(proxy)
            
            # Случайно перемешиваем
            random.shuffle(available_proxies)
            
            logger.info(f"Ищем первый рабочий прокси из {len(available_proxies)} доступных...")
            
            # Статистика по протоколам
            protocol_stats = {}
            for proxy in available_proxies:  # Все прокси, не только первые 20
                protocol = proxy.get('protocol', 'http').upper()
                protocol_stats[protocol] = protocol_stats.get(protocol, 0) + 1
            
            logger.info(f"Статистика прокси: {protocol_stats}")
            logger.info(f"Проверяем первые {max_attempts} прокси из {len(available_proxies)} доступных")
            
            for i, proxy in enumerate(available_proxies[:max_attempts]):
                logger.info(f"Проверяем прокси {i+1}/{max_attempts}: {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()})")
                
                if self.validate_proxy_for_trast(proxy, timeout=30):  # Проверяем ТОЛЬКО на trast-zapchast.ru
                    logger.info(f"Найден первый рабочий прокси: {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()}) ({proxy.get('country', 'Unknown')})")
                    return proxy
                else:
                    logger.debug(f"Прокси {proxy['ip']}:{proxy['port']} не работает")
                    self.failed_proxies.add(f"{proxy['ip']}:{proxy['port']}")
            
            logger.warning("Не удалось найти рабочий прокси")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске первого прокси: {e}")
            return None
    
    def get_next_working_proxy(self, start_from_index=0, max_attempts=50):
        """Получает следующий рабочий прокси начиная с определенного индекса"""
        try:
            if not os.path.exists(self.proxies_file):
                return None, start_from_index
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                all_proxies = json.load(f)
            
            # Фильтруем прокси по протоколу, стране и исключаем неработающие
            available_proxies = []
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
                if proxy_key not in self.failed_proxies:
                    available_proxies.append(proxy)
            
            # Начинаем поиск с указанного индекса
            proxies_to_check = available_proxies[start_from_index:start_from_index + max_attempts]
            
            logger.info(f"Ищем следующий рабочий прокси (начиная с позиции {start_from_index})...")
            
            for i, proxy in enumerate(proxies_to_check):
                logger.info(f"Проверяем прокси {i+1}/{len(proxies_to_check)}: {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()})")
                
                if self.validate_proxy_for_trast(proxy, timeout=30):  # Проверяем ТОЛЬКО на trast-zapchast.ru
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