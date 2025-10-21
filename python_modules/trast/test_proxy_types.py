#!/usr/bin/env python3
"""
Тестовый скрипт для диагностики каждого типа прокси
Проверяет HTTP, HTTPS, SOCKS4, SOCKS5 прокси отдельно
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))

from proxy_manager import ProxyManager
import logging
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_proxy_types():
    """Тестирует каждый тип прокси отдельно"""
    print("=== ДИАГНОСТИКА ПРОКСИ ПО ТИПАМ ===")
    
    proxy_manager = ProxyManager()
    
    print("Скачиваем свежие прокси...")
    proxy_manager.download_proxies()
    
    print("Загружаем прокси...")
    proxy_manager.load_proxies()
    
    print(f"Всего прокси загружено: {len(proxy_manager.proxies)}")
    
    # Статистика по типам
    protocol_stats = {}
    for proxy in proxy_manager.proxies:
        protocol = proxy.get('protocol', 'http').lower()
        protocol_stats[protocol] = protocol_stats.get(protocol, 0) + 1
    
    print("\nСтатистика прокси по типам:")
    for protocol, count in protocol_stats.items():
        print(f"  {protocol.upper()}: {count} прокси")
    
    # Тестируем каждый тип отдельно
    test_site = "https://trast-zapchast.ru/shop/"
    
    for protocol in ['http', 'https', 'socks4', 'socks5']:
        print(f"\n{'='*50}")
        print(f"ТЕСТИРУЕМ {protocol.upper()} ПРОКСИ")
        print(f"{'='*50}")
        
        # Берем первые 10 прокси этого типа
        proxies_of_type = [p for p in proxy_manager.proxies if p.get('protocol', '').lower() == protocol][:10]
        
        if not proxies_of_type:
            print(f"Нет прокси типа {protocol.upper()}")
            continue
            
        print(f"Тестируем {len(proxies_of_type)} прокси типа {protocol.upper()}:")
        
        working_count = 0
        for i, proxy in enumerate(proxies_of_type):
            print(f"\n{i+1}. {proxy['ip']}:{proxy['port']} ({proxy.get('country', 'Unknown')})")
            
            start_time = time.time()
            result = proxy_manager.validate_proxy_for_site(proxy, test_site, timeout=20)
            end_time = time.time()
            
            status = "✅ РАБОТАЕТ" if result else "❌ НЕ РАБОТАЕТ"
            duration = f"{end_time - start_time:.1f}с"
            
            print(f"   Результат: {status} (время: {duration})")
            
            if result:
                working_count += 1
                print(f"   🎉 НАЙДЕН РАБОЧИЙ ПРОКСИ!")
                print(f"   📍 Прокси успешно подключен и работает!")
                break  # Прерываем после первого рабочего
        
        print(f"\nИтого рабочих {protocol.upper()} прокси: {working_count}/{len(proxies_of_type)}")
        
        if working_count > 0:
            print(f"✅ {protocol.upper()} прокси РАБОТАЮТ!")
        else:
            print(f"❌ {protocol.upper()} прокси НЕ РАБОТАЮТ")
    
    print(f"\n{'='*50}")
    print("ДИАГНОСТИКА ЗАВЕРШЕНА")
    print(f"{'='*50}")

if __name__ == "__main__":
    test_proxy_types()
