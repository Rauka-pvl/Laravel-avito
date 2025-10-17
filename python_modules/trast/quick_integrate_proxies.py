#!/usr/bin/env python3
"""
Быстрая интеграция найденных прокси в систему
"""

import os
import sys
import json
import glob
from datetime import datetime

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logger_setup import setup_logger

def integrate_found_proxies():
    """Интегрирует найденные прокси в систему."""
    logger = setup_logger("proxy_integrator")
    
    logger.info("🔗 ИНТЕГРАЦИЯ НАЙДЕННЫХ ПРОКСИ")
    logger.info("=" * 40)
    
    # Ищем последние файлы с прокси
    patterns = [
        "working_proxies_*.json",
        "proxies_for_server_*.txt",
        "working_russian_proxies_*.json"
    ]
    
    all_proxies = set()
    found_files = []
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            # Берем самый новый файл
            latest_file = max(files, key=os.path.getmtime)
            found_files.append(latest_file)
            
            logger.info(f"📁 Найден файл: {latest_file}")
            
            try:
                if latest_file.endswith('.json'):
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                        if isinstance(data, list):
                            # Если это список прокси
                            for item in data:
                                if isinstance(item, str):
                                    all_proxies.add(item)
                                elif isinstance(item, dict) and 'proxy' in item:
                                    all_proxies.add(item['proxy'])
                        elif isinstance(data, dict):
                            # Если это объект с прокси
                            if 'proxies' in data:
                                all_proxies.update(data['proxies'])
                            elif 'russian_proxies' in data:
                                for item in data['russian_proxies']:
                                    if isinstance(item, dict) and 'proxy' in item:
                                        all_proxies.add(item['proxy'])
                
                elif latest_file.endswith('.txt'):
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and ':' in line and not line.startswith('#'):
                                all_proxies.add(line)
                
                logger.info(f"✅ Загружено {len(all_proxies)} прокси из {latest_file}")
                
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки {latest_file}: {e}")
    
    if not all_proxies:
        logger.error("❌ Не найдены прокси для интеграции")
        return False
    
    # Создаем основной файл working_proxies.json
    proxies_list = list(all_proxies)
    
    data = {
        'proxies': proxies_list,
        'count': len(proxies_list),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'proxy_integrator',
        'description': f'Интегрировано из {len(found_files)} файлов'
    }
    
    try:
        with open("working_proxies.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Сохранено {len(proxies_list)} прокси в working_proxies.json")
        
        # Создаем простой текстовый файл
        with open("working_proxies.txt", 'w', encoding='utf-8') as f:
            for proxy in proxies_list:
                f.write(f"{proxy}\n")
        
        logger.info(f"📄 Создан working_proxies.txt")
        
        # Показываем примеры прокси
        logger.info("📋 Примеры интегрированных прокси:")
        for i, proxy in enumerate(proxies_list[:10]):
            logger.info(f"  {i+1}. {proxy}")
        
        if len(proxies_list) > 10:
            logger.info(f"  ... и еще {len(proxies_list) - 10} прокси")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")
        return False

def main():
    """Основная функция."""
    print("🔗 БЫСТРАЯ ИНТЕГРАЦИЯ ПРОКСИ")
    print("=" * 40)
    
    success = integrate_found_proxies()
    
    if success:
        print("\n✅ ГОТОВО!")
        print("Теперь можно запускать:")
        print("  python3 main.py")
    else:
        print("\n❌ Интеграция не удалась")
        print("Проверьте наличие файлов с прокси")

if __name__ == "__main__":
    main()
