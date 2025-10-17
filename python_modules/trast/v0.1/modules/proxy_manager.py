"""
Proxy management module for Trast parser.

Handles proxy loading, testing, rotation, and Tor integration.
"""

import json
import os
import random
import logging
import requests
from typing import List, Optional, Tuple, Dict, Union
from dataclasses import dataclass
from datetime import datetime
from .config import TrastConfig
from .warp_manager import WARPManager

logger = logging.getLogger("trast.proxy_manager")


@dataclass
class Proxy:
    """Represents a proxy server."""
    address: str
    port: int
    protocol: str = "http"
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[float] = None
    
    @property
    def full_address(self) -> str:
        """Get full proxy address."""
        return f"{self.address}:{self.port}"
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    def mark_success(self):
        """Mark proxy as successful."""
        self.success_count += 1
        self.last_used = random.random()  # Random for load balancing
    
    def mark_failure(self):
        """Mark proxy as failed."""
        self.failure_count += 1


class ProxyPool:
    """Manages a pool of proxy servers."""
    
    def __init__(self):
        self.proxies: List[Proxy] = []
        self.failed_proxies: set = set()
        self.current_index = 0
        self._load_proxies()
    
    def _load_proxies(self):
        """Load proxies from all configured files."""
        proxy_files = TrastConfig.get_proxy_file_paths()
        
        for file_path in proxy_files:
            if not os.path.exists(file_path):
                logger.warning(f"Proxy file not found: {file_path}")
                continue
                
            if file_path.endswith('.json'):
                self._load_from_json(file_path)
            elif file_path.endswith('.txt'):
                self._load_from_txt(file_path)
        
        logger.info(f"Loaded {len(self.proxies)} proxies total")
    
    def _load_from_json(self, file_path: str):
        """Load proxies from JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                proxies_data = json.load(f)
                for p in proxies_data:
                    proxy = Proxy(
                        address=p['ip_address'],
                        port=p['port'],
                        protocol="http"  # Default, will be auto-detected
                    )
                    self.proxies.append(proxy)
            logger.info(f"Loaded {len(proxies_data)} proxies from JSON")
        except Exception as e:
            logger.error(f"Error loading JSON proxies: {e}")
    
    def _load_from_txt(self, file_path: str):
        """Load proxies from TXT file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        address, port = line.split(':', 1)
                        proxy = Proxy(
                            address=address.strip(),
                            port=int(port.strip()),
                            protocol="http"  # Default, will be auto-detected
                        )
                        self.proxies.append(proxy)
            logger.info(f"Loaded proxies from TXT file")
        except Exception as e:
            logger.error(f"Error loading TXT proxies: {e}")
    
    def test_proxy(self, proxy: Proxy, timeout: int = None) -> Tuple[bool, str]:
        """Test proxy with automatic protocol detection."""
        if timeout is None:
            timeout = TrastConfig.PROXY_TEST_TIMEOUT
            
        protocols = ['http', 'https', 'socks4', 'socks5']
        
        for protocol in protocols:
            try:
                if protocol.startswith('socks'):
                    proxy_url = f"{protocol}://{proxy.full_address}"
                else:
                    proxy_url = f"{protocol}://{proxy.full_address}"
                
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                
                response = requests.get(
                    'https://httpbin.org/ip',
                    proxies=proxies,
                    timeout=timeout,
                    headers={'User-Agent': TrastConfig.get_random_user_agent()}
                )
                
                if response.status_code == 200:
                    proxy.protocol = protocol
                    logger.debug(f"Proxy {proxy.full_address} works with {protocol}")
                    return True, protocol
                    
            except Exception as e:
                logger.debug(f"Proxy {proxy.full_address} failed with {protocol}: {e}")
                continue
        
        return False, None
    
    def get_next_proxy(self, max_attempts: int = 10) -> Optional[Proxy]:
        """Get next working proxy with adaptive selection."""
        attempts = 0
        max_attempts = min(max_attempts, len(self.proxies))
        
        # Random sampling for better coverage
        random_indices = random.sample(range(len(self.proxies)), max_attempts)
        
        for idx in random_indices:
            proxy = self.proxies[idx]
            
            if proxy.full_address in self.failed_proxies:
                attempts += 1
                continue
            
            logger.info(f"Testing proxy {attempts+1}/{max_attempts}: {proxy.full_address}")
            success, protocol = self.test_proxy(proxy)
            
            if success:
                logger.info(f"✅ Using proxy: {proxy.full_address} (protocol: {protocol})")
                return proxy
            else:
                self.failed_proxies.add(proxy.full_address)
                attempts += 1
                
            if attempts >= max_attempts:
                break
        
        logger.error("❌ No working proxies found!")
        return None
    
    def mark_success(self, proxy: Proxy):
        """Mark proxy as successful."""
        proxy.mark_success()
        # Remove from failed list if it has enough successes
        if proxy.success_count > TrastConfig.PROXY_SUCCESS_THRESHOLD:
            self.failed_proxies.discard(proxy.full_address)
    
    def mark_failure(self, proxy: Proxy):
        """Mark proxy as failed."""
        proxy.mark_failure()
        self.failed_proxies.add(proxy.full_address)
    
    def get_stats(self) -> Dict:
        """Get proxy pool statistics."""
        total = len(self.proxies)
        failed = len(self.failed_proxies)
        working = total - failed
        
        return {
            'total_proxies': total,
            'working_proxies': working,
            'failed_proxies': failed,
            'success_rate': working / total if total > 0 else 0
        }


class TorManager:
    """Manages Tor connections and circuit rotation."""
    
    def __init__(self):
        self.socks_port = TrastConfig.TOR_SOCKS_PORT
        self.control_port = TrastConfig.TOR_CONTROL_PORT
        self._stem_controller = None
    
    def is_available(self) -> bool:
        """Check if Tor is available."""
        try:
            proxies = {
                'http': f'socks5://127.0.0.1:{self.socks_port}',
                'https': f'socks5://127.0.0.1:{self.socks_port}'
            }
            response = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=10)
            if response.status_code == 200:
                logger.info("✅ Tor is available")
                return True
        except Exception as e:
            logger.debug(f"Tor not available: {e}")
        return False
    
    def get_proxy_config(self) -> Dict[str, str]:
        """Get Tor proxy configuration."""
        return {
            'http': f'socks5://127.0.0.1:{self.socks_port}',
            'https': f'socks5://127.0.0.1:{self.socks_port}'
        }
    
    def rotate_circuit(self) -> bool:
        """Rotate Tor circuit to get new IP."""
        try:
            # Try to use stem library if available
            try:
                import stem
                from stem import Signal
                from stem.control import Controller
                
                with Controller.from_port(port=self.control_port) as controller:
                    controller.authenticate()
                    controller.signal(Signal.NEWNYM)
                    logger.info("🔄 Tor circuit rotated successfully")
                    return True
            except ImportError:
                logger.warning("stem library not available, using basic Tor")
                return True
            except Exception as e:
                logger.warning(f"Failed to rotate Tor circuit: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error rotating Tor circuit: {e}")
            return False
    
    def get_current_ip(self) -> Optional[str]:
        """Get current IP through Tor."""
        try:
            proxies = self.get_proxy_config()
            response = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('origin', '').split(',')[0].strip()
        except Exception as e:
            logger.debug(f"Failed to get Tor IP: {e}")
        return None


class HybridProxyStrategy:
    """Hybrid strategy combining WARP, Tor and proxy pool."""
    
    def __init__(self):
        self.proxy_pool = ProxyPool()
        self.tor_manager = TorManager()
        self.warp_manager = WARPManager()
        self.current_connection = None
        self.connection_type = None  # 'warp', 'tor', 'proxy', or None
        self.success_count = 0
        self.failure_count = 0
    
    def _test_warp_connection(self, proxy_config: Dict) -> bool:
        """Test WARP connection quickly."""
        try:
            import requests
            
            # Список сервисов для тестирования
            test_urls = [
                "https://httpbin.org/ip",
                "https://api.ipify.org?format=json",
                "https://ipinfo.io/json"
            ]
            
            for url in test_urls:
                try:
                    response = requests.get(
                        url, 
                        proxies=proxy_config, 
                        timeout=3  # Быстрый тест
                    )
                    if response.status_code == 200:
                        logger.debug(f"✅ WARP connection test passed with {url}")
                        return True
                except Exception as e:
                    logger.debug(f"❌ WARP test failed with {url}: {e}")
                    continue
            
            logger.debug("❌ All WARP connection tests failed")
            return False
            
        except Exception as e:
            logger.debug(f"❌ WARP connection test error: {e}")
            return False
    
    def get_connection(self) -> Union[Proxy, Dict]:
        """Get next connection (WARP, Tor, or proxy)."""
        # Try WARP first if available
        if self.warp_manager.is_available():
            try:
                proxy_config = self.warp_manager.get_proxy_config()
                if proxy_config:
                    # Тестируем WARP соединение
                    if self._test_warp_connection(proxy_config):
                        self.connection_type = 'warp'
                        self.current_connection = proxy_config
                        logger.info("🌐 Using WARP connection (tested)")
                        return proxy_config
                    else:
                        # Если тест не прошел, все равно попробуем использовать WARP
                        logger.warning("⚠️ WARP connection test failed, but trying WARP anyway")
                        self.connection_type = 'warp'
                        self.current_connection = proxy_config
                        logger.info("🌐 Using WARP connection (untested)")
                        return proxy_config
            except Exception as e:
                logger.warning(f"⚠️ WARP connection error: {e}, trying alternatives")
        
        # Try Tor if WARP is not available
        if self.tor_manager.is_available():
            self.connection_type = 'tor'
            self.current_connection = self.tor_manager.get_proxy_config()
            logger.info("🔗 Using Tor connection")
            return self.current_connection
        
        # Fallback to proxy pool
        proxy = self.proxy_pool.get_next_proxy()
        if proxy:
            self.connection_type = 'proxy'
            self.current_connection = proxy
            logger.info(f"🔗 Using proxy: {proxy.full_address}")
            return proxy
        
        logger.error("❌ No connections available!")
        return None
    
    def mark_success(self):
        """Mark current connection as successful."""
        if self.connection_type == 'proxy' and self.current_connection:
            self.proxy_pool.mark_success(self.current_connection)
        elif self.connection_type == 'tor':
            logger.debug("Tor connection successful")
    
    def mark_failure(self):
        """Mark current connection as failed."""
        if self.connection_type == 'proxy' and self.current_connection:
            self.proxy_pool.mark_failure(self.current_connection)
        elif self.connection_type == 'tor':
            logger.warning("Tor connection failed")
    
    def rotate_ip(self) -> bool:
        """Force IP rotation."""
        if self.connection_type == 'warp':
            logger.info("🔄 Rotating WARP IP...")
            return self.warp_manager.rotate_ip()
        elif self.connection_type == 'tor':
            return self.tor_manager.rotate_circuit()
        elif self.connection_type == 'proxy':
            # Get new proxy
            new_proxy = self.proxy_pool.get_next_proxy()
            if new_proxy:
                self.current_connection = new_proxy
                return True
        return False
    
    def get_stats(self) -> Dict:
        """Get connection statistics."""
        stats = {
            'connection_type': self.connection_type,
            'current_connection': str(self.current_connection) if self.current_connection else None,
            'tor_available': self.tor_manager.is_available(),
            'warp_available': self.warp_manager.is_available(),
            'warp_stats': self.warp_manager.get_stats(),
            'tor_ip': self.tor_manager.get_current_ip() if self.tor_manager.is_available() else None,
            'warp_ip': self.warp_manager.get_current_ip() if self.warp_manager.is_available() else None,
            'success_rate': self.success_count / (self.success_count + self.failure_count) if (self.success_count + self.failure_count) > 0 else 0
        }
        stats.update(self.proxy_pool.get_stats())
        return stats
