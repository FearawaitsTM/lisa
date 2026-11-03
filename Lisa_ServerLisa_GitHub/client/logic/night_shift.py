from datetime import datetime, timedelta, time
from functools import lru_cache

from .time_utils import minutes_to_worked_time, parse_time


@lru_cache(maxsize=16384)
def get_night_shift_date(event_date, event_time):
    parsed_time = parse_time(event_time)
    if parsed_time is None:
        return event_date
    day_value = datetime.strptime(event_date, "%Y-%m-%d").date()
    if parsed_time <= time(12, 0):
        return (day_value - timedelta(days=1)).strftime("%Y-%m-%d")
    return event_date


def group_night_events(events):
    grouped = {}
    for event in events:
        key = (
            event["employee_name"],
            get_night_shift_date(event["date"], event["event_time"]),
        )
        grouped.setdefault(key, []).append(event)
    return grouped


def build_night_summary(employee_name, shift_date, employee_events, parse_time_value):
    def event_datetime(event):
        event_time = parse_time_value(event.get("event_time"))
        if event_time is None:
            return None
        event_day = datetime.strptime(event["date"], "%Y-%m-%d").date()
        return datetime.combine(event_day, event_time)

    dated_events = []
    for event in employee_events:
        value = event_datetime(event)
        if value is not None:
            dated_events.append((value, event))

    dated_events.sort(key=lambda item: item[0])
    sorted_events = [event for _, event in dated_events]

    entry_events = [
        (value, event)
        for value, event in dated_events
        if event["direction"] == "вход"
    ]
    exit_events = [
        (value, event)
        for value, event in dated_events
        if event["direction"] == "выход"
    ]

    first_in_dt, first_in = entry_events[0] if entry_events else (None, None)
    last_out_dt, last_out = exit_events[-1] if exit_events else (None, None)

    break_count = 0
    total_break_minutes = 0
    pending_exit_dt = None
    employee_has_entered = False

    for event_dt, event in dated_events:
        if event["direction"] == "вход":
            if pending_exit_dt is not None:
                break_minutes = int((event_dt - pending_exit_dt).total_seconds() // 60)
                if break_minutes > 0:
                    break_count += 1
                    total_break_minutes += min(break_minutes, 30)
                pending_exit_dt = None
            employee_has_entered = True
        elif event["direction"] == "выход" and employee_has_entered:
            pending_exit_dt = event_dt

    worked_time = "недостаточно данных"
    if first_in_dt and last_out_dt and last_out_dt >= first_in_dt:
        worked_time = minutes_to_worked_time((last_out_dt - first_in_dt).total_seconds() // 60)

    tab_number = next((event["tab_number"] for event in sorted_events if event.get("tab_number")), "")
    last_event = sorted_events[-1] if sorted_events else None
    if last_event and last_event["direction"] == "вход":
        presence_status = "внутри здания"
    elif last_event and last_event["direction"] == "выход":
        presence_status = "не внутри здания"
    else:
        presence_status = "нет данных"

    summary = {
        "report_date": shift_date,
        "tab_number": tab_number,
        "employee_name": employee_name,
        "employee_type": "ночник",
        "first_in_time": first_in["event_time"] if first_in else "",
        "last_out_time": last_out["event_time"] if last_out else "",
        "worked_time": worked_time,
        "break_count": break_count,
        "total_break_time": minutes_to_worked_time(total_break_minutes),
        "total_break_minutes": total_break_minutes,
        "selected_total": "",
        "first_in_reader": first_in["reader_name"] if first_in else "",
        "last_out_reader": last_out["reader_name"] if last_out else "",
        "arrival_status": "ночная смена" if first_in else "нет входа",
        "departure_status": "ночная смена" if last_out else "нет выхода",
        "presence_status": presence_status,
    }

    return summary
