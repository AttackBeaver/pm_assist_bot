import asyncio
import logging
import uuid
import re
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.parser import parse_task as regex_parse_task
from bot.utils.llm_parser import parse_task_with_llm
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from bot.utils.meet_utils import process_meet_link
from web.database import add_user, add_task, get_telegram_id_by_username, add_meeting_reminder
from bot.utils.meet_processor import process_meeting
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)
router = Router()
_CONFIDENCE_THRESHOLD = 85


async def ensure_user_exists(username: str, bot: Bot, chat_id: int) -> int | None:
    clean = username.lstrip('@')
    existing_id = get_telegram_id_by_username(clean)
    if existing_id:
        return existing_id
    try:
        chat = await bot.get_chat(chat_id)
        member = await chat.get_member(clean)
        if member.user.id:
            add_user(member.user.id, clean, member.user.full_name)
            return member.user.id
    except Exception:
        pass
    return None

# НОВОЕ: парсинг времени встречи из текста
def parse_meeting_time(text: str) -> datetime | None:
    """
    Ищет в тексте указание времени встречи (например, "в 15:30", "через 20 минут").
    Возвращает datetime (с сегодняшним днём) или None.
    """
    now = datetime.now()
    # 1. "в 15:30" или "в 15-30"
    match = re.search(r'(?:в|встреча)\s+(\d{1,2})[:.-](\d{2})', text.lower())
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < now:
            dt += timedelta(days=1)
        return dt
    # 2. "через N минут"
    match = re.search(r'через\s+(\d+)\s+минут', text.lower())
    if match:
        minutes = int(match.group(1))
        return now + timedelta(minutes=minutes)
    # 3. "через N часов"
    match = re.search(r'через\s+(\d+)\s+часов?', text.lower())
    if match:
        hours = int(match.group(1))
        return now + timedelta(hours=hours)
    return None

@router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_text_message(message: Message, bot: Bot) -> None:
    # Ссылка на Яндекс.Диск
    yandex_link_match = re.search(r'(https?://disk\.yandex\.(?:ru|com)/(?:i|d|public)/[^\s]+)', message.text)
    if yandex_link_match:
        await process_meet_link(yandex_link_match.group(1), message, bot)
        return

    # Ссылка на Яндекс Телемост
    telemost_match = re.search(r'(https?://telemost\.yandex\.ru/j/\S+)', message.text)
    if telemost_match:
        meet_url = telemost_match.group(1)
        # НОВОЕ: пытаемся определить время встречи для напоминания
        meeting_time = parse_meeting_time(message.text)
        if meeting_time:
            remind_at = meeting_time - timedelta(minutes=10)
            if remind_at > datetime.now():
                add_meeting_reminder(message.chat.id, meet_url, remind_at)
                await message.reply(f"🔔 Напомню о встрече за 10 минут (в {remind_at.strftime('%H:%M')}).")
        await message.reply("🔗 Обнаружена ссылка на Яндекс Телемост. Начинаю запись (60 секунд)...")
        asyncio.create_task(process_meeting(meet_url, 60, message, bot))
        return

    # Регистрируем автора
    add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    # Гибридный парсинг: сначала LLM
    llm_result = parse_task_with_llm(message.text)
    if llm_result and llm_result.get("confidence", 0) >= _CONFIDENCE_THRESHOLD:
        parse_result = llm_result
        logger.info(f"✅ Распознано через LLM: confidence={parse_result['confidence']}")
    else:
        parse_result = regex_parse_task(message.text, known_usernames=[])
        logger.info(f"🔄 Fallback на regex: confidence={parse_result['confidence']}")

    if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
        return

    assignee_usernames = parse_result.get("assignees", [])
    if not assignee_usernames:
        assignee_usernames = [None]

    author_id = message.from_user.id

    for assignee_username in assignee_usernames:
        # ИЗМЕНЕНИЕ: если нет ответственного, responsible_id = None
        responsible_id = None
        if assignee_username:
            found_id = await ensure_user_exists(assignee_username, bot, message.chat.id)
            if found_id:
                responsible_id = found_id
        # Если assignee_username нет, responsible_id остаётся None

        # В YouGile передаём список ID ответственных (или пустой список)
        assignee_ids = [responsible_id] if responsible_id else []
        card_id = await create_yougile_task(
            title=parse_result["task"],
            description=message.text,
            deadline_str=parse_result["deadline"],
            assignee_user_ids=assignee_ids
        )
        if not card_id:
            await message.reply("❌ Не удалось создать задачу в YouGile.")
            return

        task_uuid = str(uuid.uuid4())
        add_task(
            task_id=task_uuid,
            title=parse_result["task"],
            description=message.text,
            responsible_telegram_id=responsible_id,  # может быть None
            author_telegram_id=author_id,
            deadline=parse_result["deadline"],
            deadline_timestamp=deadline_to_timestamp(parse_result["deadline"]) if parse_result["deadline"] else None,
            yougile_card_id=card_id,
            chat_id=message.chat.id,
        )

        # Уведомления
        if responsible_id is None:
            # Нет ответственного – уведомляем только автора с пометкой "без исполнителя"
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
            keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
            keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
            keyboard.adjust(1)
            try:
                await bot.send_message(
                    author_id,
                    f"📌 Вы создали задачу (без исполнителя):\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                    f"👥 Ответственные: не назначены\n\n"
                    f"Вы можете взять задачу в работу или назначить исполнителя в YouGile.",
                    reply_markup=keyboard.as_markup()
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление автору {author_id}: {e}")
        elif responsible_id == author_id:
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
            keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
            keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
            keyboard.adjust(1)
            try:
                await bot.send_message(
                    author_id,
                    f"📌 Вы создали задачу:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                    f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames[0] else 'вы'}\n\n"
                    f"Управляйте задачей:",
                    reply_markup=keyboard.as_markup()
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление автору {author_id}: {e}")
        else:
            keyboard_worker = InlineKeyboardBuilder()
            keyboard_worker.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
            keyboard_worker.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
            keyboard_worker.adjust(1)
            try:
                await bot.send_message(
                    responsible_id,
                    f"🔔 Вам назначена задача в группе {message.chat.title}:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                    f"Управляйте задачей:",
                    reply_markup=keyboard_worker.as_markup()
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление ответственному {responsible_id}: {e}")

            keyboard_author = InlineKeyboardBuilder()
            keyboard_author.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
            keyboard_author.adjust(1)
            try:
                await bot.send_message(
                    author_id,
                    f"📌 Вы создали задачу для @{assignee_username}:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                    f"Вы можете удалить задачу, если она создана ошибочно:",
                    reply_markup=keyboard_author.as_markup()
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление автору {author_id}: {e}")

    # Ответ в группе
    reply_text = (
        f"✅ Задача автоматически создана в YouGile!\n\n"
        f"📋 {parse_result['task']}\n"
        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
        f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames and assignee_usernames[0] else 'не назначены'}"
    )
    await message.reply(reply_text)