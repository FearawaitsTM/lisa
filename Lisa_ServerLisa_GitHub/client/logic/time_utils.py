from datetime import datetime, time


def parse_time(value):
    if not value:
        return None
    value = str(value).strip()
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, time_format).time()
        except ValueError:
            continue
    return None


def time_to_minutes(value):
    parsed = parse_time(value)
    if parsed is None:
        return None
    return parsed.hour * 60 + parsed.minute


def minutes_to_worked_time(total_minutes):
    total_minutes = max(0, int(total_minutes or 0))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours}ч {minutes:02}мин"


def worked_time_to_minutes(value):
    if not value or value == "недостаточно данных":
        return 0
    text = str(value).replace(" ", "")
    try:
        hours_text, minutes_text = text.split("ч", 1)
        minutes_text = minutes_text.replace("мин", "")
        return int(hours_text) * 60 + int(minutes_text)
    except Exception:
        return 0


def is_before_noon(value):
    parsed = parse_time(value)
    return parsed is not None and parsed <= time(12, 0)
