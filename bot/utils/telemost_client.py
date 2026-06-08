import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TelemostClient:
    BASE_URL = "https://cloud-api.yandex.net/v1/telemost-api"

    def __init__(self, oauth_token: str):
        self.oauth_token = oauth_token
        self.headers = {
            "Authorization": f"OAuth {oauth_token}",
            "Content-Type": "application/json",
        }

    def create_conference(self, title: str = "Встреча PM Assist", 
                         is_auto_summarization_enabled: bool = True,
                         cohosts_emails: list = None) -> Optional[Dict[str, Any]]:
        """Создаёт встречу с автоматической записью и расшифровкой."""
        url = f"{self.BASE_URL}/conferences"
        payload = {
            "title": title,
            "is_auto_summarization_enabled": is_auto_summarization_enabled,
        }
        if cohosts_emails:
            payload["cohosts"] = [{"email": email} for email in cohosts_emails]

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            if response.status_code == 201:
                data = response.json()
                logger.info(f"Встреча создана: {data.get('id')}, ссылка: {data.get('join_link')}")
                return data
            else:
                logger.error(f"Ошибка создания встречи: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Исключение при создании встречи: {e}")
            return None

    def add_cohost(self, conference_id: str, email: str) -> bool:
        """Добавляет соорганизатора по email."""
        url = f"{self.BASE_URL}/conferences/{conference_id}/cohosts"
        payload = {"cohosts": [{"email": email}]}
        try:
            response = requests.patch(url, headers=self.headers, json=payload, timeout=30)
            if response.status_code == 200:
                logger.info(f"Пользователь {email} добавлен как соорганизатор встречи {conference_id}")
                return True
            else:
                logger.error(f"Ошибка добавления соорганизатора: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Исключение: {e}")
            return False

    def enable_summarization(self, conference_id: str) -> bool:
        """Включает автоматическую запись/расшифровку встречи."""
        url = f"{self.BASE_URL}/conferences/{conference_id}"
        payload = {"is_auto_summarization_enabled": True}
        try:
            response = requests.patch(url, headers=self.headers, json=payload, timeout=30)
            if response.status_code == 200:
                logger.info(f"Авторасшифровка включена для встречи {conference_id}")
                return True
            else:
                logger.error(f"Ошибка включения расшифровки: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Исключение: {e}")
            return False

    def get_conference(self, conference_id: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о встрече (в т.ч. ссылку на результат расшифровки, если есть)."""
        url = f"{self.BASE_URL}/conferences/{conference_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ошибка получения информации: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Исключение: {e}")
            return None