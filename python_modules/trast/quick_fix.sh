#!/bin/bash

# Быстрое исправление проблем парсера
echo "🔧 Быстрое исправление проблем парсера"
echo "====================================="

# 1. Устанавливаем httpx с SOCKS поддержкой
echo "📦 Устанавливаем httpx[socks]..."
pip install 'httpx[socks]'

# 2. Обновляем geckodriver до совместимой версии
echo "🦊 Обновляем geckodriver..."
GECKODRIVER_VERSION="v0.36.0"
wget -O /tmp/geckodriver.tar.gz "https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-linux64.tar.gz"
tar -xzf /tmp/geckodriver.tar.gz -C /tmp/
mv /tmp/geckodriver /usr/local/bin/
chmod +x /usr/local/bin/geckodriver
rm /tmp/geckodriver.tar.gz

# 3. Проверяем версии
echo "🔍 Проверяем версии..."
echo "Firefox: $(firefox --version)"
echo "Geckodriver: $(geckodriver --version)"

# 4. Тестируем браузеры
echo "🧪 Тестируем браузеры..."
python3 test_browsers.py

echo "✅ Исправления применены!"
echo "🚀 Теперь можно запускать: python3 main.py"
