#!/bin/bash

# Скрипт для решения конфликтов git с learning_data.json
# Использование: ./fix_git_conflicts.sh

echo "🔧 Исправление конфликтов git с learning_data.json"
echo "=================================================="

# Проверяем, есть ли конфликтующий файл
if [ -f "learning_data.json" ]; then
    echo "📁 Найден файл learning_data.json"
    
    # Создаем бэкап
    echo "💾 Создаем бэкап файла..."
    cp learning_data.json learning_data.json.backup
    
    # Удаляем файл из git tracking
    echo "🗑️ Удаляем файл из git tracking..."
    git rm --cached learning_data.json 2>/dev/null || echo "Файл не отслеживается git"
    
    # Принудительно добавляем в .gitignore
    echo "📝 Обновляем .gitignore..."
    if ! grep -q "learning_data.json" .gitignore; then
        echo "learning_data.json" >> .gitignore
    fi
    
    # Восстанавливаем файл
    echo "🔄 Восстанавливаем файл..."
    mv learning_data.json.backup learning_data.json
    
    echo "✅ Файл восстановлен и исключен из git"
else
    echo "ℹ️ Файл learning_data.json не найден"
fi

# Выполняем git pull с принудительным сбросом
echo "🔄 Выполняем git pull..."
git stash push -m "Auto-stash learning_data.json" learning_data.json 2>/dev/null || echo "Нет изменений для stash"

# Пробуем pull
if git pull; then
    echo "✅ Git pull выполнен успешно"
else
    echo "⚠️ Конфликт все еще есть, применяем принудительное решение..."
    
    # Принудительно сбрасываем изменения в файле
    git checkout HEAD -- learning_data.json 2>/dev/null || echo "Файл не в репозитории"
    
    # Повторяем pull
    git pull
fi

# Восстанавливаем файл из stash если нужно
if git stash list | grep -q "learning_data.json"; then
    echo "🔄 Восстанавливаем learning_data.json из stash..."
    git stash pop 2>/dev/null || echo "Не удалось восстановить из stash"
fi

echo "🎉 Готово! Конфликты решены."
echo ""
echo "📋 Для предотвращения будущих конфликтов:"
echo "   1. Файл learning_data.json теперь в .gitignore"
echo "   2. Используйте этот скрипт при конфликтах: ./fix_git_conflicts.sh"
echo "   3. Или выполните: git stash && git pull && git stash pop"
