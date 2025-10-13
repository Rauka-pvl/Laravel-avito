#!/bin/bash

# Исправленная установка Tor для парсера Trast
# Решает все проблемы с namespace и директориями

set -e  # Остановка при ошибке

echo "🚀 Исправленная установка Tor для парсера Trast"
echo "=============================================="

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт с правами root: sudo ./install_tor.sh"
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

# Установка Tor
echo "📦 Установка Tor..."
if [ "$DISTRO" = "debian" ]; then
    apt install -y tor
elif [ "$DISTRO" = "redhat" ]; then
    yum install -y tor
elif [ "$DISTRO" = "arch" ]; then
    pacman -S --noconfirm tor
fi

# Остановка стандартного Tor сервиса
echo "⏹️ Остановка стандартного Tor сервиса..."
systemctl stop tor 2>/dev/null || true
systemctl disable tor 2>/dev/null || true

# Очистка старых конфигураций
echo "🧹 Очистка старых конфигураций..."
systemctl stop tor-parser 2>/dev/null || true
systemctl disable tor-parser 2>/dev/null || true
rm -f /etc/systemd/system/tor-parser.service
rm -rf /tmp/tor_data
rm -f /tmp/tor_cookie

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

# Создание простого systemd сервиса (без namespace)
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
echo "⏳ Ожидание запуска Tor (60 секунд)..."
sleep 60

# Проверка статуса
echo "🔍 Проверка статуса Tor..."
if systemctl is-active --quiet tor-parser; then
    echo "✅ Tor сервис запущен успешно"
else
    echo "❌ Ошибка запуска Tor сервиса"
    echo "📋 Логи сервиса:"
    systemctl status tor-parser --no-pager
    echo ""
    echo "📋 Логи Tor:"
    journalctl -u tor-parser --no-pager -n 20
    exit 1
fi

# Проверка портов
echo "🔌 Проверка портов..."
if netstat -tlnp 2>/dev/null | grep -q ":9050"; then
    echo "✅ SOCKS порт 9050 активен"
else
    echo "❌ SOCKS порт 9050 не активен"
fi

if netstat -tlnp 2>/dev/null | grep -q ":9051"; then
    echo "✅ Control порт 9051 активен"
else
    echo "❌ Control порт 9051 не активен"
fi

# Тестирование подключения
echo "🌐 Тестирование подключения через Tor..."
if curl --socks5 127.0.0.1:9050 --connect-timeout 15 https://httpbin.org/ip > /dev/null 2>&1; then
    echo "✅ Подключение через Tor работает"
    
    # Получение IP через Tor
    TOR_IP=$(curl --socks5 127.0.0.1:9050 --connect-timeout 15 -s https://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
    if [ -n "$TOR_IP" ]; then
        echo "🌍 Ваш IP через Tor: $TOR_IP"
    else
        echo "⚠️ Не удалось получить IP через Tor"
    fi
else
    echo "❌ Ошибка подключения через Tor"
    echo "📋 Проверьте логи: journalctl -u tor-parser -f"
    exit 1
fi

# Тестирование сайта
echo "🎯 Тестирование сайта trast-zapchast.ru через Tor..."
if curl --socks5 127.0.0.1:9050 --connect-timeout 15 -I https://trast-zapchast.ru/shop/ > /dev/null 2>&1; then
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
        systemctl status tor-parser --no-pager
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

# Создание скрипта мониторинга
echo "📊 Создание скрипта мониторинга..."
cat > /usr/local/bin/tor-monitor << 'EOF'
#!/bin/bash

echo "🔍 Мониторинг Tor для парсера Trast"
echo "=================================="

# Проверка статуса сервиса
if systemctl is-active --quiet tor-parser; then
    echo "✅ Tor сервис: АКТИВЕН"
else
    echo "❌ Tor сервис: НЕ АКТИВЕН"
fi

# Проверка портов
if netstat -tlnp 2>/dev/null | grep -q ":9050"; then
    echo "✅ SOCKS порт 9050: ОТКРЫТ"
else
    echo "❌ SOCKS порт 9050: ЗАКРЫТ"
fi

if netstat -tlnp 2>/dev/null | grep -q ":9051"; then
    echo "✅ Control порт 9051: ОТКРЫТ"
else
    echo "❌ Control порт 9051: ЗАКРЫТ"
fi

# Проверка подключения
echo "🌐 Тестирование подключения..."
if curl --socks5 127.0.0.1:9050 --connect-timeout 5 https://httpbin.org/ip > /dev/null 2>&1; then
    echo "✅ Подключение через Tor: РАБОТАЕТ"
    TOR_IP=$(curl --socks5 127.0.0.1:9050 --connect-timeout 5 -s https://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
    echo "🌍 IP через Tor: $TOR_IP"
else
    echo "❌ Подключение через Tor: НЕ РАБОТАЕТ"
fi

# Проверка сайта
echo "🎯 Проверка сайта trast-zapchast.ru..."
if curl --socks5 127.0.0.1:9050 --connect-timeout 5 -I https://trast-zapchast.ru/shop/ > /dev/null 2>&1; then
    echo "✅ Сайт доступен через Tor"
else
    echo "⚠️ Сайт недоступен через Tor"
fi

echo ""
echo "📋 Полезные команды:"
echo "  tor-parser status  - Статус сервиса"
echo "  tor-parser logs    - Логи в реальном времени"
echo "  tor-parser test    - Тест подключения"
echo "  tor-parser ip      - Показать IP"
EOF

chmod +x /usr/local/bin/tor-monitor

# Финальная проверка
echo ""
echo "🎉 Установка завершена!"
echo "======================"
echo ""
echo "✅ Tor установлен и настроен"
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
echo "  tor-monitor         - Полная диагностика"
echo ""
echo "🚀 Теперь можно запускать парсер:"
echo "  cd python_modules/trast"
echo "  python3 main.py"
echo ""
echo "📊 Для мониторинга используйте:"
echo "  tor-monitor"
echo ""
echo "🎯 Tor готов к работе с парсером Trast!"