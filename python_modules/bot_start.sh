#!/bin/bash

# === Папка проекта ===
PROJECT_DIR="/home/admin/web/233204.fornex.cloud/public_html"
BOT_FILE="python_modules/bz_telebot/main.py"
LOG_FILE="$PROJECT_DIR/storage/app/public/output/logs-telebot/telebot.log"

# === Убиваем все процессы, связанные с ботом ===
echo "🔪 Убиваем процессы bz_telebot.py..."
ps aux | grep "$BOT_FILE" | grep python | awk '{print $2}' | xargs -r kill -9

# === Подождем для надежности ===
sleep 1

# === Запускаем бота в фоне ===
echo "🚀 Запуск бота в фоне..."
cd "$PROJECT_DIR" || exit
nohup python3 "$BOT_FILE" > "$LOG_FILE" 2>&1 &

echo "✅ Бот перезапущен. Лог: $LOG_FILE"
