#!/bin/bash

# Находим и останавливаем бота
PID=$(pgrep -f "python3 -m bot.main")

if [ -z "$PID" ]; then
    echo "Бот не запущен!"
    exit 1
fi

# Останавливаем процесс
kill $PID

echo "Бот остановлен (PID: $PID)"
