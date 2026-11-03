from dataclasses import dataclass


@dataclass
class Event:
    date: str
    event_time: str
    reader_name: str
    direction: str
    event_name: str
    tab_number: str
    employee_name: str
