#!/bin/bash

# Исправленная установка Tor для Ubuntu 22.04
echo "🚀 Установка Tor для парсера Trast"

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите с правами root: sudo ./install_tor_fixed.sh"
    exit 1
fi

# Обновление пакетов
echo "🔄 Обновление пакетов..."
apt update

# Установка Tor (без Firefox)
echo "📦 Установка Tor..."
apt install -y tor

# Создание директорий
echo "📁 Создание директорий..."
mkdir -p /tmp/tor_data
mkdir -p /var/log/tor
chmod 755 /tmp/tor_data
chmod 755 /var/log/tor

# Создание файла cookie
echo "🍪 Настройка аутентификации..."
touch /tmp/tor_cookie
chmod 600 /tmp/tor_cookie

# Создание конфигурации Tor
echo "⚙️ Создание конфигурации Tor..."
cat > /etc/tor/torrc << 'EOF'
SOCKSPort 9050
ControlPort 9051
DataDirectory /tmp/tor_data
CookieAuthentication 1
CookieAuthFile /tmp/tor_cookie
Log notice file /var/log/tor/tor.log
SafeLogging 1
CircuitBuildTimeout 10
NewCircuitPeriod 30
MaxCircuitDirtiness 600
EOF

# Создание systemd сервиса
echo "🔧 Создание systemd сервиса..."
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

# Перезагрузка systemd
echo "🔄 Перезагрузка systemd..."
systemctl daemon-reload

# Включение автозапуска
echo "🚀 Включение автозапуска Tor..."
systemctl enable tor-parser

# Запуск сервиса
echo "▶️ Запуск Tor сервиса..."
systemctl start tor-parser

# Ожидание запуска
echo "⏳ Ожидание запуска Tor (30 секунд)..."
sleep 30

# Проверка статуса
echo "🔍 Проверка статуса Tor..."
if systemctl is-active --quiet tor-parser; then
    echo "✅ Tor сервис запущен успешно"
    
    # Тестирование подключения
    echo "🌐 Тестирование подключения через Tor..."
    if curl --socks5 127.0.0.1:9050 --connect-timeout 10 https://httpbin.org/ip > /dev/null 2>&1; then
        echo "✅ Подключение через Tor работает"
        TOR_IP=$(curl --socks5 127.0.0.1:9050 --connect-timeout 10 -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
        echo "🌍 Ваш IP через Tor: $TOR_IP"
    else
        echo "❌ Ошибка подключения через Tor"
    fi
else
    echo "❌ Ошибка запуска Tor сервиса"
    systemctl status tor-parser
fi

echo ""
echo "🎉 Установка завершена!"
echo "✅ Tor установлен и настроен"
echo "⚠️ Firefox не установлен (будет использоваться Chrome)"
echo ""
echo "🚀 Теперь можно запускать парсер:"
echo "  cd python_modules/trast"
echo "  python main.py"
