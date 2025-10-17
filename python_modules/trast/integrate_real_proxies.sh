#!/bin/bash
# Быстрое исправление - интеграция реально рабочих прокси

echo "🔗 ИНТЕГРАЦИЯ РЕАЛЬНО РАБОЧИХ ПРОКСИ"
echo "===================================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📥 Обновляем код..."
git pull

echo "🔗 Интегрируем реально рабочие прокси..."
python3 integrate_real_proxies.py

echo "🚀 Запускаем парсер с реально рабочими прокси..."
python3 main.py

echo "✅ ГОТОВО!"
