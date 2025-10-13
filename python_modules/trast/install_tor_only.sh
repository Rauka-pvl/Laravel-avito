#!/bin/bash

# Установка только Tor (без Firefox)
# Для случаев когда Firefox недоступен

echo "🚀 Установка только Tor для парсера Trast"

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите с правами root: sudo ./install_tor_only.sh"
    exit 1
fi

# Определение дистрибутива
if [ -f /etc/debian_version ]; then
    DISTRO="debian"
elif [ -f /etc/redhat-release ]; then
    DISTRO="redhat"
elif [ -f /etc/arch-release ]; then
    DISTRO="arch"
else
    echo "❌ Неподдерживаемый дистрибутив Linux"
    exit 1
fi

echo "📋 Обнаружен дистрибутив: $DISTRO"

# Обновление пакетов
echo "🔄 Обновление пакетов..."
if [ "$DISTRO" = "debian" ]; then
    apt update
elif [ "$DISTRO" = "redhat" ]; then
    yum update -y
elif [ "$DISTRO" = "arch" ]; then
    pacman -Sy
fi

# Установка только Tor
echo "📦 Установка Tor..."
if [ "$DISTRO" = "debian" ]; then
    apt install -y tor
elif [ "$DISTRO" = "redhat" ]; then
    yum install -y tor
elif [ "$DISTRO" = "arch" ]; then
    pacman -S --noconfirm tor
fi

# Создание директорий
echo "📁 Создание директорий..."
mkdir -p /tmp/tor_data
mkdir -p /var/log/tor
chmod 755 /tmp/tor_data
chmod 755 /var/log/tor

# Создание файла cookie для аутентификации
echo "🍪 Настройка аутентификации..."
touch /tmp/tor_cookie
chmod 600 /tmp/tor_cookie

# Создание конфигурации Tor
echo "⚙️ Создание конфигурации Tor..."
cat > /etc/tor/torrc << 'EOF'
# Конфигурация Tor для парсера Trast
SOCKSPort 9050
ControlPort 9051
DataDirectory /tmp/tor_data
CookieAuthentication 1
CookieAuthFile /tmp/tor_cookie

# Логирование
Log notice file /var/log/tor/tor.log
Log notice stdout

# Безопасность
SafeLogging 1
AvoidDiskWrites 1

# Производительность
CircuitBuildTimeout 10
NewCircuitPeriod 30
MaxCircuitDirtiness 600

# Отключение некоторых функций для скорости
DisableDebuggerAttachment 1
SafeSocks 0
TestSocks 0
EOF

# Создание systemd сервиса
echo "🔧 Создание systemd сервиса..."
cat > /etc/systemd/system/tor-parser.service << 'EOF'
[Unit]
Description=Tor service for Trast parser
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/tor -f /etc/tor/torrc
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/tmp/tor_data /var/log/tor

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
else
    echo "❌ Ошибка запуска Tor сервиса"
    systemctl status tor-parser
    exit 1
fi

# Проверка портов
echo "🔌 Проверка портов..."
if netstat -tlnp | grep -q ":9050"; then
    echo "✅ SOCKS порт 9050 активен"
else
    echo "❌ SOCKS порт 9050 не активен"
fi

if netstat -tlnp | grep -q ":9051"; then
    echo "✅ Control порт 9051 активен"
else
    echo "❌ Control порт 9051 не активен"
fi

# Тестирование подключения
echo "🌐 Тестирование подключения через Tor..."
if curl --socks5 127.0.0.1:9050 --connect-timeout 10 https://httpbin.org/ip > /dev/null 2>&1; then
    echo "✅ Подключение через Tor работает"
    
    # Получение IP через Tor
    TOR_IP=$(curl --socks5 127.0.0.1:9050 --connect-timeout 10 -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
    echo "🌍 Ваш IP через Tor: $TOR_IP"
else
    echo "❌ Ошибка подключения через Tor"
    echo "📋 Проверьте логи: journalctl -u tor-parser -f"
fi

# Тестирование сайта
echo "🎯 Тестирование сайта trast-zapchast.ru через Tor..."
if curl --socks5 127.0.0.1:9050 --connect-timeout 10 -I https://trast-zapchast.ru/shop/ > /dev/null 2>&1; then
    echo "✅ Сайт доступен через Tor"
else
    echo "⚠️ Сайт может быть недоступен через Tor (это нормально)"
fi

# Создание скрипта управления
echo "📝 Создание скрипта управления..."
cat > /usr/local/bin/tor-parser << 'EOF'
#!/bin/bash

case "$1" in
    start)
        echo "🚀 Запуск Tor для парсера..."
        systemctl start tor-parser
        ;;
    stop)
        echo "⏹️ Остановка Tor для парсера..."
        systemctl stop tor-parser
        ;;
    restart)
        echo "🔄 Перезапуск Tor для парсера..."
        systemctl restart tor-parser
        ;;
    status)
        echo "📊 Статус Tor для парсера:"
        systemctl status tor-parser
        ;;
    logs)
        echo "📋 Логи Tor для парсера:"
        journalctl -u tor-parser -f
        ;;
    test)
        echo "🧪 Тестирование подключения через Tor..."
        curl --socks5 127.0.0.1:9050 --connect-timeout 10 https://httpbin.org/ip
        ;;
    ip)
        echo "🌍 Ваш IP через Tor:"
        curl --socks5 127.0.0.1:9050 --connect-timeout 10 -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4
        ;;
    *)
        echo "Использование: tor-parser {start|stop|restart|status|logs|test|ip}"
        echo ""
        echo "Команды:"
        echo "  start   - Запустить Tor"
        echo "  stop    - Остановить Tor"
        echo "  restart - Перезапустить Tor"
        echo "  status  - Показать статус"
        echo "  logs    - Показать логи"
        echo "  test    - Тестировать подключение"
        echo "  ip      - Показать IP через Tor"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/tor-parser

# Финальная проверка
echo ""
echo "🎉 Установка завершена!"
echo "======================"
echo ""
echo "✅ Tor установлен и настроен"
echo "⚠️ Firefox не установлен (будет использоваться Chrome)"
echo "✅ Systemd сервис создан"
echo "✅ Автозапуск включен"
echo "✅ Скрипты управления созданы"
echo ""
echo "📋 Полезные команды:"
echo "  tor-parser start    - Запустить Tor"
echo "  tor-parser stop     - Остановить Tor"
echo "  tor-parser status   - Статус сервиса"
echo "  tor-parser logs     - Логи в реальном времени"
echo "  tor-parser test     - Тест подключения"
echo "  tor-parser ip       - Показать IP через Tor"
echo ""
echo "🚀 Теперь можно запускать парсер:"
echo "  cd python_modules/trast"
echo "  python main.py"
echo ""
echo "📊 Парсер будет использовать:"
echo "  1. Tor + Chrome (если Tor доступен)"
echo "  2. Chrome + прокси (если Tor недоступен)"
echo "  3. Chrome напрямую (если прокси не работают)"
echo ""
echo "🎯 Tor готов к работе с парсером Trast!"
