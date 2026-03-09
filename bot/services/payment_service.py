import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

# Конфигурация YooKassa
from yookassa import Configuration, Payment

# Настройка YooKassa
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_DEBUG = os.getenv("YOOKASSA_DEBUG", "true").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# Настройка библиотеки
if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
    Configuration.is_test = YOOKASSA_DEBUG


class PaymentService:
    """Сервис для работы с платежами через YooKassa"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.is_configured = bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)

    def _load_prices(self) -> dict:
        """Загрузка цен из prices.json"""
        try:
            with open("data/prices.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading prices: {e}")
            return {}

    async def create_payment(
        self, telegram_id: int, plan_key: str, period_months: int
    ) -> Optional[Dict[str, Any]]:
        """
        Создание платежа в YooKassa

        Args:
            telegram_id: ID пользователя Telegram
            plan_key: Ключ тарифа (например, "1_month")
            period_months: Количество месяцев подписки

        Returns:
            Словарь с данными платежа или None при ошибке
        """
        if not self.is_configured:
            return None

        prices = self._load_prices()
        plan = prices.get("plans", {}).get(plan_key)

        if not plan:
            return None

        amount = plan["price_rub"]
        description = f"VPN подписка: {plan['name']}"

        # Создаем уникальный ID платежа
        payment_id = str(uuid.uuid4())

        try:
            payment = Payment.create(
                {
                    "amount": {"value": str(amount), "currency": "RUB"},
                    "payment_method_data": {"type": "bank_card"},
                    "confirmation": {
                        "type": "redirect",
                        "return_url": f"{WEBHOOK_URL}/success"
                        if WEBHOOK_URL
                        else "https://t.me/YOUR_BOT",
                    },
                    "capture": True,
                    "description": description,
                    "metadata": {
                        "telegram_id": str(telegram_id),
                        "plan_key": plan_key,
                        "period_months": period_months,
                        "payment_id": payment_id,
                    },
                },
                payment_id,
            )

            # Возвращаем данные для создания платежа
            return {
                "payment_id": payment.id,
                "confirmation_url": payment.confirmation.confirmation_url,
                "amount": amount,
                "description": description,
                "status": payment.status,
            }

        except Exception as e:
            print(f"Error creating payment: {e}")
            return None

    async def check_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Проверка статуса платежа

        Args:
            payment_id: ID платежа в YooKassa

        Returns:
            Словарь со статусом платежа или None
        """
        if not self.is_configured:
            return None

        try:
            payment = Payment.find_one(payment_id)
            return {
                "status": payment.status,
                "paid": payment.paid,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
            }
        except Exception as e:
            print(f"Error checking payment: {e}")
            return None

    async def handle_webhook(self, event_data: dict) -> Optional[Dict[str, Any]]:
        """
        Обработка webhook от YooKassa

        Args:
            event_data: Данные события от YooKassa

        Returns:
            Данные для обработки или None
        """
        event_type = event_data.get("event", "")

        if event_type == "payment.succeeded":
            payment_obj = event_data.get("object", {})
            metadata = payment_obj.get("metadata", {})

            return {
                "event": "payment_succeeded",
                "telegram_id": metadata.get("telegram_id"),
                "plan_key": metadata.get("plan_key"),
                "period_months": metadata.get("period_months"),
                "payment_id": payment_obj.get("id"),
                "amount": payment_obj.get("amount", {}).get("value"),
            }

        elif event_type == "payment.canceled":
            payment_obj = event_data.get("object", {})
            return {"event": "payment_canceled", "payment_id": payment_obj.get("id")}

        return None

    def get_payment_url(self, payment_id: str) -> str:
        """Получение URL для оплаты (если нужно создать новый платеж)"""
        # Для этого нужно создать новый платеж
        # Этот метод можно использовать для повторной попытки
        return ""


# Функция для создания платежа (для использования в хендлерах)
async def create_yookassa_payment(
    telegram_id: int, plan_key: str, period_months: int, db_path: str
) -> Optional[Dict[str, Any]]:
    """Создание платежа через YooKassa"""
    service = PaymentService(db_path)
    return await service.create_payment(telegram_id, plan_key, period_months)


# Функция для проверки платежа
async def check_yookassa_payment(
    payment_id: str, db_path: str
) -> Optional[Dict[str, Any]]:
    """Проверка статуса платежа"""
    service = PaymentService(db_path)
    return await service.check_payment(payment_id)
