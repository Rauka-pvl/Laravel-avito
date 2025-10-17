#!/usr/bin/env python3
"""
Отладочная версия парсера без headless режима
"""

import sys
import os

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger
from connection_manager import ConnectionManager
from parser import TrastParser

def main():
    """Отладочная версия с видимым браузером."""
    logger = setup_logger("trast_debug")
    
    # Включаем отладочный режим
    TrastConfig.SELENIUM_HEADLESS = False
    TrastConfig.SELENIUM_DEBUG_MODE = True
    
    logger.info("🐛 Запуск в отладочном режиме (браузер будет виден)")
    logger.info(f"Headless режим: {TrastConfig.SELENIUM_HEADLESS}")
    
    try:
        # Тестируем соединения
        import asyncio
        connection_manager = ConnectionManager()
        
        logger.info("Тестируем соединения...")
        connection_results = asyncio.run(connection_manager.test_all_connections())
        best_connection = connection_manager.get_best_connection(connection_results)
        
        if not best_connection:
            logger.error("❌ Нет рабочих соединений")
            return 1
        
        logger.info(f"✅ Используем соединение: {best_connection.connection_type}")
        
        # Тестируем парсинг
        parser = TrastParser()
        logger.info("Тестируем парсинг первой страницы...")
        
        success, page_count, content = parser.parse_first_page(best_connection)
        
        if success:
            logger.info(f"✅ Успешно! Страниц: {page_count}")
            logger.info(f"Контент: {len(content)} символов")
        else:
            logger.error("❌ Парсинг не удался")
            logger.info(f"Контент: {content[:500]}...")
        
        input("Нажмите Enter для завершения...")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
