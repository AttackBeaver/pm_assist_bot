import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from bot.handlers import user_commands, message_handler, voice_handler, callbacks
from bot.tasks.scheduler import reminder_worker, evening_digest_worker, stale_task_reminder_worker
import uvicorn
from web.app import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

async def run_web():
    """Запускает веб-кабинет (FastAPI) асинхронно."""
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    dp = Dispatcher()
    dp.include_router(user_commands.router)
    dp.include_router(message_handler.router)
    dp.include_router(voice_handler.router)
    dp.include_router(callbacks.router)
    logger.info("Запуск PM-Assist Bot...")

    # Запускаем все компоненты конкурентно
    await asyncio.gather(
        run_web(),
        dp.start_polling(bot, allowed_updates=['message', 'callback_query', 'my_chat_member']),
        reminder_worker(bot),
        evening_digest_worker(bot),
        stale_task_reminder_worker(bot)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")