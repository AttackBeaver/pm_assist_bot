from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID

client = YouGileClient(YOUGILE_TOKEN)
columns = client.get_columns(YOUGILE_BOARD_ID)
if columns:
    print("Колонки:")
    for col in columns:
        print(f"  {col['title']} (id: {col['id']})")
else:
    print("Не удалось получить колонки. Проверь ID доски и токен.")