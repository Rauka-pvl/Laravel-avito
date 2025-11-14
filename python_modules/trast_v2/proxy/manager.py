"""Proxy manager with caching and thread-safe operations"""

import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import (
    PROXY_FILE, SUCCESSFUL_PROXIES_FILE, LAST_UPDATE_FILE,
    PROXY_COUNTRIES, PROXY_SEARCH_THREADS, MAX_PROXY_ATTEMPTS_PER_THREAD
)
from proxy.sources import fetch_all_proxies
from proxy.validator import validate_proxy_for_trast
from utils.exceptions import ProxyValidationError, ProxyConnectionError

logger = get_logger("proxy.manager")


class ProxyManager:
    """Thread-safe proxy manager with caching"""
    
    def __init__(self, country_filter: Optional[List[str]] = None, cache_dir: Path = None):
        """
        Initialize ProxyManager
        
        Args:
            country_filter: List of country codes to filter (None = use config default)
            cache_dir: Cache directory (defaults to proxy_cache in module dir)
        """
        self.country_filter = country_filter or PROXY_COUNTRIES
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "proxy_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.proxies_file = self.cache_dir / "proxies.json"
        self.successful_proxies_file = self.cache_dir / "successful_proxies.json"
        self.last_update_file = self.cache_dir / "last_update.txt"
        
        self.proxies = []
        self.successful_proxies = []
        self.failed_proxies = set()
        self.current_index = 0
        
        # Thread safety
        self.lock = threading.Lock()
        self.thread_proxies = {}  # Map thread_id to proxy
        
        # Load cached data
        self.successful_proxies = self._load_successful_proxies()
        logger.info(f"Loaded {len(self.successful_proxies)} successful proxies from cache")
    
    def _load_successful_proxies(self) -> List[Dict]:
        """Load successful proxies from cache"""
        try:
            if not self.successful_proxies_file.exists():
                return []
            
            with open(self.successful_proxies_file, 'r', encoding='utf-8') as f:
                proxies = json.load(f)
            
            # Filter by country
            if self.country_filter:
                proxies = [p for p in proxies 
                          if p.get('country', '').upper() in [c.upper() for c in self.country_filter]]
            
            # Sort by last success
            proxies.sort(key=lambda p: p.get('last_success', ''), reverse=True)
            return proxies
            
        except Exception as e:
            logger.warning(f"Error loading successful proxies: {e}")
            return []
    
    def _save_successful_proxies(self):
        """Save successful proxies to cache"""
        try:
            with self.lock:
                with open(self.successful_proxies_file, 'w', encoding='utf-8') as f:
                    json.dump(self.successful_proxies, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error saving successful proxies: {e}")
    
    def download_proxies(self, force_update: bool = False) -> bool:
        """
        Download proxies from all sources
        
        Args:
            force_update: Force update even if cache is fresh
        
        Returns:
            True if successful
        """
        try:
            # Check if update needed
            if not force_update and self._should_update():
                logger.info("Proxy cache is fresh, skipping update")
                return True
            
            logger.info("Downloading proxies from all sources...")
            proxies = fetch_all_proxies(country_filter=self.country_filter)
            
            if not proxies:
                logger.warning("No proxies fetched")
                return False
            
            # Save to file
            with self.lock:
                with open(self.proxies_file, 'w', encoding='utf-8') as f:
                    json.dump(proxies, f, ensure_ascii=False, indent=2)
                
                with open(self.last_update_file, 'w') as f:
                    f.write(datetime.now().isoformat())
            
            self.proxies = proxies
            self.failed_proxies.clear()
            self.current_index = 0
            
            logger.info(f"Downloaded and saved {len(proxies)} proxies")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading proxies: {e}")
            return False
    
    def _should_update(self) -> bool:
        """Check if proxy list should be updated (older than 1 hour)"""
        try:
            if not self.last_update_file.exists():
                return True
            
            with open(self.last_update_file, 'r') as f:
                last_update_str = f.read().strip()
            
            last_update = datetime.fromisoformat(last_update_str)
            return datetime.now() - last_update > timedelta(hours=1)
            
        except Exception:
            return True
    
    def load_proxies(self) -> List[Dict]:
        """Load proxies from cache file"""
        try:
            if not self.proxies_file.exists():
                logger.warning("Proxy file not found")
                return []
            
            with open(self.proxies_file, 'r', encoding='utf-8') as f:
                proxies = json.load(f)
            
            # Filter by country
            if self.country_filter:
                proxies = [p for p in proxies 
                          if p.get('country', '').upper() in [c.upper() for c in self.country_filter]]
            
            self.proxies = proxies
            logger.info(f"Loaded {len(proxies)} proxies from cache")
            return proxies
            
        except Exception as e:
            logger.error(f"Error loading proxies: {e}")
            return []
    
    def get_proxy_for_thread(self, thread_id: int) -> Optional[Dict]:
        """
        Get a proxy for a specific thread (thread-safe)
        
        Args:
            thread_id: Thread ID
        
        Returns:
            Proxy dict or None
        """
        with self.lock:
            # Check if thread already has a proxy
            if thread_id in self.thread_proxies:
                return self.thread_proxies[thread_id]
            
            # Try successful proxies first
            if self.successful_proxies:
                proxy = self.successful_proxies[0]
                self.thread_proxies[thread_id] = proxy
                return proxy
            
            # Try regular proxies
            if not self.proxies:
                self.load_proxies()
            
            # Find next available proxy
            attempts = 0
            while attempts < len(self.proxies):
                if self.current_index >= len(self.proxies):
                    self.current_index = 0
                
                proxy = self.proxies[self.current_index]
                self.current_index += 1
                
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in self.failed_proxies:
                    self.thread_proxies[thread_id] = proxy
                    return proxy
                
                attempts += 1
            
            return None
    
    def mark_proxy_failed(self, proxy: Dict):
        """Mark proxy as failed (thread-safe)"""
        with self.lock:
            proxy_key = f"{proxy['ip']}:{proxy['port']}"
            self.failed_proxies.add(proxy_key)
            
            # Remove from successful if present
            self.successful_proxies = [
                p for p in self.successful_proxies
                if f"{p['ip']}:{p['port']}" != proxy_key
            ]
            self._save_successful_proxies()
    
    def mark_proxy_successful(self, proxy: Dict, context: Optional[Dict] = None):
        """Mark proxy as successful (thread-safe)"""
        with self.lock:
            proxy_key = f"{proxy['ip']}:{proxy['port']}"
            
            # Remove from failed
            self.failed_proxies.discard(proxy_key)
            
            # Add or update in successful
            existing = None
            for p in self.successful_proxies:
                if f"{p['ip']}:{p['port']}" == proxy_key:
                    existing = p
                    break
            
            if existing:
                existing['last_success'] = datetime.now().isoformat()
                existing['success_count'] = existing.get('success_count', 0) + 1
                if context and context.get('total_pages'):
                    existing['total_pages'] = context['total_pages']
            else:
                new_proxy = {
                    'ip': proxy['ip'],
                    'port': proxy['port'],
                    'protocol': proxy.get('protocol', 'http'),
                    'country': proxy.get('country', 'Unknown'),
                    'first_success': datetime.now().isoformat(),
                    'last_success': datetime.now().isoformat(),
                    'success_count': 1
                }
                if context and context.get('total_pages'):
                    new_proxy['total_pages'] = context['total_pages']
                self.successful_proxies.append(new_proxy)
            
            # Sort by last success
            self.successful_proxies.sort(key=lambda p: p.get('last_success', ''), reverse=True)
            self._save_successful_proxies()
    
    def get_working_proxies_parallel(
        self, 
        count: int = 3,
        max_attempts: int = None,
        callback_list: List = None,
        callback_event = None,
        callback_lock = None
    ) -> List[Dict]:
        """
        Find working proxies in parallel
        
        Args:
            count: Number of working proxies to find
            max_attempts: Max attempts per thread (defaults to config)
            callback_list: List to append found proxies to (for immediate updates)
            callback_event: Event to set when first proxy found
            callback_lock: Lock for callback_list
        
        Returns:
            List of working proxy dicts
        """
        if max_attempts is None:
            max_attempts = MAX_PROXY_ATTEMPTS_PER_THREAD
        
        if not self.proxies:
            self.load_proxies()
        
        if not self.proxies:
            logger.warning("No proxies available")
            return []
        
        working_proxies = []
        working_lock = threading.Lock()
        
        def validate_proxy_worker(proxy: Dict):
            """Worker function to validate a proxy"""
            try:
                is_valid, context = validate_proxy_for_trast(proxy)
                if is_valid:
                    with working_lock:
                        if len(working_proxies) < count:
                            working_proxies.append(proxy)
                            self.mark_proxy_successful(proxy, context)
                            
                            # Callback
                            if callback_list is not None and callback_lock is not None:
                                with callback_lock:
                                    if proxy not in callback_list:
                                        callback_list.append(proxy)
                                        if callback_event and len(callback_list) == 1:
                                            callback_event.set()
                            
                            logger.info(f"Found working proxy: {proxy['ip']}:{proxy['port']}")
                            return True
                else:
                    self.mark_proxy_failed(proxy)
                    return False
            except (ProxyValidationError, ProxyConnectionError) as e:
                logger.debug(f"Proxy validation failed: {e}")
                self.mark_proxy_failed(proxy)
                return False
            except Exception as e:
                logger.warning(f"Error validating proxy: {e}")
                return False
        
        # Use thread pool to validate proxies in parallel
        with ThreadPoolExecutor(max_workers=PROXY_SEARCH_THREADS) as executor:
            futures = []
            attempts = 0
            
            # Start with successful proxies
            for proxy in self.successful_proxies[:count]:
                if len(working_proxies) >= count:
                    break
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in self.failed_proxies:
                    future = executor.submit(validate_proxy_worker, proxy)
                    futures.append(future)
                    attempts += 1
            
            # Then try regular proxies
            for proxy in self.proxies:
                if len(working_proxies) >= count:
                    break
                if attempts >= max_attempts * PROXY_SEARCH_THREADS:
                    break
                
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                if proxy_key not in self.failed_proxies:
                    # Check if already in working
                    already_working = any(
                        f"{p['ip']}:{p['port']}" == proxy_key 
                        for p in working_proxies
                    )
                    if not already_working:
                        future = executor.submit(validate_proxy_worker, proxy)
                        futures.append(future)
                        attempts += 1
            
            # Wait for results
            for future in as_completed(futures):
                if len(working_proxies) >= count:
                    # Cancel remaining
                    for f in futures:
                        f.cancel()
                    break
        
        logger.info(f"Found {len(working_proxies)} working proxies")
        return working_proxies

