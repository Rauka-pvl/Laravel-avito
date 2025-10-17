#!/usr/bin/env python3
"""
Скрипт для интеграции найденных прокси в систему парсера
"""

import os
import sys
import json
import glob
from datetime import datetime

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logger_setup import setup_logger

class ProxyIntegrator:
    """Интегратор найденных прокси в систему."""
    
    def __init__(self):
        self.logger = setup_logger("proxy_integrator")
    
    def find_latest_proxy_files(self):
        """Находит последние файлы с прокси."""
        self.logger.info("🔍 Ищем последние файлы с прокси...")
        
        # Паттерны для поиска файлов
        patterns = [
            "working_proxies_*.txt",
            "working_russian_proxies_*.txt", 
            "proxies_for_server_*.txt",
            "verified_proxies_*.txt"
        ]
        
        found_files = {}
        
        for pattern in patterns:
            files = glob.glob(pattern)
            if files:
                # Сортируем по времени модификации (новые первыми)
                files.sort(key=os.path.getmtime, reverse=True)
                found_files[pattern] = files[0]  # Берем самый новый
                self.logger.info(f"📁 Найден файл: {files[0]}")
        
        return found_files
    
    def load_proxies_from_file(self, file_path: str) -> list:
        """Загружает прокси из файла."""
        proxies = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line and not line.startswith('#'):
                        proxies.append(line)
            
            self.logger.info(f"📊 Загружено {len(proxies)} прокси из {file_path}")
            return proxies
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки {file_path}: {e}")
            return []
    
    def create_working_proxies_file(self, proxies: list):
        """Создает файл working_proxies.json для системы."""
        if not proxies:
            self.logger.warning("❌ Нет прокси для сохранения")
            return False
        
        # Создаем структуру данных
        data = {
            "proxies": proxies,
            "count": len(proxies),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "source": "proxy_integrator",
            "description": "Интегрированные прокси из различных источников"
        }
        
        # Сохраняем в working_proxies.json
        try:
            with open("working_proxies.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"✅ Сохранено {len(proxies)} прокси в working_proxies.json")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения working_proxies.json: {e}")
            return False
    
    def backup_old_proxies(self):
        """Создает резервную копию старых прокси."""
        if os.path.exists("working_proxies.json"):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"working_proxies_backup_{timestamp}.json"
            
            try:
                import shutil
                shutil.copy2("working_proxies.json", backup_name)
                self.logger.info(f"💾 Создана резервная копия: {backup_name}")
                return True
            except Exception as e:
                self.logger.warning(f"⚠️ Не удалось создать резервную копию: {e}")
        
        return False
    
    def integrate_proxies(self):
        """Основная функция интеграции прокси."""
        self.logger.info("🚀 ИНТЕГРАЦИЯ ПРОКСИ В СИСТЕМУ")
        self.logger.info("=" * 50)
        
        # Шаг 1: Создаем резервную копию
        self.backup_old_proxies()
        
        # Шаг 2: Ищем файлы с прокси
        proxy_files = self.find_latest_proxy_files()
        
        if not proxy_files:
            self.logger.warning("❌ Не найдены файлы с прокси")
            return False
        
        # Шаг 3: Загружаем прокси из всех файлов
        all_proxies = set()  # Используем set для уникальности
        
        for pattern, file_path in proxy_files.items():
            proxies = self.load_proxies_from_file(file_path)
            all_proxies.update(proxies)
        
        # Шаг 4: Сохраняем объединенные прокси
        unique_proxies = list(all_proxies)
        
        if self.create_working_proxies_file(unique_proxies):
            self.logger.info(f"🎉 УСПЕШНО ИНТЕГРИРОВАНО {len(unique_proxies)} УНИКАЛЬНЫХ ПРОКСИ!")
            
            # Показываем статистику
            self.logger.info("📊 СТАТИСТИКА:")
            for pattern, file_path in proxy_files.items():
                file_proxies = self.load_proxies_from_file(file_path)
                self.logger.info(f"  {pattern}: {len(file_proxies)} прокси")
            
            self.logger.info(f"  ИТОГО УНИКАЛЬНЫХ: {len(unique_proxies)} прокси")
            
            return True
        else:
            self.logger.error("❌ Не удалось интегрировать прокси")
            return False
    
    def test_integration(self):
        """Тестирует интеграцию прокси."""
        self.logger.info("🧪 Тестируем интеграцию прокси...")
        
        if not os.path.exists("working_proxies.json"):
            self.logger.error("❌ Файл working_proxies.json не найден")
            return False
        
        try:
            with open("working_proxies.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            proxy_count = data.get('count', 0)
            timestamp = data.get('timestamp', 'unknown')
            
            self.logger.info(f"✅ Файл working_proxies.json содержит {proxy_count} прокси")
            self.logger.info(f"📅 Время создания: {timestamp}")
            
            # Проверяем первые несколько прокси
            proxies = data.get('proxies', [])
            if proxies:
                self.logger.info("📋 Примеры прокси:")
                for i, proxy in enumerate(proxies[:5]):
                    self.logger.info(f"  {i+1}. {proxy}")
                
                if len(proxies) > 5:
                    self.logger.info(f"  ... и еще {len(proxies) - 5} прокси")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка тестирования: {e}")
            return False

def main():
    """Основная функция."""
    integrator = ProxyIntegrator()
    
    print("🔗 ИНТЕГРАЦИЯ ПРОКСИ В СИСТЕМУ ПАРСЕРА")
    print("=" * 50)
    
    # Интегрируем прокси
    success = integrator.integrate_proxies()
    
    if success:
        print("\n🧪 Тестируем интеграцию...")
        integrator.test_integration()
        
        print("\n🎉 ГОТОВО!")
        print("Теперь можно запускать:")
        print("  python3 main.py")
        print("  python3 test_cloudflare_bypass.py")
    else:
        print("\n❌ Интеграция не удалась")
        print("Проверьте наличие файлов с прокси")

if __name__ == "__main__":
    main()
