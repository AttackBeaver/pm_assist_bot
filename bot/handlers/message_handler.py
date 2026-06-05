import logging
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.parser import parse_task
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from web.database import add_user, add_task, get_telegram_id_by_username, get_user

logger = logging.getLogger(__name__)
router = Router()
_CONFIDENCE_THRESHOLD = 50

async def ensure_user_exists(username: str, bot: Bot, chat_id: int) -> int | None:
    """Проверяет, есть ли пользователь в БД. Если нет – пытается получить telegram_id из чата."""
    # Убираем @ в начале
    clean = username.lstrip('@')
    existing_id = get_telegram_id_by_username(clean)
    if existing_id:
        return existing_id
    # Пытаемся найти пользователя в чате
    try:
        # Получаем список участников чата (требует прав администратора)
        # В группе без прав может не работать, но попробуем
        chat = await bot.get_chat(chat_id)
        member = await chat.get_member(clean)
        if member.user.id:
            add_user(member.user.id, clean, member.user.full_name)
            return member.user.id
    except Exception:
        pass
    return None

@router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_text_message(message: Message, bot: Bot) -> None:
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    parse_result = parse_task(message.text, known_usernames=[])
    if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
        return

    responsible_id = message.from_user.id
    assignee_username = parse_result.get("assignee")
    if assignee_username:
        # Пытаемся найти или создать пользователя
        found_id = await ensure_user_exists(assignee_username, bot, message.chat.id)
        if found_id:
            responsible_id = found_id
            logger.info(f"Назначен ответственный {assignee_username} (id={responsible_id})")
        else:
            logger.warning(f"Пользователь @{assignee_username} не найден в БД и чате. Задача назначена автору.")

    card_id = await create_yougile_task(
        title=parse_result["task"],
        description=message.text,
        deadline_str=parse_result["deadline"],
    )
    if not card_id:
        await message.reply("❌ Не удалось создать задачу в YouGile.")
        return

    task_uuid = str(uuid.uuid4())
    add_task(
        task_id=task_uuid,
        title=parse_result["task"],
        description=message.text,
        responsible_telegram_id=responsible_id,
        deadline=parse_result["deadline"],
        deadline_timestamp=deadline_to_timestamp(parse_result["deadline"]) if parse_result["deadline"] else None,
        yougile_card_id=card_id,
        chat_id=message.chat.id,
    )

    # Уведомление ответственному
    if responsible_id != message.from_user.id:
        try:
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
            keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
            keyboard.button(text="❌ Отменить", callback_data=f"cancel_task_{task_uuid}")
            keyboard.adjust(1)
            await bot.send_message(
                responsible_id,
                f"🔔 Вам назначена задача в группе {message.chat.title}:\n\n"
                f"📋 {parse_result['task']}\n"
                f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                f"Управляйте задачей с помощью кнопок:",
                reply_markup=keyboard.as_markup()
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {responsible_id}: {e}")

    # Ответ в группе с кнопкой отмены
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить задачу", callback_data=f"cancel_task_{task_uuid}")
    builder.adjust(1)

    reply_text = (
        f"✅ Задача автоматически создана в YouGile!\n\n"
        f"📋 {parse_result['task']}\n"
        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
        f"👤 Ответственный: @{assignee_username or 'не назначен'}\n\n"
        f"Нажмите «Отменить», если задача создана ошибочно."
    )
    await message.reply(reply_text, reply_markup=builder.as_markup())