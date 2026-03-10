import io
import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import cfg
from bot.keyboards import (
    back_to_menu,
    config_actions,
    device_selection,
    help_menu,
    main_menu,
    payment_plans,
    payment_plans_yookassa,
)
from bot.services.database import Database
from bot.services.xray_manager import XRayManager
from bot.utils.helpers import calculate_expiry, format_expiry, generate_qr

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
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "menu:payment")
async def btn_payment(callback: CallbackQuery):
    if cfg.PAYMENT_PROVIDER == "yookassa":
        await callback.message.edit_text(
            "💳 <b>Оплата через ЮKassa</b>\n\n" "Выберите тариф:",
            parse_mode="HTML",
            reply_markup=payment_plans_yookassa(),
        )
    else:
        await callback.message.edit_text(
            "📋 Выберите тариф:", reply_markup=payment_plans(cfg.PRICES)
        )
    await callback.answer()


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
        text, parse_mode="HTML", reply_markup=back_to_menu()
    )


@router.callback_query(F.data == "menu:configs")
async def btn_configs(callback: CallbackQuery):
    subs = db.get_user_subscriptions(callback.from_user.id)

    if not subs:
        await callback.message.edit_text(
            "❌ У вас нет активных конфигураций.\n\n"
            "Сначала оплатите подписку или выберите устройство для создания конфига:",
            parse_mode="HTML",
            reply_markup=device_selection(),
        )
        await callback.answer()
        return

    text = "📱 <b>Ваши конфигурации:</b>\n\n"
    for sub in subs:
        expiry = format_expiry(sub.expires_at)
        flow_type = "🔓 Общий" if not sub.flow else "⚡ XTLS"
        
        # Generate VLESS link
        try:
            vless_link = xray._create_vless_link(sub.uuid, sub.email, sub.flow)
        except:
            vless_link = f"vless://{sub.uuid}@194.5.79.95:443?security=reality&flow={sub.flow}&type=tcp&sni=www.google.com&fp=chrome"
        
        text += (
            f"<b>{sub.email}</b>\n"
            f"Тип: {flow_type}\n"
            f"Действует до: {expiry}\n"
            f"<code>{vless_link}</code>\n\n"
        )

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu())
    except Exception as e:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("device:"))
async def process_device(callback: CallbackQuery):
    device_type = callback.data.split(":")[1]
    print(f"[DEBUG] process_device called for user {callback.from_user.id}, device: {device_type}")

    await callback.message.edit_text("⏳ Создаю конфигурацию...")

    try:
        print(f"[DEBUG] Creating config for {callback.from_user.id}")
        if device_type == "shared":
            # Общий конфиг без flow
            config = xray.create_shared_client(callback.from_user.id, device_type)
            flow = ""
        else:
            # Индивидуальный конфиг с XTLS
            config = xray.create_client(
                callback.from_user.id, device_type, "xtls-rprx-vision"
            )
            flow = "xtls-rprx-vision"
        
        print(f"[DEBUG] Config created: {config.link[:50]}...")

        # Сохраняем в БД (без срока, пока не оплачено)
        db.add_subscription(
            telegram_id=callback.from_user.id,
            email=config.email,
            uuid=config.uuid,
            device_type=device_type,
            flow=flow,
            expires_at=None,  # Бессрочно до оплаты или тестовый период
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
            parse_mode="HTML",
        )

        # Отправляем JSON файл
        json_bytes = json.dumps(config.json_config, indent=2).encode()
        await callback.message.answer_document(
            BufferedInputFile(json_bytes, filename=f"{config.email}.json"),
            caption="📄 JSON конфиг для Nekoray/v2rayN",
            reply_markup=main_menu(),
        )

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "menu:help")
async def btn_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "📚 <b>Инструкции по настройке</b>\n\n" "Выберите ваше устройство:",
        parse_mode="HTML",
        reply_markup=help_menu(),
    )
    await callback.answer()


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
""",
    }

    text = instructions.get(device, "Инструкция не найдена")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=help_menu())


@router.callback_query(F.data == "menu:support")
async def btn_support(callback: CallbackQuery):
    await callback.message.edit_text(
        f"📞 <b>Техническая поддержка</b>\n\n"
        f"Если у вас возникли проблемы:\n"
        f"• Не подключается VPN\n"
        f"• Низкая скорость\n"
        f"• Вопросы по оплате\n\n"
        f"👉 <a href='{cfg.SUPPORT_LINK}'>Написать в поддержку</a>\n\n"
        f"Или напишите напрямую: {cfg.SUPPORT_USERNAME}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "back:menu")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
