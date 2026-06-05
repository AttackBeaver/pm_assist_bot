import re
from datetime import datetime, timedelta
from typing import Optional

# Все возможные падежи дней недели
WEEKDAY_VARIANTS = {
    "понедельник": 0, "понедельника": 0, "понедельнику": 0, "понедельник": 0, "понедельником": 0,
    "вторник": 1, "вторника": 1, "вторнику": 1, "вторник": 1, "вторником": 1,
    "среда": 2, "среды": 2, "среде": 2, "среду": 2, "средой": 2,
    "четверг": 3, "четверга": 3, "четвергу": 3, "четверг": 3, "четвергом": 3,
    "пятница": 4, "пятницы": 4, "пятнице": 4, "пятницу": 4, "пятницей": 4,
    "суббота": 5, "субботы": 5, "субботе": 5, "субботу": 5, "субботой": 5,
    "воскресенье": 6, "воскресенья": 6, "воскресенью": 6, "воскресенье": 6, "воскресеньем": 6,
}

def parse_deadline(text: str) -> Optional[str]:
    """Ищет упоминание дедлайна в тексте, возвращает найденную подстроку."""
    text_lower = text.lower()
    # Время
    match = re.search(r'(?:до|к)\s+(\d{1,2}:\d{2})', text_lower)
    if match:
        return match.group(0)
    # Дата в формате ДД.ММ или ДД.ММ.ГГГГ
    match = re.search(r'(\d{1,2})[\.\/](\d{1,2})(?:[\.\/](\d{2,4}))?', text_lower)
    if match:
        return match.group(0)
    # "через X дней/дня"
    match = re.search(r'через\s+(\d+)\s+(день|дня|дней)', text_lower)
    if match:
        return match.group(0)
    # Относительные: сегодня, завтра, послезавтра
    match = re.search(r'\b(сегодня|завтра|послезавтра)\b', text_lower)
    if match:
        return match.group(0)
    # День недели в любом падеже (с предлогом "до"/"к" или без)
    for day_form, _ in WEEKDAY_VARIANTS.items():
        pattern = rf'(?:до|к)\s+{day_form}'
        if re.search(pattern, text_lower):
            return f"до {day_form}" if "до" in pattern else f"к {day_form}"
        if re.search(rf'\b{day_form}\b', text_lower):
            return day_form
    return None

def deadline_to_timestamp(deadline_str: str, reference_date: Optional[datetime] = None) -> Optional[int]:
    if not deadline_str:
        return None
    now = reference_date or datetime.now()
    dl = deadline_str.lower()
    result_date = None
    result_time = None

    # Время
    time_match = re.search(r'(\d{1,2}):(\d{2})', dl)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        result_time = timedelta(hours=hour, minutes=minute)

    # Абсолютная дата
    date_match = re.search(r'(\d{1,2})[\.\/](\d{1,2})(?:[\.\/](\d{2,4}))?', dl)
    if date_match:
        day, month = int(date_match.group(1)), int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else now.year
        if year < 100:
            year += 2000
        try:
            result_date = datetime(year, month, day)
            if result_date < now:
                result_date = datetime(year + 1, month, day)
        except ValueError:
            pass

    # Относительные
    if "сегодня" in dl:
        result_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif "завтра" in dl:
        result_date = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif "послезавтра" in dl:
        result_date = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        days_match = re.search(r'через\s+(\d+)\s+(день|дня|дней)', dl)
        if days_match:
            days = int(days_match.group(1))
            result_date = (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            for day_form, weekday_num in WEEKDAY_VARIANTS.items():
                if day_form in dl:
                    days_ahead = (weekday_num - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    result_date = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
                    break

    if result_date is None:
        result_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if result_time:
        final = result_date.replace(hour=result_time.seconds // 3600, minute=(result_time.seconds // 60) % 60, second=0, microsecond=0)
        if final < now and not any(x in dl for x in ['сегодня', 'завтра', 'послезавтра']):
            final += timedelta(days=1)
    else:
        final = result_date.replace(hour=23, minute=59, second=59)

    return int(final.timestamp() * 1000)