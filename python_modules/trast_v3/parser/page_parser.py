"""Enhanced page parsing with partial page handling and retry logic for Trast Parser V3"""

import time
import random
from typing import Dict, Optional, Tuple
from bs4 import BeautifulSoup
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import (
    SHOP_PAGE_URL, CLOUDFLARE_WAIT_TIMEOUT, MIN_PAGE_DELAY, MAX_PAGE_DELAY,
    PARTIAL_PAGE_RETRY_TIMEOUT, PARTIAL_PAGE_RETRIES, TIMEOUT_RETRIES
)
from parser.page_validator import (
    is_page_blocked, get_page_status, is_catalog_page_loaded, get_total_pages
)
from parser.product_extractor import extract_products
from browser.driver_manager import is_tab_crashed_error
from utils.exceptions import (
    PageLoadError, PageBlockedError, TabCrashedError, PagePartialLoadError
)
from utils.retry import retry_timeout
from metrics.collector import metrics

logger = get_logger("parser.page_parser")


def reload_page_if_needed(
    driver: WebDriver,
    page_url: str,
    max_retries: int = PARTIAL_PAGE_RETRIES
) -> Tuple[BeautifulSoup, int]:
    """
    Reload page if needed (for partial loads)
    
    Enhanced version from old parser with better error handling
    
    Args:
        driver: WebDriver instance
        page_url: URL of page to reload
        max_retries: Maximum retry attempts
    
    Returns:
        Tuple of (BeautifulSoup object, products_count)
    
    Raises:
        TabCrashedError: If tab crashes
        PageLoadError: If page fails to load after retries
    """
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.info(f"Reloading page {page_url} (attempt {attempt + 1}/{max_retries + 1})...")
                time.sleep(random.uniform(1, 2))
            
            # Load page
            driver.get(page_url)
            time.sleep(random.uniform(3, 6))
            
            # Wait for page to load
            try:
                wait = WebDriverWait(driver, 15)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except TimeoutException:
                logger.warning(f"Timeout waiting for page {page_url} to load")
            
            # Parse page
            soup = BeautifulSoup(driver.page_source, "html.parser")
            products = extract_products(soup)
            
            return soup, len(products)
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for tab crash
            if is_tab_crashed_error(e):
                logger.error(f"Tab crashed while reloading page {page_url} (attempt {attempt + 1}): {e}")
                raise TabCrashedError(f"Browser tab crashed: {e}") from e
            
            # Check for proxy errors
            is_proxy_error = (
                "proxyconnectfailure" in error_msg or
                ("proxy" in error_msg and ("refusing" in error_msg or "connection" in error_msg or "failed" in error_msg)) or
                ("neterror" in error_msg and "proxy" in error_msg)
            )
            
            if is_proxy_error:
                logger.warning(f"Proxy error while reloading page {page_url} (attempt {attempt + 1})")
                if attempt < max_retries:
                    continue
                else:
                    # Return empty result for proxy error
                    return BeautifulSoup("", "html.parser"), 0
            
            logger.warning(f"Error reloading page {page_url} (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                continue
            else:
                # Return empty result after all retries
                return BeautifulSoup("", "html.parser"), 0
    
    # Should never reach here
    return BeautifulSoup("", "html.parser"), 0


def load_page(
    driver: WebDriver,
    page_num: int,
    max_retries: int = TIMEOUT_RETRIES
) -> Tuple[BeautifulSoup, int]:
    """
    Load and parse a catalog page with enhanced error handling
    
    Args:
        driver: WebDriver instance
        page_num: Page number to load
        max_retries: Maximum retry attempts
    
    Returns:
        Tuple of (BeautifulSoup object, products_count)
    
    Raises:
        PageLoadError: If page fails to load
        PageBlockedError: If page is blocked
        TabCrashedError: If browser tab crashed
    """
    page_url = SHOP_PAGE_URL.format(page=page_num)
    page_load_start = time.time()
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.info(f"Retrying page {page_num} (attempt {attempt + 1}/{max_retries + 1})...")
                time.sleep(random.uniform(1, 2))
            
            # Load page
            driver.get(page_url)
            time.sleep(random.uniform(MIN_PAGE_DELAY, MAX_PAGE_DELAY))
            
            # Wait for page to load
            try:
                wait = WebDriverWait(driver, 15)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except TimeoutException:
                logger.warning(f"Timeout waiting for page {page_num} to load")
                if attempt < max_retries:
                    continue
                else:
                    raise PageLoadError(f"Timeout loading page {page_num}")
            
            # Check for Cloudflare
            page_source_lower = driver.page_source.lower()
            wait_time = 0
            max_wait = CLOUDFLARE_WAIT_TIMEOUT
            
            while ("cloudflare" in page_source_lower or 
                   "checking your browser" in page_source_lower or 
                   "just a moment" in page_source_lower) and wait_time < max_wait:
                logger.info(f"Cloudflare check detected on page {page_num}, waiting... ({wait_time}/{max_wait}s)")
                time.sleep(3)
                driver.refresh()
                time.sleep(2)
                page_source_lower = driver.page_source.lower()
                wait_time += 5
            
            if wait_time >= max_wait:
                logger.warning(f"Cloudflare check timeout for page {page_num}")
            
            # Parse page
            soup = BeautifulSoup(driver.page_source, "html.parser")
            products = extract_products(soup)
            
            # Record metrics
            page_load_time = time.time() - page_load_start
            metrics.record_page_load_time(page_load_time)
            
            return soup, len(products)
            
        except TimeoutException as e:
            if attempt < max_retries:
                logger.warning(f"Timeout loading page {page_num} (attempt {attempt + 1}), retrying...")
                continue
            else:
                raise PageLoadError(f"Timeout loading page {page_num} after {max_retries + 1} attempts: {e}")
        
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for tab crash
            if is_tab_crashed_error(e):
                logger.error(f"Tab crashed while loading page {page_num}")
                raise TabCrashedError(f"Browser tab crashed: {e}") from e
            
            # Check for proxy errors
            is_proxy_error = (
                "proxyconnectfailure" in error_msg or
                ("proxy" in error_msg and ("refusing" in error_msg or "connection" in error_msg or "failed" in error_msg)) or
                ("neterror" in error_msg and "proxy" in error_msg)
            )
            
            if is_proxy_error:
                logger.warning(f"Proxy error on page {page_num}: {e}")
                if attempt < max_retries:
                    continue
                else:
                    raise PageLoadError(f"Proxy error after {max_retries + 1} attempts: {e}")
            
            # Other errors
            if attempt < max_retries:
                logger.warning(f"Error loading page {page_num} (attempt {attempt + 1}): {e}")
                continue
            else:
                raise PageLoadError(f"Failed to load page {page_num} after {max_retries + 1} attempts: {e}")
    
    # Should never reach here
    raise PageLoadError(f"Failed to load page {page_num}")


def parse_page(driver: WebDriver, page_num: int) -> Dict:
    """
    Parse a catalog page and return results with enhanced partial page handling
    
    Args:
        driver: WebDriver instance
        page_num: Page number to parse
    
    Returns:
        Dict with keys: 'products', 'status', 'total_pages', 'soup', 'products_count'
    """
    try:
        soup, products_count = load_page(driver, page_num)
        
        # Check page status
        page_status = get_page_status(soup, driver.page_source, products_count)
        
        # Handle partial pages - retry if needed
        if page_status["status"] == "partial":
            logger.warning(f"Page {page_num} partially loaded ({page_status['reason']}), attempting reload...")
            
            try:
                page_url = SHOP_PAGE_URL.format(page=page_num)
                soup, products_count = reload_page_if_needed(driver, page_url, max_retries=PARTIAL_PAGE_RETRIES)
                
                # Re-check status after reload
                page_status = get_page_status(soup, driver.page_source, products_count)
                
                if page_status["status"] == "partial":
                    logger.warning(f"Page {page_num} still partial after reload")
                    metrics.record_page_status("partial")
                elif page_status["status"] == "normal":
                    logger.info(f"Page {page_num} loaded successfully after reload")
                    metrics.record_page_status("normal")
                    
            except TabCrashedError:
                raise
            except Exception as e:
                logger.error(f"Error reloading partial page {page_num}: {e}")
                page_status = {"status": "error", "reason": str(e)}
        
        # Extract products
        products = extract_products(soup) if page_status["status"] == "normal" else []
        
        # Get total pages (if available)
        total_pages = get_total_pages(soup)
        
        # Record metrics
        if page_status["status"] == "normal":
            metrics.record_page_parsed(success=True)
            metrics.record_products(len(products))
        else:
            metrics.record_page_parsed(success=False)
            metrics.record_page_status(page_status["status"])
        
        return {
            "products": products,
            "status": page_status["status"],
            "reason": page_status["reason"],
            "total_pages": total_pages,
            "soup": soup,
            "products_count": len(products)
        }
        
    except TabCrashedError:
        raise
    except PageBlockedError as e:
        logger.warning(f"Page {page_num} is blocked: {e}")
        metrics.record_page_status("blocked")
        metrics.record_error("PageBlockedError")
        return {
            "products": [],
            "status": "blocked",
            "reason": str(e),
            "total_pages": None,
            "soup": None,
            "products_count": 0
        }
    except Exception as e:
        logger.error(f"Error parsing page {page_num}: {e}")
        metrics.record_page_parsed(success=False)
        metrics.record_error(type(e).__name__)
        return {
            "products": [],
            "status": "error",
            "reason": str(e),
            "total_pages": None,
            "soup": None,
            "products_count": 0
        }


def get_pages_count(driver: WebDriver) -> Optional[int]:
    """
    Get total number of pages from first page
    
    Args:
        driver: WebDriver instance
    
    Returns:
        Total pages count or None if not found
    """
    try:
        soup, _ = load_page(driver, 1)
        total_pages = get_total_pages(soup)
        if total_pages:
            logger.info(f"Found {total_pages} total pages")
        return total_pages
    except Exception as e:
        logger.error(f"Error getting pages count: {e}")
        return None

