#!/usr/bin/env python3
"""
Быстрое тестирование найденных прокси
"""

import asyncio
import sys
import os
import json
import random
from typing import List, Dict

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logger_setup import setup_logger

async def test_proxy_fast(proxy: str) -> Dict:
    """Быстрое тестирование прокси."""
    import time
    start_time = time.time()
    
    try:
        import httpx
        
        proxy_url = f"http://{proxy}"
        
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(2.0, connect=1.0),  # Очень быстрые таймауты
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            verify=False
        ) as client:
            response = await client.get("http://httpbin.org/ip")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    ip_address = data.get('origin', 'unknown')
                except:
                    ip_address = 'unknown'
                
                return {
                    'proxy': proxy,
                    'success': True,
                    'ip_address': ip_address,
                    'response_time': time.time() - start_time
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

async def test_proxies_from_file(filename: str, max_test: int = 50):
    """Тестирует прокси из файла."""
    logger = setup_logger("proxy_tester")
    
    logger.info(f"🧪 Тестируем прокси из файла: {filename}")
    
    # Читаем прокси из файла
    proxies = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    proxies.append(line)
        
        logger.info(f"📊 Загружено {len(proxies)} прокси из файла")
        
        if not proxies:
            logger.error("❌ Файл пустой или не содержит прокси")
            return
        
        # Тестируем случайные прокси
        test_proxies = random.sample(proxies, min(max_test, len(proxies)))
        logger.info(f"🎲 Тестируем {len(test_proxies)} случайных прокси")
        
        # Тестируем параллельно
        tasks = [test_proxy_fast(proxy) for proxy in test_proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        working_proxies = []
        failed_proxies = []
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"❌ Ошибка тестирования: {result}")
            elif result['success']:
                working_proxies.append(result)
                logger.info(f"✅ {result['proxy']} - {result['response_time']:.3f}s - {result['ip_address']}")
            else:
                failed_proxies.append(result)
                logger.debug(f"❌ {result['proxy']} - {result['error']}")
        
        # Статистика
        logger.info(f"\n📊 РЕЗУЛЬТАТЫ:")
        logger.info(f"   ✅ Рабочих: {len(working_proxies)}")
        logger.info(f"   ❌ Не рабочих: {len(failed_proxies)}")
        logger.info(f"   📈 Процент успеха: {len(working_proxies)/len(test_proxies)*100:.1f}%")
        
        if working_proxies:
            # Сохраняем рабочие прокси
            output_file = f"verified_proxies_{len(working_proxies)}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                for proxy_data in working_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            logger.info(f"💾 Сохранено {len(working_proxies)} рабочих прокси в {output_file}")
            
            # Показываем топ-5
            sorted_proxies = sorted(working_proxies, key=lambda x: x['response_time'])
            logger.info(f"🏆 ТОП-5 САМЫХ БЫСТРЫХ:")
            for i, proxy_data in enumerate(sorted_proxies[:5]):
                logger.info(f"   {i+1}. {proxy_data['proxy']} - {proxy_data['response_time']:.3f}s")
        
    except FileNotFoundError:
        logger.error(f"❌ Файл {filename} не найден")
    except Exception as e:
        logger.error(f"❌ Ошибка чтения файла: {e}")

async def main():
    """Основная функция."""
    if len(sys.argv) < 2:
        print("Использование: python3 test_proxies_fast.py <файл_с_прокси> [количество_тестов]")
        print("Пример: python3 test_proxies_fast.py proxies.txt 100")
        return
    
    filename = sys.argv[1]
    max_test = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    
    await test_proxies_from_file(filename, max_test)

if __name__ == "__main__":
    asyncio.run(main())
