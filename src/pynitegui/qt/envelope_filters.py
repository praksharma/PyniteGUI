"""Scope existing envelope summaries without sampling or changing the solver."""
import math
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def filter_rows(rows, specification):
    scope = specification.get("entities")
    scope = None if scope is None else {tuple(identity) for identity in scope}
    component = specification.get("component")
    mode, threshold = specification.get("mode", "all"), specification.get("threshold", 0.)
    if mode not in ("all", "minimum", "maximum", "absolute"):
        raise ValueError("Unknown envelope value filter.")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
        raise ValueError("Threshold must be finite.")
    if mode != "all" and component is None:
        raise ValueError("Choose a component before applying a unit-aware threshold.")
    if mode == "absolute" and threshold < 0:
        raise ValueError("An absolute threshold cannot be negative.")
    for row in rows:
        kind, name, label, _, low, _, high, _ = row
        if scope is not None and (kind, name) not in scope:
            continue
        if component is not None and [kind, label] != list(component):
            continue
        if mode == "minimum" and (low is None or low > threshold):
            continue
        if mode == "maximum" and (high is None or high < threshold):
            continue
        if mode == "absolute" and not any(v is not None and abs(v) >= threshold for v in (low, high)):
            continue
        yield row


class EnvelopeFilters(QWidget):
    changed = Signal()

    def __init__(self, project, rows, selections):
        super().__init__()
        self.project, self.threshold_canonical, self.updating = project, 0., False
        self.scopes = {"all": None, "selection": [("Node" if k == "nodes" else "Member", n)
                       for k, n in selections if k in ("nodes", "members") and n in getattr(project, k)]}
        for name, group in project.groups.items():
            self.scopes["group:"+name] = [("Node" if kind == "nodes" else "Member", key)
                                         for kind in ("nodes", "members") for key in group[kind]]
        self.components = {}
        for kind, _, label, quantity, *_ in rows:
            self.components[f"{kind}:{label}"] = (kind, label, quantity)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.scope, self.member = QComboBox(), QComboBox()
        self.scope.addItem("All entities", "all")
        self.scope.addItem("Member ID", "member")
        self.scope.addItem("Selection at open", "selection")
        for name in project.groups:
            self.scope.addItem(f"Group: {name}", "group:"+name)
        self.member.addItems(list(project.members))
        self.member.setAccessibleName("Summary member ID")
        self.component = QComboBox()
        self.component.addItem("All components", None)
        for key in self.components:
            self.component.addItem(key, key)
        for label, control in (("Summary scope", self.scope), ("Member", self.member), ("Component", self.component)):
            row.addWidget(QLabel(label))
            row.addWidget(control)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.setToolTip("Choose one component first so threshold values have a single physical unit.")
        for label, key in (("All values", "all"), ("Minimum ≤", "minimum"), ("Maximum ≥", "maximum"), ("Absolute extreme ≥", "absolute")):
            self.mode.addItem(label, key)
        self.threshold = QDoubleSpinBox()
        self.threshold.setDecimals(8)
        self.threshold.setKeyboardTracking(False)
        self.count = QLabel()
        self.count.setWordWrap(True)
        row.addWidget(QLabel("Value filter"))
        row.addWidget(self.mode)
        row.addWidget(self.threshold)
        row.addWidget(self.count, 1)
        layout.addLayout(row)
        self.scope.currentIndexChanged.connect(self.controls_changed)
        self.member.currentTextChanged.connect(self.controls_changed)
        self.component.currentIndexChanged.connect(self.component_changed)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.threshold.valueChanged.connect(self.threshold_changed)
        self.refresh_units()

    def component_changed(self):
        self.threshold_canonical = 0.
        if self.component.currentData() is None:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(0)
            self.mode.blockSignals(False)
        self.controls_changed()

    def mode_changed(self):
        if self.mode.currentData() != "all" and self.component.currentData() is None and self.component.count() > 1:
            self.component.blockSignals(True)
            self.component.setCurrentIndex(1)
            self.component.blockSignals(False)
            self.threshold_canonical = 0.
        if self.mode.currentData() == "absolute":
            self.threshold_canonical = abs(self.threshold_canonical)
        self.controls_changed()

    def quantity(self):
        choice = self.components.get(self.component.currentData())
        return choice[2] if choice else "force"

    def refresh_units(self):
        self.updating = True
        try:
            for i in range(1, self.component.count()):
                kind, label, quantity = self.components[self.component.itemData(i)]
                unit = "rad" if quantity == "rotation" else getattr(self.project.units, quantity)
                self.component.setItemText(i, f"{kind} {label} ({unit})")
            quantity = self.quantity()
            unit = "rad" if quantity == "rotation" else getattr(self.project.units, quantity)
            bound = self.project.units.to_display(1e15, quantity)
            self.threshold.setRange(0. if self.mode.currentData() == "absolute" else -bound, bound)
            self.threshold.setSuffix(" "+unit)
            self.threshold.setValue(self.project.units.to_display(self.threshold_canonical, quantity))
            self.threshold.setEnabled(self.mode.currentData() != "all" and self.component.currentData() is not None)
            self.mode.setEnabled(self.component.currentData() is not None)
            self.member.setEnabled(self.scope.currentData() == "member")
        finally:
            self.updating = False

    def controls_changed(self):
        self.refresh_units()
        self.changed.emit()

    def threshold_changed(self):
        if not self.updating:
            self.threshold_canonical = self.project.units.from_display(self.threshold.value(), self.quantity())
            self.changed.emit()

    def specification(self):
        key = self.scope.currentData()
        component = self.components.get(self.component.currentData())
        return {"scope": self.scope.currentText(),
                "entities": [("Member", self.member.currentText())] if key == "member" else self.scopes[key],
                "component": list(component[:2]) if component else None,
                "mode": self.mode.currentData(), "threshold": self.threshold_canonical,
                "threshold_quantity": self.quantity() if component else None,
                "threshold_display": self.threshold.value(), "threshold_unit": self.threshold.suffix().strip()}
