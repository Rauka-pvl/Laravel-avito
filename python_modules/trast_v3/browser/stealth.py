"""Stealth techniques for bypassing detection"""

import random
from typing import Dict, Any
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeWebDriver
from selenium.webdriver.firefox.webdriver import WebDriver as FirefoxWebDriver

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import USER_AGENTS

logger = get_logger("browser.stealth")


def apply_chrome_stealth(driver: ChromeWebDriver):
    """Apply stealth techniques to Chrome driver"""
    try:
        stealth_scripts = """
        // Hide webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        
        // Chrome object
        window.chrome = {
            runtime: {}
        };
        
        // Permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
            configurable: true
        });
        
        // Languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en'],
            configurable: true
        });
        
        // Hardware concurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 4,
            configurable: true
        });
        
        // Device memory
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
            configurable: true
        });
        """
        
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': stealth_scripts
        })
        logger.debug("Chrome stealth scripts applied")
    except Exception as e:
        logger.warning(f"Failed to apply Chrome stealth: {e}")


def apply_firefox_stealth(driver: FirefoxWebDriver):
    """Apply stealth techniques to Firefox driver"""
    try:
        # Firefox doesn't support CDP, so we use execute_script
        safe_scripts = [
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
            "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})",
            "Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']})",
            "Object.defineProperty(navigator, 'permissions', {get: () => ({query: () => Promise.resolve({state: 'granted'})})})",
            "Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4})",
            "Object.defineProperty(navigator, 'deviceMemory', {get: () => 8})",
            "Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0})",
        ]
        
        for script in safe_scripts:
            try:
                driver.execute_script(script)
            except Exception as e:
                logger.debug(f"Failed to execute stealth script: {e}")
        
        logger.debug("Firefox stealth scripts applied")
    except Exception as e:
        logger.warning(f"Failed to apply Firefox stealth: {e}")


def get_random_user_agent() -> str:
    """Get a random user agent"""
    return random.choice(USER_AGENTS)


def get_random_window_size() -> tuple:
    """Get random window size"""
    width = random.randint(1200, 1920)
    height = random.randint(800, 1080)
    return width, height

