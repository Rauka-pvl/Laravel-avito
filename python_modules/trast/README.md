# Парсер trast-zapchast.ru

Однопоточный парсер товаров с сайта trast-zapchast.ru с улучшенным обходом nginx и других систем защиты.

## Особенности

- ✅ Однопоточность для лучшего обхода защиты (nginx/cloudflare)
- ✅ Фильтрация прокси только из СНГ стран
- ✅ Использование undetected-chromedriver для Chrome
- ✅ Умное переиспользование cookies через cloudscraper
- ✅ Fallback на Selenium при необходимости
- ✅ Только через прокси (никакого прямого соединения)
- ✅ Экспорт в XLSX и CSV
- ✅ Логирование через loguru

## Установка

### Автоматическая установка (рекомендуется)

Используйте скрипты установки для автоматической настройки всех зависимостей:

**Windows:**
```bash
install.bat
```

**Linux/Mac:**
```bash
chmod +x install.sh
./install.sh
```

**Или через Python (кроссплатформенно):**
```bash
python install.py
```

Скрипты автоматически:
- Обновят pip
- Установят все зависимости из `requirements.txt`
- Обновят `undetected-chromedriver` для совместимости с Chrome
- Проверят установку пакетов

### Ручная установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
pip install --upgrade --force-reinstall undetected-chromedriver
```

2. Убедитесь, что установлены браузеры:
- Chrome/Chromium (для HTTP/HTTPS прокси)
- Firefox (для SOCKS прокси)

### Решение проблем с версией ChromeDriver

Если возникает ошибка несовместимости версий Chrome и ChromeDriver:
1. Обновите Chrome до последней версии
2. Запустите скрипт установки снова: `python install.py`
3. Парсер автоматически использует Firefox при ошибках Chrome

## Использование

Просто запустите:
```bash
python main.py
```

Парсер автоматически:
1. Загрузит прокси из источников (proxymania.su, proxifly, Proxy6, Proxys.io, Proxy-Seller, Floppydata, Prosox и др.)
2. Фильтрует прокси только из стран СНГ (RU, BY, KZ, AM, AZ, GE, KG, MD, TJ, TM, UZ, UA)
3. Обходит nginx JS challenge и другие системы защиты
4. Проверит прокси на доступность trast-zapchast.ru
5. Получит количество страниц
6. Начнет парсинг товаров
7. Сохранит результаты в `output/trast.csv` и `output/trast.xlsx`

## Структура проекта

```
trast_parser/
├── main.py              # Главный файл
├── proxy_manager.py     # Менеджер прокси
├── utils.py             # Вспомогательные функции
├── config.py            # Конфигурация
├── requirements.txt     # Зависимости
├── proxy_cache/         # Кэш прокси
├── output/              # Результаты парсинга
└── logs/                # Логи
```

## Логика пустой страницы

Пустая страница определяется как страница с 16 товарами, но все НЕ в наличии.
Парсинг останавливается после 2 пустых страниц подряд.

## Настройки

Все настройки находятся в `config.py`:
- Таймауты
- Количество рабочих прокси
- Фильтры по странам
- Пути к файлам

