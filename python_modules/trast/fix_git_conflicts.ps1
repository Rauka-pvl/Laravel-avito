# PowerShell скрипт для решения конфликтов git с learning_data.json
# Использование: .\fix_git_conflicts.ps1

Write-Host "🔧 Исправление конфликтов git с learning_data.json" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

# Проверяем, есть ли конфликтующий файл
if (Test-Path "learning_data.json") {
    Write-Host "📁 Найден файл learning_data.json" -ForegroundColor Yellow
    
    # Создаем бэкап
    Write-Host "💾 Создаем бэкап файла..." -ForegroundColor Blue
    Copy-Item "learning_data.json" "learning_data.json.backup"
    
    # Удаляем файл из git tracking
    Write-Host "🗑️ Удаляем файл из git tracking..." -ForegroundColor Blue
    try {
        git rm --cached learning_data.json 2>$null
    } catch {
        Write-Host "Файл не отслеживается git" -ForegroundColor Gray
    }
    
    # Принудительно добавляем в .gitignore
    Write-Host "📝 Обновляем .gitignore..." -ForegroundColor Blue
    $gitignoreContent = Get-Content .gitignore -ErrorAction SilentlyContinue
    if ($gitignoreContent -notcontains "learning_data.json") {
        Add-Content .gitignore "learning_data.json"
    }
    
    # Восстанавливаем файл
    Write-Host "🔄 Восстанавливаем файл..." -ForegroundColor Blue
    Move-Item "learning_data.json.backup" "learning_data.json"
    
    Write-Host "✅ Файл восстановлен и исключен из git" -ForegroundColor Green
} else {
    Write-Host "ℹ️ Файл learning_data.json не найден" -ForegroundColor Gray
}

# Выполняем git pull с принудительным сбросом
Write-Host "🔄 Выполняем git pull..." -ForegroundColor Blue

# Пробуем stash
try {
    git stash push -m "Auto-stash learning_data.json" learning_data.json 2>$null
} catch {
    Write-Host "Нет изменений для stash" -ForegroundColor Gray
}

# Пробуем pull
try {
    git pull
    Write-Host "✅ Git pull выполнен успешно" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Конфликт все еще есть, применяем принудительное решение..." -ForegroundColor Yellow
    
    # Принудительно сбрасываем изменения в файле
    try {
        git checkout HEAD -- learning_data.json 2>$null
    } catch {
        Write-Host "Файл не в репозитории" -ForegroundColor Gray
    }
    
    # Повторяем pull
    git pull
}

# Восстанавливаем файл из stash если нужно
$stashList = git stash list 2>$null
if ($stashList -match "learning_data.json") {
    Write-Host "🔄 Восстанавливаем learning_data.json из stash..." -ForegroundColor Blue
    try {
        git stash pop 2>$null
    } catch {
        Write-Host "Не удалось восстановить из stash" -ForegroundColor Gray
    }
}

Write-Host "🎉 Готово! Конфликты решены." -ForegroundColor Green
Write-Host ""
Write-Host "📋 Для предотвращения будущих конфликтов:" -ForegroundColor Cyan
Write-Host "   1. Файл learning_data.json теперь в .gitignore" -ForegroundColor White
Write-Host "   2. Используйте этот скрипт при конфликтах: .\fix_git_conflicts.ps1" -ForegroundColor White
Write-Host "   3. Или выполните: git stash && git pull && git stash pop" -ForegroundColor White
