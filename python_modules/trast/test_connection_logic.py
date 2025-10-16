#!/usr/bin/env python3
"""
Тест логики соединений
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
from modules.proxy_manager import HybridProxyStrategy

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_connections")

def test_connection_logic():
    """Тестируем логику соединений."""
    print("🧪 Тестирование логики соединений...")
    
    try:
        # Инициализируем стратегию
        strategy = HybridProxyStrategy()
        
        print("1️⃣ Проверяем доступность WARP...")
        warp_available = strategy.warp_manager.is_available()
        print(f"WARP доступен: {warp_available}")
        
        if warp_available:
            print("2️⃣ Получаем конфигурацию WARP...")
            proxy_config = strategy.warp_manager.get_proxy_config()
            print(f"Конфигурация WARP: {proxy_config}")
            
            if proxy_config:
                print("3️⃣ Тестируем WARP соединение...")
                test_result = strategy._test_warp_connection(proxy_config)
                print(f"Тест WARP: {test_result}")
        
        print("4️⃣ Получаем соединение...")
        connection = strategy.get_connection()
        print(f"Тип соединения: {strategy.connection_type}")
        print(f"Соединение: {connection}")
        
        print("5️⃣ Статистика...")
        stats = strategy.get_stats()
        print(f"Статистика: {stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    test_connection_logic()
