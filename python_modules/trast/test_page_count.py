#!/usr/bin/env python3
"""
Simple test script to determine page count on trast-zapchast.ru
"""

import os
import sys
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), "modules"))
from config import TrastConfig

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_page_count():
    """Test to determine page count."""
    
    # Chrome options
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")
    
    # Add unique user data directory
    import tempfile
    user_data_dir = tempfile.mkdtemp(prefix="chrome_test_")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    
    driver = None
    try:
        logger.info("🚀 Starting Chrome browser...")
        driver = webdriver.Chrome(options=options)
        
        # Access main page first
        logger.info(f"🏠 Accessing main page: {TrastConfig.MAIN_URL}")
        driver.get(TrastConfig.MAIN_URL)
        time.sleep(5)
        
        # Access shop page
        logger.info(f"🛒 Accessing shop page: {TrastConfig.SHOP_URL}")
        driver.get(TrastConfig.SHOP_URL)
        time.sleep(10)
        
        # Log page info
        logger.info(f"📄 Page title: {driver.title}")
        logger.info(f"🌐 Current URL: {driver.current_url}")
        
        # Save HTML for analysis
        debug_file = "debug_shop_page.html"
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info(f"💾 Saved HTML to: {debug_file}")
        
        # Parse HTML
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Look for pagination
        logger.info("🔍 Looking for pagination...")
        
        # Try FacetWP pagination first
        last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
        if last_page_el and last_page_el.has_attr("data-page"):
            page_count = int(last_page_el["data-page"])
            logger.info(f"✅ Found FacetWP pagination: {page_count} pages")
            return page_count
        
        # Try other pagination selectors
        pagination_selectors = [
            ".page-numbers",
            ".pagination", 
            ".woocommerce-pagination",
            ".pager",
            "nav.pagination",
            ".page-links"
        ]
        
        for selector in pagination_selectors:
            pagination = soup.select_one(selector)
            if pagination:
                logger.info(f"🔍 Found pagination with selector: {selector}")
                page_links = pagination.select("a, span")
                page_numbers = []
                
                for link in page_links:
                    text = link.get_text().strip()
                    if text.isdigit():
                        page_numbers.append(int(text))
                
                if page_numbers:
                    max_page = max(page_numbers)
                    logger.info(f"✅ Found {max_page} pages using selector: {selector}")
                    return max_page
        
        # Look for any elements with 'page' in class or text
        logger.info("🔍 Looking for any page-related elements...")
        page_elements = soup.find_all(text=lambda text: text and 'page' in text.lower())
        for element in page_elements[:10]:  # Show first 10
            logger.info(f"📝 Found text: {element.strip()}")
        
        logger.warning("⚠️ Could not determine page count")
        return 1
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return 1
    finally:
        if driver:
            driver.quit()
            logger.info("🧹 Browser closed")

if __name__ == "__main__":
    page_count = test_page_count()
    print(f"\n📊 RESULT: {page_count} pages found")
