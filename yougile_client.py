import requests
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15


class YouGileClient:
    BASE_URL = "https://ru.yougile.com/api-v2"

    def __init__(self, api_token: str) -> None:
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[requests.Response]:
        try:
            return requests.get(
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                params=params,
                timeout=_HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error(f"GET {path} — ошибка сети: {e}")
            return None

    def _post(self, path: str, payload: Dict[str, Any]) -> Optional[requests.Response]:
        try:
            return requests.post(
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                json=payload,
                timeout=_HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error(f"POST {path} — ошибка сети: {e}")
            return None

    def _patch(self, path: str, payload: Dict[str, Any]) -> Optional[requests.Response]:
        """PATCH-запрос для обновления задачи (перемещение, изменение полей)."""
        try:
            return requests.patch(
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                json=payload,
                timeout=_HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error(f"PATCH {path} — ошибка сети: {e}")
            return None

    def get_columns(self, board_id: str) -> Optional[List[Dict[str, Any]]]:
        response = self._get("/columns", params={"boardId": board_id})
        if response is None:
            return None
        if response.status_code == 200:
            columns = response.json().get("content", [])
            logger.info(f"Получено колонок: {len(columns)}")
            return columns
        logger.error(f"Ошибка получения колонок ({response.status_code}): {response.text}")
        return None

    def create_task(
        self,
        title: str,
        column_id: str,
        description: str = "",
        assigned_user_ids: Optional[List[str]] = None,
        deadline_timestamp: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = {
            "title": title,
            "columnId": column_id,
            "description": description,
            "archived": False,
            "completed": False,
            "assigned": assigned_user_ids or [],
        }
        if deadline_timestamp is not None:
            payload["deadline"] = {"deadline": deadline_timestamp, "withTime": True}

        response = self._post("/tasks", payload)
        if response is None:
            return None
        if response.status_code in (200, 201):
            data = response.json()
            logger.info(f"Задача создана: id={data.get('id')}")
            return data
        logger.error(f"Ошибка создания задачи ({response.status_code}): {response.text}")
        return None

    def move_task(self, card_id: str, new_column_id: str) -> bool:
        """Перемещает задачу в другую колонку (используя PUT /tasks/{id})."""
        url = f"{self.BASE_URL}/tasks/{card_id}"
        payload = {"columnId": new_column_id}
        try:
            response = requests.put(url, headers=self.headers, json=payload, timeout=_HTTP_TIMEOUT)
            if response.status_code == 200:
                logger.info(f"Задача {card_id} перемещена в колонку {new_column_id}")
                return True
            logger.error(f"Ошибка перемещения задачи ({response.status_code}): {response.text}")
            return False
        except requests.RequestException as e:
            logger.error(f"Ошибка сети при перемещении задачи: {e}")
            return False
    
    def delete_task(self, card_id: str) -> bool:
        url = f"{self.BASE_URL}/tasks/{card_id}"
        payload = {"deleted": True}
        try:
            response = requests.put(url, headers=self.headers, json=payload, timeout=_HTTP_TIMEOUT)
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Ошибка при удалении задачи {card_id}: {e}")
            return False

    def get_column_id_by_title(self, board_id: str, title: str) -> Optional[str]:
        columns = self.get_columns(board_id)
        if not columns:
            return None
        for col in columns:
            if col.get("title", "").lower() == title.lower():
                return col["id"]
        logger.warning(f"Колонка '{title}' не найдена на доске {board_id}")
        return None

    def get_board_users(self, board_id: str) -> Optional[List[Dict[str, Any]]]:
        response = self._get(f"/boards/{board_id}/users")
        if response is None:
            return None
        if response.status_code == 200:
            return response.json().get("content", [])
        logger.error(f"Ошибка получения пользователей доски ({response.status_code}): {response.text}")
        return None
    
