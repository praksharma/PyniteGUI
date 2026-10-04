"""Renderer-aware force-diagram labels, without changing diagram geometry."""
import math

from matplotlib.artist import Artist
from matplotlib.text import Annotation, Text


class LabelLayout(Artist):
    def __init__(self):
        super().__init__()
        self.set_zorder(6)
        self.set_in_layout(False)
        self.occupied = []
        self.obstacles = []

    def draw(self, renderer):
        # Axes limits and constrained layout are final by the time artists draw.
        self.occupied.clear()
        self.occupied.extend(artist.get_window_extent(renderer).padded(renderer.points_to_pixels(2))
                             for artist in self.obstacles if artist.get_visible())
        self.stale = False


class DiagramLabel(Annotation):
    def __init__(self, text, point, layout, color, background, member=False):
        self.layout = layout
        self.preferred = (5, -12) if member else (5, 5)
        self.placed = False
        super().__init__(text, point, xytext=self.preferred, textcoords="offset points", fontsize=8,
                         color=color, annotation_clip=True,
                         bbox={"facecolor": background, "edgecolor": "none", "alpha": 0.9, "pad": 1},
                         arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.5})
        self.set_zorder(7 if member else 8)
        self.set_in_layout(False)

    def draw(self, renderer):
        self.placed = False
        if not self.get_visible() or not self._check_xy(renderer):
            return
        candidates = [self.preferred]
        for radius in (18, 30, 45, 60):
            candidates.extend((radius * math.cos(angle * math.pi / 4), radius * math.sin(angle * math.pi / 4))
                              for angle in range(8))
        for offset in candidates:
            self.set_position(offset)
            self.update_positions(renderer)
            box = Text.get_window_extent(self, renderer).padded(renderer.points_to_pixels(2))
            area = self.axes.bbox
            if not (area.contains(box.x0, box.y0) and area.contains(box.x1, box.y1)):
                continue
            if any(box.overlaps(previous) for previous in self.layout.occupied):
                continue
            self.layout.occupied.append(box)
            self.placed = True
            self.arrow_patch.set_visible(math.hypot(*offset) >= 18)
            super().draw(renderer)
            return
        # Suppress crowded labels instead of printing overlapping values. A new
        # draw retries every label, so zooming or resizing can reveal them again.


def add_diagram_label(ax, text, point, color, background, member=False):
    layout = getattr(ax, "_diagram_label_layout", None)
    if layout is None:
        layout = LabelLayout()
        ax.add_artist(layout)
        ax._diagram_label_layout = layout
    label = DiagramLabel(text, point, layout, color, background, member)
    ax.add_artist(label)
    return label


def reserve_annotation(ax, artist):
    layout = getattr(ax, "_diagram_label_layout", None)
    if layout is not None:
        layout.obstacles.append(artist)
