#!/bin/bash
# Полное исправление всех проблем с прокси и парсингом

echo "🔧 ПОЛНОЕ ИСПРАВЛЕНИЕ ПРОБЛЕМ"
echo "============================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🔗 Интегрируем найденные прокси..."
python3 quick_integrate_proxies.py

echo "🧪 Тестируем прямое подключение..."
python3 test_direct_connection.py

echo "🚀 Запускаем парсер с исправлениями..."
python3 main.py

echo "✅ ГОТОВО!"
