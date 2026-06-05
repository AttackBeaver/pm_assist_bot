import logging
import uuid
from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.parser import parse_task
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from web.database import add_user, add_task

logger = logging.getLogger(__name__)
router = Router()
_CONFIDENCE_THRESHOLD = 50


@router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_text_message(message: Message) -> None:
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    parse_result = parse_task(message.text, known_usernames=[])
    if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
        return

    # Автоматическое создание задачи в YouGile
    card_id = await create_yougile_task(
        title=parse_result["task"],
        description=message.text,
        deadline_str=parse_result["deadline"],
    )
    if not card_id:
        await message.reply("❌ Не удалось создать задачу в YouGile. Проверьте настройки.")
        return

    # Сохраняем в локальную БД
    task_uuid = str(uuid.uuid4())
    add_task(
        task_id=task_uuid,
        title=parse_result["task"],
        description=message.text,
        responsible_telegram_id=message.from_user.id,
        deadline=parse_result["deadline"],
        deadline_timestamp=deadline_to_timestamp(parse_result["deadline"]) if parse_result["deadline"] else None,
        yougile_card_id=card_id,
        chat_id=message.chat.id,
    )

    # Кнопка отмены
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить задачу", callback_data=f"cancel_task_{task_uuid}")
    builder.adjust(1)

    reply_text = (
        f"✅ Задача автоматически создана в YouGile!\n\n"
        f"📋 {parse_result['task']}\n"
        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
        f"👤 Ответственный: @{parse_result['assignee'] or 'не назначен'}\n\n"
        f"Нажмите «Отменить», если задача создана ошибочно."
    )
    await message.reply(reply_text, reply_markup=builder.as_markup())