"""Native dimensioned catalog sketches; solver properties remain independent."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget
from .section_library import DIMENSIONS
from .theme import colors


class SectionPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 240)
        self.setAccessibleName("Dimensioned section sketch")
        self.designation, self.weak, self.units = None, False, None

    def set_section(self, designation, weak, units):
        self.designation, self.weak, self.units = designation, weak, units
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = colors()
        painter.fillRect(self.rect(), QColor(c["canvas"]))
        painter.setPen(QColor(c["text"]))
        if self.designation is None:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No section selected")
            return
        d = DIMENSIONS[self.designation]
        width, height = (d.depth, d.width) if self.weak else (d.width, d.depth)
        scale = min((self.width()-110)/width, (self.height()-120)/height)
        cx, cy = self.width()/2+12, self.height()/2+8
        painter.save()
        painter.translate(cx, cy)
        if self.weak:
            painter.rotate(-90)
        painter.scale(scale, scale)
        pen = QPen(QColor(c["member"]), 1.3)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(c["accent"]))
        w, h = d.width, d.depth
        if d.shape == "I":
            for rect in (QRectF(-w/2, -h/2, w, d.flange), QRectF(-w/2, h/2-d.flange, w, d.flange),
                         QRectF(-d.web/2, -h/2+d.flange, d.web, h-2*d.flange)):
                painter.drawRect(rect)
        else:
            outside = QRectF(-w/2, -h/2, w, h)
            inside = outside.adjusted(d.design, d.design, -d.design, -d.design)
            draw = painter.drawEllipse if d.shape == "round" else painter.drawRect
            draw(outside)
            painter.setBrush(QColor(c["canvas"]))
            draw(inside)
        painter.restore()
        # Axes are fixed local y/z; the weak-axis sketch rotates inside them.
        painter.setPen(QPen(QColor(c["label"]), 1.))
        painter.drawLine(QPointF(cx, cy), QPointF(cx, cy-36))
        painter.drawLine(QPointF(cx, cy), QPointF(cx+36, cy))
        painter.drawText(QPointF(cx+4, cy-29), "y")
        painter.drawText(QPointF(cx+29, cy-5), "z")
        x, y = cx-width*scale/2, cy-height*scale/2
        right, bottom = x+width*scale, y+height*scale
        painter.setPen(QPen(QColor(c["text"]), 1.))
        painter.drawLine(QPointF(x, bottom+16), QPointF(right, bottom+16))
        for edge in (x, right):
            painter.drawLine(QPointF(edge, bottom+11), QPointF(edge, bottom+21))
        painter.drawLine(QPointF(x-16, y), QPointF(x-16, bottom))
        for edge in (y, bottom):
            painter.drawLine(QPointF(x-21, edge), QPointF(x-11, edge))
        h_label, w_label = ("d", "bf") if d.shape == "I" else ("OD", "OD") if d.shape == "round" else ("Ht", "B")
        if self.weak:
            h_label, w_label = w_label, h_label
        painter.drawText(QRectF(x-25, bottom+22, width*scale+50, 22), Qt.AlignmentFlag.AlignCenter,
                         f"{w_label} = {self.units.to_display(width, 'length'):.5g} {self.units.length}")
        painter.save()
        painter.translate(x-25, cy)
        painter.rotate(-90)
        painter.drawText(QRectF(-height*scale/2, -22, height*scale, 22), Qt.AlignmentFlag.AlignCenter,
                         f"{h_label} = {self.units.to_display(height, 'length'):.5g} {self.units.length}")
        painter.restore()

    def apply_theme(self):
        self.update()
