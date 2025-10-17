#!/usr/bin/env python3
"""
Детальное тестирование прокси с диагностикой
"""

import asyncio
import sys
import os
import random

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from proxy_manager import ProxyManager
from logger_setup import setup_logger

async def test_proxy_detailed(proxy: str):
    """Детальное тестирование одного прокси."""
    logger = setup_logger("proxy_test")
    
    logger.info(f"🔍 Детальное тестирование прокси: {proxy}")
    
    # Тестируем разные URL
    test_urls = [
        "http://httpbin.org/ip",
        "http://ip-api.com/json",
        "https://api.ipify.org?format=json",
        "http://icanhazip.com"
    ]
    
    proxy_url = f"http://{proxy}"
    
    for url in test_urls:
        try:
            import httpx
            
            logger.info(f"🌐 Тестируем {url}...")
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                follow_redirects=True,
                verify=False
            ) as client:
                response = await client.get(url)
                
                logger.info(f"📊 Статус: {response.status_code}")
                logger.info(f"📊 Время ответа: {response.elapsed.total_seconds():.3f}s")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.info(f"✅ JSON ответ: {data}")
                    except:
                        text = response.text[:200]
                        logger.info(f"✅ Текстовый ответ: {text}")
                    
                    logger.info(f"🎉 Прокси {proxy} работает с {url}!")
                    return True
                else:
                    logger.warning(f"❌ Статус {response.status_code} для {url}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка с {url}: {e}")
    
    logger.error(f"💀 Прокси {proxy} не работает ни с одним URL")
    return False

async def test_random_proxies():
    """Тестирует случайные прокси из списка."""
    logger = setup_logger("proxy_test")
    
    logger.info("🎲 Тестируем случайные прокси...")
    
    manager = ProxyManager()
    
    # Получаем прокси из источников
    all_proxies = await manager.fetch_proxies_from_sources()
    
    if not all_proxies:
        logger.error("❌ Не удалось получить прокси")
        return
    
    logger.info(f"📊 Получено {len(all_proxies)} прокси")
    
    # Тестируем 10 случайных прокси
    test_proxies = random.sample(list(all_proxies), min(10, len(all_proxies)))
    
    working_count = 0
    for i, proxy in enumerate(test_proxies):
        logger.info(f"\n--- Тест {i+1}/10 ---")
        if await test_proxy_detailed(proxy):
            working_count += 1
    
    logger.info(f"\n📊 Результат: {working_count}/{len(test_proxies)} прокси работают")
    
    if working_count == 0:
        logger.warning("⚠️ Ни один прокси не работает. Возможные причины:")
        logger.warning("   - Все прокси мертвые")
        logger.warning("   - Проблемы с сетью")
        logger.warning("   - Слишком строгие таймауты")
        logger.warning("   - Блокировка по IP")

async def main():
    """Основная функция."""
    await test_random_proxies()

if __name__ == "__main__":
    asyncio.run(main())
