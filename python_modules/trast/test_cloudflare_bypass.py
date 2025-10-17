#!/usr/bin/env python3
"""
Тестирование обхода Cloudflare с undetected-chromedriver
"""

import sys
import os
import time
import asyncio

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger
from connection_manager import ConnectionManager, ConnectionResult
from parser import PageFetcher

class CloudflareTester:
    """Тестер обхода Cloudflare."""
    
    def __init__(self):
        self.logger = setup_logger("cloudflare_tester")
        self.page_fetcher = PageFetcher()
    
    def test_undetected_chrome(self):
        """Тестирует undetected-chromedriver."""
        self.logger.info("🧪 Тестируем undetected-chromedriver...")
        
        try:
            import undetected_chromedriver as uc
            
            # Настройки для тестирования
            options = uc.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            # User agent
            user_agent = TrastConfig.get_random_user_agent()
            options.add_argument(f"--user-agent={user_agent}")
            
            # Создаем драйвер
            driver = uc.Chrome(options=options)
            
            # Дополнительные настройки для маскировки
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.logger.info("✅ Undetected Chrome создан успешно")
            
            # Тестируем на целевом сайте
            test_url = TrastConfig.FIRST_PAGE_URL
            self.logger.info(f"🌐 Тестируем на: {test_url}")
            
            start_time = time.time()
            driver.get(test_url)
            
            # Ждем загрузки
            time.sleep(10)
            
            # Проверяем результат
            page_source = driver.page_source
            page_length = len(page_source)
            
            self.logger.info(f"📊 Длина страницы: {page_length} символов")
            
            # Проверяем на Cloudflare
            cloudflare_indicators = ['checking your browser', 'ddos protection', 'cloudflare', 'ray id']
            cloudflare_found = False
            
            for indicator in cloudflare_indicators:
                if indicator in page_source.lower():
                    self.logger.warning(f"⚠️ Cloudflare индикатор найден: {indicator}")
                    cloudflare_found = True
            
            if not cloudflare_found:
                self.logger.info("✅ Cloudflare не обнаружен!")
            
            # Проверяем наличие контента
            content_selectors = [
                "a.facetwp-page.last",
                ".facetwp-pager", 
                ".pagination",
                "[data-page]",
                ".product",
                ".woocommerce-loop-product"
            ]
            
            content_found = False
            for selector in content_selectors:
                try:
                    element = driver.find_element("css selector", selector)
                    if element:
                        self.logger.info(f"✅ Найден элемент контента: {selector}")
                        content_found = True
                        break
                except:
                    continue
            
            if not content_found:
                self.logger.warning("⚠️ Элементы контента не найдены")
            
            # Сохраняем скриншот для анализа
            try:
                screenshot_path = "cloudflare_test_screenshot.png"
                driver.save_screenshot(screenshot_path)
                self.logger.info(f"📸 Скриншот сохранен: {screenshot_path}")
            except Exception as e:
                self.logger.warning(f"Не удалось сохранить скриншот: {e}")
            
            # Сохраняем HTML для анализа
            try:
                html_path = "cloudflare_test_page.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(page_source)
                self.logger.info(f"📄 HTML сохранен: {html_path}")
            except Exception as e:
                self.logger.warning(f"Не удалось сохранить HTML: {e}")
            
            driver.quit()
            
            # Результат теста
            if page_length > 5000 and not cloudflare_found and content_found:
                self.logger.info("🎉 ТЕСТ ПРОЙДЕН! Undetected Chrome успешно обходит Cloudflare!")
                return True
            else:
                self.logger.warning("❌ ТЕСТ НЕ ПРОЙДЕН. Cloudflare все еще блокирует.")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка тестирования undetected-chromedriver: {e}")
            return False
    
    def test_selenium_stealth(self):
        """Тестирует selenium-stealth с Firefox."""
        self.logger.info("🧪 Тестируем selenium-stealth с Firefox...")
        
        try:
            from selenium import webdriver
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            from selenium.webdriver.firefox.service import Service as FirefoxService
            from selenium_stealth import stealth
            
            options = FirefoxOptions()
            options.add_argument("--headless")
            
            # User agent
            user_agent = TrastConfig.get_random_user_agent()
            options.set_preference("general.useragent.override", user_agent)
            
            # Дополнительные настройки для обхода блокировок
            options.set_preference("dom.webdriver.enabled", False)
            options.set_preference("useAutomationExtension", False)
            
            service = FirefoxService()
            driver = webdriver.Firefox(options=options, service=service)
            
            # Применяем stealth
            stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Linux x86_64",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            
            self.logger.info("✅ Firefox с stealth создан успешно")
            
            # Тестируем на целевом сайте
            test_url = TrastConfig.FIRST_PAGE_URL
            self.logger.info(f"🌐 Тестируем на: {test_url}")
            
            driver.get(test_url)
            time.sleep(10)
            
            # Проверяем результат
            page_source = driver.page_source
            page_length = len(page_source)
            
            self.logger.info(f"📊 Длина страницы: {page_length} символов")
            
            driver.quit()
            
            if page_length > 5000:
                self.logger.info("🎉 ТЕСТ ПРОЙДЕН! Firefox с stealth работает!")
                return True
            else:
                self.logger.warning("❌ ТЕСТ НЕ ПРОЙДЕН. Страница слишком короткая.")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка тестирования selenium-stealth: {e}")
            return False
    
    async def test_full_parser(self):
        """Тестирует полный парсер с новыми настройками."""
        self.logger.info("🧪 Тестируем полный парсер...")
        
        try:
            # Тестируем подключения
            connection_manager = ConnectionManager()
            connection_results = await connection_manager.test_all_connections()
            best_connection = connection_manager.get_best_connection(connection_results)
            
            if not best_connection:
                self.logger.error("❌ Нет рабочих подключений")
                return False
            
            self.logger.info(f"✅ Используем подключение: {best_connection.connection_type}")
            
            # Тестируем парсинг первой страницы
            success, page_count, content = self.page_fetcher.parse_first_page(best_connection)
            
            if success:
                self.logger.info(f"🎉 ПАРСИНГ УСПЕШЕН! Найдено {page_count} страниц")
                self.logger.info(f"📊 Длина контента: {len(content)} символов")
                return True
            else:
                self.logger.warning("❌ Парсинг не удался")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка тестирования парсера: {e}")
            return False

async def main():
    """Основная функция тестирования."""
    tester = CloudflareTester()
    
    print("🧪 ТЕСТИРОВАНИЕ ОБХОДА CLOUDFLARE")
    print("=" * 50)
    
    # Тест 1: undetected-chromedriver
    print("\n1️⃣ Тестируем undetected-chromedriver...")
    result1 = tester.test_undetected_chrome()
    
    # Тест 2: selenium-stealth
    print("\n2️⃣ Тестируем selenium-stealth...")
    result2 = tester.test_selenium_stealth()
    
    # Тест 3: Полный парсер
    print("\n3️⃣ Тестируем полный парсер...")
    result3 = await tester.test_full_parser()
    
    # Итоги
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"   undetected-chromedriver: {'✅ ПРОЙДЕН' if result1 else '❌ НЕ ПРОЙДЕН'}")
    print(f"   selenium-stealth: {'✅ ПРОЙДЕН' if result2 else '❌ НЕ ПРОЙДЕН'}")
    print(f"   Полный парсер: {'✅ ПРОЙДЕН' if result3 else '❌ НЕ ПРОЙДЕН'}")
    
    if result1 or result2 or result3:
        print("\n🎉 ХОРОШИЕ НОВОСТИ! Хотя бы один метод работает!")
    else:
        print("\n😞 Все тесты не прошли. Нужна дополнительная настройка.")

if __name__ == "__main__":
    TrastConfig.ensure_directories()
    asyncio.run(main())
