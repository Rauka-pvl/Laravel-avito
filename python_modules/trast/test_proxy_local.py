#!/usr/bin/env python3
"""
Тест прокси локально
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from proxy_manager import ProxyManager
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_proxy():
    """Тестируем работу прокси"""
    print("=== ТЕСТ ПРОКСИ ЛОКАЛЬНО ===")
    
    # Создаем менеджер прокси
    proxy_manager = ProxyManager()
    
    # Скачиваем прокси
    print("Скачиваем прокси...")
    proxy_manager.download_proxies()
    
    # Загружаем прокси
    print("Загружаем прокси...")
    proxy_manager.load_proxies()
    
    print(f"Всего прокси: {len(proxy_manager.proxies)}")
    
    # Тестируем первые 5 прокси
    print("\nТестируем первые 5 прокси:")
    for i, proxy in enumerate(proxy_manager.proxies[:5]):
        print(f"\n{i+1}. Тестируем {proxy['ip']}:{proxy['port']} ({proxy.get('protocol', 'http')})")
        
        # Тестируем на сайте
        is_working = proxy_manager.validate_proxy_for_site(proxy, timeout=5)
        print(f"   Результат: {'РАБОТАЕТ' if is_working else 'НЕ РАБОТАЕТ'}")
        
        if is_working:
            print("   Найден рабочий прокси!")
            break
    
    print("\n=== ТЕСТ ЗАВЕРШЕН ===")

if __name__ == "__main__":
    test_proxy()
