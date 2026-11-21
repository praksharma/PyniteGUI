"""Staged pressure-case, combination and horizontal self-weight editing."""
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                              QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                              QLineEdit, QMessageBox, QPushButton, QTableWidget,
                              QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .plate_model import PlateDefinition, plate_point_load_directions


class PlateLoadsDialog(QDialog):
    def __init__(self, parent, definition):
        super().__init__(parent)
        from dataclasses import replace
        self.definition = replace(definition, material=replace(definition.material),
                                  origin=list(definition.origin), x_control=list(definition.x_control),
                                  y_control=list(definition.y_control),
                                  openings=[dict(item) for item in definition.openings],
                                  edges=dict(definition.edges),
                                  additional_pressures=dict(definition.additional_pressures),
                                  combinations={k: dict(v) for k, v in definition.combinations.items()},
                                  pressure_profiles={k: dict(v) for k, v in definition.pressure_profiles.items()},
                                  point_loads=[dict(item) for item in definition.point_loads],
                                  wall_supports=[dict(item) for item in definition.wall_supports],
                                  wall_stories=[dict(item) for item in definition.wall_stories],
                                  wall_loads=[dict(item) for item in definition.wall_loads])
        self.setWindowTitle("Plate Load Cases and Combinations")
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        note = QLabel("Choose uniform pressure or linear variation along local x (width) / y (height). "
                      "The first pressure is at coordinate zero; the end pressure is at the opposite edge. "
                      "Profiles follow the geometry through remeshing, holes and placement. Each element receives its centroid pressure: compare mesh refinements. "
                      "Signed profiles may cross zero; they are not automatically clipped at a liquid surface. "
                      "Plate uses the primary case/factor; named combinations combine all cases. Self-weight adds global -Y pressure on horizontal XZ plates only.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.cases, self.combinations, self.point_loads = QTableWidget(), QTableWidget(), QTableWidget()
        self.wall_stories, self.wall_loads, self.wall_supports = QTableWidget(), QTableWidget(), QTableWidget()
        self.buttons = {}
        for kind, table, title in (("cases", self.cases, "Pressure cases"),
                                   ("combinations", self.combinations, "Combinations"),
                                   ("point_loads", self.point_loads, "Point loads"),
                                   ("wall_stories", self.wall_stories, "Wall stories"),
                                   ("wall_loads", self.wall_loads, "Wall story loads"),
                                   ("wall_supports", self.wall_supports, "Wall supports")):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            table.setObjectName("plate_load_"+kind)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            page_layout.addWidget(table)
            row = QHBoxLayout()
            actions = (("add", "Add"), ("delete", "Delete")) if kind in ("point_loads", "wall_stories", "wall_loads", "wall_supports") else (
                ("add", "Add…"), ("edit", "Rename…" if kind == "cases" else "Edit…"), ("delete", "Delete"))
            for action, text in actions:
                button = QPushButton(text)
                button.clicked.connect(lambda checked=False, kind=kind, action=action: self.perform(kind, action))
                self.buttons[kind, action] = button
                row.addWidget(button)
            row.addStretch()
            page_layout.addLayout(row)
            self.tabs.addTab(page, title)
            table.itemSelectionChanged.connect(self.update_buttons)
        form = QFormLayout()
        self.weight_case = QComboBox()
        self.weight_case.setObjectName("plate_weight_case")
        from .app import number
        self.weight_factor = number(self.definition.self_weight_factor, 1e-8, 1e6, 8)
        self.weight_factor.setObjectName("plate_weight_factor")
        self.weight_factor.setProperty("canonical", self.definition.self_weight_factor)
        self.weight_factor.setProperty("initial", self.weight_factor.value())
        form.addRow("Self-weight case", self.weight_case)
        form.addRow("Self-weight multiplier", self.weight_factor)
        density = self.definition.units.to_display(self.definition.material.rho, "density")
        form.addRow("Material weight density", QLabel(f"{density:.8g} {self.definition.units.density}"))
        self.weight_case.setEnabled(self.definition.plane == "XZ" or self.definition.self_weight_case is not None)
        self.weight_factor.setEnabled(self.definition.plane == "XZ")
        self.weight_case.setToolTip("Choose the horizontal XZ plane and set material weight density in the main plate controls before enabling self-weight.")
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def selected(self, kind):
        if kind in ("point_loads", "wall_stories", "wall_loads", "wall_supports"):
            table = getattr(self, kind)
            row = table.currentRow()
            return row if 0 <= row < table.rowCount() else None
        table = self.cases if kind == "cases" else self.combinations
        item = table.item(table.currentRow(), 0)
        return item.text() if item else None

    def read_inputs(self):
        from .app import unit_value
        values = {};profiles={}
        for row in range(self.cases.rowCount()):
            widget = self.cases.cellWidget(row, 1)
            widget.interpretText()
            name=self.cases.item(row,0).text()
            values[name] = unit_value(widget, self.definition.units, "pressure")
            axis=self.cases.cellWidget(row,3).currentData()
            if axis is not None:
                end=self.cases.cellWidget(row,4);end.interpretText()
                profiles[name]={'axis':axis,'end_pressure':unit_value(end,self.definition.units,'pressure')}
        self.definition.pressure = values.pop(self.definition.load_case)
        self.definition.additional_pressures = values
        self.definition.pressure_profiles = profiles
        point_loads = []
        for row in range(self.point_loads.rowCount()):
            case_box = self.point_loads.cellWidget(row, 0)
            x_widget = self.point_loads.cellWidget(row, 1)
            y_widget = self.point_loads.cellWidget(row, 2)
            dir_box = self.point_loads.cellWidget(row, 3)
            mag_widget = self.point_loads.cellWidget(row, 4)
            x_widget.interpretText(); y_widget.interpretText(); mag_widget.interpretText()
            direction = dir_box.currentText()
            quantity = "moment" if direction.startswith("M") else "force"
            point_loads.append({
                "case": case_box.currentText(),
                "x": unit_value(x_widget, self.definition.units, "length"),
                "y": unit_value(y_widget, self.definition.units, "length"),
                "direction": direction,
                "magnitude": unit_value(mag_widget, self.definition.units, quantity),
            })
        self.definition.point_loads = point_loads
        old_story_names = [s["name"] for s in self.definition.wall_stories]
        wall_stories = []
        story_rename = {}
        for row in range(self.wall_stories.rowCount()):
            name_edit = self.wall_stories.cellWidget(row, 0)
            elev = self.wall_stories.cellWidget(row, 1); elev.interpretText()
            x0 = self.wall_stories.cellWidget(row, 2); x0.interpretText()
            x1 = self.wall_stories.cellWidget(row, 3); x1.interpretText()
            new_name = name_edit.text().strip()
            if row < len(old_story_names) and old_story_names[row] != new_name:
                story_rename[old_story_names[row]] = new_name
            wall_stories.append({
                "name": new_name,
                "elevation": unit_value(elev, self.definition.units, "length"),
                "x_start": unit_value(x0, self.definition.units, "length"),
                "x_end": unit_value(x1, self.definition.units, "length"),
            })
        self.definition.wall_stories = wall_stories
        wall_loads = []
        for row in range(self.wall_loads.rowCount()):
            story_box = self.wall_loads.cellWidget(row, 0)
            case_box = self.wall_loads.cellWidget(row, 1)
            kind_box = self.wall_loads.cellWidget(row, 2)
            mag = self.wall_loads.cellWidget(row, 3); mag.interpretText()
            chosen_story = story_rename.get(story_box.currentText(), story_box.currentText())
            wall_loads.append({
                "story": chosen_story,
                "case": case_box.currentText(),
                "kind": kind_box.currentData(),
                "magnitude": unit_value(mag, self.definition.units, "force"),
            })
        self.definition.wall_loads = wall_loads
        wall_supports = []
        for row in range(self.wall_supports.rowCount()):
            elev = self.wall_supports.cellWidget(row, 0); elev.interpretText()
            x0 = self.wall_supports.cellWidget(row, 1); x0.interpretText()
            x1 = self.wall_supports.cellWidget(row, 2); x1.interpretText()
            wall_supports.append({
                "elevation": unit_value(elev, self.definition.units, "length"),
                "x_start": unit_value(x0, self.definition.units, "length"),
                "x_end": unit_value(x1, self.definition.units, "length"),
            })
        self.definition.wall_supports = wall_supports
        self.definition.self_weight_case = self.weight_case.currentData()
        self.weight_factor.interpretText()
        self.definition.self_weight_factor = (self.weight_factor.property("canonical")
            if self.weight_factor.value() == self.weight_factor.property("initial") else self.weight_factor.value())

    def refresh(self, kind=None, selected=None):
        from .app import unit_number
        selection = selected if kind == "cases" else self.selected("cases")
        self.cases.blockSignals(True)
        self.cases.setColumnCount(5)
        self.cases.setHorizontalHeaderLabels(["Case", f"Pressure at zero ({self.definition.units.pressure})", "Role", "Profile", f"End pressure ({self.definition.units.pressure})"])
        self.cases.setRowCount(len(self.definition.load_cases))
        for row, (name, pressure) in enumerate(self.definition.case_pressures.items()):
            self.cases.setItem(row, 0, QTableWidgetItem(name))
            field = unit_number(pressure, self.definition.units, "pressure", decimals=10)
            self.cases.setCellWidget(row, 1, field)
            self.cases.setItem(row, 2, QTableWidgetItem("Primary" if name == self.definition.load_case else "Additional"))
            profile=self.definition.pressure_profiles.get(name,{})
            axis=QComboBox();axis.addItem('Uniform',None);axis.addItem('Linear local x','x');axis.addItem('Linear local y','y')
            axis.setObjectName('plate_profile_'+name);axis.setCurrentIndex(axis.findData(profile.get('axis')))
            end=unit_number(profile.get('end_pressure',pressure),self.definition.units,'pressure',decimals=10)
            end.setObjectName('plate_end_pressure_'+name);end.setEnabled(bool(profile))
            axis.currentIndexChanged.connect(lambda index,end=end:end.setEnabled(index!=0))
            self.cases.setCellWidget(row,3,axis);self.cases.setCellWidget(row,4,end)
            if name == selection or (selection not in self.definition.load_cases and row == 0):
                self.cases.selectRow(row)
        self.cases.resizeColumnsToContents()
        self.cases.horizontalHeader().setStretchLastSection(True)
        self.cases.blockSignals(False)
        selection = selected if kind == "combinations" else self.selected("combinations")
        self.combinations.blockSignals(True)
        self.combinations.setColumnCount(2)
        self.combinations.setHorizontalHeaderLabels(["Combination", "Case factors"])
        self.combinations.setRowCount(len(self.definition.load_combinations))
        for row, (name, factors) in enumerate(self.definition.load_combinations.items()):
            self.combinations.setItem(row, 0, QTableWidgetItem(name))
            self.combinations.setItem(row, 1, QTableWidgetItem("; ".join(f"{case}: {factor:g}" for case, factor in factors.items())))
            if name == selection or (selection not in self.definition.load_combinations and row == 0):
                self.combinations.selectRow(row)
        self.combinations.resizeColumnsToContents()
        self.combinations.setColumnWidth(0, max(140, self.combinations.columnWidth(0)))
        self.combinations.horizontalHeader().setStretchLastSection(True)
        self.combinations.blockSignals(False)
        pt_row = selected if kind == "point_loads" else self.selected("point_loads")
        self.point_loads.blockSignals(True)
        self.point_loads.setColumnCount(5)
        self.point_loads.setHorizontalHeaderLabels([
            "Case", f"Local x ({self.definition.units.length})", f"Local y ({self.definition.units.length})",
            "Direction", f"Magnitude ({self.definition.units.force} or {self.definition.units.moment})"])
        self.point_loads.setRowCount(len(self.definition.point_loads))
        directions = list(plate_point_load_directions(self.definition.plane, self.definition.analysis_mode))
        for row, load in enumerate(self.definition.point_loads):
            for col in range(5):
                self.point_loads.setItem(row, col, QTableWidgetItem(""))
            case_box = QComboBox()
            case_box.addItems(self.definition.load_cases)
            case_box.setCurrentText(load["case"])
            x_field = unit_number(load["x"], self.definition.units, "length", decimals=8)
            y_field = unit_number(load["y"], self.definition.units, "length", decimals=8)
            dir_box = QComboBox()
            dir_box.addItems(directions)
            dir_box.setCurrentText(load["direction"])
            quantity = "moment" if load["direction"].startswith("M") else "force"
            mag_field = unit_number(load["magnitude"], self.definition.units, quantity, decimals=8)
            dir_box.currentTextChanged.connect(lambda _text, widget=mag_field: widget.setProperty("initial", None))
            self.point_loads.setCellWidget(row, 0, case_box)
            self.point_loads.setCellWidget(row, 1, x_field)
            self.point_loads.setCellWidget(row, 2, y_field)
            self.point_loads.setCellWidget(row, 3, dir_box)
            self.point_loads.setCellWidget(row, 4, mag_field)
            if row == pt_row or (pt_row is None and row == 0):
                self.point_loads.selectRow(row)
        self.point_loads.resizeColumnsToContents()
        self.point_loads.horizontalHeader().setStretchLastSection(True)
        self.point_loads.blockSignals(False)
        st_row = selected if kind == "wall_stories" else self.selected("wall_stories")
        self.wall_stories.blockSignals(True)
        self.wall_stories.setColumnCount(4)
        self.wall_stories.setHorizontalHeaderLabels([
            "Story", f"Elevation y ({self.definition.units.length})",
            f"Start x ({self.definition.units.length})", f"End x ({self.definition.units.length})"])
        self.wall_stories.setRowCount(len(self.definition.wall_stories))
        for row, story in enumerate(self.definition.wall_stories):
            for col in range(4):
                self.wall_stories.setItem(row, col, QTableWidgetItem(""))
            self.wall_stories.setCellWidget(row, 0, QLineEdit(story["name"]))
            self.wall_stories.setCellWidget(row, 1, unit_number(story["elevation"], self.definition.units, "length", decimals=8))
            self.wall_stories.setCellWidget(row, 2, unit_number(story["x_start"], self.definition.units, "length", decimals=8))
            self.wall_stories.setCellWidget(row, 3, unit_number(story["x_end"], self.definition.units, "length", decimals=8))
            if row == st_row or (st_row is None and row == 0):
                self.wall_stories.selectRow(row)
        self.wall_stories.resizeColumnsToContents()
        self.wall_stories.horizontalHeader().setStretchLastSection(True)
        self.wall_stories.blockSignals(False)
        wl_row = selected if kind == "wall_loads" else self.selected("wall_loads")
        self.wall_loads.blockSignals(True)
        self.wall_loads.setColumnCount(4)
        self.wall_loads.setHorizontalHeaderLabels([
            "Story", "Case", "Kind", f"Force ({self.definition.units.force})"])
        self.wall_loads.setRowCount(len(self.definition.wall_loads))
        story_names = [s["name"] for s in self.definition.wall_stories]
        for row, load in enumerate(self.definition.wall_loads):
            for col in range(4):
                self.wall_loads.setItem(row, col, QTableWidgetItem(""))
            st_box = QComboBox(); st_box.addItems(story_names or [load["story"]]); st_box.setCurrentText(load["story"])
            cs_box = QComboBox(); cs_box.addItems(self.definition.load_cases); cs_box.setCurrentText(load["case"])
            kd_box = QComboBox(); kd_box.addItem("Shear (+local x)", "shear"); kd_box.addItem("Axial (-local y)", "axial")
            kd_box.setCurrentIndex(max(0, kd_box.findData(load["kind"])))
            self.wall_loads.setCellWidget(row, 0, st_box)
            self.wall_loads.setCellWidget(row, 1, cs_box)
            self.wall_loads.setCellWidget(row, 2, kd_box)
            self.wall_loads.setCellWidget(row, 3, unit_number(load["magnitude"], self.definition.units, "force", decimals=8))
            if row == wl_row or (wl_row is None and row == 0):
                self.wall_loads.selectRow(row)
        self.wall_loads.resizeColumnsToContents()
        self.wall_loads.horizontalHeader().setStretchLastSection(True)
        self.wall_loads.blockSignals(False)
        ws_row = selected if kind == "wall_supports" else self.selected("wall_supports")
        self.wall_supports.blockSignals(True)
        self.wall_supports.setColumnCount(3)
        self.wall_supports.setHorizontalHeaderLabels([
            f"Elevation y ({self.definition.units.length})",
            f"Start x ({self.definition.units.length})", f"End x ({self.definition.units.length})"])
        self.wall_supports.setRowCount(len(self.definition.wall_supports))
        for row, sup in enumerate(self.definition.wall_supports):
            for col in range(3):
                self.wall_supports.setItem(row, col, QTableWidgetItem(""))
            self.wall_supports.setCellWidget(row, 0, unit_number(sup["elevation"], self.definition.units, "length", decimals=8))
            self.wall_supports.setCellWidget(row, 1, unit_number(sup["x_start"], self.definition.units, "length", decimals=8))
            self.wall_supports.setCellWidget(row, 2, unit_number(sup["x_end"], self.definition.units, "length", decimals=8))
            if row == ws_row or (ws_row is None and row == 0):
                self.wall_supports.selectRow(row)
        self.wall_supports.resizeColumnsToContents()
        self.wall_supports.horizontalHeader().setStretchLastSection(True)
        self.wall_supports.blockSignals(False)
        self.weight_case.blockSignals(True)
        self.weight_case.clear()
        self.weight_case.addItem("Off", None)
        for name in self.definition.load_cases:
            self.weight_case.addItem(name, name)
        self.weight_case.setCurrentIndex(max(0, self.weight_case.findData(self.definition.self_weight_case)))
        self.weight_case.blockSignals(False)
        self.update_buttons()

    def update_buttons(self):
        if len(self.buttons) < 14:
            return
        case, combination = self.selected("cases"), self.selected("combinations")
        self.buttons["cases", "edit"].setEnabled(case is not None)
        self.buttons["cases", "delete"].setEnabled(case is not None and case != self.definition.load_case)
        for action in ("edit", "delete"):
            self.buttons["combinations", action].setEnabled(combination is not None and combination != "Plate")
        self.buttons["combinations", "edit"].setToolTip("Plate uses the primary case/factor from the main controls; named combinations can mix all cases.")
        for key in ("point_loads", "wall_stories", "wall_loads", "wall_supports"):
            self.buttons[key, "delete"].setEnabled(self.selected(key) is not None)

    def perform(self, kind, action):
        from .load_cases import CombinationEditor
        self.read_inputs()
        previous = self.selected(kind)
        if action != "add" and previous is None:
            return
        try:
            if kind == "point_loads":
                if action == "add":
                    if len(self.definition.point_loads) >= 64:
                        raise ValueError("Use at most 64 concentrated plate point loads.")
                    directions = plate_point_load_directions(self.definition.plane, self.definition.analysis_mode)
                    self.definition.point_loads.append({
                        "case": self.definition.load_case,
                        "x": self.definition.width / 2.,
                        "y": self.definition.height / 2.,
                        "direction": directions[0],
                        "magnitude": 0.,
                    })
                    self.refresh("point_loads", len(self.definition.point_loads) - 1)
                else:
                    del self.definition.point_loads[previous]
                    self.refresh("point_loads", min(previous, len(self.definition.point_loads) - 1) if self.definition.point_loads else None)
                return
            if kind == "wall_stories":
                if action == "add":
                    if len(self.definition.wall_stories) >= 32:
                        raise ValueError("Use at most 32 shear wall stories.")
                    existing = {s["name"] for s in self.definition.wall_stories}
                    name = next(f"Story_{i}" for i in range(1, 34) if f"Story_{i}" not in existing)
                    self.definition.wall_stories.append({
                        "name": name, "elevation": self.definition.height,
                        "x_start": 0., "x_end": self.definition.width,
                    })
                    self.refresh("wall_stories", len(self.definition.wall_stories) - 1)
                else:
                    story_name = self.definition.wall_stories[previous]["name"]
                    if any(load["story"] == story_name for load in self.definition.wall_loads):
                        raise ValueError("Remove wall story loads referencing this story before deleting it.")
                    del self.definition.wall_stories[previous]
                    self.refresh("wall_stories", min(previous, len(self.definition.wall_stories) - 1) if self.definition.wall_stories else None)
                return
            if kind == "wall_loads":
                if action == "add":
                    if not self.definition.wall_stories:
                        raise ValueError("Add at least one wall story before adding a story load.")
                    if len(self.definition.wall_loads) >= 64:
                        raise ValueError("Use at most 64 shear wall story loads.")
                    self.definition.wall_loads.append({
                        "story": self.definition.wall_stories[0]["name"],
                        "case": self.definition.load_case,
                        "kind": "shear",
                        "magnitude": 10.,
                    })
                    self.refresh("wall_loads", len(self.definition.wall_loads) - 1)
                else:
                    del self.definition.wall_loads[previous]
                    self.refresh("wall_loads", min(previous, len(self.definition.wall_loads) - 1) if self.definition.wall_loads else None)
                return
            if kind == "wall_supports":
                if action == "add":
                    if len(self.definition.wall_supports) >= 16:
                        raise ValueError("Use at most 16 shear wall support segments.")
                    self.definition.wall_supports.append({
                        "elevation": 0., "x_start": 0., "x_end": self.definition.width,
                    })
                    self.refresh("wall_supports", len(self.definition.wall_supports) - 1)
                else:
                    del self.definition.wall_supports[previous]
                    self.refresh("wall_supports", min(previous, len(self.definition.wall_supports) - 1) if self.definition.wall_supports else None)
                return
            if kind == "cases":
                if action == "delete":
                    if (previous == self.definition.load_case or previous == self.definition.self_weight_case or
                            any(previous in factors for factors in self.definition.combinations.values()) or
                            any(load["case"] == previous for load in self.definition.point_loads) or
                            any(load["case"] == previous for load in self.definition.wall_loads)):
                        raise ValueError("Remove combination/self-weight/point-load/wall-load references before deleting an additional case; keep the primary case.")
                    del self.definition.additional_pressures[previous]
                    self.definition.pressure_profiles.pop(previous,None)
                else:
                    name, accepted = QInputDialog.getText(self, "Add Pressure Case" if action == "add" else "Rename Pressure Case", "Name", text="" if action == "add" else previous)
                    if not accepted:
                        return
                    name = name.strip()
                    self.definition.validate_load_name(name)
                    if action == "add":
                        if name in self.definition.load_cases:
                            raise ValueError("A pressure case with that name already exists.")
                        if len(self.definition.load_cases) >= 32:
                            raise ValueError("Use at most 32 pressure cases.")
                        self.definition.additional_pressures[name] = 0.
                    else:
                        self.definition.rename_case(previous, name)
                    self.refresh(kind, name)
                    return
            elif action == "delete":
                if previous == "Plate":
                    raise ValueError("Keep the primary Plate combination.")
                del self.definition.combinations[previous]
            else:
                if action == "add" and len(self.definition.load_combinations) >= 32:
                    raise ValueError("Use at most 32 plate combinations.")
                name = previous if action == "edit" else next(f"Combination {i}" for i in range(1, 33) if f"Combination {i}" not in self.definition.combinations)
                factors = self.definition.combinations[previous] if action == "edit" else {self.definition.load_case: 1.}
                editor = CombinationEditor(self, self.definition, name, factors, previous if action == "edit" else None)
                if editor.exec() != QDialog.DialogCode.Accepted:
                    return
                name, factors = editor.definition
                if action == "edit":
                    del self.definition.combinations[previous]
                self.definition.combinations[name] = factors
                self.refresh(kind, name)
                return
            self.refresh()
        except ValueError as error:
            QMessageBox.warning(self, "Plate Loading", str(error))

    def accept(self):
        self.read_inputs()
        try:
            self.definition.validate()
        except ValueError as error:
            QMessageBox.warning(self, "Plate Loading", str(error))
            return
        super().accept()
