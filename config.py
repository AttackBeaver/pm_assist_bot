import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

SPEECH2TEXT_API_KEY = os.getenv("SPEECH2TEXT_API_KEY")
if not SPEECH2TEXT_API_KEY:
    raise ValueError("SPEECH2TEXT_API_KEY не найден в .env")

YOUGILE_TOKEN = os.getenv("YOUGILE_TOKEN")
YOUGILE_BOARD_ID = os.getenv("YOUGILE_BOARD_ID")