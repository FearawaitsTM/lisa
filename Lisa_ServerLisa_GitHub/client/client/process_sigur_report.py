import csv
import io
import math
import os
import re
import warnings
from datetime import date, datetime, time
from functools import lru_cache
from itertools import chain

from openpyxl import load_workbook

from logic.day_shift import build_day_summary
from logic.employee_type import build_night_period_index, find_night_period, get_employee_type
from logic.highlights import get_arrival_status, get_departure_status
from logic.night_shift import build_night_summary, get_night_shift_date, group_night_events

warnings.filterwarnings(
    "ignore",
    message="Workbook contains no default style.*",
)


def is_empty(value):
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def normalize_text(value):
    if is_empty(value):
        return ""
    return str(value).strip()


@lru_cache(maxsize=4096)
def normalize_date_text(text):
    possible_formats = [
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    for format_value in possible_formats:
        try:
            return datetime.strptime(text, format_value).date().strftime("%Y-%m-%d")
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize_date(value):
    if is_empty(value):
        return None
    if isinstance(value, datetime):
        return value.date().strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return normalize_date_text(str(value).strip())


@lru_cache(maxsize=4096)
def normalize_time_text(text):
    possible_formats = [
        "%H:%M:%S",
        "%H:%M",
        "%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
    ]
    for format_value in possible_formats:
        try:
            return datetime.strptime(text, format_value).time().strftime("%H:%M:%S")
        except ValueError:
            continue

    try:
        return time.fromisoformat(text).strftime("%H:%M:%S")
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).time().strftime("%H:%M:%S")
        except ValueError:
            return None


def normalize_time(value):
    if is_empty(value):
        return None
    if isinstance(value, datetime):
        return value.time().strftime("%H:%M:%S")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, (int, float)):
        total_seconds = int(round(float(value) * 24 * 60 * 60))
        total_seconds %= 24 * 60 * 60
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return normalize_time_text(str(value).strip())


@lru_cache(maxsize=4096)
def parse_time_value(value):
    normalized = normalize_time(value)
    if normalized is None:
        return None
    for format_value in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(normalized, format_value).time()
        except ValueError:
            continue
    return None


def decode_csv_bytes(raw_bytes):
    encodings = ["utf-8-sig", "utf-8", "cp1251"]
    last_error = None
    for encoding in encodings:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError as error:
            last_error = error
    raise RuntimeError(f"Не удалось прочитать CSV: {last_error}")


def read_csv(source):
    if isinstance(source, str):
        text = source
    else:
        text = decode_csv_bytes(bytes(source))

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"
    return csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)


def read_xlsx(source):
    def rows():
        workbook = load_workbook(source, read_only=True, data_only=True)
        try:
            worksheet = workbook.active
            if hasattr(worksheet, "reset_dimensions"):
                worksheet.reset_dimensions()
            yield from worksheet.iter_rows(values_only=True)
        finally:
            workbook.close()

    return rows()


def read_source(source):
    if isinstance(source, (bytes, bytearray)):
        raw_bytes = bytes(source)
        if raw_bytes.startswith(b"PK"):
            return read_xlsx(io.BytesIO(raw_bytes))
        return read_csv(raw_bytes)

    if hasattr(source, "read"):
        raw_bytes = source.read()
        if isinstance(raw_bytes, str):
            return read_csv(raw_bytes)
        return read_source(raw_bytes)

    file_name = os.fspath(source)
    extension = os.path.splitext(file_name)[1].lower()
    if extension == ".xlsx":
        return read_xlsx(file_name)
    if extension == ".csv":
        with open(file_name, "rb") as file:
            return read_csv(file.read())
    raise ValueError("Поддерживаются только XLSX и CSV")


def infer_direction(direction, event_name, reader_name=""):
    direction_text = normalize_text(direction).lower()
    event_text = normalize_text(event_name).lower()
    reader_text = normalize_text(reader_name).lower()
    combined = f"{direction_text} {event_text} {reader_text}"
    if "выход" in combined or "exit" in combined:
        return "выход"
    if "вход" in combined or "entry" in combined or "enter" in combined:
        return "вход"
    return direction_text


def normalize_header(value):
    text = normalize_text(value).lower().replace("ё", "е")
    return " ".join(re.findall(r"[a-zа-я0-9]+", text))


def classify_header(value):
    text = normalize_header(value)
    if not text:
        return ()

    result = []
    if "дата" in text:
        result.append("date")
    if "врем" in text:
        result.append("time")
    if "считывател" in text or "точка проход" in text or "точка доступ" in text or "устройств" in text:
        result.append("reader")
    if "направлен" in text or "вход выход" in text:
        result.append("direction")
    if "событ" in text or "операц" in text or "результат проход" in text:
        result.append("event")
    if "табель" in text or "таб номер" in text or text == "таб" or text.endswith(" таб"):
        result.append("tab")
    if (
        "фио" in text
        or "фио сотруд" in text
        or "сотрудник" in text
        or "владелец карт" in text
        or "фамилия имя" in text
    ):
        result.append("employee")
    return tuple(result)


def detect_column_map(preview_rows):
    best = None
    for row_index, row in enumerate(preview_rows):
        for header_height in (1, 2):
            end_index = row_index + header_height - 1
            if end_index >= len(preview_rows):
                continue

            header_rows = preview_rows[row_index : end_index + 1]
            max_columns = max((len(header_row) for header_row in header_rows), default=0)
            column_map = {}
            combined_headers = []
            for column_index in range(max_columns):
                header_parts = [
                    normalize_text(header_row[column_index])
                    for header_row in header_rows
                    if column_index < len(header_row) and not is_empty(header_row[column_index])
                ]
                combined_header = " ".join(dict.fromkeys(header_parts))
                combined_headers.append(combined_header)
                for field_name in classify_header(combined_header):
                    column_map.setdefault(field_name, column_index)

            score = len(column_map)
            has_identity = "employee" in column_map or "tab" in column_map
            date_header = (
                combined_headers[column_map["date"]]
                if "date" in column_map and column_map["date"] < len(combined_headers)
                else ""
            )
            has_timestamp = "date" in column_map and (
                "time" in column_map or "дата и время" in normalize_header(date_header)
            )
            has_event = any(name in column_map for name in ("direction", "event", "reader"))
            if score >= 4 and has_identity and has_timestamp and has_event:
                candidate = (score, end_index, column_map)
                if best is None or candidate[0] > best[0]:
                    best = candidate

    if best is not None:
        return best[1], best[2]
    return None, None


def row_value(row, column_index):
    if column_index is None or column_index >= len(row):
        return None
    return row[column_index]


def is_successful_pass(event_name):
    text = normalize_header(event_name)
    if not text:
        return True

    rejected_markers = (
        "взлом",
        "доступ запрещ",
        "проход не совершен",
        "проход не совершён",
        "связь с точкой",
        "неизвестный номер пропуска",
        "access denied",
        "passage not completed",
    )
    return not any(marker in text for marker in rejected_markers)


def is_unknown_employee(employee_name):
    text = normalize_header(employee_name)
    return text in {"", "не определен", "не определён", "unknown", "undefined", "none"}


def read_events_from_rows(rows):
    iterator = iter(rows)
    preview = []
    for _ in range(50):
        try:
            preview.append(next(iterator))
        except StopIteration:
            break

    header_index, column_map = detect_column_map(preview)
    if column_map is None:
        column_map = {
            "date": 0,
            "time": 1,
            "reader": 2,
            "direction": 3,
            "event": 4,
            "tab": 6,
            "employee": 7,
        }
        data_rows = chain(preview[8:], iterator)
    else:
        data_rows = chain(preview[header_index + 1 :], iterator)

    events = []
    last_date = None
    last_tab_number = None
    last_employee_name = None

    for row in data_rows:
        raw_date = row_value(row, column_map.get("date"))
        raw_time = row_value(row, column_map.get("time"))
        raw_reader = row_value(row, column_map.get("reader"))
        raw_direction = row_value(row, column_map.get("direction"))
        raw_event = row_value(row, column_map.get("event"))
        raw_tab = row_value(row, column_map.get("tab"))
        raw_employee = row_value(row, column_map.get("employee"))

        explicit_event_date = normalize_date(raw_date)
        event_date = explicit_event_date
        event_time = normalize_time(raw_time)
        if event_time is None and isinstance(raw_date, datetime):
            event_time = normalize_time(raw_date)
        reader_name = normalize_text(raw_reader)
        event_name = normalize_text(raw_event)
        tab_number = normalize_text(raw_tab)
        employee_name = normalize_text(raw_employee)

        if event_date:
            last_date = event_date
        else:
            event_date = last_date
        if tab_number:
            last_tab_number = tab_number
        elif not explicit_event_date:
            tab_number = last_tab_number
        if employee_name:
            last_employee_name = employee_name
        elif not explicit_event_date:
            employee_name = last_employee_name

        direction = infer_direction(raw_direction, event_name, reader_name)
        if (
            not event_date
            or not event_time
            or is_unknown_employee(employee_name)
            or direction not in {"вход", "выход"}
            or not is_successful_pass(event_name)
        ):
            continue

        events.append(
            {
                "date": event_date,
                "event_time": event_time,
                "reader_name": reader_name,
                "direction": direction,
                "event_name": event_name,
                "tab_number": tab_number,
                "employee_name": employee_name,
            }
        )
    return events


def open_xlsx_workbook(source):
    if isinstance(source, (bytes, bytearray)):
        return load_workbook(io.BytesIO(bytes(source)), read_only=True, data_only=True)
    if hasattr(source, "read"):
        return load_workbook(source, read_only=True, data_only=True)
    return load_workbook(os.fspath(source), read_only=True, data_only=True)


def source_is_xlsx(source):
    if isinstance(source, (bytes, bytearray)):
        return bytes(source).startswith(b"PK")
    if hasattr(source, "read"):
        position = source.tell() if hasattr(source, "tell") else None
        prefix = source.read(2)
        if position is not None and hasattr(source, "seek"):
            source.seek(position)
        return prefix == b"PK"
    return os.path.splitext(os.fspath(source))[1].lower() == ".xlsx"


def read_sigur_report(source):
    if not source_is_xlsx(source):
        return read_events_from_rows(read_source(source))

    workbook = open_xlsx_workbook(source)
    try:
        events = []
        seen = set()
        for worksheet in workbook.worksheets:
            if hasattr(worksheet, "reset_dimensions"):
                worksheet.reset_dimensions()
            sheet_events = read_events_from_rows(
                worksheet.iter_rows(values_only=True)
            )
            for event in sheet_events:
                key = (
                    event["date"],
                    event["event_time"],
                    event["reader_name"],
                    event["direction"],
                    event["tab_number"],
                    event["employee_name"],
                )
                if key not in seen:
                    seen.add(key)
                    events.append(event)
        return events
    finally:
        workbook.close()


def split_events_by_employee_type(events, night_employees):
    day_events = []
    night_events = []
    for event in events:
        shift_date = get_night_shift_date(event["date"], event["event_time"])
        night_period = find_night_period(
            event.get("employee_name", ""),
            event.get("tab_number", ""),
            shift_date,
            night_employees,
        )
        if night_period:
            night_events.append(event)
        else:
            day_events.append(event)
    return day_events, night_events


def group_day_events(events):
    grouped = {}
    for event in events:
        key = (event["employee_name"], event["date"])
        grouped.setdefault(key, []).append(event)
    return grouped


def finalize_summary(summary):
    if summary.get("employee_type") == "ночник":
        summary["arrival_status"] = "ночная смена" if summary.get("first_in_time") else "нет входа"
        summary["departure_status"] = "ночная смена" if summary.get("last_out_time") else "нет выхода"
    else:
        summary["arrival_status"] = get_arrival_status(summary.get("first_in_time"))
        summary["departure_status"] = get_departure_status(summary.get("last_out_time"))
    summary["selected_total"] = ""
    return summary


def normalize_night_employee_list(night_employees):
    result = []
    for employee in night_employees or []:
        if isinstance(employee, dict):
            result.append(
                {
                    "name": employee.get("name", ""),
                    "tab_number": employee.get("tab_number", ""),
                    "valid_from": employee.get("valid_from") or employee.get("date_from") or employee.get("from"),
                    "valid_to": employee.get("valid_to") or employee.get("date_to") or employee.get("to"),
                }
            )
        else:
            result.append(
                {
                    "name": str(employee),
                    "tab_number": "",
                    "valid_from": None,
                    "valid_to": None,
                }
            )
    return result


def generate_daily_report(source, output_file=None, night_employees=None):
    events = read_sigur_report(source)
    if not events:
        raise RuntimeError(
            "В файле Sigur не найдены строки проходов. "
            "Клиент сохранил полученный файл для диагностики."
        )

    night_periods = normalize_night_employee_list(night_employees)
    night_period_index = build_night_period_index(night_periods)
    day_events, night_events = split_events_by_employee_type(events, night_period_index)
    summaries = []

    for (employee_name, report_date), employee_events in group_day_events(day_events).items():
        summaries.append(finalize_summary(build_day_summary(
            employee_name,
            report_date,
            employee_events,
            parse_time_value,
        )))

    for (employee_name, report_date), employee_events in group_night_events(night_events).items():
        summaries.append(finalize_summary(build_night_summary(
            employee_name,
            report_date,
            employee_events,
            parse_time_value,
        )))

    for summary in summaries:
        summary["employee_type"] = get_employee_type(summary, night_period_index)

    summaries.sort(key=lambda summary: (summary["report_date"], summary["employee_type"], summary["employee_name"]))

    if output_file:
        fieldnames = list(summaries[0]) if summaries else []
        with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summaries)

    return {
        "events": events,
        "summaries": summaries,
    }
