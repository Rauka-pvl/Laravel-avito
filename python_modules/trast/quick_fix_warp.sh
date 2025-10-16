#!/bin/bash

# Быстрое исправление WARP для восстановления SSH
# Используется когда WARP заблокировал сеть

echo "🚨 Быстрое исправление WARP для восстановления SSH"
echo "=================================================="

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт с правами root: sudo ./quick_fix_warp.sh"
    exit 1
fi

echo "🔧 Выполняем экстренное исправление..."

# 1. Отключение WARP
echo "1️⃣ Отключаем WARP..."
if warp-cli disconnect; then
    echo "✅ WARP отключен"
else
    echo "⚠️ Ошибка отключения WARP (возможно, уже отключен)"
fi

# 2. Установка безопасного режима
echo "2️⃣ Устанавливаем безопасный режим (proxy-only)..."
if warp-cli mode proxy; then
    echo "✅ Безопасный режим установлен"
else
    echo "❌ Ошибка установки безопасного режима"
    exit 1
fi

# 3. Проверка статуса
echo "3️⃣ Проверяем статус..."
WARP_STATUS=$(warp-cli status)
echo "Статус WARP: $WARP_STATUS"

# 4. Проверка настроек
echo "4️⃣ Проверяем настройки..."
warp-cli settings list | grep "Mode:"

# 5. Тест SSH
echo "5️⃣ Тестируем SSH..."
if systemctl is-active --quiet ssh; then
    echo "✅ SSH сервис активен"
else
    echo "⚠️ SSH сервис неактивен, пытаемся запустить..."
    systemctl start ssh
fi

# 6. Тест сети
echo "6️⃣ Тестируем сеть..."
if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
    echo "✅ Сеть работает"
else
    echo "⚠️ Проблемы с сетью, перезапускаем сетевые службы..."
    systemctl restart networking
fi

echo ""
echo "🎉 Исправление завершено!"
echo "========================"
echo ""
echo "✅ WARP отключен"
echo "✅ Безопасный режим установлен"
echo "✅ SSH должен работать"
echo ""
echo "📋 Для проверки выполните:"
echo "  warp-cli status"
echo "  systemctl status ssh"
echo "  ping 8.8.8.8"
echo ""
echo "💡 Для безопасного подключения к WARP:"
echo "  warp-cli connect"
echo ""
echo "🛡️ Теперь WARP безопасен для использования!"
