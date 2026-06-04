import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from config import BOT_TOKEN

# Включаем логирование, чтобы видеть ошибки
logging.basicConfig(level=logging.INFO)

# Создаём объекты бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я PM‑Assist_bot. Работаю в фоне и помогаю с задачами.")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())