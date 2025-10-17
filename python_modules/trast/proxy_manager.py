#!/usr/bin/env python3
"""
Модуль для работы с публичными прокси
Получает, проверяет и сохраняет рабочие прокси
"""

import asyncio
import json
import os
import random
import time
from typing import List, Dict, Set, Optional, Tuple
import aiohttp
import httpx
from dataclasses import dataclass

from config import TrastConfig
from logger_setup import LoggerMixin


@dataclass
class ProxyResult:
    """Результат проверки прокси."""
    proxy: str
    success: bool
    response_time: float
    ip_address: Optional[str] = None
    error: Optional[str] = None


class ProxyManager(LoggerMixin):
    """Менеджер для работы с публичными прокси."""
    
    def __init__(self):
        self.working_proxies_file = os.path.join(TrastConfig.SCRIPT_DIR, "working_proxies.json")
        self.proxy_sources = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1500&country=all",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
            "https://openproxylist.xyz/http.txt",
            "https://www.proxy-list.download/api/v1/get?type=http",
            "http://spys.me/proxy.txt",
        ]
        self.working_proxies: List[str] = []
        self.load_working_proxies()
    
    def load_working_proxies(self):
        """Загружает рабочие прокси из файла."""
        try:
            if os.path.exists(self.working_proxies_file):
                with open(self.working_proxies_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.working_proxies = data.get('proxies', [])
                    self.logger.info(f"📁 Загружено {len(self.working_proxies)} рабочих прокси из файла")
            else:
                self.logger.info("📁 Файл с рабочими прокси не найден, начнем с пустого списка")
        except Exception as e:
            self.logger.warning(f"⚠️ Ошибка загрузки рабочих прокси: {e}")
            self.working_proxies = []
    
    def save_working_proxies(self):
        """Сохраняет рабочие прокси в файл."""
        try:
            data = {
                'proxies': self.working_proxies,
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(self.working_proxies)
            }
            with open(self.working_proxies_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"💾 Сохранено {len(self.working_proxies)} рабочих прокси в файл")
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения рабочих прокси: {e}")
    
    async def fetch_proxies_from_sources(self) -> Set[str]:
        """Получает прокси из всех источников."""
        all_proxies = set()
        
        self.logger.info(f"🌐 Получаем прокси из {len(self.proxy_sources)} источников...")
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            tasks = []
            for source in self.proxy_sources:
                task = self._fetch_from_source(session, source)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.warning(f"❌ Источник {self.proxy_sources[i]}: {result}")
                else:
                    all_proxies.update(result)
                    self.logger.info(f"✅ Источник {self.proxy_sources[i]}: {len(result)} прокси")
        
        self.logger.info(f"📊 Всего получено {len(all_proxies)} уникальных прокси")
        return all_proxies
    
    async def _fetch_from_source(self, session: aiohttp.ClientSession, url: str) -> Set[str]:
        """Получает прокси из одного источника."""
        proxies = set()
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    
                    # Парсим разные форматы
                    for line in text.splitlines():
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        # Проверяем формат IP:PORT
                        if ':' in line and not line.startswith('http'):
                            parts = line.split(':')
                            if len(parts) == 2:
                                try:
                                    ip, port = parts[0], int(parts[1])
                                    if 1 <= port <= 65535:
                                        proxies.add(f"{ip}:{port}")
                                except ValueError:
                                    continue
                    
                    self.logger.debug(f"📥 {url}: найдено {len(proxies)} прокси")
                else:
                    self.logger.warning(f"⚠️ {url}: HTTP {response.status}")
                    
        except Exception as e:
            self.logger.debug(f"❌ {url}: {e}")
        
        return proxies
    
    async def test_proxy(self, proxy: str) -> ProxyResult:
        """Тестирует один прокси."""
        start_time = time.time()
        
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=10,
                headers=TrastConfig.get_headers_with_user_agent()
            ) as client:
                response = await client.get(TrastConfig.TEST_URL)
                
                if response.status_code == 200:
                    data = response.json()
                    ip_address = data.get('origin', 'unknown')
                    response_time = time.time() - start_time
                    
                    return ProxyResult(
                        proxy=proxy,
                        success=True,
                        response_time=response_time,
                        ip_address=ip_address
                    )
                else:
                    return ProxyResult(
                        proxy=proxy,
                        success=False,
                        response_time=time.time() - start_time,
                        error=f"HTTP {response.status_code}"
                    )
                    
        except Exception as e:
            return ProxyResult(
                proxy=proxy,
                success=False,
                response_time=time.time() - start_time,
                error=str(e)
            )
    
    async def test_proxies_batch(self, proxies: List[str], batch_size: int = 50) -> List[ProxyResult]:
        """Тестирует прокси батчами."""
        self.logger.info(f"🧪 Тестируем {len(proxies)} прокси батчами по {batch_size}...")
        
        all_results = []
        
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            self.logger.info(f"📦 Тестируем батч {i//batch_size + 1}/{(len(proxies) + batch_size - 1)//batch_size} ({len(batch)} прокси)")
            
            tasks = [self.test_proxy(proxy) for proxy in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    self.logger.warning(f"❌ Ошибка тестирования прокси: {result}")
                else:
                    all_results.append(result)
            
            # Небольшая пауза между батчами
            if i + batch_size < len(proxies):
                await asyncio.sleep(1)
        
        return all_results
    
    async def update_working_proxies(self, max_proxies: int = 100) -> int:
        """Обновляет список рабочих прокси."""
        self.logger.info("🔄 Обновляем список рабочих прокси...")
        
        # Получаем прокси из источников
        all_proxies = await self.fetch_proxies_from_sources()
        
        if not all_proxies:
            self.logger.warning("⚠️ Не удалось получить прокси из источников")
            return len(self.working_proxies)
        
        # Добавляем уже рабочие прокси
        all_proxies.update(self.working_proxies)
        
        # Конвертируем в список и перемешиваем
        proxies_list = list(all_proxies)
        random.shuffle(proxies_list)
        
        # Ограничиваем количество для тестирования
        if len(proxies_list) > max_proxies * 2:
            proxies_list = proxies_list[:max_proxies * 2]
            self.logger.info(f"📊 Ограничили тестирование до {len(proxies_list)} прокси")
        
        # Тестируем прокси
        results = await self.test_proxies_batch(proxies_list)
        
        # Фильтруем рабочие прокси
        working_results = [r for r in results if r.success]
        
        # Сортируем по времени отклика
        working_results.sort(key=lambda x: x.response_time)
        
        # Обновляем список рабочих прокси
        self.working_proxies = [r.proxy for r in working_results[:max_proxies]]
        
        # Сохраняем в файл
        self.save_working_proxies()
        
        self.logger.info(f"✅ Обновлено {len(self.working_proxies)} рабочих прокси")
        
        # Выводим статистику
        if working_results:
            fastest = working_results[0]
            slowest = working_results[-1]
            avg_time = sum(r.response_time for r in working_results) / len(working_results)
            
            self.logger.info(f"📊 Статистика рабочих прокси:")
            self.logger.info(f"   🏃 Самый быстрый: {fastest.proxy} ({fastest.response_time:.3f}s)")
            self.logger.info(f"   🐌 Самый медленный: {slowest.proxy} ({slowest.response_time:.3f}s)")
            self.logger.info(f"   ⚡ Среднее время: {avg_time:.3f}s")
        
        return len(self.working_proxies)
    
    def get_random_proxy(self) -> Optional[str]:
        """Возвращает случайный рабочий прокси."""
        if self.working_proxies:
            return random.choice(self.working_proxies)
        return None
    
    def get_proxy_config(self, proxy: str) -> Dict[str, str]:
        """Возвращает конфигурацию прокси для requests/httpx."""
        return {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
    
    def get_proxy_count(self) -> int:
        """Возвращает количество рабочих прокси."""
        return len(self.working_proxies)
    
    def print_proxy_stats(self):
        """Выводит статистику прокси."""
        self.logger.info(f"📊 Статистика прокси:")
        self.logger.info(f"   🔢 Всего рабочих прокси: {len(self.working_proxies)}")
        if self.working_proxies:
            self.logger.info(f"   🎲 Примеры прокси: {', '.join(self.working_proxies[:5])}")
            if len(self.working_proxies) > 5:
                self.logger.info(f"   ... и еще {len(self.working_proxies) - 5} прокси")


async def main():
    """Тестовая функция."""
    manager = ProxyManager()
    
    # Обновляем прокси
    count = await manager.update_working_proxies(max_proxies=50)
    
    # Выводим статистику
    manager.print_proxy_stats()
    
    # Тестируем случайный прокси
    proxy = manager.get_random_proxy()
    if proxy:
        print(f"\n🎲 Тестируем случайный прокси: {proxy}")
        result = await manager.test_proxy(proxy)
        if result.success:
            print(f"✅ Прокси работает! IP: {result.ip_address}, время: {result.response_time:.3f}s")
        else:
            print(f"❌ Прокси не работает: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
