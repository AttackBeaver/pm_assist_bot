import logging
import uuid
from typing import Dict, Any, Optional

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID, YOUGILE_TO_COLUMN_ID, WEB_BASE_URL
from bot.utils.date_utils import deadline_to_timestamp
from web.database import add_task
from bot.handlers.message_handler import pending_text_tasks
from bot.handlers.voice_handler import pending_tasks
logger = logging.getLogger(__name__)
router = Router()


def _cabinet_button(telegram_id: int) -> Optional[InlineKeyboardMarkup]:
    """Inline-кнопка перехода в личный кабинет.
    Возвращает None если URL локальный (Telegram не принимает localhost)."""
    if "localhost" in WEB_BASE_URL or "127.0.0.1" in WEB_BASE_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🌐 Открыть личный кабинет",
            url=f"{WEB_BASE_URL}/cabinet/{telegram_id}",
        )
    ]])

async def _create_yougile_task(title, description, deadline_str=None):
    if not YOUGILE_TOKEN or not YOUGILE_BOARD_ID:
        logger.error("YouGile не настроен")
        return None

    client = YouGileClient(YOUGILE_TOKEN)
    
    # Используем ID колонки "Сделать" из .env
    column_id = YOUGILE_TO_COLUMN_ID
    if not column_id:
        # fallback: первая колонка
        columns = client.get_columns(YOUGILE_BOARD_ID)
        if not columns:
            return None
        column_id = columns[0]["id"]
    
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
            f"✅ Задача создана в YouGile!\n\n"
            f"📋 Название: {task_data['title']}\n"
            f"⏰ Дедлайн: {task_data['deadline_str'] or 'не указан'}\n"
            f"🔗 ID карточки: {card_id}",
            reply_markup=_cabinet_button(responsible_id),
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось создать задачу в YouGile. Проверьте настройки интеграции."
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
    await callback.message.edit_text("❌ Создание задачи отменено.")
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

@router.callback_query(lambda c: c.data.startswith("cancel_task_"))
async def cancel_task_callback(callback: CallbackQuery):
    task_uuid = callback.data.removeprefix("cancel_task_")
    from web.database import get_task_by_id, delete_task
    from yougile_client import YouGileClient
    from config import YOUGILE_TOKEN

    task = get_task_by_id(task_uuid)
    if not task:
        await callback.answer("Задача уже удалена или не найдена", show_alert=True)
        await callback.message.delete()
        return

    yougile_card_id = task.get("yougile_card_id")
    if yougile_card_id and YOUGILE_TOKEN:
        client = YouGileClient(YOUGILE_TOKEN)
        success = client.delete_task(yougile_card_id)
        if success:
            delete_task(task_uuid)
            await callback.message.edit_text("❌ Задача удалена из YouGile и из вашего списка.")
        else:
            # Если YouGile не удалилось, всё равно удаляем локально
            delete_task(task_uuid)
            await callback.message.edit_text("⚠️ Не удалось удалить задачу в YouGile, но она удалена из локального списка.")
    else:
        delete_task(task_uuid)
        await callback.message.edit_text("❌ Задача удалена из локального списка (карточка в YouGile не найдена).")
    await callback.answer()