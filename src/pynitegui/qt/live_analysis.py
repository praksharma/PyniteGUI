"""Debounced scheduling around the existing isolated analysis lifecycle."""
from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLineEdit


class LiveRecalculation(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.enabled = False
        self.pending = False
        self.ready = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.timeout)
        self.deferred = None
        self.publication_timer = QTimer(self)
        self.publication_timer.setSingleShot(True)
        self.publication_timer.setInterval(100)
        self.publication_timer.timeout.connect(self.publish)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            if self.window.result is None and (self.window.thread is None or
                                               self.window.analysis_revision != self.window.revision):
                self.schedule()
            else:
                self.window.statusBar().showMessage("Live recalculation enabled for completed model edits")
        else:
            self.discard()
            if self.window.thread is not None and self.window.analysis_automatic:
                self.window.cancel_analysis(user_requested=False)
            elif self.window.thread is None:
                self.window.cancel_analysis_action.setEnabled(False)
                state = "Current" if self.window.result is not None else "Outdated"
                self.window.results_panel.set_analysis_state(state)
                self.window.statusBar().showMessage("Live recalculation off | Use Analyze (F5)")

    def discard(self):
        self.timer.stop()
        self.publication_timer.stop()
        self.deferred = None
        self.pending = self.ready = False

    def editing_blocker(self):
        window = self.window
        if window.mcp_mode:
            return ""
        def belongs_to_project(widget):
            # Qt isAncestorOf stops at top-level dialog boundaries. Follow ownership.
            while widget is not None:
                if widget is window:
                    return True
                widget = widget.parentWidget()
            return False

        modal = QApplication.activeModalWidget()
        if belongs_to_project(modal):
            return "Close or finish this project's open editing dialog before automation edits/analysis."
        if window.planar_view.drag_node or window.planar_view.box_origin is not None:
            return "Finish the node drag or box selection, or press Escape to cancel it."
        if window.mode == "draw":
            return "Member drawing mode is active. Switch to Select mode to finish/cancel drawing before automation edits/analysis."
        focus = QApplication.focusWidget()
        if belongs_to_project(focus):
            current = focus
            while current is not None and current is not window:
                if current.property("pynitegui_non_model_controls"):
                    return ""
                current = current.parentWidget()
            if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
                return "Release the mouse button to finish the current editor gesture."
            editor = focus.findChild(QLineEdit) if isinstance(focus, QAbstractSpinBox) else focus
            if isinstance(editor, QLineEdit) and not editor.isReadOnly() and editor.isModified():
                return "An editable model input has an unfinished change. Apply or discard it before automation edits/analysis."
        return ""

    def is_editing(self):
        return bool(self.editing_blocker())

    def defer(self, result, error):
        self.deferred = (result, error, self.window.analysis_revision)
        self.window.results_panel.set_analysis_state("Pending", "Solve finished; waiting for the current input or gesture before refreshing results.")
        self.publication_timer.start()

    def publish(self):
        if self.deferred is None:
            return
        if self.is_editing() or self.window.thread is not None:
            self.publication_timer.start()
            return
        result, error, revision = self.deferred
        self.deferred = None
        if self.enabled and not self.pending and revision == self.window.revision and self.window.thread is None:
            self.window.cancel_analysis_action.setEnabled(False)
            self.window.analysis_finished(result, error)

    def schedule(self):
        if not self.enabled:
            return
        self.discard()
        if not self.window.project.members:
            return
        self.pending = True
        self.timer.start()
        self.window.cancel_analysis_action.setEnabled(True)
        if self.window.thread is not None and self.window.analysis_automatic:
            self.window.cancel_analysis(user_requested=False)
        self.window.results_panel.set_analysis_state("Pending", "Live recalculation waits 750 ms after completed model edits.")
        self.window.statusBar().showMessage("Live recalculation pending")

    def timeout(self):
        self.ready = True
        self.try_start()

    def try_start(self):
        if self.enabled and self.pending and self.ready and self.window.thread is None:
            if self.is_editing():
                self.timer.start()
                return
            self.discard()
            self.window.run_analysis(automatic=True)
