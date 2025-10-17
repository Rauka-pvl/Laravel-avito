# Решение конфликтов git с learning_data.json

## Проблема
Файл `learning_data.json` создается парсером и вызывает конфликты при `git pull`.

## Быстрое решение (на сервере)

### Вариант 1: Автоматический скрипт
```bash
cd /home/admin/web/233204.fornex.cloud/public_html/python_modules/trast/
chmod +x fix_git_conflicts.sh
./fix_git_conflicts.sh
```

### Вариант 2: Ручное решение
```bash
# 1. Сохраняем файл
cp learning_data.json learning_data.json.backup

# 2. Удаляем из git tracking
git rm --cached learning_data.json

# 3. Делаем pull
git pull

# 4. Восстанавливаем файл
mv learning_data.json.backup learning_data.json
```

### Вариант 3: Через stash
```bash
git stash push -m "Save learning_data.json" learning_data.json
git pull
git stash pop
```

## Предотвращение конфликтов

1. **Файл уже в .gitignore** - конфликты больше не должны возникать
2. **Используйте скрипт** при возникновении конфликтов
3. **Регулярно делайте pull** перед запуском парсера

## Проверка статуса
```bash
git status
git ls-files | grep learning_data  # Не должно показывать файл
```

## Если проблема повторяется
```bash
# Принудительно исключаем файл
echo "learning_data.json" >> .gitignore
git add .gitignore
git commit -m "Add learning_data.json to gitignore"
git push
```
