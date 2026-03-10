#!/bin/bash
set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Установка XRay + VLESS Reality + VPN Bot ===${NC}"

# Проверка root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Запустите от root: sudo bash install_xray.sh${NC}"
    exit 1
fi

# Получаем IP сервера
SERVER_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "YOUR_SERVER_IP")
echo -e "${YELLOW}IP сервера: $SERVER_IP${NC}"

# Установка зависимостей
echo -e "${YELLOW}Установка зависимостей...${NC}"
apt update
apt install -y curl wget unzip jq uuid-runtime openssl iptables-persistent sqlite3

# Очистка старых VPN (если есть)
echo -e "${YELLOW}Очистка старых VPN...${NC}"
systemctl stop wg-quick@wg0 2>/dev/null || true
systemctl stop amneziawg-go@wg0 2>/dev/null || true
docker stop $(docker ps -aq) 2>/dev/null || true
docker rm $(docker ps -aq) 2>/dev/null || true
iptables -F
iptables -t nat -F
iptables -t mangle -F

# Установка XRay
echo -e "${YELLOW}Установка XRay...${NC}"
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# Генерация ключей
echo -e "${YELLOW}Генерация ключей Reality...${NC}"
ADMIN_UUID=$(xray uuid)
KEYS=$(xray x25519)
PRIVATE_KEY=$(echo "$KEYS" | grep "Private key" | awk '{print $3}')
PUBLIC_KEY=$(echo "$KEYS" | grep "Public key" | awk '{print $3}')
SHORT_ID=$(openssl rand -hex 8)
DEST="www.google.com:443"

# Создание директорий
mkdir -p /usr/local/etc/xray
mkdir -p /var/log/xray
mkdir -p /opt/vpn-bot/data
touch /var/log/xray/access.log /var/log/xray/error.log
chown -R nobody:nogroup /var/log/xray

# Сохранение ключей
cat > /usr/local/etc/xray/keys.env << EOF
SERVER_IP=$SERVER_IP
ADMIN_UUID=$ADMIN_UUID
PRIVATE_KEY=$PRIVATE_KEY
PUBLIC_KEY=$PUBLIC_KEY
SHORT_ID=$SHORT_ID
DEST=$DEST
EOF

# Создание конфига XRay
echo -e "${YELLOW}Создание конфигурации XRay...${NC}"
cat > /usr/local/etc/xray/config.json << EOF
{
  "log": {
    "loglevel": "warning",
    "access": "/var/log/xray/access.log",
    "error": "/var/log/xray/error.log"
  },
  "api": {
    "tag": "api",
    "services": ["HandlerService", "LoggerService", "StatsService"],
    "listen": "127.0.0.1",
    "port": 10085
  },
  "policy": {
    "levels": {
      "0": {
        "statsUserUplink": true,
        "statsUserDownlink": true
      }
    },
    "system": {
      "statsInboundUplink": true,
      "statsInboundDownlink": true
    }
  },
  "inbounds": [
    {
      "tag": "vless-reality",
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "$DEST",
          "xver": 0,
          "serverNames": ["www.google.com", "www.youtube.com", "www.cloudflare.com"],
          "privateKey": "$PRIVATE_KEY",
          "shortIds": ["", "$SHORT_ID"]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls"]
      }
    },
    {
      "tag": "api",
      "listen": "127.0.0.1",
      "port": 10085,
      "protocol": "dokodemo-door",
      "settings": {
        "address": "127.0.0.1"
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "direct"
    },
    {
      "protocol": "blackhole",
      "tag": "blocked"
    }
  ],
  "routing": {
    "rules": [
      {
        "type": "field",
        "inboundTag": ["api"],
        "outboundTag": "api"
      }
    ]
  },
  "stats": {}
}
EOF

# Добавление админского клиента
cat > /tmp/admin_client.json << EOF
{
  "id": "$ADMIN_UUID",
  "flow": "xtls-rprx-vision",
  "email": "admin@server.com",
  "level": 0
}
EOF

# Запуск XRay
echo -e "${YELLOW}Запуск XRay...${NC}"
systemctl daemon-reload
systemctl enable xray
systemctl start xray
sleep 2

# Проверка статуса
if systemctl is-active --quiet xray; then
    echo -e "${GREEN}✅ XRay запущен успешно!${NC}"
else
    echo -e "${RED}❌ Ошибка запуска XRay${NC}"
    systemctl status xray --no-pager
    exit 1
fi

# Настройка firewall (БЕЗОПАСНО для SSH)
echo -e "${YELLOW}Настройка firewall...${NC}"

# Сначала разрешаем SSH, чтобы не потерять доступ!
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 443/tcp comment 'XRay VLESS'
ufw --force enable

echo -e "${GREEN}✅ Firewall настроен (SSH и 443 открыты)${NC}"

# Создание базы данных бота
echo -e "${YELLOW}Создание базы данных...${NC}"
sqlite3 /opt/vpn-bot/data/bot.db << 'EOSQL'
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    email TEXT UNIQUE,
    uuid TEXT UNIQUE,
    device_type TEXT,
    flow TEXT,
    expires_at TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    amount REAL,
    currency TEXT,
    period_months INTEGER,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT,
    target_user INTEGER,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
EOSQL

# Сохранение админского конфига
mkdir -p /opt/vpn-bot/configs
cat > /opt/vpn-bot/configs/admin.txt << EOF
=== АДМИНСКИЙ КОНФИГ ===
Email: admin@server.com
UUID: $ADMIN_UUID

VLESS ссылка:
vless://${ADMIN_UUID}@${SERVER_IP}:443?security=reality&flow=xtls-rprx-vision&type=tcp&sni=www.google.com&fp=chrome&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}#Admin

Public Key: $PUBLIC_KEY
Short ID: $SHORT_ID
EOF

# Установка бота
echo -e "${YELLOW}Установка VPN бота...${NC}"
REPO_URL="https://github.com/Bambale0/vlessbot.git"

# Проверяем, установлен ли git
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Установка git...${NC}"
    apt install -y git
fi

# Клонируем репозиторий
if [ -d "/opt/vpn-bot" ]; then
    echo -e "${YELLOW}Обновление бота...${NC}"
    cd /opt/vpn-bot
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    echo -e "${YELLOW}Клонирование репозитория...${NC}"
    git clone $REPO_URL /opt/vpn-bot
fi

# Установка Python зависимостей
echo -e "${YELLOW}Установка Python зависимостей...${NC}"
cd /opt/vpn-bot
pip3 install -r requirements.txt

# Создание .env из примера
if [ ! -f "/opt/vpn-bot/.env" ]; then
    cp /opt/vpn-bot/.env.example /opt/vpn-bot/.env
fi

# Сообщение о настройке
echo -e ""
echo -e "${GREEN}=== Установка бота завершена! ===${NC}"
echo -e ""
echo -e "${YELLOW}НАСТРОЙКА:${NC}"
echo -e "1. Отредактируйте .env файл:"
echo -e "   nano /opt/vpn-bot/.env"
echo -e "   Добавьте: BOT_TOKEN, ADMIN_IDS"
echo -e ""
echo -e "2. Для включения YooKassa добавьте:"
echo -e "   PAYMENT_PROVIDER=yookassa"
echo -e "   YOOKASSA_SHOP_ID=ваш_id"
echo -e "   YOOKASSA_SECRET_KEY=ваш_ключ"
echo -e ""
echo -e "3. Запуск бота:"
echo -e "   cd /opt/vpn-bot && python3 -m bot.main"
echo -e ""
echo -e "Для автозапуска бота добавьте в crontab:"
echo -e "   @reboot cd /opt/vpn-bot && python3 -m bot.main"
