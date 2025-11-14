"""Proxy validation utilities"""

import time
import random
import requests
from typing import Dict, Optional, Tuple
from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import TARGET_URL, SHOP_URL, PROXY_VALIDATION_TIMEOUT, CLOUDFLARE_WAIT_TIMEOUT
from browser.driver_factory import create_driver, verify_proxy_usage
from browser.driver_manager import managed_driver
from parser.page_validator import get_total_pages, is_page_blocked, has_catalog_structure
from utils.exceptions import ProxyValidationError, ProxyConnectionError

logger = get_logger("proxy.validator")


def validate_proxy_basic(proxy: Dict, timeout: int = 10) -> Tuple[bool, Dict]:
    """
    Basic proxy validation (step 1) - check if proxy works at all
    
    Args:
        proxy: Proxy dict with 'ip', 'port', 'protocol'
        timeout: Request timeout
    
    Returns:
        Tuple of (is_working, proxy_info)
    """
    try:
        protocol = proxy.get('protocol', 'http').lower()
        ip = proxy['ip']
        port = proxy['port']
        
        logger.debug(f"Basic validation: {ip}:{port} ({protocol.upper()})")
        
        # Build proxy URL
        if protocol in ['http', 'https']:
            proxy_url = f"{protocol}://{ip}:{port}"
            proxies = {'http': proxy_url, 'https': proxy_url}
        elif protocol in ['socks4', 'socks5']:
            proxy_url = f"socks5h://{ip}:{port}" if protocol == 'socks5' else f"socks4://{ip}:{port}"
            proxies = {'http': proxy_url, 'https': proxy_url}
        else:
            logger.warning(f"Unsupported protocol: {protocol}")
            return False, {}
        
        # Test with simple service
        test_url = "https://ifconfig.me/ip"
        try:
            response = requests.get(test_url, proxies=proxies, timeout=timeout, verify=False)
            if response.status_code == 200:
                external_ip = response.text.strip()
                if external_ip and len(external_ip.split('.')) == 4:
                    logger.info(f"Proxy works! External IP: {external_ip}")
                    return True, {
                        'ip': ip,
                        'port': port,
                        'protocol': protocol,
                        'external_ip': external_ip,
                        'proxies': proxies
                    }
        except Exception as e:
            logger.debug(f"Failed to connect via {test_url}: {e}")
        
        return False, {}
        
    except Exception as e:
        logger.error(f"Error in basic validation: {e}")
        return False, {}


def validate_proxy_for_trast(proxy: Dict, timeout: int = None) -> Tuple[bool, Optional[Dict]]:
    """
    Validate proxy for Trast website access (step 2) - check if proxy can access target site
    
    Args:
        proxy: Proxy dict
        timeout: Validation timeout (defaults to config)
    
    Returns:
        Tuple of (is_valid, context_dict)
    """
    if timeout is None:
        timeout = PROXY_VALIDATION_TIMEOUT
    
    context = {
        "total_pages": None,
        "html": None,
        "source": None,
    }
    
    try:
        # First basic validation
        is_basic, proxy_info = validate_proxy_basic(proxy, timeout=10)
        if not is_basic:
            logger.debug(f"Proxy {proxy['ip']}:{proxy['port']} failed basic validation")
            return False, context
        
        # Now test with Selenium
        logger.info(f"Testing proxy {proxy['ip']}:{proxy['port']} with Selenium...")
        
        with managed_driver(proxy=proxy, verify_proxy=False) as driver:
            try:
                # Navigate to main page first
                logger.debug("Navigating to main page...")
                driver.get(TARGET_URL)
                time.sleep(random.uniform(2, 4))
                
                # Scroll
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                time.sleep(random.uniform(1, 2))
                
                # Navigate to shop
                logger.debug("Navigating to shop page...")
                driver.get(SHOP_URL)
                time.sleep(random.uniform(5, 8))
                
                # Check for Cloudflare
                page_source_lower = driver.page_source.lower()
                wait_time = 0
                max_wait = CLOUDFLARE_WAIT_TIMEOUT
                
                while ("cloudflare" in page_source_lower or 
                       "checking your browser" in page_source_lower or 
                       "just a moment" in page_source_lower) and wait_time < max_wait:
                    logger.info(f"Cloudflare check detected, waiting... ({wait_time}/{max_wait}s)")
                    time.sleep(3)
                    driver.refresh()
                    time.sleep(2)
                    page_source_lower = driver.page_source.lower()
                    wait_time += 5
                
                if wait_time >= max_wait:
                    logger.warning("Cloudflare check timeout")
                    return False, context
                
                # Analyze page
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")
                
                # Check if blocked
                block_check = is_page_blocked(soup, page_source)
                if block_check["blocked"]:
                    logger.warning(f"Page is blocked: {block_check['reason']}")
                    return False, context
                
                # Get total pages
                total_pages = get_total_pages(soup)
                
                # Check for products
                has_products = bool(soup.select("div.product.product-plate"))
                
                context["total_pages"] = total_pages
                context["html"] = page_source
                context["source"] = "selenium"
                
                if total_pages:
                    logger.info(f"Proxy validated! Total pages: {total_pages}")
                    return True, context
                
                if has_products:
                    logger.info("Proxy validated! Products found (pagination not available)")
                    return True, context
                
                logger.warning("Page has no products or pagination")
                return False, context
                
            except Exception as e:
                error_msg = str(e).lower()
                if "timeout" in error_msg or "timed out" in error_msg:
                    raise ProxyConnectionError(f"Timeout connecting to target site: {e}")
                elif "connection" in error_msg or "neterror" in error_msg:
                    raise ProxyConnectionError(f"Connection error: {e}")
                else:
                    raise ProxyValidationError(f"Validation error: {e}")
        
    except ProxyConnectionError:
        raise
    except ProxyValidationError:
        raise
    except Exception as e:
        logger.error(f"Error validating proxy: {e}")
        return False, context

