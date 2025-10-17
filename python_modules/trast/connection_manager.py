"""
Connection manager module for Trast parser.

Handles parallel testing of WARP, TOR, and proxy connections.
"""

import asyncio
import json
import os
import random
import time
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass
import aiohttp
import httpx
from config import TrastConfig
from logger_setup import LoggerMixin


@dataclass
class ConnectionResult:
    """Result of connection test."""
    connection_type: str
    success: bool
    response_time: float
    error: Optional[str] = None
    proxy_config: Optional[Dict[str, str]] = None
    ip_address: Optional[str] = None


class WARPConnection(LoggerMixin):
    """Manages WARP connection testing."""
    
    def __init__(self):
        self.proxy_urls = [
            f"socks5://{TrastConfig.WARP_SOCKS_HOST}:{port}"
            for port in TrastConfig.WARP_ALTERNATIVE_PORTS
        ]
    
    async def test_connection(self) -> ConnectionResult:
        """Test WARP connection."""
        start_time = time.time()
        
        for proxy_url in self.proxy_urls:
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=TrastConfig.CONNECTION_TIMEOUT)
                ) as session:
                    async with session.get(
                        TrastConfig.TEST_URL,
                        proxy=proxy_url,
                        headers=TrastConfig.get_headers_with_user_agent()
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            ip_address = data.get('origin', 'unknown')
                            response_time = time.time() - start_time
                            
                            self.logger.info(f"WARP connection successful: {ip_address} ({response_time:.3f}s)")
                            
                            return ConnectionResult(
                                connection_type="warp",
                                success=True,
                                response_time=response_time,
                                proxy_config={"http": proxy_url, "https": proxy_url},
                                ip_address=ip_address
                            )
            except Exception as e:
                self.logger.debug(f"WARP connection failed on {proxy_url}: {e}")
                continue
        
        response_time = time.time() - start_time
        self.logger.warning(f"WARP connection failed after {response_time:.3f}s")
        
        return ConnectionResult(
            connection_type="warp",
            success=False,
            response_time=response_time,
            error="All WARP ports failed"
        )


class TORConnection(LoggerMixin):
    """Manages TOR connection testing."""
    
    def __init__(self):
        self.proxy_url = TrastConfig.TOR_PROXY_URL
    
    async def test_connection(self) -> ConnectionResult:
        """Test TOR connection."""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TrastConfig.CONNECTION_TIMEOUT)
            ) as session:
                async with session.get(
                    TrastConfig.TEST_URL,
                    proxy=self.proxy_url,
                    headers=TrastConfig.get_headers_with_user_agent()
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        ip_address = data.get('origin', 'unknown')
                        response_time = time.time() - start_time
                        
                        self.logger.info(f"TOR connection successful: {ip_address} ({response_time:.3f}s)")
                        
                        return ConnectionResult(
                            connection_type="tor",
                            success=True,
                            response_time=response_time,
                            proxy_config={"http": self.proxy_url, "https": self.proxy_url},
                            ip_address=ip_address
                        )
                    else:
                        raise Exception(f"HTTP {response.status}")
                        
        except Exception as e:
            response_time = time.time() - start_time
            self.logger.warning(f"TOR connection failed after {response_time:.3f}s: {e}")
            
            return ConnectionResult(
                connection_type="tor",
                success=False,
                response_time=response_time,
                error=str(e)
            )


class ProxyConnection(LoggerMixin):
    """Manages proxy connection testing."""
    
    def __init__(self):
        self.proxies = self._load_proxies()
        self.tested_proxies = set()
    
    def _load_proxies(self) -> List[Dict[str, Union[str, int]]]:
        """Load proxies from files."""
        proxies = []
        
        for file_path in TrastConfig.PROXY_FILES:
            if not os.path.exists(file_path):
                self.logger.warning(f"Proxy file not found: {file_path}")
                continue
            
            try:
                if file_path.endswith('.json'):
                    proxies.extend(self._load_json_proxies(file_path))
                elif file_path.endswith('.txt'):
                    proxies.extend(self._load_txt_proxies(file_path))
            except Exception as e:
                self.logger.error(f"Error loading proxies from {file_path}: {e}")
        
        self.logger.info(f"Loaded {len(proxies)} proxies from files")
        return proxies
    
    def _load_json_proxies(self, file_path: str) -> List[Dict[str, Union[str, int]]]:
        """Load proxies from JSON file."""
        proxies = []
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for item in data:
                if 'ip_address' in item and 'port' in item:
                    proxies.append({
                        'address': item['ip_address'],
                        'port': int(item['port']),
                        'protocol': 'http'
                    })
        return proxies
    
    def _load_txt_proxies(self, file_path: str) -> List[Dict[str, Union[str, int]]]:
        """Load proxies from TXT file."""
        proxies = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    try:
                        address, port = line.split(':', 1)
                        proxies.append({
                            'address': address.strip(),
                            'port': int(port.strip()),
                            'protocol': 'http'
                        })
                    except ValueError:
                        continue
        return proxies
    
    def _get_random_proxies(self, count: int = 10) -> List[Dict[str, Union[str, int]]]:
        """Get random untested proxies."""
        untested = [p for p in self.proxies if f"{p['address']}:{p['port']}" not in self.tested_proxies]
        if not untested:
            # Reset tested proxies if all have been tested
            self.tested_proxies.clear()
            untested = self.proxies
        
        return random.sample(untested, min(count, len(untested)))
    
    async def test_connection(self) -> ConnectionResult:
        """Test proxy connections."""
        start_time = time.time()
        test_proxies = self._get_random_proxies(10)
        
        for proxy_info in test_proxies:
            proxy_key = f"{proxy_info['address']}:{proxy_info['port']}"
            self.tested_proxies.add(proxy_key)
            
            proxy_url = f"http://{proxy_info['address']}:{proxy_info['port']}"
            
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=TrastConfig.CONNECTION_TIMEOUT)
                ) as session:
                    async with session.get(
                        TrastConfig.TEST_URL,
                        proxy=proxy_url,
                        headers=TrastConfig.get_headers_with_user_agent()
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            ip_address = data.get('origin', 'unknown')
                            response_time = time.time() - start_time
                            
                            self.logger.info(f"Proxy connection successful: {proxy_key} -> {ip_address} ({response_time:.3f}s)")
                            
                            return ConnectionResult(
                                connection_type="proxy",
                                success=True,
                                response_time=response_time,
                                proxy_config={"http": proxy_url, "https": proxy_url},
                                ip_address=ip_address
                            )
            except Exception as e:
                self.logger.debug(f"Proxy {proxy_key} failed: {e}")
                continue
        
        response_time = time.time() - start_time
        self.logger.warning(f"All proxy connections failed after {response_time:.3f}s")
        
        return ConnectionResult(
            connection_type="proxy",
            success=False,
            response_time=response_time,
            error="All tested proxies failed"
        )


class ConnectionManager(LoggerMixin):
    """Manages parallel connection testing."""
    
    def __init__(self):
        self.warp_connection = WARPConnection()
        self.tor_connection = TORConnection()
        self.proxy_connection = ProxyConnection()
        self.last_successful_connection = None
    
    async def test_all_connections(self) -> List[ConnectionResult]:
        """Test all connections in parallel."""
        self.logger.info("Testing connections in parallel...")
        
        # Run all connection tests in parallel
        tasks = [
            self.warp_connection.test_connection(),
            self.tor_connection.test_connection(),
            self.proxy_connection.test_connection()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        connection_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                connection_type = ["warp", "tor", "proxy"][i]
                connection_results.append(ConnectionResult(
                    connection_type=connection_type,
                    success=False,
                    response_time=0,
                    error=str(result)
                ))
            else:
                connection_results.append(result)
        
        # Log results
        successful_connections = [r for r in connection_results if r.success]
        failed_connections = [r for r in connection_results if not r.success]
        
        self.logger.info(f"Connection test results: {len(successful_connections)} successful, {len(failed_connections)} failed")
        
        for result in successful_connections:
            self.logger.info(f"✅ {result.connection_type.upper()}: {result.ip_address} ({result.response_time:.3f}s)")
        
        for result in failed_connections:
            self.logger.warning(f"❌ {result.connection_type.upper()}: {result.error}")
        
        return connection_results
    
    def get_best_connection(self, results: List[ConnectionResult]) -> Optional[ConnectionResult]:
        """Get the best working connection."""
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            self.logger.error("No working connections found")
            return None
        
        # Sort by preference: WARP > TOR > Proxy, then by response time
        preference_order = {"warp": 1, "tor": 2, "proxy": 3}
        successful_results.sort(key=lambda x: (preference_order.get(x.connection_type, 4), x.response_time))
        
        best_connection = successful_results[0]
        self.last_successful_connection = best_connection
        
        self.logger.info(f"Selected best connection: {best_connection.connection_type.upper()} ({best_connection.response_time:.3f}s)")
        
        return best_connection
    
    def get_connection_for_requests(self, connection_result: ConnectionResult) -> Dict[str, str]:
        """Get connection config for requests library."""
        if not connection_result or not connection_result.success:
            return {}
        
        return connection_result.proxy_config or {}
    
    def get_connection_for_httpx(self, connection_result: ConnectionResult) -> Dict[str, str]:
        """Get connection config for httpx library."""
        if not connection_result or not connection_result.success:
            return {}
        
        return connection_result.proxy_config or {}
    
    def get_connection_for_selenium(self, connection_result: ConnectionResult) -> Optional[str]:
        """Get connection config for Selenium."""
        if not connection_result or not connection_result.success:
            return None
        
        if connection_result.proxy_config:
            # Extract proxy URL for Selenium
            proxy_url = connection_result.proxy_config.get('http', '')
            if proxy_url.startswith('socks5://'):
                return proxy_url
            elif proxy_url.startswith('http://'):
                return proxy_url
        
        return None
    
    async def test_single_connection(self, connection_type: str) -> ConnectionResult:
        """Test a single connection type."""
        if connection_type == "warp":
            return await self.warp_connection.test_connection()
        elif connection_type == "tor":
            return await self.tor_connection.test_connection()
        elif connection_type == "proxy":
            return await self.proxy_connection.test_connection()
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")
