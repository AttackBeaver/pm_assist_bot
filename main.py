import asyncio
import logging
from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from bot.handlers import user_commands, message_handler, voice_handler, callbacks
from bot.tasks.scheduler import reminder_worker, evening_digest_worker, stale_task_reminder_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    dp = Dispatcher()
    dp.include_router(user_commands.router)
    dp.include_router(message_handler.router)
    dp.include_router(voice_handler.router)
    dp.include_router(callbacks.router)

    logger.info("Запуск PM-Assist Bot...")

    async with asyncio.TaskGroup() as tg:
        tg.create_task(reminder_worker(bot))
        tg.create_task(evening_digest_worker(bot))
        tg.create_task(stale_task_reminder_worker(bot))
        tg.create_task(dp.start_polling(bot, allowed_updates=['message', 'callback_query', 'my_chat_member']))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")