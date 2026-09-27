from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import *

import ui_json_codec
from model import NodeModel, UiDocument
from canvas import 画布编辑器
from canvas_interaction import _限制整数, _安全取几何, _布局默认名, 画布最小宽高, 画布最大宽高, 支持布局类
from property_panel import 属性面板


DEMO名称 = "PyIDE Demo"

class 控件箱(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setDragEnabled(True)
        self.setIconSize(QSize(48, 48))
        self.setSpacing(6)
        self.setGridSize(QSize(84, 76))
        self.setViewMode(QListWidget.IconMode)

        self._拖拽起始点 = QPoint()

        for 名称, 类型, 图标颜色, 图标类型 in [
            ("按钮", "widget:QPushButton", "#4A90D9", "button"),
            ("标签", "widget:QLabel", "#F5A623", "label"),
            ("文本框", "widget:QTextEdit", "#50C878", "text"),
            ("单行框", "widget:QLineEdit", "#26A69A", "line"),
            ("分组框", "widget:QGroupBox", "#8E8E93", "group"),
            ("选项卡", "widget:QTabWidget", "#9013FE", "tabs"),
            ("垂直布局区域", "layout:QVBoxLayout", "#607D8B", "vbox"),
            ("水平布局区域", "layout:QHBoxLayout", "#3F51B5", "hbox"),
            ("网格布局区域", "layout:QGridLayout", "#795548", "grid"),
            ("表单布局区域", "layout:QFormLayout", "#009688", "form"),
        ]:
            pixmap = self._创建控件箱图标(图标类型, 图标颜色)

            item = QListWidgetItem(QIcon(pixmap), 名称)
            item.setData(Qt.UserRole, 类型)
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.SizeHintRole, QSize(100, 72))
            self.addItem(item)

    @staticmethod
    def _创建控件箱图标(图标类型: str, 颜色: str) -> QPixmap:
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        outline = QColor("#64748B")
        accent = QColor(颜色)
        painter.setPen(QPen(outline, 1.5))
        painter.setBrush(QColor("#F8FAFC"))
        painter.drawRoundedRect(3, 3, 42, 42, 6, 6)
        painter.setPen(QPen(accent, 2))
        painter.setBrush(Qt.NoBrush)

        if 图标类型 == "button":
            painter.drawRoundedRect(10, 16, 28, 16, 3, 3)
            painter.drawLine(17, 24, 31, 24)
        elif 图标类型 == "label":
            painter.setFont(QFont("Arial", 20, QFont.Bold))
            painter.drawText(QRect(8, 8, 32, 31), Qt.AlignCenter, "A")
        elif 图标类型 == "text":
            painter.drawRoundedRect(9, 10, 30, 28, 3, 3)
            for y in (17, 23, 29):
                painter.drawLine(14, y, 34, y)
        elif 图标类型 == "line":
            painter.drawRoundedRect(8, 16, 32, 16, 3, 3)
            painter.drawLine(13, 24, 35, 24)
        elif 图标类型 == "group":
            painter.drawRect(9, 12, 30, 25)
            painter.drawLine(13, 12, 27, 12)
        elif 图标类型 in ("tabs", "toolbox"):
            painter.drawRect(9, 13, 30, 24)
            painter.drawLine(9, 20, 39, 20)
            painter.drawLine(16, 13, 16, 20)
        elif 图标类型 == "vbox":
            for y in (12, 20, 28):
                painter.drawRoundedRect(13, y, 22, 5, 1, 1)
        elif 图标类型 == "hbox":
            for x in (10, 19, 28):
                painter.drawRoundedRect(x, 16, 7, 16, 1, 1)
        elif 图标类型 == "grid":
            painter.drawRect(10, 11, 28, 26)
            painter.drawLine(19, 11, 19, 37)
            painter.drawLine(29, 11, 29, 37)
            painter.drawLine(10, 20, 38, 20)
            painter.drawLine(10, 29, 38, 29)
        else:
            painter.drawRect(10, 12, 28, 24)
            painter.drawLine(10, 22, 38, 22)
        painter.end()
        return pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._拖拽起始点 = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and (
            event.position().toPoint() - self._拖拽起始点
        ).manhattanLength() > QApplication.startDragDistance():
            self.开始拖拽()
        super().mouseMoveEvent(event)

    def 开始拖拽(self):
        item = self.currentItem()
        if not item:
            return

        mime_data = QMimeData()
        mime_data.setText(item.data(Qt.UserRole))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setPixmap(item.icon().pixmap(48, 48))
        drag.setHotSpot(QPoint(24, 24))
        drag.exec(Qt.CopyAction)


# =========================================================
# 主窗口
# =========================================================

class 主窗口(QMainWindow):
    def __init__(self):
        super().__init__()
        self._当前文件路径 = None

        self.画布 = 画布编辑器()
        self.setCentralWidget(self.画布)

        self.属性区 = 属性面板()
        self.属性区.节点属性提交.connect(self._应用节点属性)
        self.属性区.文档属性提交.connect(self._应用文档属性)

        self.画布.选中节点变化.connect(self._同步属性区)
        self.画布.文档变化.connect(self._文档变化后刷新标题)

        self._创建停靠区()
        self._创建菜单()
        self._创建工具栏()

        self.画布.设置文档(ui_json_codec.新建空白文档(), 记录快照=False)
        self.resize(1460, 860)
        self._设置控制台默认高度()

    def _创建停靠区(self):


        控件箱dock = QDockWidget("控件箱", self)
        控件箱dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        控件箱dock.setWidget(控件箱())
        self.addDockWidget(Qt.LeftDockWidgetArea, 控件箱dock)

        属性dock = QDockWidget("属性", self)
        属性dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        属性dock.setWidget(self.属性区)
        self.addDockWidget(Qt.RightDockWidgetArea, 属性dock)

        self._控制台 = QPlainTextEdit(self)
        self._控制台.setObjectName("debug_console")
        self._控制台.setReadOnly(True)
        self._控制台.setMaximumBlockCount(2000)
        self._控制台.setFont(QFont("Consolas", 9))
        self._控制台.setPlaceholderText("调试输出会显示在这里")
        self._控制台dock = QDockWidget("控制台", self)
        self._控制台dock.setObjectName("console_dock")
        self._控制台dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self._控制台dock.setWidget(self._控制台)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._控制台dock)
        self._输出控制台("控制台已就绪")
        self._控制台.appendPlainText("")
        self._控制台.appendPlainText("这是简易文件,完整IDE,请访问官网pyide.net")

    def _创建菜单(self):
        菜单栏 = self.menuBar()

        文件菜单 = 菜单栏.addMenu("文件")
        新建动作 = QAction("新建", self)
        新建动作.setShortcut(QKeySequence.New)
        新建动作.triggered.connect(self._新建文件)
        文件菜单.addAction(新建动作)

        打开动作 = QAction("打开 .ui", self)
        打开动作.setShortcut(QKeySequence.Open)
        打开动作.triggered.connect(self._打开文件)
        文件菜单.addAction(打开动作)

        保存动作 = QAction("保存", self)
        保存动作.setShortcut(QKeySequence.Save)
        保存动作.triggered.connect(self._保存文件)
        文件菜单.addAction(保存动作)

        另存为动作 = QAction("另存为 .ui", self)
        另存为动作.setShortcut(QKeySequence.SaveAs)
        另存为动作.triggered.connect(self._另存为文件)
        文件菜单.addAction(另存为动作)

        导出Python动作 = QAction("导出 Python", self)
        导出Python动作.setShortcut("Ctrl+Shift+E")
        导出Python动作.triggered.connect(self._导出Python)
        文件菜单.addAction(导出Python动作)

        查看Python动作 = QAction("查看 Python", self)
        查看Python动作.triggered.connect(self._查看Python)
        文件菜单.addAction(查看Python动作)

        调试菜单 = 菜单栏.addMenu("调试")
        清空控制台动作 = QAction("清空控制台", self)
        清空控制台动作.triggered.connect(lambda: self._控制台.clear())
        调试菜单.addAction(清空控制台动作)

        编辑菜单 = 菜单栏.addMenu("编辑")

        撤销动作 = QAction("撤销", self)
        撤销动作.setShortcut(QKeySequence.Undo)
        撤销动作.triggered.connect(self.画布.undo)
        编辑菜单.addAction(撤销动作)

        重做动作 = QAction("重做", self)
        重做动作.setShortcut(QKeySequence.Redo)
        重做动作.triggered.connect(self.画布.redo)
        编辑菜单.addAction(重做动作)

        编辑菜单.addSeparator()

        删除动作 = QAction("删除", self)
        删除动作.setShortcut(QKeySequence.Delete)
        删除动作.triggered.connect(self.画布.删除当前选中)
        编辑菜单.addAction(删除动作)

        布局菜单 = 菜单栏.addMenu("布局")

        for 文本, layout_class in [
            ("给选中容器设置垂直布局", "QVBoxLayout"),
            ("给选中容器设置水平布局", "QHBoxLayout"),
            ("给选中容器设置网格布局", "QGridLayout"),
            ("给选中容器设置表单布局", "QFormLayout"),
        ]:
            action = QAction(文本, self)
            action.triggered.connect(lambda checked=False, cls=layout_class: self._工具栏设置布局(cls))
            布局菜单.addAction(action)

    def _创建工具栏(self):
        toolbar = QToolBar("主工具栏", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(True)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        文件动作 = [
            ("新建", QStyle.SP_FileIcon, QKeySequence.New, self._新建文件),
            ("打开 .ui", QStyle.SP_DialogOpenButton, QKeySequence.Open, self._打开文件),
            ("保存", QStyle.SP_DialogSaveButton, QKeySequence.Save, self._保存文件),
            ("另存为 .ui", QStyle.SP_DriveHDIcon, QKeySequence.SaveAs, self._另存为文件),
            ("导出 Python", QStyle.SP_FileDialogDetailedView, "Ctrl+Shift+E", self._导出Python),
            ("查看 Python", QStyle.SP_FileDialogContentsView, None, self._查看Python),
        ]
        for 文本, 图标, 快捷键, 回调 in 文件动作:
            action = QAction(self.style().standardIcon(图标), 文本, self)
            if 快捷键:
                action.setShortcut(快捷键)
            action.triggered.connect(回调)
            toolbar.addAction(action)

        toolbar.addSeparator()
        for 文本, layout_class in [
            ("垂直布局", "QVBoxLayout"),
            ("水平布局", "QHBoxLayout"),
            ("网格布局", "QGridLayout"),
            ("表单布局", "QFormLayout"),
        ]:
            action = QAction(文本, self)
            action.setToolTip(f"给当前选中的容器设置整体布局：{layout_class}")
            action.triggered.connect(lambda checked=False, cls=layout_class: self._工具栏设置布局(cls))
            toolbar.addAction(action)

    def _工具栏设置布局(self, layout_class: str):
        ok, message = self.画布.设置当前容器布局(layout_class)
        if ok:
            self.statusBar().showMessage(message, 3000)
            self._输出控制台(message)
        else:
            QMessageBox.information(self, "布局工具", message)
            self._输出控制台(message, "WARN")

    def _输出控制台(self, message: str, level: str = "INFO"):
        if not hasattr(self, "_控制台"):
            return
        self._控制台.appendPlainText(f"[{level}] {message}")

    def _设置控制台默认高度(self):
        if hasattr(self, "_控制台dock"):
            self.resizeDocks(
                [self._控制台dock],
                [max(160, int(self.height() * 0.25))],
                Qt.Vertical,
            )

    def _同步属性区(self, node_dict):
        if node_dict:
            self.属性区.设置节点(node_dict)

            node_id = node_dict["id"]
            geometry_editable = False

            if node_dict.get("kind") == "widget":
                geometry_editable = not self.画布.导出文档().is_layout_managed_widget(node_id)
                if node_dict.get("role") == "page":
                    geometry_editable = False

            if node_dict.get("kind") in ("layout", "layoutItem", "spacer"):
                geometry_editable = False

            self.属性区.设置几何是否可编辑(geometry_editable)
        else:
            self.属性区.设置文档(self.画布.导出文档())

    def _文档变化后刷新标题(self, doc: UiDocument):
        title = doc.get_root_node().props.get("windowTitle", "Form")
        file_name = os.path.basename(self._当前文件路径) if self._当前文件路径 else "未命名"
        self.setWindowTitle(f"{DEMO名称} - {file_name} - {title}")

    def _应用节点属性(self, payload: dict):
        node_id = payload.get("id")
        if node_id:
            self.画布.更新节点属性(node_id, payload)

    def _应用文档属性(self, payload: dict):
        self.画布.更新文档属性(
            width=payload.get("width"),
            height=payload.get("height"),
            windowTitle=payload.get("windowTitle"),
        )

    def _新建文件(self):
        self._当前文件路径 = None
        self.画布.设置文档(ui_json_codec.新建空白文档(), 记录快照=True)

    def _打开文件(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 UI 文件", "", "Qt UI Files (*.ui)")
        if not path:
            return

        try:
            doc = ui_json_codec.从ui文件读取(path)
            self._当前文件路径 = path
            self.画布.设置文档(doc)
            self.statusBar().showMessage(f"已打开：{path}", 3000)
            self._输出控制台(f"已打开：{path}")
        except Exception as e:
            self._输出控制台(f"打开失败：{e}", "ERROR")
            QMessageBox.critical(self, "打开失败", str(e))

    def _保存文件(self):
        if not self._当前文件路径:
            self._另存为文件()
            return

        try:
            ui_json_codec.保存为ui文件(self._当前文件路径, self.画布.导出文档())
            self.statusBar().showMessage(f"已保存：{self._当前文件路径}", 3000)
            self._输出控制台(f"已保存：{self._当前文件路径}")
        except Exception as e:
            self._输出控制台(f"保存失败：{e}", "ERROR")
            QMessageBox.critical(self, "保存失败", str(e))

    def _另存为文件(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 UI 文件",
            self._当前文件路径 or "",
            "Qt UI Files (*.ui)",
        )
        if not path:
            return

        if not path.lower().endswith(".ui"):
            path += ".ui"

        try:
            ui_json_codec.保存为ui文件(path, self.画布.导出文档())
            self._当前文件路径 = path
            self._文档变化后刷新标题(self.画布.导出文档())
            self.statusBar().showMessage(f"已保存：{path}", 3000)
            self._输出控制台(f"已保存：{path}")
        except Exception as e:
            self._输出控制台(f"保存失败：{e}", "ERROR")
            QMessageBox.critical(self, "保存失败", str(e))

    def _导出Python(self):
        默认路径 = (
            os.path.splitext(self._当前文件路径)[0] + ".py"
            if self._当前文件路径
            else "Form.py"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 Python 文件",
            默认路径,
            "Python Files (*.py)",
        )
        if not path:
            return
        if not path.lower().endswith(".py"):
            path += ".py"

        try:
            ui_json_codec.保存为python文件(path, self.画布.导出文档())
            self.statusBar().showMessage(f"Python 已导出：{path}", 4000)
            self._输出控制台(f"Python 已导出：{path}")
        except Exception as e:
            self._输出控制台(f"Python 导出失败：{e}", "ERROR")
            QMessageBox.critical(self, "导出失败", str(e))

    def _查看Python(self):
        code = ui_json_codec.生成Python代码(self.画布.导出文档())
        dialog = QDialog(self)
        dialog.setWindowTitle("Python 代码预览")
        dialog.resize(900, 650)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(dialog)
        editor.setReadOnly(True)
        editor.setPlainText(code)
        editor.setFont(QFont("Consolas", 10))
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = 主窗口()
    win.show()
    app.exec()
