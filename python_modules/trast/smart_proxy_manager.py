#!/usr/bin/env python3
"""
Система управления прокси с автоматическим переключением
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

class ProxyManager:
    """Управляет прокси с автоматическим переключением."""
    
    def __init__(self):
        self.logger = setup_logger("proxy_manager")
        self.working_proxies = []
        self.current_proxy_index = 0
        self.last_working_proxy = None
        self.failed_proxies = set()
        self.proxy_stats = {}
    
    def load_working_proxies(self) -> List[str]:
        """Загружает рабочие прокси из файлов."""
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
    
    async def test_proxy(self, proxy: str) -> Dict:
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
    
    async def find_all_working_proxies(self) -> List[Dict]:
        """Находит ВСЕ рабочие прокси."""
        self.logger.info("🔍 Поиск ВСЕХ рабочих прокси...")
        
        all_proxies = self.load_working_proxies()
        if not all_proxies:
            self.logger.error("❌ Не найдены прокси для тестирования")
            return []
        
        working_proxies = []
        total_tested = 0
        
        # Тестируем ВСЕ прокси
        for i, proxy in enumerate(all_proxies):
            total_tested += 1
            
            if i % 20 == 0:
                self.logger.info(f"📊 Тестируем прокси {i+1}/{len(all_proxies)}: {proxy}")
            
            result = await self.test_proxy(proxy)
            
            if result['success']:
                working_proxies.append(result)
                self.logger.info(f"✅ РАБОЧИЙ ПРОКСИ: {proxy} ({result['response_time']:.3f}s)")
            
            # Небольшая пауза между тестами
            await asyncio.sleep(0.1)
        
        # Сортируем по времени отклика
        working_proxies.sort(key=lambda x: x['response_time'])
        
        self.logger.info(f"📊 Найдено {len(working_proxies)} рабочих прокси из {total_tested} протестированных")
        return working_proxies
    
    def get_next_proxy(self) -> Optional[str]:
        """Возвращает следующий рабочий прокси."""
        if not self.working_proxies:
            return None
        
        # Ищем следующий рабочий прокси (не в списке failed)
        for i in range(len(self.working_proxies)):
            proxy = self.working_proxies[self.current_proxy_index]['proxy']
            
            if proxy not in self.failed_proxies:
                return proxy
            
            # Переходим к следующему прокси
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.working_proxies)
        
        # Если все прокси в failed, очищаем список и начинаем сначала
        self.logger.warning("⚠️ Все прокси в списке failed, очищаем список")
        self.failed_proxies.clear()
        self.current_proxy_index = 0
        
        if self.working_proxies:
            return self.working_proxies[0]['proxy']
        
        return None
    
    def mark_proxy_failed(self, proxy: str):
        """Помечает прокси как неработающий."""
        self.failed_proxies.add(proxy)
        self.logger.warning(f"❌ Прокси {proxy} помечен как неработающий")
    
    def mark_proxy_success(self, proxy: str, response_time: float):
        """Помечает прокси как успешно работающий."""
        if proxy in self.failed_proxies:
            self.failed_proxies.remove(proxy)
            self.logger.info(f"✅ Прокси {proxy} восстановлен")
        
        # Обновляем статистику
        if proxy not in self.proxy_stats:
            self.proxy_stats[proxy] = {'success_count': 0, 'total_time': 0}
        
        self.proxy_stats[proxy]['success_count'] += 1
        self.proxy_stats[proxy]['total_time'] += response_time
    
    def get_proxy_stats(self) -> Dict:
        """Возвращает статистику прокси."""
        return {
            'total_proxies': len(self.working_proxies),
            'failed_proxies': len(self.failed_proxies),
            'working_proxies': len(self.working_proxies) - len(self.failed_proxies),
            'current_proxy_index': self.current_proxy_index,
            'proxy_stats': self.proxy_stats
        }
    
    def save_working_proxies(self):
        """Сохраняет рабочие прокси в файл."""
        if not self.working_proxies:
            return
        
        data = {
            'proxies': [p['proxy'] for p in self.working_proxies],
            'count': len(self.working_proxies),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'proxy_manager',
            'failed_proxies': list(self.failed_proxies),
            'proxy_stats': self.proxy_stats
        }
        
        with open("working_proxies.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Сохранено {len(self.working_proxies)} рабочих прокси")

async def main():
    """Основная функция управления прокси."""
    manager = ProxyManager()
    
    print("🔧 УПРАВЛЕНИЕ ПРОКСИ С АВТОМАТИЧЕСКИМ ПЕРЕКЛЮЧЕНИЕМ")
    print("=" * 60)
    
    # Находим все рабочие прокси
    working_proxies = await manager.find_all_working_proxies()
    
    if not working_proxies:
        print("❌ Не найдены рабочие прокси")
        return
    
    manager.working_proxies = working_proxies
    manager.save_working_proxies()
    
    print(f"\n🎉 НАЙДЕНО {len(working_proxies)} РАБОЧИХ ПРОКСИ!")
    print("📋 Список рабочих прокси:")
    for i, proxy_data in enumerate(working_proxies):
        print(f"  {i+1}. {proxy_data['proxy']} - {proxy_data['response_time']:.3f}s - {proxy_data['ip_address']}")
    
    # Показываем статистику
    stats = manager.get_proxy_stats()
    print(f"\n📊 Статистика:")
    print(f"  Всего прокси: {stats['total_proxies']}")
    print(f"  Рабочих: {stats['working_proxies']}")
    print(f"  Не рабочих: {stats['failed_proxies']}")
    
    print("\nТеперь можно запускать:")
    print("  python3 main.py")

if __name__ == "__main__":
    asyncio.run(main())
