"""
Browser management module for Trast parser.

Handles Firefox browser creation, session management, and anti-detection measures.
"""

import os
import platform
import logging
import random
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Import browser-specific modules
try:
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    FIREFOX_AVAILABLE = True
except ImportError:
    FIREFOX_AVAILABLE = False

try:
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    CHROME_AVAILABLE = True
except ImportError:
    CHROME_AVAILABLE = False

from .config import TrastConfig
from .proxy_manager import Proxy

logger = logging.getLogger("trast.browser_manager")


class BrowserFactory:
    """Factory for creating configured browser instances (Firefox on Linux, Chrome on Windows)."""
    
    @staticmethod
    def create_stealth_browser(proxy: Optional[Proxy] = None, 
                             proxy_config: Optional[Dict] = None,
                             headless: bool = True) -> Optional[webdriver.Remote]:
        """Create stealth browser with anti-detection measures."""
        try:
            # Determine best browser for current OS
            browser_type = BrowserFactory._get_best_browser()
            logger.info(f"🔍 Selected browser: {browser_type}")
            
            if browser_type == "firefox":
                return BrowserFactory._create_firefox_browser(proxy, proxy_config, headless)
            elif browser_type == "chrome":
                return BrowserFactory._create_chrome_browser(proxy, proxy_config, headless)
            else:
                logger.error("❌ No suitable browser available")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error creating browser: {e}")
            return None
    
    @staticmethod
    def _get_best_browser() -> str:
        """Determine the best browser for current OS."""
        system = platform.system().lower()
        
        # Check if Firefox is actually available (not just importable)
        firefox_available = BrowserFactory._check_firefox_availability()
        chrome_available = BrowserFactory._check_chrome_availability()
        
        # Linux: prefer Firefox (better Tor/WARP compatibility)
        if system == "linux":
            if firefox_available:
                return "firefox"
            elif chrome_available:
                return "chrome"
        
        # Windows: prefer Chrome (more stable on Windows)
        elif system == "windows":
            if chrome_available:
                return "chrome"
            elif firefox_available:
                return "firefox"
        
        # macOS: prefer Firefox
        elif system == "darwin":
            if firefox_available:
                return "firefox"
            elif chrome_available:
                return "chrome"
        
        # Fallback
        if chrome_available:
            return "chrome"
        elif firefox_available:
            return "firefox"
        
        return "none"
    
    @staticmethod
    def _check_firefox_availability() -> bool:
        """Check if Firefox is actually available on the system."""
        # Firefox через snap не работает с Selenium, возвращаем False
        return False
    
    @staticmethod
    def _check_chrome_availability() -> bool:
        """Check if Chrome is actually available on the system."""
        try:
            import subprocess
            # Try different Chrome paths
            chrome_paths = [
                'google-chrome',
                'chrome',
                'chromium-browser',
                'chromium'
            ]
            
            for path in chrome_paths:
                try:
                    result = subprocess.run([path, '--version'], 
                                          capture_output=True, 
                                          text=True, 
                                          timeout=5)
                    if result.returncode == 0:
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False
    
    @staticmethod
    def _create_firefox_browser(proxy: Optional[Proxy] = None, 
                              proxy_config: Optional[Dict] = None,
                              headless: bool = True) -> Optional[webdriver.Firefox]:
        """Create Firefox browser."""
        try:
            options = FirefoxOptions()
            
            # Basic configuration
            if headless:
                options.add_argument("--headless")
            
            # Apply proxy configuration
            if proxy:
                BrowserFactory._apply_proxy_to_firefox_options(options, proxy)
            elif proxy_config:
                BrowserFactory._apply_proxy_config_to_firefox_options(options, proxy_config)
            
            # Anti-detection configuration
            BrowserFactory._configure_firefox_anti_detection(options)
            
            # Create Firefox browser
            driver = webdriver.Firefox(options=options)
            
            logger.info("✅ Firefox stealth browser created successfully")
            return driver
            
        except Exception as e:
            logger.error(f"❌ Error creating Firefox browser: {e}")
            return None
    
    @staticmethod
    def _create_chrome_browser(proxy: Optional[Proxy] = None, 
                             proxy_config: Optional[Dict] = None,
                             headless: bool = True) -> Optional[webdriver.Chrome]:
        """Create Chrome browser."""
        try:
            options = ChromeOptions()
            
            # Basic configuration
            if headless:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-dev-shm-usage")
            
            # Add unique user data directory to avoid conflicts
            import tempfile
            user_data_dir = tempfile.mkdtemp(prefix="chrome_")
            options.add_argument(f"--user-data-dir={user_data_dir}")
            
            # Apply proxy configuration
            if proxy:
                BrowserFactory._apply_proxy_to_chrome_options(options, proxy)
            elif proxy_config:
                BrowserFactory._apply_proxy_config_to_chrome_options(options, proxy_config)
            
            # Anti-detection configuration
            BrowserFactory._configure_chrome_anti_detection(options)
            
            # Create Chrome browser
            driver = webdriver.Chrome(options=options)
            
            logger.info("✅ Chrome stealth browser created successfully")
            return driver
            
        except Exception as e:
            logger.error(f"❌ Error creating Chrome browser: {e}")
            return None
    
    @staticmethod
    def _apply_proxy_to_firefox_options(options: FirefoxOptions, proxy: Proxy):
        """Apply proxy configuration to Firefox options."""
        if proxy.protocol.startswith('socks'):
            # SOCKS5 proxy configuration for Firefox
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", proxy.address)
            options.set_preference("network.proxy.socks_port", proxy.port)
            options.set_preference("network.proxy.socks_version", 5)
            options.set_preference("network.proxy.socks_remote_dns", True)
        else:
            # HTTP proxy configuration for Firefox
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", proxy.address)
            options.set_preference("network.proxy.http_port", proxy.port)
            options.set_preference("network.proxy.ssl", proxy.address)
            options.set_preference("network.proxy.ssl_port", proxy.port)
        
        logger.info(f"🔗 Configured Firefox proxy: {proxy.protocol}://{proxy.full_address}")
    
    @staticmethod
    def _apply_proxy_to_chrome_options(options: ChromeOptions, proxy: Proxy):
        """Apply proxy configuration to Chrome options."""
        if proxy.protocol.startswith('socks'):
            proxy_url = f"socks5://{proxy.full_address}"
        else:
            proxy_url = f"{proxy.protocol}://{proxy.full_address}"
        
        options.add_argument(f"--proxy-server={proxy_url}")
        logger.info(f"🔗 Configured Chrome proxy: {proxy_url}")
    
    @staticmethod
    def _apply_proxy_config_to_firefox_options(options: FirefoxOptions, proxy_config: Dict):
        """Apply proxy configuration dict to Firefox options."""
        # Extract SOCKS5 proxy from config (for Tor/WARP)
        socks_url = proxy_config.get('http', '').replace('socks5://', '')
        if socks_url:
            host, port = socks_url.split(':')
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", host)
            options.set_preference("network.proxy.socks_port", int(port))
            options.set_preference("network.proxy.socks_version", 5)
            options.set_preference("network.proxy.socks_remote_dns", True)
            logger.info(f"🔗 Configured Firefox Tor/WARP proxy: socks5://{socks_url}")
    
    @staticmethod
    def _apply_proxy_config_to_chrome_options(options: ChromeOptions, proxy_config: Dict):
        """Apply proxy configuration dict to Chrome options."""
        # Extract SOCKS5 proxy from config (for Tor/WARP)
        socks_url = proxy_config.get('http', '').replace('socks5://', '')
        if socks_url:
            options.add_argument(f"--proxy-server=socks5://{socks_url}")
            logger.info(f"🔗 Configured Chrome Tor/WARP proxy: socks5://{socks_url}")
    
    @staticmethod
    def _configure_firefox_anti_detection(options: FirefoxOptions):
        """Configure anti-detection measures for Firefox."""
        # Random user agent
        user_agent = TrastConfig.get_random_user_agent()
        options.set_preference("general.useragent.override", user_agent)
        
        # Random viewport
        width, height = TrastConfig.get_random_viewport()
        options.set_preference("browser.window.width", width)
        options.set_preference("browser.window.height", height)
        
        # Anti-detection preferences
        anti_detection_prefs = {
            "dom.webdriver.enabled": False,
            "useAutomationExtension": False,
            "marionette.enabled": True,
            "dom.webnotifications.enabled": False,
            "media.peerconnection.enabled": False,
            "media.navigator.enabled": False,
            "dom.push.enabled": False,
            "geo.enabled": False,
            "browser.safebrowsing.enabled": False,
            "browser.safebrowsing.malware.enabled": False,
            "browser.safebrowsing.phishing.enabled": False,
            "privacy.trackingprotection.enabled": False,
            "browser.cache.disk.enable": False,
            "browser.cache.memory.enable": False,
            "browser.cache.offline.enable": False,
            "network.http.use-cache": False,
            "browser.sessionstore.enabled": False,
            "browser.sessionstore.resume_from_crash": False,
            "browser.startup.page": 0,
            "browser.startup.homepage": "about:blank",
            "startup.homepage_welcome_url": "about:blank",
            "startup.homepage_welcome_url.additional": "about:blank"
        }
        
        for pref, value in anti_detection_prefs.items():
            options.set_preference(pref, value)
        
        logger.debug("🛡️ Firefox anti-detection measures configured")
    
    @staticmethod
    def _configure_chrome_anti_detection(options: ChromeOptions):
        """Configure anti-detection measures for Chrome."""
        # Random user agent
        user_agent = TrastConfig.get_random_user_agent()
        options.add_argument(f"--user-agent={user_agent}")
        
        # Random viewport
        width, height = TrastConfig.get_random_viewport()
        options.add_argument(f"--window-size={width},{height}")
        
        # Additional anti-detection arguments
        anti_detection_args = [
            "--disable-images",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--memory-pressure-off",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-networking",
            "--aggressive-cache-discard",
            "--disable-blink-features=AutomationControlled"
        ]
        
        for arg in anti_detection_args:
            options.add_argument(arg)
        
        # Experimental options
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        logger.debug("🛡️ Chrome anti-detection measures configured")


class BrowserSession:
    """Represents a browser session with lifecycle management."""
    
    def __init__(self, driver: webdriver.Remote, proxy: Optional[Proxy] = None, 
                 proxy_config: Optional[Dict] = None):
        self.driver = driver
        self.proxy = proxy
        self.proxy_config = proxy_config
        self.start_time = datetime.now()
        self.request_count = 0
        self.last_request_time = None
        self.is_disposed = False
        self.browser_type = "firefox" if "firefox" in str(type(driver)).lower() else "chrome"
    
    def increment_request_count(self):
        """Increment request counter."""
        self.request_count += 1
        self.last_request_time = datetime.now()
    
    def get_session_duration(self) -> float:
        """Get session duration in seconds."""
        return (datetime.now() - self.start_time).total_seconds()
    
    def get_requests_per_minute(self) -> float:
        """Calculate requests per minute."""
        duration = self.get_session_duration()
        if duration > 0:
            return (self.request_count * 60) / duration
        return 0
    
    def dispose(self):
        """Clean shutdown of browser session."""
        if not self.is_disposed:
            try:
                self.driver.quit()
                self.is_disposed = True
                logger.debug(f"{self.browser_type.title()} session disposed after {self.get_session_duration():.1f}s")
            except Exception as e:
                logger.warning(f"Error disposing {self.browser_type} session: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.dispose()
    
    def __del__(self):
        """Destructor fallback."""
        if not self.is_disposed:
            self.dispose()


class DisposableBrowserPool:
    """Manages disposable browser instances."""
    
    def __init__(self, max_sessions: int = 5):
        self.max_sessions = max_sessions
        self.active_sessions: list = []
        self.session_counter = 0
    
    def get_browser(self, proxy: Optional[Proxy] = None, 
                   proxy_config: Optional[Dict] = None) -> Optional[BrowserSession]:
        """Get a new browser session."""
        try:
            # Clean up old sessions
            self._cleanup_old_sessions()
            
            # Create new browser
            driver = BrowserFactory.create_stealth_browser(proxy, proxy_config)
            if not driver:
                return None
            
            # Create session
            session = BrowserSession(driver, proxy, proxy_config)
            session.session_id = self.session_counter
            self.session_counter += 1
            
            self.active_sessions.append(session)
            logger.info(f"Created {session.browser_type.title()} session {session.session_id}")
            
            return session
            
        except Exception as e:
            logger.error(f"Error creating browser session: {e}")
            return None
    
    def recycle_on_failure(self, session: BrowserSession):
        """Recycle browser session on failure."""
        logger.warning(f"Recycling {session.browser_type.title()} session {session.session_id} due to failure")
        session.dispose()
        if session in self.active_sessions:
            self.active_sessions.remove(session)
    
    def cleanup_all(self):
        """Clean up all active sessions."""
        logger.info(f"Cleaning up {len(self.active_sessions)} active browser sessions")
        for session in self.active_sessions[:]:  # Copy list to avoid modification during iteration
            session.dispose()
        self.active_sessions.clear()
    
    def _cleanup_old_sessions(self):
        """Clean up sessions that are too old or have too many requests."""
        current_time = datetime.now()
        sessions_to_remove = []
        
        for session in self.active_sessions:
            # Remove sessions older than 30 minutes
            if (current_time - session.start_time).total_seconds() > 1800:
                sessions_to_remove.append(session)
            # Remove sessions with too many requests
            elif session.request_count > 100:
                sessions_to_remove.append(session)
        
        for session in sessions_to_remove:
            logger.debug(f"Cleaning up old {session.browser_type.title()} session {session.session_id}")
            session.dispose()
            self.active_sessions.remove(session)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        total_requests = sum(session.request_count for session in self.active_sessions)
        avg_duration = sum(session.get_session_duration() for session in self.active_sessions) / len(self.active_sessions) if self.active_sessions else 0
        
        # Count browser types
        browser_types = {}
        for session in self.active_sessions:
            browser_types[session.browser_type] = browser_types.get(session.browser_type, 0) + 1
        
        return {
            'active_sessions': len(self.active_sessions),
            'total_requests': total_requests,
            'average_duration': avg_duration,
            'session_counter': self.session_counter,
            'browser_types': browser_types
        }
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup_all()
