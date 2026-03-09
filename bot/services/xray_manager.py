import json
import os
import subprocess
import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional


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
            with open(keys_path, "r") as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        keys[key] = value
        return keys

    def _load_xray_config(self) -> dict:
        with open(self.config_path, "r") as f:
            return json.load(f)

    def _save_xray_config(self, config: dict):
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

    def _reload_xray(self):
        subprocess.run(["systemctl", "reload", "xray"], check=True)

    def _generate_uuid(self) -> str:
        return str(uuid.uuid4())

    def _create_vless_link(
        self, client_uuid: str, email: str, flow: str = "xtls-rprx-vision"
    ) -> str:
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

    def _create_json_config(
        self, client_uuid: str, email: str, flow: str = "xtls-rprx-vision"
    ) -> dict:
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
            "flow": flow,
        }

    def create_client(
        self,
        telegram_id: int,
        device_type: str = "mobile",
        flow: str = "xtls-rprx-vision",
    ) -> ClientConfig:
        """Создание клиента с XTLS (для 1-3 устройств)"""
        client_uuid = self._generate_uuid()

        device_emojis = {"mobile": "📱", "desktop": "💻", "tablet": "📟", "tv": "📺"}
        emoji = device_emojis.get(device_type, "📱")
        email = f"{emoji}{telegram_id}_{device_type}_{uuid.uuid4().hex[:6]}"

        # Добавляем в XRay
        xray_config = self._load_xray_config()
        new_client = {"id": client_uuid, "flow": flow, "email": email, "level": 0}

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
            flow=flow,
        )

    def create_shared_client(
        self, telegram_id: int, device_type: str = "shared"
    ) -> ClientConfig:
        """Создание общего клиента без flow (для неограниченных устройств)"""
        client_uuid = self._generate_uuid()
        email = f"🔓{telegram_id}_shared_{uuid.uuid4().hex[:8]}"

        # Без flow для совместимости
        flow = ""

        # Добавляем в XRay
        xray_config = self._load_xray_config()
        new_client = {"id": client_uuid, "flow": flow, "email": email, "level": 0}

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
            flow=flow,
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
                [
                    "xray",
                    "api",
                    "statsquery",
                    "--server=127.0.0.1:10085",
                    f"pattern=user>>>{email}>>>",
                ],
                capture_output=True,
                text=True,
                timeout=5,
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
                    "total_bytes": uplink + downlink,
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
            if client.get("email") not in active_emails and not client.get(
                "email", ""
            ).startswith("admin@"):
                clients.remove(client)
                removed.append(client.get("email"))

        if removed:
            self._save_xray_config(xray_config)
            self._reload_xray()

        return removed
