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

# ID колонок YouGile (можно задать в .env)
YOUGILE_TO_COLUMN_ID: str | None = os.getenv("YOUGILE_TO_COLUMN_ID")      # колонка "Сделать"
YOUGILE_DO_COLUMN_ID: str | None = os.getenv("YOUGILE_DO_COLUMN_ID")      # колонка "В процессе"
YOUGILE_DONE_COLUMN_ID: str | None = os.getenv("YOUGILE_DONE_COLUMN_ID")  # колонка "Готово"

# URL веб-кабинета
WEB_BASE_URL: str = os.getenv("WEB_BASE_URL", "http://localhost:8000")

# YandexGPT
YANDEX_FOLDER_ID: str | None = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY: str | None = os.getenv("YANDEX_API_KEY")

if YANDEX_FOLDER_ID and YANDEX_API_KEY:
    logger.info("✅ YandexGPT настроен — будет использоваться для распознавания задач")
else:
    logger.warning("⚠️ YandexGPT не настроен — используется только regex‑парсер")