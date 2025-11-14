"""Proxy sources (Proxifly, proxymania)"""

import re
import time
import random
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import PROXIFLY_BASE_URL, PROXYMANIA_BASE_URL, PROXY_COUNTRIES

logger = get_logger("proxy.sources")


# Country name to code mapping
COUNTRY_NAME_TO_CODE = {
    'Russia': 'RU', 'Russian Federation': 'RU',
    'Poland': 'PL', 'Polska': 'PL',
    'Czech Republic': 'CZ', 'Czechia': 'CZ',
    'Germany': 'DE', 'Deutschland': 'DE',
    'Netherlands': 'NL', 'Holland': 'NL',
    'Sweden': 'SE', 'Sverige': 'SE',
    'France': 'FR',
    'Romania': 'RO', 'România': 'RO',
    'Bulgaria': 'BG', 'България': 'BG',
    'Belarus': 'BY', 'Беларусь': 'BY',
    'Ukraine': 'UA', 'Україна': 'UA',
    'Kazakhstan': 'KZ', 'Казахстан': 'KZ',
    'Moldova': 'MD', 'Молдова': 'MD',
    'Georgia': 'GE', 'საქართველო': 'GE',
    'Armenia': 'AM', 'Հայաստան': 'AM',
    'Azerbaijan': 'AZ', 'Azərbaycan': 'AZ',
    'Lithuania': 'LT', 'Lietuva': 'LT',
    'Latvia': 'LV', 'Latvija': 'LV',
    'Estonia': 'EE', 'Eesti': 'EE',
    'Finland': 'FI', 'Suomi': 'FI',
    'Slovakia': 'SK', 'Slovensko': 'SK',
    'Hungary': 'HU', 'Magyarország': 'HU',
    'China': 'CN', '中国': 'CN',
    'Mongolia': 'MN', 'Монгол': 'MN',
    'United States': 'US', 'USA': 'US',
    'Indonesia': 'ID',
    'Vietnam': 'VN', 'Việt Nam': 'VN',
    'Bangladesh': 'BD',
    'Brazil': 'BR', 'Brasil': 'BR',
    'Singapore': 'SG',
    'Japan': 'JP', '日本': 'JP',
    'South Korea': 'KR', '한국': 'KR',
    'Hong Kong': 'HK',
    'Turkey': 'TR', 'Türkiye': 'TR',
    'Ecuador': 'EC',
    'Peru': 'PE',
    'Colombia': 'CO',
    'Iran': 'IR',
    'United Kingdom': 'GB', 'UK': 'GB',
    'Croatia': 'HR',
    'Spain': 'ES', 'España': 'ES',
    'Kenya': 'KE',
    'Venezuela': 'VE',
    'Costa Rica': 'CR',
    'Argentina': 'AR',
    'India': 'IN',
    'Ghana': 'GH',
    'Canada': 'CA',
    'Montenegro': 'ME',
    'Philippines': 'PH',
}


def fetch_proxifly_proxies(country_filter: Optional[List[str]] = None) -> List[Dict]:
    """
    Fetch proxies from Proxifly repository
    
    Args:
        country_filter: List of country codes to filter (None = all)
    
    Returns:
        List of proxy dicts
    """
    all_proxies = []
    CIS_COUNTRIES = ["RU", "BY", "KZ", "AM", "AZ", "GE", "KG", "MD", "TJ", "TM", "UZ", "UA"]
    
    try:
        logger.info("Fetching proxies from Proxifly...")
        
        # If single country filter and it's in CIS, use direct URL
        if country_filter and len(country_filter) == 1 and country_filter[0] in CIS_COUNTRIES:
            country = country_filter[0]
            url = f"{PROXIFLY_BASE_URL}/countries/{country}/data.json"
            logger.info(f"Fetching proxies for {country} from Proxifly...")
        else:
            # Load all and filter
            url = f"{PROXIFLY_BASE_URL}/all/data.json"
            logger.info("Fetching all proxies from Proxifly for filtering...")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        proxies_data = response.json()
        
        # Process proxies
        for proxy in proxies_data:
            protocol = proxy.get('protocol', '').lower()
            
            # Extract country
            geolocation = proxy.get('geolocation', {})
            country = (geolocation.get('country', '') or proxy.get('country', '')).upper()
            
            # Filter by country
            if country_filter and country not in country_filter:
                continue
            
            # Filter by protocol
            if protocol not in ['http', 'https', 'socks4', 'socks5']:
                continue
            
            port = proxy.get('port', '')
            if isinstance(port, int):
                port = str(port)
            
            all_proxies.append({
                'ip': proxy.get('ip', ''),
                'port': port,
                'protocol': protocol,
                'country': country,
                'anonymity': proxy.get('anonymity', ''),
                'speed': proxy.get('speed', 0),
                'source': 'proxifly'
            })
        
        logger.info(f"Fetched {len(all_proxies)} proxies from Proxifly")
        return all_proxies
        
    except Exception as e:
        logger.warning(f"Error fetching proxies from Proxifly: {e}")
        return []


def parse_proxymania_page(page_num: int = 1) -> List[Dict]:
    """
    Parse a single page from proxymania.su
    
    Args:
        page_num: Page number (starts from 1)
    
    Returns:
        List of proxy dicts from this page
    """
    try:
        url = f"{PROXYMANIA_BASE_URL}?page={page_num}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find table
        table = soup.select_one('table.table_proxychecker')
        if not table:
            logger.debug(f"Table not found on page {page_num}")
            return []
        
        # Find rows
        rows = table.select('tbody#resultTable tr')
        proxies = []
        
        for row in rows:
            try:
                cells = row.select('td')
                if len(cells) < 5:
                    continue
                
                # Proxy (IP:PORT)
                proxy_text = cells[0].get_text(strip=True)
                if ':' not in proxy_text:
                    continue
                
                ip, port = proxy_text.split(':', 1)
                
                # Country
                country_name = cells[1].get_text(strip=True).strip()
                country_code = COUNTRY_NAME_TO_CODE.get(country_name, 
                    country_name[:2].upper() if len(country_name) >= 2 else 'UN')
                
                # Protocol
                protocol_text = cells[2].get_text(strip=True).upper()
                protocol_map = {
                    'SOCKS4': 'socks4',
                    'SOCKS5': 'socks5',
                    'HTTPS': 'https',
                    'HTTP': 'http',
                }
                protocol = protocol_map.get(protocol_text, protocol_text.lower())
                
                if protocol not in ['http', 'https', 'socks4', 'socks5']:
                    continue
                
                # Anonymity
                anonymity = cells[3].get_text(strip=True)
                
                # Speed
                speed_text = cells[4].get_text(strip=True)
                speed = 0
                try:
                    speed_match = re.search(r'(\d+)', speed_text)
                    if speed_match:
                        speed = int(speed_match.group(1))
                except:
                    pass
                
                proxies.append({
                    'ip': ip,
                    'port': port,
                    'protocol': protocol,
                    'country': country_code,
                    'anonymity': anonymity,
                    'speed': speed,
                    'source': 'proxymania'
                })
                
            except Exception as e:
                logger.debug(f"Error parsing proxy row: {e}")
                continue
        
        logger.debug(f"Page {page_num}: found {len(proxies)} proxies")
        return proxies
        
    except Exception as e:
        logger.warning(f"Error parsing proxymania page {page_num}: {e}")
        return []


def fetch_proxymania_proxies(country_filter: Optional[List[str]] = None, max_pages: int = 15) -> List[Dict]:
    """
    Fetch proxies from proxymania.su
    
    Args:
        country_filter: List of country codes to filter (None = all)
        max_pages: Maximum pages to parse
    
    Returns:
        List of proxy dicts
    """
    all_proxies = []
    
    try:
        logger.info("Fetching proxies from proxymania.su...")
        
        # Try to detect max pages
        try:
            url = f"{PROXYMANIA_BASE_URL}?page=1"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            pagination = soup.select('.pagination a, .pager a, a[href*="page="]')
            if pagination:
                page_numbers = []
                for link in pagination:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    page_match = re.search(r'page=(\d+)', href)
                    if page_match:
                        page_numbers.append(int(page_match.group(1)))
                    elif text.isdigit():
                        page_numbers.append(int(text))
                
                if page_numbers:
                    detected_max = max(page_numbers)
                    if 0 < detected_max < max_pages:
                        max_pages = detected_max
                        logger.info(f"Detected {max_pages} pages on proxymania.su")
        except Exception as e:
            logger.debug(f"Could not detect max pages, using {max_pages}: {e}")
        
        # Parse pages
        for page_num in range(1, max_pages + 1):
            try:
                proxies = parse_proxymania_page(page_num)
                if not proxies:
                    # Check next page if empty
                    if page_num < max_pages:
                        next_proxies = parse_proxymania_page(page_num + 1)
                        if not next_proxies:
                            logger.debug(f"Page {page_num + 1} also empty, stopping")
                            break
                    else:
                        break
                
                # Filter by country
                if country_filter:
                    proxies = [p for p in proxies if p.get('country', '').upper() in country_filter]
                
                all_proxies.extend(proxies)
                logger.info(f"Page {page_num}/{max_pages}: added {len(proxies)} proxies, total: {len(all_proxies)}")
                
                time.sleep(random.uniform(1, 2))
                
            except Exception as e:
                logger.warning(f"Error parsing page {page_num}: {e}")
                if page_num == 1:
                    break
                continue
        
        logger.info(f"Fetched {len(all_proxies)} proxies from proxymania.su")
        return all_proxies
        
    except Exception as e:
        logger.warning(f"Error fetching proxies from proxymania.su: {e}")
        return []


def fetch_all_proxies(country_filter: Optional[List[str]] = None) -> List[Dict]:
    """
    Fetch proxies from all sources
    
    Args:
        country_filter: List of country codes to filter (None = all from config)
    
    Returns:
        List of unique proxy dicts
    """
    if country_filter is None:
        country_filter = PROXY_COUNTRIES
    
    all_proxies = []
    
    # Fetch from Proxifly
    proxifly_proxies = fetch_proxifly_proxies(country_filter)
    all_proxies.extend(proxifly_proxies)
    
    # Fetch from proxymania
    proxymania_proxies = fetch_proxymania_proxies(country_filter)
    all_proxies.extend(proxymania_proxies)
    
    # Remove duplicates
    seen = set()
    unique_proxies = []
    for proxy in all_proxies:
        proxy_key = f"{proxy['ip']}:{proxy['port']}"
        if proxy_key not in seen:
            seen.add(proxy_key)
            unique_proxies.append(proxy)
    
    duplicates_removed = len(all_proxies) - len(unique_proxies)
    logger.info(f"Total unique proxies: {len(unique_proxies)} (removed {duplicates_removed} duplicates)")
    
    return unique_proxies

