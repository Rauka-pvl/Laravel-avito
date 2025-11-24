# Структура прокси-серверов в проекте

## Общая информация
Проект: VPN для ChatGPT (Chrome Extension)
Версия: 4.5
Дата обновления: 15.10.2025

---

## 1. Жестко заданные прокси-серверы (Hardcoded)

**Файл:** `js/conf.js`  
**Переменная:** `serverConfigs`

### Список прокси:

| № | Хост | Порт | Логин | Пароль | Тип | Статус |
|---|------|------|-------|--------|-----|--------|
| 1 | nl-hub.freeruproxy.ink | 443 | openproxy | 2ad5c3cece9f19f6 | HTTPS | Free |
| 2 | srv10.undiscord.com | 443 | discord_0.0.2 | dkVDPxFyi5IWnGnHjvj2jY5V | HTTPS | Free |
| 3 | 62.133.62.12 | 1081 | - | - | PROXY | Free |
| 4 | 178.130.47.129 | 1082 | - | - | PROXY | Free |

### Формат хранения:
```javascript
var serverConfigs=[
    'nl-hub.freeruproxy.ink:443:openproxy:2ad5c3cece9f19f6',
    "srv10.undiscord.com:443:discord_0.0.2:dkVDPxFyi5IWnGnHjvj2jY5V",
    "62.133.62.12:1081",
    "178.130.47.129:1082"
];
```

### Формат строки прокси:
- **С аутентификацией:** `host:port:login:pass`
- **Без аутентификации:** `host:port`

---

## 2. Динамические прокси-серверы (Dynamic)

**Источники загрузки:**
- Telegram канал: `https://t.me/liservers/15`
- Telegraph страница: `https://telegra.ph/Servers-10-16-15`

**Хранение:** Chrome Storage (`chrome.storage.local`)  
**Ключ:** `servers`  
**Формат:** JSON массив base64-encoded строк

### Структура данных:

#### Формат base64 строки:
```
base64("host:port:login:pass|date|country|flags")
```

#### Расшифровка:
- **k[0]:** `host:port:login:pass` - основная информация о прокси
- **k[1]:** `date` - дата окончания действия (формат: YYYY-MM-DD)
- **k[2]:** `country` - код страны (например: 'ru', 'us', 'nl')
- **k[3]:** `flags` - дополнительные флаги (например: 'rmd' для случайного выбора)

#### Пример декодирования:
```javascript
let k = atob(base64String).split("|");
// k[0] = "host:port:login:pass"
// k[1] = "2025-12-31" (дата окончания)
// k[2] = "ru" (код страны)
// k[3] = "rmd" (флаг случайного выбора, опционально)
```

### Обработка:
- Прокси с странами из `bancountries` исключаются
- Прокси с флагом `|rmd` могут быть выбраны случайным образом
- Динамические прокси добавляются в начало списка `serverConfigs`

---

## 3. VIP прокси-серверы

**Хранение:** Chrome Storage (`chrome.storage.local`)  
**Ключ:** `vipserver`  
**Формат:** JSON объект

### Структура VIP прокси:

```json
{
    "host": "example.com",
    "port": "443",
    "user": "username",
    "pass": "password",
    "date_end": "2025-12-31 23:59:59",
    "country": "us"
}
```

### Поля:
- **host** - адрес прокси-сервера
- **port** - порт прокси-сервера
- **user** - имя пользователя
- **pass** - пароль
- **date_end** - дата и время окончания действия
- **country** - код страны (опционально)

### Особенности:
- VIP прокси имеют приоритет над обычными
- Проверяется срок действия (`date_end`)
- При истечении срока автоматически переключается на обычный прокси
- Может быть активирован через VIP код (base64 строка)

### Формат VIP кода:
```
base64("host:port:user:pass|date_end|country")
```

---

## 4. PAC Script (Proxy Auto-Configuration)

**Файл:** `js/conf.js`  
**Переменная:** `pacscript`

### Домены, использующие прокси:

1. **OpenAI:**
   - openai.com
   - chatgpt.com
   - snc.apps.openai.com
   - oaistatic.com
   - oaiusercontent.com

2. **Google:**
   - apis.google.com
   - googleapis.com
   - googleusercontent.com
   - gstatic.com

3. **Microsoft:**
   - live.com
   - live.net
   - microsoft.com
   - onedrive.com
   - sharepoint.com
   - webpubsub.azure.com
   - blob.core.windows.net

4. **Другие сервисы:**
   - stripe.com
   - cloudflare.com
   - facebook.net
   - mapbox.com
   - reddit.com
   - redditstatic.com
   - atlassian.com
   - datadoghq.com
   - statsigapi.net
   - featuregates.org
   - livekit.io
   - browser-intake-datadoghq.com
   - vimeo.com
   - youtube.com

### Логика PAC Script:
- Если домен совпадает с одним из указанных - используется прокси
- Иначе - прямое соединение (DIRECT)
- Для порта 443 используется HTTPS прокси, иначе PROXY

---

## 5. Механизм работы прокси

### Установка прокси:
**Файл:** `js/bg.js`  
**Функция:** `setProxy(proxy)`

1. Если прокси имеет поле `full` - используется полный PAC скрипт
2. Иначе используется шаблон `pacscript` с подстановкой `{{host}}` и `{{port}}`
3. Для порта 443 заменяется `PROXY` на `HTTPS`
4. Устанавливается через `chrome.proxy.settings.set()`

### Получение данных прокси:
**Файл:** `js/bg.js`  
**Функция:** `getProxyData()`

1. Если `proxyid === 'vip'` - загружается VIP прокси из storage
2. Иначе:
   - Загружаются динамические прокси из storage (`servers`)
   - Декодируются base64 строки
   - Фильтруются по `bancountries`
   - Объединяются с `serverConfigs`
   - Выбирается прокси по индексу `proxyid - 1`

### Аутентификация:
**Файл:** `js/bg.js`  
**Функция:** `authHandler(details)`

- Используется `chrome.webRequest.onAuthRequired`
- Автоматически подставляются логин и пароль из `proxyData`
- Максимум 10 попыток аутентификации

---

## 6. Источники прокси

### API Endpoint:
- **Базовый URL:** `https://api.hhos.ru` (может быть переопределен через `apiurl` в storage)
- **Версия API:** `v2.0`
- **Тип:** `vpnchatgpt2`

### Внешние источники:
1. **Telegram:** `https://t.me/liservers/15`
2. **Telegraph:** `https://telegra.ph/Servers-10-16-15`

### Формат данных из внешних источников:
Данные зашифрованы сдвигом Цезаря (shift=3) и содержат JSON:
```json
{
    "u": "api.hhos.ru",
    "s": [
        "base64_encoded_proxy1",
        "base64_encoded_proxy2",
        ...
    ]
}
```

---

## 7. Страны прокси

**Файл:** `js/conf.js`  
**Переменная:** `countrys`

Поддерживаемые страны (код -> название):
- au - Австралия
- ca - Канада
- de - Германия
- fr - Франция
- gb - Великобритания
- jp - Япония
- nl - Нидерланды
- ru - Россия
- sg - Сингапур
- us - США
- и другие (см. файл `js/conf.js`, строки 91-153)

### Заблокированные страны:
**Переменная:** `bancountries`  
**Текущее значение:** `[]` (пустой массив)

---

## 8. Файлы, связанные с прокси

### Основные файлы:
- `js/conf.js` - конфигурация, жестко заданные прокси, PAC script
- `js/bg.js` - логика работы с прокси, установка, получение данных
- `popup/main.js` - UI для управления прокси, загрузка динамических прокси

### Дополнительные файлы:
- `manifest.json` - разрешения для работы с прокси (`"proxy"`, `"webRequest"`, `"webRequestAuthProvider"`)
- `popup/main.html` - интерфейс выбора прокси
- `settings/main.js` - настройки расширения

---

## 9. Статистика

- **Жестко заданных прокси:** 4
- **Динамических прокси:** переменное количество (загружаются извне)
- **VIP прокси:** 0-1 (зависит от наличия подписки)
- **Всего доменов в PAC:** 30

---

## 10. Примечания

1. Динамические прокси имеют приоритет над жестко заданными (добавляются в начало списка)
2. VIP прокси имеют наивысший приоритет
3. Прокси с портом 443 автоматически используют HTTPS протокол
4. Данные прокси могут быть зашифрованы и требуют декодирования
5. Система поддерживает автоматическое переключение при ошибках прокси
6. Прокси применяются только к указанным доменам через PAC script

---

*Документ создан на основе анализа кода проекта VPN для ChatGPT v4.5*

