from __future__ import annotations
from dataclasses import dataclass, field
from PySide6.QtCore import Signal
from PySide6.QtWidgets import *

from model import NodeModel, UiDocument
from canvas_interaction import _限制整数, _安全取几何, _布局默认名, 画布最小宽高, 画布最大宽高, 支持布局类



无布局选项 = "无布局"

# =========================================================
# 属性面板 / 控件箱
# =========================================================

class 属性面板(QWidget):
    节点属性提交 = Signal(dict)
    文档属性提交 = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._当前节点id = None
        self._当前类型 = None
        self._当前kind = None
        self._文档模式 = False
        self._正在填充 = False

        self._布局 = QVBoxLayout(self)
        self._表单 = QFormLayout()
        self._布局.addLayout(self._表单)
        self._布局.addStretch()

        self._node_id = QLineEdit()
        self._node_id.setReadOnly(True)
        self._kind = QLineEdit()
        self._kind.setReadOnly(True)
        self._type_name = QLineEdit()
        self._type_name.setReadOnly(True)

        self._x = QSpinBox()
        self._y = QSpinBox()
        self._w = QSpinBox()
        self._h = QSpinBox()

        for sb in (self._x, self._y):
            sb.setRange(-画布最大宽高, 画布最大宽高)
            sb.setKeyboardTracking(False)

        for sb in (self._w, self._h):
            sb.setRange(1, 画布最大宽高)
            sb.setKeyboardTracking(False)

        self._text = QLineEdit()
        self._plainText = QLineEdit()
        self._placeholder = QLineEdit()
        self._title = QLineEdit()
        self._label = QLineEdit()
        self._windowTitle = QLineEdit()

        self._layoutClass = QComboBox()
        self._layoutClass.addItems([无布局选项] + [x for x in 支持布局类 if x != 无布局选项])

        self._spacing = QSpinBox()
        self._spacing.setRange(-1, 200)
        self._spacing.setSpecialValueText("默认")

        self._marginLeft = QSpinBox()
        self._marginTop = QSpinBox()
        self._marginRight = QSpinBox()
        self._marginBottom = QSpinBox()
        for sb in (self._marginLeft, self._marginTop, self._marginRight, self._marginBottom):
            sb.setRange(0, 200)
            sb.setKeyboardTracking(False)

        for label, widget in [
            ("节点ID", self._node_id),
            ("kind", self._kind),
            ("类型", self._type_name),
            ("x", self._x),
            ("y", self._y),
            ("width", self._w),
            ("height", self._h),
            ("text", self._text),
            ("plainText", self._plainText),
            ("placeholderText", self._placeholder),
            ("title", self._title),
            ("label", self._label),
            ("windowTitle", self._windowTitle),
            ("layoutClass", self._layoutClass),
            ("spacing", self._spacing),
            ("marginLeft", self._marginLeft),
            ("marginTop", self._marginTop),
            ("marginRight", self._marginRight),
            ("marginBottom", self._marginBottom),
        ]:
            self._表单.addRow(label, widget)

        self._绑定提交信号()
        self.清空()

    def _绑定提交信号(self):
        for sb in (
            self._x,
            self._y,
            self._w,
            self._h,
            self._spacing,
            self._marginLeft,
            self._marginTop,
            self._marginRight,
            self._marginBottom,
        ):
            sb.valueChanged.connect(self._发射修改)

        for le in (
            self._text,
            self._plainText,
            self._placeholder,
            self._title,
            self._label,
            self._windowTitle,
        ):
            le.editingFinished.connect(self._发射修改)

        self._layoutClass.currentIndexChanged.connect(self._发射修改)

    def 清空(self):
        self._正在填充 = True
        self._文档模式 = False
        self._当前节点id = None
        self._当前类型 = None
        self._当前kind = None

        for le in (
            self._node_id,
            self._kind,
            self._type_name,
            self._text,
            self._plainText,
            self._placeholder,
            self._title,
            self._label,
            self._windowTitle,
        ):
            le.setText("")

        self._layoutClass.setCurrentIndex(0)
        self._x.setValue(0)
        self._y.setValue(0)
        self._w.setValue(1)
        self._h.setValue(1)
        self._spacing.setValue(-1)
        self._marginLeft.setValue(0)
        self._marginTop.setValue(0)
        self._marginRight.setValue(0)
        self._marginBottom.setValue(0)

        for w in self._可编辑控件列表():
            w.setEnabled(False)

        self._正在填充 = False

    def _可编辑控件列表(self):
        return (
            self._x,
            self._y,
            self._w,
            self._h,
            self._text,
            self._plainText,
            self._placeholder,
            self._title,
            self._label,
            self._windowTitle,
            self._layoutClass,
            self._spacing,
            self._marginLeft,
            self._marginTop,
            self._marginRight,
            self._marginBottom,
        )

    def 设置文档(self, doc: UiDocument):
        self._正在填充 = True
        self._文档模式 = True
        self._当前节点id = "document"
        self._当前kind = "document"
        self._当前类型 = "UiDocument"

        root = doc.get_root_node()
        g = root.props.get("geometry", {})

        self._node_id.setText("document")
        self._kind.setText("document")
        self._type_name.setText("UiDocument")

        self._x.setValue(0)
        self._y.setValue(0)
        self._w.setValue(_限制整数(g.get("width", 380), 画布最小宽高, 画布最大宽高, 380))
        self._h.setValue(_限制整数(g.get("height", 550), 画布最小宽高, 画布最大宽高, 550))

        self._text.setText("")
        self._plainText.setText("")
        self._placeholder.setText("")
        self._title.setText("")
        self._label.setText("")
        self._windowTitle.setText(root.props.get("windowTitle", "Form"))
        self._layoutClass.setCurrentIndex(0)
        self._spacing.setValue(-1)
        self._marginLeft.setValue(0)
        self._marginTop.setValue(0)
        self._marginRight.setValue(0)
        self._marginBottom.setValue(0)

        for w in self._可编辑控件列表():
            w.setEnabled(False)

        self._w.setEnabled(True)
        self._h.setEnabled(True)
        self._windowTitle.setEnabled(True)

        self._正在填充 = False

    def 设置节点(self, node: dict | None):
        if not node:
            self.清空()
            return

        self._正在填充 = True
        self._文档模式 = False
        self._当前节点id = node.get("id")
        self._当前kind = node.get("kind")
        self._当前类型 = node.get("widgetClass") or node.get("layoutClass") or node.get("kind", "")

        props = node.get("props", {})
        geo = _安全取几何(props)

        self._node_id.setText(node.get("id", ""))
        self._kind.setText(node.get("kind", ""))
        self._type_name.setText(self._当前类型)

        self._x.setValue(geo["x"])
        self._y.setValue(geo["y"])
        self._w.setValue(geo["width"])
        self._h.setValue(geo["height"])

        self._text.setText(props.get("text", ""))
        self._plainText.setText(props.get("plainText", ""))
        self._placeholder.setText(props.get("placeholderText", ""))
        self._title.setText(props.get("title", ""))
        self._label.setText(props.get("label", ""))
        self._windowTitle.setText(props.get("windowTitle", ""))

        layout_class = props.get("layoutClass") or node.get("layoutClass") or 无布局选项

        idx = self._layoutClass.findText(layout_class)
        self._layoutClass.setCurrentIndex(idx if idx >= 0 else self._layoutClass.findText(无布局选项))

        self._spacing.setValue(_限制整数(props.get("spacing", 6), -1, 200, 6))
        self._marginLeft.setValue(_限制整数(props.get("marginLeft", 9), 0, 200, 9))
        self._marginTop.setValue(_限制整数(props.get("marginTop", 9), 0, 200, 9))
        self._marginRight.setValue(_限制整数(props.get("marginRight", 9), 0, 200, 9))
        self._marginBottom.setValue(_限制整数(props.get("marginBottom", 9), 0, 200, 9))

        for w in self._可编辑控件列表():
            w.setEnabled(False)

        if node.get("kind") == "widget":
            self._x.setEnabled(True)
            self._y.setEnabled(True)
            self._w.setEnabled(True)
            self._h.setEnabled(True)

            widget_class = node.get("widgetClass")

            if widget_class in ("QPushButton", "QLabel", "QLineEdit"):
                self._text.setEnabled(True)
            if widget_class == "QTextEdit":
                self._plainText.setEnabled(True)
            if widget_class in ("QTextEdit", "QLineEdit"):
                self._placeholder.setEnabled(True)
            if widget_class == "QGroupBox":
                self._title.setEnabled(True)
            if widget_class == "__LayoutRegion__":
                self._layoutClass.setEnabled(True)
            if widget_class in ("QWidget", "QGroupBox", "QTabWidget", "QToolBox"):
                self._layoutClass.setEnabled(True)
            if node.get("role") == "page":
                self._layoutClass.setEnabled(True)
                if "title" in props:
                    self._title.setEnabled(True)
                if "label" in props:
                    self._label.setEnabled(True)

        elif node.get("kind") == "layout":
            self._layoutClass.setEnabled(True)
            self._spacing.setEnabled(True)
            self._marginLeft.setEnabled(True)
            self._marginTop.setEnabled(True)
            self._marginRight.setEnabled(True)
            self._marginBottom.setEnabled(True)

        self._正在填充 = False

    def 设置几何是否可编辑(self, enabled: bool):
        self._x.setEnabled(enabled)
        self._y.setEnabled(enabled)
        self._w.setEnabled(enabled)
        self._h.setEnabled(enabled)

    def _发射修改(self):
        if self._正在填充:
            return

        if self._文档模式:
            self.文档属性提交.emit(
                {
                    "width": _限制整数(self._w.value(), 画布最小宽高, 画布最大宽高, 800),
                    "height": _限制整数(self._h.value(), 画布最小宽高, 画布最大宽高, 600),
                    "windowTitle": self._windowTitle.text(),
                }
            )
            return

        if not self._当前节点id:
            return

        payload = {"id": self._当前节点id, "kind": self._当前kind, "props": {}}

        if self._当前kind == "widget":
            if self._x.isEnabled() and self._y.isEnabled() and self._w.isEnabled() and self._h.isEnabled():
                payload["props"]["geometry"] = {
                    "x": self._x.value(),
                    "y": self._y.value(),
                    "width": self._w.value(),
                    "height": self._h.value(),
                }

            if self._当前类型 in ("QPushButton", "QLabel", "QLineEdit"):
                payload["props"]["text"] = self._text.text()
            if self._当前类型 == "QTextEdit":
                payload["props"]["plainText"] = self._plainText.text()
            if self._当前类型 in ("QTextEdit", "QLineEdit"):
                payload["props"]["placeholderText"] = self._placeholder.text()
            if self._当前类型 == "QGroupBox":
                payload["props"]["title"] = self._title.text()

            if self._layoutClass.isEnabled():
                layout_text = self._layoutClass.currentText()
                payload["props"]["layoutClass"] = "" if layout_text == 无布局选项 else layout_text

            if self._title.isEnabled():
                payload["props"]["title"] = self._title.text()
            if self._label.isEnabled():
                payload["props"]["label"] = self._label.text()

        elif self._当前kind == "layout":
            layout_text = self._layoutClass.currentText()
            payload["layoutClass"] = "" if layout_text == 无布局选项 else layout_text
            payload["props"]["spacing"] = self._spacing.value()
            payload["props"]["marginLeft"] = self._marginLeft.value()
            payload["props"]["marginTop"] = self._marginTop.value()
            payload["props"]["marginRight"] = self._marginRight.value()
            payload["props"]["marginBottom"] = self._marginBottom.value()

        self.节点属性提交.emit(payload)
