#!/bin/bash

# Скрипт установки Cloudflare WARP для парсера Trast
# Автор: AI Assistant
# Дата: $(date)

set -e  # Остановка при ошибке

echo "🌐 Установка Cloudflare WARP для парсера Trast"
echo "=============================================="

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт с правами root: sudo ./install_warp.sh"
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

# Установка WARP
echo "📦 Установка Cloudflare WARP..."
if [ "$DISTRO" = "debian" ]; then
    # Добавление репозитория Cloudflare
    curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflare-client.list
    apt update
    apt install -y cloudflare-warp
elif [ "$DISTRO" = "redhat" ]; then
    # Для CentOS/RHEL
    yum install -y https://pkg.cloudflareclient.com/cloudflare-release-el7.rpm
    yum install -y cloudflare-warp
elif [ "$DISTRO" = "arch" ]; then
    # Для Arch Linux
    pacman -S --noconfirm cloudflare-warp-bin
fi

# Регистрация WARP
echo "📝 Регистрация WARP..."
warp-cli registration new

# Подключение к WARP
echo "🔗 Подключение к WARP..."
warp-cli connect

# Ожидание подключения
echo "⏳ Ожидание подключения (10 секунд)..."
sleep 10

# Проверка статуса
echo "🔍 Проверка статуса WARP..."
if warp-cli status | grep -q "Connected"; then
    echo "✅ WARP подключен успешно"
else
    echo "❌ Ошибка подключения WARP"
    warp-cli status
    exit 1
fi

# Получение IP
echo "🌍 Получение IP через WARP..."
WARP_IP=$(curl --socks5 127.0.0.1:40000 --connect-timeout 10 -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
if [ -n "$WARP_IP" ]; then
    echo "✅ IP через WARP: $WARP_IP"
else
    echo "⚠️ Не удалось получить IP через WARP"
fi

# Тестирование сайта
echo "🎯 Тестирование сайта trast-zapchast.ru через WARP..."
if curl --socks5 127.0.0.1:40000 --connect-timeout 10 -I https://trast-zapchast.ru/shop/ > /dev/null 2>&1; then
    echo "✅ Сайт доступен через WARP"
else
    echo "⚠️ Сайт может быть недоступен через WARP"
fi

# Создание скрипта управления
echo "📝 Создание скрипта управления..."
cat > /usr/local/bin/warp-parser << 'EOF'
#!/bin/bash

case "$1" in
    start)
        echo "🌐 Подключение к WARP..."
        warp-cli connect
        ;;
    stop)
        echo "🔌 Отключение от WARP..."
        warp-cli disconnect
        ;;
    restart)
        echo "🔄 Переподключение к WARP..."
        warp-cli disconnect
        sleep 2
        warp-cli connect
        ;;
    status)
        echo "📊 Статус WARP:"
        warp-cli status
        ;;
    ip)
        echo "🌍 IP через WARP:"
        curl --socks5 127.0.0.1:40000 --connect-timeout 10 -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4
        ;;
    test)
        echo "🧪 Тестирование подключения через WARP..."
        curl --socks5 127.0.0.1:40000 --connect-timeout 10 https://httpbin.org/ip
        ;;
    *)
        echo "Использование: warp-parser {start|stop|restart|status|ip|test}"
        echo ""
        echo "Команды:"
        echo "  start   - Подключиться к WARP"
        echo "  stop    - Отключиться от WARP"
        echo "  restart - Переподключиться к WARP"
        echo "  status  - Показать статус"
        echo "  ip      - Показать IP через WARP"
        echo "  test    - Тестировать подключение"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/warp-parser

# Создание systemd сервиса для автозапуска
echo "🔧 Создание systemd сервиса..."
cat > /etc/systemd/system/warp-parser.service << 'EOF'
[Unit]
Description=Cloudflare WARP for Trast parser
After=network.target
Wants=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/warp-cli connect
RemainAfterExit=true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Включение автозапуска
echo "🚀 Включение автозапуска WARP..."
systemctl daemon-reload
systemctl enable warp-parser

# Финальная проверка
echo ""
echo "🎉 Установка завершена!"
echo "======================"
echo ""
echo "✅ Cloudflare WARP установлен и настроен"
echo "✅ Systemd сервис создан"
echo "✅ Автозапуск включен"
echo "✅ Скрипты управления созданы"
echo ""
echo "📋 Полезные команды:"
echo "  warp-parser start    - Подключиться к WARP"
echo "  warp-parser stop     - Отключиться от WARP"
echo "  warp-parser status   - Статус подключения"
echo "  warp-parser ip       - Показать IP через WARP"
echo "  warp-parser test     - Тест подключения"
echo ""
echo "🚀 Теперь можно запускать парсер:"
echo "  cd python_modules/trast"
echo "  python main.py"
echo ""
echo "📊 Парсер будет использовать:"
echo "  1. WARP (если доступен)"
echo "  2. Tor + прокси (если WARP недоступен)"
echo "  3. Прокси напрямую (если Tor недоступен)"
echo ""
echo "🎯 WARP готов к работе с парсером Trast!"
