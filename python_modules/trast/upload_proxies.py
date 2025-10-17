#!/usr/bin/env python3
"""
Скрипт для загрузки найденных прокси на сервер
"""

import os
import sys
import subprocess
from datetime import datetime

def upload_proxies_to_server(proxy_file: str, server_info: str):
    """Загружает файл с прокси на сервер."""
    print(f"📤 Загружаем прокси на сервер...")
    print(f"📁 Файл: {proxy_file}")
    print(f"🖥️ Сервер: {server_info}")
    
    if not os.path.exists(proxy_file):
        print(f"❌ Файл {proxy_file} не найден")
        return False
    
    try:
        # Команда для загрузки через scp
        remote_path = "/home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/"
        scp_command = f"scp {proxy_file} {server_info}:{remote_path}"
        
        print(f"🚀 Выполняем: {scp_command}")
        result = subprocess.run(scp_command, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Файл успешно загружен на сервер")
            
            # Создаем команды для выполнения на сервере
            commands = [
                f"cd {remote_path}",
                f"cp {os.path.basename(proxy_file)} working_proxies.json",
                f"python3 main.py"
            ]
            
            print(f"\n📋 Команды для выполнения на сервере:")
            print("=" * 50)
            for cmd in commands:
                print(cmd)
            print("=" * 50)
            
            return True
        else:
            print(f"❌ Ошибка загрузки: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def main():
    """Основная функция."""
    if len(sys.argv) < 3:
        print("Использование: python3 upload_proxies.py <файл_прокси> <сервер>")
        print("Пример: python3 upload_proxies.py working_proxies_20241017_120000.json root@31.172.69.102")
        return
    
    proxy_file = sys.argv[1]
    server_info = sys.argv[2]
    
    success = upload_proxies_to_server(proxy_file, server_info)
    
    if success:
        print(f"\n🎉 ГОТОВО!")
        print(f"Теперь подключитесь к серверу и выполните команды выше.")
    else:
        print(f"\n❌ Загрузка не удалась")

if __name__ == "__main__":
    main()
