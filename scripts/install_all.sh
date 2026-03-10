#!/bin/bash
set -e

# ============================================
# Полная установка VPN бота с нуля
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Установка VPN Bot + XRay ===${NC}"

# Проверка root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Запустите от root: sudo bash install_all.sh${NC}"
    exit 1
fi

# Безопасность - проверка SSH
if [ -n "$SSH_CLIENT" ] && [ -z "$TMUX" ] && [ -z "$STY" ]; then
    echo -e "${YELLOW}⚠️ Запущено через SSH без tmux/screen${NC}"
    echo -e "${YELLOW}Если соединение оборвётся, установка прервётся${NC}"
    echo -e "Нажми Ctrl+C и запусти: ${GREEN}tmux new-session 'bash install_all.sh'${NC}"
    sleep 5
fi

# === 1. Обновление системы ===
echo -e "${YELLOW}[1/8] Обновление системы...${NC}"
apt-get update
apt-get upgrade -y

# === 2. Установка зависимостей ===
echo -e "${YELLOW}[2/8] Установка зависимостей...${NC}"
apt-get install -y curl wget unzip jq uuid-runtime openssl sqlite3 python3 python3-pip git

# === 3. Остановка старых VPN ===
echo -e "${YELLOW}[3/8] Очистка старых VPN...${NC}"
systemctl stop wg-quick@wg0 2>/dev/null || true
systemctl stop amneziawg-go@wg0 2>/dev/null || true
systemctl stop nginx 2>/dev/null || true
docker stop $(docker ps -aq) 2>/dev/null || true
docker rm $(docker ps -aq) 2>/dev/null || true

# === 4. Установка XRay ===
echo -e "${YELLOW}[4/8] Установка XRay...${NC}"
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# === 5. Генерация ключей ===
echo -e "${YELLOW}[5/8] Генерация ключей...${NC}"

# Получаем IP
SERVER_IP=$(curl -s --max-time 10 ifconfig.me || curl -s --max-time 10 icanhazip.com || hostname -I | awk '{print $1}')
echo -e "${GREEN}IP сервера: $SERVER_IP${NC}"

# Генерация X25519 ключей
KEYS=$(xray x25519)
PRIVATE_KEY=$(echo "$KEYS" | grep "PrivateKey:" | awk -F': ' '{print $2}')
PUBLIC_KEY=""

# Вычисляем PUBLIC_KEY из PRIVATE_KEY
python3 << PYEOF
import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization

private_key = "$PRIVATE_KEY"
private_bytes = base64.urlsafe_b64decode(private_key + "==")
private_key_obj = X25519PrivateKey.from_private_bytes(private_bytes)
public_key_obj = private_key_obj.public_key()
public_bytes = public_key_obj.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw
)
public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b'=').decode()
print(public_key)
PYEOF

PUBLIC_KEY=$(python3 << PYEOF
import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization

private_key = "$PRIVATE_KEY"
private_bytes = base64.urlsafe_b64decode(private_key + "==")
private_key_obj = X25519PrivateKey.from_private_bytes(private_bytes)
public_key_obj = private_key_obj.public_key()
public_bytes = public_key_obj.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw
)
public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b'=').decode()
print(public_key)
PYEOF
)

# ADMIN_UUID
ADMIN_UUID=$(xray uuid)
SHORT_ID=$(openssl rand -hex 8)
DEST="www.google.com:443"

# === 6. Создание конфигов ===
echo -e "${YELLOW}[6/8] Создание конфигов...${NC}"

# Директории
mkdir -p /usr/local/etc/xray
mkdir -p /var/log/xray
mkdir -p /opt/vpn-bot/data
mkdir -p /opt/vpn-bot/configs

touch /var/log/xray/access.log /var/log/xray/error.log
chown -R nobody:nogroup /var/log/xray

# keys.env
cat > /usr/local/etc/xray/keys.env << EOF
SERVER_IP=$SERVER_IP
ADMIN_UUID=$ADMIN_UUID
PRIVATE_KEY=$PRIVATE_KEY
PUBLIC_KEY=$PUBLIC_KEY
SHORT_ID=$SHORT_ID
DEST=$DEST
EOF

# XRay config.json
cat > /usr/local/etc/xray/config.json << EOF
{
  "log": {
    "loglevel": "warning",
    "access": "/var/log/xray/access.log",
    "error": "/var/log/xray/error.log"
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
  ]
}
EOF

# === 7. Запуск XRay ===
echo -e "${YELLOW}[7/8] Запуск XRay...${NC}"
systemctl daemon-reload
systemctl enable xray
systemctl start xray
sleep 2

if systemctl is-active --quiet xray; then
    echo -e "${GREEN}✅ XRay запущен!${NC}"
else
    echo -e "${RED}❌ Ошибка запуска XRay${NC}"
    systemctl status xray --no-pager
    exit 1
fi

# === 8. Настройка firewall ===
echo -e "${YELLOW}[8/8] Настройка firewall...${NC}"

# Проверка SSH
if ! ss -tulnp | grep -q ':22'; then
    echo -e "${RED}SSH не работает! Пропускаем firewall${NC}"
else
    ufw --force reset 2>/dev/null || true
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment 'SSH'
    ufw allow 443/tcp comment 'XRay VLESS'
    
    echo -e "${YELLOW}Включение UFW через 10 сек (Ctrl+C для отмены)...${NC}"
    sleep 10
    ufw --force enable
    echo -e "${GREEN}✅ Firewall настроен${NC}"
fi

# === 9. Клонирование бота ===
echo -e "${YELLOW}[9] Установка бота...${NC}"
cd /opt
rm -rf vpn-bot 2>/dev/null || true
git clone https://github.com/Bambale0/vlessbot.git vpn-bot
cd vpn-bot

# Python venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Копирование ключей
cp /usr/local/etc/xray/keys.env /opt/vpn-bot/keys.env

# Создание .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}⚠️ Отредактируйте .env файл!${NC}"
    echo "Добавьте BOT_TOKEN и другие настройки"
fi

# База данных
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

# === Итог ===
echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  УСТАНОВКА ЗАВЕРШЕНА!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "${YELLOW}Следующие шаги:${NC}"
echo "1. Отредактируйте /opt/vpn-bot/.env"
echo "   - Добавьте BOT_TOKEN"
echo "   - Настройте ADMIN_IDS"
echo ""
echo "2. Запустите бота:"
echo "   cd /opt/vpn-bot"
echo "   source venv/bin/activate"
echo "   python -m bot.main"
echo ""
echo -e "${GREEN}Админская ссылка:${NC}"
echo "vless://${ADMIN_UUID}@${SERVER_IP}:443?security=reality&flow=xtls-rprx-vision&type=tcp&sni=www.google.com&fp=chrome&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}#Admin"
echo ""
