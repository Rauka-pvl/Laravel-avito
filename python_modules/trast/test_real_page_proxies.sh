#!/bin/bash
# Тестирование прокси на реальную загрузку страницы сайта

echo "🧪 ТЕСТИРОВАНИЕ ПРОКСИ НА РЕАЛЬНУЮ ЗАГРУЗКУ СТРАНИЦЫ"
echo "=================================================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🧪 Тестируем прокси на реальную загрузку страницы..."
python3 test_real_page_proxies.py

echo "🚀 Запускаем парсер с реально рабочими прокси..."
python3 main.py

echo "✅ ГОТОВО!"
