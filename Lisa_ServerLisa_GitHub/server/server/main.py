import atexit
import ctypes
import os
import re
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import psutil
import pyautogui
from pywinauto import Desktop
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from PIL import ImageGrab, ImageOps

from server.config import REPORTS_DIR
from server.database import initialize_database
from server.employees import router as employees_router
from server.updater import router as updater_router


SERVER_VERSION = "1.2.24"

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.03

app = FastAPI(title="ServerLisa", version=SERVER_VERSION)
app.include_router(employees_router)
app.include_router(updater_router)


@app.on_event("startup")
def startup():
    initialize_database()


DATE_FROM_X = 669
DATE_FROM_Y = 252
DATE_TO_X = 619
DATE_TO_Y = 276

DATE_FROM_IMAGE = "date_from_anchor.png"
DATE_TO_IMAGE = "date_to_anchor.png"
GET_REPORT_IMAGES = (
    "report_button_text_large.png",
    "report_button_text_small.png",
    "get_report.png",
    "sigur_get_report.png",
)

IMAGE_CONFIDENCE = 0.68
DATE_FIELD_CONFIDENCE = 0.52
DATE_SEARCH_RADIUS_X = 200
DATE_SEARCH_RADIUS_Y = 80
FIELD_KEY_SETTLE_SECONDS = 0.03
FIELD_COMMIT_SECONDS = 0.10
IMAGE_POLL_SECONDS = 0.10
IMAGE_SCALES = (0.75, 0.80, 0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30)

# Шаблоны включают подпись и пустое поле. Здесь указаны координаты центров
# секций день/месяц/год внутри исходных картинок. Они масштабируются вместе
# с найденным шаблоном, поэтому ввод не зависит от разрешения экрана.
DATE_TEMPLATE_COMPONENTS = {
    DATE_FROM_IMAGE: {
        "label_width": 37,
        "component_x": (48, 69, 98),
    },
    DATE_TO_IMAGE: {
        "label_width": 37,
        "component_x": (48, 69, 98),
    },
}

REPORT_SEARCH_FOLDERS = [
    REPORTS_DIR,
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path(tempfile.gettempdir()),
    Path.cwd(),
]
REPORT_EXTENSIONS = {".xlsx", ".csv"}
TEMP_REPORT_PREFIXES = ("tc-tmp",)
REPORT_TIMEOUT_SECONDS = 120
FILE_POLL_SECONDS = 0.10
FILE_STABLE_SECONDS = 0.25

SIGUR_WINDOW_TITLES = (
    "Программа управления",
    "Administrator",
    "SIGUR",
    "Sigur",
)

automation_busy = False
automation_lock = threading.Lock()
wait_event = threading.Event()
desktop_position = threading.local()

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def prevent_windows_sleep():
    try:
        result = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        )
        if result:
            print("Сон и отключение дисплея запрещены")
        else:
            print("Не удалось запретить сон Windows")
    except Exception as error:
        print("Ошибка настройки питания:", repr(error))


def allow_windows_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass


atexit.register(allow_windows_sleep)


def keep_computer_awake():
    while True:
        prevent_windows_sleep()
        wait_event.wait(300)


def wait_until(predicate, timeout_seconds, interval_seconds=0.05):
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            if predicate():
                return True
        except Exception:
            pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        wait_event.wait(min(interval_seconds, remaining))


@app.get("/ping")
def ping():
    try:
        screen_width, screen_height = pyautogui.size()
        mouse_x, mouse_y = pyautogui.position()
        return {
            "message": "Сервер работает",
            "version": SERVER_VERSION,
            "screen_width": screen_width,
            "screen_height": screen_height,
            "mouse_x": mouse_x,
            "mouse_y": mouse_y,
            "search_folders": [str(folder) for folder in REPORT_SEARCH_FOLDERS],
        }
    except Exception as error:
        return {
            "message": "Сервер работает",
            "version": SERVER_VERSION,
            "screen_error": str(error),
        }


def convert_date_for_sigur(date_value):
    return datetime.strptime(date_value, "%Y-%m-%d").strftime("%d.%m.%Y")


def prepare_sigur_dates(date_from, date_to):
    # The client's end date is inclusive. Sigur filters by date and time, so
    # midnight at the start of the following day covers the entire last day.
    end_exclusive = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    return convert_date_for_sigur(date_from), end_exclusive.strftime("%d.%m.%Y")


def check_virtual_screen():
    screen_width, screen_height = pyautogui.size()
    mouse_x, mouse_y = pyautogui.position()
    print("Размер экрана:", screen_width, "x", screen_height)
    print("Положение мыши:", mouse_x, mouse_y)
    if screen_width < 500 or screen_height < 500:
        raise RuntimeError("Виртуальный экран недоступен")


def activate_sigur_window():
    sigur_window = None
    for title in SIGUR_WINDOW_TITLES:
        try:
            windows = pyautogui.getWindowsWithTitle(title)
            if windows:
                sigur_window = windows[0]
                break
        except Exception as error:
            print("Ошибка поиска окна:", title, repr(error))

    if sigur_window is None:
        print("Окно Sigur не найдено")
        return False

    print("Найдено окно Sigur:", sigur_window.title)
    try:
        if sigur_window.isMinimized:
            sigur_window.restore()
        sigur_window.maximize()
        sigur_window.activate()
    except Exception as error:
        print("Не удалось подготовить окно:", repr(error))

    last_geometry = None
    stable_checks = 0

    def window_is_ready():
        nonlocal last_geometry, stable_checks
        geometry = (
            sigur_window.left,
            sigur_window.top,
            sigur_window.width,
            sigur_window.height,
            sigur_window.isMinimized,
        )
        if geometry == last_geometry and not sigur_window.isMinimized:
            stable_checks += 1
        else:
            last_geometry = geometry
            stable_checks = 0
        return stable_checks >= 2 and sigur_window.width > 500 and sigur_window.height > 500

    wait_until(window_is_ready, timeout_seconds=2.0)
    return True


def desktop_preview():
    image = ImageGrab.grab(all_screens=True).convert("RGB")
    return np.asarray(image.resize((160, 90)), dtype=np.int16)


def switch_virtual_desktop(direction):
    """Use the Windows virtual desktop shortcut; detect an edge by its unchanged screen."""
    before = desktop_preview()
    pyautogui.hotkey("ctrl", "win", direction, interval=0.04)
    wait_event.wait(0.55)
    after = desktop_preview()
    difference = float(np.mean(np.abs(before - after)))
    print("Переключение рабочего стола:", direction, "изменение экрана:", round(difference, 2))
    if difference < 2.0:
        return False
    desktop_position.offset += -1 if direction == "left" else 1
    return True


def restore_original_desktop():
    offset = getattr(desktop_position, "offset", 0)
    direction = "right" if offset < 0 else "left"
    for _ in range(abs(offset)):
        if not switch_virtual_desktop(direction):
            print("Не удалось вернуться на исходный рабочий стол")
            break
    desktop_position.offset = 0


def split_sigur_date(date_value):
    day, month, year = date_value.split(".")
    return day.zfill(2), month.zfill(2), year.zfill(4)


def date_search_region(x, y):
    screen_width, screen_height = pyautogui.size()
    left = max(0, x - DATE_SEARCH_RADIUS_X)
    top = max(0, y - DATE_SEARCH_RADIUS_Y)
    right = min(screen_width, x + DATE_SEARCH_RADIUS_X)
    bottom = min(screen_height, y + DATE_SEARCH_RADIUS_Y)
    return left, top, right - left, bottom - top


def date_label_candidates(image_name, screen_gray, left, top):
    image_path = resource_path(image_name)
    template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(f"Не удалось открыть картинку: {image_path}")

    candidates = []
    for scale in IMAGE_SCALES:
        scaled = cv2.resize(
            template,
            (round(template.shape[1] * scale), round(template.shape[0] * scale)),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )
        if scaled.shape[0] > screen_gray.shape[0] or scaled.shape[1] > screen_gray.shape[1]:
            continue
        result = cv2.matchTemplate(screen_gray, scaled, cv2.TM_CCOEFF_NORMED)
        # Собираем несколько совпадений: одно слово «От» само по себе часто
        # находится на другой строке. Нужна пара «От» и «До» рядом.
        for _ in range(12):
            _, score, _, (x, y) = cv2.minMaxLoc(result)
            if score < DATE_FIELD_CONFIDENCE:
                break
            candidates.append((score, left + x, top + y, scale))
            result[max(0, y - 14):y + 15, max(0, x - 14):x + 15] = -1

    unique = []
    for candidate in sorted(candidates, reverse=True):
        if any(abs(candidate[1] - c[1]) < 12 and abs(candidate[2] - c[2]) < 12 for c in unique):
            continue
        unique.append(candidate)
    return unique[:30], template.shape[0]


def select_date_label_pair(from_candidates, to_candidates):
    pairs = []
    for first in from_candidates:
        for second in to_candidates:
            dx = abs(first[1] - second[1])
            dy = second[2] - first[2]
            if dx <= 22 and 23 <= dy <= 55 and abs(first[3] - second[3]) <= 0.16:
                rank = first[0] + second[0] - 0.002 * dx - 0.003 * abs(dy - 34)
                pairs.append((rank, first, second))
    return max(pairs, default=None, key=lambda item: item[0])


def locate_date_fields(required=True):
    screen_width, screen_height = pyautogui.size()
    left = max(0, min(DATE_FROM_X, DATE_TO_X) - 280)
    top = max(0, min(DATE_FROM_Y, DATE_TO_Y) - 110)
    right = min(screen_width, max(DATE_FROM_X, DATE_TO_X) + 200)
    bottom = min(screen_height, max(DATE_FROM_Y, DATE_TO_Y) + 200)
    screenshot = np.asarray(ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True))
    screen_gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
    first, first_height = date_label_candidates(DATE_FROM_IMAGE, screen_gray, left, top)
    second, second_height = date_label_candidates(DATE_TO_IMAGE, screen_gray, left, top)
    pair = select_date_label_pair(first, second)
    if pair is None:
        if not required:
            return None
        save_debug_screenshot("date_labels_not_found")
        raise RuntimeError("Не удалось найти соседние поля «От» и «До» в Sigur. Отчёт не запущен.")

    _, from_label, to_label = pair
    points = {}
    for image_name, label, template_height in (
        (DATE_FROM_IMAGE, from_label, first_height),
        (DATE_TO_IMAGE, to_label, second_height),
    ):
        _, x, y, scale = label
        field_y = y + round(template_height * scale / 2)
        points[image_name] = tuple(
            pyautogui.Point(x + round(component_x * scale), field_y)
            for component_x in DATE_TEMPLATE_COMPONENTS[image_name]["component_x"]
        )
    print("Найдена пара полей дат:", points[DATE_FROM_IMAGE][0], points[DATE_TO_IMAGE][0])
    return points


def find_sigur_date_fields():
    """Look on the active desktop, then search adjacent Windows desktops."""
    points = locate_date_fields(required=False)
    if points is not None:
        return points
    for direction, steps in (("left", 6), ("right", 12)):
        for _ in range(steps):
            if not switch_virtual_desktop(direction):
                break
            points = locate_date_fields(required=False)
            if points is not None:
                # The window may have remained behind another window; bring it forward.
                activate_sigur_window()
                points = locate_date_fields(required=False)
                if points is not None:
                    return points
    save_debug_screenshot("date_labels_not_found")
    raise RuntimeError("Sigur с полями «От» и «До» не найден на рабочих столах Windows. Отчёт не запущен.")


def fallback_date_components(x, y):
    return (
        pyautogui.Point(x - 55, y),
        pyautogui.Point(x - 30, y),
        pyautogui.Point(x + 5, y),
    )


def type_date_components(points, date_value):
    values = split_sigur_date(date_value)
    print("Ввожу дату по частям:", date_value)
    for point, value, part_name in zip(points, values, ("день", "месяц", "год")):
        print("  ", part_name, value, "координаты:", point.x, point.y)
        # В QDateEdit один щелчок выбирает секцию. Двойной щелчок мог
        # выделить не секцию, а соседний разделитель и Sigur отклонял ввод.
        pyautogui.click(point.x, point.y)
        pyautogui.write(value, interval=0.05)
        wait_event.wait(FIELD_KEY_SETTLE_SECONDS)
    pyautogui.press("tab")
    wait_event.wait(FIELD_COMMIT_SECONDS)


def normalized_date_text(value):
    return re.sub(r"\s+", "", str(value).strip())


def date_ocr_matches(actual, expected):
    """Ignore OCR's extra punctuation, but require every date digit in place."""
    match = re.fullmatch(r"(\d{2})\D+(\d{2})\D+(\d{4})", actual)
    if match is None:
        return False
    return ".".join(match.groups()) == expected


@lru_cache(maxsize=1)
def date_ocr_engine():
    from rapidocr import RapidOCR
    return RapidOCR()


def read_date_from_screen(point):
    """Read pixels of the date field; Sigur does not expose its text to UIA."""
    x, y = point.x, point.y
    image = ImageGrab.grab(bbox=(x - 7, y - 10, x + 150, y + 11))
    image = image.resize((image.width * 4, image.height * 4))
    image = ImageOps.expand(image, border=25, fill="white")
    result = date_ocr_engine()(np.asarray(image), use_det=False, use_cls=False)
    text = "".join(result.txts or ())
    confidence = min(result.scores or (0,))
    print("Дата на экране:", repr(text), "доверие:", round(confidence, 3))
    return normalized_date_text(text), confidence


def date_field_has_visible_text(point):
    """Check black and red text inside the edit box, away from its outline.

    On this Sigur screen OCR sometimes returns '.' or ':' for an empty box.
    Rejected input turns red; checking only black ink made a malformed date
    look empty and the next attempt appended text to it.
    """
    x, y = point.x, point.y
    pixels = np.asarray(ImageGrab.grab(bbox=(x - 7, y - 7, x + 145, y + 7)))[:, :, :3].astype(np.int16)
    dark = np.all(pixels < 135, axis=2)
    red = ((pixels[:, :, 0] > 135)
           & (pixels[:, :, 0] - pixels[:, :, 1] > 65)
           & (pixels[:, :, 0] - pixels[:, :, 2] > 65))
    count = int(np.count_nonzero(dark | red))
    print("Пикселей текста внутри поля даты:", count)
    return count > 15


def date_field_has_error_border(point):
    """Sigur marks rejected dates with a red frame."""
    x, y = point.x, point.y
    pixels = np.asarray(ImageGrab.grab(bbox=(x - 8, y - 13, x + 160, y + 14)))
    red = pixels[:, :, 0].astype(np.int16)
    green = pixels[:, :, 1].astype(np.int16)
    blue = pixels[:, :, 2].astype(np.int16)
    return int(np.count_nonzero((red > 170) & (red - green > 70) & (red - blue > 70))) > 80


def fill_date_field(points, date_value, field_name):
    try:
        point = points[0]
        actual, score = read_date_from_screen(point)
        if date_ocr_matches(actual, date_value) and score >= 0.70 and not date_field_has_error_border(point):
            print("Поле", field_name, "уже содержит нужную дату")
            return

        # The user confirmed that dragging across the whole date field and
        # pressing Backspace clears it. Ctrl+A/Home only removed part of the
        # text in this Sigur control (e.g. left "19.100").
        for attempt in range(3):
            if attempt and not date_field_has_visible_text(point):
                break
            pyautogui.moveTo(point.x + 145, point.y)
            pyautogui.dragTo(point.x - 20, point.y, duration=0.4, button="left")
            pyautogui.press("backspace")
            wait_event.wait(0.15)
            print("Очистка поля", field_name, "попытка", attempt + 1)
            if not date_field_has_visible_text(point):
                break
        remaining, _ = read_date_from_screen(point)
        if date_field_has_visible_text(point):
            raise RuntimeError(f"Старое значение не удалилось: {remaining!r}")

        pyautogui.write(date_value, interval=0.12)
        pyautogui.press("tab")
        wait_event.wait(0.25)
        actual, score = read_date_from_screen(point)
        if not date_ocr_matches(actual, date_value) or score < 0.70:
            raise RuntimeError(f"На экране {actual!r} (точность {score:.2f}), ожидалось {date_value!r}")
        if date_field_has_error_border(point):
            raise RuntimeError("Sigur пометил дату красной рамкой")
    except Exception as error:
        save_debug_screenshot("date_entry_" + field_name.replace(" ", "_"))
        raise RuntimeError(
            f"Не удалось подтвердить поле «{field_name}»: {error}. "
            "Отчёт не запущен."
        ) from error


def locate_end_time_field(from_date_point, to_date_point):
    """Find the unchanged 00:00 start time, then use its column for end time."""
    image_path = resource_path("time_zero_anchor.png")
    template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    x, y = from_date_point.x, from_date_point.y
    left, top = x + 125, y - 14
    screenshot = np.asarray(ImageGrab.grab(bbox=(left, top, x + 350, y + 15)))
    gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
    best = None
    for scale in (0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4):
        scaled = cv2.resize(template, None, fx=scale, fy=scale)
        if scaled.shape[0] > gray.shape[0]:
            continue
        _, score, _, (match_x, match_y) = cv2.minMaxLoc(
            cv2.matchTemplate(gray, scaled, cv2.TM_CCOEFF_NORMED)
        )
        if best is None or score > best[0]:
            best = (score, left + match_x, top + match_y, scale)
    if best is None or best[0] < 0.55:
        raise RuntimeError("Не удалось найти время «От» 00:00 рядом с датой")
    print("Найдено время начала:", best)
    start_time, score = read_time_from_screen(best[1], from_date_point.y, best[3])
    if start_time != "00:00" or score < 0.85:
        raise RuntimeError(f"Не удалось подтвердить время «От»: {start_time!r}")
    return best[1], to_date_point.y, best[3]


def read_time_from_screen(text_x, center_y, scale):
    image = ImageGrab.grab(
        bbox=(text_x - 2, center_y - 8, text_x + round(42 * scale), center_y + 8)
    )
    image = ImageOps.expand(image.resize((image.width * 4, image.height * 4)), border=25, fill="white")
    result = date_ocr_engine()(np.asarray(image), use_det=False, use_cls=False)
    return normalized_date_text("".join(result.txts or ())), min(result.scores or (0,))


def read_time_row(point):
    """Read the time widget in the same row as a confirmed date field."""
    x, y = point.x, point.y
    image = ImageGrab.grab(bbox=(x + 125, y - 12, x + 355, y + 13))
    image = image.resize((image.width * 4, image.height * 4))
    result = date_ocr_engine()(np.asarray(image), use_det=True, use_cls=False)
    times = [
        (normalized_date_text(value), score)
        for value, score in zip(result.txts or (), result.scores or ())
        if re.fullmatch(r"\d{1,2}:\d{2}", normalized_date_text(value))
    ]
    if len(times) != 1:
        raise RuntimeError(f"На строке времени найдено {len(times)} значений: {result.txts!r}")
    return times[0]


def verify_midnight_times(from_date_point, to_date_point):
    """Keep Sigur's time widgets untouched; require midnight in both rows."""
    try:
        for name, point in (("От", from_date_point), ("До", to_date_point)):
            actual, score = read_time_row(point)
            print("Время", name, "на экране:", actual, "доверие:", round(score, 3))
            if actual != "00:00" or score < 0.75:
                raise RuntimeError(f"Время «{name}» на экране {actual!r}, требуется '00:00'")
    except Exception as error:
        save_debug_screenshot("midnight_time_check")
        raise RuntimeError(f"Не удалось подтвердить время 00:00: {error}. Отчёт не запущен.") from error


def resource_path(file_name):
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return str(Path(base_path) / file_name)


@lru_cache(maxsize=8)
def load_scaled_templates(image_path):
    template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(f"Не удалось открыть картинку: {image_path}")

    scaled = []
    for scale in IMAGE_SCALES:
        width = max(1, round(template.shape[1] * scale))
        height = max(1, round(template.shape[0] * scale))
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        scaled.append((cv2.resize(template, (width, height), interpolation=interpolation), scale))
    return tuple(scaled)


def locate_image_multiscale(image_path, confidence, region=None):
    if region:
        left, top, width, height = region
        bbox = (left, top, left + width, top + height)
    else:
        bbox = None

    # Используем прямой захват Pillow. Он надёжно включается в PyInstaller и
    # не зависит от ленивого импорта PyScreeze внутри PyAutoGUI.
    screenshot = np.asarray(ImageGrab.grab(bbox=bbox, all_screens=True))
    screen_gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
    offset_x = region[0] if region else 0
    offset_y = region[1] if region else 0

    best_score = -1.0
    best_point = None
    for template, _scale in load_scaled_templates(image_path):
        height, width = template.shape[:2]
        if height > screen_gray.shape[0] or width > screen_gray.shape[1]:
            continue
        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if score > best_score:
            best_score = score
            best_point = pyautogui.Point(
                offset_x + location[0] + width // 2,
                offset_y + location[1] + height // 2,
            )

    if best_score >= confidence:
        return best_point, best_score
    return None, best_score


def save_debug_screenshot(image_name):
    try:
        target = REPORTS_DIR / f"debug_{Path(image_name).stem}.png"
        ImageGrab.grab(all_screens=True).save(target)
        print("Снимок экрана сохранён:", target)
    except Exception as error:
        print("Не удалось сохранить снимок экрана:", repr(error))


def find_image_on_screen(
    image_name,
    timeout_seconds=30,
    confidence=IMAGE_CONFIDENCE,
    region=None,
):
    image_path = resource_path(image_name)
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Не найдена картинка для поиска: {image_path}")

    print("Ищу на экране:", image_path, "точность:", confidence)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            point, score = locate_image_multiscale(image_path, confidence, region)
            if point is not None:
                print("Картинка найдена:", image_name, "координаты:", point.x, point.y, "точность:", round(score, 3))
                return point
        except Exception as error:
            print("Ошибка распознавания картинки:", image_name, repr(error))

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            save_debug_screenshot(image_name)
            return None
        wait_event.wait(min(IMAGE_POLL_SECONDS, remaining))


def click_image_on_screen(
    image_name,
    timeout_seconds=30,
    confidence=IMAGE_CONFIDENCE,
    region=None,
):
    point = find_image_on_screen(
        image_name=image_name,
        timeout_seconds=timeout_seconds,
        confidence=confidence,
        region=region,
    )
    if point is None:
        return False
    pyautogui.click(point.x, point.y)
    return True


def click_first_matching_image(image_names, timeout_per_image, confidence=IMAGE_CONFIDENCE, region=None):
    for image_name in image_names:
        print("Пробую шаблон:", image_name)
        if click_image_on_screen(
            image_name,
            timeout_seconds=timeout_per_image,
            confidence=max(confidence, 0.78) if image_name.startswith("report_button_text_") else confidence,
            region=region,
        ):
            return True
    return False


def report_button_region(to_date_point):
    """Search below Sigur's date fields, away from the Lisa client and dialogs."""
    screen_width, screen_height = pyautogui.size()
    left = max(0, to_date_point.x - 500)
    top = min(screen_height, to_date_point.y + 100)
    right = min(screen_width, to_date_point.x + 70)
    bottom = min(screen_height, to_date_point.y + 440)
    return left, top, right - left, bottom - top


def iter_report_files():
    visited = set()
    for folder in REPORT_SEARCH_FOLDERS:
        try:
            folder_key = str(folder.resolve()).casefold()
        except OSError:
            folder_key = str(folder).casefold()
        if folder_key in visited:
            continue
        visited.add(folder_key)

        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if not entry.is_file() or entry.name.startswith("~$"):
                            continue
                        entry_path = Path(entry.name)
                        is_known_extension = entry_path.suffix.lower() in REPORT_EXTENSIONS
                        is_sigur_temp = entry.name.casefold().startswith(TEMP_REPORT_PREFIXES)
                        if not is_known_extension and not is_sigur_temp:
                            continue
                        stat = entry.stat()
                        yield Path(entry.path), (stat.st_mtime_ns, stat.st_size)
                    except OSError:
                        continue
        except OSError:
            continue


def snapshot_report_files():
    return {str(path.resolve()).casefold(): signature for path, signature in iter_report_files()}


def find_changed_reports(previous_files):
    changed = []
    for path, signature in iter_report_files():
        key = str(path.resolve()).casefold()
        if signature[1] <= 0 or previous_files.get(key) == signature:
            continue
        changed.append((signature[0], path, signature))
    changed.sort(key=lambda item: item[0], reverse=True)
    return changed


def detect_report_extension(path):
    """Определяет формат и для временных tc-tmp без расширения."""
    try:
        if path.suffix.lower() == ".csv":
            with path.open("rb") as report_file:
                return ".csv" if report_file.read(1) else None

        if path.suffix.lower() == ".xlsx" or path.name.casefold().startswith(TEMP_REPORT_PREFIXES):
            with zipfile.ZipFile(path) as workbook:
                if "[Content_Types].xml" in workbook.namelist():
                    return ".xlsx"
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def report_can_be_opened(path):
    return detect_report_extension(path) is not None


def wait_for_report_file(previous_files, timeout_seconds=REPORT_TIMEOUT_SECONDS):
    print("Ожидаю только новый файл отчёта:", timeout_seconds, "секунд")
    deadline = time.monotonic() + timeout_seconds
    stable_candidates = {}
    last_popup_probe = 0

    while True:
        now = time.monotonic()
        for _, report_path, signature in find_changed_reports(previous_files):
            key = str(report_path.resolve()).casefold()
            previous_state = stable_candidates.get(key)
            if previous_state is None or previous_state[0] != signature:
                stable_candidates[key] = (signature, now)
                continue
            if now - previous_state[1] >= FILE_STABLE_SECONDS and report_can_be_opened(report_path):
                print("Новый файл полностью сохранён:", report_path)
                return report_path
            if (
                report_path.name.casefold().startswith(TEMP_REPORT_PREFIXES)
                and now - last_popup_probe >= 1.0
            ):
                confirm_excel_report_popup(report_path)
                last_popup_probe = now

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print("Новый файл отчёта не найден")
            return None
        wait_event.wait(min(FILE_POLL_SECONDS, remaining))


def delete_file_later(file_path, attempts=30, delay=0.5):
    file_path = Path(file_path)
    for attempt in range(1, attempts + 1):
        try:
            if not file_path.exists():
                return
            file_path.unlink()
            print("Временный файл удалён:", file_path)
            return
        except PermissionError:
            print("Файл пока занят. Попытка удаления:", f"{attempt}/{attempts}")
        except OSError as error:
            print("Ошибка удаления временного файла:", repr(error))
        wait_event.wait(delay)


def close_generated_excel_workbook(file_path):
    """Закрывает только созданную Sigur временную книгу tc-tmp в Excel."""
    file_path = Path(file_path)
    if not file_path.name.casefold().startswith(TEMP_REPORT_PREFIXES):
        return False

    workbook_name = file_path.name.casefold()
    workbook_path = str(file_path.resolve()).casefold()

    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            excel = win32com.client.GetActiveObject("Excel.Application")
            for workbook in list(excel.Workbooks):
                try:
                    name_matches = str(workbook.Name).casefold() == workbook_name
                    path_matches = str(workbook.FullName).casefold() == workbook_path
                    if not name_matches and not path_matches:
                        continue
                    workbook.Close(SaveChanges=False)
                    print("Временная книга Excel закрыта:", file_path.name)
                    return True
                except Exception as error:
                    print("Не удалось проверить книгу Excel:", repr(error))
        finally:
            pythoncom.CoUninitialize()
    except Exception as error:
        print("COM-закрытие Excel недоступно:", repr(error))

    # Запасной вариант на случай, если Excel не зарегистрировал COM-объект.
    try:
        for window in pyautogui.getWindowsWithTitle(file_path.name):
            title = str(getattr(window, "title", ""))
            if file_path.name.casefold() not in title.casefold():
                continue
            window.close()
            print("Окно временной книги Excel закрыто:", title)
            return True
    except Exception as error:
        print("Не удалось закрыть окно временной книги Excel:", repr(error))
    return False


def confirm_excel_report_popup(file_path):
    """Confirm only an Excel OK dialog after a new Sigur temp report exists."""
    if not Path(file_path).name.casefold().startswith(TEMP_REPORT_PREFIXES):
        return False
    try:
        desktop = Desktop(backend="uia")
        for window in desktop.windows():
            try:
                if psutil.Process(window.process_id()).name().casefold() != "excel.exe":
                    continue
                if "excel" not in window.window_text().casefold():
                    continue
                for button in window.descendants(control_type="Button"):
                    if button.window_text().strip().replace("&", "").casefold() in ("ok", "ок"):
                        button.click_input()
                        print("Подтверждена плашка Excel для временного отчёта")
                        return True
            except (psutil.Error, RuntimeError, AttributeError) as error:
                print("Не удалось проверить окно Excel:", repr(error))
    except Exception as error:
        print("Не удалось найти плашку Excel:", repr(error))
    return False


def export_report_from_sigur(date_from, date_to):
    check_virtual_screen()
    sigur_date_from, sigur_date_to = prepare_sigur_dates(date_from, date_to)

    print("Дата от для Sigur:", sigur_date_from)
    print("Дата до для Sigur:", sigur_date_to)
    if not activate_sigur_window():
        raise RuntimeError("Окно Sigur не найдено")

    date_points = find_sigur_date_fields()

    fill_date_field(
        date_points[DATE_FROM_IMAGE],
        sigur_date_from,
        "Дата от",
    )
    fill_date_field(
        date_points[DATE_TO_IMAGE],
        sigur_date_to,
        "Дата до",
    )
    verify_midnight_times(date_points[DATE_FROM_IMAGE][0], date_points[DATE_TO_IMAGE][0])
    save_debug_screenshot("dates_entered")

    # Снимок делается непосредственно перед запуском отчёта. Благодаря этому
    # файлы от предыдущих запросов никогда не считаются новым результатом.
    previous_files = snapshot_report_files()

    print("Ищу кнопку «Получить отчёт»")
    if not click_first_matching_image(
        GET_REPORT_IMAGES,
        timeout_per_image=3,
        confidence=IMAGE_CONFIDENCE,
        region=report_button_region(date_points[DATE_TO_IMAGE][0]),
    ):
        save_debug_screenshot("report_button_not_found")
        raise RuntimeError("Кнопка «Получить отчёт» не найдена")

    # В установленном Sigur отчёт появляется как новая временная книга Excel.
    # Никаких слепых Enter и кнопок Edge: чужое окно можно подтвердить случайно.
    report_path = wait_for_report_file(previous_files, REPORT_TIMEOUT_SECONDS)
    if report_path is None:
        save_debug_screenshot("report_not_created")
    return report_path


@app.get("/report")
def get_report(date_from: str, date_to: str):
    global automation_busy

    if not automation_lock.acquire(blocking=False):
        return JSONResponse(status_code=409, content={"error": "Уже выполняется другой отчёт"})
    automation_busy = True
    desktop_position.offset = 0

    try:
        print("=" * 60)
        print("Получен запрос отчёта", date_from, date_to)
        datetime.strptime(date_from, "%Y-%m-%d")
        datetime.strptime(date_to, "%Y-%m-%d")

        report_path = export_report_from_sigur(date_from, date_to)
        if report_path is None:
            return JSONResponse(
                status_code=500,
                content={"error": "Новый файл отчёта не найден. Старые файлы намеренно игнорируются."},
            )
        if not report_path.exists():
            return JSONResponse(status_code=500, content={"error": "Файл отчёта исчез"})

        extension = detect_report_extension(report_path)
        if extension is None:
            shown_extension = report_path.suffix.lower() or "без расширения"
            return JSONResponse(
                status_code=500,
                content={"error": f"Неподдерживаемый формат: {shown_extension}"},
            )

        file_bytes = report_path.read_bytes()
        if not file_bytes:
            return JSONResponse(status_code=500, content={"error": "Файл отчёта пустой"})

        confirm_excel_report_popup(report_path)
        # Sigur открывает временную книгу tc-tmp в Excel. Она уже прочитана,
        # поэтому закрываем только её без сохранения, чтобы следующий запрос
        # не требовал ручного закрытия окна.
        close_generated_excel_workbook(report_path)

        if extension == ".csv":
            media_type = "text/csv"
            file_name = "sigur_report.csv"
        else:
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            file_name = "sigur_report.xlsx"

        threading.Thread(
            target=delete_file_later,
            args=(report_path,),
            daemon=True,
        ).start()

        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "X-Report-Extension": extension,
                "X-Date-From": date_from,
                "X-Date-To": date_to,
                "X-Server-Version": SERVER_VERSION,
            },
        )
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Неверная дата. Используй YYYY-MM-DD"})
    except Exception as error:
        print("Ошибка сервера:", repr(error))
        return JSONResponse(status_code=500, content={"error": str(error)})
    finally:
        try:
            restore_original_desktop()
        except Exception as error:
            print("Не удалось вернуть исходный рабочий стол:", repr(error))
        automation_busy = False
        automation_lock.release()
        print("Запрос завершён")
        print("=" * 60)


def run():
    import uvicorn

    print("=" * 60)
    print("Запуск ServerLisa", SERVER_VERSION)
    print("Папки поиска файлов:")
    for folder in REPORT_SEARCH_FOLDERS:
        print(" -", folder)

    prevent_windows_sleep()
    threading.Thread(target=keep_computer_awake, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
