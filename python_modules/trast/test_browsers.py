#!/usr/bin/env python3
"""
Диагностика браузеров для Selenium
"""

import sys
import os
import subprocess

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_firefox():
    """Проверяем Firefox."""
    print("🦊 Проверка Firefox:")
    
    try:
        # Проверяем версию Firefox
        result = subprocess.run(['firefox', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ Firefox: {result.stdout.strip()}")
        else:
            print("❌ Firefox не найден")
            return False
    except Exception as e:
        print(f"❌ Firefox ошибка: {e}")
        return False
    
    try:
        # Проверяем geckodriver
        result = subprocess.run(['geckodriver', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ Geckodriver: {result.stdout.strip()}")
        else:
            print("❌ Geckodriver не найден")
            return False
    except Exception as e:
        print(f"❌ Geckodriver ошибка: {e}")
        return False
    
    return True

def check_chrome():
    """Проверяем Chrome."""
    print("\n🌐 Проверка Chrome:")
    
    try:
        # Проверяем версию Chrome
        result = subprocess.run(['google-chrome', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ Chrome: {result.stdout.strip()}")
        else:
            print("❌ Chrome не найден")
            return False
    except Exception as e:
        print(f"❌ Chrome ошибка: {e}")
        return False
    
    return True

def test_selenium():
    """Тестируем Selenium."""
    print("\n🧪 Тестирование Selenium:")
    
    try:
        from selenium import webdriver
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        
        print("✅ Selenium импортирован успешно")
        
        # Тестируем Firefox
        try:
            print("🦊 Тестируем Firefox...")
            options = FirefoxOptions()
            options.add_argument('--headless')
            driver = webdriver.Firefox(options=options)
            driver.get("https://httpbin.org/ip")
            print(f"✅ Firefox работает! IP: {driver.page_source[:100]}...")
            driver.quit()
            return True
        except Exception as e:
            print(f"❌ Firefox тест failed: {e}")
        
        # Тестируем Chrome
        try:
            print("🌐 Тестируем Chrome...")
            options = ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            driver = webdriver.Chrome(options=options)
            driver.get("https://httpbin.org/ip")
            print(f"✅ Chrome работает! IP: {driver.page_source[:100]}...")
            driver.quit()
            return True
        except Exception as e:
            print(f"❌ Chrome тест failed: {e}")
        
        return False
        
    except Exception as e:
        print(f"❌ Selenium ошибка: {e}")
        return False

def main():
    """Основная функция."""
    print("🔍 Диагностика браузеров для Selenium")
    print("=" * 50)
    
    firefox_ok = check_firefox()
    chrome_ok = check_chrome()
    selenium_ok = test_selenium()
    
    print("\n📊 Результаты:")
    print(f"Firefox: {'✅' if firefox_ok else '❌'}")
    print(f"Chrome: {'✅' if chrome_ok else '❌'}")
    print(f"Selenium: {'✅' if selenium_ok else '❌'}")
    
    if not selenium_ok:
        print("\n💡 Рекомендации:")
        if not firefox_ok:
            print("1. Установите Firefox ESR: sudo ./install_firefox.sh")
        if not chrome_ok:
            print("2. Установите Chrome: sudo apt install google-chrome-stable")
        print("3. Проверьте логи выше для деталей")
    
    return 0 if selenium_ok else 1

if __name__ == "__main__":
    sys.exit(main())
