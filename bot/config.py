import json
import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = None
    SERVER_IP: str = os.getenv("SERVER_IP", "")
    XRAY_CONFIG_PATH: str = os.getenv(
        "XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json"
    )
    KEYS_PATH: str = os.getenv("KEYS_PATH", "/usr/local/etc/xray/keys.env")
    DB_PATH: str = os.getenv("DB_PATH", "/opt/vpn-bot/data/bot.db")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "")
    SUPPORT_LINK: str = os.getenv("SUPPORT_LINK", "")

    # Payment settings
    PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "manual")
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "")
    YOOKASSA_DEBUG: bool = os.getenv("YOOKASSA_DEBUG", "true").lower() == "true"

    def __post_init__(self):
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

        # Загрузка цен
        with open("data/prices.json", "r", encoding="utf-8") as f:
            self.PRICES = json.load(f)

        # YooKassa configuration
        if (
            self.PAYMENT_PROVIDER == "yookassa"
            and self.YOOKASSA_SHOP_ID
            and self.YOOKASSA_SECRET_KEY
        ):
            from yookassa import Configuration

            Configuration.account_id = self.YOOKASSA_SHOP_ID
            Configuration.secret_key = self.YOOKASSA_SECRET_KEY
            Configuration.is_test = self.YOOKASSA_DEBUG


cfg = Config()
