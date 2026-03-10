#!/bin/bash

# Скрипт для создания самоподписанного SSL сертификата
# Использование: bash scripts/generate_selfsigned_ssl.sh your_domain.com

DOMAIN=${1:-localhost}

echo "=== Создание самоподписанного SSL сертификата для $DOMAIN ==="

# Создание директории для сертификатов
mkdir -p ssl

# Генерация сертификата
openssl req -x509 -newkey rsa:4096 \
    -keyout ssl/key.pem \
    -out ssl/cert.pem \
    -days 365 -nodes \
    -subj "/CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN,DNS:www.$DOMAIN,IP:0.0.0.0"

if [ $? -eq 0 ]; then
    echo "✅ Самоподписанный сертификат создан!"
    echo ""
    echo "Файлы:"
    echo "  - ssl/cert.pem (публичный сертификат)"
    echo "  - ssl/key.pem (приватный ключ)"
    echo ""
    echo "⚠️  Для использования с YooKassa:"
    echo "   - Вам нужен реальный домен"
    echo "   - Используйте Let's Encrypt: sudo bash scripts/get_ssl.sh your_domain.com"
else
    echo "❌ Ошибка создания сертификата"
    exit 1
fi
