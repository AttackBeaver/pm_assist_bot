import logging
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.parser import parse_task
from web.database import add_user

logger = logging.getLogger(__name__)
router = Router()

# Временное хранилище неподтверждённых задач (сбрасывается при перезапуске бота)
pending_text_tasks: Dict[str, Dict[str, Any]] = {}

# _CONFIDENCE_THRESHOLD = 60
_CONFIDENCE_THRESHOLD = 30

@router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_text_message(message: Message) -> None:
    logger.info(f"Получено сообщение в группе: {message.text[:50]}")   
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    parse_result = parse_task(message.text, known_usernames=[])
    logger.info(f"Результат парсинга: confidence={parse_result['confidence']}, task={parse_result['task'][:50]}, deadline={parse_result['deadline']}, assignee={parse_result['assignee']}")

    if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
        logger.info(f"Пропускаем: confidence {parse_result['confidence']} < {_CONFIDENCE_THRESHOLD}")
        return

    callback_id = f"text_{message.message_id}"
    pending_text_tasks[callback_id] = {
        "title": parse_result["task"],
        "description": message.text,
        "deadline_str": parse_result["deadline"],
        "assignee_username": parse_result["assignee"],
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "from_user_id": message.from_user.id,
    }

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, создать задачу", callback_data=f"confirm_text_{callback_id}")
    builder.button(text="❌ Отмена", callback_data=f"cancel_text_{callback_id}")
    builder.adjust(1)

    lines = [f"📋 Задача: {parse_result['task']}"]
    if parse_result["deadline"]:
        lines.append(f"⏰ Дедлайн: {parse_result['deadline']}")
    if parse_result["assignee"]:
        lines.append(f"👤 Ответственный: @{parse_result['assignee']}")
    task_info = "\n".join(lines)

    await message.reply(
        f"📝 Найдена задача:\n\n{task_info}\n\nСоздать карточку в YouGile?",
        reply_markup=builder.as_markup(),
    )