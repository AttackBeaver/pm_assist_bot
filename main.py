import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN

# Импорт роутеров
from bot.handlers import user_commands, message_handler, voice_handler, callbacks
from bot.tasks.scheduler import reminder_worker, evening_digest_worker

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Подключаем роутеры
dp.include_router(user_commands.router)
dp.include_router(message_handler.router)
dp.include_router(voice_handler.router)
dp.include_router(callbacks.router)

async def main():
    # Запускаем фоновые задачи
    asyncio.create_task(reminder_worker(bot))
    asyncio.create_task(evening_digest_worker(bot))
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())