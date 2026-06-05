"""
Интеграционный тест: получение колонок доски YouGile.
Требует заполненных YOUGILE_TOKEN и YOUGILE_BOARD_ID в .env.
Запуск: python qa/test_yougile.py
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID
from yougile_client import YouGileClient

if not YOUGILE_TOKEN or not YOUGILE_BOARD_ID:
    print("❌ YOUGILE_TOKEN или YOUGILE_BOARD_ID не заданы в .env")
    sys.exit(1)

client = YouGileClient(YOUGILE_TOKEN)
columns = client.get_columns(YOUGILE_BOARD_ID)
if columns:
    print(f"✅ Найдено колонок: {len(columns)}")
    for col in columns:
        print(f"  • {col['title']}  (id: {col['id']})")
else:
    print("❌ Не удалось получить колонки. Проверьте YOUGILE_TOKEN и YOUGILE_BOARD_ID.")
    sys.exit(1)