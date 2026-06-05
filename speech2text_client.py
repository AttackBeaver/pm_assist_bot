import requests
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 30  # секунд


class Speech2TextClient:
    """HTTP-клиент к API speech2text.ru для распознавания речи."""

    BASE_URL = "https://speech2text.ru/api/recognitions"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def send_file(self, file_path: str, lang: str = "ru") -> Optional[str]:
        """Отправляет аудиофайл на распознавание, возвращает task_id или None."""
        url = f"{self.BASE_URL}/task/file?api-key={self.api_key}"
        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    url,
                    files={"file": f},
                    data={"lang": lang},
                    timeout=_HTTP_TIMEOUT,
                )
        except OSError as e:
            logger.error(f"Не удалось открыть файл {file_path}: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"Ошибка HTTP при отправке файла: {e}")
            return None

        if response.status_code in (200, 201):
            task_id: Optional[str] = response.json().get("id")
            logger.info(f"Файл отправлен, task_id={task_id}")
            return task_id

        logger.error(f"Ошибка отправки ({response.status_code}): {response.text}")
        return None

    def is_task_complete(self, task_id: str) -> bool:
        """Возвращает True, если задача распознавания завершена успешно."""
        url = f"{self.BASE_URL}/{task_id}?api-key={self.api_key}"
        try:
            response = requests.get(url, timeout=_HTTP_TIMEOUT)
        except requests.RequestException as e:
            logger.error(f"Ошибка HTTP при проверке статуса задачи {task_id}: {e}")
            return False

        if response.status_code != 200:
            logger.error(f"Ошибка проверки статуса ({response.status_code}): {response.text}")
            return False

        status_code = response.json().get("status", {}).get("code")
        return status_code == 200

    def get_result(self, task_id: str, result_format: str = "txt") -> Optional[str]:
        """Получает результат распознавания в указанном формате."""
        url = f"{self.BASE_URL}/{task_id}/result/{result_format}?api-key={self.api_key}"
        try:
            response = requests.get(url, timeout=_HTTP_TIMEOUT)
        except requests.RequestException as e:
            logger.error(f"Ошибка HTTP при получении результата задачи {task_id}: {e}")
            return None

        if response.status_code == 200:
            logger.info(f"Результат для задачи {task_id} получен")
            return response.text

        logger.error(f"Ошибка получения результата ({response.status_code}): {response.text}")
        return None

    def wait_and_get_result(
        self,
        task_id: str,
        result_format: str = "txt",
        poll_interval: int = 5,
        timeout: int = 300,
    ) -> Optional[str]:
        """Ждёт завершения задачи и возвращает результат. При таймауте возвращает None."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_task_complete(task_id):
                return self.get_result(task_id, result_format)
            time.sleep(poll_interval)
        logger.warning(f"Таймаут ожидания задачи {task_id} ({timeout}с)")
        return None
