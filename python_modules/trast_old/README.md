# Trast Parser

## Установка на Ubuntu/VPS

```bash
# Установка Firefox для Selenium
sudo apt-get update
sudo apt-get install -y firefox

# Установка зависимостей
pip3 install -r ../requirements.txt
```

## Запуск

```bash
cd python_modules/trast
python3 main.py
```

## Что делает парсер

1. Автоматически скачивает российские прокси из репозитория Proxifly
2. Проверяет их работоспособность (базовая + доступ к сайту через Selenium)
3. Парсит товары с сайта trast-zapchast.ru через рабочие прокси
4. Сохраняет результаты в Excel и CSV

## Файлы

- `main.py` - основной файл для запуска
- `proxy_manager.py` - управление прокси
- `.gitignore` - исключает временные файлы

## Результаты

- Excel: `storage/app/public/output/trast.xlsx`
- CSV: `storage/app/public/output/trast.csv`
- Логи: `storage/app/public/output/logs-trast/`

