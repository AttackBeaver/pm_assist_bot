import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class YouGileClient:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://ru.yougile.com/api-v2"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    def get_columns(self, board_id: str) -> Optional[list]:
        """Получает список колонок доски."""
        url = f"{self.base_url}/columns"
        params = {"boardId": board_id}
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            data = response.json()
            columns = data.get('content', [])
            logger.info(f"Получено колонок: {len(columns)}")
            return columns
        else:
            logger.error(
                f"Ошибка получения колонок: {response.status_code} - {response.text}")
            return None

    def create_task(self, title: str, column_id: str, description: str = "",
                    assigned_user_ids: list = None, deadline_timestamp: int = None) -> Optional[Dict]:
        """Создаёт задачу в указанной колонке."""
        payload = {
            "title": title,
            "columnId": column_id,
            "description": description,
            "archived": False,
            "completed": False,
            "assigned": assigned_user_ids or []
        }
        if deadline_timestamp:
            payload["deadline"] = {
                "deadline": deadline_timestamp,
                "withTime": True
            }

        url = f"{self.base_url}/tasks"
        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code in (200, 201):
            logger.info(f"Задача создана: {response.json()}")
            return response.json()
        else:
            logger.error(
                f"Ошибка создания задачи: {response.status_code} - {response.text}")
            return None

    def get_column_id_by_title(self, board_id: str, title: str) -> Optional[str]:
        """Возвращает ID колонки по её названию (первое совпадение)."""
        columns = self.get_columns(board_id)
        if not columns:
            return None
        for col in columns:
            if col.get('title', '').lower() == title.lower():
                return col['id']
        logger.warning(f"Колонка с названием '{title}' не найдена")
        return None

    def get_board_users(self, board_id: str) -> Optional[list]:
        """Возвращает список пользователей, имеющих доступ к доске."""
        url = f"{self.base_url}/boards/{board_id}/users"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('content', [])
        else:
            logger.error(f"Ошибка получения пользователей: {response.text}")
            return None
