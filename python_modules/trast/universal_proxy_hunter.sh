#!/bin/bash
# Универсальный охотник за прокси

echo "🎯 УНИВЕРСАЛЬНЫЙ ОХОТНИК ЗА ПРОКСИ"
echo "=================================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🎯 Запускаем универсальный охотник за прокси..."
echo "Этот процесс может занять много времени..."
echo "Нажмите Ctrl+C для остановки"
python3 universal_proxy_hunter.py

echo "🚀 Запускаем парсер с найденными прокси..."
python3 main.py

echo "✅ ГОТОВО!"
