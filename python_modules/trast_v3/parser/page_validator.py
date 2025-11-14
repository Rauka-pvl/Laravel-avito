"""Enhanced page validation with partial page handling for Trast Parser V3"""

import re
from typing import Dict, Optional
from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from utils.exceptions import PageBlockedError, PageEmptyError, PagePartialLoadError

logger = get_logger("parser.page_validator")


def has_catalog_structure(soup: BeautifulSoup) -> bool:
    """
    Check if page has catalog structure
    
    Args:
        soup: BeautifulSoup object
    
    Returns:
        True if catalog structure is present
    """
    # Check for product grid
    has_products_grid = bool(soup.select(".products-grid, .products, .shop-container, .woocommerce-products-header"))
    
    # Check for pagination
    has_pagination = bool(soup.select(".woocommerce-pagination, .page-numbers, .facetwp-pager, .facetwp-pager .facetwp-page"))
    
    # Check for menu/navigation
    has_menu = bool(soup.select("header, .site-header, .main-navigation, nav, .menu, .navigation"))
    
    # Check for footer
    has_footer = bool(soup.select("footer, .site-footer, .footer"))
    
    # Check for title and meta
    has_title = bool(soup.select("title"))
    has_meta = bool(soup.select("meta"))
    
    # Count structure elements
    structure_count = sum([
        has_products_grid,
        has_pagination,
        has_menu,
        has_footer,
        has_title,
        has_meta
    ])
    
    # Need at least 3 elements to confirm catalog structure
    return structure_count >= 3


def is_page_blocked(soup: BeautifulSoup, page_source: str) -> Dict[str, any]:
    """
    Check if page is blocked (Cloudflare, etc.)
    
    Args:
        soup: BeautifulSoup object
        page_source: Raw HTML page source
    
    Returns:
        Dict with 'blocked' (bool) and 'reason' (str or None)
    """
    page_source_lower = page_source.lower() if page_source else ""
    
    # Block indicators
    blocker_keywords = [
        "cloudflare",
        "attention required",
        "checking your browser",
        "just a moment",
        "access denied",
        "forbidden",
        "service temporarily unavailable",
        "temporarily unavailable",
        "maintenance",
        "запрос отклонен",
        "доступ запрещен",
        "ошибка 403",
        "ошибка 503",
        "error 403",
        "error 503",
        "captcha",
        "please enable javascript",
        "varnish cache server",
        "bad gateway",
        "gateway timeout",
    ]
    
    for keyword in blocker_keywords:
        if keyword in page_source_lower:
            return {
                "blocked": True,
                "reason": keyword
            }
    
    # Check for catalog structure
    if not has_catalog_structure(soup):
        return {
            "blocked": True,
            "reason": "no_catalog_structure"
        }
    
    return {
        "blocked": False,
        "reason": None
    }


def is_catalog_page_loaded(soup: BeautifulSoup, page_source: str) -> bool:
    """
    Check if catalog page loaded correctly
    
    Args:
        soup: BeautifulSoup object
        page_source: Raw HTML page source
    
    Returns:
        True if page loaded correctly
    """
    page_source_lower = page_source.lower() if page_source else ""
    
    has_pagination = bool(soup.select(".facetwp-pager .facetwp-page"))
    has_products = bool(soup.select("div.product.product-plate"))
    
    # Check for blockers
    blocker_keywords = [
        "cloudflare",
        "attention required",
        "checking your browser",
        "just a moment",
        "access denied",
        "forbidden",
        "service temporarily unavailable",
        "temporarily unavailable",
        "maintenance",
        "запрос отклонен",
        "доступ запрещен",
        "ошибка 403",
        "ошибка 503",
        "error 403",
        "error 503",
        "captcha",
        "please enable javascript",
        "varnish cache server",
        "bad gateway",
        "gateway timeout",
    ]
    
    if any(keyword in page_source_lower for keyword in blocker_keywords):
        return False
    
    # Need either products or pagination
    if not has_products and not has_pagination:
        return False
    
    return True


def get_page_status(soup: BeautifulSoup, page_source: str, products_count: int = 0) -> Dict[str, any]:
    """
    Determine page status: empty, blocked, partial, or normal
    
    Enhanced version with better partial page detection
    
    Args:
        soup: BeautifulSoup object
        page_source: Raw HTML page source
        products_count: Number of products found on page
    
    Returns:
        Dict with 'status' ('empty'|'blocked'|'partial'|'normal') and 'reason'
    """
    # First check for blocking
    block_check = is_page_blocked(soup, page_source)
    if block_check["blocked"]:
        return {
            "status": "blocked",
            "reason": block_check["reason"] or "no_dom"
        }
    
    # Check product count
    if products_count == 0:
        if has_catalog_structure(soup):
            # Has structure but no products - end of data
            return {
                "status": "empty",
                "reason": "no_items"
            }
        else:
            # No structure - partial load or block
            return {
                "status": "partial",
                "reason": "partial_dom"
            }
    elif products_count < 3:
        # Few products - suspicious, might be partial
        # Check if we have structure but few products
        if has_catalog_structure(soup):
            # Has structure but few products - might be end of data or partial
            # If we have pagination, it's likely partial
            has_pagination = bool(soup.select(".facetwp-pager .facetwp-page"))
            if has_pagination:
                return {
                    "status": "partial",
                    "reason": "few_items_with_pagination"
                }
            else:
                # No pagination, might be end of data
                return {
                    "status": "empty",
                    "reason": "few_items_no_pagination"
                }
        else:
            # No structure - definitely partial
            return {
                "status": "partial",
                "reason": "few_items_no_structure"
            }
    else:
        # Normal page with products
        return {
            "status": "normal",
            "reason": None
        }


def get_total_pages(soup: BeautifulSoup) -> Optional[int]:
    """
    Extract total number of pages from pagination
    
    Args:
        soup: BeautifulSoup object
    
    Returns:
        Total pages count or None if not found
    """
    # Try to find last page element
    last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
    if last_page_el and last_page_el.has_attr("data-page"):
        try:
            return int(last_page_el["data-page"])
        except (ValueError, TypeError):
            pass
    
    # Try to find max page from all pagination items
    pagination_items = soup.select(".facetwp-pager .facetwp-page")
    if pagination_items:
        max_page = 0
        for page_el in pagination_items:
            data_page = page_el.get("data-page")
            text_value = page_el.get_text(strip=True)
            
            candidate = None
            if data_page:
                try:
                    candidate = int(data_page)
                except ValueError:
                    pass
            elif text_value.isdigit():
                candidate = int(text_value)
            
            if candidate and candidate > max_page:
                max_page = candidate
        
        if max_page > 0:
            return max_page
    
    return None

