#!/bin/bash

# Скрипт восстановления SSH после установки WARP
# Исправляет проблему с блокировкой SSH трафика

set -e

echo "🔧 Восстановление SSH соединения после установки WARP"
echo "====================================================="

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт с правами root: sudo ./fix_warp_ssh.sh"
    exit 1
fi

echo "📋 Диагностика текущего состояния WARP..."

# Проверка статуса WARP
echo "🔍 Статус WARP:"
warp-cli status

echo ""
echo "🔍 Текущий режим WARP:"
warp-cli settings

echo ""
echo "🔧 Исправление проблемы..."

# 1. Отключение WARP
echo "1️⃣ Отключение WARP..."
warp-cli disconnect

# 2. Установка режима proxy-only (не влияет на весь трафик)
echo "2️⃣ Установка режима proxy-only..."
warp-cli set-mode proxy

# 3. Проверка режима
echo "3️⃣ Проверка режима..."
warp-cli settings

# 4. Перезапуск сетевых служб
echo "4️⃣ Перезапуск сетевых служб..."
systemctl restart networking 2>/dev/null || true
systemctl restart NetworkManager 2>/dev/null || true

# 5. Очистка DNS кэша
echo "5️⃣ Очистка DNS кэша..."
systemctl flush-dns 2>/dev/null || true
systemctl restart systemd-resolved 2>/dev/null || true

# 6. Проверка SSH службы
echo "6️⃣ Проверка SSH службы..."
systemctl status ssh --no-pager || systemctl status sshd --no-pager

# 7. Перезапуск SSH если нужно
echo "7️⃣ Перезапуск SSH службы..."
systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true

# 8. Проверка сетевых интерфейсов
echo "8️⃣ Проверка сетевых интерфейсов..."
ip route show

echo ""
echo "✅ Исправление завершено!"
echo ""
echo "📋 Рекомендации:"
echo "1. Проверьте SSH соединение с другого терминала"
echo "2. Если SSH все еще не работает, перезагрузите сервер"
echo "3. Для безопасного использования WARP используйте только proxy режим"
echo ""
echo "🔧 Команды для управления WARP:"
echo "  warp-cli set-mode proxy    # Только прокси (безопасно для SSH)"
echo "  warp-cli set-mode warp     # Весь трафик (может заблокировать SSH)"
echo "  warp-cli disconnect        # Отключить WARP"
echo "  warp-cli connect           # Подключить WARP"
echo ""
echo "⚠️  ВНИМАНИЕ: Никогда не используйте 'warp-cli set-mode warp' на сервере!"
echo "   Это заблокирует SSH и другие соединения!"
