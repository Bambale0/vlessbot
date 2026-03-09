реализация VPN бота с XRay/VLESS и автоматическим деплоем.
Структура проекта
plain
Copy
vpn-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── keyboards.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── admin.py
│   │   └── payment.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── xray_manager.py
│   │   ├── database.py
│   │   └── payment_service.py
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── scripts/
│   └── install_xray.sh
├── data/
│   └── prices.json
├── .env.example
├── requirements.txt
└── README.md
1. Bash скрипт установки XRay
Файл: scripts/install_xray.sh
bash
Copy
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

# Настройка firewall
echo -e "${YELLOW}Настройка firewall...${NC}"
ufw allow 22/tcp
ufw allow 443/tcp
ufw --force enable

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
2. Конфигурация бота
Файл: .env.example
env
Copy
# Telegram Bot
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321  # ID админов через запятую

# Server
SERVER_IP=your_server_ip
XRAY_CONFIG_PATH=/usr/local/etc/xray/config.json
KEYS_PATH=/usr/local/etc/xray/keys.env
DB_PATH=/opt/vpn-bot/data/bot.db

# Payments (можно подключить ЮKassa, Crypto и т.д.)
PAYMENT_PROVIDER=manual  # manual, yookassa, crypto
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# Support
SUPPORT_USERNAME=@your_support_username
SUPPORT_LINK=https://t.me/your_support_username
Файл: data/prices.json
JSON
Copy
{
  "plans": {
    "1_month": {
      "name": "1 месяц",
      "period_months": 1,
      "price_rub": 299,
      "price_usd": 3.99,
      "devices": 3,
      "description": "3 устройства, полная скорость"
    },
    "6_months": {
      "name": "6 месяцев",
      "period_months": 6,
      "price_rub": 1499,
      "price_usd": 19.99,
      "devices": 5,
      "description": "5 устройств, выгода 15%",
      "badge": "🔥 Популярный"
    },
    "12_months": {
      "name": "12 месяцев",
      "period_months": 12,
      "price_rub": 2499,
      "price_usd": 32.99,
      "devices": 7,
      "description": "7 устройств, выгода 30%",
      "badge": "💰 Выгодный"
    }
  },
  "currency": "RUB"
}
3. Python код бота
Файл: requirements.txt
plain
Copy
aiogram==3.4.1
aiohttp==3.9.3
python-dotenv==1.0.0
qrcode==7.4.2
Pillow==10.2.0
pynacl==1.5.0
Файл: bot/config.py
Python
Copy
import os
import json
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = None
    SERVER_IP: str = os.getenv("SERVER_IP", "")
    XRAY_CONFIG_PATH: str = os.getenv("XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
    KEYS_PATH: str = os.getenv("KEYS_PATH", "/usr/local/etc/xray/keys.env")
    DB_PATH: str = os.getenv("DB_PATH", "/opt/vpn-bot/data/bot.db")
    SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "")
    SUPPORT_LINK: str = os.getenv("SUPPORT_LINK", "")
    
    def __post_init__(self):
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
        
        # Загрузка цен
        with open("data/prices.json", "r", encoding="utf-8") as f:
            self.PRICES = json.load(f)

cfg = Config()
Файл: bot/services/database.py
Python
Copy
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass

@dataclass
class User:
    telegram_id: int
    username: Optional[str]
    created_at: str
    is_active: bool

@dataclass
class Subscription:
    id: int
    telegram_id: int
    email: str
    uuid: str
    device_type: str
    flow: str
    expires_at: Optional[str]
    is_active: bool
    created_at: str

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
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
                    flow TEXT DEFAULT 'xtls-rprx-vision',
                    expires_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    period_months INTEGER,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS admin_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT,
                    target_user INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
    
    def get_or_create_user(self, telegram_id: int, username: Optional[str] = None) -> User:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT telegram_id, username, created_at, is_active FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return User(*row)
            
            cursor.execute(
                "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
                (telegram_id, username)
            )
            conn.commit()
            
            return User(telegram_id, username, datetime.now().isoformat(), True)
    
    def add_subscription(self, telegram_id: int, email: str, uuid: str, 
                       device_type: str, flow: str = "xtls-rprx-vision",
                       expires_at: Optional[datetime] = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            expires_str = expires_at.isoformat() if expires_at else None
            
            cursor.execute("""
                INSERT INTO subscriptions (telegram_id, email, uuid, device_type, flow, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (telegram_id, email, uuid, device_type, flow, expires_str))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_user_subscriptions(self, telegram_id: int, active_only: bool = True) -> List[Subscription]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, telegram_id, email, uuid, device_type, flow, expires_at, is_active, created_at
                FROM subscriptions WHERE telegram_id = ?
            """
            if active_only:
                query += " AND is_active = 1 AND (expires_at IS NULL OR expires_at > ?)"
                cursor.execute(query, (telegram_id, datetime.now().isoformat()))
            else:
                cursor.execute(query, (telegram_id,))
            
            rows = cursor.fetchall()
            return [Subscription(*row) for row in rows]
    
    def get_subscription_by_email(self, email: str) -> Optional[Subscription]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, telegram_id, email, uuid, device_type, flow, expires_at, is_active, created_at
                FROM subscriptions WHERE email = ?
            """, (email,))
            row = cursor.fetchone()
            return Subscription(*row) if row else None
    
    def deactivate_subscription(self, email: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE subscriptions SET is_active = 0 WHERE email = ?",
                (email,)
            )
            conn.commit()
    
    def extend_subscription(self, email: str, new_expires: datetime):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE subscriptions SET expires_at = ?, is_active = 1 WHERE email = ?",
                (new_expires.isoformat(), email)
            )
            conn.commit()
    
    def add_payment(self, telegram_id: int, amount: float, currency: str, 
                    period_months: int, status: str = "pending"):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO payments (telegram_id, amount, currency, period_months, status)
                VALUES (?, ?, ?, ?, ?)
            """, (telegram_id, amount, currency, period_months, status))
            conn.commit()
    
    def update_payment_status(self, payment_id: int, status: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE payments SET status = ? WHERE id = ?",
                (status, payment_id)
            )
            conn.commit()
    
    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1")
            active_subs = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM subscriptions 
                WHERE is_active = 1 AND expires_at > ?
            """, (datetime.now().isoformat(),))
            paid_subs = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT SUM(amount) FROM payments WHERE status = 'completed'
            """)
            total_revenue = cursor.fetchone()[0] or 0
            
            return {
                "total_users": total_users,
                "active_subscriptions": active_subs,
                "paid_subscriptions": paid_subs,
                "total_revenue": total_revenue
            }
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.telegram_id, u.username, u.created_at,
                       COUNT(s.id) as sub_count,
                       MAX(s.expires_at) as max_expiry
                FROM users u
                LEFT JOIN subscriptions s ON u.telegram_id = s.telegram_id AND s.is_active = 1
                GROUP BY u.telegram_id
                ORDER BY u.created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def log_admin_action(self, admin_id: int, action: str, target_user: Optional[int] = None, details: Optional[str] = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_actions (admin_id, action, target_user, details)
                VALUES (?, ?, ?, ?)
            """, (admin_id, action, target_user, details))
            conn.commit()
Файл: bot/services/xray_manager.py
Python
Copy
import json
import uuid
import subprocess
import os
from typing import Dict, Optional, List
from dataclasses import dataclass
import urllib.parse

@dataclass
class ClientConfig:
    uuid: str
    email: str
    link: str
    json_config: dict
    qr_data: str
    flow: str

class XRayManager:
    def __init__(self, config_path: str, keys_path: str):
        self.config_path = config_path
        self.keys = self._load_keys(keys_path)
    
    def _load_keys(self, keys_path: str) -> Dict:
        keys = {}
        if os.path.exists(keys_path):
            with open(keys_path, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        keys[key] = value
        return keys
    
    def _load_xray_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def _save_xray_config(self, config: dict):
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def _reload_xray(self):
        subprocess.run(["systemctl", "reload", "xray"], check=True)
    
    def _generate_uuid(self) -> str:
        return str(uuid.uuid4())
    
    def _create_vless_link(self, client_uuid: str, email: str, flow: str = "xtls-rprx-vision") -> str:
        params = {
            "security": "reality",
            "type": "tcp",
            "headerType": "none",
            "sni": "www.google.com",
            "fp": "chrome",
            "pbk": self.keys.get("PUBLIC_KEY", ""),
            "sid": self.keys.get("SHORT_ID", ""),
        }
        
        if flow:
            params["flow"] = flow
        
        query = urllib.parse.urlencode(params)
        return f"vless://{client_uuid}@{self.keys.get('SERVER_IP', 'localhost')}:443?{query}#{urllib.parse.quote(email)}"
    
    def _create_json_config(self, client_uuid: str, email: str, flow: str = "xtls-rprx-vision") -> dict:
        return {
            "v": "2",
            "ps": email,
            "add": self.keys.get("SERVER_IP", "localhost"),
            "port": "443",
            "id": client_uuid,
            "aid": "0",
            "scy": "none",
            "net": "tcp",
            "type": "none",
            "host": "",
            "path": "",
            "tls": "reality",
            "sni": "www.google.com",
            "fp": "chrome",
            "pbk": self.keys.get("PUBLIC_KEY", ""),
            "sid": self.keys.get("SHORT_ID", ""),
            "flow": flow
        }
    
    def create_client(self, telegram_id: int, device_type: str = "mobile", 
                     flow: str = "xtls-rprx-vision") -> ClientConfig:
        """Создание клиента с XTLS (для 1-3 устройств)"""
        client_uuid = self._generate_uuid()
        
        device_emojis = {
            "mobile": "📱",
            "desktop": "💻",
            "tablet": "📟",
            "tv": "📺"
        }
        emoji = device_emojis.get(device_type, "📱")
        email = f"{emoji}{telegram_id}_{device_type}_{uuid.uuid4().hex[:6]}"
        
        # Добавляем в XRay
        xray_config = self._load_xray_config()
        new_client = {
            "id": client_uuid,
            "flow": flow,
            "email": email,
            "level": 0
        }
        
        xray_config["inbounds"][0]["settings"]["clients"].append(new_client)
        self._save_xray_config(xray_config)
        self._reload_xray()
        
        # Создаем конфиги
        vless_link = self._create_vless_link(client_uuid, email, flow)
        json_config = self._create_json_config(client_uuid, email, flow)
        
        return ClientConfig(
            uuid=client_uuid,
            email=email,
            link=vless_link,
            json_config=json_config,
            qr_data=vless_link,
            flow=flow
        )
    
    def create_shared_client(self, telegram_id: int, device_type: str = "shared") -> ClientConfig:
        """Создание общего клиента без flow (для неограниченных устройств)"""
        client_uuid = self._generate_uuid()
        email = f"🔓{telegram_id}_shared_{uuid.uuid4().hex[:8]}"
        
        # Без flow для совместимости
        flow = ""
        
        # Добавляем в XRay
        xray_config = self._load_xray_config()
        new_client = {
            "id": client_uuid,
            "flow": flow,
            "email": email,
            "level": 0
        }
        
        xray_config["inbounds"][0]["settings"]["clients"].append(new_client)
        self._save_xray_config(xray_config)
        self._reload_xray()
        
        # Создаем конфиги
        vless_link = self._create_vless_link(client_uuid, email, flow)
        json_config = self._create_json_config(client_uuid, email, flow)
        
        return ClientConfig(
            uuid=client_uuid,
            email=email,
            link=vless_link,
            json_config=json_config,
            qr_data=vless_link,
            flow=flow
        )
    
    def remove_client(self, email: str) -> bool:
        """Удаление клиента из XRay"""
        try:
            xray_config = self._load_xray_config()
            clients = xray_config["inbounds"][0]["settings"]["clients"]
            original_len = len(clients)
            
            xray_config["inbounds"][0]["settings"]["clients"] = [
                c for c in clients if c.get("email") != email
            ]
            
            if len(xray_config["inbounds"][0]["settings"]["clients"]) < original_len:
                self._save_xray_config(xray_config)
                self._reload_xray()
                return True
            return False
        except Exception as e:
            print(f"Error removing client: {e}")
            return False
    
    def get_client_stats(self, email: str) -> Optional[Dict]:
        """Получение статистики по email"""
        try:
            result = subprocess.run(
                ["xray", "api", "statsquery", "--server=127.0.0.1:10085",
                 f"pattern=user>>>{email}>>>"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Парсим трафик
                uplink = 0
                downlink = 0
                
                for stat in data.get("stat", []):
                    name = stat.get("name", "")
                    value = stat.get("value", 0)
                    if "traffic>>>" in name and "uplink" in name:
                        uplink = value
                    elif "traffic>>>" in name and "downlink" in name:
                        downlink = value
                
                return {
                    "uplink_bytes": uplink,
                    "downlink_bytes": downlink,
                    "total_bytes": uplink + downlink
                }
            return None
        except Exception as e:
            print(f"Error getting stats: {e}")
            return None
    
    def get_all_clients(self) -> List[Dict]:
        """Получение всех клиентов из XRay"""
        xray_config = self._load_xray_config()
        return xray_config["inbounds"][0]["settings"]["clients"]
    
    def sync_with_db(self, active_emails: List[str]):
        """Синхронизация: удаление неактивных из XRay"""
        xray_config = self._load_xray_config()
        clients = xray_config["inbounds"][0]["settings"]["clients"]
        
        removed = []
        for client in clients[:]:
            if client.get("email") not in active_emails and not client.get("email", "").startswith("admin@"):
                clients.remove(client)
                removed.append(client.get("email"))
        
        if removed:
            self._save_xray_config(xray_config)
            self._reload_xray()
        
        return removed
Файл: bot/keyboards.py
Python
Copy
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Оплатить подписку")],
            [KeyboardButton(text="🔑 Получить конфиги"), KeyboardButton(text="❓ Помощь")],
            [KeyboardButton(text="📞 Техподдержка")]
        ],
        resize_keyboard=True
    )

def payment_plans(prices: dict):
    buttons = []
    for key, plan in prices["plans"].items():
        badge = plan.get("badge", "")
        text = f"{plan['name']} - {plan['price_rub']}₽ {badge}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"buy:{key}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def device_selection():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 Телефон", callback_data="device:mobile"),
            InlineKeyboardButton(text="💻 Компьютер", callback_data="device:desktop")
        ],
        [
            InlineKeyboardButton(text="📟 Планшет", callback_data="device:tablet"),
            InlineKeyboardButton(text="📺 ТВ", callback_data="device:tv")
        ],
        [
            InlineKeyboardButton(text="🔓 Общий (все устройства)", callback_data="device:shared")
        ]
    ])

def config_actions(email: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Копировать ссылку", callback_data=f"copy:{email}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{email}")
        ]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin:users")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin:search")],
        [InlineKeyboardButton(text="➕ Выдать подписку", callback_data="admin:give")],
        [InlineKeyboardButton(text="🔄 Синхронизировать XRay", callback_data="admin:sync")]
    ])

def admin_user_actions(telegram_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить подписку", callback_data=f"admin_give:{telegram_id}"),
            InlineKeyboardButton(text="📋 Его конфиги", callback_data=f"admin_configs:{telegram_id}")
        ],
        [
            InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin_block:{telegram_id}"),
            InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin_unblock:{telegram_id}")
        ]
    ])

def help_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 Android", callback_data="help:android"),
            InlineKeyboardButton(text="🍎 iOS", callback_data="help:ios")
        ],
        [
            InlineKeyboardButton(text="💻 Windows", callback_data="help:windows"),
            InlineKeyboardButton(text="🍏 macOS", callback_data="help:macos")
        ],
        [
            InlineKeyboardButton(text="🐧 Linux", callback_data="help:linux"),
            InlineKeyboardButton(text="📡 Роутер", callback_data="help:router")
        ],
        [
            InlineKeyboardButton(text="📞 Связаться с поддержкой", url="https://t.me/your_support")
        ]
    ])

def back_to_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back:menu")]
    ])
Файл: bot/utils/helpers.py
Python
Copy
import io
import qrcode
from PIL import Image
from datetime import datetime, timedelta

def generate_qr(data: str) -> io.BytesIO:
    """Генерация QR кода"""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def format_bytes(bytes_count: int) -> str:
    """Форматирование байтов в человекочитаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.2f} PB"

def calculate_expiry(period_months: int) -> datetime:
    """Расчет даты окончания подписки"""
    return datetime.now() + timedelta(days=30 * period_months)

def format_expiry(date_str: str) -> str:
    """Форматирование даты"""
    if not date_str:
        return "Бессрочно"
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d.%m.%Y")
    except:
        return date_str
Файл: bot/handlers/user.py
Python
Copy
import json
import io
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.config import cfg
from bot.keyboards import main_menu, payment_plans, device_selection, config_actions, help_menu, back_to_menu
from bot.services.database import Database
from bot.services.xray_manager import XRayManager
from bot.utils.helpers import generate_qr, calculate_expiry, format_expiry

router = Router()
db = Database(cfg.DB_PATH)
xray = XRayManager(cfg.XRAY_CONFIG_PATH, cfg.KEYS_PATH)

@router.message(Command("start"))
async def cmd_start(message: Message):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"👋 Привет! Я бот для управления VPN.\n\n"
        f"🔒 Безопасное соединение с маскировкой под обычный HTTPS\n"
        f"⚡ Высокая скорость на всех устройствах\n"
        f"🌍 Доступ к любым сайтам\n\n"
        f"Выберите действие:",
        reply_markup=main_menu()
    )

@router.message(F.text == "💳 Оплатить подписку")
async def btn_payment(message: Message):
    await message.answer(
        "📋 Выберите тариф:",
        reply_markup=payment_plans(cfg.PRICES)
    )

@router.callback_query(F.data.startswith("buy:"))
async def process_buy(callback: CallbackQuery):
    plan_key = callback.data.split(":")[1]
    plan = cfg.PRICES["plans"].get(plan_key)
    
    if not plan:
        await callback.answer("Тариф не найден")
        return
    
    text = (
        f"📦 <b>{plan['name']}</b> {plan.get('badge', '')}\n\n"
        f"💰 Цена: <b>{plan['price_rub']} ₽</b>\n"
        f"⏱ Период: {plan['period_months']} мес.\n"
        f"📱 Устройств: до {plan['devices']}\n"
        f"📝 {plan['description']}\n\n"
        f"Для оплаты свяжитесь с поддержкой или используйте /pay"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_menu()
    )

@router.message(F.text == "🔑 Получить конфиги")
async def btn_configs(message: Message):
    subs = db.get_user_subscriptions(message.from_user.id)
    
    if not subs:
        await message.answer(
            "❌ У вас нет активных конфигураций.\n\n"
            "Сначала оплатите подписку или выберите устройство для создания конфига:",
            reply_markup=device_selection()
        )
        return
    
    text = "📱 <b>Ваши конфигурации:</b>\n\n"
    for sub in subs:
        expiry = format_expiry(sub.expires_at)
        flow_type = "🔓 Общий" if not sub.flow else "⚡ XTLS"
        text += (
            f"<b>{sub.email}</b>\n"
            f"Тип: {flow_type}\n"
            f"Действует до: {expiry}\n"
            f"<code>{sub.uuid}</code>\n\n"
        )
    
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())

@router.callback_query(F.data.startswith("device:"))
async def process_device(callback: CallbackQuery):
    device_type = callback.data.split(":")[1]
    
    await callback.message.edit_text("⏳ Создаю конфигурацию...")
    
    try:
        if device_type == "shared":
            # Общий конфиг без flow
            config = xray.create_shared_client(callback.from_user.id, device_type)
            flow = ""
        else:
            # Индивидуальный конфиг с XTLS
            config = xray.create_client(callback.from_user.id, device_type, "xtls-rprx-vision")
            flow = "xtls-rprx-vision"
        
        # Сохраняем в БД (без срока, пока не оплачено)
        db.add_subscription(
            telegram_id=callback.from_user.id,
            email=config.email,
            uuid=config.uuid,
            device_type=device_type,
            flow=flow,
            expires_at=None  # Бессрочно до оплаты или тестовый период
        )
        
        # Формируем сообщение
        text = (
            f"✅ <b>Конфигурация создана!</b>\n\n"
            f"📧 <b>Email:</b> <code>{config.email}</code>\n"
            f"🆔 <b>UUID:</b> <code>{config.uuid}</code>\n\n"
        )
        
        if device_type == "shared":
            text += (
                f"🔓 <b>Общий доступ</b> — работает на всех устройствах\n"
                f"⚠️ Без XTLS ускорения, но максимальная совместимость\n\n"
            )
        else:
            text += (
                f"⚡ <b>XTLS Vision</b> — максимальная скорость\n"
                f"📱 Оптимизировано для {device_type}\n\n"
            )
        
        text += (
            f"<b>Ссылка для импорта:</b>\n"
            f"<code>{config.link}</code>\n\n"
            f"<i>Нажмите на ссылку чтобы скопировать</i>"
        )
        
        await callback.message.delete()
        
        # Отправляем QR
        qr_buf = generate_qr(config.link)
        await callback.message.answer_photo(
            BufferedInputFile(qr_buf.read(), filename="qr.png"),
            caption=text,
            parse_mode="HTML"
        )
        
        # Отправляем JSON файл
        json_bytes = json.dumps(config.json_config, indent=2).encode()
        await callback.message.answer_document(
            BufferedInputFile(json_bytes, filename=f"{config.email}.json"),
            caption="📄 JSON конфиг для Nekoray/v2rayN",
            reply_markup=main_menu()
        )
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")

@router.message(F.text == "❓ Помощь")
async def btn_help(message: Message):
    await message.answer(
        "📚 <b>Инструкции по настройке</b>\n\n"
        "Выберите ваше устройство:",
        parse_mode="HTML",
        reply_markup=help_menu()
    )

@router.callback_query(F.data.startswith("help:"))
async def process_help(callback: CallbackQuery):
    device = callback.data.split(":")[1]
    
    instructions = {
        "android": """
📱 <b>Настройка на Android (Nekoray)</b>

<b>1.</b> Скачайте Nekoray с GitHub
   github.com/MatsuriDayo/Nekoray/releases

<b>2.</b> Откройте приложение → "Program" → "Add profile from clipboard"

<b>3.</b> Скопируйте vless:// ссылку из бота и вставьте

<b>4.</b> Выберите сервер → "Start"

<b>5.</b> Проверьте IP на 2ip.ru

<b>Альтернатива:</b> v2rayNG из Google Play
""",
        "ios": """
🍎 <b>Настройка на iOS (Shadowrocket)</b>

<b>1.</b> Установите Shadowrocket из App Store ($2.99)

<b>2.</b> Скопируйте vless:// ссылку из бота

<b>3.</b> Откройте приложение — ссылка подхватится автоматически

<b>4.</b> Нажмите на добавленный сервер для подключения

<b>Бесплатная альтернатива:</b> Streisand (требует TestFlight)
""",
        "windows": """
💻 <b>Настройка на Windows (Nekoray)</b>

<b>1.</b> Скачайте Nekoray:
   github.com/MatsuriDayo/Nekoray/releases

<b>2.</b> Распакуйте архив и запустите nekoray.exe

<b>3.</b> "Program" → "Add profile from clipboard"

<b>4.</b> Вставьте vless:// ссылку из бота

<b>5.</b> Выберите сервер → ПКМ → "Start"

<b>6.</b> Проверьте IP в браузере
""",
        "macos": """
🍏 <b>Настройка на macOS</b>

<b>Вариант 1 — Nekoray:</b>
• Скачайте версию для macOS
• Аналогично Windows версии

<b>Вариант 2 — V2RayXS:</b>
• App Store или GitHub
• Импорт через JSON или ссылку

<b>Вариант 3 — Терминал:</b>
brew install v2ray
# Ручная настройка config.json
""",
        "linux": """
🐧 <b>Настройка на Linux</b>

<b>Nekoray (рекомендуется):</b>
• Скачайте AppImage с GitHub
• chmod +x Nekoray-x.x.x.AppImage
• ./Nekoray-x.x.x.AppImage

<b>Или v2ray-core:</b>
• Установите v2ray из репозитория
• Импортируйте JSON конфиг в /etc/v2ray/config.json
• systemctl restart v2ray

<b>Проверка:</b>
curl --proxy socks5h://127.0.0.1:1080 ifconfig.me
""",
        "router": """
📡 <b>Настройка на роутере</b>

<b>Важно:</b> Не все роутеры поддерживают VLESS.

<b>Keenetic с Entware:</b>
opkg install xray
# Ручная настройка /opt/etc/xray/config.json

<b>OpenWrt:</b>
• Установите пакет xray-core
• Настройка через Luci или вручную

<b>Рекомендация:</b> Настройте VPN на отдельном устройстве
и раздайте через него WiFi.
"""
    }
    
    text = instructions.get(device, "Инструкция не найдена")
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=help_menu()
    )

@router.message(F.text == "📞 Техподдержка")
async def btn_support(message: Message):
    await message.answer(
        f"📞 <b>Техническая поддержка</b>\n\n"
        f"Если у вас возникли проблемы:\n"
        f"• Не подключается VPN\n"
        f"• Низкая скорость\n"
        f"• Вопросы по оплате\n\n"
        f"👉 <a href='{cfg.SUPPORT_LINK}'>Написать в поддержку</a>\n\n"
        f"Или напишите напрямую: {cfg.SUPPORT_USERNAME}",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "back:menu")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu()
    )
Файл: bot/handlers/admin.py
Python
Copy
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import cfg
from bot.keyboards import admin_menu, admin_user_actions, back_to_menu
from bot.services.database import Database
from bot.services.xray_manager import XRayManager
from bot.utils.helpers import calculate_expiry, format_expiry

router = Router()
db = Database(cfg.DB_PATH)
xray = XRayManager(cfg.XRAY_CONFIG_PATH, cfg.KEYS_PATH)

class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_give_user = State()
    waiting_for_give_months = State()

def is_admin(telegram_id: int) -> bool:
    return telegram_id in cfg.ADMIN_IDS

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    stats = db.get_stats()
    
    text = (
        f"🔐 <b>Админ панель</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего пользователей: {stats['total_users']}\n"
        f"• Активных подписок: {stats['active_subscriptions']}\n"
        f"• Оплаченных подписок: {stats['paid_subscriptions']}\n"
        f"• Общая выручка: {stats['total_revenue']:.2f} ₽\n\n"
        f"Выберите действие:"
    )
    
    await message.answer(text, parse_mode="HTML", reply_markup=admin_menu())

@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    
    stats = db.get_stats()
    
    # Дополнительная статистика XRay
    clients = xray.get_all_clients()
    
    text = (
        f"📊 <b>Полная статистика</b>\n\n"
        f"<b>База данных:</b>\n"
        f"• Пользователей: {stats['total_users']}\n"
        f"• Подписок в БД: {stats['active_subscriptions']}\n"
        f"• Оплаченных: {stats['paid_subscriptions']}\n"
        f"• Выручка: {stats['total_revenue']:.2f} ₽\n\n"
        f"<b>XRay:</b>\n"
        f"• Клиентов в конфиге: {len(clients)}\n"
        f"• Админских: {sum(1 for c in clients if 'admin@' in c.get('email', ''))}\n"
        f"• Обычных: {sum(1 for c in clients if 'admin@' not in c.get('email', ''))}\n\n"
    )
    
    # Последние клиенты
    text += "<b>Последние клиенты:</b>\n"
    for client in clients[-5:]:
        text += f"• {client.get('email', 'N/A')}\n"
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu())

@router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    users = db.get_all_users(limit=10)
    
    text = "👥 <b>Пользователи (последние 10):</b>\n\n"
    for user in users:
        text += (
            f"🆔 <code>{user['telegram_id']}</code>\n"
            f"   @{user['username'] or 'no_username'}\n"
            f"   Подписок: {user['sub_count']}\n"
            f"   <a href='tg://user?id={user['telegram_id']}'>Написать</a> | "
            f"<a href='#'>Действия</a>\n\n"
        )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=admin_menu()
    )

@router.callback_query(F.data == "admin:search")
async def admin_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.edit_text(
        "🔍 Введите Telegram ID пользователя:",
        reply_markup=back_to_menu()
    )

@router.message(AdminStates.waiting_for_user_id)
async def process_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        user_id = int(message.text.strip())
        user = db.get_or_create_user(user_id)  # Получаем или создаем (если не было)
        
        subs = db.get_user_subscriptions(user_id, active_only=False)
        
        text = (
            f"👤 <b>Пользователь {user_id}</b>\n"
            f"Username: @{user.username or 'нет'}\n"
            f"Дата регистрации: {user.created_at}\n\n"
            f"<b>Подписки:</b>\n"
        )
        
        for sub in subs:
            status = "✅" if sub.is_active else "❌"
            expiry = format_expiry(sub.expires_at)
            text += f"{status} {sub.email} (до {expiry})\n"
        
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=admin_user_actions(user_id)
        )
        
    except ValueError:
        await message.answer("❌ Неверный ID. Введите число.")
        return
    
    await state.clear()

@router.callback_query(F.data == "admin:give")
async def admin_give_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.waiting_for_give_user)
    await callback.message.edit_text(
        "➕ Введите Telegram ID пользователя для выдачи подписки:",
        reply_markup=back_to_menu()
    )

@router.message(AdminStates.waiting_for_give_user)
async def process_give_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        user_id = int(message.text.strip())
        await state.update_data(target_user=user_id)
        await state.set_state(AdminStates.waiting_for_give_months)
        
        await message.answer(
            "Введите количество месяцев (1, 6, 12):",
            reply_markup=back_to_menu()
        )
    except ValueError:
        await message.answer("❌ Неверный ID")

@router.message(AdminStates.waiting_for_give_months)
async def process_give_months(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        months = int(message.text.strip())
        data = await state.get_data()
        user_id = data['target_user']
        
        # Создаем или продлеваем подписку
        subs = db.get_user_subscriptions(user_id)
        
        if subs:
            # Продлеваем существующую
            sub = subs[0]
            current_expiry = datetime.fromisoformat(sub.expires_at) if sub.expires_at else datetime.now()
            new_expiry = current_expiry + timedelta(days=30*months)
            db.extend_subscription(sub.email, new_expiry)
            
            text = f"✅ Подписка {sub.email} продлена на {months} мес.\nДо: {format_expiry(new_expiry.isoformat())}"
        else:
            # Создаем новую (без устройства, пользователь сам выберет)
            await message.answer(
                f"Пользователь {user_id} не имеет конфигов.\n"
                f"Попросите его создать конфигурацию через 'Получить конфиги'"
            )
            await state.clear()
            return
        
        db.log_admin_action(message.from_user.id, "give_subscription", user_id, f"{months} months")
        
        await message.answer(text, reply_markup=main_menu())
        
    except ValueError:
        await message.answer("❌ Неверное количество месяцев")
    
    await state.clear()

@router.callback_query(F.data.startswith("admin_give:"))
async def admin_give_direct(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    user_id = int(callback.data.split(":")[1])
    await callback.message.answer(
        f"Введите количество месяцев для пользователя {user_id}:"
    )
    # Можно добавить FSM для обработки ответа

@router.callback_query(F.data == "admin:sync")
async def admin_sync(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    # Получаем все активные email из БД
    all_subs = []
    # Нужно получить всех пользователей и их подписки
    # Упрощенно: получаем все подписки
    import sqlite3
    conn = sqlite3.connect(cfg.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscriptions WHERE is_active = 1")
    active_emails = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    # Добавляем админский
    active_emails.append("admin@server.com")
    
    removed = xray.sync_with_db(active_emails)
    
    text = (
        f"🔄 <b>Синхронизация завершена</b>\n\n"
        f"Активных в БД: {len(active_emails)}\n"
        f"Удалено из XRay: {len(removed)}\n"
    )
    if removed:
        text += f"\nУдаленные: {', '.join(removed)}"
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu())
Файл: bot/handlers/__init__.py
Python
Copy
from aiogram import Router

def get_routers() -> list[Router]:
    from . import user, admin
    
    return [
        user.router,
        admin.router,
    ]
Файл: bot/main.py
Python
Copy
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from bot.config import cfg
from bot.handlers import get_routers

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=cfg.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    # Регистрация роутеров
    for router in get_routers():
        dp.include_router(router)
    
    # Удаление вебхука и запуск
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
Файл: bot/__init__.py
Python
Copy
# Empty
Файл: bot/services/__init__.py
Python
Copy
# Empty
Файл: bot/handlers/payment.py (заглушка для интеграции)
Python
Copy
from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment
from aiogram.filters import Command

router = Router()

@router.message(Command("pay"))
async def cmd_pay(message: Message):
    await message.answer(
        "💳 Оплата временно производится через поддержку.\n"
        "Напишите @support для получения реквизитов."
    )

# Здесь можно добавить интеграцию с ЮKassa, CryptoBot и т.д.
4. Запуск
bash
Copy
# 1. Клонируем/создаем структуру
mkdir -p /opt/vpn-bot && cd /opt/vpn-bot

# 2. Создаем все файлы выше

# 3. Устанавливаем зависимости
pip install -r requirements.txt

# 4. Настраиваем окружение
cp .env.example .env
nano .env  # Заполняем BOT_TOKEN и ADMIN_IDS

# 5. Запускаем бота
python -m bot.main
