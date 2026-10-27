"""Native saved-selection and elevation editor, using ordinary undo commands."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                              QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                              QTabWidget, QVBoxLayout, QWidget)
from .organization import level_selections, rename_entry, set_group, show_all, show_group


class OrganizationDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Groups and Levels")
        self.resize(600, 510)
        layout = QVBoxLayout(self)
        note = QLabel("Groups and global-Y levels organize editing. They do not restrain nodes, create diaphragms or change analysis.")
        note.setWordWrap(True)
        layout.addWidget(note)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        self.groups, self.levels = QListWidget(), QListWidget()
        self.group_name, self.level_name = QLineEdit(), QLineEdit()
        from .app import unit_number
        self.elevation = unit_number(0., window.project.units, "length")
        for title, listing, name in (("Groups", self.groups, self.group_name), ("Levels", self.levels, self.level_name)):
            page = QWidget()
            content = QVBoxLayout(page)
            content.addWidget(listing)
            form = QFormLayout()
            form.addRow("Name", name)
            content.addLayout(form)
            if title == "Groups":
                info = QLabel("Save uses the current node/member selection. Saving an existing name replaces that group. Empty groups remain after deletion and can be filled again.")
                info.setWordWrap(True)
                content.addWidget(info)
                self.group_buttons = self.buttons(content, (
                    ("Save current selection", self.save_group), ("Rename", self.rename_group), ("Delete", self.delete_group),
                    ("Select", lambda: self.select_group(False)), ("Isolate", lambda: self.select_group(True)),
                    ("Show all", lambda: show_all(window))))
            else:
                form.addRow(f"Global Y ({window.project.units.length})", self.elevation)
                self.snap = QCheckBox("Snap drawing and node drags to named levels")
                self.snap.setToolTip("Within 20% of grid spacing, choose the nearest level before grid snapping. Existing-node snaps take priority. Fixed work-plane coordinates stay fixed.")
                content.addWidget(self.snap)
                self.snap.toggled.connect(lambda value: self.change("Level snapping", lambda p: setattr(p, "snap_levels", value)))
                self.level_buttons = self.buttons(content, (
                    ("Save elevation", self.save_level), ("Rename", self.rename_level), ("Delete", self.delete_level),
                    ("Select at level", self.select_level), ("Use as XZ plane", self.use_plane)))
                self.level_buttons[-1].setVisible(getattr(window.project, "dimension", "2D") == "3D")
            tabs.addTab(page, title)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.groups.currentItemChanged.connect(self.group_changed)
        self.levels.currentItemChanged.connect(self.level_changed)
        self.reload()

    def buttons(self, layout, actions):
        # Two short rows remain usable at the minimum desktop width.
        result = []
        for i, (text, callback) in enumerate(actions):
            if i % 3 == 0:
                row = QHBoxLayout()
                layout.addLayout(row)
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
            result.append(button)
        return result

    @staticmethod
    def key(listing):
        item = listing.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def reload(self):
        p = self.window.project
        for listing, entries, detail in (
                (self.groups, p.groups, lambda g: f"{len(g['nodes'])} nodes, {len(g['members'])} members"),
                (self.levels, p.levels, lambda y: f"Y {p.units.to_display(y, 'length'):.6g} {p.units.length}")):
            chosen = self.key(listing)
            if chosen not in entries:
                chosen = (self.group_name if listing is self.groups else self.level_name).text()
            listing.blockSignals(True)
            listing.clear()
            for name, value in entries.items():
                item = QListWidgetItem(f"{name} | {detail(value)}")
                item.setData(Qt.ItemDataRole.UserRole, name)
                listing.addItem(item)
                if name == chosen:
                    listing.setCurrentItem(item)
            listing.blockSignals(False)
        self.snap.blockSignals(True)
        self.snap.setChecked(p.snap_levels)
        self.snap.blockSignals(False)

    def change(self, label, mutate):
        self.window.edit(label, mutate)
        self.reload()

    def group_changed(self):
        self.group_name.setText(self.key(self.groups) or "")

    def level_changed(self):
        name = self.key(self.levels)
        self.level_name.setText(name or "")
        if name is not None:
            self.elevation.setValue(self.window.project.units.to_display(self.window.project.levels[name], "length"))

    def save_group(self):
        self.change("Save group", lambda p: set_group(p, self.group_name.text(), self.window.selections))

    def rename_group(self):
        old, new = self.key(self.groups), self.group_name.text()
        isolated = old is not None and getattr(self.window, "isolated_group", None) == old
        self.change("Rename group", lambda p: rename_entry(p, "groups", old, new))
        if isolated and new in self.window.project.groups:
            show_group(self.window, new, True)

    def delete_group(self):
        name = self.key(self.groups)
        if name is not None:
            self.change("Delete group", lambda p: p.groups.pop(name))

    def select_group(self, isolate):
        show_group(self.window, self.key(self.groups), isolate)

    def save_level(self):
        from .app import unit_value
        self.change("Save level", lambda p: p.levels.__setitem__(self.level_name.text(), unit_value(self.elevation, p.units)))

    def rename_level(self):
        self.change("Rename level", lambda p: rename_entry(p, "levels", self.key(self.levels), self.level_name.text()))

    def delete_level(self):
        name = self.key(self.levels)
        if name is not None:
            self.change("Delete level", lambda p: p.levels.pop(name))

    def select_level(self):
        if self.window.mcp_mode:
            return
        name = self.key(self.levels)
        if name is not None:
            show_all(self.window)
            self.window.select_many(level_selections(self.window.project, self.window.project.levels[name]))
            if self.window.selections:
                self.window.fit_selection()

    def use_plane(self):
        if self.window.mcp_mode:
            return
        name = self.key(self.levels)
        if name is not None:
            view = self.window.view
            view.plane.setCurrentText("XZ")
            view.offset.setValue(self.window.project.units.to_display(self.window.project.levels[name], "length"))
