# bot/handlers/callbacks.py
import logging
import uuid
from aiogram import Router, F
from aiogram.types import CallbackQuery

from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID
from bot.utils.date_utils import deadline_to_timestamp
from web.database import add_task

from bot.handlers.message_handler import pending_text_tasks
from bot.handlers.voice_handler import pending_tasks

logger = logging.getLogger(__name__)
router = Router()

def get_yougile_client():
    return YouGileClient(YOUGILE_TOKEN)

async def create_yougile_task(title: str, description: str, deadline_str: str = None) -> str | None:
    client = get_yougile_client()
    columns = client.get_columns(YOUGILE_BOARD_ID)
    if not columns:
        logger.error("Не удалось получить колонки YouGile")
        return None
    column_id = columns[0]['id']
    deadline_ts = deadline_to_timestamp(deadline_str) if deadline_str else None
    result = client.create_task(title, column_id, description, deadline_timestamp=deadline_ts)
    if result:
        return result.get('id')
    return None

# ---- Callback для текстовых задач ----
@router.callback_query(lambda c: c.data.startswith("confirm_text_"))
async def confirm_text_task(callback: CallbackQuery):
    callback_id = callback.data.replace("confirm_text_", "")
    task_data = pending_text_tasks.get(callback_id)
    if not task_data:
        await callback.answer("Задача уже обработана", show_alert=True)
        await callback.message.delete()
        return
    
    card_id = await create_yougile_task(
        title=task_data['title'],
        description=task_data['description'],
        deadline_str=task_data['deadline_str']
    )
    if card_id:
        # Генерируем уникальный ID для локальной задачи
        local_task_id = str(uuid.uuid4())
        add_task(
            task_id=local_task_id,
            title=task_data['title'],
            description=task_data['description'],
            responsible_telegram_id=task_data['from_user_id'],
            deadline=task_data['deadline_str'],
            deadline_timestamp=deadline_to_timestamp(task_data['deadline_str']) if task_data['deadline_str'] else None,
            yougile_card_id=card_id,
            chat_id=task_data['chat_id']
        )
        await callback.message.edit_text(
            f"✅ Задача создана в YouGile!\n\n"
            f"**Название:** {task_data['title']}\n"
            f"**Дедлайн:** {task_data['deadline_str'] or 'не указан'}\n"
            f"ID карточки: {card_id}"
        )
    else:
        await callback.message.edit_text("❌ Ошибка при создании задачи в YouGile.")
    
    del pending_text_tasks[callback_id]
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("cancel_text_"))
async def cancel_text_task(callback: CallbackQuery):
    callback_id = callback.data.replace("cancel_text_", "")
    pending_text_tasks.pop(callback_id, None)
    await callback.message.edit_text("❌ Создание задачи отменено.")
    await callback.answer()

# ---- Callback для голосовых задач ----
@router.callback_query(lambda c: c.data.startswith("confirm_voice_"))
async def confirm_voice_task(callback: CallbackQuery):
    callback_id = callback.data.replace("confirm_voice_", "")
    task_data = pending_tasks.get(callback_id)
    if not task_data:
        await callback.answer("Задача уже обработана", show_alert=True)
        await callback.message.delete()
        return
    card_id = await create_yougile_task(
        title=task_data['title'],
        description=task_data['description'],
        deadline_str=task_data['deadline_str']
    )
    if card_id:
        local_task_id = str(uuid.uuid4())
        add_task(
            task_id=local_task_id,
            title=task_data['title'],
            description=task_data['description'],
            responsible_telegram_id=callback.from_user.id,
            deadline=task_data['deadline_str'],
            deadline_timestamp=deadline_to_timestamp(task_data['deadline_str']) if task_data['deadline_str'] else None,
            yougile_card_id=card_id,
            chat_id=callback.message.chat.id
        )
        await callback.message.edit_text(
            f"✅ Задача создана в YouGile!\n\n"
            f"**Название:** {task_data['title']}\n"
            f"**Дедлайн:** {task_data['deadline_str'] or 'не указан'}\n"
            f"ID карточки: {card_id}"
        )
    else:
        await callback.message.edit_text("❌ Ошибка при создании задачи.")
    del pending_tasks[callback_id]
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("cancel_voice_"))
async def cancel_voice_task(callback: CallbackQuery):
    callback_id = callback.data.replace("cancel_voice_", "")
    pending_tasks.pop(callback_id, None)
    await callback.message.edit_text("❌ Создание задачи отменено.")
    await callback.answer()