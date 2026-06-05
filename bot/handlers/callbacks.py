import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from yougile_client import YouGileClient
from config import YOUGILE_TOKEN
from web.database import get_task_by_id, delete_task

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
            delete_task(task_uuid)
            await callback.message.edit_text("⚠️ Не удалось удалить задачу в YouGile, но она удалена из локального списка.")
    else:
        delete_task(task_uuid)
        await callback.message.edit_text("❌ Задача удалена из локального списка (карточка в YouGile не найдена).")
    await callback.answer()