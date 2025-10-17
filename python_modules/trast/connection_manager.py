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
from proxy_manager import ProxyManager


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
            # Используем httpx для TOR, так как он поддерживает SOCKS5
            import httpx
            
            async with httpx.AsyncClient(
                proxy=TrastConfig.TOR_PROXY_URL,
                timeout=TrastConfig.CONNECTION_TIMEOUT
            ) as client:
                response = await client.get(
                    TrastConfig.TEST_URL,
                    headers=TrastConfig.get_headers_with_user_agent()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    ip_address = data.get('origin', 'unknown')
                    response_time = time.time() - start_time
                    
                    self.logger.info(f"TOR connection successful: {ip_address} ({response_time:.3f}s)")
                    
                    return ConnectionResult(
                        connection_type="tor",
                        success=True,
                        response_time=response_time,
                        proxy_config={"http": TrastConfig.TOR_PROXY_URL, "https": TrastConfig.TOR_PROXY_URL},
                        ip_address=ip_address
                    )
                else:
                    raise Exception(f"HTTP {response.status_code}")
                    
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
        self.proxy_manager = ProxyManager()
        self.proxies = self.proxy_manager.working_proxies.copy()
        self.tested_proxies = set()
    
    def _load_proxies(self) -> List[str]:
        """Load proxies from files and update working proxies."""
        # Обновляем список рабочих прокси
        self.proxy_manager.load_working_proxies()
        self.proxies = self.proxy_manager.working_proxies.copy()
        
        # Также загружаем из старых файлов для совместимости
        additional_proxies = []
        
        for proxy_file in TrastConfig.PROXY_FILES:
            if os.path.exists(proxy_file):
                try:
                    with open(proxy_file, 'r', encoding='utf-8') as f:
                        if proxy_file.endswith('.json'):
                            data = json.load(f)
                            if isinstance(data, list):
                                additional_proxies.extend(data)
                            elif isinstance(data, dict) and 'proxies' in data:
                                additional_proxies.extend(data['proxies'])
                        else:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    additional_proxies.append(line)
                    
                    self.logger.info(f"Loaded {len(additional_proxies)} additional proxies from {proxy_file}")
                except Exception as e:
                    self.logger.warning(f"Failed to load proxies from {proxy_file}: {e}")
            else:
                self.logger.warning(f"Proxy file not found: {proxy_file}")
        
        # Объединяем все прокси
        all_proxies = list(set(self.proxies + additional_proxies))
        self.logger.info(f"Total proxies available: {len(all_proxies)}")
        
        return all_proxies
    
    async def test_connection(self) -> ConnectionResult:
        """Test proxy connection with aggressive testing."""
        start_time = time.time()
        
        # Обновляем список прокси
        self.proxies = self._load_proxies()
        
        if not self.proxies:
            return ConnectionResult(
                connection_type="proxy",
                success=False,
                response_time=time.time() - start_time,
                error="No proxies available"
            )
        
        self.logger.info(f"🧪 Тестируем {len(self.proxies)} прокси агрессивно...")
        
        # Тестируем ВСЕ прокси (до 124 вместо 50)
        test_count = min(124, len(self.proxies))
        test_proxies = random.sample(self.proxies, test_count)
        
        self.logger.info(f"🎲 Тестируем {test_count} случайных прокси")
        
        # Тестируем прокси параллельно батчами
        batch_size = 10
        working_proxy = None
        
        for i in range(0, len(test_proxies), batch_size):
            batch = test_proxies[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(test_proxies) + batch_size - 1) // batch_size
            
            self.logger.info(f"📦 Батч {batch_num}/{total_batches}: тестируем {len(batch)} прокси")
            
            # Тестируем батч параллельно
            tasks = [self._test_single_proxy(proxy) for proxy in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Ищем рабочий прокси в батче
            for j, result in enumerate(batch_results):
                proxy = batch[j]
                
                if isinstance(result, Exception):
                    self.logger.debug(f"Прокси {proxy} не работает: {result}")
                    continue
                
                if result['success']:
                    working_proxy = result
                    self.logger.info(f"✅ НАЙДЕН РАБОЧИЙ ПРОКСИ: {proxy} ({result['response_time']:.3f}s)")
                    break
            
            # Если нашли рабочий прокси, останавливаемся
            if working_proxy:
                break
            
            # Пауза между батчами
            if i + batch_size < len(test_proxies):
                await asyncio.sleep(0.5)
        
        if working_proxy:
            return ConnectionResult(
                connection_type="proxy",
                success=True,
                response_time=working_proxy['response_time'],
                proxy_config={"http": working_proxy['proxy_url'], "https": working_proxy['proxy_url']},
                ip_address=working_proxy['ip_address']
            )
        else:
            # Если все прокси не сработали
            response_time = time.time() - start_time
            self.logger.warning(f"❌ Все {test_count} прокси не сработали за {response_time:.3f}s")
            
            return ConnectionResult(
                connection_type="proxy",
                success=False,
                response_time=response_time,
                error=f"All {test_count} tested proxies failed"
            )
    
    async def _test_single_proxy(self, proxy: str) -> Dict:
        """Тестирует один прокси."""
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(5.0, connect=3.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False
            ) as client:
                start_time = time.time()
                
                # Тестируем против целевого сайта
                response = await client.get(TrastConfig.SHOP_URL)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    # Проверяем, что это не Cloudflare
                    content = response.text.lower()
                    cloudflare_indicators = ['checking your browser', 'ddos protection', 'cloudflare', 'ray id']
                    
                    if not any(indicator in content for indicator in cloudflare_indicators):
                        # Получаем IP адрес
                        try:
                            ip_response = await client.get("http://httpbin.org/ip")
                            if ip_response.status_code == 200:
                                ip_data = ip_response.json()
                                ip_address = ip_data.get('origin', 'unknown')
                            else:
                                ip_address = 'unknown'
                        except:
                            ip_address = 'unknown'
                        
                        return {
                            'success': True,
                            'response_time': response_time,
                            'proxy_url': proxy_url,
                            'ip_address': ip_address
                        }
                    else:
                        return {
                            'success': False,
                            'response_time': response_time,
                            'error': 'Cloudflare detected'
                        }
                else:
                    return {
                        'success': False,
                        'response_time': response_time,
                        'error': f'HTTP {response.status_code}'
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'response_time': 0,
                'error': str(e)
            }


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
