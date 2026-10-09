"""Shared application, engineering-canvas, and result-plot colors."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


LIGHT = {
    "window": "#f5f7f7", "base": "#ffffff", "canvas": "#fafcfc",
    "alternate": "#f2f6f6", "text": "#24343b", "muted": "#69777e",
    "button": "#edf1f2", "panel": "#e5ebed", "border": "#bac6cb",
    "highlight": "#176b73", "highlight_text": "#ffffff", "selection": "#d5e8ea",
    "hover": "#e0eded", "checked_border": "#62979c", "shadow": "#47575c",
    "light": "#ffffff", "dark": "#86959c", "visited": "#495c91",
    "grid": "#e2e7e8", "axis": "#a8b5b8", "member": "#32464d",
    "label": "#47575c", "accent": "#168b8b", "support": "#258451",
    "load": "#bd3549", "axial": "#3279a4", "shear": "#168b8b", "moment": "#b53c5b",
}
DARK = {
    "window": "#232629", "base": "#292d31", "canvas": "#191c1f",
    "alternate": "#30353a", "text": "#eef1f2", "muted": "#a1aab2",
    "button": "#353b40", "panel": "#30353a", "border": "#56616a",
    "highlight": "#236d73", "highlight_text": "#ffffff", "selection": "#334e52",
    "hover": "#3b4a4f", "checked_border": "#6dabae", "shadow": "#111416",
    "light": "#657079", "dark": "#15191c", "visited": "#bca4ed",
    "grid": "#30373b", "axis": "#58656c", "member": "#d1dbe0",
    "label": "#c4cdd3", "accent": "#4cc9c0", "support": "#73d89c",
    "load": "#ff7b8a", "axial": "#79bdf1", "shear": "#4cc9c0", "moment": "#ff91ad",
}
THEMES = {"light": LIGHT, "dark": DARK}


def theme_name():
    application = QApplication.instance()
    name = application.property("pynitegui_theme") if application else None
    return name if name in THEMES else "light"


def colors():
    return THEMES[theme_name()]


def configure_theme(application, name="light"):
    name = name if isinstance(name, str) and name in THEMES else "light"
    if application.property("pynitegui_theme") == name:
        return
    application.setProperty("pynitegui_theme", name)
    application.setStyle("Fusion")
    c = THEMES[name]
    palette = QPalette()
    roles = {
        "Window": "window", "WindowText": "text", "Base": "base", "AlternateBase": "alternate",
        "Text": "text", "Button": "button", "ButtonText": "text", "Highlight": "highlight",
        "HighlightedText": "highlight_text", "ToolTipBase": "base", "ToolTipText": "text",
        "PlaceholderText": "muted", "Link": "highlight", "LinkVisited": "visited", "Light": "light",
        "Midlight": "panel", "Mid": "border", "Dark": "dark", "Shadow": "shadow",
        "BrightText": "highlight_text", "Accent": "highlight",
    }
    for role, key in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(c[key]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(c["button"]))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor(c["selection"]))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor(c["text"]))
    application.setPalette(palette)
    application.setStyleSheet(f"""
        QMainWindow {{ background: {c['window']}; }}
        QToolBar {{ spacing: 4px; padding: 5px; background: {c['window']}; color: {c['text']}; border-bottom: 1px solid {c['border']}; }}
        QToolBar::separator {{ background: {c['border']}; width: 1px; margin: 5px 2px; }}
        QToolButton {{ padding: 4px; border: 1px solid transparent; border-radius: 3px; }}
        QToolButton:hover {{ background: {c['hover']}; }}
        QToolButton:checked {{ background: {c['selection']}; border-color: {c['checked_border']}; }}
        QDockWidget::title {{ padding: 7px; background: {c['panel']}; color: {c['text']}; }}
        QTreeWidget, QTableWidget {{ border: 0; alternate-background-color: {c['alternate']}; }}
        QPushButton {{ padding: 5px 10px; }}
        QStatusBar {{ background: {c['panel']}; color: {c['text']}; }}
    """)
    for widget in application.topLevelWidgets():
        if hasattr(widget, "apply_theme"):
            widget.apply_theme()


def style_axes(ax):
    c = colors()
    ax.figure.set_facecolor(c["window"])
    ax.set_facecolor(c["canvas"])
    ax.tick_params(colors=c["label"])
    for spine in ax.spines.values():
        spine.set_color(c["axis"])
    for text in (ax.title, ax.xaxis.label, ax.yaxis.label, ax.xaxis.get_offset_text(), ax.yaxis.get_offset_text()):
        text.set_color(c["text"])
    ax.grid(color=c["axis"], alpha=0.3)


def restyle_figure(figure, previous):
    from matplotlib.colors import to_hex, to_rgba
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.text import Text
    current = colors()
    replacements = {color: current[key] for key, color in previous.items()}

    def recolor(value):
        rgba = to_rgba(value)
        replacement = replacements.get(to_hex(rgba))
        return (*to_rgba(replacement)[:3], rgba[3]) if replacement else value

    for artist in figure.findobj():
        if isinstance(artist, (Line2D, Text)):
            artist.set_color(recolor(artist.get_color()))
            if isinstance(artist, Text) and artist.get_bbox_patch() is not None:
                patch = artist.get_bbox_patch()
                patch.set_facecolor(recolor(patch.get_facecolor()))
                patch.set_edgecolor(recolor(patch.get_edgecolor()))
        elif isinstance(artist, Patch):
            artist.set_facecolor(recolor(artist.get_facecolor()))
            artist.set_edgecolor(recolor(artist.get_edgecolor()))
    for ax in figure.axes:
        style_axes(ax)
