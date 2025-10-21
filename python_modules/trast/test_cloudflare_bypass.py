#!/usr/bin/env python3
"""
Альтернативные стратегии обхода Cloudflare
"""

import requests
import time
import random
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
import geckodriver_autoinstaller

def test_direct_access():
    """Тест прямого доступа без прокси"""
    print("=== ТЕСТ ПРЯМОГО ДОСТУПА ===")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        response = requests.get("https://trast-zapchast.ru/shop/", headers=headers, timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Размер: {len(response.content)} байт")
        
        if response.status_code == 200:
            content = response.text.lower()
            if "cloudflare" in content:
                print("❌ Cloudflare блокирует прямой доступ")
            elif "shop" in content or "товар" in content:
                print("✅ Прямой доступ работает!")
                return True
            else:
                print("⚠️ Неизвестное содержимое")
        else:
            print(f"❌ HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    return False

def test_mobile_user_agent():
    """Тест с мобильным User-Agent"""
    print("\n=== ТЕСТ МОБИЛЬНОГО USER-AGENT ===")
    
    mobile_headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        response = requests.get("https://trast-zapchast.ru/shop/", headers=mobile_headers, timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Размер: {len(response.content)} байт")
        
        if response.status_code == 200:
            content = response.text.lower()
            if "cloudflare" in content:
                print("❌ Cloudflare блокирует мобильный доступ")
            elif "shop" in content or "товар" in content:
                print("✅ Мобильный доступ работает!")
                return True
            else:
                print("⚠️ Неизвестное содержимое")
        else:
            print(f"❌ HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    return False

def test_selenium_without_proxy():
    """Тест Selenium без прокси"""
    print("\n=== ТЕСТ SELENIUM БЕЗ ПРОКСИ ===")
    
    try:
        geckodriver_autoinstaller.install()
        
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        
        # DNS настройки
        options.add_argument("--dns-prefetch-disable")
        options.set_preference("network.dns.disablePrefetch", True)
        options.set_preference("network.dns.defaultIPv4", "8.8.8.8")
        
        # Обход детекции
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        
        # Случайный User-Agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0"
        ]
        options.set_preference("general.useragent.override", random.choice(user_agents))
        
        # Увеличенные таймауты
        options.set_preference("network.http.connection-timeout", 60)
        options.set_preference("network.http.response.timeout", 60)
        options.set_preference("network.dns.timeout", 30)
        
        service = Service()
        driver = webdriver.Firefox(service=service, options=options)
        
        # Дополнительные скрипты
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        
        print("Загружаем страницу...")
        driver.get("https://trast-zapchast.ru/shop/")
        time.sleep(5)
        
        page_source = driver.page_source
        print(f"Размер страницы: {len(page_source)} байт")
        
        if "cloudflare" in page_source.lower():
            print("❌ Cloudflare блокирует Selenium")
        elif "shop" in page_source.lower() or "товар" in page_source.lower():
            print("✅ Selenium без прокси работает!")
            driver.quit()
            return True
        else:
            print("⚠️ Неизвестное содержимое")
            print(f"Первые 200 символов: {page_source[:200]}...")
        
        driver.quit()
        
    except Exception as e:
        print(f"❌ Ошибка Selenium: {e}")
    
    return False

def test_alternative_urls():
    """Тест альтернативных URL"""
    print("\n=== ТЕСТ АЛЬТЕРНАТИВНЫХ URL ===")
    
    urls_to_test = [
        "https://trast-zapchast.ru/",
        "http://trast-zapchast.ru/shop/",
        "https://trast-zapchast.ru/shop/?_paged=1",
        "https://trast-zapchast.ru/shop/?page=1",
        "https://trast-zapchast.ru/catalog/",
        "https://trast-zapchast.ru/products/"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8'
    }
    
    for url in urls_to_test:
        try:
            print(f"Тестируем: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"  Статус: {response.status_code}")
            
            if response.status_code == 200:
                content = response.text.lower()
                if "cloudflare" in content:
                    print("  ❌ Cloudflare")
                elif "shop" in content or "товар" in content or "каталог" in content:
                    print("  ✅ Доступен!")
                    return url
                else:
                    print("  ⚠️ Неизвестное содержимое")
            else:
                print(f"  ❌ HTTP {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    
    return None

if __name__ == "__main__":
    print("=== ТЕСТИРОВАНИЕ АЛЬТЕРНАТИВНЫХ СТРАТЕГИЙ ===")
    
    # Тест 1: Прямой доступ
    if test_direct_access():
        print("🎉 Прямой доступ работает!")
        exit(0)
    
    # Тест 2: Мобильный User-Agent
    if test_mobile_user_agent():
        print("🎉 Мобильный доступ работает!")
        exit(0)
    
    # Тест 3: Selenium без прокси
    if test_selenium_without_proxy():
        print("🎉 Selenium без прокси работает!")
        exit(0)
    
    # Тест 4: Альтернативные URL
    working_url = test_alternative_urls()
    if working_url:
        print(f"🎉 Альтернативный URL работает: {working_url}")
        exit(0)
    
    print("\n❌ Все стратегии заблокированы Cloudflare")
