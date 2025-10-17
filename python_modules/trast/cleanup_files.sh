#!/bin/bash
# Очистка лишних файлов - наведение порядка

echo "🧹 НАВЕДЕНИЕ ПОРЯДКА В ФАЙЛАХ"
echo "=============================="

cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/

echo "📁 Текущие файлы:"
ls -la | wc -l
echo "файлов найдено"

echo ""
echo "🗑️ УДАЛЯЕМ ЛИШНИЕ ФАЙЛЫ..."

# Удаляем старые тестовые файлы
echo "Удаляем тестовые файлы..."
rm -f test_*.py
rm -f test_*.sh
rm -f *_test_*.py
rm -f *_test_*.sh

# Удаляем старые hunter'ы
echo "Удаляем старые hunter'ы..."
rm -f proxy_hunter.py
rm -f proxyscrape_hunter.py
rm -f continuous_proxy_hunter.py
rm -f continuous_proxy_finder.py
rm -f smart_proxy_manager.py

# Удаляем старые интеграторы
echo "Удаляем старые интеграторы..."
rm -f integrate_proxies.py
rm -f integrate_real_proxies.py
rm -f integrate_real_proxies.sh
rm -f quick_integrate_proxies.py

# Удаляем старые скрипты обновления
echo "Удаляем старые скрипты обновления..."
rm -f update_proxies.py
rm -f quick_proxy_update.sh
rm -f quick_update.sh
rm -f quick_fix_proxies.sh

# Удаляем диагностические файлы
echo "Удаляем диагностические файлы..."
rm -f proxy_diagnostic.py
rm -f test_alternative_strategies.py
rm -f test_all_strategies.sh
rm -f test_direct_connection.py
rm -f test_cloudflare_bypass.py
rm -f test_browsers.py
rm -f test_parser.py

# Удаляем старые скрипты установки
echo "Удаляем старые скрипты установки..."
rm -f install_cloudflare_deps.py
rm -f install_chrome.sh
rm -f install_firefox.sh
rm -f install.py
rm -f quick_start.py
rm -f server_setup.sh

# Удаляем старые скрипты исправления
echo "Удаляем старые скрипты исправления..."
rm -f quick_fix.sh
rm -f fix_all_problems.sh
rm -f fix_git_conflicts.sh
rm -f fix_git_conflicts.ps1

# Удаляем старые скрипты загрузки
echo "Удаляем старые скрипты загрузки..."
rm -f upload_proxies.py

# Удаляем старые README
echo "Удаляем старые README..."
rm -f PROXY_HUNTING_README.md
rm -f GIT_CONFLICTS_FIX.md

# Удаляем старые скрипты поиска
echo "Удаляем старые скрипты поиска..."
rm -f continuous_proxy_search.sh

# Удаляем старые скрипты тестирования
echo "Удаляем старые скрипты тестирования..."
rm -f test_all_proxies.py
rm -f test_all_proxies.sh

# Удаляем старые скрипты отладки
echo "Удаляем старые скрипты отладки..."
rm -f debug_parser.py

# Удаляем временные файлы
echo "Удаляем временные файлы..."
rm -f *.log
rm -f *.tmp
rm -f *.bak
rm -f *~

# Удаляем старые файлы прокси
echo "Удаляем старые файлы прокси..."
rm -f working_proxies_*.json
rm -f working_proxies_*.txt
rm -f russian_proxies_*.json
rm -f russian_proxies_*.txt
rm -f real_working_proxies_*.json
rm -f real_working_proxies_*.txt
rm -f universal_working_proxies_*.json
rm -f universal_working_proxies_*.txt
rm -f continuous_working_proxies_*.json
rm -f continuous_working_proxies_*.txt
rm -f proxyscrape_*.json
rm -f proxyscrape_*.txt
rm -f verified_*.json
rm -f verified_*.txt
rm -f real_page_proxy_test_*.json
rm -f universal_proxy_hunter_*.json

# Удаляем старые файлы из v0.1 (кроме самого v0.1)
echo "Удаляем старые файлы из v0.1..."
rm -rf v0.1/backups
rm -f v0.1/68f0af05c9bf6.txt
rm -f v0.1/learning_data.json
rm -f v0.1/proxies*.json
rm -f v0.1/test_*.py
rm -f v0.1/install_*.sh
rm -f v0.1/README.md

echo ""
echo "📁 Файлы после очистки:"
ls -la | wc -l
echo "файлов осталось"

echo ""
echo "📋 Оставшиеся файлы:"
ls -la

echo ""
echo "✅ ОЧИСТКА ЗАВЕРШЕНА!"
echo "Оставлены только необходимые файлы:"
echo "  - config.py (конфигурация)"
echo "  - connection_manager.py (управление подключениями)"
echo "  - logger_setup.py (настройка логирования)"
echo "  - main.py (основной парсер)"
echo "  - parser.py (парсинг страниц)"
echo "  - proxy_manager.py (управление прокси)"
echo "  - requirements.txt (зависимости)"
echo "  - universal_proxy_hunter.py (универсальный охотник)"
echo "  - universal_proxy_hunter.sh (скрипт запуска)"
echo "  - v0.1/ (резервная копия)"
