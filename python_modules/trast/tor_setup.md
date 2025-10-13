# Установка Tor для парсера Trast

## Установка Tor на Ubuntu/Debian

```bash
# Обновляем пакеты
sudo apt update

# Устанавливаем Tor
sudo apt install tor

# Устанавливаем Firefox (если не установлен)
sudo apt install firefox

# Проверяем установку
tor --version
firefox --version
```

## Настройка Tor

### 1. Создание конфигурации Tor

```bash
# Создаем директорию для данных Tor
sudo mkdir -p /tmp/tor_data
sudo chmod 755 /tmp/tor_data

# Создаем файл cookie для аутентификации
sudo touch /tmp/tor_cookie
sudo chmod 600 /tmp/tor_cookie
```

### 2. Запуск Tor вручную (для тестирования)

```bash
# Запускаем Tor с нашими настройками
tor --SOCKSPort 9050 --ControlPort 9051 --DataDirectory /tmp/tor_data --CookieAuthentication 1 --CookieAuthFile /tmp/tor_cookie
```

### 3. Проверка работы Tor

```bash
# Проверяем, что Tor слушает на портах
netstat -tlnp | grep 9050
netstat -tlnp | grep 9051

# Тестируем подключение через Tor
curl --socks5 127.0.0.1:9050 https://httpbin.org/ip
```

## Автоматический запуск Tor

### Создание systemd сервиса

```bash
# Создаем файл сервиса
sudo nano /etc/systemd/system/tor-parser.service
```

Содержимое файла:
```ini
[Unit]
Description=Tor service for parser
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/tor --SOCKSPort 9050 --ControlPort 9051 --DataDirectory /tmp/tor_data --CookieAuthentication 1 --CookieAuthFile /tmp/tor_cookie
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Активация сервиса

```bash
# Перезагружаем systemd
sudo systemctl daemon-reload

# Включаем автозапуск
sudo systemctl enable tor-parser

# Запускаем сервис
sudo systemctl start tor-parser

# Проверяем статус
sudo systemctl status tor-parser
```

## Установка Python зависимостей

```bash
# Устанавливаем дополнительные зависимости для Firefox
pip install webdriver-manager

# Обновляем requirements.txt
pip install -r requirements.txt
```

## Тестирование парсера с Tor

```bash
# Запускаем парсер
cd python_modules/trast
python main.py
```

## Логи и диагностика

### Проверка логов Tor

```bash
# Логи systemd сервиса
sudo journalctl -u tor-parser -f

# Логи Tor (если запущен вручную)
tail -f /tmp/tor_data/tor.log
```

### Проверка подключения

```bash
# Проверяем IP через Tor
curl --socks5 127.0.0.1:9050 https://httpbin.org/ip

# Проверяем доступность сайта через Tor
curl --socks5 127.0.0.1:9050 https://trast-zapchast.ru/shop/
```

## Преимущества Tor + Firefox

1. **Анонимность**: Полная анонимность через сеть Tor
2. **Обход блокировок**: Автоматический обход IP блокировок
3. **Стабильность**: Меньше детектирования автоматизации
4. **Производительность**: Firefox оптимизирован для парсинга
5. **Надежность**: Автоматическое переключение узлов Tor

## Fallback стратегия

Если Tor недоступен, парсер автоматически переключится на:
1. Chrome с прокси серверами
2. Прямое подключение с усиленной anti-detection

## Мониторинг

Парсер будет логировать:
- Статус запуска Tor
- IP адрес через Tor
- Переключение между режимами
- Ошибки подключения
