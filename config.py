import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

SPEECH2TEXT_API_KEY: str = os.getenv("SPEECH2TEXT_API_KEY", "")
if not SPEECH2TEXT_API_KEY:
    raise ValueError("SPEECH2TEXT_API_KEY не найден в .env")

YOUGILE_TOKEN: str | None = os.getenv("YOUGILE_TOKEN")
YOUGILE_BOARD_ID: str | None = os.getenv("YOUGILE_BOARD_ID")

if not YOUGILE_TOKEN:
    logger.warning("YOUGILE_TOKEN не задан — создание задач в YouGile недоступно")
if not YOUGILE_BOARD_ID:
    logger.warning("YOUGILE_BOARD_ID не задан — создание задач в YouGile недоступно")