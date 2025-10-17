#!/usr/bin/env python3
"""
Улучшенная система тестирования российских прокси
"""

import asyncio
import sys
import os
import json
import random
import time
from typing import List, Dict, Optional, Tuple
import httpx

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class RussianProxyTester:
    """Тестер российских прокси с приоритетом."""
    
    def __init__(self):
        self.logger = setup_logger("russian_proxy_tester")
        self.russian_proxies = []
        self.working_proxies = []
        self.tested_count = 0
        self.max_tests = 100  # Максимум тестов за один запуск
    
    def load_russian_proxies(self) -> List[str]:
        """Загружает российские прокси из файлов."""
        self.logger.info("🇷🇺 Загружаем российские прокси...")
        
        # Ищем файлы с российскими прокси
        proxy_files = [
            "working_russian_proxies_*.json",
            "russian_proxies_*.json", 
            "working_proxies.json"
        ]
        
        all_proxies = set()
        
        for pattern in proxy_files:
            import glob
            files = glob.glob(pattern)
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                        if isinstance(data, list):
                            # Если это список прокси
                            for item in data:
                                if isinstance(item, str):
                                    all_proxies.add(item)
                                elif isinstance(item, dict) and 'proxy' in item:
                                    all_proxies.add(item['proxy'])
                        elif isinstance(data, dict):
                            # Если это объект с прокси
                            if 'proxies' in data:
                                all_proxies.update(data['proxies'])
                            elif 'russian_proxies' in data:
                                for item in data['russian_proxies']:
                                    if isinstance(item, dict) and 'proxy' in item:
                                        all_proxies.add(item['proxy'])
                    
                    self.logger.info(f"📁 Загружено из {file_path}")
                    
                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка загрузки {file_path}: {e}")
        
        self.russian_proxies = list(all_proxies)
        self.logger.info(f"🇷🇺 Загружено {len(self.russian_proxies)} российских прокси")
        
        return self.russian_proxies
    
    async def test_proxy_against_target(self, proxy: str) -> Tuple[bool, float, str]:
        """Тестирует прокси против целевого сайта."""
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
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
                        return True, response_time, "Success"
                    else:
                        return False, response_time, "Cloudflare detected"
                else:
                    return False, response_time, f"HTTP {response.status_code}"
                    
        except Exception as e:
            return False, 0, str(e)
    
    async def test_proxies_batch(self, proxies: List[str], batch_size: int = 10) -> List[Dict]:
        """Тестирует батч прокси параллельно."""
        results = []
        
        # Разбиваем на батчи
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            
            self.logger.info(f"🧪 Тестируем батч {i//batch_size + 1}: {len(batch)} прокси")
            
            # Тестируем батч параллельно
            tasks = [self.test_proxy_against_target(proxy) for proxy in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for j, result in enumerate(batch_results):
                proxy = batch[j]
                self.tested_count += 1
                
                if isinstance(result, Exception):
                    results.append({
                        'proxy': proxy,
                        'success': False,
                        'response_time': 0,
                        'error': str(result)
                    })
                else:
                    success, response_time, error = result
                    results.append({
                        'proxy': proxy,
                        'success': success,
                        'response_time': response_time,
                        'error': error
                    })
                    
                    if success:
                        self.working_proxies.append({
                            'proxy': proxy,
                            'response_time': response_time,
                            'tested_at': time.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        self.logger.info(f"✅ РАБОЧИЙ ПРОКСИ: {proxy} ({response_time:.3f}s)")
                        
                        # Если нашли рабочий прокси, можем остановиться
                        if len(self.working_proxies) >= 5:
                            self.logger.info("🎯 Найдено достаточно рабочих прокси, останавливаем тестирование")
                            break
            
            # Пауза между батчами
            if i + batch_size < len(proxies):
                await asyncio.sleep(1)
        
        return results
    
    async def find_working_proxy(self, max_tests: int = 100) -> Optional[str]:
        """Находит рабочий прокси для целевого сайта."""
        self.logger.info(f"🎯 Ищем рабочий прокси для {TrastConfig.SHOP_URL}")
        self.logger.info(f"📊 Максимум тестов: {max_tests}")
        
        # Загружаем прокси
        proxies = self.load_russian_proxies()
        
        if not proxies:
            self.logger.error("❌ Нет прокси для тестирования")
            return None
        
        # Перемешиваем прокси для случайного тестирования
        random.shuffle(proxies)
        
        # Ограничиваем количество тестов
        test_proxies = proxies[:max_tests]
        self.logger.info(f"🎲 Тестируем {len(test_proxies)} случайных прокси")
        
        # Тестируем батчами
        results = await self.test_proxies_batch(test_proxies, batch_size=20)
        
        # Анализируем результаты
        working_count = len(self.working_proxies)
        self.logger.info(f"📊 РЕЗУЛЬТАТЫ: {working_count}/{len(test_proxies)} рабочих прокси")
        
        if self.working_proxies:
            # Сортируем по скорости
            self.working_proxies.sort(key=lambda x: x['response_time'])
            best_proxy = self.working_proxies[0]['proxy']
            
            self.logger.info(f"🏆 ЛУЧШИЙ ПРОКСИ: {best_proxy}")
            return best_proxy
        else:
            self.logger.warning("❌ Рабочие прокси не найдены")
            return None
    
    def save_working_proxies(self):
        """Сохраняет рабочие прокси."""
        if not self.working_proxies:
            return
        
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем в JSON
        json_file = f"working_russian_proxies_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.working_proxies, f, indent=2, ensure_ascii=False)
        
        # Сохраняем в простом формате для парсера
        txt_file = f"working_proxies_{timestamp}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            for proxy_data in self.working_proxies:
                f.write(f"{proxy_data['proxy']}\n")
        
        # Обновляем основной файл
        with open("working_proxies.json", 'w', encoding='utf-8') as f:
            data = {
                'proxies': [p['proxy'] for p in self.working_proxies],
                'count': len(self.working_proxies),
                'timestamp': timestamp,
                'source': 'russian_proxy_tester',
                'target_site': TrastConfig.SHOP_URL
            }
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Сохранено {len(self.working_proxies)} рабочих прокси")
        self.logger.info(f"📄 Файлы: {json_file}, {txt_file}, working_proxies.json")

async def main():
    """Основная функция."""
    tester = RussianProxyTester()
    
    print("🇷🇺 ТЕСТИРОВАНИЕ РОССИЙСКИХ ПРОКСИ")
    print("=" * 50)
    
    # Ищем рабочий прокси
    working_proxy = await tester.find_working_proxy(max_tests=200)
    
    if working_proxy:
        print(f"\n🎉 НАЙДЕН РАБОЧИЙ ПРОКСИ: {working_proxy}")
        
        # Сохраняем результаты
        tester.save_working_proxies()
        
        print("\n✅ ГОТОВО!")
        print("Теперь можно запускать:")
        print("  python3 main.py")
    else:
        print("\n❌ Рабочие прокси не найдены")
        print("Попробуйте:")
        print("  1. Запустить proxy_hunter.py для поиска новых прокси")
        print("  2. Увеличить max_tests в скрипте")
        print("  3. Проверить доступность целевого сайта")

if __name__ == "__main__":
    asyncio.run(main())
