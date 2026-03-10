import asyncio
import json
import logging
import ssl
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from bot.config import cfg
from bot.handlers import get_routers
from bot.handlers.payment import handle_yookassa_webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_yookassa_webhook_request(request):
    """Обработчик webhook от YooKassa"""
    try:
        data = await request.json()
        logger.info(f"Received webhook: {data}")
        
        event_type = data.get("event", "")
        
        if event_type == "payment.succeeded":
            result = await handle_yookassa_webhook(data)
            
            if result and result.get("status") == "success":
                return web.Response(text="OK")
        
        return web.Response(text="OK")  # YooKassa ожидает 200 для подтверждения получения
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(text="ERROR", status=500)


async def start_webhook_server():
    """Запуск веб-сервера для webhook с SSL"""
    app = web.Application()
    app.router.add_post("/webhook/yookassa", handle_yookassa_webhook_request)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Запускаем на порту 8443 с SSL
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain("./cert.pem", "./key.pem")
    
    site = web.TCPSite(runner, "0.0.0.0", 8443, ssl_context=ssl_context)
    await site.start()
    logger.info("Webhook server started on port 8443 with SSL")


async def main():
    bot = Bot(token=cfg.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Регистрация роутеров
    for router in get_routers():
        dp.include_router(router)

    # Запускаем webhook сервер
    await start_webhook_server()

    # Удаление вебхука и запуск
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
