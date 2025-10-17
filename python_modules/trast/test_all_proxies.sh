#!/bin/bash
# Тестирование ВСЕХ прокси для поиска работающих

echo "🧪 ТЕСТИРОВАНИЕ ВСЕХ ПРОКСИ"
echo "============================"

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🧪 Тестируем ВСЕ прокси..."
python3 test_all_proxies.py

echo "🚀 Запускаем парсер с найденными прокси..."
python3 main.py

echo "✅ ГОТОВО!"
