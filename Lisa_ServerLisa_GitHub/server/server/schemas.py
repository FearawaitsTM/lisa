from typing import Optional

from pydantic import BaseModel


class ShiftScheduleCreate(BaseModel):
    name: str
    tab_number: str = ""
    shift_type: str = "day"
    start_time: str = "08:00"
    end_time: str = "20:00"
    valid_from: str
    valid_to: Optional[str] = None


NightEmployeeCreate = ShiftScheduleCreate
