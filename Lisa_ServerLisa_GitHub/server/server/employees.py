from fastapi import APIRouter, HTTPException

from .database import add_shift_schedule, delete_shift_schedule, list_shift_schedules
from .schemas import ShiftScheduleCreate


router = APIRouter()


@router.get("/shift-schedules")
def get_shift_schedules():
    return list_shift_schedules()


@router.post("/shift-schedules")
def create_shift_schedule(payload: ShiftScheduleCreate):
    try:
        return add_shift_schedule(
            payload.name,
            payload.tab_number,
            payload.shift_type,
            payload.start_time,
            payload.end_time,
            payload.valid_from,
            payload.valid_to,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/shift-schedules/{schedule_id}")
def remove_shift_schedule(schedule_id: int):
    return delete_shift_schedule(schedule_id)


# Совместимость с уже установленными клиентами.
@router.get("/night-employees")
def get_night_employees_compat():
    return list_shift_schedules()


@router.post("/night-employees")
def create_night_employee_compat(payload: ShiftScheduleCreate):
    return create_shift_schedule(payload)


@router.delete("/night-employees/{schedule_id}")
def remove_night_employee_compat(schedule_id: int):
    return delete_shift_schedule(schedule_id)
