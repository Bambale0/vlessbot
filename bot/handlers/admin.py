from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

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

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu())


@router.callback_query(F.data == "admin:search")
async def admin_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.edit_text(
        "🔍 Введите Telegram ID пользователя:", reply_markup=back_to_menu()
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
            text, parse_mode="HTML", reply_markup=admin_user_actions(user_id)
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
        reply_markup=back_to_menu(),
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
            "Введите количество месяцев (1, 6, 12):", reply_markup=back_to_menu()
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
        user_id = data["target_user"]

        # Создаем или продлеваем подписку
        subs = db.get_user_subscriptions(user_id)

        if subs:
            # Продлеваем существующую
            sub = subs[0]
            current_expiry = (
                datetime.fromisoformat(sub.expires_at)
                if sub.expires_at
                else datetime.now()
            )
            new_expiry = current_expiry + timedelta(days=30 * months)
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

        db.log_admin_action(
            message.from_user.id, "give_subscription", user_id, f"{months} months"
        )

        await message.answer(text, reply_markup=admin_menu())

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
