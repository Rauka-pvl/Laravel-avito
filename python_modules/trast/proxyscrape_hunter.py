#!/usr/bin/env python3
"""
Специальный скрипт для получения всех типов прокси из ProxyScrape API
и тестирования российских прокси
"""

import asyncio
import sys
import os
import json
import time
import random
from datetime import datetime
from typing import List, Set, Dict, Tuple
import httpx
import requests

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logger_setup import setup_logger

class ProxyScrapeHunter:
    """Охотник за прокси из ProxyScrape API."""
    
    def __init__(self):
        self.logger = setup_logger("proxyscrape_hunter")
        self.all_proxies = {}
        self.russian_proxies = []
        self.working_proxies = []
    
    async def fetch_all_proxy_types(self):
        """Получает все типы прокси из ProxyScrape API."""
        self.logger.info("🌐 Получаем все типы прокси из ProxyScrape API...")
        
        # Все возможные протоколы и таймауты
        protocols = ['http', 'https', 'socks4', 'socks5']
        timeouts = [1000, 1500, 2000, 3000, 5000]
        
        base_url = "https://api.proxyscrape.com/v2/"
        
        for protocol in protocols:
            self.logger.info(f"📡 Получаем {protocol.upper()} прокси...")
            
            protocol_proxies = set()
            
            for timeout in timeouts:
                try:
                    url = f"{base_url}?request=displayproxies&protocol={protocol}&timeout={timeout}&country=all"
                    self.logger.debug(f"Запрос: {url}")
                    
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(url)
                        
                        if response.status_code == 200:
                            text = response.text.strip()
                            if text:
                                proxies = [line.strip() for line in text.split('\n') if line.strip() and ':' in line]
                                protocol_proxies.update(proxies)
                                self.logger.info(f"  ✅ {protocol} timeout={timeout}: {len(proxies)} прокси")
                            else:
                                self.logger.warning(f"  ⚠️ {protocol} timeout={timeout}: пустой ответ")
                        else:
                            self.logger.warning(f"  ❌ {protocol} timeout={timeout}: HTTP {response.status_code}")
                            
                except Exception as e:
                    self.logger.warning(f"  ❌ {protocol} timeout={timeout}: {e}")
                
                # Небольшая пауза между запросами
                await asyncio.sleep(0.5)
            
            self.all_proxies[protocol] = list(protocol_proxies)
            self.logger.info(f"📊 {protocol.upper()}: {len(protocol_proxies)} уникальных прокси")
        
        # Подсчитываем общее количество
        total_proxies = sum(len(proxies) for proxies in self.all_proxies.values())
        self.logger.info(f"🎯 ВСЕГО ПОЛУЧЕНО: {total_proxies} прокси всех типов")
        
        return self.all_proxies
    
    async def identify_russian_proxies(self, max_test: int = 1000):
        """Определяет российские прокси по IP-адресам."""
        self.logger.info("🇷🇺 Определяем российские прокси...")
        
        # Собираем все прокси для проверки
        all_proxies = []
        for protocol, proxies in self.all_proxies.items():
            for proxy in proxies:
                all_proxies.append((proxy, protocol))
        
        # Перемешиваем и берем случайную выборку
        random.shuffle(all_proxies)
        test_proxies = all_proxies[:max_test]
        
        self.logger.info(f"🔍 Тестируем {len(test_proxies)} прокси для определения страны...")
        
        russian_count = 0
        
        for i, (proxy, protocol) in enumerate(test_proxies):
            if i % 50 == 0:
                self.logger.info(f"📊 Проверено {i}/{len(test_proxies)} прокси, найдено российских: {russian_count}")
            
            try:
                # Проверяем IP через ipinfo.io
                ip_address = proxy.split(':')[0]
                
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"https://ipinfo.io/{ip_address}/json")
                    
                    if response.status_code == 200:
                        data = response.json()
                        country = data.get('country', '').upper()
                        
                        if country == 'RU':
                            self.russian_proxies.append({
                                'proxy': proxy,
                                'protocol': protocol,
                                'ip': ip_address,
                                'country': country,
                                'city': data.get('city', ''),
                                'region': data.get('region', ''),
                                'org': data.get('org', '')
                            })
                            russian_count += 1
                            self.logger.info(f"🇷🇺 Найден российский прокси: {proxy} ({data.get('city', 'Unknown')})")
                
            except Exception as e:
                self.logger.debug(f"Ошибка проверки {proxy}: {e}")
            
            # Пауза между запросами
            await asyncio.sleep(0.1)
        
        self.logger.info(f"🎉 НАЙДЕНО РОССИЙСКИХ ПРОКСИ: {len(self.russian_proxies)}")
        return self.russian_proxies
    
    async def test_russian_proxies(self):
        """Тестирует российские прокси на работоспособность."""
        if not self.russian_proxies:
            self.logger.warning("❌ Нет российских прокси для тестирования")
            return []
        
        self.logger.info(f"🧪 Тестируем {len(self.russian_proxies)} российских прокси...")
        
        working_count = 0
        
        for i, proxy_data in enumerate(self.russian_proxies):
            proxy = proxy_data['proxy']
            protocol = proxy_data['protocol']
            
            if i % 10 == 0:
                self.logger.info(f"📊 Протестировано {i}/{len(self.russian_proxies)}, рабочих: {working_count}")
            
            try:
                # Формируем URL прокси в зависимости от протокола
                if protocol in ['http', 'https']:
                    proxy_url = f"http://{proxy}"
                elif protocol == 'socks4':
                    proxy_url = f"socks4://{proxy}"
                elif protocol == 'socks5':
                    proxy_url = f"socks5://{proxy}"
                else:
                    continue
                
                # Тестируем прокси
                async with httpx.AsyncClient(
                    proxy=proxy_url,
                    timeout=httpx.Timeout(5.0, connect=3.0),
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                    verify=False
                ) as client:
                    # Тестируем на разных сайтах
                    test_urls = [
                        "http://httpbin.org/ip",
                        "https://www.google.com",
                        "https://trast-zapchast.ru"
                    ]
                    
                    success = False
                    response_time = 0
                    
                    for test_url in test_urls:
                        try:
                            start_time = time.time()
                            response = await client.get(test_url)
                            response_time = time.time() - start_time
                            
                            if response.status_code == 200:
                                success = True
                                break
                        except:
                            continue
                    
                    if success:
                        proxy_data['working'] = True
                        proxy_data['response_time'] = response_time
                        proxy_data['test_url'] = test_url
                        self.working_proxies.append(proxy_data)
                        working_count += 1
                        
                        self.logger.info(f"✅ Рабочий российский прокси: {proxy} ({response_time:.3f}s)")
                    else:
                        proxy_data['working'] = False
                
            except Exception as e:
                proxy_data['working'] = False
                self.logger.debug(f"Прокси {proxy} не работает: {e}")
            
            # Пауза между тестами
            await asyncio.sleep(0.2)
        
        self.logger.info(f"🎉 РАБОЧИХ РОССИЙСКИХ ПРОКСИ: {len(self.working_proxies)}")
        return self.working_proxies
    
    async def save_results(self):
        """Сохраняет результаты в файлы."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Сохраняем все прокси по типам
        all_proxies_file = f"proxyscrape_all_proxies_{timestamp}.json"
        with open(all_proxies_file, 'w', encoding='utf-8') as f:
            json.dump(self.all_proxies, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Сохранены все прокси в {all_proxies_file}")
        
        # Сохраняем российские прокси
        if self.russian_proxies:
            russian_file = f"russian_proxies_{timestamp}.json"
            with open(russian_file, 'w', encoding='utf-8') as f:
                json.dump(self.russian_proxies, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"🇷🇺 Сохранены российские прокси в {russian_file}")
            
            # Создаем простой текстовый файл для сервера
            russian_txt = f"russian_proxies_{timestamp}.txt"
            with open(russian_txt, 'w', encoding='utf-8') as f:
                for proxy_data in self.russian_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            self.logger.info(f"📄 Создан текстовый файл: {russian_txt}")
        
        # Сохраняем рабочие прокси
        if self.working_proxies:
            working_file = f"working_russian_proxies_{timestamp}.json"
            with open(working_file, 'w', encoding='utf-8') as f:
                json.dump(self.working_proxies, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"✅ Сохранены рабочие прокси в {working_file}")
            
            # Создаем файл для парсера
            working_txt = f"working_proxies_{timestamp}.txt"
            with open(working_txt, 'w', encoding='utf-8') as f:
                for proxy_data in self.working_proxies:
                    f.write(f"{proxy_data['proxy']}\n")
            
            self.logger.info(f"🚀 Создан файл для парсера: {working_txt}")
    
    def print_statistics(self):
        """Выводит статистику."""
        self.logger.info("=" * 60)
        self.logger.info("📊 СТАТИСТИКА PROXYSCRAPE HUNTER")
        self.logger.info("=" * 60)
        
        for protocol, proxies in self.all_proxies.items():
            self.logger.info(f"  {protocol.upper()}: {len(proxies)} прокси")
        
        total_proxies = sum(len(proxies) for proxies in self.all_proxies.values())
        self.logger.info(f"  ВСЕГО: {total_proxies} прокси")
        
        self.logger.info(f"🇷🇺 Российских прокси: {len(self.russian_proxies)}")
        self.logger.info(f"✅ Рабочих российских прокси: {len(self.working_proxies)}")
        
        if self.working_proxies:
            self.logger.info("🏆 ТОП-10 РАБОЧИХ РОССИЙСКИХ ПРОКСИ:")
            sorted_proxies = sorted(self.working_proxies, key=lambda x: x.get('response_time', 999))
            for i, proxy_data in enumerate(sorted_proxies[:10]):
                self.logger.info(f"  {i+1}. {proxy_data['proxy']} - {proxy_data.get('response_time', 0):.3f}s - {proxy_data.get('city', 'Unknown')}")

async def main():
    """Основная функция."""
    hunter = ProxyScrapeHunter()
    
    print("🇷🇺 PROXYSCRAPE HUNTER - ПОИСК РОССИЙСКИХ ПРОКСИ")
    print("=" * 60)
    
    # Шаг 1: Получаем все типы прокси
    await hunter.fetch_all_proxy_types()
    
    # Шаг 2: Определяем российские прокси
    await hunter.identify_russian_proxies(max_test=2000)
    
    # Шаг 3: Тестируем российские прокси
    await hunter.test_russian_proxies()
    
    # Шаг 4: Сохраняем результаты
    await hunter.save_results()
    
    # Шаг 5: Выводим статистику
    hunter.print_statistics()
    
    print("\n🎉 ПОИСК ЗАВЕРШЕН!")

if __name__ == "__main__":
    asyncio.run(main())
