import re
from datetime import datetime, timedelta
from typing import Optional

# Падежные формы дней недели с предлогами "до", "к" (для поиска)
_DAYS_PREPOSITIONAL = (
    r'(?:'
    r'понедельник[уа]?|понедельником|'
    r'вторник[уа]?|вторником|'
    r'сред[уе]|средой|'
    r'четверг[уа]?|четвергом|'
    r'пятниц[уе]|пятницей|'
    r'суббот[уе]|субботой|'
    r'воскресень[ею]|воскресеньем'
    r')'
)

# Падежи для месяцев (родительный падеж)
_MONTHS_GENITIVE = r'(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)'

def parse_deadline(text: str) -> Optional[str]:
    """
    Ищет упоминание дедлайна в тексте, возвращает найденную подстроку или None.
    """
    text_lower = text.lower()
    patterns = [
        r'(?:до|к)\s+\d{1,2}:\d{2}',                                    # до 18:00
        r'(?:до|к)\s+\d{1,2}[./\-]\d{1,2}(?:[./\-]\d{2,4})?',          # до 15.06, до 15.06.2025
        rf'(?:до|к)\s+{_DAYS_PREPOSITIONAL}',                           # до пятницы, к среде
        rf'до\s+\d{{1,2}}\s+{_MONTHS_GENITIVE}',                       # до 7 июня
        r'до\s+\d{1,2}\s+числа',                                       # до 7 числа
        r'\bзавтра\b',
        r'\bпослезавтра\b',
        r'через\s+\d+\s+(?:дня|дней|часов?|неделю|недели|месяц[а]?)',  # через 2 дня
        rf'\b{_DAYS_PREPOSITIONAL}\b',                                 # пятница (без предлога)
        r'(?:в|в конце)\s+(?:январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре)', # в июле
        r'(?:до|к)\s+концу\s+(?:недели|месяца|года)',
        r'(?:на|в)\s+(?:следующей|этой|будущей|прошлой)\s+неделе',
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

    # 1. Время (часы:минуты)
    time_match = re.search(r'(\d{1,2}):(\d{2})', dl)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        result_time = timedelta(hours=hour, minutes=minute)

    # 2. Абсолютная дата в формате ДД.ММ или ДД.ММ.ГГГГ
    date_match = re.search(r'(\d{1,2})[./\-](\d{1,2})(?:[./\-](\d{2,4}))?', dl)
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
            pass

    # 3. Относительные: сегодня, завтра, послезавтра
    if "сегодня" in dl:
        result_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif "завтра" in dl:
        result_date = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif "послезавтра" in dl:
        result_date = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # "через N дней"
        days_match = re.search(r'через\s+(\d+)\s+(?:дня|дней)', dl)
        if days_match:
            days = int(days_match.group(1))
            result_date = (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # День недели (ближайший в будущем)
            weekday_map = {
                "понедельник": 0, "понедельника": 0, "понедельнику": 0, "понедельник": 0, "понедельником": 0,
                "вторник": 1, "вторника": 1, "вторнику": 1, "вторник": 1, "вторником": 1,
                "среда": 2, "среды": 2, "среде": 2, "среду": 2, "средой": 2,
                "четверг": 3, "четверга": 3, "четвергу": 3, "четверг": 3, "четвергом": 3,
                "пятница": 4, "пятницы": 4, "пятнице": 4, "пятницу": 4, "пятницей": 4,
                "суббота": 5, "субботы": 5, "субботе": 5, "субботу": 5, "субботой": 5,
                "воскресенье": 6, "воскресенья": 6, "воскресенью": 6, "воскресенье": 6, "воскресеньем": 6,
            }
            for wd, wd_num in weekday_map.items():
                if wd in dl:
                    days_ahead = (wd_num - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    result_date = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
                    break

            # Месяц без числа (например, "в июле") – принимаем первое число месяца
            if not result_date:
                month_match = re.search(r'(?:в|в конце)\s+(январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре)', dl)
                if month_match:
                    month_name = month_match.group(1)
                    month_num = {
                        "январе": 1, "феврале": 2, "марте": 3, "апреле": 4, "мае": 5, "июне": 6,
                        "июле": 7, "августе": 8, "сентябре": 9, "октябре": 10, "ноябре": 11, "декабре": 12
                    }[month_name]
                    year = now.year
                    # Если месяц уже прошёл в этом году, берём следующий год
                    if month_num < now.month:
                        year += 1
                    try:
                        result_date = datetime(year, month_num, 1)
                    except ValueError:
                        pass

    # Если дата не найдена, считаем, что дедлайн сегодня
    if result_date is None:
        result_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Комбинируем дату и время
    if result_time:
        final = result_date.replace(hour=result_time.seconds // 3600,
                                    minute=(result_time.seconds // 60) % 60,
                                    second=0, microsecond=0)
        # Если полученное время уже прошло сегодня и это не "сегодня"/"завтра", переносим на завтра
        if final < now and "сегодня" not in dl and "завтра" not in dl and "послезавтра" not in dl:
            final += timedelta(days=1)
    else:
        final = result_date.replace(hour=23, minute=59, second=59)

    return int(final.timestamp() * 1000)