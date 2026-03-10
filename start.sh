#!/bin/bash

# Переходим в директорию проекта
cd /home/dev/vlessbot

# Проверяем, запущен ли уже бот
if pgrep -f "python3 -m bot.main" > /dev/null; then
    echo "Бот уже запущен!"
    exit 1
fi

# Запускаем бота в фоновом режиме
nohup python3 -m bot.main > bot.log 2>&1 &

echo "Бот запущен (PID: $!)"
echo "Логи: bot.log"
