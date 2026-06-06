import os
import tempfile
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def extract_yadisk_direct_link(public_url: str) -> Optional[str]:
    """
    Извлекает прямую ссылку на скачивание для публичного файла на Яндекс.Диске.
    Документация: https://yandex.ru/dev/disk/rest/public/resources-download.html
    """
    if not public_url:
        return None
    # Очищаем ссылку от параметров (например, ?from=...)
    base_url = public_url.split('?')[0]
    api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    params = {"public_key": base_url}
    try:
        response = requests.get(api_url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            direct_link = data.get("href")
            if direct_link:
                logger.info(f"Получена прямая ссылка для {public_url}")
                return direct_link
            else:
                logger.error(f"Нет поля href в ответе: {data}")
                return None
        else:
            logger.error(f"Ошибка API Яндекс.Диска: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении прямой ссылки: {e}")
        return None


def download_file_from_url(download_url: str, destination_path: str) -> bool:
    """Скачивает файл по прямой ссылке."""
    try:
        response = requests.get(download_url, stream=True, timeout=60)
        if response.status_code == 200:
            with open(destination_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"Файл скачан: {destination_path}")
            return True
        else:
            logger.error(f"Ошибка скачивания: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при скачивании: {e}")
        return False