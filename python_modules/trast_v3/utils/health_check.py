"""Health check utilities for drivers and proxies"""

import time
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from selenium.webdriver.remote.webdriver import WebDriver

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import (
    HEALTH_CHECK_TIMEOUT,
    HEALTH_CHECK_INTERVAL,
    DRIVER_HEALTH_CHECK_ENABLED,
    PROXY_HEALTH_CHECK_ENABLED,
    IP_CHECK_SERVICES,
    VPS_EXTERNAL_IP
)
from utils.exceptions import DriverHealthCheckFailed

logger = get_logger("utils.health_check")


class HealthChecker:
    """Health checker for drivers and proxies"""
    
    def __init__(self):
        self.last_check_time: Dict[str, datetime] = {}
        self.health_status: Dict[str, bool] = {}
        self.lock = threading.Lock()
    
    def check_driver_health(
        self,
        driver: WebDriver,
        driver_id: str = "default"
    ) -> bool:
        """
        Check if driver is healthy
        
        Args:
            driver: WebDriver instance
            driver_id: Unique identifier for driver
        
        Returns:
            True if healthy, False otherwise
        """
        if not DRIVER_HEALTH_CHECK_ENABLED:
            return True
        
        try:
            # Check if driver is still responsive
            current_url = driver.current_url
            page_title = driver.title
            
            # Try to execute a simple command
            driver.execute_script("return document.readyState;")
            
            with self.lock:
                self.health_status[f"driver_{driver_id}"] = True
                self.last_check_time[f"driver_{driver_id}"] = datetime.now()
            
            return True
            
        except Exception as e:
            logger.warning(f"Driver health check failed for {driver_id}: {e}")
            with self.lock:
                self.health_status[f"driver_{driver_id}"] = False
                self.last_check_time[f"driver_{driver_id}"] = datetime.now()
            return False
    
    def check_proxy_health(
        self,
        driver: WebDriver,
        proxy: Dict,
        proxy_id: str = None
    ) -> bool:
        """
        Check if proxy is working correctly
        
        Args:
            driver: WebDriver instance using proxy
            proxy: Proxy configuration dict
            proxy_id: Unique identifier for proxy
        
        Returns:
            True if healthy, False otherwise
        """
        if not PROXY_HEALTH_CHECK_ENABLED:
            return True
        
        if proxy_id is None:
            proxy_id = f"{proxy.get('ip')}:{proxy.get('port')}"
        
        try:
            # Try to get external IP
            original_timeout = None
            try:
                original_timeout = driver.timeouts.page_load
            except:
                pass
            
            # Set shorter timeout for health check
            try:
                driver.set_page_load_timeout(HEALTH_CHECK_TIMEOUT)
            except:
                pass
            
            # Try to access IP check service
            for service_url in IP_CHECK_SERVICES:
                try:
                    driver.get(service_url)
                    time.sleep(1)
                    
                    page_text = driver.page_source.strip()
                    
                    # Check if we got an IP
                    import re
                    ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
                    ip_matches = re.findall(ip_pattern, page_text)
                    
                    if ip_matches:
                        detected_ip = ip_matches[0]
                        # Check if IP differs from VPS IP (proxy is working)
                        if detected_ip != VPS_EXTERNAL_IP:
                            with self.lock:
                                self.health_status[f"proxy_{proxy_id}"] = True
                                self.last_check_time[f"proxy_{proxy_id}"] = datetime.now()
                            
                            # Restore timeout
                            if original_timeout:
                                try:
                                    driver.set_page_load_timeout(original_timeout)
                                except:
                                    pass
                            
                            return True
                    
                except Exception as e:
                    logger.debug(f"Health check failed for {service_url}: {e}")
                    continue
            
            # Restore timeout
            if original_timeout:
                try:
                    driver.set_page_load_timeout(original_timeout)
                except:
                    pass
            
            # Health check failed
            with self.lock:
                self.health_status[f"proxy_{proxy_id}"] = False
                self.last_check_time[f"proxy_{proxy_id}"] = datetime.now()
            
            return False
            
        except Exception as e:
            logger.warning(f"Proxy health check failed for {proxy_id}: {e}")
            with self.lock:
                self.health_status[f"proxy_{proxy_id}"] = False
                self.last_check_time[f"proxy_{proxy_id}"] = datetime.now()
            return False
    
    def should_check(self, resource_id: str) -> bool:
        """
        Check if health check should be performed
        
        Args:
            resource_id: Resource identifier
        
        Returns:
            True if check should be performed
        """
        with self.lock:
            last_check = self.last_check_time.get(resource_id)
            if not last_check:
                return True
            
            elapsed = (datetime.now() - last_check).total_seconds()
            return elapsed >= HEALTH_CHECK_INTERVAL
    
    def get_health_status(self, resource_id: str) -> Optional[bool]:
        """
        Get health status for resource
        
        Args:
            resource_id: Resource identifier
        
        Returns:
            Health status or None if unknown
        """
        with self.lock:
            return self.health_status.get(resource_id)
    
    def mark_unhealthy(self, resource_id: str):
        """Mark resource as unhealthy"""
        with self.lock:
            self.health_status[resource_id] = False
            self.last_check_time[resource_id] = datetime.now()
    
    def mark_healthy(self, resource_id: str):
        """Mark resource as healthy"""
        with self.lock:
            self.health_status[resource_id] = True
            self.last_check_time[resource_id] = datetime.now()


# Global health checker instance
health_checker = HealthChecker()

