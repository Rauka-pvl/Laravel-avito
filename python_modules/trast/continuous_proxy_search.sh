#!/bin/bash
# Непрерывный поиск рабочего прокси

echo "🔍 НЕПРЕРЫВНЫЙ ПОИСК РАБОЧЕГО ПРОКСИ"
echo "====================================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🔍 Запускаем непрерывный поиск прокси..."
python3 continuous_proxy_finder.py

echo "🔧 Управляем прокси с автоматическим переключением..."
python3 smart_proxy_manager.py

echo "🚀 Запускаем парсер с найденными прокси..."
python3 main.py

echo "✅ ГОТОВО!"
