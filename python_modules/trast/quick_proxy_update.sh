#!/bin/bash
# Скрипт для быстрого обновления прокси на сервере

echo "🚀 БЫСТРОЕ ОБНОВЛЕНИЕ ПРОКСИ НА СЕРВЕРЕ"
echo "======================================"

# Переходим в директорию парсера
cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🔗 Интегрируем найденные прокси..."
python3 integrate_proxies.py

echo "🧪 Тестируем обход Cloudflare..."
python3 test_cloudflare_bypass.py

echo "🚀 Запускаем парсер..."
python3 main.py

echo "✅ ГОТОВО!"
