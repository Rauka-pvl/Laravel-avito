#!/usr/bin/env python3
"""
Диагностика проблем с прокси и поиск работающих решений
"""

import asyncio
import sys
import os
import json
import random
import time
from typing import List, Dict, Optional, Tuple
import httpx
import requests

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class ProxyDiagnostic:
    """Диагностика проблем с прокси."""
    
    def __init__(self):
        self.logger = setup_logger("proxy_diagnostic")
        self.test_results = []
        self.working_proxies = []
    
    async def test_direct_connection(self):
        """Тестирует прямое подключение без прокси."""
        self.logger.info("🔍 Тестируем прямое подключение к сайту...")
        
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False
            ) as client:
                start_time = time.time()
                response = await client.get(TrastConfig.SHOP_URL)
                response_time = time.time() - start_time
                
                self.logger.info(f"📊 Прямое подключение:")
                self.logger.info(f"  Статус: {response.status_code}")
                self.logger.info(f"  Время: {response_time:.3f}s")
                self.logger.info(f"  Длина контента: {len(response.text)} символов")
                
                if response.status_code == 200:
                    content = response.text.lower()
                    if 'cloudflare' in content or 'checking your browser' in content:
                        self.logger.warning("⚠️ Cloudflare блокирует прямое подключение")
                        return False
                    else:
                        self.logger.info("✅ Прямое подключение работает!")
                        return True
                else:
                    self.logger.warning(f"⚠️ Прямое подключение не работает: HTTP {response.status_code}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка прямого подключения: {e}")
            return False
    
    async def test_proxy_types(self):
        """Тестирует разные типы прокси."""
        self.logger.info("🧪 Тестируем разные типы прокси...")
        
        # Получаем прокси из разных источников
        proxy_sources = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1000&country=all",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt"
        ]
        
        all_proxies = set()
        
        for source in proxy_sources:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(source)
                    if response.status_code == 200:
                        proxies = [line.strip() for line in response.text.split('\n') 
                                 if line.strip() and ':' in line]
                        all_proxies.update(proxies)
                        self.logger.info(f"📡 Получено {len(proxies)} прокси из {source}")
            except Exception as e:
                self.logger.warning(f"⚠️ Ошибка получения прокси из {source}: {e}")
        
        self.logger.info(f"📊 Всего получено {len(all_proxies)} прокси")
        
        # Тестируем случайные прокси
        test_proxies = random.sample(list(all_proxies), min(100, len(all_proxies)))
        
        for i, proxy in enumerate(test_proxies):
            if i % 20 == 0:
                self.logger.info(f"📊 Тестируем прокси {i+1}/{len(test_proxies)}")
            
            result = await self._test_single_proxy(proxy)
            self.test_results.append(result)
            
            if result['success']:
                self.working_proxies.append(result)
                self.logger.info(f"✅ РАБОЧИЙ ПРОКСИ: {proxy}")
            
            # Пауза между тестами
            await asyncio.sleep(0.1)
        
        self.logger.info(f"📊 РЕЗУЛЬТАТЫ: {len(self.working_proxies)}/{len(test_proxies)} рабочих прокси")
        return self.working_proxies
    
    async def _test_single_proxy(self, proxy: str) -> Dict:
        """Тестирует один прокси."""
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(5.0, connect=3.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False
            ) as client:
                start_time = time.time()
                
                # Тестируем против простого сайта
                response = await client.get("http://httpbin.org/ip")
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        ip_address = data.get('origin', 'unknown')
                        
                        # Теперь тестируем против целевого сайта
                        target_response = await client.get(TrastConfig.SHOP_URL)
                        
                        if target_response.status_code == 200:
                            content = target_response.text.lower()
                            if 'cloudflare' in content or 'checking your browser' in content:
                                return {
                                    'proxy': proxy,
                                    'success': False,
                                    'response_time': response_time,
                                    'ip_address': ip_address,
                                    'error': 'Cloudflare blocked',
                                    'target_status': target_response.status_code
                                }
                            else:
                                return {
                                    'proxy': proxy,
                                    'success': True,
                                    'response_time': response_time,
                                    'ip_address': ip_address,
                                    'target_status': target_response.status_code,
                                    'content_length': len(target_response.text)
                                }
                        else:
                            return {
                                'proxy': proxy,
                                'success': False,
                                'response_time': response_time,
                                'ip_address': ip_address,
                                'error': f'Target site HTTP {target_response.status_code}',
                                'target_status': target_response.status_code
                            }
                    except:
                        return {
                            'proxy': proxy,
                            'success': False,
                            'response_time': response_time,
                            'error': 'JSON parse error'
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
    
    def analyze_results(self):
        """Анализирует результаты тестирования."""
        self.logger.info("📊 АНАЛИЗ РЕЗУЛЬТАТОВ")
        self.logger.info("=" * 50)
        
        total_tests = len(self.test_results)
        working_count = len(self.working_proxies)
        
        self.logger.info(f"📊 Всего тестов: {total_tests}")
        self.logger.info(f"✅ Рабочих прокси: {working_count}")
        self.logger.info(f"❌ Не рабочих: {total_tests - working_count}")
        
        if total_tests > 0:
            success_rate = (working_count / total_tests) * 100
            self.logger.info(f"📈 Процент успеха: {success_rate:.1f}%")
        
        # Анализируем ошибки
        error_counts = {}
        for result in self.test_results:
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
            for i, proxy_data in enumerate(sorted_proxies[:10]):
                self.logger.info(f"  {i+1}. {proxy_data['proxy']} - {proxy_data['response_time']:.3f}s - {proxy_data['ip_address']}")
    
    def save_results(self):
        """Сохраняет результаты диагностики."""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем все результаты
        results_file = f"proxy_diagnostic_results_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                'test_results': self.test_results,
                'working_proxies': self.working_proxies,
                'timestamp': timestamp,
                'target_site': TrastConfig.SHOP_URL
            }, f, indent=2, ensure_ascii=False)
        
        # Сохраняем рабочие прокси
        if self.working_proxies:
            working_file = f"working_proxies_{timestamp}.json"
            with open(working_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'proxies': [p['proxy'] for p in self.working_proxies],
                    'count': len(self.working_proxies),
                    'timestamp': timestamp,
                    'source': 'proxy_diagnostic'
                }, f, indent=2, ensure_ascii=False)
            
            # Создаем простой файл
            with open("working_proxies.txt", 'w', encoding='utf-8') as f:
                for proxy_data in self.working_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            self.logger.info(f"💾 Сохранены рабочие прокси в {working_file}")
        
        self.logger.info(f"📄 Результаты диагностики сохранены в {results_file}")

async def main():
    """Основная функция диагностики."""
    diagnostic = ProxyDiagnostic()
    
    print("🔍 ДИАГНОСТИКА ПРОКСИ")
    print("=" * 50)
    
    # Шаг 1: Тестируем прямое подключение
    direct_works = await diagnostic.test_direct_connection()
    
    if not direct_works:
        print("\n⚠️ Прямое подключение не работает!")
        print("Возможные причины:")
        print("  1. Сайт заблокирован Cloudflare")
        print("  2. Проблемы с сетью")
        print("  3. Сайт недоступен")
        print("\nПопробуйте:")
        print("  1. Проверить доступность сайта в браузере")
        print("  2. Использовать VPN")
        print("  3. Попробовать другой сайт для тестирования")
        return
    
    print("\n✅ Прямое подключение работает!")
    print("Тестируем прокси...")
    
    # Шаг 2: Тестируем прокси
    working_proxies = await diagnostic.test_proxy_types()
    
    # Шаг 3: Анализируем результаты
    diagnostic.analyze_results()
    
    # Шаг 4: Сохраняем результаты
    diagnostic.save_results()
    
    if working_proxies:
        print(f"\n🎉 НАЙДЕНО {len(working_proxies)} РАБОЧИХ ПРОКСИ!")
        print("Теперь можно запускать:")
        print("  python3 main.py")
    else:
        print("\n❌ РАБОЧИЕ ПРОКСИ НЕ НАЙДЕНЫ")
        print("\nВозможные решения:")
        print("  1. Попробовать другие источники прокси")
        print("  2. Использовать платные прокси")
        print("  3. Настроить TOR или WARP")
        print("  4. Использовать Selenium без прокси")

if __name__ == "__main__":
    asyncio.run(main())
