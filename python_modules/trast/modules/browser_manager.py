"""
Browser management module for Trast parser.

Handles browser creation, configuration, and lifecycle management.
"""

import time
import random
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import undetected_chromedriver as uc
from .config import TrastConfig
from .proxy_manager import Proxy

logger = logging.getLogger("trast.browser_manager")


class BrowserFactory:
    """Factory for creating configured browser instances."""
    
    @staticmethod
    def create_stealth_browser(proxy: Optional[Proxy] = None, 
                             proxy_config: Optional[Dict] = None,
                             headless: bool = True) -> Optional[uc.Chrome]:
        """Create stealth browser with anti-detection measures."""
        try:
            options = uc.ChromeOptions()
            
            # Basic configuration
            if headless:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            
            # Apply proxy configuration
            if proxy:
                BrowserFactory._apply_proxy_to_options(options, proxy)
            elif proxy_config:
                BrowserFactory._apply_proxy_config_to_options(options, proxy_config)
            
            # Anti-detection configuration
            BrowserFactory._configure_anti_detection(options)
            
            # Create browser
            driver = uc.Chrome(options=options, version_main=None)
            
            logger.info("✅ Stealth browser created successfully")
            return driver
            
        except Exception as e:
            logger.error(f"❌ Error creating stealth browser: {e}")
            return None
    
    @staticmethod
    def _apply_proxy_to_options(options: uc.ChromeOptions, proxy: Proxy):
        """Apply proxy configuration to Chrome options."""
        if proxy.protocol.startswith('socks'):
            proxy_url = f"{proxy.protocol}://{proxy.full_address}"
        else:
            proxy_url = f"{proxy.protocol}://{proxy.full_address}"
        
        options.add_argument(f"--proxy-server={proxy_url}")
        logger.info(f"🔗 Configured proxy: {proxy_url}")
    
    @staticmethod
    def _apply_proxy_config_to_options(options: uc.ChromeOptions, proxy_config: Dict):
        """Apply proxy configuration dict to Chrome options."""
        # Extract SOCKS5 proxy from config
        socks_url = proxy_config.get('http', '').replace('socks5://', '')
        if socks_url:
            options.add_argument(f"--proxy-server=socks5://{socks_url}")
            logger.info(f"🔗 Configured Tor proxy: socks5://{socks_url}")
    
    @staticmethod
    def _configure_anti_detection(options: uc.ChromeOptions):
        """Configure anti-detection measures."""
        # Random user agent
        user_agent = TrastConfig.get_random_user_agent()
        options.add_argument(f"user-agent={user_agent}")
        
        # Random viewport
        width, height = TrastConfig.get_random_viewport()
        options.add_argument(f"--window-size={width},{height}")
        
        # Additional anti-detection arguments
        anti_detection_args = [
            "--disable-images",
            "--disable-dev-shm-usage",
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
        
        # Experimental options (commented out due to Chrome version compatibility)
        # options.add_experimental_option("excludeSwitches", ["enable-automation"])
        # options.add_experimental_option('useAutomationExtension', False)
        
        logger.debug("🛡️ Anti-detection measures configured")


class BrowserSession:
    """Represents a browser session with lifecycle management."""
    
    def __init__(self, driver: uc.Chrome, proxy: Optional[Proxy] = None, 
                 proxy_config: Optional[Dict] = None):
        self.driver = driver
        self.proxy = proxy
        self.proxy_config = proxy_config
        self.start_time = datetime.now()
        self.request_count = 0
        self.last_request_time = None
        self.is_disposed = False
    
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
                logger.debug(f"Browser session disposed after {self.get_session_duration():.1f}s")
            except Exception as e:
                logger.warning(f"Error disposing browser session: {e}")
    
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
            logger.info(f"Created browser session {session.session_id}")
            
            return session
            
        except Exception as e:
            logger.error(f"Error creating browser session: {e}")
            return None
    
    def recycle_on_failure(self, session: BrowserSession):
        """Recycle browser session on failure."""
        logger.warning(f"Recycling browser session {session.session_id} due to failure")
        session.dispose()
        if session in self.active_sessions:
            self.active_sessions.remove(session)
    
    def cleanup_all(self):
        """Clean up all active sessions."""
        logger.info(f"Cleaning up {len(self.active_sessions)} active sessions")
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
            logger.debug(f"Cleaning up old session {session.session_id}")
            session.dispose()
            self.active_sessions.remove(session)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        total_requests = sum(session.request_count for session in self.active_sessions)
        avg_duration = sum(session.get_session_duration() for session in self.active_sessions) / len(self.active_sessions) if self.active_sessions else 0
        
        return {
            'active_sessions': len(self.active_sessions),
            'total_requests': total_requests,
            'average_duration': avg_duration,
            'session_counter': self.session_counter
        }
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup_all()
