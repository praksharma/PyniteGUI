"""Recent-project menu housekeeping; never deletes project or recovery files."""
from pathlib import Path


def recent_paths(settings):
    if settings is None:
        return []
    try:
        stored = settings.value("recent_projects", [], type=list)
    except (TypeError, ValueError):
        return []
    if not isinstance(stored, (list, tuple)):
        return []
    paths = []
    for entry in stored:
        if not isinstance(entry, str) or not entry or "\0" in entry:
            continue
        path = Path(entry)
        if path.is_absolute() and path not in paths:
            paths.append(path)
        if len(paths) == 10:
            break
    return paths


def available(path):
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def update_menu(window):
    menu = window.recent_menu
    menu.clear()
    paths = recent_paths(window.settings_store)
    menu.setEnabled(bool(paths))
    missing = False
    for path in paths:
        exists = available(path)
        missing |= not exists
        title = f"{path.name} ({path.parent.name})".replace("&", "&&")
        # Menu ownership ensures refreshes dispose the old actions instead of
        # accumulating children on the main window for the whole session.
        action = menu.addAction(title + (" — unavailable" if not exists else ""))
        action.setData(str(path))
        action.setToolTip(str(path))
        action.setStatusTip(str(path))
        action.setEnabled(exists)
        action.triggered.connect(lambda checked=False, path=path: window.open_recent(path))
    if paths:
        menu.addSeparator()
        if missing:
            remove = menu.addAction("Remove Unavailable Entries")
            remove.triggered.connect(lambda: clean_history(window, unavailable_only=True))
        clear = menu.addAction("Clear Recent Projects")
        clear.triggered.connect(lambda: clean_history(window))


def clean_history(window, *, unavailable_only=False):
    if window.settings_store is None:
        return
    paths = recent_paths(window.settings_store)
    retained = [str(path) for path in paths if available(path)] if unavailable_only else []
    window.settings_store.setValue("recent_projects", retained)
    update_menu(window)
    window.statusBar().showMessage("Unavailable recent-project entries removed" if unavailable_only
                                  else "Recent-project history cleared", 5000)
