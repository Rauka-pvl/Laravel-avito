#!/usr/bin/env python3
"""
Тестирование альтернативных стратегий обхода блокировок
"""

import asyncio
import sys
import os
import time
import random
from typing import List, Dict, Optional
import httpx
import requests

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class AlternativeStrategies:
    """Тестирование альтернативных стратегий."""
    
    def __init__(self):
        self.logger = setup_logger("alternative_strategies")
    
    async def test_user_agents(self):
        """Тестирует разные User-Agent."""
        self.logger.info("🧪 Тестируем разные User-Agent...")
        
        user_agents = [
            # Популярные браузеры
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            
            # Мобильные браузеры
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            
            # Старые браузеры
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
            
            # Боты и сканеры
            "Googlebot/2.1 (+http://www.google.com/bot.html)",
            "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
            "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"
        ]
        
        working_agents = []
        
        for i, user_agent in enumerate(user_agents):
            self.logger.info(f"📊 Тестируем User-Agent {i+1}/{len(user_agents)}")
            
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0),
                    headers={'User-Agent': user_agent},
                    verify=False
                ) as client:
                    response = await client.get(TrastConfig.SHOP_URL)
                    
                    if response.status_code == 200:
                        content = response.text.lower()
                        if 'cloudflare' not in content and 'checking your browser' not in content:
                            working_agents.append(user_agent)
                            self.logger.info(f"✅ Рабочий User-Agent: {user_agent[:50]}...")
                        else:
                            self.logger.debug(f"❌ Cloudflare блокирует: {user_agent[:50]}...")
                    else:
                        self.logger.debug(f"❌ HTTP {response.status_code}: {user_agent[:50]}...")
                        
            except Exception as e:
                self.logger.debug(f"❌ Ошибка: {user_agent[:50]}... - {e}")
            
            # Пауза между тестами
            await asyncio.sleep(1)
        
        self.logger.info(f"📊 РЕЗУЛЬТАТ: {len(working_agents)}/{len(user_agents)} рабочих User-Agent")
        return working_agents
    
    async def test_headers_combinations(self):
        """Тестирует комбинации заголовков."""
        self.logger.info("🧪 Тестируем комбинации заголовков...")
        
        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        additional_headers = [
            {'Referer': 'https://www.google.com/'},
            {'Referer': 'https://yandex.ru/'},
            {'Referer': 'https://www.bing.com/'},
            {'Cache-Control': 'no-cache'},
            {'Pragma': 'no-cache'},
            {'DNT': '1'},
            {'Sec-Fetch-Dest': 'document'},
            {'Sec-Fetch-Mode': 'navigate'},
            {'Sec-Fetch-Site': 'none'},
            {'Sec-Fetch-User': '?1'},
        ]
        
        working_combinations = []
        
        # Тестируем базовые заголовки
        result = await self._test_headers(base_headers)
        if result['success']:
            working_combinations.append(base_headers)
            self.logger.info("✅ Базовые заголовки работают")
        
        # Тестируем комбинации с дополнительными заголовками
        for additional in additional_headers:
            test_headers = {**base_headers, **additional}
            result = await self._test_headers(test_headers)
            
            if result['success']:
                working_combinations.append(test_headers)
                self.logger.info(f"✅ Работает с заголовком: {list(additional.keys())[0]}")
        
        self.logger.info(f"📊 РЕЗУЛЬТАТ: {len(working_combinations)} рабочих комбинаций заголовков")
        return working_combinations
    
    async def _test_headers(self, headers: Dict[str, str]) -> Dict:
        """Тестирует набор заголовков."""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers=headers,
                verify=False
            ) as client:
                response = await client.get(TrastConfig.SHOP_URL)
                
                if response.status_code == 200:
                    content = response.text.lower()
                    if 'cloudflare' not in content and 'checking your browser' not in content:
                        return {'success': True, 'status': response.status_code, 'content_length': len(response.text)}
                    else:
                        return {'success': False, 'status': response.status_code, 'error': 'Cloudflare detected'}
                else:
                    return {'success': False, 'status': response.status_code, 'error': f'HTTP {response.status_code}'}
                    
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_delays_and_retries(self):
        """Тестирует задержки и повторные попытки."""
        self.logger.info("🧪 Тестируем задержки и повторные попытки...")
        
        delays = [0, 1, 2, 5, 10]  # секунды
        max_retries = 3
        
        for delay in delays:
            self.logger.info(f"📊 Тестируем с задержкой {delay}s...")
            
            success = False
            for attempt in range(max_retries):
                try:
                    if delay > 0:
                        await asyncio.sleep(delay)
                    
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(15.0),
                        headers=TrastConfig.get_headers_with_user_agent(),
                        verify=False
                    ) as client:
                        response = await client.get(TrastConfig.SHOP_URL)
                        
                        if response.status_code == 200:
                            content = response.text.lower()
                            if 'cloudflare' not in content and 'checking your browser' not in content:
                                success = True
                                self.logger.info(f"✅ Успех с задержкой {delay}s, попытка {attempt+1}")
                                break
                            else:
                                self.logger.debug(f"❌ Cloudflare с задержкой {delay}s, попытка {attempt+1}")
                        else:
                            self.logger.debug(f"❌ HTTP {response.status_code} с задержкой {delay}s, попытка {attempt+1}")
                            
                except Exception as e:
                    self.logger.debug(f"❌ Ошибка с задержкой {delay}s, попытка {attempt+1}: {e}")
                
                # Пауза между попытками
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
            
            if success:
                self.logger.info(f"🎉 НАЙДЕНА РАБОЧАЯ СТРАТЕГИЯ: задержка {delay}s")
                return delay
        
        self.logger.warning("❌ Ни одна стратегия с задержками не сработала")
        return None
    
    async def test_session_simulation(self):
        """Тестирует симуляцию сессии."""
        self.logger.info("🧪 Тестируем симуляцию сессии...")
        
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False
            ) as client:
                # Шаг 1: Идем на главную страницу
                self.logger.info("📊 Шаг 1: Заходим на главную страницу...")
                main_response = await client.get(TrastConfig.BASE_URL)
                
                if main_response.status_code == 200:
                    self.logger.info("✅ Главная страница загружена")
                    
                    # Пауза как у человека
                    await asyncio.sleep(random.uniform(2, 5))
                    
                    # Шаг 2: Переходим на целевую страницу
                    self.logger.info("📊 Шаг 2: Переходим на целевую страницу...")
                    target_response = await client.get(TrastConfig.SHOP_URL)
                    
                    if target_response.status_code == 200:
                        content = target_response.text.lower()
                        if 'cloudflare' not in content and 'checking your browser' not in content:
                            self.logger.info("✅ Симуляция сессии успешна!")
                            return True
                        else:
                            self.logger.warning("❌ Cloudflare блокирует даже после симуляции сессии")
                    else:
                        self.logger.warning(f"❌ Целевая страница недоступна: HTTP {target_response.status_code}")
                else:
                    self.logger.warning(f"❌ Главная страница недоступна: HTTP {main_response.status_code}")
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка симуляции сессии: {e}")
        
        return False

async def main():
    """Основная функция тестирования альтернативных стратегий."""
    strategies = AlternativeStrategies()
    
    print("🧪 ТЕСТИРОВАНИЕ АЛЬТЕРНАТИВНЫХ СТРАТЕГИЙ")
    print("=" * 60)
    
    # Тест 1: User-Agent
    print("\n1️⃣ Тестируем User-Agent...")
    working_agents = await strategies.test_user_agents()
    
    # Тест 2: Заголовки
    print("\n2️⃣ Тестируем заголовки...")
    working_headers = await strategies.test_headers_combinations()
    
    # Тест 3: Задержки
    print("\n3️⃣ Тестируем задержки...")
    working_delay = await strategies.test_delays_and_retries()
    
    # Тест 4: Симуляция сессии
    print("\n4️⃣ Тестируем симуляцию сессии...")
    session_works = await strategies.test_session_simulation()
    
    # Итоги
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"   Рабочих User-Agent: {len(working_agents)}")
    print(f"   Рабочих комбинаций заголовков: {len(working_headers)}")
    print(f"   Рабочая задержка: {working_delay}s" if working_delay else "   Рабочая задержка: не найдена")
    print(f"   Симуляция сессии: {'✅ работает' if session_works else '❌ не работает'}")
    
    if working_agents or working_headers or working_delay or session_works:
        print("\n🎉 НАЙДЕНЫ РАБОЧИЕ СТРАТЕГИИ!")
        print("Можно попробовать:")
        print("  1. Использовать рабочие User-Agent")
        print("  2. Применить рабочие заголовки")
        print("  3. Добавить задержки в запросы")
        print("  4. Симулировать сессию пользователя")
    else:
        print("\n❌ НИ ОДНА СТРАТЕГИЯ НЕ СРАБОТАЛА")
        print("Возможно, нужны более радикальные меры:")
        print("  1. Использовать Selenium с undetected-chromedriver")
        print("  2. Настроить TOR или WARP")
        print("  3. Использовать платные прокси")
        print("  4. Обратиться к администратору сайта")

if __name__ == "__main__":
    asyncio.run(main())
