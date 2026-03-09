import json
import os
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import cfg
from bot.keyboards import back_to_menu, main_menu
from bot.services.database import Database
from bot.services.payment_service import PaymentService
from bot.services.xray_manager import XRayManager
from bot.utils.helpers import calculate_expiry

router = Router()
db = Database(cfg.DB_PATH)
xray = XRayManager(cfg.XRAY_CONFIG_PATH, cfg.KEYS_PATH)
payment_service = PaymentService(cfg.DB_PATH)

# Состояния для оплаты
class PaymentStates(StatesGroup):
    waiting_for_payment = State()


async def process_payment_success(telegram_id: int, plan_key: str, period_months: int):
    """Обработка успешного платежа - активация подписки"""

    # Проверяем, есть ли уже конфиг у пользователя
    subs = db.get_user_subscriptions(telegram_id)

    if subs:
        # Продлеваем существующую подписку
        from datetime import datetime, timedelta

        for sub in subs:
            if sub.expires_at:
                current_expiry = datetime.fromisoformat(sub.expires_at)
            else:
                current_expiry = datetime.now()
            new_expiry = current_expiry + timedelta(days=30 * period_months)
            db.extend_subscription(sub.email, new_expiry)
        return subs[0].email if subs else None
    else:
        # Создаем новую подписку
        try:
            config = xray.create_client(telegram_id, "mobile", "xtls-rprx-vision")
            from datetime import datetime, timedelta

            expires_at = datetime.now() + timedelta(days=30 * period_months)

            db.add_subscription(
                telegram_id=telegram_id,
                email=config.email,
                uuid=config.uuid,
                device_type="mobile",
                flow="xtls-rprx-vision",
                expires_at=expires_at,
            )
            return config.email
        except Exception as e:
            print(f"Error creating subscription: {e}")
            return None


@router.message(Command("pay"))
async def cmd_pay(message: Message):
    """Обработка команды /pay"""
    if cfg.PAYMENT_PROVIDER == "yookassa":
        # Если используем YooKassa - показываем тарифы
        await message.answer(
            "💳 <b>Оплата через ЮKassa</b>\n\n" "Выберите тариф для оплаты:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="1 месяц - 299₽",
                            callback_data="yookassa_buy:1_month:1",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="6 месяцев - 1499₽",
                            callback_data="yookassa_buy:6_months:6",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="12 месяцев - 2499₽",
                            callback_data="yookassa_buy:12_months:12",
                        )
                    ],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back:menu")],
                ]
            ),
        )
    else:
        await message.answer(
            "💳 Оплата временно производится через поддержку.\n"
            f"Напишите {cfg.SUPPORT_USERNAME} для получения реквизитов."
        )


@router.callback_query(F.data.startswith("yookassa_buy:"))
async def process_yookassa_buy(callback: CallbackQuery):
    """Обработка покупки через YooKassa"""
    try:
        # Разбираем callback_data: yookassa_buy:plan_key:period_months
        parts = callback.data.split(":")
        plan_key = parts[1]
        period_months = int(parts[2])

        # Создаем платеж в YooKassa
        payment_data = await payment_service.create_payment(
            telegram_id=callback.from_user.id,
            plan_key=plan_key,
            period_months=period_months,
        )

        if payment_data:
            # Сохраняем информацию о платеже в БД
            db.add_payment(
                telegram_id=callback.from_user.id,
                amount=payment_data["amount"],
                currency="RUB",
                period_months=period_months,
                status="pending",
            )

            # Отправляем пользователю ссылку на оплату
            await callback.message.edit_text(
                f"💳 <b>Оплата через ЮKassa</b>\n\n"
                f"Тариф: {payment_data['description']}\n"
                f"Сумма: {payment_data['amount']} ₽\n\n"
                f"Для оплаты нажмите кнопку ниже:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="💰 Оплатить", url=payment_data["confirmation_url"]
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="🔄 Проверить оплату",
                                callback_data=f"check_payment:{payment_data['payment_id']}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="◀️ Отмена", callback_data="back:menu"
                            )
                        ],
                    ]
                ),
            )
        else:
            await callback.answer(
                "Ошибка создания платежа. Проверьте настройки YooKassa.",
                show_alert=True,
            )

    except Exception as e:
        print(f"Error processing payment: {e}")
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment(callback: CallbackQuery):
    """Проверка статуса платежа"""
    payment_id = callback.data.split(":")[1]

    payment_status = await payment_service.check_payment(payment_id)

    if payment_status:
        if payment_status.get("paid"):
            # Платеж успешен - активируем подписку
            # Находим данные платежа в БД
            # (в реальном приложении нужно хранить mapping payment_id -> user)

            await callback.message.edit_text(
                "✅ <b>Оплата успешна!</b>\n\n"
                "Ваша подписка активирована.\n"
                "Используйте /configs для получения конфигурации.",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )
        else:
            status = payment_status.get("status", "unknown")
            await callback.answer(
                f"Платеж ещё не завершён. Статус: {status}", show_alert=True
            )
    else:
        await callback.answer("Не удалось проверить платеж.", show_alert=True)


# Обработка webhook от YooKassa (для Flask/aiohttp)
async def handle_yookassa_webhook(event_data: dict):
    """Обработка webhook уведомлений от YooKassa"""
    result = await payment_service.handle_webhook(event_data)

    if result and result.get("event") == "payment_succeeded":
        telegram_id = result.get("telegram_id")
        plan_key = result.get("plan_key")
        period_months = result.get("period_months")

        if telegram_id and period_months:
            # Активируем подписку
            email = await process_payment_success(
                int(telegram_id), plan_key, period_months
            )

            # Обновляем статус платежа в БД
            # (нужно добавить метод для поиска по payment_id)

            return {"status": "success", "email": email}

    return {"status": "error"}


# Для ручной оплаты (старый функционал)
@router.callback_query(F.data == "payment:manual")
async def process_manual_payment(callback: CallbackQuery):
    """Обработка запроса на ручную оплату"""
    await callback.message.edit_text(
        "💳 <b>Ручная оплата</b>\n\n"
        "Для оплаты свяжитесь с поддержкой:\n"
        f"{cfg.SUPPORT_USERNAME}\n\n"
        "После оплаты администратор активирует вашу подписку.",
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
