"""Factory for creating browser drivers"""

import random
import time
from typing import Optional, Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
import geckodriver_autoinstaller

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import (
    HEADLESS, CHROME_PREFERRED, PAGE_LOAD_TIMEOUT,
    VPS_EXTERNAL_IP, IP_CHECK_SERVICES
)
from browser.stealth import (
    apply_chrome_stealth, apply_firefox_stealth,
    get_random_user_agent, get_random_window_size
)
from utils.exceptions import DriverCreationError

logger = get_logger("browser.driver_factory")


def create_chrome_driver(proxy: Optional[Dict] = None) -> webdriver.Chrome:
    """
    Create Chrome driver with proxy support
    
    Args:
        proxy: Proxy configuration dict with 'ip', 'port', 'protocol'
    
    Returns:
        Chrome WebDriver instance
    
    Raises:
        DriverCreationError: If driver creation fails
    """
    try:
        driver_path = ChromeDriverManager().install()
        logger.debug(f"ChromeDriver path: {driver_path}")
    except Exception as e:
        raise DriverCreationError(f"Failed to install ChromeDriver: {e}")
    
    options = ChromeOptions()
    
    # Basic options
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # User-Agent
    user_agent = get_random_user_agent()
    options.add_argument(f"--user-agent={user_agent}")
    logger.debug(f"Chrome User-Agent: {user_agent}")
    
    # Proxy configuration
    if proxy:
        protocol = proxy.get('protocol', 'http').lower()
        ip = proxy['ip']
        port = proxy['port']
        
        if protocol in ['http', 'https']:
            proxy_arg = f"{protocol}://{ip}:{port}"
            options.add_argument(f"--proxy-server={proxy_arg}")
            logger.debug(f"Chrome proxy configured: {proxy_arg}")
        elif protocol in ['socks4', 'socks5']:
            raise DriverCreationError(
                f"Chrome does not support {protocol.upper()} proxies directly. Use Firefox."
            )
        else:
            # Fallback to HTTP
            proxy_arg = f"http://{ip}:{port}"
            options.add_argument(f"--proxy-server={proxy_arg}")
            logger.debug(f"Chrome proxy configured (fallback to HTTP): {proxy_arg}")
    
    # Create driver
    try:
        service = ChromeService(driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set timeouts
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        
        # Apply stealth
        apply_chrome_stealth(driver)
        
        # Set random window size
        width, height = get_random_window_size()
        driver.set_window_size(width, height)
        
        # Random delay
        time.sleep(random.uniform(0.5, 1.5))
        
        logger.info("Chrome driver created successfully")
        return driver
        
    except Exception as e:
        raise DriverCreationError(f"Failed to create Chrome driver: {e}")


def create_firefox_driver(proxy: Optional[Dict] = None) -> webdriver.Firefox:
    """
    Create Firefox driver with proxy support
    
    Args:
        proxy: Proxy configuration dict with 'ip', 'port', 'protocol'
    
    Returns:
        Firefox WebDriver instance
    
    Raises:
        DriverCreationError: If driver creation fails
    """
    try:
        geckodriver_autoinstaller.install()
    except Exception as e:
        logger.warning(f"Failed to auto-install geckodriver: {e}")
    
    options = FirefoxOptions()
    
    # Basic options
    if HEADLESS:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # DNS settings (only if no proxy)
    if not proxy:
        options.set_preference("network.dns.disablePrefetch", True)
        options.set_preference("network.dns.disablePrefetchFromHTTPS", True)
        options.set_preference("network.dns.defaultIPv4", "8.8.8.8")
        options.set_preference("network.dns.defaultIPv6", "2001:4860:4860::8888")
    
    # Anti-detection
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.set_preference("marionette.logging", "FATAL")
    
    # User-Agent
    user_agent = get_random_user_agent()
    options.set_preference("general.useragent.override", user_agent)
    logger.debug(f"Firefox User-Agent: {user_agent}")
    
    # Platform
    platforms = ["Win32", "MacIntel", "Linux x86_64"]
    options.set_preference("general.platform.override", random.choice(platforms))
    
    # WebRTC disabled
    options.set_preference("media.peerconnection.enabled", False)
    options.set_preference("media.navigator.enabled", False)
    
    # Timeouts for slow proxies
    options.set_preference("network.http.connection-timeout", 60)
    options.set_preference("network.http.response.timeout", 60)
    options.set_preference("network.http.keep-alive.timeout", 60)
    options.set_preference("network.http.request.timeout", 60)
    options.set_preference("network.dns.timeout", 30)
    
    # Tracking protection
    options.set_preference("privacy.trackingprotection.enabled", True)
    options.set_preference("privacy.trackingprotection.pbmode.enabled", True)
    options.set_preference("browser.safebrowsing.enabled", False)
    options.set_preference("toolkit.telemetry.enabled", False)
    
    # SSL/TLS settings
    options.set_preference("security.tls.insecure_fallback_hosts", "trast-zapchast.ru")
    options.set_preference("security.tls.unrestricted_rc4_fallback", True)
    options.set_preference("security.cert_pinning.enforcement_level", 0)
    
    # Proxy configuration
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
            logger.debug(f"Firefox HTTP/HTTPS proxy configured: {ip}:{port}")
        elif protocol in ['socks4', 'socks5']:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", ip)
            options.set_preference("network.proxy.socks_port", int(port))
            if protocol == 'socks5':
                options.set_preference("network.proxy.socks_version", 5)
            else:
                options.set_preference("network.proxy.socks_version", 4)
            options.set_preference("network.proxy.socks_remote_dns", True)
            logger.debug(f"Firefox {protocol.upper()} proxy configured: {ip}:{port}")
    
    # Create driver
    try:
        service = FirefoxService()
        driver = webdriver.Firefox(service=service, options=options)
        
        # Set timeouts
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        
        # Apply stealth
        apply_firefox_stealth(driver)
        
        # Set random window size
        width, height = get_random_window_size()
        driver.set_window_size(width, height)
        
        # Random delay
        time.sleep(random.uniform(0.5, 1.5))
        
        logger.info("Firefox driver created successfully")
        return driver
        
    except Exception as e:
        raise DriverCreationError(f"Failed to create Firefox driver: {e}")


def create_driver(proxy: Optional[Dict] = None, prefer_chrome: bool = None) -> webdriver.Remote:
    """
    Create a browser driver (Chrome or Firefox) with proxy support
    
    Automatically chooses the appropriate browser based on proxy protocol:
    - Chrome: HTTP/HTTPS only
    - Firefox: All protocols (HTTP/HTTPS/SOCKS4/SOCKS5)
    
    Args:
        proxy: Proxy configuration dict
        prefer_chrome: Whether to prefer Chrome (defaults to config value)
    
    Returns:
        WebDriver instance (Chrome or Firefox)
    
    Raises:
        DriverCreationError: If driver creation fails
    """
    if prefer_chrome is None:
        prefer_chrome = CHROME_PREFERRED
    
    # Determine browser based on proxy protocol
    use_chrome = prefer_chrome
    if proxy:
        protocol = proxy.get('protocol', 'http').lower()
        if protocol in ['socks4', 'socks5']:
            use_chrome = False
            logger.info(f"SOCKS proxy detected, using Firefox")
    
    # Try Chrome first if applicable
    if use_chrome:
        try:
            return create_chrome_driver(proxy)
        except DriverCreationError as e:
            if "SOCKS" in str(e):
                logger.info(f"Chrome doesn't support this proxy type, falling back to Firefox")
                return create_firefox_driver(proxy)
            else:
                logger.warning(f"Chrome driver creation failed: {e}, trying Firefox...")
                try:
                    return create_firefox_driver(proxy)
                except DriverCreationError:
                    raise e
    
    # Use Firefox
    return create_firefox_driver(proxy)


def verify_proxy_usage(driver: webdriver.Remote, proxy: Dict, vps_ip: str = None) -> bool:
    """
    Verify that proxy is actually being used by checking external IP
    
    Args:
        driver: WebDriver instance
        proxy: Proxy configuration dict
        vps_ip: VPS external IP for comparison (defaults to config value)
    
    Returns:
        True if proxy is being used, False otherwise
    """
    if not proxy:
        return False
    
    if vps_ip is None:
        vps_ip = VPS_EXTERNAL_IP
    
    import re
    ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
    
    # Save original timeout
    original_timeout = None
    try:
        original_timeout = driver.timeouts.page_load
    except:
        pass
    
    # Try to get IP from check services
    detected_ip = None
    for service_url in IP_CHECK_SERVICES:
        try:
            # Set shorter timeout for IP check
            try:
                driver.set_page_load_timeout(10)
            except:
                pass
            
            driver.get(service_url)
            time.sleep(2)
            
            page_text = driver.page_source.strip()
            
            # Check for error pages
            if "ERR_" in page_text or "can't be reached" in page_text:
                continue
            
            # Extract IP
            ip_matches = re.findall(ip_pattern, page_text)
            if ip_matches:
                candidate_ip = ip_matches[0]
                # Validate IP format
                parts = candidate_ip.split('.')
                if len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts if p.isdigit()):
                    detected_ip = candidate_ip
                    logger.debug(f"Detected IP via {service_url}: {detected_ip}")
                    break
        except Exception as e:
            logger.debug(f"Failed to check IP via {service_url}: {e}")
            continue
    
    # Restore timeout
    if original_timeout is not None:
        try:
            driver.set_page_load_timeout(original_timeout)
        except:
            try:
                driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            except:
                pass
    
    if not detected_ip:
        logger.warning("Could not verify proxy usage (could not get external IP)")
        return False
    
    # Check if IP differs from VPS IP
    if detected_ip == vps_ip:
        logger.error(f"Proxy NOT being used! Detected IP ({detected_ip}) matches VPS IP")
        return False
    
    logger.info(f"Proxy verified: detected IP {detected_ip} differs from VPS IP {vps_ip}")
    return True

