"""Driver lifecycle management with context managers"""

import threading
from contextlib import contextmanager
from typing import Optional, Dict, Any
from selenium.webdriver.remote.webdriver import WebDriver

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from browser.driver_factory import create_driver, verify_proxy_usage
from utils.exceptions import DriverCreationError, TabCrashedError

logger = get_logger("browser.driver_manager")


def is_tab_crashed_error(error: Exception) -> bool:
    """Check if error is related to tab crash"""
    error_msg = str(error).lower()
    return (
        "tab crashed" in error_msg or
        "session deleted" in error_msg or
        "target frame detached" in error_msg or
        "no such session" in error_msg
    )


@contextmanager
def managed_driver(proxy: Optional[Dict] = None, verify_proxy: bool = True):
    """
    Context manager for WebDriver lifecycle
    
    Args:
        proxy: Proxy configuration dict
        verify_proxy: Whether to verify proxy usage
    
    Yields:
        WebDriver instance
    
    Example:
        with managed_driver(proxy=my_proxy) as driver:
            driver.get("https://example.com")
    """
    driver = None
    try:
        driver = create_driver(proxy=proxy)
        
        # Store proxy info in driver for later use
        if proxy:
            driver.proxy_info = {
                'ip': proxy.get('ip'),
                'port': proxy.get('port'),
                'protocol': proxy.get('protocol', 'http'),
                'country': proxy.get('country', 'Unknown')
            }
        
        # Verify proxy if requested
        if verify_proxy and proxy:
            try:
                verify_proxy_usage(driver, proxy)
            except Exception as e:
                logger.warning(f"Proxy verification failed: {e}, continuing anyway")
        
        yield driver
        
    except DriverCreationError as e:
        logger.error(f"Failed to create driver: {e}")
        raise
    except Exception as e:
        if is_tab_crashed_error(e):
            raise TabCrashedError(f"Browser tab crashed: {e}") from e
        raise
    finally:
        if driver:
            try:
                driver.quit()
                logger.debug("Driver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")


class DriverPool:
    """Thread-safe pool of drivers"""
    
    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self.drivers = []
        self.lock = threading.Lock()
        self.proxies = {}  # Map driver id to proxy
    
    def get_driver(self, proxy: Optional[Dict] = None) -> Optional[WebDriver]:
        """
        Get a driver from pool or create new one
        
        Args:
            proxy: Proxy configuration dict
        
        Returns:
            WebDriver instance or None if pool is full
        """
        with self.lock:
            # Try to reuse existing driver with same proxy
            if proxy:
                proxy_key = f"{proxy.get('ip')}:{proxy.get('port')}"
                for driver in self.drivers:
                    if hasattr(driver, 'proxy_info'):
                        driver_proxy_key = f"{driver.proxy_info.get('ip')}:{driver.proxy_info.get('port')}"
                        if driver_proxy_key == proxy_key:
                            try:
                                # Test if driver is still alive
                                driver.current_url
                                logger.debug("Reusing driver from pool")
                                return driver
                            except:
                                # Driver is dead, remove it
                                self.drivers.remove(driver)
                                if id(driver) in self.proxies:
                                    del self.proxies[id(driver)]
            
            # Create new driver if pool not full
            if len(self.drivers) < self.max_size:
                try:
                    driver = create_driver(proxy=proxy)
                    if proxy:
                        driver.proxy_info = {
                            'ip': proxy.get('ip'),
                            'port': proxy.get('port'),
                            'protocol': proxy.get('protocol', 'http'),
                            'country': proxy.get('country', 'Unknown')
                        }
                    self.drivers.append(driver)
                    if proxy:
                        self.proxies[id(driver)] = proxy
                    logger.debug(f"Created new driver (pool size: {len(self.drivers)})")
                    return driver
                except Exception as e:
                    logger.error(f"Failed to create driver for pool: {e}")
                    return None
            
            logger.warning("Driver pool is full")
            return None
    
    def remove_driver(self, driver: WebDriver):
        """Remove driver from pool and close it"""
        with self.lock:
            if driver in self.drivers:
                self.drivers.remove(driver)
                if id(driver) in self.proxies:
                    del self.proxies[id(driver)]
                try:
                    driver.quit()
                except:
                    pass
                logger.debug(f"Removed driver from pool (pool size: {len(self.drivers)})")
    
    def close_all(self):
        """Close all drivers in pool"""
        with self.lock:
            for driver in self.drivers:
                try:
                    driver.quit()
                except:
                    pass
            self.drivers.clear()
            self.proxies.clear()
            logger.info("All drivers in pool closed")
    
    def __len__(self):
        return len(self.drivers)

