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

def parse_meeting_time(text: str) -> datetime | None:
    now = datetime.now()
    match = re.search(r'(?:в|встреча)\s+(\d{1,2})[:.-](\d{2})', text.lower())
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < now:
            dt += timedelta(days=1)
        return dt
    match = re.search(r'через\s+(\d+)\s+минут', text.lower())
    if match:
        minutes = int(match.group(1))
        return now + timedelta(minutes=minutes)
    match = re.search(r'через\s+(\d+)\s+часов?', text.lower())
    if match:
        hours = int(match.group(1))
        return now + timedelta(hours=hours)
    return None

@router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_text_message(message: Message, bot: Bot) -> None:
    yandex_link_match = re.search(r'(https?://disk\.yandex\.(?:ru|com)/(?:i|d|public)/[^\s]+)', message.text)
    if yandex_link_match:
        await process_meet_link(yandex_link_match.group(1), message, bot)
        return

    telemost_match = re.search(r'(https?://telemost\.yandex\.ru/j/\S+)', message.text)
    if telemost_match:
        meet_url = telemost_match.group(1)
        meeting_time = parse_meeting_time(message.text)
        if meeting_time:
            remind_at = meeting_time - timedelta(minutes=10)
            if remind_at > datetime.now():
                add_meeting_reminder(message.chat.id, meet_url, remind_at)
                await message.reply(f"🔔 Напомню о встрече за 10 минут (в {remind_at.strftime('%H:%M')}).")
        await message.reply("🔗 Обнаружена ссылка на Яндекс Телемост. Начинаю запись (60 секунд)...")
        asyncio.create_task(process_meeting(meet_url, 60, message, bot))
        return

    add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    # --- Гибридный парсинг: LLM может вернуть список задач ---
    llm_result = parse_task_with_llm(message.text)
    tasks_to_create = []  # список словарей с ключами task, deadline, assignees, confidence

    if llm_result:
        if isinstance(llm_result, list):
            # LLM вернула несколько задач
            for task_dict in llm_result:
                if task_dict.get("confidence", 100) >= _CONFIDENCE_THRESHOLD:
                    tasks_to_create.append(task_dict)
                else:
                    logger.info(f"Задача от LLM отклонена из-за низкой confidence: {task_dict}")
        elif isinstance(llm_result, dict) and llm_result.get("confidence", 0) >= _CONFIDENCE_THRESHOLD:
            # LLM вернула одну задачу (старый формат)
            tasks_to_create.append(llm_result)
        else:
            # LLM вернула что-то непонятное или низкую уверенность
            pass

    # Если LLM не дал задач с достаточной уверенностью – fallback на regex
    if not tasks_to_create:
        regex_result = regex_parse_task(message.text, known_usernames=[])
        if regex_result.get("confidence", 0) >= _CONFIDENCE_THRESHOLD:
            tasks_to_create.append(regex_result)
            logger.info(f"🔄 Fallback на regex: confidence={regex_result['confidence']}")
        else:
            logger.info("Не удалось распознать задачу ни через LLM, ни через regex")
            return

    author_id = message.from_user.id
    created_any = False

    for parse_result in tasks_to_create:
        assignee_usernames = parse_result.get("assignees", [])
        if not assignee_usernames:
            assignee_usernames = [None]

        for assignee_username in assignee_usernames:
            responsible_id = None
            if assignee_username:
                found_id = await ensure_user_exists(assignee_username, bot, message.chat.id)
                if found_id:
                    responsible_id = found_id

            assignee_ids = [responsible_id] if responsible_id else []
            card_id = await create_yougile_task(
                title=parse_result["task"],
                description=message.text,
                deadline_str=parse_result.get("deadline"),
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
                responsible_telegram_id=responsible_id,
                author_telegram_id=author_id,
                deadline=parse_result.get("deadline"),
                deadline_timestamp=deadline_to_timestamp(parse_result.get("deadline")) if parse_result.get("deadline") else None,
                yougile_card_id=card_id,
                chat_id=message.chat.id,
            )

            # Отправка уведомлений (аналогично ранее, с учётом responsible_id = None)
            if responsible_id is None:
                keyboard = InlineKeyboardBuilder()
                keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                keyboard.adjust(1)
                await bot.send_message(
                    author_id,
                    f"📌 Вы создали задачу (без исполнителя):\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result.get('deadline') or 'не указан'}\n\n"
                    f"Вы можете взять задачу в работу или назначить исполнителя в YouGile.",
                    reply_markup=keyboard.as_markup()
                )
            elif responsible_id == author_id:
                keyboard = InlineKeyboardBuilder()
                keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                keyboard.adjust(1)
                await bot.send_message(
                    author_id,
                    f"📌 Вы создали задачу:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result.get('deadline') or 'не указан'}\n"
                    f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames[0] else 'вы'}\n\n"
                    f"Управляйте задачей:",
                    reply_markup=keyboard.as_markup()
                )
            else:
                keyboard_worker = InlineKeyboardBuilder()
                keyboard_worker.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                keyboard_worker.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                keyboard_worker.adjust(1)
                await bot.send_message(
                    responsible_id,
                    f"🔔 Вам назначена задача в группе {message.chat.title}:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result.get('deadline') or 'не указан'}\n\n"
                    f"Управляйте задачей:",
                    reply_markup=keyboard_worker.as_markup()
                )
                keyboard_author = InlineKeyboardBuilder()
                keyboard_author.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                keyboard_author.adjust(1)
                await bot.send_message(
                    author_id,
                    f"📌 Вы создали задачу для @{assignee_username}:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result.get('deadline') or 'не указан'}\n\n"
                    f"Вы можете удалить задачу, если она создана ошибочно:",
                    reply_markup=keyboard_author.as_markup()
                )
            created_any = True

    if created_any:
        reply_text = f"✅ Задача(и) автоматически созданы в YouGile!\n\n" \
                     f"📋 {tasks_to_create[0]['task']}" + \
                     (f" и ещё {len(tasks_to_create)-1}" if len(tasks_to_create) > 1 else "")
        await message.reply(reply_text)