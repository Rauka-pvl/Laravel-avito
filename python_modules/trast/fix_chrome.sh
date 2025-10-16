#!/bin/bash

echo "🔧 Обновление ChromeDriver для совместимости с Chrome 134..."

# Проверяем версию Chrome
echo "1️⃣ Проверяем версию Chrome..."
CHROME_VERSION=$(google-chrome --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
echo "Версия Chrome: $CHROME_VERSION"

# Получаем мажорную версию
MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d. -f1)
echo "Мажорная версия: $MAJOR_VERSION"

# Удаляем старые версии ChromeDriver
echo "2️⃣ Удаляем старые версии ChromeDriver..."
rm -rf /root/.local/share/undetected_chromedriver/
rm -rf /tmp/chromedriver*

# Устанавливаем webdriver-manager для автоматического управления
echo "3️⃣ Устанавливаем webdriver-manager..."
pip3 install --upgrade webdriver-manager

# Создаем тестовый скрипт
echo "4️⃣ Создаем тестовый скрипт..."
cat > test_chrome.py << 'EOF'
#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def test_chrome():
    """Тестируем Chrome с автоматическим ChromeDriver."""
    print("🧪 Тестирование Chrome...")
    
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        
        # Автоматическое управление ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Тестируем
        driver.get("https://httpbin.org/ip")
        print(f"✅ Chrome работает! Статус: {driver.title}")
        
        driver.quit()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Chrome: {e}")
        return False

if __name__ == "__main__":
    test_chrome()
EOF

chmod +x test_chrome.py

echo "5️⃣ Тестируем Chrome..."
python3 test_chrome.py

echo "✅ Обновление завершено!"
