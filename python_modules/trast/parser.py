"""
Parser module for Trast parser.

Handles page fetching with requests-first approach and Selenium fallback.
"""

import time
import random
from typing import Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup
import httpx
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from config import TrastConfig
from logger_setup import LoggerMixin
from connection_manager import ConnectionResult


class PageFetcher(LoggerMixin):
    """Handles page fetching with multiple strategies."""
    
    def __init__(self):
        self.session = None
        self.driver = None
    
    def _detect_cloudflare(self, content: str, status_code: int) -> bool:
        """Detect Cloudflare protection."""
        content_lower = content.lower()
        
        for indicator in TrastConfig.CLOUDFLARE_INDICATORS:
            if indicator in content_lower:
                self.logger.warning(f"Cloudflare detected: {indicator}")
                return True
        
        if status_code in [403, 503]:
            self.logger.warning(f"Cloudflare likely (status {status_code})")
            return True
        
        return False
    
    def _create_requests_session(self, connection_result: ConnectionResult) -> requests.Session:
        """Create requests session with proxy configuration."""
        session = requests.Session()
        
        if connection_result and connection_result.success:
            proxy_config = connection_result.proxy_config
            if proxy_config:
                session.proxies.update(proxy_config)
                self.logger.debug(f"Using proxy for requests: {proxy_config}")
        
        session.headers.update(TrastConfig.get_headers_with_user_agent())
        return session
    
    def _create_httpx_client(self, connection_result: ConnectionResult) -> httpx.Client:
        """Create httpx client with proxy configuration."""
        proxy_url = None
        
        if connection_result and connection_result.success:
            proxy_config = connection_result.proxy_config
            if proxy_config:
                # httpx использует proxy_url вместо proxies
                proxy_url = proxy_config.get('http') or proxy_config.get('https')
                self.logger.debug(f"Using proxy for httpx: {proxy_url}")
        
        return httpx.Client(
            proxy=proxy_url,
            headers=TrastConfig.get_headers_with_user_agent(),
            timeout=TrastConfig.REQUEST_TIMEOUT,
            follow_redirects=True
        )
    
    def fetch_with_requests(self, url: str, connection_result: ConnectionResult) -> Tuple[bool, str, int]:
        """Fetch page using requests library."""
        try:
            session = self._create_requests_session(connection_result)
            
            self.logger.info(f"Fetching {url} with requests...")
            start_time = time.time()
            
            response = session.get(url, timeout=TrastConfig.REQUEST_TIMEOUT)
            response_time = time.time() - start_time
            
            self.logger.info(f"Requests response: {response.status_code} ({response_time:.2f}s)")
            
            # Check for Cloudflare
            if self._detect_cloudflare(response.text, response.status_code):
                self.logger.warning("Cloudflare detected, will try Selenium")
                return False, response.text, response.status_code
            
            if response.status_code == 200:
                self.logger.info("Page fetched successfully with requests")
                return True, response.text, response.status_code
            else:
                self.logger.warning(f"Unexpected status code: {response.status_code}")
                return False, response.text, response.status_code
                
        except Exception as e:
            self.logger.error(f"Requests fetch failed: {e}")
            return False, "", 0
    
    def fetch_with_httpx(self, url: str, connection_result: ConnectionResult) -> Tuple[bool, str, int]:
        """Fetch page using httpx library."""
        try:
            with self._create_httpx_client(connection_result) as client:
                self.logger.info(f"Fetching {url} with httpx...")
                start_time = time.time()
                
                response = client.get(url)
                response_time = time.time() - start_time
                
                self.logger.info(f"httpx response: {response.status_code} ({response_time:.2f}s)")
                
                # Check for Cloudflare
                if self._detect_cloudflare(response.text, response.status_code):
                    self.logger.warning("Cloudflare detected, will try Selenium")
                    return False, response.text, response.status_code
                
                if response.status_code == 200:
                    self.logger.info("Page fetched successfully with httpx")
                    return True, response.text, response.status_code
                else:
                    self.logger.warning(f"Unexpected status code: {response.status_code}")
                    return False, response.text, response.status_code
                    
        except Exception as e:
            self.logger.error(f"httpx fetch failed: {e}")
            return False, "", 0
    
    def _create_selenium_driver(self, connection_result: ConnectionResult) -> Optional[webdriver.Remote]:
        """Create Selenium WebDriver with proxy configuration."""
        try:
            # Попробуем Firefox сначала (лучше для серверов)
            try:
                from selenium.webdriver.firefox.options import Options as FirefoxOptions
                from selenium.webdriver.firefox.service import Service as FirefoxService
                
                self.logger.info("Attempting to create Firefox driver...")
                
                options = FirefoxOptions()
                
                # Firefox options
                for option in TrastConfig.FIREFOX_OPTIONS:
                    options.add_argument(option)
                
                # Add random user agent
                user_agent = TrastConfig.get_random_user_agent()
                options.set_preference("general.useragent.override", user_agent)
                
                # Дополнительные настройки для обхода блокировок
                options.set_preference("dom.webdriver.enabled", False)
                options.set_preference("useAutomationExtension", False)
                options.set_preference("general.platform.override", "Linux x86_64")
                options.set_preference("general.appversion.override", "5.0 (X11)")
                options.set_preference("general.oscpu.override", "Linux x86_64")
                
                # Configure proxy
                if connection_result and connection_result.success:
                    proxy_url = connection_result.proxy_config.get('http', '') if connection_result.proxy_config else None
                    if proxy_url:
                        if proxy_url.startswith('socks5://'):
                            options.set_preference("network.proxy.type", 1)
                            options.set_preference("network.proxy.socks", "127.0.0.1")
                            options.set_preference("network.proxy.socks_port", 40000)
                            options.set_preference("network.proxy.socks_version", 5)
                        elif proxy_url.startswith('http://'):
                            options.set_preference("network.proxy.type", 1)
                            options.set_preference("network.proxy.http", "127.0.0.1")
                            options.set_preference("network.proxy.http_port", 40000)
                        self.logger.debug(f"Using proxy for Firefox: {proxy_url}")
                
                # Создаем сервис с явным указанием пути к geckodriver
                service = FirefoxService()
                
                # Create Firefox driver
                driver = webdriver.Firefox(options=options, service=service)
                self.logger.info("✅ Firefox WebDriver created successfully")
                
            except Exception as firefox_error:
                self.logger.warning(f"❌ Firefox failed: {firefox_error}")
                self.logger.info("Trying Chrome as fallback...")
                
                # Fallback to Chrome
                try:
                    from selenium.webdriver.chrome.service import Service as ChromeService
                    
                    options = ChromeOptions()
                    
                    # Add Chrome options
                    for option in TrastConfig.CHROME_OPTIONS:
                        options.add_argument(option)
                    
                    # Add random user agent
                    user_agent = TrastConfig.get_random_user_agent()
                    options.add_argument(f"--user-agent={user_agent}")
                    
                    # Configure proxy
                    if connection_result and connection_result.success:
                        proxy_url = connection_result.proxy_config.get('http', '') if connection_result.proxy_config else None
                        if proxy_url:
                            if proxy_url.startswith('socks5://'):
                                options.add_argument(f"--proxy-server={proxy_url}")
                            elif proxy_url.startswith('http://'):
                                options.add_argument(f"--proxy-server={proxy_url}")
                            self.logger.debug(f"Using proxy for Chrome: {proxy_url}")
                    
                    # Создаем сервис для Chrome
                    service = ChromeService()
                    
                    # Create Chrome driver
                    driver = webdriver.Chrome(options=options, service=service)
                    self.logger.info("✅ Chrome WebDriver created successfully")
                    
                except Exception as chrome_error:
                    self.logger.error(f"❌ Chrome also failed: {chrome_error}")
                    raise Exception(f"Both Firefox and Chrome failed. Firefox: {firefox_error}, Chrome: {chrome_error}")
            
            driver.set_page_load_timeout(TrastConfig.SELENIUM_PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(TrastConfig.SELENIUM_IMPLICIT_WAIT)
            
            return driver
            
        except Exception as e:
            self.logger.error(f"❌ Failed to create any Selenium driver: {e}")
            return None
    
    def fetch_with_selenium(self, url: str, connection_result: ConnectionResult) -> Tuple[bool, str, int]:
        """Fetch page using Selenium WebDriver."""
        driver = None
        
        try:
            driver = self._create_selenium_driver(connection_result)
            if not driver:
                return False, "", 0
            
            self.logger.info(f"Fetching {url} with Selenium...")
            start_time = time.time()
            
            # Сначала идем на главную страницу для установки сессии
            try:
                self.logger.info("Establishing session on main page...")
                driver.get(TrastConfig.BASE_URL)
                time.sleep(random.uniform(3, 6))
                
                # Симулируем человеческое поведение
                driver.execute_script("window.scrollTo(0, 100);")
                time.sleep(random.uniform(1, 3))
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(random.uniform(1, 2))
                
            except Exception as e:
                self.logger.warning(f"Session establishment failed: {e}")
            
            # Navigate to target page
            self.logger.info(f"Navigating to target page: {url}")
            driver.get(url)
            
            # Wait for page to load with progressive delays
            initial_wait = random.uniform(5, 10)
            self.logger.info(f"Initial wait: {initial_wait:.1f}s...")
            time.sleep(initial_wait)
            
            # Check for Cloudflare challenge
            page_source = driver.page_source
            if self._detect_cloudflare(page_source, 200):
                self.logger.info("Cloudflare challenge detected, applying bypass strategy...")
                
                # Стратегия обхода Cloudflare
                bypass_attempts = 0
                max_bypass_attempts = 3
                
                while bypass_attempts < max_bypass_attempts:
                    bypass_attempts += 1
                    self.logger.info(f"Cloudflare bypass attempt {bypass_attempts}/{max_bypass_attempts}")
                    
                    # Дополнительное ожидание
                    additional_wait = random.uniform(15, 30)
                    self.logger.info(f"Extended wait: {additional_wait:.1f}s...")
                    time.sleep(additional_wait)
                    
                    # Симулируем активность пользователя
                    try:
                        # Скроллинг
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                        time.sleep(random.uniform(2, 4))
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(random.uniform(1, 2))
                        
                        # Клик по пустому месту
                        driver.execute_script("document.body.click();")
                        time.sleep(random.uniform(1, 2))
                        
                    except Exception as e:
                        self.logger.debug(f"User simulation error: {e}")
                    
                    # Проверяем результат
                    page_source = driver.page_source
                    if not self._detect_cloudflare(page_source, 200):
                        self.logger.info("Cloudflare bypass successful!")
                        break
                    else:
                        self.logger.warning(f"Cloudflare still present after attempt {bypass_attempts}")
                        
                        if bypass_attempts < max_bypass_attempts:
                            # Попробуем обновить страницу
                            self.logger.info("Refreshing page...")
                            driver.refresh()
                            time.sleep(random.uniform(5, 10))
            
            # Try to wait for specific elements
            try:
                self.logger.info("Waiting for page content...")
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Дополнительная проверка на наличие контента
                WebDriverWait(driver, 10).until(
                    lambda d: len(d.page_source) > 1000
                )
                
            except TimeoutException:
                self.logger.warning("Timeout waiting for page elements")
            
            response_time = time.time() - start_time
            page_source = driver.page_source
            
            self.logger.info(f"Selenium fetch completed ({response_time:.2f}s)")
            self.logger.info(f"Page source length: {len(page_source)} characters")
            
            # Более детальная проверка контента
            if page_source and len(page_source) > 1000:
                # Проверяем, что это не страница ошибки
                if any(indicator in page_source.lower() for indicator in ['error', 'not found', 'access denied', 'blocked']):
                    self.logger.warning("Page appears to be an error page")
                    return False, page_source, 0
                
                self.logger.info("Page fetched successfully with Selenium")
                return True, page_source, 200
            else:
                self.logger.warning("Selenium returned empty or short content")
                return False, page_source, 0
                
        except Exception as e:
            self.logger.error(f"Selenium fetch failed: {e}")
            return False, "", 0
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    self.logger.debug(f"Error closing driver: {e}")
    
    def fetch_page(self, url: str, connection_result: ConnectionResult) -> Tuple[bool, str, int]:
        """Fetch page with fallback strategy: httpx -> requests -> selenium."""
        
        # Try httpx first (fastest)
        success, content, status_code = self.fetch_with_httpx(url, connection_result)
        if success:
            return True, content, status_code
        
        # Try requests as fallback
        success, content, status_code = self.fetch_with_requests(url, connection_result)
        if success:
            return True, content, status_code
        
        # Try Selenium as last resort
        self.logger.info("Falling back to Selenium...")
        success, content, status_code = self.fetch_with_selenium(url, connection_result)
        
        return success, content, status_code


class PageParser(LoggerMixin):
    """Handles parsing of page content."""
    
    def extract_page_count(self, html_content: str) -> Optional[int]:
        """Extract total page count from pagination."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for pagination element
            pagination_element = soup.select_one(TrastConfig.PAGINATION_SELECTOR)
            
            if pagination_element:
                page_count_str = pagination_element.get(TrastConfig.PAGE_COUNT_ATTRIBUTE)
                if page_count_str:
                    try:
                        page_count = int(page_count_str)
                        self.logger.info(f"Found pagination: {page_count} pages")
                        return page_count
                    except ValueError:
                        self.logger.warning(f"Invalid page count value: {page_count_str}")
            
            # Alternative selectors to try
            alternative_selectors = [
                "a.facetwp-page.last",
                ".facetwp-pager a.last",
                ".pagination a.last",
                "a[data-page]"
            ]
            
            for selector in alternative_selectors:
                elements = soup.select(selector)
                for element in elements:
                    page_count_str = element.get('data-page') or element.get_text().strip()
                    if page_count_str and page_count_str.isdigit():
                        page_count = int(page_count_str)
                        self.logger.info(f"Found pagination with selector '{selector}': {page_count} pages")
                        return page_count
            
            self.logger.warning("No pagination found")
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting page count: {e}")
            return None
    
    def extract_product_links(self, html_content: str) -> list:
        """Extract product links from catalog page."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Common selectors for product links
            product_selectors = [
                "a[href*='/product/']",
                "a[href*='/shop/']",
                ".product a",
                ".woocommerce-loop-product__link",
                ".product-item a"
            ]
            
            product_links = []
            
            for selector in product_selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href and ('/product/' in href or '/shop/' in href):
                        # Convert relative URLs to absolute
                        if href.startswith('/'):
                            href = TrastConfig.BASE_URL + href
                        elif not href.startswith('http'):
                            href = TrastConfig.BASE_URL + '/' + href
                        
                        if href not in product_links:
                            product_links.append(href)
            
            self.logger.info(f"Found {len(product_links)} product links")
            return product_links
            
        except Exception as e:
            self.logger.error(f"Error extracting product links: {e}")
            return []
    
    def extract_product_data(self, html_content: str) -> Dict[str, Any]:
        """Extract product data from product page."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            product_data = {}
            
            # Extract title
            title_selectors = [
                "h1.product_title",
                "h1.entry-title",
                ".product-title h1",
                "h1"
            ]
            
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    product_data['title'] = title_element.get_text().strip()
                    break
            
            # Extract manufacturer
            manufacturer_selectors = [
                "div.wl-attr--item.pa_proizvoditel",
                ".manufacturer",
                ".brand",
                "[data-attribute='pa_proizvoditel']"
            ]
            
            for selector in manufacturer_selectors:
                manufacturer_element = soup.select_one(selector)
                if manufacturer_element:
                    product_data['manufacturer'] = manufacturer_element.get_text().strip()
                    break
            
            # Extract SKU/Article
            sku_selectors = [
                "div.wl-attr--item.sku",
                ".sku",
                ".product-sku",
                "[data-attribute='sku']"
            ]
            
            for selector in sku_selectors:
                sku_element = soup.select_one(selector)
                if sku_element:
                    product_data['sku'] = sku_element.get_text().strip()
                    break
            
            # Extract price
            price_selectors = [
                "div.wl-variable--price",
                ".price",
                ".product-price",
                ".woocommerce-Price-amount"
            ]
            
            for selector in price_selectors:
                price_element = soup.select_one(selector)
                if price_element:
                    price_text = price_element.get_text().strip()
                    # Extract numeric price
                    import re
                    price_match = re.search(r'[\d\s,]+', price_text)
                    if price_match:
                        product_data['price'] = price_match.group().replace(' ', '').replace(',', '')
                    break
            
            return product_data
            
        except Exception as e:
            self.logger.error(f"Error extracting product data: {e}")
            return {}


class TrastParser(LoggerMixin):
    """Main parser class combining fetching and parsing."""
    
    def __init__(self):
        self.fetcher = PageFetcher()
        self.parser = PageParser()
    
    def parse_first_page(self, connection_result: ConnectionResult) -> Tuple[bool, Optional[int], str]:
        """Parse first page to get page count."""
        self.logger.info("Parsing first page to get page count...")
        
        success, content, status_code = self.fetcher.fetch_page(
            TrastConfig.FIRST_PAGE_URL, 
            connection_result
        )
        
        if not success:
            self.logger.error("Failed to fetch first page")
            return False, None, ""
        
        page_count = self.parser.extract_page_count(content)
        
        if page_count:
            self.logger.info(f"Successfully extracted page count: {page_count}")
            return True, page_count, content
        else:
            self.logger.warning("Could not extract page count from first page")
            return False, None, content
