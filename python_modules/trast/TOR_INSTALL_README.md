# 🚀 Автоматическая установка Tor для парсера Trast

## 📋 Описание

Созданы скрипты для автоматической установки и управления Tor на Linux сервере для работы с парсером Trast.

## 📁 Файлы

### 1. `install_tor.sh` - Полная установка
- Автоматическая установка Tor и Firefox
- Настройка systemd сервиса
- Создание конфигурации
- Тестирование подключения
- Создание скриптов управления

### 2. `quick_install_tor.sh` - Быстрая установка
- Минимальная установка Tor
- Базовые настройки
- Быстрый запуск

### 3. `tor_manager.sh` - Управление Tor
- Запуск/остановка Tor
- Проверка статуса
- Мониторинг
- Тестирование подключения

## 🛠️ Установка на сервере

### Вариант 1: Полная установка
```bash
# Загрузить скрипт на сервер
scp install_tor.sh root@your-server:/tmp/

# Подключиться к серверу
ssh root@your-server

# Сделать исполняемым и запустить
chmod +x /tmp/install_tor.sh
/tmp/install_tor.sh
```

### Вариант 2: Быстрая установка
```bash
# Загрузить скрипт на сервер
scp quick_install_tor.sh root@your-server:/tmp/

# Подключиться к серверу
ssh root@your-server

# Сделать исполняемым и запустить
chmod +x /tmp/quick_install_tor.sh
/tmp/quick_install_tor.sh
```

### Вариант 3: Только Tor (если Firefox недоступен)
```bash
# Загрузить скрипт на сервер
scp install_tor_only.sh root@your-server:/tmp/

# Подключиться к серверу
ssh root@your-server

# Сделать исполняемым и запустить
chmod +x /tmp/install_tor_only.sh
/tmp/install_tor_only.sh
```

## 🔧 Управление Tor

### Загрузить скрипт управления
```bash
scp tor_manager.sh root@your-server:/usr/local/bin/
ssh root@your-server
chmod +x /usr/local/bin/tor_manager.sh
```

### Команды управления
```bash
# Запустить Tor
sudo tor_manager.sh start

# Остановить Tor
sudo tor_manager.sh stop

# Перезапустить Tor
sudo tor_manager.sh restart

# Проверить статус
tor_manager.sh status

# Показать IP через Tor
tor_manager.sh ip

# Тестировать подключение
tor_manager.sh test

# Показать логи
tor_manager.sh logs

# Мониторинг в реальном времени
tor_manager.sh monitor
```

## 🎯 Что делает установка

### 1. Устанавливает пакеты
- `tor` - Tor браузер
- `firefox-esr` - Firefox браузер

### 2. Создает конфигурацию
- SOCKS порт: 9050
- Control порт: 9051
- Директория данных: `/tmp/tor_data`
- Логи: `/var/log/tor/tor.log`

### 3. Настраивает systemd сервис
- Имя: `tor-parser`
- Автозапуск: включен
- Перезапуск при сбоях: включен

### 4. Тестирует подключение
- Проверяет доступность портов
- Тестирует подключение через Tor
- Проверяет доступность сайта

## 📊 Мониторинг

### Проверка статуса
```bash
# Статус сервиса
systemctl status tor-parser

# Логи в реальном времени
journalctl -u tor-parser -f

# Проверка портов
netstat -tlnp | grep 9050
netstat -tlnp | grep 9051
```

### Тестирование подключения
```bash
# Проверка IP через Tor
curl --socks5 127.0.0.1:9050 https://httpbin.org/ip

# Проверка сайта
curl --socks5 127.0.0.1:9050 -I https://trast-zapchast.ru/shop/
```

## 🚀 Запуск парсера

После установки Tor можно запускать парсер:

```bash
cd python_modules/trast
python main.py
```

Парсер автоматически:
1. Проверит доступность Tor
2. Запустит Tor если нужно
3. Создаст Firefox с Tor
4. Начнет парсинг

## 🔍 Диагностика проблем

### Tor не запускается
```bash
# Проверить логи
journalctl -u tor-parser -f

# Проверить конфигурацию
cat /etc/tor/torrc

# Проверить права доступа
ls -la /tmp/tor_data
```

### Подключение не работает
```bash
# Проверить порты
netstat -tlnp | grep 9050

# Тестировать подключение
curl --socks5 127.0.0.1:9050 --connect-timeout 10 https://httpbin.org/ip

# Проверить файрвол
iptables -L | grep 9050
```

### Сайт недоступен
```bash
# Проверить через Tor
curl --socks5 127.0.0.1:9050 -I https://trast-zapchast.ru/shop/

# Проверить без Tor
curl -I https://trast-zapchast.ru/shop/

# Проверить DNS
nslookup trast-zapchast.ru
```

## 📋 Требования

- Ubuntu/Debian/CentOS/Arch Linux
- Права root
- Интернет подключение
- Минимум 512MB RAM
- Минимум 100MB свободного места

## 🎉 Результат

После установки у вас будет:
- ✅ Tor установлен и настроен
- ✅ Firefox установлен
- ✅ Systemd сервис создан
- ✅ Автозапуск включен
- ✅ Скрипты управления созданы
- ✅ Парсер готов к работе

## 🔄 Обновление

Для обновления Tor:
```bash
# Остановить сервис
sudo tor_manager.sh stop

# Обновить пакеты
sudo apt update && sudo apt upgrade tor

# Запустить сервис
sudo tor_manager.sh start
```

## 🗑️ Удаление

Для удаления Tor:
```bash
# Остановить и отключить сервис
sudo systemctl stop tor-parser
sudo systemctl disable tor-parser

# Удалить файлы
sudo rm /etc/systemd/system/tor-parser.service
sudo rm -rf /tmp/tor_data
sudo rm /tmp/tor_cookie

# Удалить пакеты
sudo apt remove tor firefox-esr

# Перезагрузить systemd
sudo systemctl daemon-reload
```

---

**🎯 Tor готов к работе с парсером Trast!**
