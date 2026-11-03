from .time_utils import minutes_to_worked_time, worked_time_to_minutes


def calculate_selected_totals(rows, worked_index, break_count_index, break_time_index):
    total_worked = 0
    total_breaks = 0
    total_break_minutes = 0

    for row in rows:
        total_worked += worked_time_to_minutes(row[worked_index])
        try:
            total_breaks += int(row[break_count_index] or 0)
        except Exception:
            pass
        total_break_minutes += worked_time_to_minutes(row[break_time_index])

    return {
        "worked_minutes": total_worked,
        "worked_time": minutes_to_worked_time(total_worked),
        "break_count": total_breaks,
        "break_minutes": total_break_minutes,
        "break_time": minutes_to_worked_time(total_break_minutes),
    }
