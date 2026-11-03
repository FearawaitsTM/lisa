import textwrap
from datetime import datetime
import tkinter as tk
from tkinter import ttk

from tksheet import Sheet

from .constants import CURRENT_VERSION, TABLE_COLUMNS
from .tksheet_compat import patch_tksheet_icons_if_needed
from .resource import resource_path


BG = "#0d1b2a"
BG_DARK = "#071523"
PANEL = "#10243a"
PANEL_SOFT = "#132b45"
BORDER = "#274765"
TEXT = "#f8fbff"
MUTED = "#9fc5e8"
PRIMARY = "#1f6f8b"
PRIMARY_HOVER = "#2c88aa"
SECONDARY = "#1f3f5f"
SECONDARY_HOVER = "#2c5278"
DANGER = "#7f1d1d"
DANGER_HOVER = "#9f2a2a"
DISABLED = "#465465"


class FlatButton(tk.Label):
    def __init__(self, master, text, command=None, variant="primary", **kwargs):
        self._command = command
        self._variant = variant
        self._state = "normal"
        self._active = False
        self._palette = {
            "primary": (PRIMARY, PRIMARY_HOVER),
            "secondary": (SECONDARY, SECONDARY_HOVER),
            "danger": (DANGER, DANGER_HOVER),
            "tab": (PANEL_SOFT, SECONDARY_HOVER),
        }
        bg, _ = self._colors()
        padx = kwargs.pop("padx", 13)
        pady = kwargs.pop("pady", 7)
        font = kwargs.pop("font", ("Arial", 10, "bold"))
        super().__init__(
            master,
            text=text,
            bg=bg,
            fg=TEXT,
            padx=padx,
            pady=pady,
            cursor="hand2",
            font=font,
            bd=0,
            **kwargs,
        )
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _colors(self):
        if self._state == "disabled":
            return DISABLED, DISABLED
        if self._variant == "tab" and self._active:
            return PRIMARY, PRIMARY_HOVER
        return self._palette.get(self._variant, self._palette["primary"])

    def _refresh(self, hovered=False):
        normal, hover = self._colors()
        self.configure_raw(bg=hover if hovered else normal)
        self.configure_raw(fg="#b8c4d2" if self._state == "disabled" else TEXT)
        self.configure_raw(cursor="" if self._state == "disabled" else "hand2")

    def configure_raw(self, **kwargs):
        super().configure(**kwargs)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self._refresh()
        return super().configure(**kwargs)

    config = configure

    def set_active(self, active):
        self._active = active
        self._refresh()

    def _click(self, _event):
        if self._state != "disabled" and self._command:
            self._command()

    def _enter(self, _event):
        if self._state != "disabled":
            self._refresh(hovered=True)

    def _leave(self, _event):
        self._refresh()


def label(parent, text, **kwargs):
    return tk.Label(
        parent,
        text=text,
        bg=kwargs.pop("bg", PANEL),
        fg=kwargs.pop("fg", TEXT),
        font=kwargs.pop("font", ("Arial", 10)),
        **kwargs,
    )


def entry(parent, **kwargs):
    return tk.Entry(
        parent,
        bg="#0b1726",
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=PRIMARY,
        font=("Arial", 11),
        **kwargs,
    )


def panel(parent, **kwargs):
    return tk.Frame(
        parent,
        bg=PANEL,
        highlightthickness=1,
        highlightbackground=BORDER,
        **kwargs,
    )


def build_ui(app):
    patch_tksheet_icons_if_needed()
    root = app.root
    root.title("Лиса — отчёт посещений")
    root.geometry("1550x860")
    root.minsize(1100, 680)
    root.configure(bg=BG)
    root.grid_rowconfigure(1, weight=1)
    root.grid_columnconfigure(0, weight=1)

    app.label_options = {"bg": PANEL, "fg": TEXT}
    app.entry_options = {}
    app.button_options = {}

    build_update_banner(app)
    build_header(app)

    app.content_frame = tk.Frame(root, bg=BG)
    app.content_frame.grid(row=1, column=0, sticky="nsew")
    app.content_frame.grid_rowconfigure(0, weight=1)
    app.content_frame.grid_columnconfigure(0, weight=1)

    app.report_tab = tk.Frame(app.content_frame, bg=BG)
    app.night_tab = tk.Frame(app.content_frame, bg=BG)

    build_report_tab(app)
    build_night_tab(app)
    show_tab(app, "report")


def build_header(app):
    header = tk.Frame(app.root, bg=BG_DARK, height=72)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    header.grid_columnconfigure(1, weight=1)

    brand_box = tk.Frame(header, bg=BG_DARK)
    brand_box.grid(row=0, column=0, sticky="w", padx=20, pady=8)
    try:
        app.fox_header_image = tk.PhotoImage(file=resource_path("fox_app.png"))
        tk.Label(
            brand_box,
            image=app.fox_header_image,
            bg=BG_DARK,
            bd=0,
        ).pack(side="left", padx=(0, 10))
    except tk.TclError:
        app.fox_header_image = None

    title_box = tk.Frame(brand_box, bg=BG_DARK)
    title_box.pack(side="left")
    tk.Label(
        title_box,
        text="Лиса",
        bg=BG_DARK,
        fg=TEXT,
        font=("Arial", 20, "bold"),
    ).pack(anchor="w")
    tk.Label(
        title_box,
        text="отчёт посещений",
        bg=BG_DARK,
        fg=MUTED,
        font=("Arial", 10),
    ).pack(anchor="w")

    tabs = tk.Frame(header, bg=BG_DARK)
    tabs.grid(row=0, column=1, sticky="w", padx=20)
    app.report_tab_button = FlatButton(
        tabs,
        text="Отчёт",
        variant="tab",
        command=lambda: show_tab(app, "report"),
    )
    app.report_tab_button.pack(side="left", padx=(0, 8))
    app.night_tab_button = FlatButton(
        tabs,
        text="Ночники",
        variant="tab",
        command=lambda: show_tab(app, "night"),
    )
    app.night_tab_button.pack(side="left")

    tk.Label(
        header,
        text=f"v{CURRENT_VERSION}",
        bg=BG_DARK,
        fg="#6f90ad",
        font=("Arial", 10),
    ).grid(row=0, column=2, sticky="e", padx=20)


def show_tab(app, tab_name):
    app.report_tab.grid_forget()
    app.night_tab.grid_forget()

    if tab_name == "night":
        app.night_tab.grid(row=0, column=0, sticky="nsew")
    else:
        app.report_tab.grid(row=0, column=0, sticky="nsew")

    app.report_tab_button.set_active(tab_name == "report")
    app.night_tab_button.set_active(tab_name == "night")


def build_update_banner(app):
    app.update_frame = tk.Frame(
        app.root,
        bg="#7a4b00",
        highlightbackground="#ffb74d",
        highlightthickness=1,
    )
    app.update_text_var = tk.StringVar(value="Доступно обновление")
    app.update_details_var = tk.StringVar(value="")
    tk.Label(
        app.update_frame,
        textvariable=app.update_text_var,
        bg="#7a4b00",
        fg="white",
        font=("Arial", 10, "bold"),
    ).place(x=10, y=7)
    tk.Label(
        app.update_frame,
        textvariable=app.update_details_var,
        bg="#7a4b00",
        fg="#ffe0b2",
        anchor="nw",
        justify="left",
        wraplength=410,
    ).place(x=10, y=32, relwidth=0.70, relheight=0.65)
    app.update_button = FlatButton(
        app.update_frame,
        text="Обновить",
        command=app.update_manager.start_update,
        variant="primary",
    )
    app.update_button.place(relx=0.75, y=16)
    FlatButton(
        app.update_frame,
        text="×",
        command=app.hide_update_banner,
        variant="secondary",
        padx=8,
        pady=3,
        font=("Arial", 12, "bold"),
    ).place(relx=0.95, y=4)


def build_report_tab(app):
    parent = app.report_tab
    parent.grid_rowconfigure(2, weight=1)
    parent.grid_columnconfigure(0, weight=1)

    top = tk.Frame(parent, bg=BG)
    top.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 12))
    top.grid_columnconfigure(0, weight=3)
    top.grid_columnconfigure(1, weight=2)

    controls = panel(top)
    controls.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    controls.grid_columnconfigure(0, weight=1)

    build_server_controls(app, controls)
    build_file_controls(app, controls)
    build_filter_controls(app, controls)

    summary = panel(top)
    summary.grid(row=0, column=1, sticky="nsew")
    summary.grid_columnconfigure(0, weight=1)
    build_selected_summary(app, summary)

    status_band = tk.Frame(parent, bg=BG)
    status_band.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
    app.status_var = tk.StringVar(value="Готов к работе")
    tk.Label(
        status_band,
        textvariable=app.status_var,
        bg=BG,
        fg=MUTED,
        font=("Arial", 10, "bold"),
    ).pack(side="left")

    table_frame = panel(parent)
    table_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    app.sheet = Sheet(
        table_frame,
        headers=[heading for _, heading, _ in TABLE_COLUMNS],
        data=[],
        theme="dark blue",
        show_row_index=False,
        default_row_height=27,
        header_align="center",
        align="center",
        empty_horizontal=0,
        empty_vertical=0,
    )
    app.sheet.extra_bindings("all_select_events", app.on_employee_select)
    app.sheet.enable_bindings(
        "single_select",
        "drag_select",
        "select_all",
        "column_select",
        "row_select",
        "arrowkeys",
        "copy",
        "rc_select",
        "column_width_resize",
        "double_click_column_resize",
        "ctrl_select",
    )
    app.sheet.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
    for column_index, (_, _, width) in enumerate(TABLE_COLUMNS):
        app.sheet.column_width(column=column_index, width=width, redraw=False)
    app.sheet.redraw()


def build_server_controls(app, parent):
    row = tk.Frame(parent, bg=PANEL)
    row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
    row.grid_columnconfigure(1, weight=1)

    label(row, "Адрес сервера:").grid(row=0, column=0, sticky="w", padx=(0, 8))
    app.server_entry = entry(row)
    app.server_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10), ipady=5)
    app.server_entry.insert(0, app.settings["server_url"])
    FlatButton(
        row,
        text="Проверить обновление",
        command=lambda: app.update_manager.check_for_updates(silent=False),
        variant="secondary",
    ).grid(row=0, column=2, padx=(0, 8))
    FlatButton(
        row,
        text="Обновить ночников",
        command=app.employee_controller.refresh_night_employees,
        variant="secondary",
    ).grid(row=0, column=3)

    date_row = tk.Frame(parent, bg=PANEL)
    date_row.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
    label(date_row, "Дата с:").pack(side="left")
    app.date_from_entry = entry(date_row, width=13)
    app.date_from_entry.pack(side="left", padx=(8, 16), ipady=5)
    label(date_row, "Дата по:").pack(side="left")
    app.date_to_entry = entry(date_row, width=13)
    app.date_to_entry.pack(side="left", padx=(8, 16), ipady=5)
    app.server_button = FlatButton(
        date_row,
        text="Запросить отчёт с сервера",
        command=app.report_controller.request_server_report,
        variant="primary",
    )
    app.server_button.pack(side="left")

    today = datetime.now().strftime("%Y-%m-%d")
    app.date_from_entry.insert(0, today)
    app.date_to_entry.insert(0, today)


def build_file_controls(app, parent):
    row = tk.Frame(parent, bg=PANEL)
    row.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
    FlatButton(
        row,
        text="Выбрать файл Sigur",
        command=app.report_controller.choose_local_file,
        variant="secondary",
    ).pack(side="left")
    app.local_report_button = FlatButton(
        row,
        text="Сформировать локальный отчёт",
        command=app.report_controller.process_local_file,
        variant="secondary",
    )
    app.local_report_button.pack(side="left", padx=10)
    app.selected_file_var = tk.StringVar(value="Файл не выбран")
    tk.Label(
        row,
        textvariable=app.selected_file_var,
        bg=PANEL,
        fg=MUTED,
        font=("Arial", 10),
    ).pack(side="left", padx=(8, 0))


def build_filter_controls(app, parent):
    row = tk.Frame(parent, bg=PANEL)
    row.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 14))
    row.grid_columnconfigure(1, weight=1)
    label(row, "Фильтр по ФИО:").grid(row=0, column=0, sticky="w", padx=(0, 8))
    app.filter_var = tk.StringVar()
    entry(row, textvariable=app.filter_var).grid(row=0, column=1, sticky="ew", ipady=5)
    app.filter_var.trace_add("write", app.schedule_filter)

    app.employee_type_var = tk.StringVar(value="все")
    style = ttk.Style()
    style.configure("Lisa.TCombobox", fieldbackground="#0b1726", background="#0b1726")
    ttk.Combobox(
        row,
        textvariable=app.employee_type_var,
        values=["все", "дневной", "ночник"],
        width=11,
        state="readonly",
        style="Lisa.TCombobox",
    ).grid(row=0, column=2, padx=10)
    app.employee_type_var.trace_add("write", app.schedule_filter)

    app.count_var = tk.StringVar(value="Строк: 0")
    tk.Label(
        row,
        textvariable=app.count_var,
        bg=PANEL,
        fg=MUTED,
        font=("Arial", 10, "bold"),
    ).grid(row=0, column=3, sticky="e")


def build_selected_summary(app, parent):
    app.selected_employee_var = tk.StringVar(value="Сотрудник не выбран")
    app.total_worked_var = tk.StringVar(value="Всего: 0ч 00мин")
    app.total_breaks_var = tk.StringVar(value="Выходов: 0, время выходов: 0ч 00мин")

    tk.Label(
        parent,
        textvariable=app.selected_employee_var,
        bg=PANEL,
        fg=TEXT,
        font=("Arial", 12, "bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
    tk.Label(
        parent,
        textvariable=app.total_worked_var,
        bg=PANEL,
        fg=MUTED,
        font=("Arial", 10, "bold"),
        anchor="w",
    ).grid(row=1, column=0, sticky="ew", padx=16)
    tk.Label(
        parent,
        textvariable=app.total_breaks_var,
        bg=PANEL,
        fg=MUTED,
        font=("Arial", 10, "bold"),
        anchor="w",
    ).grid(row=2, column=0, sticky="ew", padx=16, pady=(2, 8))

    employee_table_frame = tk.Frame(parent, bg=PANEL)
    employee_table_frame.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))
    employee_table_frame.grid_rowconfigure(0, weight=1)
    employee_table_frame.grid_columnconfigure(0, weight=1)
    app.employee_sheet = Sheet(
        employee_table_frame,
        headers=["Дата", "Смена", "Первый вход", "Последний выход", "Отработано", "Выходов", "Время выходов"],
        data=[],
        theme="dark blue",
        show_row_index=False,
        default_row_height=25,
        header_align="center",
        align="center",
    )
    app.employee_sheet.grid(row=0, column=0, sticky="nsew")


def build_night_tab(app):
    parent = app.night_tab
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=1)

    form = panel(parent)
    form.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 12))
    form.grid_columnconfigure(1, weight=1)

    label(form, "ФИО:").grid(row=0, column=0, sticky="w", padx=(16, 8), pady=16)
    app.night_name_var = tk.StringVar()
    entry(form, textvariable=app.night_name_var).grid(row=0, column=1, sticky="ew", ipady=5)

    label(form, "Табельный:").grid(row=0, column=2, sticky="w", padx=(16, 8))
    app.night_tab_var = tk.StringVar()
    entry(form, textvariable=app.night_tab_var, width=16).grid(row=0, column=3, ipady=5)

    label(form, "С:").grid(row=1, column=0, sticky="w", padx=(16, 8), pady=(0, 16))
    app.night_from_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
    entry(form, textvariable=app.night_from_var, width=13).grid(row=1, column=1, sticky="w", ipady=5, pady=(0, 16))

    date_to_box = tk.Frame(form, bg=PANEL)
    date_to_box.grid(row=1, column=2, columnspan=2, sticky="w", pady=(0, 16))
    label(date_to_box, "По:").pack(side="left", padx=(0, 8))
    app.night_to_var = tk.StringVar()
    entry(date_to_box, textvariable=app.night_to_var, width=13).pack(side="left", ipady=5)

    app.night_add_button = FlatButton(
        form,
        text="Добавить",
        command=app.employee_controller.add_night_employee,
        variant="primary",
    )
    app.night_add_button.grid(row=0, column=4, rowspan=2, padx=(16, 8))
    FlatButton(
        form,
        text="Удалить выбранного",
        command=app.employee_controller.delete_selected_night_employee,
        variant="danger",
    ).grid(row=0, column=5, rowspan=2, padx=8)
    FlatButton(
        form,
        text="Обновить",
        command=app.employee_controller.refresh_night_employees,
        variant="secondary",
    ).grid(row=0, column=6, rowspan=2, padx=(8, 16))

    app.night_status_var = tk.StringVar(value="Ночников: 0")
    tk.Label(
        form,
        textvariable=app.night_status_var,
        bg=PANEL,
        fg=MUTED,
        font=("Arial", 10, "bold"),
        anchor="w",
    ).grid(row=2, column=0, columnspan=7, sticky="ew", padx=16, pady=(0, 14))

    frame = panel(parent)
    frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)
    app.night_sheet = Sheet(
        frame,
        headers=["ID", "ФИО", "Табельный номер", "Ночник с", "Ночник по", "Добавлен"],
        data=[],
        theme="dark blue",
        show_row_index=False,
        default_row_height=28,
        header_align="center",
        align="center",
    )
    app.night_sheet.enable_bindings(
        "single_select",
        "row_select",
        "arrowkeys",
        "copy",
        "rc_select",
        "ctrl_select",
    )
    app.night_sheet.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)


def place_update_banner(app, manifest):
    version = manifest.get("version", "?")
    notes = str(manifest.get("notes", "")).strip()
    if not notes:
        notes = "Нажми «Обновить», чтобы установить новую версию"
    app.update_text_var.set(f"Доступна версия {version}")
    app.update_details_var.set(notes)
    app.update_button.config(state="normal", text="Обновить")
    wrapped_lines = []
    for original_line in notes.splitlines():
        lines = textwrap.wrap(original_line, width=48)
        wrapped_lines.extend(lines or [""])
    banner_height = 58 + max(1, len(wrapped_lines)) * 18
    app.update_frame.place(relx=0.58, y=10, relwidth=0.40, height=banner_height)
    app.update_frame.lift()
