import re
from datetime import datetime, timedelta
from typing import Optional

# Сопоставление названий дней недели (именительный падеж)
WEEKDAYS_RU = {
    "понедельник": 0,
    "вторник": 1,
    "среду": 2,   # винительный падеж тоже распознаём
    "среда": 2,
    "четверг": 3,
    "пятницу": 4,
    "пятница": 4,
    "субботу": 5,
    "суббота": 5,
    "воскресенье": 6,
    "воскресенья": 6,
}

def parse_deadline(text: str) -> Optional[str]:
    """
    Возвращает найденную в тексте подстроку, обозначающую дедлайн,
    или None, если ничего не найдено.
    """
    text_lower = text.lower()
    # Паттерны в порядке приоритета
    patterns = [
        r'(?:до|к)\s+(\d{1,2}:\d{2})',                     # до 18:00
        r'(\d{1,2})[\.\/](\d{1,2})(?:[\.\/](\d{2,4}))?', # 15.06, 15.06.2025
        r'через\s+(\d+)\s+дней?',                         # через 2 дня
        r'\b(сегодня|завтра|послезавтра)\b',
        r'\b(понедельник|вторник|среду|среда|четверг|пятницу|пятница|субботу|суббота|воскресенье|воскресенья)\b',
    ]
    for pat in patterns:
        match = re.search(pat, text_lower)
        if match:
            return match.group(0)
    return None

def deadline_to_timestamp(deadline_str: str, reference_date: Optional[datetime] = None) -> Optional[int]:
    """
    Преобразует строку дедлайна в Unix timestamp (миллисекунды).
    """
    if not deadline_str:
        return None

    now = reference_date or datetime.now()
    dl = deadline_str.lower()
    result_date = None
    result_time = None

    # 1) Время вида HH:MM
    time_match = re.search(r'(\d{1,2}):(\d{2})', dl)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        result_time = timedelta(hours=hour, minutes=minute)

    # 2) Дата в формате ДД.ММ или ДД.ММ.ГГГГ
    date_match = re.search(r'(\d{1,2})[\.\/](\d{1,2})(?:[\.\/](\d{2,4}))?', dl)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else now.year
        if year < 100:
            year += 2000
        try:
            result_date = datetime(year, month, day)
            if result_date < now:
                result_date = datetime(year + 1, month, day)
        except ValueError:
            result_date = None

    # 3) Относительные: сегодня, завтра, послезавтра
    if "сегодня" in dl:
        result_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif "завтра" in dl:
        result_date = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif "послезавтра" in dl:
        result_date = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    # 4) "через N дней"
    days_match = re.search(r'через\s+(\d+)\s+дней?', dl)
    if days_match:
        days = int(days_match.group(1))
        result_date = (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

    # 5) День недели (ближайший в будущем)
    for weekday_ru, weekday_num in WEEKDAYS_RU.items():
        if weekday_ru in dl:
            days_ahead = (weekday_num - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            result_date = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
            break

    # Комбинируем дату и время
    if result_date is None:
        # Если дата не найдена, считаем, что дедлайн сегодня
        result_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if result_time is not None:
        final_dt = result_date.replace(hour=result_time.seconds//3600,
                                       minute=(result_time.seconds//60)%60,
                                       second=0, microsecond=0)
        # Если получившееся время уже прошло сегодня, переносим на завтра
        if final_dt < now and "сегодня" not in dl and "завтра" not in dl and "послезавтра" not in dl:
            final_dt += timedelta(days=1)
    else:
        final_dt = result_date.replace(hour=23, minute=59, second=59)

    return int(final_dt.timestamp() * 1000)