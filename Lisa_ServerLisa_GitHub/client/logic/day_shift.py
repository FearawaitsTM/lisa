from datetime import datetime, time

from .time_utils import minutes_to_worked_time


def build_day_summary(employee_name, report_date, employee_events, parse_time_value):
    timed_events = [
        (parse_time_value(event["event_time"]) or time(0, 0, 0), event)
        for event in employee_events
    ]
    timed_events.sort(key=lambda item: item[0])
    employee_events = [event for _, event in timed_events]
    entry_events = [item for item in timed_events if item[1]["direction"] == "вход"]
    exit_events = [item for item in timed_events if item[1]["direction"] == "выход"]

    first_in_time, first_in = entry_events[0] if entry_events else (None, None)
    last_out_time, last_out = exit_events[-1] if exit_events else (None, None)

    day_value = datetime.strptime(report_date, "%Y-%m-%d").date()
    break_count = 0
    total_break_minutes = 0
    pending_exit_time = None
    employee_has_entered = False

    for event_time, event in timed_events:
        if event["direction"] == "вход":
            if pending_exit_time is not None:
                exit_datetime = datetime.combine(day_value, pending_exit_time)
                return_datetime = datetime.combine(day_value, event_time)
                break_minutes = int((return_datetime - exit_datetime).total_seconds() // 60)
                if break_minutes > 0:
                    break_count += 1
                    total_break_minutes += min(break_minutes, 30)
                pending_exit_time = None
            employee_has_entered = True
        elif event["direction"] == "выход" and employee_has_entered:
            pending_exit_time = event_time

    worked_time = "недостаточно данных"
    if first_in_time and last_out_time:
        delta = datetime.combine(day_value, last_out_time) - datetime.combine(day_value, first_in_time)
        if delta.total_seconds() >= 0:
            worked_time = minutes_to_worked_time(delta.total_seconds() // 60)

    tab_number = next((event["tab_number"] for event in employee_events if event.get("tab_number")), "")
    last_event = employee_events[-1] if employee_events else None
    if last_event and last_event["direction"] == "вход":
        presence_status = "внутри здания"
    elif last_event and last_event["direction"] == "выход":
        presence_status = "не внутри здания"
    else:
        presence_status = "нет данных"

    return {
        "report_date": report_date,
        "tab_number": tab_number,
        "employee_name": employee_name,
        "employee_type": "дневной",
        "first_in_time": first_in["event_time"] if first_in else "",
        "last_out_time": last_out["event_time"] if last_out else "",
        "worked_time": worked_time,
        "break_count": break_count,
        "total_break_time": minutes_to_worked_time(total_break_minutes),
        "total_break_minutes": total_break_minutes,
        "selected_total": "",
        "first_in_reader": first_in["reader_name"] if first_in else "",
        "last_out_reader": last_out["reader_name"] if last_out else "",
        "arrival_status": "есть вход" if first_in else "нет входа",
        "departure_status": "есть выход" if last_out else "нет выхода",
        "presence_status": presence_status,
    }
