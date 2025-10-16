#!/bin/bash

echo "🔍 Проверка WARP портов..."

echo "1️⃣ Статус WARP:"
warp-cli status

echo ""
echo "2️⃣ Проверка портов 40000-40004:"
for port in 40000 40001 40002 40003 40004; do
    echo -n "Порт $port: "
    if netstat -tlnp | grep ":$port " > /dev/null 2>&1; then
        echo "✅ Слушается"
    else
        echo "❌ Не слушается"
    fi
done

echo ""
echo "3️⃣ Все слушающие порты:"
netstat -tlnp | grep "127.0.0.1"

echo ""
echo "4️⃣ Тест подключения к порту 40000:"
timeout 5 curl --socks5 127.0.0.1:40000 https://httpbin.org/ip 2>/dev/null || echo "❌ Не удалось подключиться"
