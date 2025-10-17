#!/usr/bin/env python3
"""
Тестирование ВСЕХ прокси для поиска работающих
"""

import asyncio
import sys
import os
import json
import time
import random
from typing import List, Dict, Optional
import httpx

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class AllProxiesTester:
    """Тестирует ВСЕ прокси для поиска работающих."""
    
    def __init__(self):
        self.logger = setup_logger("all_proxies_tester")
        self.working_proxies = []
        self.test_results = []
    
    def load_all_proxies(self) -> List[str]:
        """Загружает все доступные прокси."""
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
            "working_russian_proxies_*.json"
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
                                if line and ':' in line:
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
    
    async def test_all_proxies(self, proxies: List[str]) -> List[Dict]:
        """Тестирует все прокси."""
        self.logger.info(f"🧪 Начинаем тестирование {len(proxies)} прокси...")
        
        # Тестируем батчами по 20
        batch_size = 20
        all_results = []
        
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(proxies) + batch_size - 1) // batch_size
            
            self.logger.info(f"📦 Батч {batch_num}/{total_batches}: тестируем {len(batch)} прокси")
            
            # Тестируем батч параллельно
            tasks = [self.test_single_proxy(proxy) for proxy in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for j, result in enumerate(batch_results):
                proxy = batch[j]
                if isinstance(result, Exception):
                    result = {
                        'proxy': proxy,
                        'success': False,
                        'response_time': 0,
                        'error': str(result)
                    }
                
                all_results.append(result)
                
                if result['success']:
                    self.working_proxies.append(result)
                    self.logger.info(f"✅ РАБОЧИЙ ПРОКСИ: {proxy} ({result['response_time']:.3f}s)")
            
            # Пауза между батчами
            if i + batch_size < len(proxies):
                await asyncio.sleep(1)
        
        return all_results
    
    def analyze_results(self, results: List[Dict]):
        """Анализирует результаты тестирования."""
        total_tests = len(results)
        working_count = len(self.working_proxies)
        
        self.logger.info("📊 АНАЛИЗ РЕЗУЛЬТАТОВ")
        self.logger.info("=" * 50)
        self.logger.info(f"📊 Всего тестов: {total_tests}")
        self.logger.info(f"✅ Рабочих прокси: {working_count}")
        self.logger.info(f"❌ Не рабочих: {total_tests - working_count}")
        
        if total_tests > 0:
            success_rate = (working_count / total_tests) * 100
            self.logger.info(f"📈 Процент успеха: {success_rate:.1f}%")
        
        # Анализируем ошибки
        error_counts = {}
        for result in results:
            if not result['success']:
                error = result.get('error', 'Unknown error')
                error_counts[error] = error_counts.get(error, 0) + 1
        
        if error_counts:
            self.logger.info("🔍 АНАЛИЗ ОШИБОК:")
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_tests) * 100
                self.logger.info(f"  {error}: {count} ({percentage:.1f}%)")
        
        # Показываем рабочие прокси
        if self.working_proxies:
            self.logger.info("🏆 РАБОЧИЕ ПРОКСИ:")
            sorted_proxies = sorted(self.working_proxies, key=lambda x: x['response_time'])
            for i, proxy_data in enumerate(sorted_proxies):
                self.logger.info(f"  {i+1}. {proxy_data['proxy']} - {proxy_data['response_time']:.3f}s - {proxy_data['ip_address']}")
    
    def save_results(self, results: List[Dict]):
        """Сохраняет результаты тестирования."""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем все результаты
        results_file = f"all_proxies_test_results_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                'test_results': results,
                'working_proxies': self.working_proxies,
                'timestamp': timestamp,
                'target_site': TrastConfig.SHOP_URL,
                'total_tested': len(results),
                'working_count': len(self.working_proxies)
            }, f, indent=2, ensure_ascii=False)
        
        # Сохраняем только рабочие прокси
        if self.working_proxies:
            working_file = f"all_working_proxies_{timestamp}.json"
            with open(working_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'proxies': [p['proxy'] for p in self.working_proxies],
                    'count': len(self.working_proxies),
                    'timestamp': timestamp,
                    'source': 'all_proxies_tester'
                }, f, indent=2, ensure_ascii=False)
            
            # Создаем простой файл
            with open("all_working_proxies.txt", 'w', encoding='utf-8') as f:
                for proxy_data in self.working_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            self.logger.info(f"💾 Сохранены рабочие прокси в {working_file}")
        
        self.logger.info(f"📄 Результаты тестирования сохранены в {results_file}")

async def main():
    """Основная функция тестирования всех прокси."""
    tester = AllProxiesTester()
    
    print("🧪 ТЕСТИРОВАНИЕ ВСЕХ ПРОКСИ")
    print("=" * 50)
    
    # Загружаем все прокси
    all_proxies = tester.load_all_proxies()
    
    if not all_proxies:
        print("❌ Не найдены прокси для тестирования")
        return
    
    print(f"📊 Найдено {len(all_proxies)} прокси для тестирования")
    
    # Тестируем все прокси
    results = await tester.test_all_proxies(all_proxies)
    
    # Анализируем результаты
    tester.analyze_results(results)
    
    # Сохраняем результаты
    tester.save_results(results)
    
    if tester.working_proxies:
        print(f"\n🎉 НАЙДЕНО {len(tester.working_proxies)} РАБОЧИХ ПРОКСИ!")
        print("Теперь можно запускать:")
        print("  python3 main.py")
    else:
        print("\n❌ РАБОЧИЕ ПРОКСИ НЕ НАЙДЕНЫ")
        print("Возможные решения:")
        print("  1. Попробовать другие источники прокси")
        print("  2. Использовать платные прокси")
        print("  3. Настроить TOR или WARP")
        print("  4. Использовать Selenium без прокси")

if __name__ == "__main__":
    asyncio.run(main())
