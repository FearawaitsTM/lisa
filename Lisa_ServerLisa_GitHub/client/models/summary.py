from dataclasses import dataclass


@dataclass
class Summary:
    report_date: str
    tab_number: str
    employee_name: str
    employee_type: str
    first_in_time: str
    last_out_time: str
    worked_time: str
    break_count: int
    total_break_time: str
    total_break_minutes: int
    first_in_reader: str
    last_out_reader: str
    arrival_status: str
    departure_status: str
    presence_status: str
