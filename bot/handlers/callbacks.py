import logging
import uuid
from typing import Dict, Any, Optional

from aiogram import Router
from aiogram.types import CallbackQuery

from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID
from bot.utils.date_utils import deadline_to_timestamp
from web.database import add_task
from bot.handlers.message_handler import pending_text_tasks
from bot.handlers.voice_handler import pending_tasks

logger = logging.getLogger(__name__)
router = Router()


async def _create_yougile_task(
    title: str,
    description: str,
    deadline_str: Optional[str] = None,
) -> Optional[str]:
    """Создаёт задачу в первой колонке доски YouGile. Возвращает ID карточки или None."""
    if not YOUGILE_TOKEN or not YOUGILE_BOARD_ID:
        logger.error("YouGile не настроен: отсутствует YOUGILE_TOKEN или YOUGILE_BOARD_ID")
        return None

    client = YouGileClient(YOUGILE_TOKEN)
    columns = client.get_columns(YOUGILE_BOARD_ID)
    if not columns:
        logger.error("Не удалось получить колонки YouGile")
        return None

    column_id: str = columns[0]["id"]
    deadline_ts = deadline_to_timestamp(deadline_str) if deadline_str else None
    result = client.create_task(title, column_id, description, deadline_timestamp=deadline_ts)
    return result.get("id") if result else None


async def _handle_confirm(
    callback: CallbackQuery,
    task_data: Dict[str, Any],
    responsible_id: int,
    chat_id: int,
) -> None:
    """Общая логика подтверждения: создаёт задачу в YouGile и сохраняет в БД."""
    card_id = await _create_yougile_task(
        title=task_data["title"],
        description=task_data["description"],
        deadline_str=task_data["deadline_str"],
    )
    if card_id:
        add_task(
            task_id=str(uuid.uuid4()),
            title=task_data["title"],
            description=task_data["description"],
            responsible_telegram_id=responsible_id,
            deadline=task_data["deadline_str"],
            deadline_timestamp=(
                deadline_to_timestamp(task_data["deadline_str"])
                if task_data["deadline_str"]
                else None
            ),
            yougile_card_id=card_id,
            chat_id=chat_id,
        )
        await callback.message.edit_text(
            f"✅ Задача создана в YouGile\\!\n\n"
            f"*Название:* {task_data['title']}\n"
            f"*Дедлайн:* {task_data['deadline_str'] or 'не указан'}\n"
            f"*ID карточки:* `{card_id}`"
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось создать задачу в YouGile\\. Проверьте настройки интеграции\\."
        )


# ── Текстовые задачи ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data.startswith("confirm_text_"))
async def confirm_text_task(callback: CallbackQuery) -> None:
    callback_id = callback.data.removeprefix("confirm_text_")
    task_data = pending_text_tasks.get(callback_id)
    if not task_data:
        await callback.answer("Задача уже обработана", show_alert=True)
        await callback.message.delete()
        return

    await _handle_confirm(
        callback,
        task_data,
        responsible_id=task_data["from_user_id"],
        chat_id=task_data["chat_id"],
    )
    pending_text_tasks.pop(callback_id, None)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("cancel_text_"))
async def cancel_text_task(callback: CallbackQuery) -> None:
    pending_text_tasks.pop(callback.data.removeprefix("cancel_text_"), None)
    await callback.message.edit_text("❌ Создание задачи отменено\\.")
    await callback.answer()


# ── Голосовые задачи ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data.startswith("confirm_voice_"))
async def confirm_voice_task(callback: CallbackQuery) -> None:
    callback_id = callback.data.removeprefix("confirm_voice_")
    task_data = pending_tasks.get(callback_id)
    if not task_data:
        await callback.answer("Задача уже обработана", show_alert=True)
        await callback.message.delete()
        return

    await _handle_confirm(
        callback,
        task_data,
        responsible_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
    )
    pending_tasks.pop(callback_id, None)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("cancel_voice_"))
async def cancel_voice_task(callback: CallbackQuery) -> None:
    pending_tasks.pop(callback.data.removeprefix("cancel_voice_"), None)
    await callback.message.edit_text("❌ Создание задачи отменено\\.")
    await callback.answer()