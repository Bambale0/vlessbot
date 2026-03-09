from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Оплатить подписку")],
            [
                KeyboardButton(text="🔑 Получить конфиги"),
                KeyboardButton(text="❓ Помощь"),
            ],
            [KeyboardButton(text="📞 Техподдержка")],
        ],
        resize_keyboard=True,
    )


def payment_plans(prices: dict):
    buttons = []
    for key, plan in prices["plans"].items():
        badge = plan.get("badge", "")
        text = f"{plan['name']} - {plan['price_rub']}₽ {badge}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"buy:{key}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_plans_yookassa():
    """Кнопки оплаты через YooKassa"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1 месяц - 299₽", callback_data="yookassa_buy:1_month:1"
                )
            ],
            [
                InlineKeyboardButton(
                    text="6 месяцев - 1499₽ 🔥", callback_data="yookassa_buy:6_months:6"
                )
            ],
            [
                InlineKeyboardButton(
                    text="12 месяцев - 2499₽ 💰",
                    callback_data="yookassa_buy:12_months:12",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back:menu")],
        ]
    )


def device_selection():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 Телефон", callback_data="device:mobile"),
                InlineKeyboardButton(
                    text="💻 Компьютер", callback_data="device:desktop"
                ),
            ],
            [
                InlineKeyboardButton(text="📟 Планшет", callback_data="device:tablet"),
                InlineKeyboardButton(text="📺 ТВ", callback_data="device:tv"),
            ],
            [
                InlineKeyboardButton(
                    text="🔓 Общий (все устройства)", callback_data="device:shared"
                )
            ],
        ]
    )


def config_actions(email: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Копировать ссылку", callback_data=f"copy:{email}"
                ),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{email}"),
            ]
        ]
    )


def admin_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [
                InlineKeyboardButton(
                    text="👥 Список пользователей", callback_data="admin:users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Найти пользователя", callback_data="admin:search"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Выдать подписку", callback_data="admin:give"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Синхронизировать XRay", callback_data="admin:sync"
                )
            ],
        ]
    )


def admin_user_actions(telegram_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить подписку",
                    callback_data=f"admin_give:{telegram_id}",
                ),
                InlineKeyboardButton(
                    text="📋 Его конфиги", callback_data=f"admin_configs:{telegram_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать", callback_data=f"admin_block:{telegram_id}"
                ),
                InlineKeyboardButton(
                    text="✅ Разблокировать",
                    callback_data=f"admin_unblock:{telegram_id}",
                ),
            ],
        ]
    )


def help_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 Android", callback_data="help:android"),
                InlineKeyboardButton(text="🍎 iOS", callback_data="help:ios"),
            ],
            [
                InlineKeyboardButton(text="💻 Windows", callback_data="help:windows"),
                InlineKeyboardButton(text="🍏 macOS", callback_data="help:macos"),
            ],
            [
                InlineKeyboardButton(text="🐧 Linux", callback_data="help:linux"),
                InlineKeyboardButton(text="📡 Роутер", callback_data="help:router"),
            ],
            [
                InlineKeyboardButton(
                    text="📞 Связаться с поддержкой", url="https://t.me/your_support"
                )
            ],
        ]
    )


def back_to_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back:menu")]
        ]
    )
