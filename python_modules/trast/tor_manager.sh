#!/bin/bash

# Скрипт управления Tor для парсера Trast
# Использование: ./tor_manager.sh [команда]

SERVICE_NAME="tor-parser"
TOR_CONFIG="/etc/tor/torrc"
LOG_FILE="/var/log/tor/tor.log"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️ $1${NC}"
}

# Проверка прав root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Запустите скрипт с правами root: sudo $0 $1"
        exit 1
    fi
}

# Проверка статуса Tor
check_tor_status() {
    if systemctl is-active --quiet $SERVICE_NAME; then
        return 0
    else
        return 1
    fi
}

# Запуск Tor
start_tor() {
    check_root "start"
    
    if check_tor_status; then
        print_warning "Tor уже запущен"
        return 0
    fi
    
    print_info "Запуск Tor..."
    systemctl start $SERVICE_NAME
    
    # Ожидание запуска
    sleep 5
    
    if check_tor_status; then
        print_status "Tor успешно запущен"
        show_tor_ip
    else
        print_error "Ошибка запуска Tor"
        systemctl status $SERVICE_NAME
        return 1
    fi
}

# Остановка Tor
stop_tor() {
    check_root "stop"
    
    if ! check_tor_status; then
        print_warning "Tor не запущен"
        return 0
    fi
    
    print_info "Остановка Tor..."
    systemctl stop $SERVICE_NAME
    
    if ! check_tor_status; then
        print_status "Tor успешно остановлен"
    else
        print_error "Ошибка остановки Tor"
        return 1
    fi
}

# Перезапуск Tor
restart_tor() {
    check_root "restart"
    
    print_info "Перезапуск Tor..."
    systemctl restart $SERVICE_NAME
    
    # Ожидание запуска
    sleep 5
    
    if check_tor_status; then
        print_status "Tor успешно перезапущен"
        show_tor_ip
    else
        print_error "Ошибка перезапуска Tor"
        systemctl status $SERVICE_NAME
        return 1
    fi
}

# Показать статус
show_status() {
    echo "📊 Статус Tor для парсера Trast"
    echo "================================"
    
    # Статус сервиса
    if check_tor_status; then
        print_status "Сервис: АКТИВЕН"
    else
        print_error "Сервис: НЕ АКТИВЕН"
    fi
    
    # Проверка портов
    if netstat -tlnp 2>/dev/null | grep -q ":9050"; then
        print_status "SOCKS порт 9050: ОТКРЫТ"
    else
        print_error "SOCKS порт 9050: ЗАКРЫТ"
    fi
    
    if netstat -tlnp 2>/dev/null | grep -q ":9051"; then
        print_status "Control порт 9051: ОТКРЫТ"
    else
        print_error "Control порт 9051: ЗАКРЫТ"
    fi
    
    # Проверка подключения
    if curl --socks5 127.0.0.1:9050 --connect-timeout 5 https://httpbin.org/ip > /dev/null 2>&1; then
        print_status "Подключение через Tor: РАБОТАЕТ"
        show_tor_ip
    else
        print_error "Подключение через Tor: НЕ РАБОТАЕТ"
    fi
    
    # Проверка сайта
    print_info "Проверка сайта trast-zapchast.ru..."
    if curl --socks5 127.0.0.1:9050 --connect-timeout 5 -I https://trast-zapchast.ru/shop/ > /dev/null 2>&1; then
        print_status "Сайт доступен через Tor"
    else
        print_warning "Сайт недоступен через Tor"
    fi
    
    echo ""
    print_info "Подробный статус сервиса:"
    systemctl status $SERVICE_NAME --no-pager
}

# Показать IP через Tor
show_tor_ip() {
    if check_tor_status; then
        print_info "Получение IP через Tor..."
        TOR_IP=$(curl --socks5 127.0.0.1:9050 --connect-timeout 10 -s https://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
        
        if [ -n "$TOR_IP" ]; then
            print_status "Ваш IP через Tor: $TOR_IP"
        else
            print_error "Не удалось получить IP через Tor"
        fi
    else
        print_error "Tor не запущен"
    fi
}

# Тестирование подключения
test_connection() {
    if ! check_tor_status; then
        print_error "Tor не запущен"
        return 1
    fi
    
    print_info "Тестирование подключения через Tor..."
    
    # Тест базового подключения
    if curl --socks5 127.0.0.1:9050 --connect-timeout 10 https://httpbin.org/ip > /dev/null 2>&1; then
        print_status "Базовое подключение: РАБОТАЕТ"
        
        # Получение IP
        TOR_IP=$(curl --socks5 127.0.0.1:9050 --connect-timeout 10 -s https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
        print_status "IP через Tor: $TOR_IP"
        
        # Тест сайта
        print_info "Тестирование сайта trast-zapchast.ru..."
        if curl --socks5 127.0.0.1:9050 --connect-timeout 10 -I https://trast-zapchast.ru/shop/ > /dev/null 2>&1; then
            print_status "Сайт доступен через Tor"
        else
            print_warning "Сайт недоступен через Tor"
        fi
        
    else
        print_error "Базовое подключение: НЕ РАБОТАЕТ"
        return 1
    fi
}

# Показать логи
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        print_info "Логи Tor (последние 50 строк):"
        echo "================================"
        tail -50 "$LOG_FILE"
    else
        print_warning "Файл логов не найден: $LOG_FILE"
        print_info "Попробуйте: journalctl -u $SERVICE_NAME -f"
    fi
}

# Мониторинг в реальном времени
monitor() {
    print_info "Мониторинг Tor в реальном времени..."
    print_info "Нажмите Ctrl+C для выхода"
    echo ""
    
    while true; do
        clear
        echo "🔍 Мониторинг Tor - $(date)"
        echo "================================"
        
        if check_tor_status; then
            print_status "Tor: АКТИВЕН"
            
            # Проверка подключения
            if curl --socks5 127.0.0.1:9050 --connect-timeout 3 https://httpbin.org/ip > /dev/null 2>&1; then
                print_status "Подключение: РАБОТАЕТ"
                TOR_IP=$(curl --socks5 127.0.0.1:9050 --connect-timeout 3 -s https://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
                print_status "IP: $TOR_IP"
            else
                print_error "Подключение: НЕ РАБОТАЕТ"
            fi
        else
            print_error "Tor: НЕ АКТИВЕН"
        fi
        
        echo ""
        print_info "Обновление через 10 секунд..."
        sleep 10
    done
}

# Показать справку
show_help() {
    echo "🔧 Управление Tor для парсера Trast"
    echo "=================================="
    echo ""
    echo "Использование: $0 [команда]"
    echo ""
    echo "Команды:"
    echo "  start     - Запустить Tor"
    echo "  stop      - Остановить Tor"
    echo "  restart   - Перезапустить Tor"
    echo "  status    - Показать статус"
    echo "  ip        - Показать IP через Tor"
    echo "  test      - Тестировать подключение"
    echo "  logs      - Показать логи"
    echo "  monitor   - Мониторинг в реальном времени"
    echo "  help      - Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  sudo $0 start"
    echo "  sudo $0 status"
    echo "  $0 ip"
    echo "  $0 monitor"
}

# Основная логика
case "$1" in
    start)
        start_tor
        ;;
    stop)
        stop_tor
        ;;
    restart)
        restart_tor
        ;;
    status)
        show_status
        ;;
    ip)
        show_tor_ip
        ;;
    test)
        test_connection
        ;;
    logs)
        show_logs
        ;;
    monitor)
        monitor
        ;;
    help|--help|-h)
        show_help
        ;;
    "")
        show_help
        ;;
    *)
        print_error "Неизвестная команда: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
