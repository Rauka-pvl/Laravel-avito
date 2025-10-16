#!/usr/bin/env python3
"""
Быстрый тест WARP соединения
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.warp_manager import WARPManager
import logging

logging.basicConfig(level=logging.INFO)

def test_warp():
    """Тестируем WARP соединение."""
    print("🧪 Тестирование WARP соединения...")
    
    warp = WARPManager()
    
    # Проверяем доступность
    print(f"📡 WARP доступен: {warp.is_available()}")
    
    if warp.is_available():
        # Получаем конфигурацию прокси
        proxy_config = warp.get_proxy_config()
        print(f"🔧 Конфигурация прокси: {proxy_config}")
        
        # Тестируем соединение
        if proxy_config:
            print("🌐 Тестируем соединение...")
            ip = warp.get_current_ip()
            print(f"🌍 Текущий IP: {ip}")
            
            if ip:
                print("✅ WARP работает корректно!")
            else:
                print("❌ Не удалось получить IP через WARP")
        else:
            print("❌ Не удалось получить конфигурацию прокси")
    else:
        print("❌ WARP недоступен")

if __name__ == "__main__":
    test_warp()
