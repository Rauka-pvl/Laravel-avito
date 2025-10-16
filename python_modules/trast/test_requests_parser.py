#!/usr/bin/env python3
"""
Альтернативный парсер без браузера для тестирования
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
import time
import logging
from modules.config import TrastConfig
from modules.proxy_manager import HybridProxyStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_parser")

def test_requests_parsing():
    """Тестируем парсинг через requests."""
    print("🧪 Тестирование парсинга через requests...")
    
    try:
        # Инициализируем стратегию прокси
        proxy_strategy = HybridProxyStrategy()
        
        # Получаем соединение
        connection = proxy_strategy.get_connection()
        if not connection:
            print("❌ Нет доступных соединений")
            return False
        
        print(f"🔗 Используем соединение: {proxy_strategy.connection_type}")
        
        # Настраиваем прокси
        proxies = None
        if isinstance(connection, dict):
            proxies = connection
        else:
            proxies = {
                'http': f"{connection.protocol}://{connection.full_address}",
                'https': f"{connection.protocol}://{connection.full_address}"
            }
        
        print(f"🌐 Прокси: {proxies}")
        
        # Тестируем доступность сайта
        print("📡 Тестируем доступность сайта...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        }
        
        # Тестируем главную страницу
        try:
            response = requests.get(
                TrastConfig.MAIN_URL,
                proxies=proxies,
                headers=headers,
                timeout=10
            )
            print(f"✅ Главная страница: {response.status_code}")
        except Exception as e:
            print(f"❌ Главная страница: {e}")
            return False
        
        # Тестируем страницу магазина
        try:
            response = requests.get(
                TrastConfig.SHOP_URL,
                proxies=proxies,
                headers=headers,
                timeout=10
            )
            print(f"✅ Страница магазина: {response.status_code}")
            
            if response.status_code == 200:
                # Ищем продукты в HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                products = soup.find_all('div', class_='product')
                print(f"📦 Найдено продуктов: {len(products)}")
                
                if len(products) > 0:
                    print("✅ Парсинг работает!")
                    return True
                else:
                    print("⚠️ Продукты не найдены в HTML")
                    return False
            else:
                print(f"❌ Ошибка доступа к магазину: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Страница магазина: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Общая ошибка: {e}")
        return False

if __name__ == "__main__":
    test_requests_parsing()
