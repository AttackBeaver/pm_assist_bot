import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN не найден в .env — Telegram-бот не будет работать")

SPEECH2TEXT_API_KEY: str = os.getenv("SPEECH2TEXT_API_KEY", "")
if not SPEECH2TEXT_API_KEY:
    logger.warning("SPEECH2TEXT_API_KEY не найден в .env — распознавание речи недоступно")

YOUGILE_TOKEN: str | None = os.getenv("YOUGILE_TOKEN")
YOUGILE_BOARD_ID: str | None = os.getenv("YOUGILE_BOARD_ID")

if not YOUGILE_TOKEN:
    logger.warning("YOUGILE_TOKEN не задан — создание задач в YouGile недоступно")
if not YOUGILE_BOARD_ID:
    logger.warning("YOUGILE_BOARD_ID не задан — создание задач в YouGile недоступно")

YOUGILE_TO_COLUMN_ID: str | None = os.getenv("YOUGILE_TO_COLUMN_ID")
YOUGILE_DO_COLUMN_ID: str | None = os.getenv("YOUGILE_DO_COLUMN_ID")
YOUGILE_DONE_COLUMN_ID: str | None = os.getenv("YOUGILE_DONE_COLUMN_ID")

WEB_BASE_URL: str = os.getenv("WEB_BASE_URL", "http://localhost:8000")

YANDEX_FOLDER_ID: str | None = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY: str | None = os.getenv("YANDEX_API_KEY")

if YANDEX_FOLDER_ID and YANDEX_API_KEY:
    logger.info("✅ YandexGPT настроен — будет использоваться для распознавания задач")
else:
    logger.warning("⚠️ YandexGPT не настроен — используется только regex‑парсер")

# mymeet.ai (опционально, для автоматического подключения к встречам)
MYMEET_API_KEY: str | None = os.getenv("MYMEET_API_KEY")
MYMEET_API_URL: str = os.getenv("MYMEET_API_URL", "https://api.mymeet.ai/v1")

if MYMEET_API_KEY:
    logger.info("✅ mymeet.ai API ключ задан – будет использоваться для автоматического подключения к встречам")
else:
    logger.warning("⚠️ MYMEET_API_KEY не задан – автоматическое подключение к встречам недоступно, используйте загрузку файлов")

# yandex_telemost
YANDEX_TELEMOST_OAUTH_TOKEN: str | None = os.getenv("YANDEX_TELEMOST_OAUTH_TOKEN")
YANDEX_TELEMOST_BOT_EMAIL: str | None = os.getenv("YANDEX_TELEMOST_BOT_EMAIL")

if YANDEX_TELEMOST_OAUTH_TOKEN:
    logger.info("✅ Yandex Telemost OAuth токен задан")
else:
    logger.warning("⚠️ YANDEX_TELEMOST_OAUTH_TOKEN не задан — API интеграция недоступна")