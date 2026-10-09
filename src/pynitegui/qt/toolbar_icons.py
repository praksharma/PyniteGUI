"""Small native vector icons that follow the application's text colour."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from .theme import colors


def tool_icon(name):
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(colors()["text"]), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if name == "select":
        painter.setBrush(QColor(colors()["text"]))
        painter.drawPolygon(QPolygonF([QPointF(5, 3), QPointF(5, 19), QPointF(10, 14), QPointF(15, 21), QPointF(18, 19), QPointF(13, 12), QPointF(20, 11)]))
    elif name == "member":
        painter.drawLine(5, 19, 19, 5)
        painter.setBrush(QColor(colors()["window"]))
        painter.drawEllipse(QPointF(5, 19), 2.5, 2.5)
        painter.drawEllipse(QPointF(19, 5), 2.5, 2.5)
    elif name == "pan":
        painter.drawLine(3, 12, 21, 12)
        painter.drawLine(12, 3, 12, 21)
        for x, y, a, b in ((3,12,6,9), (3,12,6,15), (21,12,18,9), (21,12,18,15),
                           (12,3,9,6), (12,3,15,6), (12,21,9,18), (12,21,15,18)):
            painter.drawLine(x, y, a, b)
    elif name == "load":
        painter.drawLine(12, 3, 12, 18)
        painter.drawLine(12, 18, 7, 12)
        painter.drawLine(12, 18, 17, 12)
        painter.drawLine(4, 21, 20, 21)
    elif name == "support":
        painter.drawPolygon(QPolygonF([QPointF(12, 5), QPointF(4, 17), QPointF(20, 17)]))
        painter.drawLine(3, 20, 21, 20)
        for x in (5, 10, 15, 20):
            painter.drawLine(x, 20, x-2, 23)
    elif name == "properties":
        painter.drawRect(3, 4, 18, 16)
        painter.drawLine(3, 9, 21, 9)
        painter.drawLine(10, 4, 10, 20)
        painter.drawLine(3, 14, 21, 14)
    elif name == "diagram":
        painter.drawLine(3, 19, 21, 19)
        path = QPainterPath(QPointF(3, 19))
        path.cubicTo(8, 2, 16, 2, 21, 19)
        painter.drawPath(path)
        for x, top in ((7, 10), (12, 7), (17, 10)):
            painter.drawLine(x, 19, x, top)
    elif name == "live":
        painter.drawArc(4, 4, 16, 16, 45*16, 290*16)
        painter.drawLine(19, 5, 19, 11)
        painter.drawLine(19, 11, 13, 11)
    painter.end()
    return QIcon(pixmap)
