#!/usr/bin/env python3
"""
Тестирование прямого подключения без прокси
"""

import asyncio
import sys
import os
import time
import httpx
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
import undetected_chromedriver as uc

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class DirectConnectionTest:
    """Тестирование прямого подключения."""
    
    def __init__(self):
        self.logger = setup_logger("direct_connection_test")
        self.target_url = TrastConfig.SHOP_URL
    
    async def test_httpx_direct(self):
        """Тестирует прямое подключение через httpx."""
        self.logger.info("🧪 Тестируем прямое подключение через httpx...")
        
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False,
                follow_redirects=True
            ) as client:
                start_time = time.time()
                response = await client.get(self.target_url)
                response_time = time.time() - start_time
                
                self.logger.info(f"📊 httpx результат:")
                self.logger.info(f"  Статус: {response.status_code}")
                self.logger.info(f"  Время: {response_time:.3f}s")
                self.logger.info(f"  Длина контента: {len(response.text)} символов")
                
                if response.status_code == 200:
                    content = response.text.lower()
                    if 'cloudflare' in content or 'checking your browser' in content:
                        self.logger.warning("⚠️ Cloudflare блокирует прямое подключение")
                        return False
                    else:
                        self.logger.info("✅ httpx работает!")
                        return True
                else:
                    self.logger.warning(f"⚠️ httpx не работает: HTTP {response.status_code}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка httpx: {e}")
            return False
    
    def test_requests_direct(self):
        """Тестирует прямое подключение через requests."""
        self.logger.info("🧪 Тестируем прямое подключение через requests...")
        
        try:
            start_time = time.time()
            response = requests.get(
                self.target_url,
                headers=TrastConfig.get_headers_with_user_agent(),
                timeout=15,
                verify=False
            )
            response_time = time.time() - start_time
            
            self.logger.info(f"📊 requests результат:")
            self.logger.info(f"  Статус: {response.status_code}")
            self.logger.info(f"  Время: {response_time:.3f}s")
            self.logger.info(f"  Длина контента: {len(response.text)} символов")
            
            if response.status_code == 200:
                content = response.text.lower()
                if 'cloudflare' in content or 'checking your browser' in content:
                    self.logger.warning("⚠️ Cloudflare блокирует прямое подключение")
                    return False
                else:
                    self.logger.info("✅ requests работает!")
                    return True
            else:
                self.logger.warning(f"⚠️ requests не работает: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка requests: {e}")
            return False
    
    def test_selenium_regular(self):
        """Тестирует Selenium с обычным Chrome."""
        self.logger.info("🧪 Тестируем Selenium с обычным Chrome...")
        
        driver = None
        try:
            options = ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--disable-images")
            options.add_argument("--disable-javascript")
            user_agent = TrastConfig.get_random_user_agent()
            options.add_argument(f"--user-agent={user_agent}")
            
            service = ChromeService()
            driver = webdriver.Chrome(options=options, service=service)
            
            self.logger.info("✅ Обычный Chrome создан")
            
            start_time = time.time()
            driver.get(self.target_url)
            
            # Ждем загрузки
            time.sleep(10)
            
            response_time = time.time() - start_time
            page_source = driver.page_source
            
            self.logger.info(f"📊 Selenium результат:")
            self.logger.info(f"  Время: {response_time:.3f}s")
            self.logger.info(f"  Длина контента: {len(page_source)} символов")
            
            if len(page_source) > 5000:
                content = page_source.lower()
                if 'cloudflare' in content or 'checking your browser' in content:
                    self.logger.warning("⚠️ Cloudflare блокирует обычный Chrome")
                    return False
                else:
                    self.logger.info("✅ Обычный Chrome работает!")
                    return True
            else:
                self.logger.warning("⚠️ Обычный Chrome вернул короткий контент")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка обычного Chrome: {e}")
            return False
        finally:
            if driver:
                driver.quit()
    
    def test_selenium_undetected(self):
        """Тестирует Selenium с undetected-chromedriver."""
        self.logger.info("🧪 Тестируем Selenium с undetected-chromedriver...")
        
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            user_agent = TrastConfig.get_random_user_agent()
            options.add_argument(f"--user-agent={user_agent}")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.logger.info("✅ Undetected Chrome создан")
            
            start_time = time.time()
            driver.get(self.target_url)
            
            # Ждем загрузки
            time.sleep(15)
            
            response_time = time.time() - start_time
            page_source = driver.page_source
            
            self.logger.info(f"📊 Undetected Chrome результат:")
            self.logger.info(f"  Время: {response_time:.3f}s")
            self.logger.info(f"  Длина контента: {len(page_source)} символов")
            
            if len(page_source) > 5000:
                content = page_source.lower()
                if 'cloudflare' in content or 'checking your browser' in content:
                    self.logger.warning("⚠️ Cloudflare блокирует undetected Chrome")
                    return False
                else:
                    self.logger.info("✅ Undetected Chrome работает!")
                    return True
            else:
                self.logger.warning("⚠️ Undetected Chrome вернул короткий контент")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка undetected Chrome: {e}")
            return False
        finally:
            if driver:
                driver.quit()
    
    def test_selenium_with_delays(self):
        """Тестирует Selenium с задержками и симуляцией человека."""
        self.logger.info("🧪 Тестируем Selenium с симуляцией человека...")
        
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            user_agent = TrastConfig.get_random_user_agent()
            options.add_argument(f"--user-agent={user_agent}")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.logger.info("✅ Undetected Chrome с симуляцией создан")
            
            # Шаг 1: Идем на главную страницу
            self.logger.info("📊 Шаг 1: Заходим на главную страницу...")
            driver.get(TrastConfig.BASE_URL)
            time.sleep(5)
            
            # Шаг 2: Переходим на целевую страницу
            self.logger.info("📊 Шаг 2: Переходим на целевую страницу...")
            driver.get(self.target_url)
            time.sleep(10)
            
            # Шаг 3: Ждем дополнительно
            self.logger.info("📊 Шаг 3: Ждем загрузки...")
            time.sleep(15)
            
            page_source = driver.page_source
            
            self.logger.info(f"📊 Selenium с симуляцией результат:")
            self.logger.info(f"  Длина контента: {len(page_source)} символов")
            
            if len(page_source) > 5000:
                content = page_source.lower()
                if 'cloudflare' in content or 'checking your browser' in content:
                    self.logger.warning("⚠️ Cloudflare блокирует даже с симуляцией")
                    return False
                else:
                    self.logger.info("✅ Selenium с симуляцией работает!")
                    return True
            else:
                self.logger.warning("⚠️ Selenium с симуляцией вернул короткий контент")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка Selenium с симуляцией: {e}")
            return False
        finally:
            if driver:
                driver.quit()

async def main():
    """Основная функция тестирования."""
    tester = DirectConnectionTest()
    
    print("🧪 ТЕСТИРОВАНИЕ ПРЯМОГО ПОДКЛЮЧЕНИЯ")
    print("=" * 50)
    
    results = {}
    
    # Тест 1: httpx
    print("\n1️⃣ Тестируем httpx...")
    results['httpx'] = await tester.test_httpx_direct()
    
    # Тест 2: requests
    print("\n2️⃣ Тестируем requests...")
    results['requests'] = tester.test_requests_direct()
    
    # Тест 3: Selenium обычный
    print("\n3️⃣ Тестируем Selenium обычный...")
    results['selenium_regular'] = tester.test_selenium_regular()
    
    # Тест 4: Selenium undetected
    print("\n4️⃣ Тестируем Selenium undetected...")
    results['selenium_undetected'] = tester.test_selenium_undetected()
    
    # Тест 5: Selenium с симуляцией
    print("\n5️⃣ Тестируем Selenium с симуляцией...")
    results['selenium_simulation'] = tester.test_selenium_with_delays()
    
    # Итоги
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    for method, success in results.items():
        status = "✅ работает" if success else "❌ не работает"
        print(f"   {method}: {status}")
    
    working_methods = [method for method, success in results.items() if success]
    
    if working_methods:
        print(f"\n🎉 РАБОТАЮЩИЕ МЕТОДЫ: {', '.join(working_methods)}")
        print("Можно использовать эти методы для парсинга!")
    else:
        print("\n❌ НИ ОДИН МЕТОД НЕ РАБОТАЕТ")
        print("Возможные причины:")
        print("  1. Сайт заблокирован Cloudflare")
        print("  2. Проблемы с сетью")
        print("  3. Сайт недоступен")
        print("  4. Нужны более продвинутые методы обхода")

if __name__ == "__main__":
    asyncio.run(main())
