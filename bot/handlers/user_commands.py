import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from web.database import add_user, set_user_away, clear_user_away

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await message.answer(
        "Привет! Я PM‑Assist Bot. Помогаю превращать сообщения в задачи.\n\n"
        "Добавь меня в групповой чат — я буду автоматически распознавать задачи, "
        "дедлайны и ответственных, а также обрабатывать голосовые сообщения.\n\n"
        "Команды:\n"
        "/help — справка\n"
        "/away \\[причина\\] — отметить себя недоступным\n"
        "/back — вернуться в работу"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📌 *Как я работаю:*\n"
        "• В групповом чате читаю сообщения и ищу задачи\n"
        "• Если нахожу — предлагаю создать карточку в YouGile\n"
        "• Голосовые сообщения тоже распознаю\n"
        "• Напоминаю о дедлайнах и присылаю вечерний дайджест\n\n"
        "*Команды:*\n"
        "/away \\[причина\\] — задачи не будут назначаться до отмены\n"
        "/back — снова доступен для задач"
    )


@router.message(Command("away"))
async def cmd_away(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    reason = args[1] if len(args) > 1 else "Не указана"
    until = datetime.now() + timedelta(days=7)
    set_user_away(message.from_user.id, reason, until)
    await message.answer(
        f"✅ Вы отмечены как недоступный\\.\n"
        f"Причина: {reason}\n"
        f"До: {until.strftime('%d\\.%m\\.%Y %H:%M')}\n\n"
        "Задачи не будут назначаться на вас\\. Для возврата используйте /back"
    )


@router.message(Command("back"))
async def cmd_back(message: Message) -> None:
    clear_user_away(message.from_user.id)
    await message.answer("✅ Вы снова доступны для задач\\.")