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
