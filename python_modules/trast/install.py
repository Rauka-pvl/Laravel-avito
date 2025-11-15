#!/usr/bin/env python3
"""
Скрипт для установки и обновления зависимостей парсера trast
"""
import subprocess
import sys
import os

def run_command(command, description):
    """Выполняет команду и выводит результат"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка: {e}")
        if e.stdout:
            print(f"Вывод: {e.stdout}")
        if e.stderr:
            print(f"Ошибки: {e.stderr}")
        return False

def main():
    """Основная функция установки"""
    print("="*60)
    print("Установка зависимостей для парсера trast")
    print("="*60)
    
    # Определяем путь к requirements.txt
    script_dir = os.path.dirname(os.path.abspath(__file__))
    requirements_file = os.path.join(script_dir, "requirements.txt")
    
    if not os.path.exists(requirements_file):
        print(f"Ошибка: файл {requirements_file} не найден!")
        sys.exit(1)
    
    # Обновляем pip
    print("\n1. Обновление pip...")
    run_command(
        f"{sys.executable} -m pip install --upgrade pip",
        "Обновление pip"
    )
    
    # Устанавливаем/обновляем основные зависимости
    print("\n2. Установка основных зависимостей...")
    success = run_command(
        f"{sys.executable} -m pip install --upgrade -r {requirements_file}",
        "Установка зависимостей из requirements.txt"
    )
    
    if not success:
        print("\n⚠️  Предупреждение: некоторые зависимости не установились")
    
    # Специально обновляем undetected-chromedriver для совместимости с Chrome
    print("\n3. Обновление undetected-chromedriver...")
    run_command(
        f"{sys.executable} -m pip install --upgrade --force-reinstall undetected-chromedriver",
        "Обновление undetected-chromedriver для совместимости с Chrome"
    )
    
    # Проверяем установку
    print("\n4. Проверка установленных пакетов...")
    if os.name == 'nt':  # Windows
        run_command(
            f"{sys.executable} -m pip list | findstr /i \"undetected selenium cloudscraper beautifulsoup\"",
            "Проверка установленных пакетов"
        )
    else:  # Linux/Mac
        run_command(
            f"{sys.executable} -m pip list | grep -iE \"undetected|selenium|cloudscraper|beautifulsoup\"",
            "Проверка установленных пакетов"
        )
    
    print("\n" + "="*60)
    print("Установка завершена!")
    print("="*60)
    print("\nЕсли возникли проблемы с версией ChromeDriver:")
    print("1. Убедитесь, что Chrome установлен и обновлен")
    print("2. Запустите этот скрипт снова для обновления undetected-chromedriver")
    print("3. Парсер автоматически попробует использовать Firefox при ошибках Chrome")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nУстановка прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nКритическая ошибка: {e}")
        sys.exit(1)

