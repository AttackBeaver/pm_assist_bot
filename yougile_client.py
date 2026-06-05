import requests
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15  # секунд


class YouGileClient:
    """HTTP-клиент к YouGile API v2 (https://ru.yougile.com/api-v2)."""

    BASE_URL = "https://ru.yougile.com/api-v2"

    def __init__(self, api_token: str) -> None:
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[requests.Response]:
        """Выполняет GET-запрос, возвращает Response или None при ошибке."""
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
        """Выполняет POST-запрос, возвращает Response или None при ошибке."""
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

    def get_columns(self, board_id: str) -> Optional[List[Dict[str, Any]]]:
        """Возвращает список колонок доски или None при ошибке."""
        response = self._get("/columns", params={"boardId": board_id})
        if response is None:
            return None
        if response.status_code == 200:
            columns: List[Dict[str, Any]] = response.json().get("content", [])
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
        """Создаёт задачу в указанной колонке. Возвращает данные созданной задачи или None."""
        payload: Dict[str, Any] = {
            "title": title,
            "columnId": column_id,
            "description": description,
            "archived": False,
            "completed": False,
            "assigned": assigned_user_ids or [],
        }
        if deadline_timestamp is not None:
            payload["deadline"] = {
                "deadline": deadline_timestamp,
                "withTime": True,
            }

        response = self._post("/tasks", payload)
        if response is None:
            return None
        if response.status_code in (200, 201):
            data: Dict[str, Any] = response.json()
            logger.info(f"Задача создана: id={data.get('id')}")
            return data
        logger.error(f"Ошибка создания задачи ({response.status_code}): {response.text}")
        return None

    def get_column_id_by_title(self, board_id: str, title: str) -> Optional[str]:
        """Возвращает ID первой колонки с совпадающим названием или None."""
        columns = self.get_columns(board_id)
        if not columns:
            return None
        for col in columns:
            if col.get("title", "").lower() == title.lower():
                return col["id"]
        logger.warning(f"Колонка '{title}' не найдена на доске {board_id}")
        return None

    def get_board_users(self, board_id: str) -> Optional[List[Dict[str, Any]]]:
        """Возвращает список пользователей доски или None при ошибке."""
        response = self._get(f"/boards/{board_id}/users")
        if response is None:
            return None
        if response.status_code == 200:
            return response.json().get("content", [])
        logger.error(f"Ошибка получения пользователей доски ({response.status_code}): {response.text}")
        return None
