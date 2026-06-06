import logging
import uuid
from typing import Optional

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, WEB_BASE_URL, YOUGILE_DO_COLUMN_ID, YOUGILE_DONE_COLUMN_ID
from web.database import get_task_by_id, delete_task, complete_task

logger = logging.getLogger(__name__)
router = Router()


def _cabinet_button(telegram_id: int) -> Optional[InlineKeyboardMarkup]:
    if "localhost" in WEB_BASE_URL or "127.0.0.1" in WEB_BASE_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Открыть личный кабинет", url=f"{WEB_BASE_URL}/cabinet/{telegram_id}")
    ]])


# ---------- Отмена задачи (удаление) ----------
@router.callback_query(lambda c: c.data.startswith("cancel_task_"))
async def cancel_task_callback(callback: CallbackQuery):
    task_uuid = callback.data.removeprefix("cancel_task_")
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
            delete_task(task_uuid)
            await callback.message.edit_text("⚠️ Не удалось удалить задачу в YouGile, но она удалена из локального списка.")
    else:
        delete_task(task_uuid)
        await callback.message.edit_text("❌ Задача удалена из локального списка (карточка в YouGile не найдена).")
    await callback.answer()


# ---------- Управление задачами из списка "Мои задачи" ----------
@router.callback_query(lambda c: c.data.startswith("manage_task_"))
async def manage_task_callback(callback: CallbackQuery):
    task_id = callback.data.removeprefix("manage_task_")
    task = get_task_by_id(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        await callback.message.delete()
        return

    user_id = callback.from_user.id
    author_id = task.get("author_telegram_id")
    responsible_id = task.get("responsible_telegram_id")

    builder = InlineKeyboardBuilder()
    # Удаление доступно только автору
    if user_id == author_id:
        builder.button(text="❌ Удалить", callback_data=f"cancel_task_{task_id}")
    # Кнопки "Взять в работу" и "Завершить" – автору и ответственному
    if user_id == author_id or user_id == responsible_id:
        builder.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_id}")
        builder.button(text="✅ Завершить", callback_data=f"complete_task_{task_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📋 **{task['title']}**\n"
        f"📅 Дедлайн: {task['deadline'] or 'не указан'}\n"
        f"🟢 Статус: {task['status']}\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


# ---------- Перемещение в колонку "В процессе" ----------
@router.callback_query(lambda c: c.data.startswith("move_to_do_"))
async def move_to_do_callback(callback: CallbackQuery):
    task_id = callback.data.removeprefix("move_to_do_")
    task = get_task_by_id(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    yougile_card_id = task.get("yougile_card_id")
    if yougile_card_id and YOUGILE_TOKEN and YOUGILE_DO_COLUMN_ID:
        client = YouGileClient(YOUGILE_TOKEN)
        success = client.move_task(yougile_card_id, YOUGILE_DO_COLUMN_ID)
        if success:
            await callback.answer("Задача перемещена в колонку «В процессе»")
            await callback.message.edit_text("✅ Задача перемещена в работу!")
        else:
            await callback.answer("Ошибка перемещения", show_alert=True)
    else:
        await callback.answer("Не удалось переместить задачу", show_alert=True)


# ---------- Завершение задачи (перемещение в "Готово") ----------
@router.callback_query(lambda c: c.data.startswith("complete_task_"))
async def complete_task_callback(callback: CallbackQuery):
    task_id = callback.data.removeprefix("complete_task_")
    task = get_task_by_id(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    yougile_card_id = task.get("yougile_card_id")
    if yougile_card_id and YOUGILE_TOKEN and YOUGILE_DONE_COLUMN_ID:
        client = YouGileClient(YOUGILE_TOKEN)
        success = client.move_task(yougile_card_id, YOUGILE_DONE_COLUMN_ID)
        if success:
            complete_task(task_id)
            await callback.answer("Задача завершена!")
            await callback.message.edit_text("✅ Задача выполнена и перемещена в «Готово»")
        else:
            await callback.answer("Ошибка завершения", show_alert=True)
    else:
        await callback.answer("Не удалось завершить задачу", show_alert=True)