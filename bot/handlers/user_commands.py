import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from datetime import datetime, timedelta
import re

from web.database import add_user, get_user, set_user_away, clear_user_away

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    user = add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )
    await message.answer(
        "Привет! Я PM‑Assist_bot. Я помогаю превращать сообщения в задачи.\n\n"
        "Добавь меня в групповой чат, и я буду автоматически распознавать задачи, "
        "дедлайны и ответственных. Также я умею распознавать голосовые сообщения.\n\n"
        "Команды:\n"
        "/help – справка\n"
        "/away [причина] – отметить себя недоступным (больничный/отпуск)\n"
        "/back – вернуться в работу"
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📌 Как я работаю:\n"
        "- В групповом чате я читаю сообщения и ищу задачи.\n"
        "- Если нахожу – предлагаю создать карточку в YouGile.\n"
        "- Голосовые сообщения тоже распознаю.\n"
        "- Напоминаю о дедлайнах и присылаю вечерний дайджест.\n\n"
        "Команды:\n"
        "/away [причина] – я не буду назначать тебе задачи до отмены\n"
        "/back – снова доступен для задач"
    )

@router.message(Command("away"))
async def cmd_away(message: Message):
    args = message.text.split(maxsplit=1)
    reason = args[1] if len(args) > 1 else "Не указана"
    # По умолчанию недоступен на 7 дней
    until = datetime.now() + timedelta(days=7)
    if set_user_away(message.from_user.id, reason, until):
        await message.answer(
            f"✅ Вы отмечены как недоступный.\n"
            f"Причина: {reason}\n"
            f"До: {until.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Задачи не будут назначаться на вас. Для возврата используйте /back"
        )
    else:
        await message.answer("❌ Не удалось обновить статус. Попробуйте позже.")

@router.message(Command("back"))
async def cmd_back(message: Message):
    if clear_user_away(message.from_user.id):
        await message.answer("✅ Вы снова доступны для задач.")
    else:
        await message.answer("❌ Не удалось обновить статус.")