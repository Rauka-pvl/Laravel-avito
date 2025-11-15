#!/bin/bash
# Скрипт для установки зависимостей на Linux/Mac

set -e

echo "============================================================"
echo "Установка зависимостей для парсера trast"
echo "============================================================"

# Определяем путь к скрипту
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "Ошибка: файл $REQUIREMENTS_FILE не найден!"
    exit 1
fi

# Обновляем pip
echo ""
echo "1. Обновление pip..."
python3 -m pip install --upgrade pip

# Устанавливаем/обновляем основные зависимости
echo ""
echo "2. Установка основных зависимостей..."
python3 -m pip install --upgrade -r "$REQUIREMENTS_FILE"

# Специально обновляем undetected-chromedriver
echo ""
echo "3. Обновление undetected-chromedriver..."
python3 -m pip install --upgrade --force-reinstall undetected-chromedriver

# Проверяем установку
echo ""
echo "4. Проверка установленных пакетов..."
python3 -m pip list | grep -iE "undetected|selenium|cloudscraper|beautifulsoup"

echo ""
echo "============================================================"
echo "Установка завершена!"
echo "============================================================"
echo ""
echo "Если возникли проблемы с версией ChromeDriver:"
echo "1. Убедитесь, что Chrome установлен и обновлен"
echo "2. Запустите этот скрипт снова для обновления undetected-chromedriver"
echo "3. Парсер автоматически попробует использовать Firefox при ошибках Chrome"

