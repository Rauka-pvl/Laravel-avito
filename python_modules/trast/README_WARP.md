# 🌐 Cloudflare WARP Integration для Trast Parser

## Обзор

Интеграция Cloudflare WARP в модульный парсер Trast обеспечивает дополнительный уровень защиты и обхода блокировок.

## Преимущества WARP

- **Быстрая скорость**: WARP оптимизирован для скорости
- **Глобальная сеть**: Использует сеть Cloudflare по всему миру
- **Автоматическая ротация IP**: Меняет IP адреса автоматически
- **Стабильность**: Высокая надежность подключения
- **Простота использования**: Легкая настройка и управление

## Приоритет подключений

Парсер использует следующую иерархию подключений:

1. **WARP** (приоритет 1) - если доступен и работает
2. **Tor** (приоритет 2) - если WARP недоступен
3. **Прокси пул** (приоритет 3) - если Tor недоступен

## ⚠️ ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ

**НИКОГДА не используйте `warp-cli set-mode warp` на сервере!**

Это заблокирует SSH и все другие соединения. Всегда используйте `warp-cli set-mode proxy`.

## Установка WARP

### Автоматическая установка (безопасная)

```bash
sudo ./install_warp.sh
```

Скрипт автоматически устанавливает безопасный proxy-only режим.

### Ручная установка

```bash
# Ubuntu/Debian
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list
sudo apt update
sudo apt install -y cloudflare-warp

# Регистрация
warp-cli registration new

# Подключение
warp-cli connect
```

## Управление WARP

### Команды управления

```bash
# Подключение
warp-parser start

# Отключение
warp-parser stop

# Статус
warp-parser status

# Текущий IP
warp-parser ip

# Тест подключения
warp-parser test
```

### Прямые команды WARP

```bash
# Статус
warp-cli status

# Подключение
warp-cli connect

# Отключение
warp-cli disconnect

# Регистрация
warp-cli registration new

# Информация о регистрации
warp-cli registration show
```

## Конфигурация

### Настройки в config.py

```python
# WARP configuration
WARP_ENABLED = True
WARP_PROXY_URL = "socks5://127.0.0.1:40000"  # Default WARP proxy port
WARP_ALTERNATIVE_PORTS = [40000, 40001, 40002, 40003, 40004]
```

### Порты WARP

WARP использует следующие порты по умолчанию:
- **40000** - основной порт
- **40001-40004** - альтернативные порты

## Мониторинг

### Статистика WARP

```python
warp_manager = WARPManager()
stats = warp_manager.get_stats()

print(f"WARP enabled: {stats['warp_enabled']}")
print(f"WARP connected: {stats['is_connected']}")
print(f"WARP available: {stats['is_available']}")
print(f"Current IP: {stats['current_ip']}")
```

### Логи

WARP события логируются с префиксом `🌐`:

```
🌐 Using WARP connection
🔄 Rotating WARP IP...
✅ WARP IP rotated to: 1.2.3.4
```

## 🚨 Экстренное восстановление SSH

Если SSH заблокирован после установки WARP:

### Быстрое исправление

```bash
# Запустите этот скрипт
sudo ./emergency_fix.sh
```

### Ручное исправление

```bash
# Отключить WARP
warp-cli disconnect

# Установить безопасный режим
warp-cli mode proxy

# Проверить статус
warp-cli status
```

### Если SSH все еще не работает

1. **Перезагрузите сервер** через панель управления хостинга
2. **Используйте консоль хостинга** для доступа к серверу
3. **Обратитесь в поддержку хостинга** для восстановления доступа

## Устранение неполадок

### WARP не подключается

1. Проверьте статус:
   ```bash
   warp-cli status
   ```

2. Перерегистрируйтесь:
   ```bash
   warp-cli registration delete
   warp-cli registration new
   ```

3. Перезапустите WARP:
   ```bash
   warp-cli disconnect
   warp-cli connect
   ```

### Проблемы с портами

1. Проверьте доступные порты:
   ```bash
   netstat -tlnp | grep 4000
   ```

2. Тестируйте подключение:
   ```bash
   curl --socks5 127.0.0.1:40000 https://httpbin.org/ip
   ```

### Автозапуск

Для автоматического запуска WARP при загрузке системы:

```bash
sudo systemctl enable warp-parser
sudo systemctl start warp-parser
```

## Интеграция с парсером

### Автоматическое использование

Парсер автоматически определяет доступность WARP и использует его в приоритетном порядке.

### Ручное управление

```python
from modules.warp_manager import WARPManager

warp = WARPManager()

# Проверка доступности
if warp.is_available():
    print("WARP доступен")
    
# Получение конфигурации прокси
proxy_config = warp.get_proxy_config()
if proxy_config:
    print(f"Используем WARP: {proxy_config}")

# Ротация IP
if warp.rotate_ip():
    print("IP успешно изменен")
```

## Производительность

### Сравнение скоростей

- **WARP**: ~50-100ms задержка
- **Tor**: ~200-500ms задержка  
- **Прокси**: ~100-300ms задержка

### Рекомендации

1. **Для максимальной скорости**: Используйте только WARP
2. **Для максимальной анонимности**: Используйте Tor
3. **Для баланса**: Используйте гибридную стратегию (WARP → Tor → Прокси)

## Безопасность

### Преимущества WARP

- Шифрование трафика
- Защита от DDoS
- Скрытие реального IP
- Защита от отслеживания

### Ограничения

- WARP не обеспечивает полную анонимность как Tor
- Cloudflare может логировать подключения
- Требует регистрации в Cloudflare

## Заключение

Интеграция WARP значительно улучшает производительность и надежность парсера, обеспечивая быстрый и стабильный доступ к целевым сайтам с минимальными задержками.
