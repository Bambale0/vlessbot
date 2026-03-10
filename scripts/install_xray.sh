#!/bin/bash
set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Установка XRay + VLESS Reality ===${NC}"

# Проверка root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Запустите от root: sudo bash install_xray.sh${NC}"
    exit 1
fi

# БЕЗОПАСНОСТЬ: проверяем что не через SSH запущено без tmux/screen
if [ -n "$SSH_CLIENT" ] && [ -z "$TMUX" ] && [ -z "$STY" ]; then
    echo -e "${YELLOW}⚠️ Запущено через SSH без tmux/screen${NC}"
    echo -e "${YELLOW}Если соединение оборвётся, установка прервётся${NC}"
    echo -e "Нажми Ctrl+C и запусти: ${GREEN}tmux new-session 'bash install_xray.sh'${NC}"
    sleep 5
fi

# Получаем IP сервера
SERVER_IP=$(curl -s --max-time 10 ifconfig.me || curl -s --max-time 10 icanhazip.com || hostname -I | awk '{print $1}')
echo -e "${YELLOW}IP сервера: $SERVER_IP${NC}"

# Проверка доступности SSH перед любыми манипуляциями
echo -e "${YELLOW}Проверка SSH...${NC}"
if ! systemctl is-active --quiet sshd; then
    echo -e "${RED}SSH не запущен! Не продолжаем.${NC}"
    exit 1
fi

# Установка зависимостей
echo -e "${YELLOW}Установка зависимостей...${NC}"
apt-get update
apt-get install -y curl wget unzip jq uuid-runtime openssl sqlite3

# Очистка старых VPN (осторожно, без iptables -F)
echo -e "${YELLOW}Очистка старых VPN...${NC}"
systemctl stop wg-quick@wg0 2>/dev/null || true
systemctl stop amneziawg-go@wg0 2>/dev/null || true
docker stop $(docker ps -aq) 2>/dev/null || true
docker rm $(docker ps -aq) 2>/dev/null || true

# НЕ ДЕЛАЕМ iptables -F! Только специфичные правила
# iptables -F  # ← ОПАСНО!

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

# === БЕЗОПАСНАЯ настройка firewall ===
echo -e "${YELLOW}Настройка firewall (безопасно)...${NC}"

# Проверяем что SSH работает перед изменениями
SSH_OK=false
if systemctl is-active --quiet sshd && ss -tulnp | grep -q ':22'; then
    SSH_OK=true
fi

if [ "$SSH_OK" = false ]; then
    echo -e "${RED}SSH не отвечает, пропускаем настройку firewall!${NC}"
    echo -e "${YELLOW}Настройте вручную после проверки SSH${NC}"
else
    # UFW — безопаснее чем голый iptables
    ufw --force reset 2>/dev/null || true
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment 'SSH'
    ufw allow 443/tcp comment 'XRay VLESS'
    
    # Включаем с таймаутом на случай проблем
    echo -e "${YELLOW}Включение UFW через 10 сек (Ctrl+C для отмены)...${NC}"
    sleep 10
    ufw --force enable
    
    # Проверяем что SSH всё ещё работает
    sleep 2
    if systemctl is-active --quiet sshd; then
        echo -e "${GREEN}✅ Firewall настроен, SSH работает${NC}"
    else
        echo -e "${RED}❌ SSH упал после firewall! Откатываем...${NC}"
        ufw --force disable
        systemctl restart sshd
    fi
fi

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

echo -e "${GREEN}=== Установка завершена! ===${NC}"
echo -e "${YELLOW}Админский конфиг сохранен в: /opt/vpn-bot/configs/admin.txt${NC}"
echo -e "${YELLOW}Ключи сервера: /usr/local/etc/xray/keys.env${NC}"
echo -e ""
echo -e "${GREEN}Для установки бота:${NC}"
echo -e "1. git clone <repo> /opt/vpn-bot"
echo -e "2. cd /opt/vpn-bot && pip install -r requirements.txt"
echo -e "3. nano .env # добавь BOT_TOKEN"
echo -e "4. python -m bot.main"