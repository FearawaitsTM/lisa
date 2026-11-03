from client.constants import EARLY_ARRIVAL_LIMIT, EARLY_LEAVE_LIMIT, LATE_LIMIT
from .time_utils import parse_time


def get_arrival_status(value):
    arrival_time = parse_time(value)
    if arrival_time is None:
        return "нет входа"
    if arrival_time < EARLY_ARRIVAL_LIMIT:
        return "ранний приход"
    if arrival_time > LATE_LIMIT:
        return "опоздание"
    return "вовремя"


def get_departure_status(value):
    departure_time = parse_time(value)
    if departure_time is None:
        return "нет выхода"
    if departure_time < EARLY_LEAVE_LIMIT:
        return "ранний уход"
    return "уход вовремя"


def build_highlights(rows, columns):
    arrival_column = columns.index("arrival_status")
    departure_column = columns.index("departure_status")
    type_column = columns.index("employee_type")
    highlights = []

    for row_index, summary in enumerate(rows):
        if summary.get("employee_type") == "ночник":
            highlights.append((row_index, type_column, "#1f6f8b"))

        arrival_status = summary.get("arrival_status", "")
        departure_status = summary.get("departure_status", "")

        if arrival_status == "опоздание":
            highlights.append((row_index, arrival_column, "#ffb3b3"))
        elif arrival_status == "ранний приход":
            highlights.append((row_index, arrival_column, "#b7e4c7"))

        if departure_status == "ранний уход":
            highlights.append((row_index, departure_column, "#fff2a8"))

    return highlights
