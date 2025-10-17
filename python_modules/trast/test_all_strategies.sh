#!/bin/bash
# Скрипт для быстрого тестирования всех стратегий обхода блокировок

echo "🚀 БЫСТРОЕ ТЕСТИРОВАНИЕ СТРАТЕГИЙ ОБХОДА БЛОКИРОВОК"
echo "=================================================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🔍 Диагностируем проблемы с прокси..."
python3 proxy_diagnostic.py

echo "🧪 Тестируем альтернативные стратегии..."
python3 test_alternative_strategies.py

echo "🇷🇺 Тестируем российские прокси..."
python3 test_russian_proxies.py

echo "🎯 Непрерывный поиск рабочего прокси..."
python3 continuous_proxy_hunter.py

echo "🧪 Тестируем обход Cloudflare..."
python3 test_cloudflare_bypass.py

echo "🚀 Запускаем парсер..."
python3 main.py

echo "✅ ГОТОВО!"
