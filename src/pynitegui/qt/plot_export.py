"""Snapshot-aware, atomic PNG/SVG export of the currently displayed plot."""
import json
import os
from pathlib import Path
import tempfile
import textwrap

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from PySide6.QtWidgets import QFileDialog, QMessageBox

from pynitegui import __version__
from .theme import colors


def snapshot_metadata(owner, plot, **context):
    result = owner.result
    combinations = context.pop("combinations", (result.combination,))
    if not combinations:
        raise ValueError("Select at least one analyzed combination before exporting a plot.")
    return {"application": f"Brecon {__version__}", "source": Path(owner.source).name,
            "snapshot_id": result.snapshot_id, "analyzed_at": result.analyzed_at,
            "model_signature": result.model_signature, "analysis_method": result.method_label,
            "combinations": list(combinations), "units": owner.project.units.summary,
            "plot": plot, **context}


def export_plot(path, figure, metadata, *, allow_other=False):
    path = Path(path)
    format = path.suffix.lower().lstrip(".")
    if format not in ("png", "svg") and not (allow_other and format in figure.canvas.get_supported_filetypes()):
        raise ValueError("Choose a .png or .svg filename.")
    description = json.dumps(metadata, sort_keys=True, ensure_ascii=True)
    title = f"{metadata['plot']} | {', '.join(metadata['combinations'])}"
    image_metadata = {"Title": title, "Description": description}
    image_metadata["Software" if format == "png" else "Creator"] = metadata["application"]
    footer = textwrap.fill(f"Analysis {metadata['snapshot_id']} | {metadata['analysis_method']} | "
                           f"{', '.join(metadata['combinations'])} | {metadata['units']}", 110)
    # The export stamp is outside the figure. Keep live zoom, layout, inspection
    # lines and annotations intact, including when serialization fails.
    layout = figure.get_layout_engine()
    axes = [(ax, ax.get_position(original=True).frozen(), ax.get_xlim(), ax.get_ylim(),
             ax.get_autoscalex_on(), ax.get_autoscaley_on(), ax.get_in_layout()) for ax in figure.axes]
    stamp, temporary = None, None
    try:
        figure.set_layout_engine("none")
        stamp = figure.text(.01, -.025, footer, fontsize=7, va="top", color=colors()["text"])
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=path.suffix, delete=False) as stream:
            temporary = Path(stream.name)
        options = {"metadata": image_metadata} if format in ("png", "svg") else {}
        figure.savefig(temporary, format=format, dpi=180, **options,
                       bbox_inches="tight", bbox_extra_artists=[stamp], facecolor=figure.get_facecolor())
        os.replace(temporary, path)
        return path
    finally:
        if stamp is not None:
            stamp.remove()
        for ax, position, xlim, ylim, autoscale_x, autoscale_y, in_layout in axes:
            ax.set_position(position)
            ax.set_xlim(xlim, emit=False)
            ax.set_ylim(ylim, emit=False)
            ax.set_autoscalex_on(autoscale_x)
            ax.set_autoscaley_on(autoscale_y)
            ax.set_in_layout(in_layout)
        figure.set_layout_engine(layout)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class SnapshotPlotToolbar(NavigationToolbar2QT):
    """Retain standard pan/zoom; Save adds snapshot identity to the image."""
    def __init__(self, canvas, parent, metadata):
        self.metadata = metadata
        super().__init__(canvas, parent)
        self._actions["save_figure"].setToolTip("Save the displayed plot as PNG/SVG with analysis snapshot details")

    def save_figure(self, *args):
        try:
            metadata = self.metadata()
            filename, selected = QFileDialog.getSaveFileName(self, "Save Snapshot Plot", "diagram.png",
                                                            "PNG image (*.png);;SVG vector image (*.svg);;Other Matplotlib formats (*.*)")
            if not filename:
                return
            path = Path(filename)
            if not path.suffix:
                path = path.with_suffix(".svg" if selected.startswith("SVG") else ".png")
                # The native dialog may have confirmed a suffixless name,
                # while the actual image destination is a different file.
                if path.exists() and QMessageBox.question(self, "Replace Existing Image", f"Replace {path.name}?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
            export_plot(path, self.canvas.figure, metadata, allow_other=selected.startswith("Other"))
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Could Not Export Plot", str(error))
