"""
Core parsing logic module for Trast parser.

Handles product extraction, pagination, and page fetching with retries.
"""

import time
import random
import logging
import re
import os
from typing import List, Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .config import TrastConfig
from .anti_block import BlockDetector, HumanBehaviorSimulator, DelayStrategy, SessionEstablisher

logger = logging.getLogger("trast.parser_core")


class ProductExtractor:
    """Extracts product data from HTML content."""
    
    @staticmethod
    def extract_from_soup(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract products from BeautifulSoup object."""
        results = []
        cards = soup.select("div.product.product-plate")
        total_cards = len(cards)
        available_cards = 0
        
        for card in cards:
            # Check if product is in stock
            stock_badge = card.select_one("div.product-badge.product-stock.instock")
            if not stock_badge or "В наличии" not in stock_badge.text.strip():
                continue

            available_cards += 1
            
            # Extract product information
            title_el = card.select_one("a.product-title")
            article_el = card.select_one("div.product-attributes .item:nth-child(1) .value")
            manufacturer_el = card.select_one("div.product-attributes .item:nth-child(2) .value")
            price_el = card.select_one("div.product-price .amount")

            if not (title_el and article_el and manufacturer_el and price_el):
                continue

            # Clean and format data
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
        
        logger.info(f"[Page Stats] Total cards: {total_cards}, Available: {available_cards}, Added: {len(results)}")
        return results
    
    @staticmethod
    def get_page_count(driver, url: str = None) -> int:
        """Get total number of pages."""
        if url is None:
            url = TrastConfig.SHOP_URL
            
        try:
            # Try to access main page first to establish session
            logger.info("Accessing main page first to establish session...")
            driver.get(TrastConfig.MAIN_URL)
            time.sleep(3)
            
            # Now try to access shop page
            logger.info("Now accessing shop page...")
            driver.get(url)
        except Exception as e:
            logger.warning(f"Error accessing main page: {e}")
            driver.get(url)
        
        # Wait for products to load (FacetWP AJAX)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.product.product-plate"))
            )
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Timeout waiting for products: {e}")
            # Save HTML for debugging
            with open(os.path.join(TrastConfig.LOG_DIR, "debug_page.html"), "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Try FacetWP pagination first
        last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
        if last_page_el and last_page_el.has_attr("data-page"):
            return int(last_page_el["data-page"])
        
        # Try WordPress pagination with _paged parameter
        pagination_selectors = [
            ".page-numbers",
            ".pagination", 
            ".woocommerce-pagination",
            ".pager",
            "nav.pagination",
            ".page-links"
        ]
        
        for selector in pagination_selectors:
            try:
                pagination = soup.select_one(selector)
                if pagination:
                    # Look for page numbers
                    page_links = pagination.select("a, span")
                    page_numbers = []
                    
                    for link in page_links:
                        text = link.get_text().strip()
                        if text.isdigit():
                            page_numbers.append(int(text))
                    
                    if page_numbers:
                        max_page = max(page_numbers)
                        logger.info(f"📊 Found {max_page} pages using selector: {selector}")
                        return max_page
                        
            except Exception:
                continue
        
        # Fallback: look for _paged parameter in current URL
        try:
            current_url = driver.current_url
            if "_paged=" in current_url:
                # Try to find next page link
                next_links = soup.select("a[href*='_paged=']")
                max_page = 1
                
                for link in next_links:
                    href = link.get("href", "")
                    if "_paged=" in href:
                        try:
                            page_num = int(href.split("_paged=")[1].split("&")[0])
                            max_page = max(max_page, page_num)
                        except:
                            continue
                
                if max_page > 1:
                    logger.info(f"📊 Found {max_page} pages from URL analysis")
                    return max_page
                    
        except Exception:
            pass
        
        logger.warning("⚠️ Could not determine page count, defaulting to 1")
        return 1
    
    @staticmethod
    def try_bulk_fetch(driver) -> Optional[List[Dict[str, Any]]]:
        """Try to fetch all data by getting page count first."""
        try:
            # First, get the total page count
            logger.info("🔍 Determining total page count...")
            total_pages = ProductExtractor.get_page_count(driver)
            logger.info(f"📊 Total pages found: {total_pages}")
            
            if total_pages <= 0:
                logger.warning("No pages found, falling back to regular parsing")
                return None
            
            # Try to get products from first few pages to test
            test_pages = min(3, total_pages)  # Test first 3 pages or all if less
            all_products = []
            
            for page_num in range(1, test_pages + 1):
                try:
                    url = f"{TrastConfig.SHOP_URL}?_paged={page_num}"
                    logger.info(f"🚀 Testing page {page_num}/{test_pages}: {url}")
                    driver.get(url)
                    
                    # Human behavior
                    HumanBehaviorSimulator.apply_behavior(driver)
                    
                    # Check for CAPTCHA
                    if BlockDetector.check_for_captcha(driver):
                        logger.warning("🛡️ CAPTCHA detected, waiting...")
                        DelayStrategy.cloudflare_safe_delay()
                        continue
                    
                    # Additional wait for loading
                    time.sleep(random.uniform(3, 8))
                    
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    products = ProductExtractor.extract_from_soup(soup)
                    
                    if products:
                        logger.info(f"✅ Page {page_num}: found {len(products)} products")
                        all_products.extend(products)
                    else:
                        logger.warning(f"⚠️ Page {page_num}: no products found")
                        
                except Exception as e:
                    logger.debug(f"Error on page {page_num}: {e}")
                    continue
            
            if all_products:
                logger.info(f"✅ Bulk test successful! Got {len(all_products)} products from {test_pages} pages")
                return all_products
            else:
                logger.info("Bulk test failed, using regular parsing")
                return None
                
        except Exception as e:
            logger.error(f"Error in bulk fetch: {e}")
            return None


class PageFetcher:
    """Handles page fetching with retry logic."""
    
    def __init__(self, session_establisher: SessionEstablisher):
        self.session_establisher = session_establisher
    
    def fetch_with_retry(self, driver, url: str, current_proxy, max_retries: int = 3) -> Tuple[bool, Any, Any]:
        """Fetch page with retry logic."""
        for attempt in range(max_retries):
            try:
                logger.info(f"🌐 Loading page: {url}")
                driver.get(url)
                
                # Human behavior after loading
                HumanBehaviorSimulator.apply_behavior(driver)
                
                # Check for CAPTCHA
                if BlockDetector.check_for_captcha(driver):
                    logger.warning("🛡️ CAPTCHA detected, waiting...")
                    DelayStrategy.cloudflare_safe_delay()
                    
                    # Re-check
                    if BlockDetector.check_for_captcha(driver):
                        logger.error("🛡️ CAPTCHA persists, switching proxy")
                        return False, driver, current_proxy
                
                # Wait for products to load
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.product.product-plate"))
                )
                
                # Additional human behavior
                HumanBehaviorSimulator.apply_behavior(driver)
                
                logger.info("✅ Page loaded successfully")
                return True, driver, current_proxy
                
            except Exception as e:
                wait_time = (2 ** attempt) * 10
                logger.warning(f"❌ Attempt {attempt+1}/{max_retries} failed: {e}")
                logger.warning(f"⏳ Waiting {wait_time}s before next attempt")
                
                # Cloudflare-safe delay on errors
                DelayStrategy.cloudflare_safe_delay()
                
                if attempt < max_retries - 1:
                    logger.info("🔄 Switching proxy...")
                    return False, driver, current_proxy  # Signal to switch proxy
        
        return False, driver, current_proxy
    
    def handle_fetch_error(self, error: Exception, attempt: int):
        """Handle fetch errors with appropriate logging."""
        logger.error(f"Fetch error on attempt {attempt}: {error}")
        
        # Log specific error types
        if "timeout" in str(error).lower():
            logger.warning("Timeout error - may need longer delays")
        elif "captcha" in str(error).lower():
            logger.warning("CAPTCHA error - need to wait longer")
        elif "blocked" in str(error).lower():
            logger.warning("Blocking error - need new IP")


class ParsingOrchestrator:
    """Orchestrates the parsing process."""
    
    def __init__(self):
        self.product_extractor = ProductExtractor()
        self.session_establisher = SessionEstablisher()
        self.page_fetcher = PageFetcher(self.session_establisher)
        self.total_collected = 0
        self.pages_processed = 0
    
    def parse_all_pages(self, driver, start_page: int = 1, end_page: int = None) -> List[Dict[str, Any]]:
        """Parse all pages from start to end."""
        all_products = []
        
        try:
            # Get total pages if not specified
            if end_page is None:
                end_page = self.product_extractor.get_page_count(driver)
                logger.info(f"Total pages to parse: {end_page}")
            
            # Session-based parsing for rate limiting
            pages_per_session = TrastConfig.PAGES_PER_SESSION
            sessions_needed = (end_page - start_page + 1 + pages_per_session - 1) // pages_per_session
            
            logger.info(f"Will parse in {sessions_needed} sessions of {pages_per_session} pages each")
            
            for session in range(sessions_needed):
                session_start_page = start_page + session * pages_per_session
                session_end_page = min(session_start_page + pages_per_session - 1, end_page)
                
                logger.info(f"Session {session + 1}/{sessions_needed}: pages {session_start_page}-{session_end_page}")
                
                session_products = self.parse_session(driver, session_start_page, session_end_page)
                all_products.extend(session_products)
                
                # Session break for rate limiting
                if session < sessions_needed - 1:
                    session_progress = ((session + 1) / sessions_needed) * 100
                    logger.info(f"Session {session + 1}/{sessions_needed} completed ({session_progress:.1f}%)")
                    logger.info(f"Total collected so far: {len(all_products)} products")
                    logger.info("Restarting driver to avoid rate limiting...")
                    
                    # Long pause between sessions
                    logger.info("🛡️ Long pause between sessions for Cloudflare...")
                    DelayStrategy.cloudflare_safe_delay()
            
            self.total_collected = len(all_products)
            logger.info(f"Parsing completed. Total products: {self.total_collected}")
            
        except Exception as e:
            logger.error(f"Error in parse_all_pages: {e}")
        
        return all_products
    
    def parse_session(self, driver, start_page: int, end_page: int) -> List[Dict[str, Any]]:
        """Parse a session of pages."""
        session_products = []
        
        for page_num in range(start_page, end_page + 1):
            try:
                url = f"{TrastConfig.SHOP_URL}?_paged={page_num}"
                logger.info(f"Parsing page {page_num}/{end_page}")
                
                # Fetch page with retry
                success, driver, current_proxy = self.page_fetcher.fetch_with_retry(driver, url, None)
                
                if not success:
                    logger.error(f"Failed to load page {page_num} after retries")
                    continue
                
                # Extract products
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                products = self.product_extractor.extract_from_soup(soup)
                
                if products:
                    logger.info(f"Page {page_num}: found {len(products)} products")
                    session_products.extend(products)
                    self.pages_processed += 1
                else:
                    logger.warning(f"Page {page_num}: no products found")
                
                # Smart delays
                if page_num % 20 == 0:
                    logger.info("🛡️ Long pause for Cloudflare...")
                    DelayStrategy.cloudflare_safe_delay()
                else:
                    DelayStrategy.smart_delay(page_num)
                
            except Exception as e:
                logger.error(f"Error on page {page_num}: {e}")
                DelayStrategy.cloudflare_safe_delay()
        
        return session_products
    
    def coordinate_with_browser_rotation(self, browser_pool, proxy_strategy):
        """Coordinate parsing with browser and proxy rotation."""
        # This method will be implemented when integrating with browser_manager
        # and proxy_manager modules
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get parsing statistics."""
        return {
            'total_collected': self.total_collected,
            'pages_processed': self.pages_processed,
            'average_per_page': self.total_collected / self.pages_processed if self.pages_processed > 0 else 0
        }
