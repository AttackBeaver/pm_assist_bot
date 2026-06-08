import json
import logging
import re
import requests
from typing import Optional, Dict, Any, List

from config import YANDEX_FOLDER_ID, YANDEX_API_KEY
from bot.utils.parser import _TASK_KEYWORDS, _STOP_WORDS

logger = logging.getLogger(__name__)


class YandexGPTClient:
    def __init__(self, folder_id: str, api_key: str):
        self.folder_id = folder_id
        self.api_key = api_key
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def generate_text(self, prompt: str, system_prompt: str = None, temperature: float = 0.3) -> Optional[str]:
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "text": system_prompt})
        messages.append({"role": "user", "text": prompt})

        payload = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite/latest",
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": 500,
            },
            "messages": messages,
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
            if response.status_code != 200:
                logger.error(f"Ошибка YandexGPT API: {response.status_code} - {response.text}")
                return None
            data = response.json()
            result = data.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text")
            return result
        except Exception as e:
            logger.error(f"Исключение при запросе YandexGPT: {e}")
            return None


_client = None


def get_client():
    global _client
    if _client is None and YANDEX_FOLDER_ID and YANDEX_API_KEY:
        _client = YandexGPTClient(YANDEX_FOLDER_ID, YANDEX_API_KEY)
    return _client


def parse_task_with_llm(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Возвращает список задач (каждая задача – словарь с ключами task, deadline, assignees)
    или None, если ничего не найдено.
    """
    client = get_client()
    if not client:
        return None

    system_prompt = """
Ты — ассистент по управлению задачами. Из текста сообщения извлеки **все задачи**, дедлайны и ответственных.
Правила:
- Задача должна содержать **глагол действия**: сделать, подготовить, написать, обновить, проверить, отправить, создать, организовать, купить, заказать и т.п.
- Если в сообщении нет глагола действия, нет @упоминания, нет указания на срок → верни null.
- Игнорируй вопросы, уточнения, бытовые фразы.
- Если в тексте несколько задач, верни массив объектов.
- Для каждой задачи извлеки:
   * task: краткая формулировка
   * deadline: дата/время в понятном формате (если есть)
   * assignees: список username (без @)
- Ответ должен быть ТОЛЬКО в формате JSON. Если задач несколько, верни список. Если задача одна, можно вернуть объект (не список).
"""
    prompt = f"Пользователь: {text}"
    response = client.generate_text(prompt, system_prompt=system_prompt)
    if not response:
        return None

    try:
        clean = response.strip().strip('```json').strip('```').strip()
        data = json.loads(clean)

        # Приводим к списку
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not data:
            return None

        tasks = []
        for item in data:
            task = item.get("task")
            deadline = item.get("deadline")
            assignees = item.get("assignees") or []
            if not isinstance(assignees, list):
                assignees = [assignees] if assignees else []

            # Пост-валидация
            if not task or len(task.strip()) < 4:
                continue

            lower_text = text.lower()
            has_stopword = any(re.search(rf'\b{re.escape(sw)}\b', lower_text) for sw in _STOP_WORDS)
            if has_stopword:
                continue

            tasks.append({
                "task": task,
                "deadline": deadline,
                "assignees": assignees,
                "confidence": 95,
            })
        return tasks if tasks else None
    except Exception as e:
        logger.error(f"Ошибка парсинга JSON из LLM: {e}\nОтвет: {response}")
        return None


def summarize_text(text: str) -> Optional[str]:
    client = get_client()
    if not client:
        return None
    prompt = f"Сделай краткое саммари (3-5 предложений) следующего текста встречи:\n\n{text}"
    system_prompt = "Ты — ассистент, пишущий саммари. Ответ должен быть только текст саммари, без лишних слов."
    response = client.generate_text(prompt, system_prompt=system_prompt, temperature=0.3)
    if response:
        return response.strip()
    return None