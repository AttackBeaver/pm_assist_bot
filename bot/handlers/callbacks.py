import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from yougile_client import YouGileClient
from config import YOUGILE_TOKEN
from web.database import complete_task, get_task_by_id, delete_task

logger = logging.getLogger(__name__)
router = Router()

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
            # Если YouGile не удалилось, всё равно удаляем локально
            delete_task(task_uuid)
            await callback.message.edit_text("⚠️ Не удалось удалить задачу в YouGile, но она удалена из локального списка.")
    else:
        delete_task(task_uuid)
        await callback.message.edit_text("❌ Задача удалена из локального списка (карточка в YouGile не найдена).")
    await callback.answer()

# Добавить в конец файла callbacks.py

@router.callback_query(lambda c: c.data.startswith("move_to_do_"))
async def move_to_in_progress(callback: CallbackQuery):
    task_uuid = callback.data.removeprefix("move_to_do_")
    task = get_task_by_id(task_uuid)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    yougile_card_id = task.get("yougile_card_id")
    if yougile_card_id and YOUGILE_TOKEN:
        from config import YOUGILE_DO_COLUMN_ID
        client = YouGileClient(YOUGILE_TOKEN)
        if YOUGILE_DO_COLUMN_ID:
            success = client.move_task(yougile_card_id, YOUGILE_DO_COLUMN_ID)
            if success:
                await callback.message.edit_text("🟡 Задача перемещена в колонку «В процессе».")
            else:
                await callback.message.edit_text("⚠️ Не удалось переместить задачу.")
        else:
            await callback.message.edit_text("⚠️ Не указан ID колонки «В процессе» в .env")
    else:
        await callback.message.edit_text("⚠️ Нет связи с YouGile.")
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("complete_task_"))
async def complete_task_callback(callback: CallbackQuery):
    task_uuid = callback.data.removeprefix("complete_task_")
    task = get_task_by_id(task_uuid)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    yougile_card_id = task.get("yougile_card_id")
    if yougile_card_id and YOUGILE_TOKEN:
        from config import YOUGILE_DONE_COLUMN_ID
        client = YouGileClient(YOUGILE_TOKEN)
        if YOUGILE_DONE_COLUMN_ID:
            success = client.move_task(yougile_card_id, YOUGILE_DONE_COLUMN_ID)
            if success:
                complete_task(task_uuid)  # локальное обновление
                await callback.message.edit_text("✅ Задача завершена и перемещена в «Готово».")
            else:
                await callback.message.edit_text("⚠️ Не удалось завершить задачу.")
        else:
            await callback.message.edit_text("⚠️ Не указан ID колонки «Готово» в .env")
    else:
        complete_task(task_uuid)  # хотя бы локально
        await callback.message.edit_text("✅ Задача отмечена выполненной локально (YouGile не настроен).")
    await callback.answer()