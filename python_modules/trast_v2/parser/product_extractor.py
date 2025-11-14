"""Product extraction from page HTML"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger

logger = get_logger("parser.product_extractor")


def extract_products(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Extract products from catalog page
    
    Args:
        soup: BeautifulSoup object of catalog page
    
    Returns:
        List of product dicts with keys: manufacturer, article, description, price
    """
    results = []
    cards = soup.select("div.product.product-plate")
    
    for card in cards:
        try:
            # Check if product is in stock
            stock_badge = card.select_one("div.product-badge.product-stock.instock")
            if not stock_badge or "В наличии" not in stock_badge.text.strip():
                continue
            
            # Extract product data
            title_el = card.select_one("a.product-title")
            article_el = card.select_one("div.product-attributes .item:nth-child(1) .value")
            manufacturer_el = card.select_one("div.product-attributes .item:nth-child(2) .value")
            price_el = card.select_one("div.product-price .woocommerce-Price-amount.amount")
            
            # Validate required elements
            if not (title_el and article_el and manufacturer_el and price_el):
                continue
            
            # Extract text
            title = title_el.text.strip()
            article = article_el.text.strip()
            manufacturer = manufacturer_el.text.strip()
            raw_price = price_el.text.strip().replace("\xa0", " ")
            
            # Clean price (remove non-digit characters except spaces)
            clean_price = re.sub(r"[^\d\s]", "", raw_price).strip()
            
            product = {
                "manufacturer": manufacturer,
                "article": article,
                "description": title,
                "price": {"price": clean_price}
            }
            
            results.append(product)
            logger.debug(f"Extracted product: {manufacturer} - {article} - {clean_price}")
            
        except Exception as e:
            logger.warning(f"Error extracting product from card: {e}")
            continue
    
    logger.info(f"Extracted {len(results)} products from page")
    return results

