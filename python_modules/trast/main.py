import os
import re
import time
import random
import logging
import requests
import shutil
import traceback
from datetime import datetime
from bs4 import BeautifulSoup
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from openpyxl import Workbook, load_workbook
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import geckodriver_autoinstaller
import csv
from bz_telebot.database_manager import set_script_start, set_script_end
from proxy_manager import ProxyManager

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from notification.main import TelegramNotifier

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_XML, LOG_DIR, BASE_DIR

LOG_DIR = os.path.join(BASE_DIR, "..", "..", "storage", "app", "public", "output", "logs-trast")
OUTPUT_FILE = os.path.join(LOG_DIR, "..", "trast.xlsx")
TEMP_OUTPUT_FILE = os.path.join(LOG_DIR, "..", "trast_temp.xlsx")
CSV_FILE = os.path.join(LOG_DIR, "..", "trast.csv")
TEMP_CSV_FILE = os.path.join(LOG_DIR, "..", "trast_temp.csv")
BACKUP_FILE = os.path.join(LOG_DIR, "..", "trast_backup.xlsx")
BACKUP_CSV = os.path.join(LOG_DIR, "..", "trast_backup.csv")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("trast")

# Сохраняем путь к лог-файлу для последующего переименования
LOG_FILE_PATH = os.path.join(LOG_DIR, f"trast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8-sig"),
        logging.StreamHandler()
    ]
)

total_products = 0

def create_new_excel(path):
    if os.path.exists(path):
        os.remove(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["Manufacturer", "Article", "Description", "Price"])
    wb.save(path)

def create_new_csv(path):
    if os.path.exists(path):
        os.remove(path)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["Manufacturer", "Article", "Description", "Price"])

def append_to_excel(path, product_list):
    global total_products
    if not os.path.exists(path):
        create_new_excel(path)
    try:
        wb = load_workbook(path)
        ws = wb.active
        for p in product_list:
            ws.append([
                p.get("manufacturer", ""),
                p.get("article", ""),
                p.get("description", ""),
                p.get("price", {}).get("price", "")
            ])
        wb.save(path)
        total_products += len(product_list)
    except Exception as e:
        logger.error(f"Error writing to Excel: {e}")
    try:
        file_size = os.path.getsize(path)
        logger.info(f"Excel updated with {len(product_list)} records, file size: {file_size} bytes")
    except:
        pass

def append_to_csv(path, product_list):
    try:
        with open(path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            for p in product_list:
                writer.writerow([
                    p.get("manufacturer", ""),
                    p.get("article", ""),
                    p.get("description", ""),
                    p.get("price", {}).get("price", "")
                ])
    except Exception as e:
        logger.error(f"Error writing to CSV: {e}")

def create_driver(proxy=None, proxy_manager=None, use_chrome=True):
    """Создает Chrome или Firefox драйвер с улучшенным обходом Cloudflare
    
    ВАЖНО: Если прокси SOCKS5/SOCKS4, Chrome автоматически не используется,
    т.к. Chrome не поддерживает SOCKS напрямую.
    """
    # Проверяем тип прокси - если SOCKS, используем Firefox
    if proxy:
        protocol = proxy.get('protocol', 'http').lower()
        if protocol in ['socks4', 'socks5']:
            logger.info(f"Прокси {protocol.upper()} - используем Firefox (Chrome не поддерживает SOCKS)")
            use_chrome = False
    
    # Пробуем сначала Chrome (лучше обходит Cloudflare), потом Firefox
    if use_chrome:
        try:
            return _create_chrome_driver(proxy)
        except (ValueError, Exception) as e:
            # ValueError если SOCKS прокси, другие ошибки - технические проблемы
            if "не поддерживает" in str(e) or "SOCKS" in str(e):
                logger.info(f"Прокси не поддерживается Chrome: {e}, используем Firefox...")
            else:
                logger.warning(f"Chrome не доступен: {e}, пробуем Firefox...")
    
    # Fallback на Firefox
    return _create_firefox_driver(proxy)

def _create_chrome_driver(proxy=None):
    """Создает Chrome драйвер с прокси
    
    Примечание: Chrome НЕ поддерживает SOCKS5 напрямую через --proxy-server.
    Для SOCKS5 прокси используйте Firefox (_create_firefox_driver).
    """
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium import webdriver
    
    driver_path = ChromeDriverManager().install()
    
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # User-Agent
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    selected_ua = random.choice(user_agents)
    options.add_argument(f"--user-agent={selected_ua}")
    
    # Настройка прокси для Chrome
    # ВАЖНО: Chrome не поддерживает SOCKS5 напрямую через --proxy-server
    # Используйте только HTTP/HTTPS для Chrome
    if proxy:
        protocol = proxy.get('protocol', 'http').lower()
        ip = proxy['ip']
        port = proxy['port']
        
        if protocol in ['http', 'https']:
            proxy_arg = f"{protocol}://{ip}:{port}"
            options.add_argument(f"--proxy-server={proxy_arg}")
            logger.debug(f"Chrome прокси настроен: {proxy_arg}")
        elif protocol in ['socks4', 'socks5']:
            # SOCKS5 не поддерживается в Chrome напрямую - пропускаем этот прокси
            logger.warning(f"Chrome не поддерживает {protocol.upper()} прокси напрямую. Используйте Firefox для SOCKS прокси.")
            raise ValueError(f"Chrome не поддерживает {protocol.upper()} прокси. Используйте Firefox.")
        else:
            proxy_arg = f"http://{ip}:{port}"
            options.add_argument(f"--proxy-server={proxy_arg}")
            logger.debug(f"Chrome прокси настроен (fallback на HTTP): {proxy_arg}")
    
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    
    # Stealth скрипты
    stealth_scripts = """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });
    window.chrome = { runtime: {} };
    """
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': stealth_scripts})
    
    return driver

def _create_firefox_driver(proxy=None):
    """Создает Firefox драйвер с прокси"""
    geckodriver_autoinstaller.install()
    
    options = Options()
    
    # Базовые настройки
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # DNS настройки - НЕ переопределяем при использовании прокси (прокси сам должен делать DNS)
    if not proxy:
        # Только если прокси нет, используем Google DNS
        options.set_preference("network.dns.disablePrefetch", True)
        options.set_preference("network.dns.disablePrefetchFromHTTPS", True)
        options.set_preference("network.dns.defaultIPv4", "8.8.8.8")
        options.set_preference("network.dns.defaultIPv6", "2001:4860:4860::8888")
    else:
        # При прокси - НЕ переопределяем DNS, пусть прокси сам делает DNS резолюцию
        # Для HTTP прокси DNS идет через прокси автоматически
        # Для SOCKS можно включить remote DNS
        if proxy.get('protocol', '').lower() in ['socks4', 'socks5']:
            options.set_preference("network.proxy.socks_remote_dns", True)
    
    # Обход Cloudflare - отключение автоматизации
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    # Случайный User-Agent
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
    ]
    selected_ua = random.choice(user_agents)
    options.set_preference("general.useragent.override", selected_ua)
    
    # Случайные платформы
    platforms = ["Win32", "MacIntel", "Linux x86_64"]
    options.set_preference("general.platform.override", random.choice(platforms))
    
    # Отключение WebRTC для предотвращения утечек IP
    options.set_preference("media.peerconnection.enabled", False)
    options.set_preference("media.navigator.enabled", False)
    
    # Увеличенные таймауты для медленных прокси
    options.set_preference("network.http.connection-timeout", 60)
    options.set_preference("network.http.response.timeout", 60)
    options.set_preference("network.http.keep-alive.timeout", 60)
    options.set_preference("network.http.request.timeout", 60)
    options.set_preference("network.dns.timeout", 30)
    
    # Отключение различных функций и трекинга
    options.set_preference("dom.disable_beforeunload", True)
    options.set_preference("dom.disable_window_open_feature", True)
    options.set_preference("dom.disable_window_move_resize", True)
    options.set_preference("dom.disable_window_flip", True)
    options.set_preference("dom.disable_window_crash_reporter", True)
    
    # Дополнительные настройки обхода детекции
    options.set_preference("privacy.trackingprotection.enabled", True)
    options.set_preference("privacy.trackingprotection.pbmode.enabled", True)
    options.set_preference("browser.safebrowsing.enabled", False)
    options.set_preference("browser.safebrowsing.malware.enabled", False)
    options.set_preference("browser.safebrowsing.phishing.enabled", False)
    options.set_preference("browser.safebrowsing.blockedURIs.enabled", False)
    
    # Отключение автоматических обновлений и телеметрии
    options.set_preference("app.update.enabled", False)
    options.set_preference("app.update.auto", False)
    options.set_preference("toolkit.telemetry.enabled", False)
    options.set_preference("toolkit.telemetry.unified", False)
    options.set_preference("datareporting.healthreport.uploadEnabled", False)
    
    # Настройки SSL/TLS для работы с прокси
    options.set_preference("security.tls.insecure_fallback_hosts", "trast-zapchast.ru")
    options.set_preference("security.tls.unrestricted_rc4_fallback", True)
    options.set_preference("security.tls.version.fallback-limit", 3)
    options.set_preference("security.tls.version.min", 1)
    options.set_preference("security.tls.version.max", 4)
    options.set_preference("security.ssl3.rsa_des_ede3_sha", True)
    options.set_preference("security.ssl3.rsa_rc4_128_sha", True)
    options.set_preference("security.ssl3.rsa_rc4_128_md5", True)
    options.set_preference("security.ssl3.rsa_des_sha", True)
    options.set_preference("security.ssl3.rsa_3des_ede_sha", True)
    options.set_preference("security.ssl3.rsa_aes_128_sha", True)
    options.set_preference("security.ssl3.rsa_aes_256_sha", True)
    options.set_preference("security.ssl3.rsa_aes_128_gcm_sha256", True)
    options.set_preference("security.ssl3.rsa_aes_256_gcm_sha384", True)
    
    # Дополнительные настройки для обхода SSL проблем
    options.set_preference("security.cert_pinning.enforcement_level", 0)
    options.set_preference("security.cert_pinning.process_headers_from_telemetry", False)
    options.set_preference("security.pki.certificate_transparency.mode", 0)
    options.set_preference("security.pki.sha1_enforcement_level", 0)
    
    # Настройка прокси
    if proxy:
        protocol = proxy.get('protocol', 'http').lower()
        ip = proxy['ip']
        port = proxy['port']
        
        if protocol in ['http', 'https']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", ip)
            options.set_preference("network.proxy.http_port", int(port))
            options.set_preference("network.proxy.ssl", ip)
            options.set_preference("network.proxy.ssl_port", int(port))
            options.set_preference("network.proxy.share_proxy_settings", True)
        elif protocol in ['socks4', 'socks5']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", ip)
            options.set_preference("network.proxy.socks_port", int(port))
            if protocol == 'socks5':
                options.set_preference("network.proxy.socks_version", 5)
            else:
                options.set_preference("network.proxy.socks_version", 4)
            options.set_preference("network.proxy.socks_remote_dns", True)
    
    # Создание драйвера
    service = Service()
    driver = webdriver.Firefox(service=service, options=options)
    
    # Дополнительные скрипты для обхода детекции Cloudflare
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    driver.execute_script("Object.defineProperty(navigator, 'permissions', {get: () => ({query: () => Promise.resolve({state: 'granted'})})})")
    driver.execute_script("Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4})")
    driver.execute_script("Object.defineProperty(navigator, 'deviceMemory', {get: () => 8})")
    driver.execute_script("Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0})")
    
    # Устанавливаем случайные размеры окна
    width = random.randint(1200, 1920)
    height = random.randint(800, 1080)
    driver.set_window_size(width, height)
    
    # Добавляем случайную задержку перед началом работы
    time.sleep(random.uniform(1, 3))
    
    return driver


def get_products_from_page_soup(soup):
    results = []
    cards = soup.select("div.product.product-plate")
    for card in cards:
        stock_badge = card.select_one("div.product-badge.product-stock.instock")
        if not stock_badge or "В наличии" not in stock_badge.text.strip():
            continue

        title_el = card.select_one("a.product-title")
        article_el = card.select_one("div.product-attributes .item:nth-child(1) .value")
        manufacturer_el = card.select_one("div.product-attributes .item:nth-child(2) .value")
        price_el = card.select_one("div.product-price .woocommerce-Price-amount.amount")

        if not (title_el and article_el and manufacturer_el and price_el):
            continue

        title = title_el.text.strip()
        article = article_el.text.strip()
        manufacturer = manufacturer_el.text.strip()
        raw_price = price_el.text.strip().replace("\xa0", " ")
        clean_price = re.sub(r"[^\d\s]", "", raw_price).strip()

        product = {
            "manufacturer": manufacturer,
            "article": article,
            "description": title,
            "price": {"price": clean_price}
        }
        results.append(product)
        logger.info(f"[Product Added] {product}")
    return results

def get_vps_external_ip():
    """
    Получает внешний IP адрес VPS для сравнения.
    Этот IP используется когда прокси НЕ используется.
    
    Returns:
        str: Внешний IP VPS или None если не удалось определить
    """
    # Внешний IP VPS (можно также получить автоматически через requests)
    VPS_EXTERNAL_IP = "31.172.69.102"
    
    # Пробуем несколько сервисов для определения IP VPS
    ip_services = [
        ("http://httpbin.org/ip", lambda r: r.json().get('origin', '').split(',')[0].strip() if hasattr(r, 'json') else None),
        ("https://api.ipify.org", lambda r: r.text.strip()),
        ("https://ifconfig.me/ip", lambda r: r.text.strip()),
        ("http://icanhazip.com", lambda r: r.text.strip()),
    ]
    
    for service_url, extract_func in ip_services:
        try:
            response = requests.get(service_url, timeout=3)
            detected_vps_ip = extract_func(response)
            
            if detected_vps_ip and detected_vps_ip.replace('.', '').isdigit():
                # Проверяем что это похоже на IP адрес
                parts = detected_vps_ip.split('.')
                if len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts if p.isdigit()):
                    # Если автоматически определенный IP совпадает с известным - используем его
                    if detected_vps_ip == VPS_EXTERNAL_IP:
                        logger.debug(f" Внешний IP VPS подтвержден через {service_url}: {VPS_EXTERNAL_IP}")
                        return VPS_EXTERNAL_IP
                    else:
                        # Если IP изменился, логируем предупреждение но используем определенный
                        logger.warning(f"[WARNING]  Внешний IP VPS изменился! Ожидался: {VPS_EXTERNAL_IP}, получен: {detected_vps_ip}")
                        logger.warning(f"   Используем автоматически определенный IP: {detected_vps_ip}")
                        return detected_vps_ip
        except Exception as e:
            logger.debug(f"Не удалось получить IP через {service_url}: {str(e)[:100]}")
            continue
    
    # Если не удалось определить автоматически, используем известный IP
    logger.debug(f"Не удалось автоматически определить IP VPS, используем известный: {VPS_EXTERNAL_IP}")
    return VPS_EXTERNAL_IP

def verify_proxy_usage(driver, proxy):
    """
    Проверяет, что прокси действительно используется через драйвер.
    Пробует несколько сервисов для получения IP и проверяет, что он отличается от локального.
    
    Returns:
        bool: True если прокси используется, False если не удалось подтвердить
    """
    if not proxy:
        return False
    
    proxy_ip = proxy.get('ip', '')
    proxy_country = proxy.get('country', '')
    
    # Получаем внешний IP VPS для сравнения
    vps_external_ip = get_vps_external_ip()
    if vps_external_ip:
        logger.debug(f" Внешний IP VPS (для сравнения): {vps_external_ip}")
    
    # Список сервисов для проверки IP (пробуем несколько для надежности)
    ip_check_services = [
        ("https://api.ipify.org", lambda text: text.strip()),
        ("http://httpbin.org/ip", lambda text: extract_json_ip(text)),
        ("https://ifconfig.me/ip", lambda text: text.strip()),
    ]
    
    external_ips = []
    
    # Сохраняем оригинальный таймаут для восстановления
    original_page_load_timeout = None
    try:
        original_page_load_timeout = driver.timeouts.page_load
    except:
        pass
    
    for service_url, extract_func in ip_check_services:
        try:
            logger.debug(f"Проверка IP через {service_url}...")
            
            # Устанавливаем короткий таймаут для страниц проверки IP
            try:
                driver.set_page_load_timeout(10)  # 10 секунд вместо дефолтных 30+
            except:
                pass
            
            try:
                driver.get(service_url)
            except Exception as timeout_error:
                error_msg = str(timeout_error).lower()
                if "timeout" in error_msg or "timed out" in error_msg:
                    logger.debug(f"  [WARNING]  Таймаут при загрузке {service_url}")
                elif "net::err_" in error_msg:
                    logger.debug(f"  [WARNING]  Сетевая ошибка: {error_msg[:100]}")
                else:
                    logger.debug(f"  [WARNING]  Ошибка загрузки {service_url}: {error_msg[:100]}")
                continue
            
            # Ждем немного для загрузки
            try:
                time.sleep(2)
            except:
                pass
            
            try:
                page_text = driver.page_source.strip()
            except:
                continue
            
            # Проверяем, что это не страница ошибки Chrome
            if "ERR_TIMED_OUT" in page_text or "This site can't be reached" in page_text or "ERR_" in page_text:
                logger.debug(f"  [WARNING]  Страница {service_url} недоступна (страница ошибки Chrome)")
                continue
            
            # Проверяем размер ответа (слишком большие ответы - вероятно HTML ошибки)
            if not page_text or len(page_text) > 200:
                logger.debug(f"  [WARNING]  Неожиданный размер ответа от {service_url}: {len(page_text)} символов")
                continue
            
            try:
                # Всегда ищем IP через regex в page_text (может быть обернут в HTML теги)
                import re
                ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
                
                # Сначала пробуем извлечь через функцию
                raw_ip = extract_func(page_text) if extract_func else page_text
                
                # Ищем IP в raw_ip (может быть HTML)
                ip_matches = re.findall(ip_pattern, str(raw_ip))
                if not ip_matches:
                    # Если не нашли, ищем во всем page_text
                    ip_matches = re.findall(ip_pattern, page_text)
                
                if ip_matches:
                    external_ip = ip_matches[0]  # Берем первый найденный IP
                    logger.debug(f"  Извлечен IP из ответа: {external_ip}")
                else:
                    logger.debug(f"  [WARNING]  Не удалось извлечь IP из ответа")
                    continue
            except Exception as extract_error:
                logger.debug(f"  [WARNING]  Ошибка извлечения IP из ответа {service_url}: {str(extract_error)[:100]}")
                continue
            
            # Проверяем, что это похоже на IP адрес (формат x.x.x.x где x - числа 0-255)
            if external_ip:
                parts = external_ip.split('.')
                if len(parts) == 4:
                    try:
                        # Проверяем что все части - числа в диапазоне 0-255
                        if all(0 <= int(p) <= 255 for p in parts if p.isdigit() and len(p) > 0):
                            external_ips.append(external_ip)
                            logger.info(f"  [OK] IP получен через {service_url}: {external_ip}")
                            break  # Нашли IP, можно не пробовать другие сервисы
                        else:
                            logger.debug(f"  [WARNING]  Неверный формат IP: {external_ip}")
                    except ValueError:
                        logger.debug(f"  [WARNING]  Не удалось распарсить IP: {external_ip}")
                else:
                    logger.debug(f"  [WARNING]  Не похоже на IP (не 4 части): {external_ip[:50]}")
            else:
                logger.debug(f"  [WARNING]  Не удалось извлечь IP из ответа")
        except Exception as e:
            logger.debug(f"  [WARNING]  Неожиданная ошибка при проверке через {service_url}: {str(e)[:100]}")
            continue
    
    # Восстанавливаем оригинальный таймаут
    if original_page_load_timeout is not None:
        try:
            driver.set_page_load_timeout(original_page_load_timeout)
        except:
            try:
                driver.set_page_load_timeout(30)  # Дефолтный таймаут
            except:
                pass
    else:
        try:
            driver.set_page_load_timeout(30)  # Дефолтный таймаут
        except:
            pass
    
    if not external_ips:
        logger.warning("  [WARNING]  Не удалось получить IP ни через один сервис")
        logger.warning("  [WARNING]  Это может быть из-за проблем с сетью, таймаутов или блокировки сервисов проверки IP")
        logger.warning("  [WARNING]  Прокси настроен в драйвере, но не можем подтвердить его использование")
        return False  # Не блокируем работу, но возвращаем False
    
    # Берем первый успешный IP
    detected_ip = external_ips[0]
    
    # Проверяем, что IP действительно через прокси
    # Примечание: IP может не совпадать с IP прокси-сервера, это нормально
    # Главное - проверить, что он не наш локальный IP
    
    logger.info(f" Обнаружен внешний IP через драйвер: {detected_ip}")
    logger.info(f" Прокси: {proxy_ip}:{proxy['port']} ({proxy.get('protocol', 'http').upper()})")
    if proxy_country:
        logger.info(f" Страна прокси: {proxy_country}")
    
    # КРИТИЧЕСКАЯ ПРОВЕРКА: IP должен отличаться от внешнего IP VPS
    if vps_external_ip:
        if detected_ip == vps_external_ip:
            logger.error(f"  [ERROR] ОШИБКА: Обнаружен IP совпадает с внешним IP VPS! Прокси НЕ ИСПОЛЬЗУЕТСЯ!")
            logger.error(f"  Внешний IP VPS: {vps_external_ip}, Обнаружен IP: {detected_ip}")
            logger.error(f"  [WARNING]  Трафик идет напрямую с VPS, без прокси!")
            return False
        else:
            logger.info(f"  [OK] IP отличается от внешнего IP VPS ({vps_external_ip}) - прокси работает!")
            logger.info(f"  [OK] Подтверждено использование прокси: {detected_ip} != {vps_external_ip}")
    
    # Дополнительная проверка: если есть несколько IP от разных сервисов, они должны совпадать
    if len(external_ips) > 1:
        unique_ips = set(external_ips)
        if len(unique_ips) > 1:
            logger.warning(f"  [WARNING]  Разные IP от разных сервисов: {external_ips}")
        else:
            logger.info(f"  [OK] IP подтвержден несколькими сервисами: {detected_ip}")
    
    return True

def extract_json_ip(text):
    """Извлекает IP из JSON ответа httpbin.org/ip"""
    try:
        import json
        data = json.loads(text)
        return data.get('origin', '').split(',')[0].strip()
    except:
        return text.strip()

def get_driver_with_working_proxy(proxy_manager, start_from_index=0):
    """Получает драйвер с рабочим прокси (пробует Chrome, потом Firefox)"""
    max_attempts = 100
    attempt = 0
    
    while attempt < max_attempts:
        try:
            if attempt == 0:
                # Первая попытка - ищем первый рабочий прокси
                proxy = proxy_manager.get_first_working_proxy(max_attempts=100)
            else:
                # Последующие попытки - ищем следующий рабочий прокси
                proxy, start_from_index = proxy_manager.get_next_working_proxy(start_from_index, max_attempts=50)
            
            if not proxy:
                logger.error("Не удалось найти рабочий прокси")
                return None, start_from_index
            
            logger.info(f"Создаем драйвер с прокси {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http').upper()})")
            logger.info(f"Пробуем этот прокси на оба браузера (Chrome → Firefox)")
            
            # Пробуем сначала Chrome (лучше обходит Cloudflare)
            driver = None
            chrome_worked = False
            try:
                logger.info(f"  [1/2] Пробуем создать Chrome драйвер с прокси {proxy['ip']}:{proxy['port']}...")
                driver = create_driver(proxy, proxy_manager, use_chrome=True)
                logger.info("[OK] Chrome драйвер создан")
                chrome_worked = True
            except Exception as chrome_error:
                logger.warning(f"  [ERROR] Chrome не удалось создать: {str(chrome_error)[:200]}")
                logger.info(f"  [2/2] Пробуем Firefox с тем же прокси {proxy['ip']}:{proxy['port']}...")
                try:
                    driver = create_driver(proxy, proxy_manager, use_chrome=False)
                    logger.info("[OK] Firefox драйвер создан")
                except Exception as firefox_error:
                    logger.error(f"  [ERROR] Firefox тоже не удалось создать: {str(firefox_error)[:200]}")
                    logger.warning(f"[WARNING]  Прокси {proxy['ip']}:{proxy['port']} не работает ни в Chrome, ни в Firefox")
                    logger.info(f"Переходим к следующему прокси...")
                    attempt += 1
                    continue
            
            if not driver:
                attempt += 1
                continue
            
            # ВАЖНО: Проверяем, что прокси действительно используется (неблокирующая проверка)
            try:
                proxy_verified = verify_proxy_usage(driver, proxy)
                if proxy_verified:
                    logger.info(f"[OK] ПОДТВЕРЖДЕНО: Прокси {proxy['ip']}:{proxy['port']} используется")
                else:
                    logger.warning(f"[WARNING]  Не удалось подтвердить использование прокси через проверку IP")
                    logger.warning(f"[WARNING]  Это может быть из-за проблем с сервисами проверки IP или сети")
                    logger.warning(f"[WARNING]  Продолжаем работу (прокси настроен в драйвере)")
            except Exception as verify_error:
                logger.warning(f"[WARNING]  Ошибка при проверке прокси: {str(verify_error)[:200]}")
                logger.warning(f"[WARNING]  Продолжаем работу (прокси настроен в драйвере)")
            
            # Сохраняем информацию о прокси в драйвер для последующей проверки
            driver.proxy_info = {
                'ip': proxy['ip'],
                'port': proxy['port'],
                'protocol': proxy.get('protocol', 'http'),
                'country': proxy.get('country', 'Unknown')
            }
            
            return driver, start_from_index
            
        except Exception as e:
            logger.error(f"Ошибка при создании драйвера: {e}")
            attempt += 1
            if attempt < max_attempts:
                logger.info(f"Попытка {attempt + 1}/{max_attempts}")
                time.sleep(2)
    
    # Если все прокси не сработали, ждем 10 минут и обновляем список прокси
    logger.error("Не удалось создать драйвер после всех попыток")
    logger.info("[WAIT] Ожидаем 10 минут перед обновлением списка прокси...")
    logger.info("   Возможно список прокси обновился в репозитории")
    
    wait_minutes = 10
    wait_seconds = wait_minutes * 60
    
    # Показываем прогресс каждую минуту
    for minute in range(wait_minutes):
        remaining = wait_minutes - minute - 1
        logger.info(f"   Осталось ждать: {remaining} минут...")
        time.sleep(60)  # Ждем 1 минуту
    
    logger.info("[OK] Ожидание завершено, обновляем список прокси...")
    
    # Принудительно обновляем список прокси (force_update=True)
    try:
        if proxy_manager.download_proxies(force_update=True):
            logger.info("[OK] Список прокси обновлен, пробуем еще раз...")
            # Сбрасываем индекс и пробуем заново
            return get_driver_with_working_proxy(proxy_manager, start_from_index=0)
        else:
            logger.warning("[WARNING]  Не удалось обновить список прокси, используем кэшированный")
            return None, start_from_index
    except Exception as update_error:
        logger.error(f"[ERROR] Ошибка при обновлении списка прокси: {update_error}")
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        return None, start_from_index

def get_pages_count_with_driver(driver, url="https://trast-zapchast.ru/shop/"):
    """Получает количество страниц с улучшенной обработкой Cloudflare"""
    try:
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        
        logger.info("Получаем количество страниц для парсинга...")
        
        # Устанавливаем таймаут для загрузки страницы (увеличен для медленных прокси)
        driver.set_page_load_timeout(90)  # 90 секунд вместо 60 для медленных прокси
        try:
            driver.get(url)
        except Exception as get_error:
            error_msg = str(get_error).lower()
            if "timeout" in error_msg or "timed out" in error_msg:
                logger.warning(f"[WARNING]  Таймаут при загрузке страницы {url}")
                logger.warning(f"[WARNING]  Прокси может быть слишком медленным или недоступным для целевого сайта")
            raise
        
        # Ждем загрузки страницы и скроллим для активации динамического контента
        wait = WebDriverWait(driver, 30)
        
        # Проверяем на Cloudflare и ждем его прохождения
        page_source_lower = driver.page_source.lower()
        max_wait = 30
        wait_time = 0
        
        while ("cloudflare" in page_source_lower or "checking your browser" in page_source_lower or "just a moment" in page_source_lower) and wait_time < max_wait:
            logger.info(f"[WAIT] Cloudflare проверка... ждем {wait_time}/{max_wait} сек")
            time.sleep(3)
            driver.refresh()
            time.sleep(2)
            page_source_lower = driver.page_source.lower()
            wait_time += 5
        
        # Скроллим для активации динамического контента (как в proxy_manager)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(random.uniform(1, 2))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(random.uniform(1, 2))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2, 3))
        
        # Дополнительное ожидание для полной загрузки
        time.sleep(3)
        
        # Пробуем найти элемент пагинации (используем ту же логику что в proxy_manager)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
        
        if last_page_el and last_page_el.has_attr("data-page"):
            total_pages = int(last_page_el["data-page"])
            logger.info(f"[OK] Найдено {total_pages} страниц для парсинга")
            return total_pages
        else:
            # Пробуем альтернативные селекторы
            if not last_page_el:
                last_page_el = soup.select_one(".facetwp-page.last")
            if not last_page_el:
                last_page_els = soup.select(".facetwp-pager .facetwp-page")
                if last_page_els:
                    last_page_el = last_page_els[-1]
            
            if last_page_el and last_page_el.has_attr("data-page"):
                total_pages = int(last_page_el["data-page"])
                logger.info(f"[OK] Найдено {total_pages} страниц для парсинга (альтернативный селектор)")
                return total_pages
            
            # Пробуем через WebDriverWait (как в proxy_manager)
            try:
                wait = WebDriverWait(driver, 10)
                last_page_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".facetwp-pager .facetwp-page.last")))
                if last_page_element.get_attribute("data-page"):
                    total_pages = int(last_page_element.get_attribute("data-page"))
                    logger.info(f"[OK] Найдено {total_pages} страниц для парсинга (через WebDriverWait)")
                    return total_pages
            except Exception as wait_error:
                logger.debug(f"WebDriverWait не помог: {wait_error}")
            
            # Сохраняем HTML для отладки
            debug_file = os.path.join(LOG_DIR, f"debug_pagination_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                logger.warning(f"[WARNING]  Не удалось найти информацию о количестве страниц")
                logger.warning(f"[WARNING]  HTML сохранен в {debug_file} для отладки")
                logger.warning(f"[WARNING]  Размер страницы: {len(driver.page_source)} символов")
                logger.warning(f"[WARNING]  Содержит 'facetwp': {'facetwp' in driver.page_source.lower()}")
                logger.warning(f"[WARNING]  Содержит 'shop': {'shop' in driver.page_source.lower()}")
            except:
                pass
            
            logger.warning(f"[WARNING]  Используем 1 страницу (не удалось определить количество)")
            return 1
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"[ERROR] Ошибка при получении количества страниц: {e}")
        
        # Если это таймаут, не сохраняем HTML (страница не загрузилась)
        if "timeout" in error_msg or "timed out" in error_msg:
            logger.error(f"[ERROR] Таймаут при загрузке страницы - страница не загрузилась")
            logger.error(f"[ERROR] Прокси не может подключиться к целевому сайту или слишком медленный")
        else:
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
            # Сохраняем HTML для отладки только если страница частично загрузилась
            try:
                if driver and hasattr(driver, 'page_source') and driver.page_source:
                    debug_file = os.path.join(LOG_DIR, f"debug_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    logger.error(f"[ERROR] HTML сохранен в {debug_file} для отладки")
            except Exception as save_error:
                logger.debug(f"Не удалось сохранить HTML для отладки: {save_error}")
        raise

def producer(proxy_manager):
    """Основная функция парсинга ТОЛЬКО через прокси"""
    thread_name = "MainThread"
    logger.info(f"[{thread_name}] Starting producer with PROXY-ONLY strategy")
    
    # Получаем драйвер с рабочим прокси
    driver, start_from_index = get_driver_with_working_proxy(proxy_manager)
    
    if not driver:
        logger.error("Не удалось создать драйвер с прокси")
        return 0
    
    total_collected = 0
    empty_pages_count = 0
    max_empty_pages = 3
    pages_checked = 0  # Счетчик проверенных страниц
    
    try:
        logger.info(f"Начинаем парсинг ТОЛЬКО через прокси")
        
        # Получаем количество страниц (с повторными попытками при таймауте)
        total_pages = None
        max_retries = 3
        
        for retry in range(max_retries):
            try:
                logger.info(f"Попытка {retry + 1}/{max_retries} получить количество страниц...")
                total_pages = get_pages_count_with_driver(driver)
                if total_pages and total_pages > 0:
                    logger.info(f"[OK] Успешно получено количество страниц: {total_pages}")
                    break
                else:
                    logger.warning(f"[WARNING]  Получено некорректное количество страниц: {total_pages}")
            except Exception as e:
                error_msg = str(e).lower()
                if "timeout" in error_msg or "timed out" in error_msg:
                    logger.warning(f"[WARNING]  Таймаут при получении количества страниц (попытка {retry + 1}/{max_retries})")
                    if retry < max_retries - 1:
                        logger.info(f"Пробуем другой прокси...")
                        try:
                            driver.quit()
                        except:
                            pass
                        driver, start_from_index = get_driver_with_working_proxy(proxy_manager, start_from_index)
                        if not driver:
                            logger.error("Не удалось получить новый драйвер для повторной попытки")
                            return 0
                        logger.info(f"Получен новый драйвер, пробуем еще раз...")
                        continue
                    else:
                        logger.error(f"[ERROR] Все попытки получить количество страниц завершились таймаутом")
                        return 0
                else:
                    logger.error(f"[ERROR] Ошибка при получении количества страниц: {e}")
                    if retry < max_retries - 1:
                        logger.info(f"Пробуем другой прокси...")
                        try:
                            driver.quit()
                        except:
                            pass
                        driver, start_from_index = get_driver_with_working_proxy(proxy_manager, start_from_index)
                        if not driver:
                            logger.error("Не удалось получить новый драйвер для повторной попытки")
                            return 0
                        continue
                    else:
                        return 0
        
        if not total_pages or total_pages <= 0:
            logger.error("[ERROR] Не удалось получить количество страниц после всех попыток")
            return 0
        
        for page_num in range(1, total_pages + 1):
            try:
                pages_checked += 1  # Увеличиваем счетчик проверенных страниц
                page_url = f"https://trast-zapchast.ru/shop/?_paged={page_num}"
                logger.info(f"[{thread_name}] Parsing page {page_num}/{total_pages} (проверено: {pages_checked})")
                
                driver.get(page_url)
                time.sleep(random.uniform(3, 6))  # Увеличиваем время ожидания
                
                # Проверяем на блокировку (расширенная проверка)
                page_source_lower = driver.page_source.lower()
                is_blocked = (
                    "cloudflare" in page_source_lower or 
                    "checking your browser" in page_source_lower or
                    "access denied" in page_source_lower or
                    "blocked" in page_source_lower or
                    "forbidden" in page_source_lower
                )
                
                if is_blocked:
                    logger.warning(f"Страница {page_num}: обнаружена блокировка (Cloudflare/access denied), пробуем другой прокси...")
                    try:
                        driver.quit()
                    except:
                        pass
                    driver, start_from_index = get_driver_with_working_proxy(proxy_manager, start_from_index)
                    if not driver:
                        logger.error("Не удалось получить новый драйвер")
                        break
                    # Пробуем ту же страницу с новым прокси
                    page_num -= 1  # Уменьшаем, т.к. в конце цикла будет увеличение
                    continue
                
                soup = BeautifulSoup(driver.page_source, "html.parser")
                products = get_products_from_page_soup(soup)
                
                if products:
                    # Пишем во временные файлы (старый файл не трогаем)
                    append_to_excel(TEMP_OUTPUT_FILE, products)
                    append_to_csv(TEMP_CSV_FILE, products)
                    logger.info(f"[{thread_name}] Page {page_num}: added {len(products)} products")
                    total_collected += len(products)
                    empty_pages_count = 0  # Сбрасываем счетчик пустых страниц
                else:
                    empty_pages_count += 1
                    logger.warning(f"[{thread_name}] Page {page_num}: no products found (empty pages: {empty_pages_count})")
                    
                    # Умная остановка: если 2 пустые страницы подряд И проверено больше 100 страниц
                    if empty_pages_count >= 2 and pages_checked > 100:
                        logger.info(f"[STOP]  Остановка парсинга: найдено {empty_pages_count} пустых страниц подряд и проверено {pages_checked} страниц (>100)")
                        logger.info(f"   Вероятно достигнут конец данных или все товары собраны")
                        break
                    
                    # Если несколько пустых страниц подряд - возможно блокировка
                    if empty_pages_count >= 2:
                        logger.warning(f"Найдено {empty_pages_count} пустых страниц подряд. Возможна блокировка, пробуем новый прокси...")
                        try:
                            driver.quit()
                        except:
                            pass
                        driver, start_from_index = get_driver_with_working_proxy(proxy_manager, start_from_index)
                        if not driver:
                            logger.error("Не удалось получить новый драйвер")
                            break
                        # Пробуем ту же страницу с новым прокси
                        page_num -= 1  # Уменьшаем, т.к. в конце цикла будет увеличение
                        pages_checked -= 1  # Уменьшаем счетчик, т.к. повторяем страницу
                        empty_pages_count = 0  # Сбрасываем счетчик при смене прокси
                        continue
                    
                    # Умная остановка: если 3 страницы подряд пустые (возможно конец данных)
                    if empty_pages_count >= max_empty_pages:
                        logger.info(f"Найдено {max_empty_pages} пустых страниц подряд. Останавливаем парсинг.")
                        break
                
                # Случайная пауза между страницами
                time.sleep(random.uniform(2, 4))
                
            except Exception as e:
                logger.error(f"Ошибка при парсинге страницы {page_num}: {e}")
                # Пробуем другой прокси при ошибке
                try:
                    driver.quit()
                except:
                    pass
                driver, start_from_index = get_driver_with_working_proxy(proxy_manager, start_from_index)
                if not driver:
                    logger.error("Не удалось получить новый драйвер после ошибки")
                    break
                
    finally:
        try:
            driver.quit()
        except:
            pass
    
    return total_collected

def create_backup():
    """Создает бэкап основных файлов перед обновлением"""
    try:
        if os.path.exists(OUTPUT_FILE):
            shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
            logger.info(f"Excel backup created: {BACKUP_FILE}")
        if os.path.exists(CSV_FILE):
            shutil.copy2(CSV_FILE, BACKUP_CSV)
            logger.info(f"CSV backup created: {BACKUP_CSV}")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")

def finalize_output_files():
    """
    Финализирует временные файлы - перемещает их в основные только при успехе.
    Это гарантирует, что старый файл не будет изменен при ошибке.
    """
    try:
        # Перемещаем временные файлы в основные только если они существуют
        if os.path.exists(TEMP_OUTPUT_FILE):
            # Создаем бэкап старого файла перед заменой
            if os.path.exists(OUTPUT_FILE):
                create_backup()
            
            # Перемещаем временный файл в основной
            shutil.move(TEMP_OUTPUT_FILE, OUTPUT_FILE)
            logger.info(f"[OK] Временный Excel файл перемещен в основной: {OUTPUT_FILE}")
        else:
            logger.warning("[WARNING]  Временный Excel файл не найден")
        
        if os.path.exists(TEMP_CSV_FILE):
            # Перемещаем временный CSV в основной
            shutil.move(TEMP_CSV_FILE, CSV_FILE)
            logger.info(f"[OK] Временный CSV файл перемещен в основной: {CSV_FILE}")
        else:
            logger.warning("[WARNING]  Временный CSV файл не найден")
            
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при финализации файлов: {e}")
        raise

def cleanup_temp_files():
    """Удаляет временные файлы в случае ошибки"""
    try:
        if os.path.exists(TEMP_OUTPUT_FILE):
            os.remove(TEMP_OUTPUT_FILE)
            logger.info(f"Временный Excel файл удален: {TEMP_OUTPUT_FILE}")
        if os.path.exists(TEMP_CSV_FILE):
            os.remove(TEMP_CSV_FILE)
            logger.info(f"Временный CSV файл удален: {TEMP_CSV_FILE}")
    except Exception as e:
        logger.warning(f"Не удалось удалить временные файлы: {e}")

def rename_log_file_by_status(status, total_products=0):
    """Переименовывает лог-файл с суффиксом на основе статуса
    
    Args:
        status: Статус парсинга ('done', 'insufficient_data', 'error')
        total_products: Количество собранных товаров (для определения успеха)
    """
    try:
        if not os.path.exists(LOG_FILE_PATH):
            logger.debug(f"Лог-файл не найден: {LOG_FILE_PATH}")
            return
        
        # Определяем суффикс на основе статуса
        if status == 'done' and total_products >= 100:
            suffix = "_success"
        elif status == 'insufficient_data':
            suffix = "_insufficient_data"
        elif status == 'error':
            suffix = "_failed"
        else:
            suffix = "_unknown"
        
        # Создаем новое имя файла
        base_name = os.path.splitext(LOG_FILE_PATH)[0]
        extension = os.path.splitext(LOG_FILE_PATH)[1]
        new_log_path = f"{base_name}{suffix}{extension}"
        
        # Переименовываем файл
        os.rename(LOG_FILE_PATH, new_log_path)
        logger.info(f" Лог-файл переименован: {os.path.basename(new_log_path)}")
        
    except Exception as e:
        logger.warning(f"[WARNING]  Не удалось переименовать лог-файл: {e}")

if __name__ == "__main__":
    script_name = "trast"
    logger.info("=== TRAST PARSER STARTED (PROXY-ONLY) ===")
    logger.info(f"Target URL: https://trast-zapchast.ru/shop/?_paged=1")
    logger.info(f"Start time: {datetime.now()}")
    TelegramNotifier.notify("Trast update started")
    error_message = None
    
    try:
        start_time = datetime.now()
        set_script_start(script_name)
        logger.info("[OK] Database connection successful")
    except Exception as db_error:
        logger.warning(f"[WARNING]  Database connection failed: {db_error}, continuing without DB...")
        # Продолжаем без БД
        start_time = datetime.now()

    # Создаем временные файлы для записи (основной файл не трогаем)
    try:
        create_new_excel(TEMP_OUTPUT_FILE)
        create_new_csv(TEMP_CSV_FILE)
        logger.info("[OK] Созданы временные файлы для записи данных")
    except Exception as file_error:
        logger.error(f"[ERROR] Ошибка при создании временных файлов: {file_error}")
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        TelegramNotifier.notify(f"Trast update failed: {file_error}")
        sys.exit(1)

    # Инициализируем прокси менеджер с фильтром по России
    logger.info("Step 1: Updating proxy list...")
    # Страны СНГ: Россия, Беларусь, Казахстан, Армения, Азербайджан, Грузия, Кыргызстан, Молдова, Таджикистан, Туркменистан, Узбекистан, Украина
    CIS_COUNTRIES = ["RU", "BY", "KZ", "AM", "AZ", "GE", "KG", "MD", "TJ", "TM", "UZ", "UA"]
    logger.info(f"Используем прокси из стран СНГ: {', '.join(CIS_COUNTRIES)}")
    try:
        proxy_manager = ProxyManager(country_filter=CIS_COUNTRIES)
        logger.info("[OK] ProxyManager инициализирован")
    except Exception as pm_error:
        logger.error(f"[ERROR] Ошибка при инициализации ProxyManager: {pm_error}")
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        TelegramNotifier.notify(f"Trast update failed: {pm_error}")
        sys.exit(1)
    
    # Стратегия ТОЛЬКО прокси - никакого прямого доступа
    logger.info("СТРАТЕГИЯ: ТОЛЬКО ПРОКСИ СНГ - никакого прямого доступа!")
    logger.info("Прокси проверяются ТОЛЬКО на способность получить количество страниц с trast-zapchast.ru")
    
    logger.info("============================================================")
    
    # Запускаем парсинг ТОЛЬКО через прокси
    try:
        total_products = producer(proxy_manager)
        logger.info(f"[OK] Producer завершился, собрано товаров: {total_products}")
    except Exception as producer_error:
        logger.error(f"[ERROR] Критическая ошибка в producer: {producer_error}")
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        total_products = 0
        status = 'error'
        TelegramNotifier.notify(f"Trast update failed: {producer_error}")
        cleanup_temp_files()
        try:
            set_script_end(script_name, status='error')
        except:
            pass
        # Переименовываем лог-файл перед выходом
        rename_log_file_by_status('error', total_products=0)
        sys.exit(1)

    status = 'done'
    try:
        if total_products >= 100:
            logger.info(f"[OK] Собрано {total_products} товаров - успешно!")
            # Перемещаем временные файлы в основные (старый файл сохраняется через бэкап)
            finalize_output_files()
            logger.info("[OK] Основные файлы обновлены успешно")
        else:
            logger.critical(f"❗ Недостаточно данных: {total_products} товаров")
            status = 'insufficient_data'
            # Удаляем временные файлы - основной файл НЕ ТРОГАЕМ
            cleanup_temp_files()
            logger.info("[WARNING]  Временные файлы удалены, основной файл не изменен")
            # Восстанавливаем из бэкапа только если есть
            if os.path.exists(BACKUP_FILE) and not os.path.exists(OUTPUT_FILE):
                shutil.copy2(BACKUP_FILE, OUTPUT_FILE)
                logger.info("Excel восстановлен из бэкапа")
            if os.path.exists(BACKUP_CSV) and not os.path.exists(CSV_FILE):
                shutil.copy2(BACKUP_CSV, CSV_FILE)
                logger.info("CSV восстановлен из бэкапа")
    except Exception as e:
        logger.exception(f"[ERROR] Ошибка при финализации: {e}")
        status = 'error'
        error_message = str(e)
        # При ошибке удаляем временные файлы - основной файл остается нетронутым
        cleanup_temp_files()
        logger.info("[WARNING]  При ошибке временные файлы удалены, основной файл не изменен")

    duration = (datetime.now() - start_time).total_seconds()
    try:
        set_script_end(script_name, status=status)
    except Exception as db_end_error:
        logger.warning(f"[WARNING]  Ошибка при сохранении окончания в БД: {db_end_error}")
        if status != 'done':
            error_message = error_message or str(db_end_error)

    logger.info("============================================================")
    logger.info(f"Парсинг завершен! Всего собрано товаров: {total_products}")
    logger.info(f"Время выполнения: {round(duration, 2)} секунд")
    logger.info(f"Статус: {status}")
    logger.info(f"Товаров собрано: {total_products}")
    logger.info("============================================================")

    if status == 'done':
        TelegramNotifier.notify(f"Trast update completed successfully. Duration: {duration:.2f} seconds. Products collected: {total_products}")
    elif status == 'insufficient_data':
        TelegramNotifier.notify(f"Trast update completed with insufficient data. Duration: {duration:.2f} seconds. Products collected: {total_products}")
    else:
        failure_details = error_message or "Unknown error"
        TelegramNotifier.notify(f"Trast update failed: {failure_details}")
    
    # Переименовываем лог-файл на основе статуса
    rename_log_file_by_status(status, total_products=total_products)
