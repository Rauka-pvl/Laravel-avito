"""Enhanced driver lifecycle management with improved tab crash handling for Trast Parser V3"""

import threading
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any
from selenium.webdriver.remote.webdriver import WebDriver

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from browser.driver_factory import create_driver, verify_proxy_usage
from utils.exceptions import DriverCreationError, TabCrashedError, DriverHealthCheckFailed
from utils.health_check import health_checker
from metrics.collector import metrics

logger = get_logger("browser.driver_manager")


def is_tab_crashed_error(error: Exception) -> bool:
    """
    Enhanced check if error is related to tab crash
    
    Checks for multiple indicators of tab crashes
    """
    error_msg = str(error).lower()
    error_type = type(error).__name__
    
    # Direct tab crash indicators
    tab_crash_indicators = [
        "tab crashed",
        "session deleted",
        "target frame detached",
        "no such session",
        "session not created",
        "chrome not reachable",
        "connection refused",
        "target closed",
        "invalid session id",
        "session id is null"
    ]
    
    # Check message
    if any(indicator in error_msg for indicator in tab_crash_indicators):
        return True
    
    # Check exception type
    if "SessionNotCreatedException" in error_type or \
       "InvalidSessionIdException" in error_type or \
       "WebDriverException" in error_type:
        # Additional check for specific error messages
        if any(indicator in error_msg for indicator in ["session", "crashed", "detached"]):
            return True
    
    return False


@contextmanager
def managed_driver(proxy: Optional[Dict] = None, verify_proxy: bool = True, driver_id: str = None):
    """
    Enhanced context manager for WebDriver lifecycle with health checks
    
    Args:
        proxy: Proxy configuration dict
        verify_proxy: Whether to verify proxy usage
        driver_id: Unique identifier for driver (for health checks)
    
    Yields:
        WebDriver instance
    
    Example:
        with managed_driver(proxy=my_proxy) as driver:
            driver.get("https://example.com")
    """
    driver = None
    driver_id = driver_id or f"driver_{id(proxy) if proxy else 'no_proxy'}"
    
    try:
        driver = create_driver(proxy=proxy)
        metrics.record_driver_creation()
        
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
        
        # Health check
        if health_checker.check_driver_health(driver, driver_id):
            logger.debug(f"Driver {driver_id} health check passed")
        else:
            logger.warning(f"Driver {driver_id} health check failed")
        
        yield driver
        
    except DriverCreationError as e:
        logger.error(f"Failed to create driver: {e}")
        raise
    except Exception as e:
        if is_tab_crashed_error(e):
            metrics.record_driver_crash()
            logger.error(f"Tab crashed during driver operation: {e}")
            raise TabCrashedError(f"Browser tab crashed: {e}") from e
        raise
    finally:
        if driver:
            try:
                # Mark as unhealthy before closing
                health_checker.mark_unhealthy(driver_id)
                driver.quit()
                logger.debug(f"Driver {driver_id} closed successfully")
            except Exception as e:
                logger.warning(f"Error closing driver {driver_id}: {e}")


def recreate_driver_after_crash(
    old_driver: Optional[WebDriver],
    proxy: Optional[Dict] = None,
    driver_id: str = None
) -> Optional[WebDriver]:
    """
    Recreate driver after tab crash with enhanced error handling
    
    Args:
        old_driver: Old driver instance (will be closed)
        proxy: Proxy configuration dict
        driver_id: Unique identifier for driver
    
    Returns:
        New WebDriver instance or None if creation failed
    """
    driver_id = driver_id or f"driver_{id(proxy) if proxy else 'no_proxy'}"
    
    # Close old driver
    if old_driver:
        try:
            old_driver.quit()
        except Exception as e:
            logger.debug(f"Error closing old driver: {e}")
    
    # Wait a bit before recreating
    time.sleep(1)
    
    # Create new driver
    try:
        new_driver = create_driver(proxy=proxy)
        metrics.record_driver_recreation()
        
        # Store proxy info
        if proxy:
            new_driver.proxy_info = {
                'ip': proxy.get('ip'),
                'port': proxy.get('port'),
                'protocol': proxy.get('protocol', 'http'),
                'country': proxy.get('country', 'Unknown')
            }
        
        # Health check
        if health_checker.check_driver_health(new_driver, driver_id):
            logger.info(f"Driver {driver_id} recreated successfully after crash")
            return new_driver
        else:
            logger.warning(f"Driver {driver_id} recreated but health check failed")
            # Still return it, might work
            return new_driver
            
    except Exception as e:
        logger.error(f"Failed to recreate driver {driver_id}: {e}")
        metrics.record_driver_crash()
        return None


class DriverPool:
    """Thread-safe pool of drivers with health checks"""
    
    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self.drivers = []
        self.driver_ids = {}  # Map driver to ID
        self.lock = threading.Lock()
        self.proxies = {}  # Map driver id to proxy
    
    def get_driver(self, proxy: Optional[Dict] = None, driver_id: str = None) -> Optional[WebDriver]:
        """
        Get a driver from pool or create new one with health check
        
        Args:
            proxy: Proxy configuration dict
            driver_id: Unique identifier for driver
        
        Returns:
            WebDriver instance or None if pool is full
        """
        driver_id = driver_id or f"driver_{id(proxy) if proxy else 'no_proxy'}"
        
        with self.lock:
            # Try to reuse existing driver with same proxy
            if proxy:
                proxy_key = f"{proxy.get('ip')}:{proxy.get('port')}"
                for driver in self.drivers:
                    if hasattr(driver, 'proxy_info'):
                        driver_proxy_key = f"{driver.proxy_info.get('ip')}:{driver.proxy_info.get('port')}"
                        if driver_proxy_key == proxy_key:
                            try:
                                # Health check
                                if health_checker.should_check(driver_id):
                                    if not health_checker.check_driver_health(driver, driver_id):
                                        logger.warning(f"Driver {driver_id} failed health check, removing from pool")
                                        self.remove_driver(driver)
                                        break
                                
                                # Test if driver is still alive
                                driver.current_url
                                logger.debug(f"Reusing driver {driver_id} from pool")
                                return driver
                            except Exception as e:
                                # Driver is dead, remove it
                                logger.warning(f"Driver {driver_id} is dead: {e}, removing from pool")
                                self.remove_driver(driver)
                                break
            
            # Create new driver if pool not full
            if len(self.drivers) < self.max_size:
                try:
                    driver = create_driver(proxy=proxy)
                    metrics.record_driver_creation()
                    
                    if proxy:
                        driver.proxy_info = {
                            'ip': proxy.get('ip'),
                            'port': proxy.get('port'),
                            'protocol': proxy.get('protocol', 'http'),
                            'country': proxy.get('country', 'Unknown')
                        }
                    
                    self.drivers.append(driver)
                    self.driver_ids[driver] = driver_id
                    if proxy:
                        self.proxies[driver_id] = proxy
                    
                    # Health check
                    health_checker.check_driver_health(driver, driver_id)
                    
                    logger.debug(f"Created new driver {driver_id} (pool size: {len(self.drivers)})")
                    return driver
                except Exception as e:
                    logger.error(f"Failed to create driver {driver_id} for pool: {e}")
                    return None
            
            logger.warning(f"Driver pool is full (max: {self.max_size})")
            return None
    
    def remove_driver(self, driver: WebDriver):
        """Remove driver from pool and close it"""
        with self.lock:
            if driver in self.drivers:
                self.drivers.remove(driver)
                driver_id = self.driver_ids.pop(driver, None)
                if driver_id:
                    health_checker.mark_unhealthy(driver_id)
                if driver_id in self.proxies:
                    del self.proxies[driver_id]
                try:
                    driver.quit()
                except:
                    pass
                logger.debug(f"Removed driver from pool (pool size: {len(self.drivers)})")
    
    def close_all(self):
        """Close all drivers in pool"""
        with self.lock:
            for driver in self.drivers:
                driver_id = self.driver_ids.get(driver)
                if driver_id:
                    health_checker.mark_unhealthy(driver_id)
                try:
                    driver.quit()
                except:
                    pass
            self.drivers.clear()
            self.driver_ids.clear()
            self.proxies.clear()
            logger.info("All drivers in pool closed")
    
    def __len__(self):
        return len(self.drivers)
