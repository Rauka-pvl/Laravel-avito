#!/usr/bin/env python3
"""
Быстрая установка зависимостей для обхода Cloudflare
"""

import subprocess
import sys
import os

def install_package(package):
    """Устанавливает пакет через pip."""
    try:
        print(f"📦 Устанавливаем {package}...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", package], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {package} установлен успешно")
            return True
        else:
            print(f"❌ Ошибка установки {package}: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Исключение при установке {package}: {e}")
        return False

def main():
    """Основная функция установки."""
    print("🚀 УСТАНОВКА ЗАВИСИМОСТЕЙ ДЛЯ ОБХОДА CLOUDFLARE")
    print("=" * 60)
    
    # Список пакетов для установки
    packages = [
        "undetected-chromedriver>=3.5.0",
        "selenium-stealth>=1.0.6",
        "httpx[socks]>=0.25.0",
        "socksio>=1.0.0"
    ]
    
    success_count = 0
    
    for package in packages:
        if install_package(package):
            success_count += 1
        print()
    
    print("=" * 60)
    print(f"📊 РЕЗУЛЬТАТ: {success_count}/{len(packages)} пакетов установлено")
    
    if success_count == len(packages):
        print("🎉 ВСЕ ПАКЕТЫ УСТАНОВЛЕНЫ УСПЕШНО!")
        print("\nТеперь можно запускать:")
        print("  python3 test_cloudflare_bypass.py")
        print("  python3 main.py")
    else:
        print("⚠️ НЕКОТОРЫЕ ПАКЕТЫ НЕ УСТАНОВЛЕНЫ")
        print("Попробуйте установить их вручную:")
        for package in packages:
            print(f"  pip install {package}")

if __name__ == "__main__":
    main()
