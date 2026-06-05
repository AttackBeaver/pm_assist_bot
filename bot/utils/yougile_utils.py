"""Утилиты для работы с YouGile API (создание задач, удаление)"""
import logging
from typing import Optional

from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID, YOUGILE_TO_COLUMN_ID
from bot.utils.date_utils import deadline_to_timestamp

logger = logging.getLogger(__name__)


async def create_yougile_task(
    title: str,
    description: str,
    deadline_str: Optional[str] = None,
) -> Optional[str]:
    """Создаёт задачу в колонке «Сделать» (YOUGILE_TO_COLUMN_ID). Возвращает ID карточки или None."""
    if not YOUGILE_TOKEN or not YOUGILE_BOARD_ID:
        logger.error("YouGile не настроен")
        return None

    client = YouGileClient(YOUGILE_TOKEN)
    column_id = YOUGILE_TO_COLUMN_ID
    if not column_id:
        columns = client.get_columns(YOUGILE_BOARD_ID)
        if not columns:
            logger.error("Не удалось получить колонки YouGile")
            return None
        column_id = columns[0]["id"]  # fallback

    deadline_ts = deadline_to_timestamp(deadline_str) if deadline_str else None
    result = client.create_task(title, column_id, description, deadline_timestamp=deadline_ts)
    return result.get("id") if result else None