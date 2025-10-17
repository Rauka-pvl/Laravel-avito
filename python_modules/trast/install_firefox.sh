#!/bin/bash

# Скрипт для установки Firefox и geckodriver для Selenium
# Использование: ./install_firefox.sh

echo "🦊 Установка Firefox и geckodriver для Selenium"
echo "=============================================="

# Проверяем права root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт с правами root: sudo ./install_firefox.sh"
    exit 1
fi

# Удаляем snap версию Firefox
echo "🗑️ Удаляем snap версию Firefox..."
snap remove firefox 2>/dev/null || echo "Snap Firefox не установлен"

# Устанавливаем Firefox ESR из репозитория Mozilla
echo "📦 Устанавливаем Firefox ESR..."
apt update
apt install -y wget gnupg

# Добавляем репозиторий Mozilla
wget -qO- https://packages.mozilla.org/apt/repo-signing-key.gpg | gpg --dearmor > /etc/apt/trusted.gpg.d/mozilla.gpg
echo "deb [signed-by=/etc/apt/trusted.gpg.d/mozilla.gpg] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list

apt update
apt install -y firefox-esr

# Устанавливаем geckodriver
echo "🔧 Устанавливаем geckodriver..."
GECKODRIVER_VERSION="v0.34.0"
wget -O /tmp/geckodriver.tar.gz "https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-linux64.tar.gz"
tar -xzf /tmp/geckodriver.tar.gz -C /tmp/
mv /tmp/geckodriver /usr/local/bin/
chmod +x /usr/local/bin/geckodriver
rm /tmp/geckodriver.tar.gz

# Устанавливаем зависимости для headless режима
echo "📦 Устанавливаем зависимости для headless режима..."
apt install -y xvfb x11vnc fluxbox dbus-x11

# Проверяем установку
echo "🔍 Проверяем установку..."
echo "Firefox версия:"
firefox --version

echo "Geckodriver версия:"
geckodriver --version

echo "✅ Firefox и geckodriver установлены!"
echo ""
echo "🚀 Теперь можно запускать парсер:"
echo "   python3 main.py"
