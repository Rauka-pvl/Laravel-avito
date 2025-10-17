#!/usr/bin/env python3
"""
Тестирование прокси на реальную загрузку страницы сайта
"""

import asyncio
import sys
import os
import json
import time
import random
from typing import List, Dict, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class RealPageProxyTester:
    """Тестирует прокси на реальную загрузку страницы сайта."""
    
    def __init__(self):
        self.logger = setup_logger("real_page_proxy_tester")
        self.working_proxies = []
        self.test_results = []
        self.total_tested = 0
    
    def load_all_proxies(self) -> List[str]:
        """Загружает ВСЕ доступные прокси."""
        all_proxies = set()
        
        # Загружаем из всех возможных файлов
        import glob
        patterns = [
            "working_proxies.json",
            "working_proxies_*.json",
            "proxies_for_server_*.txt",
            "working_russian_proxies_*.json",
            "all_working_proxies_*.json",
            "all_working_proxies.txt",
            "continuous_working_proxies_*.json",
            "continuous_working_proxies.txt"
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
    
    async def test_proxy_real_page(self, proxy: str) -> Dict:
        """Тестирует прокси на реальную загрузку страницы сайта."""
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(15.0, connect=10.0),  # Увеличиваем таймауты
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False,
                follow_redirects=True
            ) as client:
                start_time = time.time()
                
                # Тестируем против РЕАЛЬНОЙ страницы сайта
                response = await client.get(TrastConfig.SHOP_URL)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    content = response.text
                    content_length = len(content)
                    
                    # Проверяем на Cloudflare блокировку
                    content_lower = content.lower()
                    cloudflare_indicators = ['checking your browser', 'ddos protection', 'cloudflare', 'ray id']
                    
                    if any(indicator in content_lower for indicator in cloudflare_indicators):
                        return {
                            'proxy': proxy,
                            'success': False,
                            'response_time': response_time,
                            'error': 'Cloudflare blocked',
                            'content_length': content_length
                        }
                    
                    # Проверяем, что это реальная страница с товарами
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Ищем элементы, указывающие на реальную страницу магазина
                    product_indicators = [
                        soup.find_all(class_=lambda x: x and 'product' in x.lower()),
                        soup.find_all(class_=lambda x: x and 'item' in x.lower()),
                        soup.find_all(class_=lambda x: x and 'card' in x.lower()),
                        soup.find_all('div', {'data-product': True}),
                        soup.find_all('div', {'data-id': True})
                    ]
                    
                    # Ищем пагинацию
                    pagination_indicators = [
                        soup.find_all(class_=lambda x: x and 'page' in x.lower()),
                        soup.find_all(class_=lambda x: x and 'pagination' in x.lower()),
                        soup.find_all('a', href=lambda x: x and 'page' in x.lower()),
                        soup.find_all('a', href=lambda x: x and 'paged' in x.lower())
                    ]
                    
                    # Проверяем наличие товаров или пагинации
                    has_products = any(len(indicators) > 0 for indicators in product_indicators)
                    has_pagination = any(len(indicators) > 0 for indicators in pagination_indicators)
                    
                    # Проверяем минимальную длину контента
                    if content_length < 10000:  # Минимум 10KB для реальной страницы
                        return {
                            'proxy': proxy,
                            'success': False,
                            'response_time': response_time,
                            'error': f'Content too short: {content_length} chars',
                            'content_length': content_length
                        }
                    
                    # Если есть товары или пагинация - это рабочая страница
                    if has_products or has_pagination:
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
                        
                        # Пытаемся найти количество страниц
                        page_count = self._extract_page_count(soup)
                        
                        return {
                            'proxy': proxy,
                            'success': True,
                            'response_time': response_time,
                            'ip_address': ip_address,
                            'content_length': content_length,
                            'has_products': has_products,
                            'has_pagination': has_pagination,
                            'page_count': page_count
                        }
                    else:
                        return {
                            'proxy': proxy,
                            'success': False,
                            'response_time': response_time,
                            'error': 'No products or pagination found',
                            'content_length': content_length
                        }
                else:
                    return {
                        'proxy': proxy,
                        'success': False,
                        'response_time': response_time,
                        'error': f'HTTP {response.status_code}',
                        'content_length': len(response.text) if response.text else 0
                    }
                    
        except Exception as e:
            return {
                'proxy': proxy,
                'success': False,
                'response_time': 0,
                'error': str(e),
                'content_length': 0
            }
    
    def _extract_page_count(self, soup: BeautifulSoup) -> Optional[int]:
        """Извлекает количество страниц из HTML."""
        try:
            # Ищем ссылку "Последняя страница"
            last_page_link = soup.find('a', class_=lambda x: x and 'last' in x.lower())
            if last_page_link:
                href = last_page_link.get('href', '')
                if 'paged=' in href:
                    page_num = href.split('paged=')[1].split('&')[0]
                    return int(page_num)
            
            # Ищем пагинацию с номерами страниц
            page_links = soup.find_all('a', href=lambda x: x and 'paged=' in x)
            if page_links:
                max_page = 0
                for link in page_links:
                    href = link.get('href', '')
                    if 'paged=' in href:
                        try:
                            page_num = int(href.split('paged=')[1].split('&')[0])
                            max_page = max(max_page, page_num)
                        except:
                            continue
                if max_page > 0:
                    return max_page
            
            # Ищем текст с количеством страниц
            page_text = soup.find_all(text=lambda x: x and 'страниц' in x.lower())
            for text in page_text:
                import re
                numbers = re.findall(r'\d+', text)
                if numbers:
                    return int(numbers[-1])
            
            return None
        except:
            return None
    
    async def test_all_proxies_real_page(self, proxies: List[str]) -> List[Dict]:
        """Тестирует все прокси на реальную загрузку страницы."""
        self.logger.info(f"🧪 Тестируем {len(proxies)} прокси на реальную загрузку страницы...")
        
        # Тестируем батчами по 10 (меньше батчи для реальных страниц)
        batch_size = 10
        all_results = []
        
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(proxies) + batch_size - 1) // batch_size
            
            self.logger.info(f"📦 Батч {batch_num}/{total_batches}: тестируем {len(batch)} прокси")
            
            # Тестируем батч параллельно
            tasks = [self.test_proxy_real_page(proxy) for proxy in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for j, result in enumerate(batch_results):
                proxy = batch[j]
                if isinstance(result, Exception):
                    result = {
                        'proxy': proxy,
                        'success': False,
                        'response_time': 0,
                        'error': str(result),
                        'content_length': 0
                    }
                
                all_results.append(result)
                self.total_tested += 1
                
                if result['success']:
                    self.working_proxies.append(result)
                    self.logger.info(f"✅ РЕАЛЬНО РАБОЧИЙ ПРОКСИ: {proxy} ({result['response_time']:.3f}s, {result['content_length']} chars)")
                    if result.get('page_count'):
                        self.logger.info(f"   📄 Найдено страниц: {result['page_count']}")
                else:
                    self.logger.debug(f"❌ Прокси {proxy} не работает: {result.get('error', 'Unknown error')}")
            
            # Пауза между батчами
            if i + batch_size < len(proxies):
                await asyncio.sleep(2)
        
        return all_results
    
    def analyze_results(self, results: List[Dict]):
        """Анализирует результаты тестирования."""
        total_tests = len(results)
        working_count = len(self.working_proxies)
        
        self.logger.info("📊 АНАЛИЗ РЕЗУЛЬТАТОВ РЕАЛЬНОГО ТЕСТИРОВАНИЯ")
        self.logger.info("=" * 60)
        self.logger.info(f"📊 Всего тестов: {total_tests}")
        self.logger.info(f"✅ Реально рабочих прокси: {working_count}")
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
        
        # Показываем реально рабочие прокси
        if self.working_proxies:
            self.logger.info("🏆 РЕАЛЬНО РАБОЧИЕ ПРОКСИ:")
            sorted_proxies = sorted(self.working_proxies, key=lambda x: x['response_time'])
            for i, proxy_data in enumerate(sorted_proxies):
                page_info = f", страниц: {proxy_data.get('page_count', 'неизвестно')}" if proxy_data.get('page_count') else ""
                self.logger.info(f"  {i+1}. {proxy_data['proxy']} - {proxy_data['response_time']:.3f}s - {proxy_data['content_length']} chars{page_info}")
    
    def save_results(self, results: List[Dict]):
        """Сохраняет результаты тестирования."""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем все результаты
        results_file = f"real_page_proxy_test_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                'test_results': results,
                'working_proxies': self.working_proxies,
                'total_tested': self.total_tested,
                'timestamp': timestamp,
                'target_site': TrastConfig.SHOP_URL
            }, f, indent=2, ensure_ascii=False)
        
        # Сохраняем только реально рабочие прокси
        if self.working_proxies:
            working_file = f"real_working_proxies_{timestamp}.json"
            with open(working_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'proxies': [p['proxy'] for p in self.working_proxies],
                    'count': len(self.working_proxies),
                    'timestamp': timestamp,
                    'source': 'real_page_proxy_tester'
                }, f, indent=2, ensure_ascii=False)
            
            # Создаем простой файл
            with open("real_working_proxies.txt", 'w', encoding='utf-8') as f:
                for proxy_data in self.working_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            self.logger.info(f"💾 Сохранены реально рабочие прокси в {working_file}")
        
        self.logger.info(f"📄 Результаты тестирования сохранены в {results_file}")

async def main():
    """Основная функция тестирования прокси на реальную загрузку страницы."""
    tester = RealPageProxyTester()
    
    print("🧪 ТЕСТИРОВАНИЕ ПРОКСИ НА РЕАЛЬНУЮ ЗАГРУЗКУ СТРАНИЦЫ")
    print("=" * 60)
    
    # Загружаем все прокси
    all_proxies = tester.load_all_proxies()
    
    if not all_proxies:
        print("❌ Не найдены прокси для тестирования")
        return
    
    print(f"📊 Найдено {len(all_proxies)} прокси для тестирования")
    print("🔍 Тестируем каждый прокси на реальную загрузку страницы сайта...")
    
    # Тестируем все прокси на реальную загрузку страницы
    results = await tester.test_all_proxies_real_page(all_proxies)
    
    # Анализируем результаты
    tester.analyze_results(results)
    
    # Сохраняем результаты
    tester.save_results(results)
    
    if tester.working_proxies:
        print(f"\n🎉 НАЙДЕНО {len(tester.working_proxies)} РЕАЛЬНО РАБОЧИХ ПРОКСИ!")
        print("Эти прокси могут загружать реальные страницы сайта с товарами!")
        print("Теперь можно запускать:")
        print("  python3 main.py")
    else:
        print("\n❌ РЕАЛЬНО РАБОЧИЕ ПРОКСИ НЕ НАЙДЕНЫ")
        print("Ни один прокси не может загрузить реальную страницу сайта")
        print("Возможные решения:")
        print("  1. Попробовать другие источники прокси")
        print("  2. Использовать платные прокси")
        print("  3. Настроить TOR или WARP")
        print("  4. Использовать Selenium без прокси")

if __name__ == "__main__":
    asyncio.run(main())
