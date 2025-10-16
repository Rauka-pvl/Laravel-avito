"""
Anti-blocking strategies module for Trast parser.

Handles CAPTCHA detection, human behavior simulation, delays, and session management.
"""

import time
import random
import pickle
import logging
import os
from typing import Optional, Dict, List, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .config import TrastConfig

logger = logging.getLogger("trast.anti_block")


class BlockDetector:
    """Detects various types of blocking mechanisms."""
    
    @staticmethod
    def check_for_captcha(driver) -> bool:
        """Check for CAPTCHA or Cloudflare protection."""
        try:
            captcha_indicators = [
                "captcha", "cloudflare", "challenge", "verification",
                "robot", "bot", "security check", "checking your browser",
                "ddos protection", "access denied", "blocked"
            ]
            
            page_source = driver.page_source.lower()
            page_title = driver.title.lower()
            
            for indicator in captcha_indicators:
                if indicator in page_source or indicator in page_title:
                    logger.warning(f"🛡️ Detected protection: {indicator}")
                    return True
                    
            return False
            
        except Exception as e:
            logger.debug(f"Error checking for CAPTCHA: {e}")
            return False
    
    @staticmethod
    def check_for_cloudflare(driver) -> bool:
        """Specifically check for Cloudflare protection."""
        try:
            page_source = driver.page_source.lower()
            cloudflare_indicators = [
                "cloudflare", "checking your browser", "ddos protection",
                "cf-browser-verification", "cf-challenge"
            ]
            
            for indicator in cloudflare_indicators:
                if indicator in page_source:
                    logger.warning(f"🛡️ Cloudflare protection detected: {indicator}")
                    return True
                    
            return False
            
        except Exception as e:
            logger.debug(f"Error checking for Cloudflare: {e}")
            return False
    
    @staticmethod
    def detect_rate_limit(page_source: str) -> bool:
        """Detect rate limiting indicators."""
        rate_limit_indicators = [
            "rate limit", "too many requests", "429", "throttled",
            "slow down", "try again later", "temporarily blocked"
        ]
        
        page_source_lower = page_source.lower()
        for indicator in rate_limit_indicators:
            if indicator in page_source_lower:
                logger.warning(f"🚫 Rate limit detected: {indicator}")
                return True
                
        return False
    
    @staticmethod
    def detect_blocking_indicators(driver) -> List[str]:
        """Detect all blocking indicators and return list."""
        indicators = []
        
        try:
            page_source = driver.page_source.lower()
            page_title = driver.title.lower()
            
            blocking_patterns = {
                "captcha": ["captcha", "verification", "robot", "bot"],
                "cloudflare": ["cloudflare", "checking your browser", "ddos protection"],
                "rate_limit": ["rate limit", "too many requests", "429", "throttled"],
                "access_denied": ["access denied", "403", "forbidden", "blocked"],
                "ip_blocked": ["ip blocked", "ip banned", "suspicious activity"]
            }
            
            for category, patterns in blocking_patterns.items():
                for pattern in patterns:
                    if pattern in page_source or pattern in page_title:
                        indicators.append(f"{category}: {pattern}")
            
        except Exception as e:
            logger.debug(f"Error detecting blocking indicators: {e}")
        
        return indicators


class HumanBehaviorSimulator:
    """Simulates human-like behavior to avoid detection."""
    
    @staticmethod
    def random_scroll(driver, min_scroll: int = 100, max_scroll: int = 800):
        """Perform random scrolling."""
        try:
            scroll_amount = random.randint(min_scroll, max_scroll)
            driver.execute_script(f"window.scrollTo(0, {scroll_amount});")
            logger.debug(f"Scrolled {scroll_amount}px")
        except Exception as e:
            logger.debug(f"Error scrolling: {e}")
    
    @staticmethod
    def simulate_reading(driver, min_time: float = 2.0, max_time: float = 5.0):
        """Simulate reading behavior."""
        try:
            reading_time = random.uniform(min_time, max_time)
            logger.debug(f"Simulating reading: {reading_time:.1f}s")
            time.sleep(reading_time)
        except Exception as e:
            logger.debug(f"Error simulating reading: {e}")
    
    @staticmethod
    def random_mouse_movement(driver):
        """Simulate random mouse movements."""
        try:
            # Random click simulation
            if random.random() < 0.3:  # 30% chance
                driver.execute_script("document.body.click();")
                logger.debug("Simulated mouse click")
        except Exception as e:
            logger.debug(f"Error simulating mouse movement: {e}")
    
    @staticmethod
    def apply_behavior(driver):
        """Apply comprehensive human behavior."""
        try:
            # Random scrolling
            HumanBehaviorSimulator.random_scroll(driver)
            time.sleep(random.uniform(1, 3))
            
            # Random mouse movement
            HumanBehaviorSimulator.random_mouse_movement(driver)
            time.sleep(random.uniform(0.5, 1.5))
            
            # Simulate reading
            HumanBehaviorSimulator.simulate_reading(driver)
            
        except Exception as e:
            logger.debug(f"Error applying human behavior: {e}")


class DelayStrategy:
    """Manages various delay strategies."""
    
    @staticmethod
    def cloudflare_safe_delay():
        """Cloudflare-safe delay with randomization."""
        base_delay = random.uniform(*TrastConfig.CLOUDFLARE_DELAY_RANGE)
        extra_delay = random.uniform(*TrastConfig.EXTRA_DELAY_RANGE)
        
        total_delay = base_delay + extra_delay
        logger.info(f"🛡️ Cloudflare-safe delay: {total_delay:.1f}s")
        time.sleep(total_delay)
    
    @staticmethod
    def smart_delay(page_num: int, had_error: bool = False):
        """Smart delay based on context."""
        if had_error:
            delay = random.uniform(*TrastConfig.ERROR_DELAY_RANGE)
        elif page_num % 10 == 0:
            delay = random.uniform(*TrastConfig.SESSION_DELAY_RANGE)
        else:
            delay = random.uniform(*TrastConfig.SMART_DELAY_RANGE)
        
        logger.debug(f"Smart delay: {delay:.1f}s")
        time.sleep(delay)
    
    @staticmethod
    def adaptive_delay(success_rate: float):
        """Adaptive delay based on success rate."""
        if success_rate < 0.5:
            # Low success rate, longer delays
            delay = random.uniform(20, 40)
        elif success_rate < 0.8:
            # Medium success rate, moderate delays
            delay = random.uniform(10, 20)
        else:
            # High success rate, shorter delays
            delay = random.uniform(5, 10)
        
        logger.debug(f"Adaptive delay (success rate {success_rate:.2f}): {delay:.1f}s")
        time.sleep(delay)


class SessionEstablisher:
    """Handles session establishment and legitimacy checks."""
    
    def __init__(self):
        self.cookies_file = TrastConfig.SESSION_COOKIES_FILE
    
    def establish_legitimate_session(self, driver, max_attempts: int = 3) -> bool:
        """Establish legitimate session for bypassing Cloudflare."""
        for attempt in range(max_attempts):
            try:
                logger.info(f"🏠 Attempt {attempt + 1}/{max_attempts}: Accessing main page...")
                
                # First, try to access main page
                driver.get(TrastConfig.MAIN_URL)
                
                # Wait for Cloudflare to load
                wait_time = random.uniform(10, 20)
                logger.info(f"⏳ Waiting for Cloudflare: {wait_time:.1f}s")
                time.sleep(wait_time)
                
                # Human behavior
                HumanBehaviorSimulator.apply_behavior(driver)
                
                # Check page status
                page_title = driver.title.lower()
                page_source = driver.page_source.lower()
                
                logger.info(f"📄 Page title: {driver.title}")
                
                # Check for various blocking types
                if BlockDetector.check_for_captcha(driver):
                    logger.warning("🛡️ CAPTCHA detected, waiting...")
                    time.sleep(random.uniform(30, 60))
                    
                    # Re-check
                    if BlockDetector.check_for_captcha(driver):
                        logger.error("🛡️ CAPTCHA persists, trying different strategy")
                        if attempt < max_attempts - 1:
                            continue
                        return False
                
                # Check for other blocking indicators
                block_indicators = [
                    "access denied", "blocked", "forbidden", "403", "429",
                    "too many requests", "rate limit", "ip blocked"
                ]
                
                for indicator in block_indicators:
                    if indicator in page_source or indicator in page_title:
                        logger.warning(f"🚫 Blocking indicator: {indicator}")
                        if attempt < max_attempts - 1:
                            logger.info("🔄 Trying different strategy...")
                            time.sleep(random.uniform(30, 60))
                            continue
                        return False
                
                # If we got here, try to access shop
                logger.info("✅ Main page loaded, accessing shop...")
                driver.get(TrastConfig.SHOP_URL)
                
                # Additional wait for shop
                time.sleep(random.uniform(5, 10))
                HumanBehaviorSimulator.apply_behavior(driver)
                
                # Verify shop loaded
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                    )
                    logger.info("✅ Shop loaded successfully")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️ Shop didn't load: {e}")
                    if attempt < max_attempts - 1:
                        continue
                    return False
                
            except Exception as e:
                logger.error(f"❌ Session establishment error (attempt {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    logger.info("🔄 Retrying in 30 seconds...")
                    time.sleep(30)
                    continue
                return False
        
        logger.error("🛡️ All session establishment attempts failed")
        return False
    
    def save_cookies(self, driver, filepath: Optional[str] = None):
        """Save session cookies."""
        try:
            if filepath is None:
                filepath = self.cookies_file
                
            cookies = driver.get_cookies()
            with open(filepath, 'wb') as f:
                pickle.dump(cookies, f)
            logger.debug(f"Cookies saved to {filepath}")
        except Exception as e:
            logger.error(f"Error saving cookies: {e}")
    
    def load_cookies(self, driver, filepath: Optional[str] = None):
        """Load session cookies."""
        try:
            if filepath is None:
                filepath = self.cookies_file
                
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    cookies = pickle.load(f)
                driver.get(TrastConfig.MAIN_URL)
                for cookie in cookies:
                    try:
                        driver.add_cookie(cookie)
                    except:
                        pass
                logger.debug(f"Cookies loaded from {filepath}")
        except Exception as e:
            logger.error(f"Error loading cookies: {e}")


class FingerprintRandomizer:
    """Randomizes browser fingerprints."""
    
    @staticmethod
    def get_random_user_agent() -> str:
        """Get random user agent."""
        return TrastConfig.get_random_user_agent()
    
    @staticmethod
    def get_random_viewport() -> Tuple[int, int]:
        """Get random viewport dimensions."""
        return TrastConfig.get_random_viewport()
    
    @staticmethod
    def randomize_headers() -> Dict[str, str]:
        """Generate randomized headers."""
        return {
            'User-Agent': FingerprintRandomizer.get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
        }
    
    @staticmethod
    def randomize_browser_properties(driver):
        """Randomize browser properties via JavaScript."""
        try:
            # Randomize screen resolution
            width, height = FingerprintRandomizer.get_random_viewport()
            
            scripts = [
                f"Object.defineProperty(screen, 'width', {{value: {width}}});",
                f"Object.defineProperty(screen, 'height', {{value: {height}}});",
                f"Object.defineProperty(screen, 'availWidth', {{value: {width}}});",
                f"Object.defineProperty(screen, 'availHeight', {{value: {height}}});",
                "Object.defineProperty(navigator, 'webdriver', {value: undefined});",
                "Object.defineProperty(navigator, 'plugins', {value: []});",
                "Object.defineProperty(navigator, 'languages', {value: ['ru-RU', 'ru', 'en-US', 'en']});"
            ]
            
            for script in scripts:
                driver.execute_script(script)
                
            logger.debug("Browser properties randomized")
        except Exception as e:
            logger.debug(f"Error randomizing browser properties: {e}")
