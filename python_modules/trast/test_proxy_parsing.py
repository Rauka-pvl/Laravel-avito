#!/usr/bin/env python3
"""
Тестовый скрипт для проверки парсинга прокси
"""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from proxy_manager import ProxyManager
from logger_setup import setup_logger

async def test_proxy_parsing():
    """Тестирует парсинг прокси из разных источников."""
    logger = setup_logger("proxy_test")
    
    logger.info("🧪 Тестируем парсинг прокси из разных источников...")
    
    manager = ProxyManager()
    
    # Тестируем каждый источник отдельно
    for i, source in enumerate(manager.proxy_sources):
        logger.info(f"\n📡 Тестируем источник {i+1}/{len(manager.proxy_sources)}: {source}")
        
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                proxies = await manager._fetch_from_source(session, source)
                logger.info(f"✅ Найдено {len(proxies)} прокси")
                
                if proxies:
                    # Показываем первые 5 прокси
                    sample_proxies = list(proxies)[:5]
                    logger.info(f"📋 Примеры: {', '.join(sample_proxies)}")
                    
                    # Тестируем первый прокси
                    if sample_proxies:
                        test_proxy = sample_proxies[0]
                        logger.info(f"🔍 Тестируем прокси: {test_proxy}")
                        result = await manager.test_proxy(test_proxy)
                        
                        if result.success:
                            logger.info(f"✅ Прокси работает! IP: {result.ip_address}, время: {result.response_time:.3f}s")
                        else:
                            logger.warning(f"❌ Прокси не работает: {result.error}")
                else:
                    logger.warning("⚠️ Прокси не найдены")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования источника: {e}")
    
    logger.info("\n🎯 Тест завершен!")

async def main():
    """Основная функция."""
    await test_proxy_parsing()

if __name__ == "__main__":
    asyncio.run(main())
