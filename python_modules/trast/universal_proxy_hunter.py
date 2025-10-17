#!/usr/bin/env python3
"""
Мощный универсальный охотник за прокси
Получает ВСЕ возможные прокси, определяет страну, тестирует максимально
"""

import asyncio
import sys
import os
import json
import time
import random
from typing import List, Dict, Optional, Set, Tuple
import httpx
from bs4 import BeautifulSoup

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger

class UniversalProxyHunter:
    """Универсальный охотник за прокси."""
    
    def __init__(self):
        self.logger = setup_logger("universal_proxy_hunter")
        self.all_proxies = set()
        self.working_proxies = []
        self.proxy_countries = {}
        self.test_results = []
        self.total_tested = 0
        self.max_proxies_to_test = 50000  # Максимум прокси для тестирования
        
        # Расширенный список источников прокси
        self.proxy_sources = [
            # Основные источники
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1000&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1500&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=2000&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all",
            
            # GitHub источники
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTP_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
            
            # Другие источники
            "https://www.proxy-list.download/api/v1/get?type=http",
            "https://www.proxy-list.download/api/v1/get?type=https",
            "https://www.proxy-list.download/api/v1/get?type=socks4",
            "https://www.proxy-list.download/api/v1/get?type=socks5",
            "https://openproxylist.xyz/http.txt",
            "https://openproxylist.xyz/https.txt",
            "https://openproxylist.xyz/socks4.txt",
            "https://openproxylist.xyz/socks5.txt",
            
            # Дополнительные источники
            "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt",
            "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/https.txt",
            "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks4.txt",
            "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt",
            "https://raw.githubusercontent.com/Anonym0usWork1221/Proxyless/main/http.txt",
            "https://raw.githubusercontent.com/Anonym0usWork1221/Proxyless/main/https.txt",
            "https://raw.githubusercontent.com/Anonym0usWork1221/Proxyless/main/socks4.txt",
            "https://raw.githubusercontent.com/Anonym0usWork1221/Proxyless/main/socks5.txt",
        ]
    
    async def fetch_all_proxies(self) -> Set[str]:
        """Получает ВСЕ возможные прокси из всех источников."""
        self.logger.info(f"🌐 Получаем прокси из {len(self.proxy_sources)} источников...")
        
        all_proxies = set()
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), verify=False) as client:
            for i, source_url in enumerate(self.proxy_sources):
                try:
                    self.logger.info(f"📡 Источник {i+1}/{len(self.proxy_sources)}: {source_url}")
                    
                    response = await client.get(source_url)
                    if response.status_code == 200:
                        text = response.text
                        
                        # Парсим прокси из текста
                        proxies = self._parse_proxies_from_text(text, source_url)
                        all_proxies.update(proxies)
                        
                        self.logger.info(f"✅ Получено {len(proxies)} прокси из {source_url}")
                    else:
                        self.logger.warning(f"⚠️ {source_url}: HTTP {response.status_code}")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️ {source_url}: {e}")
                
                # Небольшая пауза между запросами
                await asyncio.sleep(0.5)
        
        self.logger.info(f"📊 Всего получено {len(all_proxies)} уникальных прокси")
        return all_proxies
    
    def _parse_proxies_from_text(self, text: str, source_url: str) -> Set[str]:
        """Парсит прокси из текста."""
        proxies = set()
        
        for line in text.split('\n'):
            line = line.strip()
            if line and ':' in line and not line.startswith('#'):
                # Проверяем формат IP:PORT
                parts = line.split(':')
                if len(parts) == 2:
                    ip, port = parts
                    if self._is_valid_ip(ip) and self._is_valid_port(port):
                        proxies.add(line)
        
        return proxies
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Проверяет валидность IP адреса."""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not part.isdigit() or int(part) < 0 or int(part) > 255:
                    return False
            return True
        except:
            return False
    
    def _is_valid_port(self, port: str) -> bool:
        """Проверяет валидность порта."""
        try:
            port_num = int(port)
            return 1 <= port_num <= 65535
        except:
            return False
    
    async def get_proxy_country(self, proxy: str) -> Optional[str]:
        """Определяет страну прокси."""
        try:
            ip = proxy.split(':')[0]
            
            # Используем ip-api.com для определения страны
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0), verify=False) as client:
                response = await client.get(f"http://ip-api.com/json/{ip}")
                if response.status_code == 200:
                    data = response.json()
                    country = data.get('country', 'Unknown')
                    country_code = data.get('countryCode', 'Unknown')
                    return f"{country} ({country_code})"
        except Exception as e:
            self.logger.debug(f"Не удалось определить страну для {proxy}: {e}")
        
        return "Unknown"
    
    async def test_proxy_real_page(self, proxy: str) -> Dict:
        """Тестирует прокси на реальную загрузку страницы."""
        try:
            proxy_url = f"http://{proxy}"
            
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(15.0, connect=10.0),
                headers=TrastConfig.get_headers_with_user_agent(),
                verify=False,
                follow_redirects=True
            ) as client:
                start_time = time.time()
                
                # Тестируем против реальной страницы сайта
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
                            'content_length': content_length,
                            'country': 'Unknown'
                        }
                    
                    # Проверяем минимальную длину контента
                    if content_length < 10000:  # Минимум 10KB для реальной страницы
                        return {
                            'proxy': proxy,
                            'success': False,
                            'response_time': response_time,
                            'error': f'Content too short: {content_length} chars',
                            'content_length': content_length,
                            'country': 'Unknown'
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
                    
                    # Если есть товары или пагинация - это рабочая страница
                    if has_products or has_pagination:
                        # Получаем страну прокси
                        country = await self.get_proxy_country(proxy)
                        
                        # Пытаемся найти количество страниц
                        page_count = self._extract_page_count(soup)
                        
                        return {
                            'proxy': proxy,
                            'success': True,
                            'response_time': response_time,
                            'content_length': content_length,
                            'has_products': has_products,
                            'has_pagination': has_pagination,
                            'page_count': page_count,
                            'country': country
                        }
                    else:
                        return {
                            'proxy': proxy,
                            'success': False,
                            'response_time': response_time,
                            'error': 'No products or pagination found',
                            'content_length': content_length,
                            'country': 'Unknown'
                        }
                else:
                    return {
                        'proxy': proxy,
                        'success': False,
                        'response_time': response_time,
                        'error': f'HTTP {response.status_code}',
                        'content_length': len(response.text) if response.text else 0,
                        'country': 'Unknown'
                    }
                    
        except Exception as e:
            return {
                'proxy': proxy,
                'success': False,
                'response_time': 0,
                'error': str(e),
                'content_length': 0,
                'country': 'Unknown'
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
            
            return None
        except:
            return None
    
    async def test_all_proxies(self, proxies: List[str]) -> List[Dict]:
        """Тестирует все прокси на реальную загрузку страницы."""
        self.logger.info(f"🧪 Начинаем тестирование {len(proxies)} прокси...")
        
        # Ограничиваем количество тестируемых прокси
        if len(proxies) > self.max_proxies_to_test:
            proxies = random.sample(proxies, self.max_proxies_to_test)
            self.logger.info(f"📊 Ограничили тестирование до {self.max_proxies_to_test} прокси")
        
        # Тестируем батчами по 20
        batch_size = 20
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
                        'content_length': 0,
                        'country': 'Unknown'
                    }
                
                all_results.append(result)
                self.total_tested += 1
                
                if result['success']:
                    self.working_proxies.append(result)
                    self.logger.info(f"✅ РАБОЧИЙ ПРОКСИ: {proxy} ({result['response_time']:.3f}s, {result['content_length']} chars, {result['country']})")
                    if result.get('page_count'):
                        self.logger.info(f"   📄 Найдено страниц: {result['page_count']}")
                else:
                    self.logger.debug(f"❌ Прокси {proxy} не работает: {result.get('error', 'Unknown error')}")
            
            # Пауза между батчами
            if i + batch_size < len(proxies):
                await asyncio.sleep(1)
        
        return all_results
    
    def analyze_results(self, results: List[Dict]):
        """Анализирует результаты тестирования."""
        total_tests = len(results)
        working_count = len(self.working_proxies)
        
        self.logger.info("📊 АНАЛИЗ РЕЗУЛЬТАТОВ УНИВЕРСАЛЬНОГО ОХОТНИКА")
        self.logger.info("=" * 60)
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
        
        # Анализируем страны
        country_counts = {}
        for result in self.working_proxies:
            country = result.get('country', 'Unknown')
            country_counts[country] = country_counts.get(country, 0) + 1
        
        if country_counts:
            self.logger.info("🌍 РАБОЧИЕ ПРОКСИ ПО СТРАНАМ:")
            for country, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True):
                self.logger.info(f"  {country}: {count} прокси")
        
        # Показываем рабочие прокси
        if self.working_proxies:
            self.logger.info("🏆 РАБОЧИЕ ПРОКСИ:")
            sorted_proxies = sorted(self.working_proxies, key=lambda x: x['response_time'])
            for i, proxy_data in enumerate(sorted_proxies):
                page_info = f", страниц: {proxy_data.get('page_count', 'неизвестно')}" if proxy_data.get('page_count') else ""
                self.logger.info(f"  {i+1}. {proxy_data['proxy']} - {proxy_data['response_time']:.3f}s - {proxy_data['content_length']} chars - {proxy_data['country']}{page_info}")
    
    def save_results(self, results: List[Dict]):
        """Сохраняет результаты тестирования."""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем все результаты
        results_file = f"universal_proxy_hunter_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                'test_results': results,
                'working_proxies': self.working_proxies,
                'total_tested': self.total_tested,
                'timestamp': timestamp,
                'target_site': TrastConfig.SHOP_URL,
                'max_proxies_tested': self.max_proxies_to_test
            }, f, indent=2, ensure_ascii=False)
        
        # Сохраняем только рабочие прокси
        if self.working_proxies:
            working_file = f"universal_working_proxies_{timestamp}.json"
            with open(working_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'proxies': [p['proxy'] for p in self.working_proxies],
                    'count': len(self.working_proxies),
                    'timestamp': timestamp,
                    'source': 'universal_proxy_hunter',
                    'countries': {p['proxy']: p['country'] for p in self.working_proxies}
                }, f, indent=2, ensure_ascii=False)
            
            # Создаем простой файл
            with open("universal_working_proxies.txt", 'w', encoding='utf-8') as f:
                for proxy_data in self.working_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            # Создаем основной файл для системы
            with open("working_proxies.json", 'w', encoding='utf-8') as f:
                json.dump({
                    'proxies': [p['proxy'] for p in self.working_proxies],
                    'count': len(self.working_proxies),
                    'timestamp': timestamp,
                    'source': 'universal_proxy_hunter',
                    'description': 'Универсальный охотник за прокси'
                }, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"💾 Сохранены рабочие прокси в {working_file}")
            self.logger.info(f"💾 Создан working_proxies.json для системы")
        
        self.logger.info(f"📄 Результаты тестирования сохранены в {results_file}")

async def main():
    """Основная функция универсального охотника за прокси."""
    hunter = UniversalProxyHunter()
    
    print("🎯 УНИВЕРСАЛЬНЫЙ ОХОТНИК ЗА ПРОКСИ")
    print("=" * 50)
    print(f"📊 Максимум прокси для тестирования: {hunter.max_proxies_to_test}")
    print("🌐 Источников прокси: 30+")
    print("🔍 Тестирование на реальную загрузку страницы")
    print("🌍 Определение страны прокси")
    print("=" * 50)
    
    # Получаем все прокси
    all_proxies = await hunter.fetch_all_proxies()
    
    if not all_proxies:
        print("❌ Не удалось получить прокси из источников")
        return
    
    print(f"📊 Получено {len(all_proxies)} уникальных прокси")
    
    # Тестируем все прокси
    results = await hunter.test_all_proxies(list(all_proxies))
    
    # Анализируем результаты
    hunter.analyze_results(results)
    
    # Сохраняем результаты
    hunter.save_results(results)
    
    if hunter.working_proxies:
        print(f"\n🎉 НАЙДЕНО {len(hunter.working_proxies)} РАБОЧИХ ПРОКСИ!")
        print("Эти прокси могут загружать реальные страницы сайта с товарами!")
        print("Система готова к использованию!")
        print("\nТеперь можно запускать:")
        print("  python3 main.py")
    else:
        print("\n❌ РАБОЧИЕ ПРОКСИ НЕ НАЙДЕНЫ")
        print("Ни один прокси не может загрузить реальную страницу сайта")

if __name__ == "__main__":
    asyncio.run(main())
