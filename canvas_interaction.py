#// 文件3：原路径/canvas.py

from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect, QSize, QMimeData
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import *


# =========================================================
# 常量 / 主题
# =========================================================

画布最小宽高 = 50
画布最大宽高 = 5000


支持布局类 = ("QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout")

布局区域填充色 = QColor(90, 120, 200, 24)
布局区域边框色 = QColor(80, 110, 190)
布局区域标签色 = QColor(70, 90, 160)

框选边框色 = QColor(80, 140, 255)
框选填充色 = QColor(80, 140, 255, 40)

表面背景色 = QColor("#f5f5f5")
表面边框色 = QColor("#cccccc")





# =========================================================
# 工具函数
# =========================================================

def _限制整数(value, min_value: int, max_value: int, default: int) -> int:
    try:
        v = int(value)
    except Exception:
        v = default
    return max(min_value, min(v, max_value))


def _安全取几何(props: dict, default_w=100, default_h=30) -> dict:
    geo = props.get("geometry", {}) if isinstance(props, dict) else {}
    return {
        "x": _限制整数(geo.get("x", 0), -画布最大宽高, 画布最大宽高, 0),
        "y": _限制整数(geo.get("y", 0), -画布最大宽高, 画布最大宽高, 0),
        "width": _限制整数(geo.get("width", default_w), 1, 画布最大宽高, default_w),
        "height": _限制整数(geo.get("height", default_h), 1, 画布最大宽高, default_h),
    }


def _布局默认名(layout_class: str) -> str:
    return {
        "QVBoxLayout": "verticalLayout",
        "QHBoxLayout": "horizontalLayout",
        "QGridLayout": "gridLayout",
        "QFormLayout": "formLayout",
    }.get(layout_class, "layout")


def _布局区域显示名(layout_class: str) -> str:
    return {
        "QVBoxLayout": "Vertical Layout Region",
        "QHBoxLayout": "Horizontal Layout Region",
        "QGridLayout": "Grid Layout Region",
        "QFormLayout": "Form Layout Region",
    }.get(layout_class, "Layout Region")




# =========================================================
# 设计期控件 / 构造器
# =========================================================

class 设计期布局区域控件(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_class = "QVBoxLayout"
        self.setObjectName("layout_region_runtime")
        self.setMouseTracking(True)
        self.setAutoFillBackground(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumSize(40, 30)

    def 设置布局类型(self, layout_class: str):
        self._layout_class = layout_class or "QVBoxLayout"
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        qp.setPen(QPen(布局区域边框色, 1, Qt.DashLine))
        qp.setBrush(Qt.NoBrush)
        qp.drawRect(rect)

        label_rect = QRect(6, 4, max(0, rect.width() - 12), 20)
        if label_rect.width() > 20:
            qp.setPen(布局区域标签色)
            # qp.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, _布局区域显示名(self._layout_class))
        qp.end()


_控件构造器 = {
    "QPushButton": QPushButton,
    "QLabel": QLabel,
    "QTextEdit": QTextEdit,
    "QLineEdit": QLineEdit,
    "QTabWidget": QTabWidget,
    "QToolBox": QToolBox,
    "QGroupBox": QGroupBox,
    "QWidget": QWidget,
    "__LayoutRegion__": 设计期布局区域控件,
}

_布局构造器 = {
    "QVBoxLayout": QVBoxLayout,
    "QHBoxLayout": QHBoxLayout,
    "QGridLayout": QGridLayout,
    "QFormLayout": QFormLayout,
}


# =========================================================
# 根表层
# =========================================================

class 根表层(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setObjectName("root_surface")
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def paintEvent(self, event):
        editor = self._editor
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        qp.fillRect(rect, 表面背景色)
        qp.setPen(QPen(表面边框色, 1))
        qp.setBrush(Qt.NoBrush)
        qp.drawRect(rect.adjusted(0, 0, -1, -1))

        editor._绘制点阵网格(qp, rect.adjusted(1, 1, -1, -1))
        editor._绘制布局高亮(qp)

        for node_id in editor.获取当前选中节点id列表():
            widget = editor._节点到控件.get(node_id)
            if widget is None:
                continue
            widget_rect = editor._控件根表面矩形(widget)
            if editor._节点可缩放(node_id):
                editor._绘制缩放控制点(qp, widget_rect)

        if editor._框选中 and editor._操作模式 == "select_rect":
            select_rect = editor._当前框选矩形()
            qp.setPen(QPen(框选边框色, 1, Qt.DashLine))
            qp.setBrush(框选填充色)
            qp.drawRect(select_rect)

        qp.end()

    def mousePressEvent(self, event):
        if self._editor._根表层鼠标按下(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._editor._根表层鼠标移动(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._editor._根表层鼠标释放(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        self._editor._根表层拖入(event)

    def dragMoveEvent(self, event):
        self._editor._根表层拖动(event)

    def dropEvent(self, event):
        self._editor._根表层放下(event)

