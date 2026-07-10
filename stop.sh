#!/bin/bash

# Находим и останавливаем бота
PID=$(pgrep -f "python3 -m bot.main")

if [ -z "$PID" ]; then
    echo "Бот не запущен!"
    exit 0
fi

# Останавливаем процесс
kill -9 $PID

echo "Бот остановлен (PID: $PID)"
