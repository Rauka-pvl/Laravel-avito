#!/bin/bash

echo "🔧 Установка Tor для обхода блокировок..."

# Обновляем пакеты
sudo apt update

# Устанавливаем Tor
sudo apt install -y tor

# Запускаем Tor
sudo systemctl start tor
sudo systemctl enable tor

# Проверяем статус
echo "📊 Статус Tor:"
sudo systemctl status tor --no-pager

echo "✅ Tor установлен и запущен!"
echo "🔗 Tor работает на порту 9050"
echo "🌐 Теперь можно использовать Tor для обхода блокировок"
