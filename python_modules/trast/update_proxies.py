#!/usr/bin/env python3
"""
Скрипт для обновления списка рабочих прокси
"""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from proxy_manager import ProxyManager
from logger_setup import setup_logger

async def main():
    """Основная функция для обновления прокси."""
    logger = setup_logger("proxy_updater")
    
    logger.info("🔄 Начинаем обновление списка прокси...")
    
    manager = ProxyManager()
    
    # Обновляем прокси
    count = await manager.update_working_proxies(max_proxies=100)
    
    # Выводим статистику
    manager.print_proxy_stats()
    
    logger.info(f"✅ Обновление завершено! Рабочих прокси: {count}")
    
    if count == 0:
        logger.warning("⚠️ Не найдено рабочих прокси. Проверьте интернет-соединение.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
