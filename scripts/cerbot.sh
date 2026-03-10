#!/bin/bash

# Скрипт для получения SSL сертификатов Let's Encrypt
# Использование: bash scripts/get_ssl.sh your_domain.com

DOMAIN=$1

if [ -z "$DOMAIN" ]; then
    echo "Usage: bash scripts/get_ssl.sh your_domain.com"
    echo "Example: bash scripts/get_ssl.sh vpn.example.com"
    exit 1
fi

echo "=== Получение SSL сертификата для $DOMAIN ==="

# Проверка что запущен от root
if [ "$EUID" -ne 0 ]; then
    echo "Запустите от root: sudo bash scripts/get_ssl.sh $DOMAIN"
    exit 1
fi

# Установка certbot если нет
if ! command -v certbot &> /dev/null; then
    echo "Установка certbot..."
    apt-get update
    apt-get install -y certbot
fi

# Остановка XRay на время получения сертификата (освобождает порт 443)
echo "Остановка XRay..."
systemctl stop xray 2>/dev/null || pkill xray

# Получение сертификата
echo "Получение сертификата..."
certbot certonly --standalone -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN

if [ $? -eq 0 ]; then
    echo "✅ Сертификат получен!"
    
    # Копирование сертификатов
    mkdir -p /home/dev/vlessbot/ssl
    cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /home/dev/vlessbot/ssl/cert.pem
    cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /home/dev/vlessbot/ssl/key.pem
    cp /etc/letsencrypt/live/$DOMAIN/chain.pem /home/dev/vlessbot/ssl/chain.pem
    
    echo "Сертификаты скопированы в /home/dev/vlessbot/ssl/"
    echo ""
    echo "Для автоматического обновления добавьте в cron:"
    echo "0 0 * * * root certbot renew --quiet && cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /home/dev/vlessbot/ssl/cert.pem && cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /home/dev/vlessbot/ssl/key.pem && systemctl restart your-bot-service"
else
    echo "❌ Ошибка получения сертификата"
    exit 1
fi
