#!/usr/bin/env python3
"""
Простой тест WARP на сервере
"""

import subprocess
import requests
import time

def test_warp_simple():
    """Простой тест WARP."""
    print("🧪 Простой тест WARP...")
    
    # 1. Проверяем статус WARP
    print("1️⃣ Проверяем статус WARP...")
    try:
        result = subprocess.run(
            ["warp-cli", "status"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        print(f"Статус WARP: {result.stdout}")
        
        if "Connected" in result.stdout:
            print("✅ WARP подключен")
        else:
            print("❌ WARP не подключен")
            return
    except Exception as e:
        print(f"❌ Ошибка проверки статуса: {e}")
        return
    
    # 2. Проверяем порт 40000
    print("2️⃣ Проверяем порт 40000...")
    proxy_url = "socks5://127.0.0.1:40000"
    proxies = {
        'http': proxy_url,
        'https': proxy_url
    }
    
    try:
        response = requests.get(
            "https://httpbin.org/ip", 
            proxies=proxies, 
            timeout=10
        )
        print(f"Ответ: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ IP через WARP: {data.get('origin', 'N/A')}")
        else:
            print(f"❌ Ошибка: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
    
    # 3. Проверяем другие порты
    print("3️⃣ Проверяем другие порты...")
    ports = [40000, 40001, 40002, 40003, 40004]
    
    for port in ports:
        try:
            proxy_url = f"socks5://127.0.0.1:{port}"
            proxies = {'http': proxy_url, 'https': proxy_url}
            
            response = requests.get(
                "https://httpbin.org/ip", 
                proxies=proxies, 
                timeout=3
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Порт {port} работает: {data.get('origin', 'N/A')}")
            else:
                print(f"❌ Порт {port} не работает: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Порт {port} ошибка: {e}")

if __name__ == "__main__":
    test_warp_simple()
