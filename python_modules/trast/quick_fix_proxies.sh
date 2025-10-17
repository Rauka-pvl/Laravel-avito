#!/bin/bash
# Быстрое исправление проблемы с прокси

echo "🔧 БЫСТРОЕ ИСПРАВЛЕНИЕ ПРОКСИ"
echo "=============================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🔗 Интегрируем найденные прокси..."
python3 quick_integrate_proxies.py

echo "🚀 Запускаем парсер..."
python3 main.py

echo "✅ ГОТОВО!"
