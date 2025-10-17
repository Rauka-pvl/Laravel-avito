#!/usr/bin/env python3
"""
Непрерывный поиск рабочего прокси до успеха
"""

import asyncio
import sys
import os
import json
import random
import time
from typing import List, Dict, Optional
import httpx

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class ContinuousProxyHunter:
    """Непрерывный охотник за рабочими прокси."""
    
    def __init__(self):
        self.logger = setup_logger("continuous_proxy_hunter")
        self.all_proxies = []
        self.tested_proxies = set()
        self.working_proxies = []
        self.attempts = 0
        self.max_attempts = 1000  # Максимум попыток
    
    def load_all_proxies(self) -> List[str]:
        """Загружает все доступные прокси."""
        self.logger.info("📁 Загружаем все доступные прокси...")
        
        all_proxies = set()
        
        # Ищем все файлы с прокси
        import glob
        patterns = [
            "working_proxies_*.txt",
            "working_russian_proxies_*.txt",
            "russian_proxies_*.txt",
            "proxies_for_server_*.txt",
            "verified_proxies_*.txt",
            "working_proxies.json"
        ]
        
        for pattern in patterns:
            files = glob.glob(pattern)
            for file_path in files:
                try:
                    if file_path.endswith('.json'):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                all_proxies.update(data)
                            elif isinstance(data, dict):
                                if 'proxies' in data:
                                    all_proxies.update(data['proxies'])
                                elif 'russian_proxies' in data:
                                    for item in data['russian_proxies']:
                                        if isinstance(item, dict) and 'proxy' in item:
                                            all_proxies.add(item['proxy'])
                    else:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if line and ':' in line and not line.startswith('#'):
                                    all_proxies.add(line)
                    
                    self.logger.info(f"📁 Загружено из {file_path}")
                    
                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка загрузки {file_path}: {e}")
        
        self.all_proxies = list(all_proxies)
        self.logger.info(f"📊 Загружено {len(self.all_proxies)} прокси")
        
        return self.all_proxies
    
    async def test_proxy_against_target(self, proxy: str) -> Optional[Dict]:
        """Тестирует прокси против целевого сайта."""
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(8.0, connect=5.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False
            ) as client:
                start_time = time.time()
                
                # Тестируем против целевого сайта
                response = await client.get(TrastConfig.SHOP_URL)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    # Проверяем, что это не Cloudflare
                    content = response.text.lower()
                    cloudflare_indicators = ['checking your browser', 'ddos protection', 'cloudflare', 'ray id']
                    
                    if not any(indicator in content for indicator in cloudflare_indicators):
                        # Проверяем длину контента
                        if len(response.text) > 1000:
                            # Получаем IP адрес
                            try:
                                ip_response = await client.get("http://httpbin.org/ip")
                                if ip_response.status_code == 200:
                                    ip_data = ip_response.json()
                                    ip_address = ip_data.get('origin', 'unknown')
                                else:
                                    ip_address = 'unknown'
                            except:
                                ip_address = 'unknown'
                            
                            return {
                                'proxy': proxy,
                                'response_time': response_time,
                                'ip_address': ip_address,
                                'content_length': len(response.text),
                                'tested_at': time.strftime('%Y-%m-%d %H:%M:%S')
                            }
                        else:
                            return None  # Слишком короткий контент
                    else:
                        return None  # Cloudflare обнаружен
                else:
                    return None  # Неуспешный HTTP статус
                    
        except Exception as e:
            return None  # Ошибка подключения
    
    async def hunt_working_proxy(self) -> Optional[str]:
        """Охотится за рабочим прокси до успеха."""
        self.logger.info(f"🎯 НАЧИНАЕМ ОХОТУ ЗА РАБОЧИМ ПРОКСИ")
        self.logger.info(f"🎯 Целевой сайт: {TrastConfig.SHOP_URL}")
        self.logger.info(f"🎯 Максимум попыток: {self.max_attempts}")
        
        # Загружаем все прокси
        proxies = self.load_all_proxies()
        
        if not proxies:
            self.logger.error("❌ Нет прокси для тестирования")
            return None
        
        # Перемешиваем прокси для случайного тестирования
        random.shuffle(proxies)
        
        self.logger.info(f"🎲 Тестируем {len(proxies)} прокси случайным образом")
        
        # Тестируем прокси по одному до нахождения рабочего
        for i, proxy in enumerate(proxies):
            if self.attempts >= self.max_attempts:
                self.logger.warning(f"⚠️ Достигнут лимит попыток: {self.max_attempts}")
                break
            
            self.attempts += 1
            
            # Показываем прогресс каждые 10 попыток
            if self.attempts % 10 == 0:
                self.logger.info(f"📊 Попытка {self.attempts}/{self.max_attempts}: тестируем {proxy}")
            
            # Тестируем прокси
            result = await self.test_proxy_against_target(proxy)
            
            if result:
                self.working_proxies.append(result)
                self.logger.info(f"🎉 НАЙДЕН РАБОЧИЙ ПРОКСИ!")
                self.logger.info(f"✅ Прокси: {proxy}")
                self.logger.info(f"⏱️ Время ответа: {result['response_time']:.3f}s")
                self.logger.info(f"🌐 IP адрес: {result['ip_address']}")
                self.logger.info(f"📄 Длина контента: {result['content_length']} символов")
                self.logger.info(f"🎯 Попытка: {self.attempts}")
                
                return proxy
            
            # Небольшая пауза между тестами
            await asyncio.sleep(0.2)
        
        self.logger.warning(f"❌ Не удалось найти рабочий прокси за {self.attempts} попыток")
        return None
    
    def save_results(self, working_proxy: str):
        """Сохраняет результаты."""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем рабочий прокси
        with open("working_proxies.json", 'w', encoding='utf-8') as f:
            data = {
                'proxies': [working_proxy],
                'count': 1,
                'timestamp': timestamp,
                'source': 'continuous_proxy_hunter',
                'target_site': TrastConfig.SHOP_URL,
                'attempts': self.attempts,
                'details': self.working_proxies[0] if self.working_proxies else None
            }
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Создаем простой файл
        with open("working_proxies.txt", 'w', encoding='utf-8') as f:
            f.write(f"{working_proxy}\n")
        
        self.logger.info(f"💾 Сохранен рабочий прокси: {working_proxy}")
        self.logger.info(f"📄 Файлы: working_proxies.json, working_proxies.txt")

async def main():
    """Основная функция."""
    hunter = ContinuousProxyHunter()
    
    print("🎯 НЕПРЕРЫВНЫЙ ПОИСК РАБОЧЕГО ПРОКСИ")
    print("=" * 50)
    print(f"Целевой сайт: {TrastConfig.SHOP_URL}")
    print("Система будет тестировать прокси до нахождения рабочего")
    print()
    
    # Охотимся за рабочим прокси
    working_proxy = await hunter.hunt_working_proxy()
    
    if working_proxy:
        print(f"\n🎉 УСПЕХ! НАЙДЕН РАБОЧИЙ ПРОКСИ!")
        print(f"✅ Прокси: {working_proxy}")
        print(f"🎯 Попыток: {hunter.attempts}")
        
        # Сохраняем результаты
        hunter.save_results(working_proxy)
        
        print("\n✅ ГОТОВО!")
        print("Теперь можно запускать:")
        print("  python3 main.py")
    else:
        print(f"\n❌ НЕ УДАЛОСЬ НАЙТИ РАБОЧИЙ ПРОКСИ")
        print(f"🎯 Попыток: {hunter.attempts}")
        print("\nПопробуйте:")
        print("  1. Запустить proxy_hunter.py для поиска новых прокси")
        print("  2. Увеличить max_attempts в скрипте")
        print("  3. Проверить доступность целевого сайта")

if __name__ == "__main__":
    asyncio.run(main())
