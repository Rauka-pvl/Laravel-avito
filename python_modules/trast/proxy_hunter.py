#!/usr/bin/env python3
"""
Мощный скрипт для поиска рабочих прокси
Запускается с локальной машины для поиска и тестирования прокси
"""

import asyncio
import sys
import os
import json
import time
import random
from datetime import datetime
from typing import List, Set, Dict
import aiohttp
import httpx

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from proxy_manager import ProxyManager
from logger_setup import setup_logger

class ProxyHunter:
    """Охотник за прокси - мощный поиск и тестирование."""
    
    def __init__(self):
        self.logger = setup_logger("proxy_hunter")
        self.working_proxies = []
        self.test_results = []
        self.stats = {
            'total_found': 0,
            'total_tested': 0,
            'working_found': 0,
            'start_time': time.time()
        }
    
    async def hunt_proxies(self, max_working: int = 100):
        """Основная функция охоты за прокси."""
        self.logger.info("🎯 НАЧИНАЕМ ОХОТУ ЗА ПРОКСИ!")
        self.logger.info("=" * 50)
        
        # Получаем прокси из всех источников
        all_proxies = await self.fetch_all_proxies()
        self.stats['total_found'] = len(all_proxies)
        
        if not all_proxies:
            self.logger.error("❌ Не удалось получить прокси из источников")
            return
        
        self.logger.info(f"📊 Получено {len(all_proxies)} прокси из источников")
        
        # Тестируем прокси агрессивно
        await self.test_proxies_aggressively(all_proxies, max_working)
        
        # Сохраняем результаты
        await self.save_results()
        
        # Выводим финальную статистику
        self.print_final_stats()
    
    async def fetch_all_proxies(self) -> Set[str]:
        """Получает прокси из всех источников."""
        manager = ProxyManager()
        return await manager.fetch_proxies_from_sources()
    
    async def test_proxies_aggressively(self, proxies: List[str], max_working: int):
        """Агрессивное тестирование прокси."""
        self.logger.info(f"🔥 АГРЕССИВНОЕ ТЕСТИРОВАНИЕ {len(proxies)} ПРОКСИ")
        
        # Перемешиваем прокси
        proxies_list = list(proxies)
        random.shuffle(proxies_list)
        
        # Тестируем большими батчами
        batch_size = 200
        tested_count = 0
        
        for i in range(0, len(proxies_list), batch_size):
            batch = proxies_list[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(proxies_list) + batch_size - 1) // batch_size
            
            self.logger.info(f"📦 БАТЧ {batch_num}/{total_batches}: тестируем {len(batch)} прокси")
            
            # Тестируем батч
            batch_results = await self.test_batch_aggressive(batch)
            
            # Подсчитываем результаты
            batch_working = [r for r in batch_results if r['success']]
            self.working_proxies.extend(batch_working)
            self.test_results.extend(batch_results)
            
            tested_count += len(batch)
            self.stats['total_tested'] = tested_count
            self.stats['working_found'] = len(self.working_proxies)
            
            self.logger.info(f"✅ Батч {batch_num}: {len(batch_working)}/{len(batch)} рабочих")
            self.logger.info(f"📊 Всего найдено: {len(self.working_proxies)} рабочих прокси")
            
            # Если нашли достаточно - останавливаемся
            if len(self.working_proxies) >= max_working:
                self.logger.info(f"🎯 ДОСТИГНУТ ЛИМИТ! Найдено {len(self.working_proxies)} рабочих прокси")
                break
            
            # Небольшая пауза между батчами
            await asyncio.sleep(1)
    
    async def test_batch_aggressive(self, proxies: List[str]) -> List[Dict]:
        """Агрессивное тестирование батча прокси."""
        results = []
        
        # Создаем задачи для параллельного тестирования
        tasks = []
        for proxy in proxies:
            task = self.test_proxy_aggressive(proxy)
            tasks.append(task)
        
        # Выполняем все задачи параллельно
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                results.append({
                    'proxy': proxies[i],
                    'success': False,
                    'error': str(result),
                    'response_time': 0
                })
            else:
                results.append(result)
        
        return results
    
    async def test_proxy_aggressive(self, proxy: str) -> Dict:
        """Агрессивное тестирование одного прокси."""
        start_time = time.time()
        
        try:
            proxy_url = f"http://{proxy}"
            
            # Очень мягкие настройки
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(3.0, connect=2.0),  # Очень быстрые таймауты
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                follow_redirects=True,
                verify=False
            ) as client:
                # Пробуем простой запрос
                response = await client.get("http://httpbin.org/ip")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        ip_address = data.get('origin', 'unknown')
                    except:
                        ip_address = 'unknown'
                    
                    response_time = time.time() - start_time
                    
                    return {
                        'proxy': proxy,
                        'success': True,
                        'ip_address': ip_address,
                        'response_time': response_time,
                        'error': None
                    }
                else:
                    return {
                        'proxy': proxy,
                        'success': False,
                        'error': f"HTTP {response.status_code}",
                        'response_time': time.time() - start_time
                    }
                    
        except Exception as e:
            return {
                'proxy': proxy,
                'success': False,
                'error': str(e),
                'response_time': time.time() - start_time
            }
    
    async def save_results(self):
        """Сохраняет результаты в файлы."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем рабочие прокси
        working_file = f"working_proxies_{timestamp}.json"
        working_data = {
            'proxies': [p['proxy'] for p in self.working_proxies],
            'count': len(self.working_proxies),
            'timestamp': timestamp,
            'stats': self.stats
        }
        
        with open(working_file, 'w', encoding='utf-8') as f:
            json.dump(working_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Сохранено {len(self.working_proxies)} рабочих прокси в {working_file}")
        
        # Сохраняем детальные результаты
        detailed_file = f"proxy_test_results_{timestamp}.json"
        detailed_data = {
            'test_results': self.test_results,
            'working_proxies': self.working_proxies,
            'stats': self.stats,
            'timestamp': timestamp
        }
        
        with open(detailed_file, 'w', encoding='utf-8') as f:
            json.dump(detailed_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"📊 Сохранены детальные результаты в {detailed_file}")
        
        # Создаем простой текстовый файл для сервера
        txt_file = f"proxies_for_server_{timestamp}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            for proxy_data in self.working_proxies:
                f.write(f"{proxy_data['proxy']}\n")
        
        self.logger.info(f"📄 Создан текстовый файл для сервера: {txt_file}")
    
    def print_final_stats(self):
        """Выводит финальную статистику."""
        duration = time.time() - self.stats['start_time']
        
        self.logger.info("=" * 50)
        self.logger.info("🎉 ОХОТА ЗА ПРОКСИ ЗАВЕРШЕНА!")
        self.logger.info("=" * 50)
        self.logger.info(f"📊 Статистика:")
        self.logger.info(f"   🔍 Найдено прокси: {self.stats['total_found']}")
        self.logger.info(f"   🧪 Протестировано: {self.stats['total_tested']}")
        self.logger.info(f"   ✅ Рабочих найдено: {self.stats['working_found']}")
        self.logger.info(f"   ⏱️ Время работы: {duration:.1f} секунд")
        
        if self.working_proxies:
            # Показываем лучшие прокси
            sorted_proxies = sorted(self.working_proxies, key=lambda x: x['response_time'])
            self.logger.info(f"🏆 ТОП-10 САМЫХ БЫСТРЫХ ПРОКСИ:")
            for i, proxy_data in enumerate(sorted_proxies[:10]):
                self.logger.info(f"   {i+1}. {proxy_data['proxy']} - {proxy_data['response_time']:.3f}s - {proxy_data['ip_address']}")
        
        self.logger.info("=" * 50)

async def main():
    """Основная функция."""
    hunter = ProxyHunter()
    
    # Запускаем охоту за прокси
    await hunter.hunt_proxies(max_working=200)  # Ищем до 200 рабочих прокси

if __name__ == "__main__":
    print("🎯 ЗАПУСК МОЩНОГО ПОИСКА ПРОКСИ!")
    print("Этот скрипт будет работать долго и найдет много рабочих прокси.")
    print("Нажмите Ctrl+C для остановки.")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Поиск остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
