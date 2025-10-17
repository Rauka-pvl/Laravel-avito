#!/usr/bin/env python3
"""
Непрерывный поиск рабочего прокси до тех пор, пока не найдем
"""

import asyncio
import sys
import os
import json
import time
import random
from typing import List, Dict, Optional, Tuple
import httpx

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class ContinuousProxyFinder:
    """Непрерывно ищет рабочий прокси до тех пор, пока не найдет."""
    
    def __init__(self):
        self.logger = setup_logger("continuous_proxy_finder")
        self.working_proxies = []
        self.last_working_proxy = None
        self.test_results = []
        self.total_tested = 0
    
    def load_all_proxies(self) -> List[str]:
        """Загружает ВСЕ доступные прокси."""
        all_proxies = set()
        
        # Загружаем из working_proxies.json
        if os.path.exists("working_proxies.json"):
            try:
                with open("working_proxies.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    proxies = data.get('proxies', [])
                    all_proxies.update(proxies)
                    self.logger.info(f"📁 Загружено {len(proxies)} прокси из working_proxies.json")
            except Exception as e:
                self.logger.warning(f"⚠️ Ошибка загрузки working_proxies.json: {e}")
        
        # Загружаем из других файлов
        import glob
        patterns = [
            "working_proxies_*.json",
            "proxies_for_server_*.txt",
            "working_russian_proxies_*.json",
            "all_working_proxies_*.json",
            "all_working_proxies.txt"
        ]
        
        for pattern in patterns:
            files = glob.glob(pattern)
            if files:
                latest_file = max(files, key=os.path.getmtime)
                try:
                    if latest_file.endswith('.json'):
                        with open(latest_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                all_proxies.update(data)
                            elif isinstance(data, dict) and 'proxies' in data:
                                all_proxies.update(data['proxies'])
                    elif latest_file.endswith('.txt'):
                        with open(latest_file, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if line and ':' in line and not line.startswith('#'):
                                    all_proxies.add(line)
                    self.logger.info(f"📁 Загружено прокси из {latest_file}")
                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка загрузки {latest_file}: {e}")
        
        proxies_list = list(all_proxies)
        self.logger.info(f"📊 Всего загружено {len(proxies_list)} уникальных прокси")
        return proxies_list
    
    async def test_single_proxy(self, proxy: str) -> Dict:
        """Тестирует один прокси."""
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(5.0, connect=3.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False,
                follow_redirects=True
            ) as client:
                start_time = time.time()
                
                # Тестируем против целевого сайта
                response = await client.get(TrastConfig.SHOP_URL)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    content = response.text.lower()
                    cloudflare_indicators = ['checking your browser', 'ddos protection', 'cloudflare', 'ray id']
                    
                    if not any(indicator in content for indicator in cloudflare_indicators):
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
                            'success': True,
                            'response_time': response_time,
                            'ip_address': ip_address,
                            'content_length': len(response.text)
                        }
                    else:
                        return {
                            'proxy': proxy,
                            'success': False,
                            'response_time': response_time,
                            'error': 'Cloudflare blocked'
                        }
                else:
                    return {
                        'proxy': proxy,
                        'success': False,
                        'response_time': response_time,
                        'error': f'HTTP {response.status_code}'
                    }
                    
        except Exception as e:
            return {
                'proxy': proxy,
                'success': False,
                'response_time': 0,
                'error': str(e)
            }
    
    async def find_working_proxy(self, proxies: List[str]) -> Optional[Dict]:
        """Ищет рабочий прокси, тестируя ВСЕ прокси по очереди."""
        self.logger.info(f"🔍 Начинаем поиск рабочего прокси из {len(proxies)} прокси...")
        
        # Перемешиваем прокси для случайности
        random.shuffle(proxies)
        
        for i, proxy in enumerate(proxies):
            self.total_tested += 1
            
            if i % 10 == 0:
                self.logger.info(f"📊 Тестируем прокси {i+1}/{len(proxies)}: {proxy}")
            
            result = await self.test_single_proxy(proxy)
            self.test_results.append(result)
            
            if result['success']:
                self.working_proxies.append(result)
                self.last_working_proxy = result
                self.logger.info(f"🎉 НАЙДЕН РАБОЧИЙ ПРОКСИ: {proxy} ({result['response_time']:.3f}s)")
                return result
            
            # Небольшая пауза между тестами
            await asyncio.sleep(0.1)
        
        self.logger.warning(f"❌ Не найдено рабочих прокси из {len(proxies)} протестированных")
        return None
    
    async def test_until_found(self, max_attempts: int = 1000) -> Optional[Dict]:
        """Тестирует прокси до тех пор, пока не найдет рабочий."""
        self.logger.info(f"🚀 Запускаем непрерывный поиск рабочего прокси (макс. {max_attempts} попыток)...")
        
        # Загружаем все прокси
        all_proxies = self.load_all_proxies()
        
        if not all_proxies:
            self.logger.error("❌ Не найдены прокси для тестирования")
            return None
        
        # Тестируем прокси циклически
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            
            # Берем случайную выборку прокси для тестирования
            test_proxies = random.sample(all_proxies, min(100, len(all_proxies)))
            
            self.logger.info(f"🔄 Попытка {attempt}/{max_attempts}: тестируем {len(test_proxies)} прокси")
            
            working_proxy = await self.find_working_proxy(test_proxies)
            
            if working_proxy:
                self.logger.info(f"✅ НАЙДЕН РАБОЧИЙ ПРОКСИ на попытке {attempt}: {working_proxy['proxy']}")
                return working_proxy
            
            # Если не нашли, ждем немного и пробуем снова
            self.logger.info(f"⏳ Попытка {attempt} не удалась, ждем 5 секунд...")
            await asyncio.sleep(5)
        
        self.logger.error(f"❌ Не удалось найти рабочий прокси за {max_attempts} попыток")
        return None
    
    def save_results(self):
        """Сохраняет результаты поиска."""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем все результаты
        results_file = f"continuous_proxy_search_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                'test_results': self.test_results,
                'working_proxies': self.working_proxies,
                'last_working_proxy': self.last_working_proxy,
                'total_tested': self.total_tested,
                'timestamp': timestamp,
                'target_site': TrastConfig.SHOP_URL
            }, f, indent=2, ensure_ascii=False)
        
        # Сохраняем рабочие прокси
        if self.working_proxies:
            working_file = f"continuous_working_proxies_{timestamp}.json"
            with open(working_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'proxies': [p['proxy'] for p in self.working_proxies],
                    'count': len(self.working_proxies),
                    'timestamp': timestamp,
                    'source': 'continuous_proxy_finder'
                }, f, indent=2, ensure_ascii=False)
            
            # Создаем простой файл
            with open("continuous_working_proxies.txt", 'w', encoding='utf-8') as f:
                for proxy_data in self.working_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            self.logger.info(f"💾 Сохранены рабочие прокси в {working_file}")
        
        self.logger.info(f"📄 Результаты поиска сохранены в {results_file}")
    
    def analyze_results(self):
        """Анализирует результаты поиска."""
        self.logger.info("📊 АНАЛИЗ РЕЗУЛЬТАТОВ ПОИСКА")
        self.logger.info("=" * 50)
        self.logger.info(f"📊 Всего протестировано: {self.total_tested}")
        self.logger.info(f"✅ Найдено рабочих: {len(self.working_proxies)}")
        
        if self.total_tested > 0:
            success_rate = (len(self.working_proxies) / self.total_tested) * 100
            self.logger.info(f"📈 Процент успеха: {success_rate:.1f}%")
        
        if self.last_working_proxy:
            self.logger.info(f"🏆 Последний рабочий прокси: {self.last_working_proxy['proxy']} ({self.last_working_proxy['response_time']:.3f}s)")
        
        # Анализируем ошибки
        error_counts = {}
        for result in self.test_results:
            if not result['success']:
                error = result.get('error', 'Unknown error')
                error_counts[error] = error_counts.get(error, 0) + 1
        
        if error_counts:
            self.logger.info("🔍 АНАЛИЗ ОШИБОК:")
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / self.total_tested) * 100
                self.logger.info(f"  {error}: {count} ({percentage:.1f}%)")

async def main():
    """Основная функция непрерывного поиска прокси."""
    finder = ContinuousProxyFinder()
    
    print("🔍 НЕПРЕРЫВНЫЙ ПОИСК РАБОЧЕГО ПРОКСИ")
    print("=" * 50)
    
    # Ищем рабочий прокси
    working_proxy = await finder.test_until_found(max_attempts=500)
    
    # Анализируем результаты
    finder.analyze_results()
    
    # Сохраняем результаты
    finder.save_results()
    
    if working_proxy:
        print(f"\n🎉 НАЙДЕН РАБОЧИЙ ПРОКСИ: {working_proxy['proxy']}")
        print(f"⏱️ Время отклика: {working_proxy['response_time']:.3f}s")
        print(f"🌐 IP адрес: {working_proxy['ip_address']}")
        print(f"📊 Всего протестировано: {finder.total_tested}")
        print(f"✅ Найдено рабочих: {len(finder.working_proxies)}")
        print("\nТеперь можно запускать:")
        print("  python3 main.py")
    else:
        print("\n❌ РАБОЧИЙ ПРОКСИ НЕ НАЙДЕН")
        print("Возможные решения:")
        print("  1. Попробовать другие источники прокси")
        print("  2. Использовать платные прокси")
        print("  3. Настроить TOR или WARP")
        print("  4. Использовать Selenium без прокси")

if __name__ == "__main__":
    asyncio.run(main())
