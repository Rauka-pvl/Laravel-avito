#!/bin/bash

# Быстрая установка Tor для парсера Trast
# Простая версия без лишних проверок

echo "🚀 Быстрая установка Tor для парсера Trast"

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите с правами root: sudo ./quick_install_tor.sh"
    exit 1
fi

# Установка Tor и Firefox
echo "📦 Установка Tor и Firefox..."
apt update && apt install -y tor firefox-esr

# Создание директорий
mkdir -p /tmp/tor_data
chmod 755 /tmp/tor_data

# Создание конфигурации
cat > /etc/tor/torrc << 'EOF'
SOCKSPort 9050
ControlPort 9051
DataDirectory /tmp/tor_data
CookieAuthentication 1
CookieAuthFile /tmp/tor_cookie
Log notice file /var/log/tor/tor.log
EOF

# Создание systemd сервиса
cat > /etc/systemd/system/tor-parser.service << 'EOF'
[Unit]
Description=Tor service for Trast parser
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/tor -f /etc/tor/torrc
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Запуск сервиса
systemctl daemon-reload
systemctl enable tor-parser
systemctl start tor-parser

# Ожидание запуска
echo "⏳ Ожидание запуска Tor..."
sleep 15

# Проверка
if systemctl is-active --quiet tor-parser; then
    echo "✅ Tor установлен и запущен!"
    echo "🌍 IP через Tor: $(curl --socks5 127.0.0.1:9050 -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)"
    echo ""
    echo "🚀 Теперь можно запускать парсер:"
    echo "  cd python_modules/trast"
    echo "  python main.py"
else
    echo "❌ Ошибка установки Tor"
    systemctl status tor-parser
fi
