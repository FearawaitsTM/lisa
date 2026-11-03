import tkinter as tk


TRANSPARENT_GIF = "R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="


def patch_tksheet_icons_if_needed():
    try:
        tk.PhotoImage(data=TRANSPARENT_GIF)
    except Exception:
        return

    try:
        import tksheet.sheet_options as sheet_options
    except Exception:
        return

    icon_names = [
        name
        for name in dir(sheet_options)
        if name.startswith("ICON_")
    ]

    for name in icon_names:
        try:
            tk.PhotoImage(data=getattr(sheet_options, name))
        except tk.TclError:
            setattr(sheet_options, name, TRANSPARENT_GIF)
