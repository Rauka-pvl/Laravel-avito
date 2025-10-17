#!/bin/bash
# Скрипт для установки Chrome на сервере Ubuntu

echo "🚀 УСТАНОВКА CHROME ДЛЯ ОБХОДА CLOUDFLARE"
echo "=========================================="

# Обновляем систему
echo "📦 Обновляем систему..."
apt update

# Устанавливаем Chrome
echo "🌐 Устанавливаем Google Chrome..."
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt update
apt install -y google-chrome-stable

# Проверяем установку
echo "✅ Проверяем установку Chrome..."
google-chrome --version

# Устанавливаем ChromeDriver
echo "🔧 Устанавливаем ChromeDriver..."
CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+')
echo "Chrome version: $CHROME_VERSION"

# Скачиваем соответствующий ChromeDriver
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION")
echo "ChromeDriver version: $CHROMEDRIVER_VERSION"

wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" -O /tmp/chromedriver.zip
unzip -q /tmp/chromedriver.zip -d /tmp
mv /tmp/chromedriver /usr/local/bin/
chmod +x /usr/local/bin/chromedriver
rm /tmp/chromedriver.zip

# Проверяем ChromeDriver
echo "✅ Проверяем установку ChromeDriver..."
chromedriver --version

echo "🎉 Chrome и ChromeDriver установлены успешно!"
echo "Теперь можно запускать:"
echo "  python3 test_cloudflare_bypass.py"
echo "  python3 main.py"
