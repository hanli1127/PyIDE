# canvas.py

import json
import traceback
import copy
from PySide6.QtCore import Qt, QPoint, QRect, QEvent, QSize, QMimeData, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import *

try:
    from shiboken6 import delete as _qt_delete
except Exception:
    _qt_delete = None


import ui_json_codec

from model import NodeModel, UiDocument
from canvas_interaction import 设计期布局区域控件, 根表层, _控件构造器, _布局构造器, _限制整数, _安全取几何, _布局默认名, 画布最小宽高, 画布最大宽高


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
# 画布编辑器
# =========================================================

class 画布编辑器(QWidget):
    选中节点变化 = Signal(object)
    文档变化 = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), Qt.white)
        self.setPalette(pal)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._文档: UiDocument = ui_json_codec.新建空白文档()

        self._当前选中节点id: str | None = None
        self._多选节点id集合: set[str] = set()
        self._多选节点id列表: list[str] = []

        self._根表面 = 根表层(self, self)
        self._根表面.setMouseTracking(True)
        self._根表面.installEventFilter(self)

        self._根布局宿主: QWidget | None = None

        self._节点到控件: dict[str, QWidget] = {}
        self._控件到节点: dict[QWidget, str] = {}
        self._页面节点到控件: dict[str, QWidget] = {}
        self._页面控件到节点: dict[QWidget, str] = {}
        self._管理器控件集合: set[QWidget] = set()

        self._操作模式: str | None = None
        self._拖拽节点id: str | None = None
        self._拖拽节点id列表: list[str] = []
        self._拖拽起始点 = QPoint()
        self._拖拽节点起始矩形映射: dict[str, QRect] = {}
        self._拖拽节点原父控件映射: dict[str, QWidget | None] = {}
        self._拖拽节点起始是否布局管理: dict[str, bool] = {}
        self._拖拽节点起始ownerid映射: dict[str, str | None] = {}

        self._缩放方向 = (0, 0)
        self._拖拽节点起始画布矩形 = QRect()

        # 画布自身的隐形边缘缩放，方案 B：由画布编辑器外层处理
        self._画布位置 = QPoint(10, 10)
        self._画布边缘热区 = 8
        self._画布缩放方向 = (0, 0)
        self._画布缩放起点 = QPoint()
        self._画布缩放起始矩形 = QRect()
        self._画布缩放起始文档快照: dict | None = None

        self._候选拖拽节点id: str | None = None
        self._候选拖拽节点id列表: list[str] = []
        self._候选拖拽起点 = QPoint()
        self._候选点击节点id: str | None = None

        self._框选中 = False
        self._框选起点 = QPoint()
        self._框选终点 = QPoint()

        self._网格间距 = 10
        self._网格颜色 = QColor(140, 140, 160)
        self._正在重建画布 = False

        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._快照中 = False

        self._重建画布()

    # -----------------------------------------------------
    # 文档 / 快照
    # -----------------------------------------------------
    def 设置文档(self, doc: UiDocument, 记录快照: bool = True):
        if 记录快照 and not self._快照中:
            self._提交快照(self._快照())
        self._文档 = doc
        self._当前选中节点id = None
        self._多选节点id集合.clear()
        self._多选节点id列表.clear()
        self._结束当前操作()
        self._重建画布()
        self.文档变化.emit(self._文档)
        self.选中节点变化.emit(None)

    def 导出文档(self) -> UiDocument:
        return self._文档

    def _快照(self) -> dict:
        return self._文档.to_dict()

    def _恢复快照(self, snapshot: dict):
        self._文档 = UiDocument.from_dict(copy.deepcopy(snapshot))
        self._当前选中节点id = None
        self._多选节点id集合.clear()
        self._多选节点id列表.clear()
        self._结束当前操作()
        self._重建画布()
        self.文档变化.emit(self._文档)
        self.选中节点变化.emit(None)

    def _提交快照(self, snapshot: dict | None = None):
        if self._快照中:
            return

        snapshot = copy.deepcopy(snapshot if snapshot is not None else self._快照())
        if self._undo_stack and self._undo_stack[-1] == snapshot:
            return

        self._快照中 = True
        try:
            self._undo_stack.append(snapshot)
            self._redo_stack.clear()
            if len(self._undo_stack) > 100:
                self._undo_stack = self._undo_stack[-100:]
        finally:
            self._快照中 = False

    def undo(self):
        if not self._undo_stack:
            return

        current = self._快照()
        snapshot = self._undo_stack.pop()

        self._快照中 = True
        try:
            self._redo_stack.append(copy.deepcopy(current))
            self._恢复快照(snapshot)
        finally:
            self._快照中 = False

    def redo(self):
        if not self._redo_stack:
            return

        current = self._快照()
        snapshot = self._redo_stack.pop()

        self._快照中 = True
        try:
            self._undo_stack.append(copy.deepcopy(current))
            self._恢复快照(snapshot)
        finally:
            self._快照中 = False

    @property
    def 可撤销(self) -> bool:
        return bool(self._undo_stack)

    @property
    def 可重做(self) -> bool:
        return bool(self._redo_stack)

    def 更新文档属性(self, width: int | None = None, height: int | None = None, windowTitle: str | None = None):
        self._提交快照(self._快照())
        width = _限制整数(width, 画布最小宽高, 画布最大宽高, 380) if width is not None else None
        height = _限制整数(height, 画布最小宽高, 画布最大宽高, 550) if height is not None else None

        self._文档.update_document_props(width=width, height=height, window_title=windowTitle)
        self._重建画布()
        self.文档变化.emit(self._文档)

    def 选中节点(self, node_id: str | None):
        self._设置当前选中节点(node_id)

    def 更新节点属性(self, node_id: str, payload: dict):
        self._提交快照(self._快照())
        if not self._文档.has_node(node_id):
            return

        node = self._文档.get_node(node_id)
        props = payload.get("props", {})

        if props:
            if "geometry" in props:
                g = props["geometry"]
                props["geometry"] = {
                    "x": _限制整数(g.get("x", 0), -画布最大宽高, 画布最大宽高, 0),
                    "y": _限制整数(g.get("y", 0), -画布最大宽高, 画布最大宽高, 0),
                    "width": _限制整数(g.get("width", 100), 1, 画布最大宽高, 100),
                    "height": _限制整数(g.get("height", 30), 1, 画布最大宽高, 30),
                }
            self._文档.update_node_props(node_id, props)

        需要重建 = False

        if node.kind == "widget" and "layoutClass" in props:
            layout_class = props.get("layoutClass")

            target_node = node

            # QTabWidget / QToolBox 本身不直接设置 layout，
            # 要把布局设置到当前页面上。
            if getattr(node, "widgetClass", None) in ("QTabWidget", "QToolBox"):
                page_id = self._获取当前页面节点(node.id)
                if page_id and self._文档.has_node(page_id):
                    target_node = self._文档.get_node(page_id)

            if self._节点可设置整体布局(target_node):
                if self._是否无布局类(layout_class):
                    self._移除容器整体布局(target_node.id)
                    target_node.props.pop("layoutClass", None)

                    if target_node.id != node.id:
                        node.props.pop("layoutClass", None)

                    需要重建 = True

                elif layout_class in _布局构造器:
                    if getattr(target_node, "layout", None) and self._文档.has_node(target_node.layout):
                        self._设置布局节点类型(target_node.layout, layout_class)
                    else:
                        self._给容器创建整体布局(target_node.id, layout_class)

                    target_node.props["layoutClass"] = layout_class

                    if target_node.id != node.id:
                        node.props.pop("layoutClass", None)

                    需要重建 = True
                    
        if payload.get("kind") == "layout":
            if "layoutClass" in payload:
                new_layout_class = payload["layoutClass"]

                if self._是否无布局类(new_layout_class):
                    owner_id = self._获取布局所属容器id(node_id)
                    if owner_id:
                        self._移除容器整体布局(owner_id)
                elif new_layout_class in _布局构造器:
                    self._设置布局节点类型(node_id, new_layout_class)

            需要重建 = True

        try:
            node = self._文档.get_node(node_id)
            if getattr(node, "role", None) == "page" and ("title" in props or "label" in props):
                需要重建 = True
        except Exception:
            pass

        if 需要重建:
            self._重建画布()
            if self._文档.has_node(node_id):
                self.选中节点变化.emit(self._节点属性面板字典(node_id))
            else:
                self.选中节点变化.emit(None)
            self._根表面.update()
        else:
            self._应用运行时节点更新(node_id, props)
            self._设置当前选中节点(node_id)

        self.文档变化.emit(self._文档)


    # -----------------------------------------------------
    # 布局工具
    # -----------------------------------------------------

    def _是否无布局类(self, layout_class) -> bool:
        if layout_class is None:
            return True
        return str(layout_class).strip() in ("", "无布局", "__none__", "None")
    
    def 设置当前容器布局(self, layout_class: str) -> tuple[bool, str]:
        self._提交快照(self._快照())

        是无布局 = self._是否无布局类(layout_class)

        if not 是无布局 and layout_class not in _布局构造器:
            return False, "不支持的布局类型。"

        target_id = self._获取布局工具目标容器()
        if not target_id or not self._文档.has_node(target_id):
            return False, "请先选中一个可以设置布局的容器。"

        target_node = self._文档.get_node(target_id)
        if target_node.kind != "widget":
            return False, "当前选中的不是容器。"

        if not self._节点可设置整体布局(target_node):
            return False, "普通控件不能设置整体布局，请选中 Form、QWidget、QGroupBox、Tab 页面或布局区域。"

        if 是无布局:
            self._移除容器整体布局(target_node.id)

            self._重建画布()
            self._设置当前选中节点(target_id if self._文档.has_node(target_id) else None)
            self.文档变化.emit(self._文档)

            return True, "已删除当前容器布局。"

        if getattr(target_node, "layout", None) and self._文档.has_node(target_node.layout):
            self._设置布局节点类型(target_node.layout, layout_class)
        else:
            self._给容器创建整体布局(target_node.id, layout_class)

        target_node.props["layoutClass"] = layout_class

        self._重建画布()
        self._设置当前选中节点(target_id if self._文档.has_node(target_id) else None)
        self.文档变化.emit(self._文档)

        if self._是否布局区域节点(target_node):
            return True, f"已把布局区域改为：{layout_class}"

        return True, f"已给容器设置整体布局：{layout_class}"


    def _获取布局工具目标容器(self) -> str | None:
        node_id = self._当前选中节点id

        if not node_id or not self._文档.has_node(node_id):
            return self._文档.root

        node = self._文档.get_node(node_id)

        if node.kind == "layout":
            owner = self._获取布局所属容器id(node_id)
            return owner or self._文档.root

        if node.kind != "widget":
            parent_id = self._获取父节点id(node_id)
            return parent_id or self._文档.root

        if node.widgetClass in ("QTabWidget", "QToolBox"):
            page_id = self._获取当前页面节点(node_id)
            return page_id or node_id

        return node_id

    def _给容器创建整体布局(self, owner_id: str, layout_class: str) -> str | None:
        if not self._文档.has_node(owner_id):
            return None

        owner_node = self._文档.get_node(owner_id)
        layout_node = self._创建文档布局节点(layout_class, owner_id)
        owner_node.layout = layout_node.id

        old_children = list(getattr(owner_node, "children", []))
        owner_node.children.clear()

        for child_id in old_children:
            if not self._文档.has_node(child_id):
                continue

            child_node = self._文档.get_node(child_id)
            if getattr(child_node, "role", None) == "page":
                owner_node.children.append(child_id)
                continue

            item_props = self._默认布局项属性(layout_node.id)
            item = self._文档.create_layout_item_node("widget", child_id, parent=layout_node.id, props=item_props)
            child_node.parent = item.id
            layout_node.items.append(item.id)

        return layout_node.id
            
    def _节点可设置整体布局(self, node) -> bool:
        if getattr(node, "kind", None) != "widget":
            return False

        if self._是否布局区域节点(node):
            return True

        if getattr(node, "role", None) == "page":
            return True

        return getattr(node, "widgetClass", None) in (
            "QWidget",
            "QGroupBox",
        )


    def _收集布局内控件和待删除节点(self, layout_id: str) -> tuple[list[str], set[str]]:
        widget_ids: list[str] = []
        remove_ids: set[str] = set()

        def walk(lid: str):
            if not lid or not self._文档.has_node(lid):
                return

            layout_node = self._文档.get_node(lid)
            if getattr(layout_node, "kind", None) != "layout":
                return

            remove_ids.add(lid)

            for item_id in list(getattr(layout_node, "items", [])):
                if not self._文档.has_node(item_id):
                    continue

                item_node = self._文档.get_node(item_id)
                remove_ids.add(item_id)

                target_id = getattr(item_node, "target", None)
                if not target_id or not self._文档.has_node(target_id):
                    continue

                target_node = self._文档.get_node(target_id)

                if getattr(target_node, "kind", None) == "widget":
                    widget_ids.append(target_id)
                elif getattr(target_node, "kind", None) == "layout":
                    walk(target_id)
                else:
                    # spacer 等布局专属节点，删除即可
                    remove_ids.add(target_id)

        walk(layout_id)
        return widget_ids, remove_ids


    def _移除容器整体布局(self, owner_id: str) -> bool:
        if not owner_id or not self._文档.has_node(owner_id):
            return False

        owner_node = self._文档.get_node(owner_id)
        layout_id = getattr(owner_node, "layout", None)

        if not layout_id or not self._文档.has_node(layout_id):
            owner_node.props.pop("layoutClass", None)
            return False

        widget_ids, remove_ids = self._收集布局内控件和待删除节点(layout_id)

        for child_id in widget_ids:
            if not self._文档.has_node(child_id):
                continue

            child_node = self._文档.get_node(child_id)

            widget = self._节点到控件.get(child_id)
            if widget is not None:
                try:
                    final_top_left = self._控件根表面矩形(widget).topLeft()
                    geometry = self._计算已有控件放置几何(owner_id, child_id, final_top_left)
                    child_node.props["geometry"] = {
                        "x": _限制整数(geometry.get("x", 0), -画布最大宽高, 画布最大宽高, 0),
                        "y": _限制整数(geometry.get("y", 0), -画布最大宽高, 画布最大宽高, 0),
                        "width": _限制整数(geometry.get("width", 100), 1, 画布最大宽高, 100),
                        "height": _限制整数(geometry.get("height", 30), 1, 画布最大宽高, 30),
                    }
                except Exception:
                    traceback.print_exc()

            child_node.parent = owner_id

            if child_id not in getattr(owner_node, "children", []):
                owner_node.children.append(child_id)

        owner_node.layout = None
        owner_node.props.pop("layoutClass", None)

        for remove_id in remove_ids:
            self._文档.nodes.pop(remove_id, None)

        return True

    def _创建文档布局节点(self, layout_class: str, parent_id: str):
        props = self._文档默认布局属性(layout_class)
        return self._文档.create_layout_node(
            layout_class=layout_class,
            name=self._生成唯一节点名(_布局默认名(layout_class)),
            props=props,
            parent=parent_id,
        )

    def _文档默认布局属性(self, layout_class: str) -> dict:
        if hasattr(self._文档, "default_layout_props"):
            try:
                return dict(self._文档.default_layout_props(layout_class))
            except Exception:
                pass

        return {"spacing": 6, "marginLeft": 9, "marginTop": 9, "marginRight": 9, "marginBottom": 9}

    def _设置布局节点类型(self, layout_id: str, layout_class: str):
        if not layout_id or not self._文档.has_node(layout_id):
            return

        if hasattr(self._文档, "update_layout_class"):
            try:
                self._文档.update_layout_class(layout_id, layout_class)
                return
            except Exception:
                pass

        layout_node = self._文档.get_node(layout_id)
        layout_node.layoutClass = layout_class
        if not getattr(layout_node, "name", ""):
            layout_node.name = self._生成唯一节点名(_布局默认名(layout_class))

    def _生成唯一节点名(self, base: str) -> str:
        existing = {getattr(node, "name", "") for node in self._文档.nodes.values() if getattr(node, "name", "")}
        if base not in existing:
            return base

        i = 1
        while True:
            candidate = f"{base}_{i}"
            if candidate not in existing:
                return candidate
            i += 1

    def _默认布局项属性(self, layout_id: str) -> dict:
        if not layout_id or not self._文档.has_node(layout_id):
            return {}

        layout_node = self._文档.get_node(layout_id)
        if getattr(layout_node, "layoutClass", "") == "QGridLayout":
            return {
                "row": len(getattr(layout_node, "items", [])),
                "column": 0,
                "rowSpan": 1,
                "columnSpan": 1,
            }

        return {}

    # -----------------------------------------------------
    # 画布重建 / 控件创建
    # -----------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._布局根表面()

    def mousePressEvent(self, event):
        if self._处理画布边缘缩放事件(self, event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._处理画布边缘缩放事件(self, event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._处理画布边缘缩放事件(self, event):
            return
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self._结束当前操作()
        super().closeEvent(event)

    def _布局根表面(self):
        root = self._文档.get_root_node()
        geo = root.props.get("geometry", {})

        w = _限制整数(geo.get("width", 380), 200, 画布最大宽高, 380)
        h = _限制整数(geo.get("height", 550), 200, 画布最大宽高, 550)

        pos = getattr(self, "_画布位置", QPoint(10, 10))

        self._根表面.setGeometry(pos.x(), pos.y(), w, h)
        self.setMinimumSize(pos.x() + w + 10, pos.y() + h + 10)

        if getattr(self, "_根布局宿主", None) is not None:
            try:
                self._根布局宿主.setGeometry(self._根表面.rect())
            except RuntimeError:
                self._根布局宿主 = None
            except Exception:
                traceback.print_exc()

        self._根表面.update()
        self.update()

    def _安全安装过滤器(self, widget: QWidget):
        if widget is None:
            return
        try:
            if getattr(widget, "_pyide_event_filter_installed", False):
                return
            widget.installEventFilter(self)
            widget._pyide_event_filter_installed = True
        except Exception:
            pass

    def _安全移除过滤器(self, widget: QWidget):
        if widget is None:
            return
        try:
            if getattr(widget, "_pyide_event_filter_installed", False):
                widget.removeEventFilter(self)
                widget._pyide_event_filter_installed = False
        except Exception:
            pass

    def _安全销毁控件(self, widget: QWidget):
        if widget is None:
            return

        try:
            self._安全移除过滤器(widget)
            for child in widget.findChildren(QWidget):
                self._安全移除过滤器(child)

            try:
                widget.hide()
            except Exception:
                pass
            try:
                widget.setParent(None)
            except Exception:
                pass
            try:
                widget.deleteLater()
            except Exception:
                pass
        except RuntimeError:
            pass
        except Exception:
            traceback.print_exc()

    def _清空根表面(self):
        # 当前架构：根表层不直接持有 layout，根布局放在 _根布局宿主 里。
        # 销毁根表层子 QWidget 时，宿主和其 layout 会一起释放。
        for child in list(self._根表面.children()):
            try:
                if isinstance(child, QWidget):
                    self._安全销毁控件(child)
            except RuntimeError:
                pass
            except Exception:
                traceback.print_exc()

        self._根布局宿主 = None
        self._节点到控件.clear()
        self._控件到节点.clear()
        self._页面节点到控件.clear()
        self._页面控件到节点.clear()
        self._管理器控件集合.clear()

    def _布局管理目标集合(self, layout_id: str) -> set[str]:
        targets = set()
        if not layout_id or not self._文档.has_node(layout_id):
            return targets

        layout_node = self._文档.get_node(layout_id)
        for item_id in getattr(layout_node, "items", []):
            if not self._文档.has_node(item_id):
                continue
            item_node = self._文档.get_node(item_id)
            target = getattr(item_node, "target", None)
            if target:
                targets.add(target)

        return targets

    def _重建画布(self):
        if self._正在重建画布:
            return

        self._正在重建画布 = True
        当前单选 = self._当前选中节点id
        当前多选列表 = list(self._多选节点id列表)
        当前多选集合 = set(self._多选节点id集合)

        try:
            self._布局根表面()
            self._清空根表面()

            root_node = self._文档.get_root_node()
            root_layout_targets = set()

            if getattr(root_node, "layout", None):
                root_layout_targets = self._布局管理目标集合(root_node.layout)

                if root_layout_targets:
                    self._根布局宿主 = QWidget(self._根表面)
                    self._根布局宿主.setObjectName("__root_layout_host__")
                    self._根布局宿主.setMouseTracking(True)
                    self._根布局宿主.setAcceptDrops(True)
                    self._根布局宿主.setGeometry(self._根表面.rect())
                    self._根布局宿主.show()
                    self._安全安装过滤器(self._根布局宿主)

                    root_layout = self._创建布局对象(root_node.layout, self._根布局宿主, set(), set())
                    try:
                        self._根布局宿主.setLayout(root_layout)
                    except RuntimeError:
                        traceback.print_exc()
                    except Exception:
                        traceback.print_exc()

            for child_id in getattr(root_node, "children", []):
                if child_id in root_layout_targets or not self._文档.has_node(child_id):
                    continue

                child_node = self._文档.get_node(child_id)
                widget = self._创建控件树(child_node.id, self._根表面, set(), set())

                if child_node.role != "page" and widget is not None:
                    self._应用绝对几何(child_node.id, widget)

            self._当前选中节点id = 当前单选 if 当前单选 and self._文档.has_node(当前单选) else None
            restored = [nid for nid in 当前多选列表 if nid in 当前多选集合 and self._文档.has_node(nid)]
            self._多选节点id列表 = restored
            self._多选节点id集合 = set(restored)

        except Exception:
            traceback.print_exc()
            self._当前选中节点id = None
            self._多选节点id集合.clear()
            self._多选节点id列表.clear()
            try:
                self._清空根表面()
            except Exception:
                traceback.print_exc()

        finally:
            self._正在重建画布 = False
            self._根表面.update()
            self.update()

    def _创建控件树(
        self,
        node_id: str,
        parent_widget: QWidget,
        visiting_widgets: set[str] | None = None,
        visiting_layouts: set[str] | None = None,
    ):
        if visiting_widgets is None:
            visiting_widgets = set()
        if visiting_layouts is None:
            visiting_layouts = set()

        if not self._文档.has_node(node_id) or node_id in visiting_widgets:
            return None

        visiting_widgets.add(node_id)

        try:
            node = self._文档.get_node(node_id)
            if node.kind != "widget":
                return None

            cls = _控件构造器.get(node.widgetClass, QWidget)
            widget = cls(parent_widget)
            widget.setObjectName(node.name or node.id)

            if isinstance(widget, 设计期布局区域控件):
                widget.设置布局类型(node.props.get("layoutClass", "QVBoxLayout"))

            self._注册控件映射(node.id, widget)

            if node.widgetClass in ("QTabWidget", "QToolBox"):
                for page_id in getattr(node, "children", []):
                    if not self._文档.has_node(page_id):
                        continue

                    page_node = self._文档.get_node(page_id)
                    if page_node.kind != "widget":
                        continue

                    page_widget = QWidget()
                    page_widget.setObjectName(page_node.name or page_node.id)
                    page_widget.setMouseTracking(True)

                    self._页面节点到控件[page_node.id] = page_widget
                    self._页面控件到节点[page_widget] = page_node.id
                    self._安全安装过滤器(page_widget)

                    if node.widgetClass == "QTabWidget":
                        widget.addTab(page_widget, page_node.props.get("title", "Page"))
                    else:
                        widget.addItem(page_widget, page_node.props.get("label", "Page"))

                    layout_targets = set()
                    if getattr(page_node, "layout", None):
                        page_layout = self._创建布局对象(page_node.layout, page_widget, visiting_layouts, visiting_widgets)
                        page_widget.setLayout(page_layout)
                        layout_targets = self._布局管理目标集合(page_node.layout)

                    for child_id in getattr(page_node, "children", []):
                        if child_id in layout_targets or not self._文档.has_node(child_id):
                            continue

                        child_node = self._文档.get_node(child_id)
                        child_widget = self._创建控件树(child_id, page_widget, visiting_widgets, visiting_layouts)

                        if child_node.role != "page" and child_widget is not None:
                            self._应用绝对几何(child_id, child_widget)

                self._应用节点属性到控件(node.id, widget)
                self._为控件及子孙安装过滤器(widget)
                return widget

            self._应用节点属性到控件(node.id, widget)

            layout_targets = set()
            if getattr(node, "layout", None):
                layout = self._创建布局对象(node.layout, widget, visiting_layouts, visiting_widgets)
                widget.setLayout(layout)
                layout_targets = self._布局管理目标集合(node.layout)

            for child_id in getattr(node, "children", []):
                if child_id in layout_targets or not self._文档.has_node(child_id):
                    continue

                child_node = self._文档.get_node(child_id)
                child_widget = self._创建控件树(child_id, widget, visiting_widgets, visiting_layouts)

                if child_node.role != "page" and child_widget is not None:
                    self._应用绝对几何(child_id, child_widget)

            self._为控件及子孙安装过滤器(widget)
            return widget

        finally:
            visiting_widgets.discard(node_id)

    def _创建布局对象(
        self,
        layout_id: str,
        owner_widget: QWidget,
        visiting_layouts: set[str] | None = None,
        visiting_widgets: set[str] | None = None,
    ):
        if visiting_layouts is None:
            visiting_layouts = set()
        if visiting_widgets is None:
            visiting_widgets = set()

        if not layout_id or not self._文档.has_node(layout_id) or layout_id in visiting_layouts:
            return QVBoxLayout()

        visiting_layouts.add(layout_id)

        try:
            layout_node = self._文档.get_node(layout_id)
            layout_cls = _布局构造器.get(layout_node.layoutClass, QVBoxLayout)
            layout = layout_cls()

            if "spacing" in layout_node.props:
                try:
                    layout.setSpacing(int(layout_node.props["spacing"]))
                except Exception:
                    pass

            margins = (
                _限制整数(layout_node.props.get("marginLeft", 9), 0, 200, 9),
                _限制整数(layout_node.props.get("marginTop", 9), 0, 200, 9),
                _限制整数(layout_node.props.get("marginRight", 9), 0, 200, 9),
                _限制整数(layout_node.props.get("marginBottom", 9), 0, 200, 9),
            )
            layout.setContentsMargins(*margins)

            for item_id in getattr(layout_node, "items", []):
                if not self._文档.has_node(item_id):
                    continue

                item_node = self._文档.get_node(item_id)
                if not getattr(item_node, "target", None) or not self._文档.has_node(item_node.target):
                    continue

                target_node = self._文档.get_node(item_node.target)

                if item_node.itemType == "widget":
                    child_widget = self._创建控件树(target_node.id, owner_widget, visiting_widgets, visiting_layouts)
                    if child_widget is not None:
                        self._加入到布局(layout, item_node, child_widget)
                elif item_node.itemType == "layout":
                    sub_layout = self._创建布局对象(target_node.id, owner_widget, visiting_layouts, visiting_widgets)
                    self._加入子布局(layout, item_node, sub_layout)
                elif item_node.itemType == "spacer":
                    spacer = self._创建spacer项(target_node.id)
                    self._加入spacer(layout, item_node, spacer)

            return layout

        finally:
            visiting_layouts.discard(layout_id)

    def _加入到布局(self, layout: QLayout, item_node, widget: QWidget):
        if isinstance(layout, QGridLayout):
            layout.addWidget(
                widget,
                int(item_node.props.get("row", 0)),
                int(item_node.props.get("column", 0)),
                int(item_node.props.get("rowSpan", 1)),
                int(item_node.props.get("columnSpan", 1)),
            )
        elif isinstance(layout, QFormLayout):
            layout.addRow(widget)
        else:
            layout.addWidget(widget)

    def _加入子布局(self, layout: QLayout, item_node, sub_layout: QLayout):
        if isinstance(layout, QGridLayout):
            layout.addLayout(
                sub_layout,
                int(item_node.props.get("row", 0)),
                int(item_node.props.get("column", 0)),
                int(item_node.props.get("rowSpan", 1)),
                int(item_node.props.get("columnSpan", 1)),
            )
        elif isinstance(layout, QFormLayout):
            layout.addRow(sub_layout)
        else:
            layout.addLayout(sub_layout)

    def _创建spacer项(self, spacer_node_id: str):
        node = self._文档.get_node(spacer_node_id)
        size_hint = node.props.get("sizeHint", {"width": 20, "height": 40})
        orientation = node.props.get("orientation", "vertical")

        if orientation == "horizontal":
            return QSpacerItem(
                int(size_hint.get("width", 40)),
                int(size_hint.get("height", 20)),
                QSizePolicy.Expanding,
                QSizePolicy.Minimum,
            )

        return QSpacerItem(
            int(size_hint.get("width", 20)),
            int(size_hint.get("height", 40)),
            QSizePolicy.Minimum,
            QSizePolicy.Expanding,
        )

    def _加入spacer(self, layout: QLayout, item_node, spacer: QSpacerItem):
        if isinstance(layout, QGridLayout):
            layout.addItem(
                spacer,
                int(item_node.props.get("row", 0)),
                int(item_node.props.get("column", 0)),
                int(item_node.props.get("rowSpan", 1)),
                int(item_node.props.get("columnSpan", 1)),
            )
        elif isinstance(layout, QFormLayout):
            row_layout = QHBoxLayout()
            row_layout.addItem(spacer)
            layout.addRow(row_layout)
        else:
            layout.addItem(spacer)

    def _注册控件映射(self, node_id: str, widget: QWidget):
        self._节点到控件[node_id] = widget
        self._控件到节点[widget] = node_id
        self._管理器控件集合.add(widget)

        widget.setMouseTracking(True)
        self._安全安装过滤器(widget)
        widget.show()

        node = self._文档.get_node(node_id)
        if node.widgetClass in ("QTabWidget", "QToolBox"):
            widget.currentChanged.connect(lambda idx, nid=node_id: self._同步容器当前页索引(nid, idx))

    def _同步容器当前页索引(self, container_node_id: str, index: int):
        if self._正在重建画布 or not self._文档.has_node(container_node_id):
            return

        node = self._文档.get_node(container_node_id)
        node.props["currentIndex"] = int(index)
        self.文档变化.emit(self._文档)
        self._根表面.update()

    def _应用节点属性到控件(self, node_id: str, widget: QWidget):
        if not self._文档.has_node(node_id):
            return

        node = self._文档.get_node(node_id)
        props = node.props

        if isinstance(widget, 设计期布局区域控件):
            widget.设置布局类型(props.get("layoutClass", "QVBoxLayout"))
        elif isinstance(widget, QPushButton):
            widget.setText(props.get("text", "按钮"))
        elif isinstance(widget, QLabel):
            widget.setText(props.get("text", "标签"))
        elif isinstance(widget, QLineEdit):
            widget.setText(props.get("text", ""))
            widget.setPlaceholderText(props.get("placeholderText", ""))
        elif isinstance(widget, QTextEdit):
            widget.setPlainText(props.get("plainText", ""))
            widget.setPlaceholderText(props.get("placeholderText", ""))
        elif isinstance(widget, QGroupBox):
            widget.setTitle(props.get("title", "GroupBox"))
        elif isinstance(widget, QTabWidget):
            idx = int(props.get("currentIndex", 0))
            old = widget.blockSignals(True)
            if 0 <= idx < widget.count():
                widget.setCurrentIndex(idx)
            widget.blockSignals(old)
        elif isinstance(widget, QToolBox):
            idx = int(props.get("currentIndex", 0))
            old = widget.blockSignals(True)
            if 0 <= idx < widget.count():
                widget.setCurrentIndex(idx)
            widget.blockSignals(old)

    def _应用绝对几何(self, node_id: str, widget: QWidget):
        node = self._文档.get_node(node_id)
        if self._是否布局区域节点(node):
            geo = _安全取几何(node.props, default_w=180, default_h=120)
        else:
            geo = _安全取几何(node.props)
        widget.setGeometry(geo["x"], geo["y"], geo["width"], geo["height"])

    def _应用运行时节点更新(self, node_id: str, props: dict):
        widget = self._节点到控件.get(node_id)
        if widget is None or not self._文档.has_node(node_id):
            return

        if "geometry" in props and not self._文档.is_layout_managed_widget(node_id):
            self._应用绝对几何(node_id, widget)

        self._应用节点属性到控件(node_id, widget)
        self._根表面.update()
        self.update()

    def _为控件及子孙安装过滤器(self, root_widget: QWidget):
        self._安全安装过滤器(root_widget)
        for child in root_widget.findChildren(QWidget):
            child.setMouseTracking(True)
            self._安全安装过滤器(child)




    def _节点属性面板字典(self, node_id: str) -> dict | None:
        if not node_id or not self._文档.has_node(node_id):
            return None

        node = self._文档.get_node(node_id)
        data = node.to_dict()
        props = dict(data.get("props", {}))

        if getattr(node, "kind", None) == "widget":
            target_node = node

            if getattr(node, "widgetClass", None) in ("QTabWidget", "QToolBox"):
                page_id = self._获取当前页面节点(node.id)
                if page_id and self._文档.has_node(page_id):
                    target_node = self._文档.get_node(page_id)

            layout_id = getattr(target_node, "layout", None)

            if layout_id and self._文档.has_node(layout_id):
                layout_node = self._文档.get_node(layout_id)
                props["layoutClass"] = getattr(layout_node, "layoutClass", "")
                data["layoutClass"] = getattr(layout_node, "layoutClass", "")
            else:
                props["layoutClass"] = ""
                data["layoutClass"] = ""

            data["props"] = props

        return data




    # -----------------------------------------------------
    # 事件解析 / 选中
    # -----------------------------------------------------
    def _从事件对象解析节点(self, watched) -> tuple[str | None, QWidget | None]:
        w = watched if isinstance(watched, QWidget) else None

        while w is not None:
            node_id = self._控件到节点.get(w)
            if node_id:
                return node_id, self._节点到控件.get(node_id)

            page_id = self._页面控件到节点.get(w)
            if page_id:
                parent_id = self._获取父节点id(page_id)
                if parent_id and parent_id in self._节点到控件:
                    return parent_id, self._节点到控件.get(parent_id)

            w = w.parentWidget()

        return None, None

    def _事件转根表面坐标(self, watched: QWidget, event) -> QPoint:
        try:
            if hasattr(event, "position"):
                p = event.position().toPoint()
            elif hasattr(event, "pos"):
                p = event.pos()
            else:
                return QPoint()
            return self._根表面.mapFromGlobal(watched.mapToGlobal(p))
        except Exception:
            return QPoint()

    def 获取当前单选节点(self):
        if not self._当前选中节点id or not self._文档.has_node(self._当前选中节点id):
            return None
        return self._文档.get_node(self._当前选中节点id).to_dict()

    def 获取当前选中节点id列表(self) -> list[str]:
        if self._多选节点id集合:
            return [
                nid
                for nid in self._多选节点id列表
                if nid in self._多选节点id集合 and self._文档.has_node(nid)
            ]

        if self._当前选中节点id and self._文档.has_node(self._当前选中节点id):
            return [self._当前选中节点id]

        return []

    def _设置当前选中节点(self, node_id: str | None):
        self._当前选中节点id = node_id
        self._多选节点id集合.clear()
        self._多选节点id列表.clear()

        if node_id and self._文档.has_node(node_id):
            self.选中节点变化.emit(self._节点属性面板字典(node_id))
        else:
            self.选中节点变化.emit(None)

        self._根表面.update()

    def _设置多选节点(self, node_ids: list[str]):
        valid_ids = []
        seen = set()

        for nid in node_ids:
            if nid in seen or not self._文档.has_node(nid):
                continue

            node = self._文档.get_node(nid)
            if node.kind == "widget" and node.role != "page":
                valid_ids.append(nid)
                seen.add(nid)

        if len(valid_ids) == 0:
            self._当前选中节点id = None
            self._多选节点id集合.clear()
            self._多选节点id列表.clear()
            self.选中节点变化.emit(None)
            self._根表面.update()
            return

        if len(valid_ids) == 1:
            only_id = valid_ids[0]
            self._当前选中节点id = only_id
            self._多选节点id集合.clear()
            self._多选节点id列表.clear()
            self.选中节点变化.emit(self._节点属性面板字典(only_id))
            self._根表面.update()
            return

        self._当前选中节点id = None
        self._多选节点id列表 = valid_ids
        self._多选节点id集合 = set(valid_ids)
        self.选中节点变化.emit(None)
        self._根表面.update()

    def _当前选中控件(self):
        if not self._当前选中节点id:
            return None
        return self._节点到控件.get(self._当前选中节点id)

    def _当前框选矩形(self) -> QRect:
        return QRect(self._框选起点, self._框选终点).normalized()

    def _根据矩形命中控件(self, select_rect: QRect) -> list[str]:
        result = []

        for node_id, widget in self._节点到控件.items():
            if not self._文档.has_node(node_id) or not self._节点在当前可见页链上(node_id):
                continue

            try:
                if widget is None or not widget.isVisibleTo(self._根表面):
                    continue
            except Exception:
                continue

            node = self._文档.get_node(node_id)
            if node.kind != "widget" or node.role == "page":
                continue

            if select_rect.intersects(self._控件根表面矩形(widget)):
                result.append(node_id)

        return result

    def _当前选中可拖拽节点id列表(self) -> list[str]:
        return self._过滤被选中祖先包含的节点(
            [nid for nid in self.获取当前选中节点id列表() if self._节点可拖拽(nid)]
        )

    def _节点可拖拽(self, node_id: str) -> bool:
        if not node_id or not self._文档.has_node(node_id):
            return False
        node = self._文档.get_node(node_id)
        return node.kind == "widget" and node.role != "page"

    def _节点可缩放(self, node_id: str) -> bool:
        if not self._节点可拖拽(node_id):
            return False
        try:
            if self._文档.is_layout_managed_widget(node_id):
                return False
        except Exception:
            return False
        return True

    def _过滤被选中祖先包含的节点(self, node_ids: list[str]) -> list[str]:
        result = []
        seen = set()
        raw_ids = []

        for nid in node_ids:
            if nid in seen or not self._文档.has_node(nid):
                continue
            seen.add(nid)
            raw_ids.append(nid)

        raw_set = set(raw_ids)
        for nid in raw_ids:
            contained = False
            for other_id in raw_set:
                if other_id == nid:
                    continue
                try:
                    if self._文档.is_descendant_of(nid, other_id):
                        contained = True
                        break
                except Exception:
                    pass
            if not contained:
                result.append(nid)

        return result

    def _切换多选(self, node_id: str):
        if not self._节点可拖拽(node_id):
            return

        if node_id in self._多选节点id集合:
            self._多选节点id集合.remove(node_id)
            self._多选节点id列表 = [nid for nid in self._多选节点id列表 if nid != node_id]
        else:
            if self._当前选中节点id and not self._多选节点id集合:
                if self._节点可拖拽(self._当前选中节点id):
                    self._多选节点id集合.add(self._当前选中节点id)
                    self._多选节点id列表.append(self._当前选中节点id)
                self._当前选中节点id = None

            if node_id not in self._多选节点id集合:
                self._多选节点id集合.add(node_id)
                self._多选节点id列表.append(node_id)

        if len(self._多选节点id集合) == 1:
            only_id = self._多选节点id列表[0] if self._多选节点id列表 else next(iter(self._多选节点id集合))
            self._当前选中节点id = only_id
            self._多选节点id集合.clear()
            self._多选节点id列表.clear()
            self.选中节点变化.emit(self._节点属性面板字典(only_id))
        else:
            self.选中节点变化.emit(None)

        self._根表面.update()

    def _设置候选拖拽(
        self,
        primary_node_id: str,
        node_ids: list[str],
        start_pos: QPoint,
        click_fallback_node_id: str | None = None,
    ):
        self._候选拖拽节点id = primary_node_id
        self._候选拖拽节点id列表 = list(node_ids)
        self._候选拖拽起点 = QPoint(start_pos)
        self._候选点击节点id = click_fallback_node_id

    def _清除候选拖拽(self):
        self._候选拖拽节点id = None
        self._候选拖拽节点id列表 = []
        self._候选拖拽起点 = QPoint()
        self._候选点击节点id = None

    def _当前选中可拖拽祖先(self, hit_node_id: str) -> str | None:
        sid = self._当前选中节点id
        if not sid or sid == hit_node_id or not self._文档.has_node(hit_node_id) or not self._节点可拖拽(sid):
            return None
        try:
            if self._文档.is_descendant_of(hit_node_id, sid):
                return sid
        except Exception:
            return None
        return None

    def _解析点击位置最小可操作节点(self, canvas_pos: QPoint) -> str | None:
        candidates: list[tuple[int, int, str]] = []

        for node_id, widget in self._节点到控件.items():
            if not self._文档.has_node(node_id) or not self._节点在当前可见页链上(node_id):
                continue

            try:
                if widget is None or not widget.isVisibleTo(self._根表面):
                    continue
            except Exception:
                continue

            node = self._文档.get_node(node_id)
            if node.kind != "widget" or node.role == "page" or not self._节点可拖拽(node_id) or not widget.isVisible():
                continue

            rect = self._控件根表面矩形(widget)
            if not rect.contains(canvas_pos):
                continue

            candidates.append((rect.width() * rect.height(), 1 if self._节点是否可作为放置容器(node_id) else 0, node_id))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][2]

    def _提升节点到最上层(self, node_ids: list[str]):
        for nid in node_ids:
            widget = self._节点到控件.get(nid)
            if widget is not None:
                widget.raise_()
        self._根表面.update()

    def _由运行时父控件推断ownerid(self, parent_widget: QWidget | None) -> str | None:
        if parent_widget is None:
            return None
        if parent_widget is self._根表面:
            return self._文档.root
        if parent_widget is getattr(self, "_根布局宿主", None):
            return self._文档.root

        owner_id = self._控件到节点.get(parent_widget)
        if owner_id:
            return owner_id

        return self._页面控件到节点.get(parent_widget)

    # -----------------------------------------------------
    # 事件过滤 / 鼠标操作
    # -----------------------------------------------------

    def eventFilter(self, watched, event):
        # 1. 选中控件的 8 个缩放点优先。
        # 这一步必须放在画布边缘缩放前面。
        try:
            if self._处理选中控件缩放手柄事件(watched, event):
                return True
        except Exception:
            traceback.print_exc()
            return True

        # 2. 画布自身的隐形边缘缩放。
        # 注意：这里只处理画布编辑器、根表面、根布局宿主。
        # 不要对所有子控件都优先做画布边缘检测，否则会压住控件手柄。
        if watched is getattr(self, "_根表面", None) or watched is getattr(self, "_根布局宿主", None):
            try:
                if self._处理画布边缘缩放事件(watched, event):
                    return True
            except Exception:
                traceback.print_exc()
                return True

        if watched is getattr(self, "_根布局宿主", None):
            try:
                if event.type() == QEvent.MouseButtonPress:
                    return self._根表层鼠标按下(event)
                if event.type() == QEvent.MouseMove:
                    return self._根表层鼠标移动(event)
                if event.type() == QEvent.MouseButtonRelease:
                    return self._根表层鼠标释放(event)
                if event.type() == QEvent.DragEnter:
                    self._根表层拖入(event)
                    return True
                if event.type() == QEvent.DragMove:
                    self._根表层拖动(event)
                    return True
                if event.type() == QEvent.Drop:
                    self._根表层放下(event)
                    return True
            except Exception:
                traceback.print_exc()
                return True

        node_id, owner_widget = self._从事件对象解析节点(watched)
        if not node_id or owner_widget is None:
            return False

        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            return self._控件鼠标按下(watched, event, node_id, owner_widget)

        if event.type() == QEvent.MouseMove:
            return self._控件鼠标移动(watched, event)

        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            return self._控件鼠标释放(event)

        return False
    
    def _控件鼠标按下(self, watched, event, node_id: str, owner_widget: QWidget) -> bool:
        self.setFocus()

        modifiers = QApplication.keyboardModifiers()
        ctrl_pressed = bool(modifiers & Qt.ControlModifier)

        surface_pos = self._事件转根表面坐标(watched, event)
        hit_node_id = self._解析点击位置最小可操作节点(surface_pos)

        if hit_node_id:
            node_id = hit_node_id
            owner_widget = self._节点到控件.get(node_id)

        if not node_id or owner_widget is None:
            return False

        node = self._文档.get_node(node_id)

        self._操作模式 = None
        self._框选中 = False
        self._清除候选拖拽()

        drag_proxy_id = None if ctrl_pressed else self._当前选中可拖拽祖先(node_id)

        if node.widgetClass in ("QTabWidget", "QToolBox"):
            if self._是否点击容器切页区域(node_id, owner_widget, surface_pos):
                if not ctrl_pressed:
                    self._设置当前选中节点(node_id)
                return False

            if ctrl_pressed:
                self._切换多选(node_id)
                return True

            if self._多选节点id集合 and node_id in self._多选节点id集合:
                ids = self._当前选中可拖拽节点id列表()
                if ids:
                    self._设置候选拖拽(node_id, ids, surface_pos)
                    self._根表面.setCursor(Qt.SizeAllCursor)
                    self.setCursor(Qt.SizeAllCursor)
                    owner_widget.setCursor(Qt.SizeAllCursor)
                return True

            self._设置当前选中节点(node_id)

            if self._节点可拖拽(node_id) and self._手柄方向(surface_pos, owner_widget) == (0, 0):
                self._设置候选拖拽(node_id, [node_id], surface_pos)
                self._根表面.setCursor(Qt.SizeAllCursor)
                self.setCursor(Qt.SizeAllCursor)
                owner_widget.setCursor(Qt.SizeAllCursor)

            return True

        if drag_proxy_id:
            self._设置候选拖拽(drag_proxy_id, [drag_proxy_id], surface_pos, click_fallback_node_id=node_id)
            self._根表面.setCursor(Qt.SizeAllCursor)
            self.setCursor(Qt.SizeAllCursor)
            owner_widget.setCursor(Qt.SizeAllCursor)
            return True

        if ctrl_pressed:
            self._切换多选(node_id)
            return True

        if self._多选节点id集合 and node_id in self._多选节点id集合:
            ids = self._当前选中可拖拽节点id列表()
            if ids:
                self._设置候选拖拽(node_id, ids, surface_pos)
                self._根表面.setCursor(Qt.SizeAllCursor)
                self.setCursor(Qt.SizeAllCursor)
                owner_widget.setCursor(Qt.SizeAllCursor)
            return True

        self._设置当前选中节点(node_id)

        if self._节点可拖拽(node_id):
            if self._手柄方向(surface_pos, owner_widget) != (0, 0):
                return False
            self._设置候选拖拽(node_id, [node_id], surface_pos)
            self._根表面.setCursor(Qt.SizeAllCursor)
            self.setCursor(Qt.SizeAllCursor)
            owner_widget.setCursor(Qt.SizeAllCursor)
            return True

        return False

    def _控件鼠标移动(self, watched, event) -> bool:
        if self._候选拖拽节点id:
            if event.buttons() & Qt.LeftButton:
                surface_pos = self._事件转根表面坐标(watched, event)
                if (surface_pos - self._候选拖拽起点).manhattanLength() >= QApplication.startDragDistance():
                    nid = self._候选拖拽节点id
                    node_ids = list(self._候选拖拽节点id列表) or [nid]
                    if self._节点可拖拽(nid):
                        self._开始拖拽(self._候选拖拽起点, nid, node_ids)
                        self._更新拖拽预览(surface_pos)
                        self._清除候选拖拽()
                        return True
            else:
                self._清除候选拖拽()
                self._根表面.setCursor(Qt.ArrowCursor)
                self.setCursor(Qt.ArrowCursor)
                widget = self._当前选中控件()
                if widget:
                    widget.setCursor(Qt.ArrowCursor)

        # 检测缩放手柄光标（仅在没有候选拖拽时）
        if not self._候选拖拽节点id and self._当前选中节点id and self._节点可缩放(self._当前选中节点id):
            widget = self._当前选中控件()
            if widget:
                surface_pos = self._事件转根表面坐标(watched, event)
                direction = self._手柄方向(surface_pos, widget)
                cursor = self._手柄光标(direction) if direction != (0, 0) else Qt.ArrowCursor
                self._根表面.setCursor(cursor)

        return False

    def _控件鼠标释放(self, event) -> bool:
        if self._候选拖拽节点id:
            selected_id = self._候选拖拽节点id
            fallback_id = self._候选点击节点id

            self._清除候选拖拽()
            self._操作模式 = None
            self._框选中 = False
            self._拖拽节点id = None
            self._拖拽节点id列表 = []

            try:
                self._根表面.releaseMouse()
            except Exception:
                pass

            self._根表面.setCursor(Qt.ArrowCursor)
            self.setCursor(Qt.ArrowCursor)

            if fallback_id and self._文档.has_node(fallback_id):
                self._设置当前选中节点(fallback_id)
                self._根表面.update()
                return True

            if selected_id and self._文档.has_node(selected_id):
                self._设置当前选中节点(selected_id)
                self._根表面.update()
                return True

            return True

        return False

    def _根表层鼠标按下(self, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False

        self._清除候选拖拽()
        canvas_pos = event.position().toPoint()

        layout_id = self._命中布局节点(canvas_pos)
        if layout_id:
            self._设置当前选中节点(layout_id)
            return True

        widget = self._当前选中控件()
        if widget and self._当前选中节点id and self._节点可缩放(self._当前选中节点id):
            direction = self._手柄方向(canvas_pos, widget)
            if direction != (0, 0):
                self._开始缩放(canvas_pos, self._当前选中节点id, direction, widget)
                return True

        self._操作模式 = "select_rect"
        self._框选中 = True
        self._框选起点 = canvas_pos
        self._框选终点 = canvas_pos

        self._当前选中节点id = None
        self._多选节点id集合.clear()
        self._多选节点id列表.clear()
        self.选中节点变化.emit(None)

        self._根表面.update()
        return True

    def _根表层鼠标移动(self, event) -> bool:
        canvas_pos = event.position().toPoint()

        if self._操作模式 == "select_rect" and self._框选中:
            if not (event.buttons() & Qt.LeftButton):
                self._操作模式 = None
                self._框选中 = False
                self._根表面.update()
                return True
            self._框选终点 = canvas_pos
            self._根表面.update()
            return True

        if self._操作模式 == "drag" and self._拖拽节点id列表:
            if not (event.buttons() & Qt.LeftButton):
                self._结束当前操作()
                self._重建画布()
                return True
            self._更新拖拽预览(canvas_pos)
            self._根表面.update()
            return True

        if self._操作模式 == "scale" and self._拖拽节点id:
            if not (event.buttons() & Qt.LeftButton):
                self._结束当前操作()
                self._重建画布()
                return True
            self._更新缩放预览(canvas_pos)
            self._根表面.update()
            return True

        widget = self._当前选中控件()
        if widget and self._当前选中节点id and self._节点可缩放(self._当前选中节点id):
            direction = self._手柄方向(canvas_pos, widget)
            self._根表面.setCursor(self._手柄光标(direction) if direction != (0, 0) else Qt.ArrowCursor)
        else:
            self._根表面.setCursor(Qt.ArrowCursor)

        return False

    def _根表层鼠标释放(self, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False

        if self._操作模式 == "select_rect" and self._框选中:
            self._框选终点 = event.position().toPoint()
            select_rect = self._当前框选矩形()

            if select_rect.width() < 4 and select_rect.height() < 4:
                self._设置当前选中节点(None)
            else:
                self._设置多选节点(self._根据矩形命中控件(select_rect))

            self._框选中 = False
            self._操作模式 = None
            self._根表面.update()
            return True

        if self._操作模式 == "drag" and self._拖拽节点id列表:
            try:
                self._提交拖拽()
            finally:
                self._结束当前操作()
            return True

        if self._操作模式 == "scale" and self._拖拽节点id:
            try:
                self._提交缩放()
            finally:
                self._结束当前操作()
            return True

        self._结束当前操作()
        return False

    # -----------------------------------------------------
    # 外部拖放新增控件 / 布局区域
    # -----------------------------------------------------
    def _根表层拖入(self, event):
        text = event.mimeData().text() if event.mimeData().hasText() else ""
        if text.startswith("widget:") or text.startswith("layout:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _根表层拖动(self, event):
        text = event.mimeData().text() if event.mimeData().hasText() else ""
        if text.startswith("widget:") or text.startswith("layout:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _根表层放下(self, event):
        self._提交快照(self._快照())
        if not event.mimeData().hasText():
            event.ignore()
            return

        text = event.mimeData().text().strip()
        pos = event.position().toPoint()

        if text.startswith("widget:"):
            控件类 = text.split(":", 1)[1].strip()
            if 控件类 not in _控件构造器 or 控件类 == "__LayoutRegion__":
                event.ignore()
                return

            owner_id = self._解析最终落点owner(pos, None)
            real_owner_id = self._解析真实容器owner(owner_id)

            if not self._文档.has_node(real_owner_id):
                event.ignore()
                return

            owner_node = self._文档.get_node(real_owner_id)

            if getattr(owner_node, "layout", None):
                new_id = self._安全新建控件到布局容器(real_owner_id, 控件类)
            else:
                geo = self._计算新建控件放置几何(real_owner_id, pos, 控件类)
                new_id = self._文档.add_absolute_widget(real_owner_id, 控件类, geo)

            self._重建画布()
            self._设置当前选中节点(new_id)
            self.文档变化.emit(self._文档)
            event.acceptProposedAction()
            return

        if text.startswith("layout:"):
            layout_class = text.split(":", 1)[1].strip()
            if layout_class not in _布局构造器:
                event.ignore()
                return

            owner_id = self._解析最终落点owner(pos, None)
            real_owner_id = self._解析真实容器owner(owner_id)

            if not self._文档.has_node(real_owner_id):
                event.ignore()
                return

            new_id = self._新建布局区域(real_owner_id, layout_class, pos)
            self._重建画布()
            self._设置当前选中节点(new_id)
            self.文档变化.emit(self._文档)
            event.acceptProposedAction()
            return

        event.ignore()

    def _是否布局区域节点(self, node) -> bool:
        return getattr(node, "widgetClass", None) == "__LayoutRegion__" or getattr(node, "role", None) == "layoutRegion"

    def _解析真实容器owner(self, owner_id: str) -> str:
        if not owner_id or not self._文档.has_node(owner_id):
            return self._文档.root

        node = self._文档.get_node(owner_id)
        if self._是否布局区域节点(node):
            return owner_id

        try:
            return self._文档.resolve_container_drop_owner(owner_id)
        except Exception:
            return owner_id

    def _新建布局区域(self, owner_id: str, layout_class: str, canvas_pos: QPoint) -> str:
        owner_id = self._解析真实容器owner(owner_id)
        geo = self._计算新建布局区域放置几何(owner_id, canvas_pos)

        region_node = self._文档.create_widget_node(
            widget_class="__LayoutRegion__",
            name=self._生成唯一节点名("layoutRegion"),
            role="layoutRegion",
            props={"geometry": geo, "layoutClass": layout_class},
            parent=None,
        )

        layout_node = self._创建文档布局节点(layout_class, region_node.id)
        region_node.layout = layout_node.id

        owner_node = self._文档.get_node(owner_id)
        if getattr(owner_node, "layout", None):
            item = self._文档.create_layout_item_node(
                "widget",
                region_node.id,
                parent=owner_node.layout,
                props=self._默认布局项属性(owner_node.layout),
            )
            region_node.parent = item.id
            self._文档.get_node(owner_node.layout).items.append(item.id)
        else:
            region_node.parent = owner_id
            owner_node.children.append(region_node.id)

        return region_node.id

    def _安全新建控件到布局容器(self, owner_id: str, widget_class: str) -> str:
        if not self._文档.has_node(owner_id):
            owner_id = self._文档.root

        owner_node = self._文档.get_node(owner_id)
        layout_id = getattr(owner_node, "layout", None)

        if not layout_id or not self._文档.has_node(layout_id):
            geo = self._文档.default_widget_props(widget_class).get(
                "geometry", {"x": 0, "y": 0, "width": 100, "height": 30}
            )
            return self._文档.add_absolute_widget(owner_id, widget_class, geo)

        try:
            return self._文档.add_widget_to_layout(owner_id, widget_class)
        except Exception:
            traceback.print_exc()

        widget_node = self._文档.create_widget_node(
            widget_class=widget_class,
            name=self._生成唯一节点名(widget_class[1:] if widget_class.startswith("Q") else widget_class),
            role=None,
            props=self._文档.default_widget_props(widget_class),
            parent=None,
        )

        item = self._文档.create_layout_item_node(
            "widget",
            widget_node.id,
            parent=layout_id,
            props=self._默认布局项属性(layout_id),
        )
        widget_node.parent = item.id

        layout_node = self._文档.get_node(layout_id)
        if item.id not in layout_node.items:
            layout_node.items.append(item.id)

        if widget_class in ("QTabWidget", "QToolBox"):
            self._文档.ensure_default_pages(widget_node.id)

        return widget_node.id

    # -----------------------------------------------------
    # 节点 / owner 查询
    # -----------------------------------------------------
    def _获取owner实际控件(self, owner_node_id: str):
        if owner_node_id == self._文档.root:
            return self._根表面
        if owner_node_id in self._页面节点到控件:
            return self._页面节点到控件[owner_node_id]
        return self._节点到控件.get(owner_node_id)

    def _节点是否可作为放置容器(self, node_id: str) -> bool:
        try:
            if not self._文档.has_node(node_id):
                return False
            node = self._文档.get_node(node_id)
            if self._是否布局区域节点(node):
                return True
            return self._文档.can_accept_widget_drop(node_id)
        except Exception:
            return False

    def _获取当前页面节点(self, container_node_id: str) -> str | None:
        if not self._文档.has_node(container_node_id):
            return None

        node = self._文档.get_node(container_node_id)
        if node.widgetClass not in ("QTabWidget", "QToolBox"):
            return None

        widget = self._节点到控件.get(container_node_id)
        if widget is None:
            return None

        current_index = widget.currentIndex()
        node.props["currentIndex"] = current_index

        pages = self._文档.get_page_nodes(container_node_id)
        if 0 <= current_index < len(pages):
            return pages[current_index].id

        return None

    def _获取父节点id(self, node_id: str) -> str | None:
        if not node_id or not self._文档.has_node(node_id):
            return None

        if hasattr(self._文档, "get_parent_id"):
            try:
                return self._文档.get_parent_id(node_id)
            except Exception:
                pass

        if hasattr(self._文档, "get_parent_node"):
            try:
                parent_node = self._文档.get_parent_node(node_id)
                return getattr(parent_node, "id", None) if parent_node is not None else None
            except Exception:
                pass

        return None

    def _获取布局所属容器id(self, layout_id: str) -> str | None:
        if not layout_id or not self._文档.has_node(layout_id):
            return None

        if hasattr(self._文档, "get_layout_owner_widget"):
            try:
                owner = self._文档.get_layout_owner_widget(layout_id)
                return getattr(owner, "id", None) if owner is not None else None
            except Exception:
                pass

        for nid, node in self._文档.nodes.items():
            if getattr(node, "kind", None) == "widget" and getattr(node, "layout", None) == layout_id:
                return nid

        return None

    def _节点在当前可见页链上(self, node_id: str) -> bool:
        if not node_id:
            return False
        if node_id == self._文档.root:
            return True
        if not self._文档.has_node(node_id):
            return False

        cur_id = node_id
        while cur_id and cur_id != self._文档.root:
            parent_id = self._获取父节点id(cur_id)
            if not parent_id or not self._文档.has_node(parent_id):
                break

            parent_node = self._文档.get_node(parent_id)
            if getattr(parent_node, "widgetClass", None) in ("QTabWidget", "QToolBox"):
                current_page_id = self._获取当前页面节点(parent_id)
                if current_page_id != cur_id:
                    return False

            cur_id = parent_id

        return True

    def _控件内容区根表面矩形(self, node_id: str) -> QRect | None:
        if node_id == self._文档.root:
            return QRect(QPoint(0, 0), self._根表面.size())

        if not self._文档.has_node(node_id) or not self._节点在当前可见页链上(node_id):
            return None

        node = self._文档.get_node(node_id)
        widget = self._获取owner实际控件(node_id)
        if widget is None:
            return None

        try:
            if not widget.isVisibleTo(self._根表面):
                return None
        except Exception:
            return None

        if node.role == "page":
            return QRect(widget.mapTo(self._根表面, QPoint(0, 0)), widget.size())

        if node.widgetClass == "QGroupBox":
            contents = widget.contentsRect()
            return QRect(widget.mapTo(self._根表面, contents.topLeft()), contents.size())

        if node.widgetClass in ("QTabWidget", "QToolBox"):
            current_page_id = self._获取当前页面节点(node_id)
            if current_page_id:
                return self._控件内容区根表面矩形(current_page_id)
            return QRect(widget.mapTo(self._根表面, QPoint(0, 0)), widget.size())

        if widget.layout() is not None:
            contents = widget.contentsRect()
            return QRect(widget.mapTo(self._根表面, contents.topLeft()), contents.size())

        return QRect(widget.mapTo(self._根表面, QPoint(0, 0)), widget.size())

    def _布局根表面矩形(self, layout_id: str) -> QRect | None:
        if not layout_id or not self._文档.has_node(layout_id):
            return None

        layout_node = self._文档.get_node(layout_id)
        if layout_node.kind != "layout":
            return None

        owner_widget_node = None
        if hasattr(self._文档, "get_layout_owner_widget"):
            try:
                owner_widget_node = self._文档.get_layout_owner_widget(layout_id)
            except Exception:
                owner_widget_node = None

        if owner_widget_node is None:
            owner_id = self._获取布局所属容器id(layout_id)
            owner_widget_node = self._文档.get_node(owner_id) if owner_id and self._文档.has_node(owner_id) else None

        if owner_widget_node is None:
            return None

        owner_rect = self._控件内容区根表面矩形(owner_widget_node.id)
        if owner_rect is None:
            return None

        target_rects: list[QRect] = []
        for item_id in getattr(layout_node, "items", []):
            if not self._文档.has_node(item_id):
                continue

            item_node = self._文档.get_node(item_id)
            target_id = getattr(item_node, "target", None)
            if not target_id or not self._文档.has_node(target_id):
                continue

            target_node = self._文档.get_node(target_id)
            if target_node.kind == "widget":
                widget = self._节点到控件.get(target_id)
                if widget is not None:
                    rect = self._控件根表面矩形(widget)
                    if not rect.isNull():
                        target_rects.append(rect)
            elif target_node.kind == "layout":
                sub_rect = self._布局根表面矩形(target_id)
                if sub_rect is not None and not sub_rect.isNull():
                    target_rects.append(sub_rect)

        if target_rects:
            result = QRect(target_rects[0])
            for r in target_rects[1:]:
                result = result.united(r)
            margin = 6
            result = result.adjusted(-margin, -margin, margin, margin)
            return result.intersected(owner_rect)

        placeholder = QRect(owner_rect.topLeft() + QPoint(8, 8), QSize(min(120, owner_rect.width()), min(60, owner_rect.height())))
        return placeholder.intersected(owner_rect)

    def _命中布局节点(self, canvas_pos: QPoint) -> str | None:
        if self._当前选中节点id and self._文档.has_node(self._当前选中节点id):
            node = self._文档.get_node(self._当前选中节点id)
            if node.kind == "layout":
                rect = self._布局根表面矩形(node.id)
                if rect is not None and rect.contains(canvas_pos):
                    return node.id
        return None

    def _绘制布局高亮(self, qp: QPainter):
        if not self._当前选中节点id or not self._文档.has_node(self._当前选中节点id):
            return

        node = self._文档.get_node(self._当前选中节点id)
        if node.kind != "layout":
            return

        owner_id = self._获取布局所属容器id(node.id)
        if owner_id == self._文档.root:
            return

        rect = self._布局根表面矩形(node.id)
        if rect is None or rect.isNull():
            return

        qp.save()
        qp.setPen(QPen(QColor(90, 120, 200), 1, Qt.DashLine))
        qp.setBrush(QColor(90, 120, 200, 28))
        qp.drawRect(rect)

        label_rect = QRect(rect.left() + 4, rect.top() + 4, min(150, rect.width() - 8), 18)
        if label_rect.width() > 10:
            qp.fillRect(label_rect, QColor(90, 120, 200, 180))
            qp.setPen(Qt.white)
            qp.drawText(label_rect.adjusted(4, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, node.layoutClass or "QLayout")
        qp.restore()

    def _解析最终落点owner(self, canvas_pos: QPoint, dragged_id: str | None) -> str:
        candidates: list[tuple[int, str]] = []
        start_owner_id = self._拖拽节点起始ownerid映射.get(dragged_id) if dragged_id else None
        start_was_layout_managed = self._拖拽节点起始是否布局管理.get(dragged_id, False) if dragged_id else False

        def ok(owner_id: str) -> bool:
            if not self._文档.has_node(owner_id):
                return False
            if dragged_id:
                if owner_id == dragged_id:
                    return False
                try:
                    if self._文档.is_descendant_of(owner_id, dragged_id):
                        return False
                except Exception:
                    return False
                if start_was_layout_managed and start_owner_id and owner_id == start_owner_id:
                    return False
            return True

        for node_id, widget in list(self._节点到控件.items()):
            if not self._文档.has_node(node_id):
                continue

            node = self._文档.get_node(node_id)
            if node.widgetClass not in ("QTabWidget", "QToolBox"):
                continue
            if widget is None or not self._节点在当前可见页链上(node_id):
                continue

            try:
                if not widget.isVisibleTo(self._根表面):
                    continue
            except Exception:
                continue

            current_page_id = self._获取当前页面节点(node_id)
            if not current_page_id or not ok(current_page_id):
                continue

            rect = self._控件内容区根表面矩形(current_page_id)
            if rect is not None and rect.contains(canvas_pos):
                candidates.append((rect.width() * rect.height(), current_page_id))

        for node_id, widget in list(self._节点到控件.items()):
            if not self._文档.has_node(node_id):
                continue
            if not self._节点是否可作为放置容器(node_id) or not ok(node_id):
                continue
            if not self._节点在当前可见页链上(node_id):
                continue

            if widget is not None:
                try:
                    if not widget.isVisibleTo(self._根表面):
                        continue
                except Exception:
                    continue

            rect = self._控件内容区根表面矩形(node_id)
            if rect is not None and rect.contains(canvas_pos):
                candidates.append((rect.width() * rect.height(), node_id))

        root_rect = QRect(QPoint(0, 0), self._根表面.size())
        if root_rect.contains(canvas_pos):
            candidates.append((root_rect.width() * root_rect.height(), self._文档.root))

        if not candidates:
            return self._文档.root

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _计算新建控件放置几何(self, owner_node_id: str, canvas_pos: QPoint, widget_class: str) -> dict:
        owner_widget = self._获取owner实际控件(owner_node_id) or self._根表面
        local = owner_widget.mapFrom(self._根表面, canvas_pos)
        default_geo = self._文档.default_widget_props(widget_class)["geometry"]

        return {
            "x": max(0, local.x()),
            "y": max(0, local.y()),
            "width": _限制整数(default_geo.get("width", 100), 1, 画布最大宽高, 100),
            "height": _限制整数(default_geo.get("height", 30), 1, 画布最大宽高, 30),
        }

    def _计算新建布局区域放置几何(self, owner_node_id: str, canvas_pos: QPoint) -> dict:
        owner_widget = self._获取owner实际控件(owner_node_id) or self._根表面
        local = owner_widget.mapFrom(self._根表面, canvas_pos)
        return {"x": max(0, local.x()), "y": max(0, local.y()), "width": 180, "height": 120}

    def _计算已有控件放置几何(self, owner_node_id: str, widget_node_id: str, canvas_top_left: QPoint) -> dict:
        owner_widget = self._获取owner实际控件(owner_node_id) or self._根表面
        widget_node = self._文档.get_node(widget_node_id)

        if self._是否布局区域节点(widget_node):
            old_geo = _安全取几何(widget_node.props, default_w=180, default_h=120)
        else:
            old_geo = _安全取几何(widget_node.props)

        local = owner_widget.mapFrom(self._根表面, canvas_top_left)
        return {
            "x": max(0, local.x()),
            "y": max(0, local.y()),
            "width": old_geo["width"],
            "height": old_geo["height"],
        }

    def _处理选中控件缩放手柄事件(self, watched, event) -> bool:
        """
        让选中控件的 8 个缩放点在任何子控件事件上都能正常工作。
        优先级高于画布自身缩放。
        """
        if not isinstance(watched, QWidget):
            return False

        event_type = event.type()

        if event_type not in (
            QEvent.MouseButtonPress,
            QEvent.MouseMove,
            QEvent.MouseButtonRelease,
        ):
            return False

        # 画布自身正在缩放时，不处理控件缩放。
        if self._操作模式 == "canvas_scale":
            return False

        # 控件正在拖拽时，继续接管 move / release。
        if self._操作模式 == "drag" and self._拖拽节点id列表:
            canvas_pos = self._事件转根表面坐标(watched, event)

            if event_type == QEvent.MouseMove:
                if event.buttons() & Qt.LeftButton:
                    self._更新拖拽预览(canvas_pos)
                    self._根表面.update()
                    event.accept()
                    return True

                self._结束当前操作()
                return True

            if event_type == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    try:
                        self._提交拖拽()
                    finally:
                        self._结束当前操作()
                    event.accept()
                    return True

                return False

        # 控件正在缩放时，继续接管 move / release。
        if self._操作模式 == "scale" and self._拖拽节点id:
            canvas_pos = self._事件转根表面坐标(watched, event)

            if event_type == QEvent.MouseMove:
                if event.buttons() & Qt.LeftButton:
                    self._更新缩放预览(canvas_pos)
                    self._根表面.update()
                    event.accept()
                    return True

                self._结束当前操作()
                return True

            if event_type == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    try:
                        self._提交缩放()
                    finally:
                        self._结束当前操作()

                    event.accept()
                    return True

            return False

        if not self._当前选中节点id:
            return False

        if not self._节点可缩放(self._当前选中节点id):
            return False

        widget = self._当前选中控件()
        if widget is None:
            return False

        canvas_pos = self._事件转根表面坐标(watched, event)
        direction = self._手柄方向(canvas_pos, widget)

        if event_type == QEvent.MouseMove:
            if direction != (0, 0):
                cursor = self._手柄光标(direction)
                self.setCursor(cursor)
                self._根表面.setCursor(cursor)
                widget.setCursor(cursor)
                event.accept()
                return True

            if self._候选拖拽节点id:
                self._根表面.setCursor(Qt.SizeAllCursor)
                self.setCursor(Qt.SizeAllCursor)
                widget.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
                self._根表面.setCursor(Qt.ArrowCursor)
                widget.setCursor(Qt.ArrowCursor)
            return False

        if event_type == QEvent.MouseButtonPress:
            if event.button() != Qt.LeftButton:
                return False

            if direction == (0, 0):

                # self.setCursor(Qt.ArrowCursor)
                # self._根表面.setCursor(Qt.ArrowCursor)
                # widget.setCursor(Qt.ArrowCursor)

                return False

            self._开始缩放(
                canvas_pos,
                self._当前选中节点id,
                direction,
                widget,
            )

            event.accept()
            return True

        return False




    # -----------------------------------------------------
    # 画布自身隐形边缘缩放，方案 B
    # -----------------------------------------------------

    def _事件转编辑器坐标(self, watched: QWidget, event) -> QPoint:
        try:
            if hasattr(event, "position"):
                p = event.position().toPoint()
            elif hasattr(event, "pos"):
                p = event.pos()
            else:
                return QPoint()

            if watched is self:
                return p

            if isinstance(watched, QWidget):
                return self.mapFromGlobal(watched.mapToGlobal(p))

            return QPoint()
        except Exception:
            return QPoint()

    def _画布边缘方向(self, editor_pos: QPoint):
        rect = self._根表面.geometry()
        edge = getattr(self, "_画布边缘热区", 8)

        if rect.isNull():
            return (0, 0)

        outer = rect.adjusted(-edge, -edge, edge, edge)
        inner = rect.adjusted(edge, edge, -edge, -edge)

        if not outer.contains(editor_pos):
            return (0, 0)

        if inner.contains(editor_pos):
            return (0, 0)

        near_left = abs(editor_pos.x() - rect.left()) <= edge
        near_right = abs(editor_pos.x() - rect.right()) <= edge
        near_top = abs(editor_pos.y() - rect.top()) <= edge
        near_bottom = abs(editor_pos.y() - rect.bottom()) <= edge

        dx = 0
        dy = 0

        if near_left:
            dx = -1
        elif near_right:
            dx = 1

        if near_top:
            dy = -1
        elif near_bottom:
            dy = 1

        return (dx, dy)

    def _处理画布边缘缩放事件(self, watched, event) -> bool:
        event_type = event.type()

        # 如果正在进行控件拖拽、控件缩放、框选等操作，不抢事件。
        if self._操作模式 is not None and self._操作模式 != "canvas_scale":
            return False

        if event_type == QEvent.MouseButtonPress:
            if event.button() != Qt.LeftButton:
                return False

            editor_pos = self._事件转编辑器坐标(watched, event)
            direction = self._画布边缘方向(editor_pos)

            if direction == (0, 0):
                return False

            self._开始画布缩放(editor_pos, direction)
            event.accept()
            return True

        if event_type == QEvent.MouseMove:
            editor_pos = self._事件转编辑器坐标(watched, event)

            if self._操作模式 == "canvas_scale":
                if event.buttons() & Qt.LeftButton:
                    self._更新画布缩放预览(editor_pos)
                    event.accept()
                    return True

                try:
                    self._提交画布缩放()
                finally:
                    self._结束当前操作()

                event.accept()
                return True

            direction = self._画布边缘方向(editor_pos)

            if direction != (0, 0):
                cursor = self._手柄光标(direction)
                self.setCursor(cursor)
                self._根表面.setCursor(cursor)
                event.accept()
                return True

            if watched is self or watched is self._根表面 or watched is getattr(self, "_根布局宿主", None):
                self.setCursor(Qt.ArrowCursor)
                self._根表面.setCursor(Qt.ArrowCursor)

            return False

        if event_type == QEvent.MouseButtonRelease:
            if event.button() != Qt.LeftButton:
                return False

            if self._操作模式 == "canvas_scale":
                try:
                    self._提交画布缩放()
                finally:
                    self._结束当前操作()

                event.accept()
                return True

        return False

    def _开始画布缩放(self, start_pos: QPoint, direction: tuple[int, int]):
        self._操作模式 = "canvas_scale"
        self._画布缩放方向 = direction
        self._画布缩放起点 = QPoint(start_pos)
        self._画布缩放起始矩形 = QRect(self._根表面.geometry())
        self._画布缩放起始文档快照 = copy.deepcopy(self._快照())

        # 拖拽画布边缘时，把属性面板切到根窗口。
        self._当前选中节点id = self._文档.root
        self._多选节点id集合.clear()
        self._多选节点id列表.clear()

        try:
            self.选中节点变化.emit(self._节点属性面板字典(self._文档.root))
        except Exception:
            traceback.print_exc()

        cursor = self._手柄光标(direction)
        self.setCursor(cursor)
        self._根表面.setCursor(cursor)

        # 不要 grabMouse。
        # Qt 鼠标按下后有隐式捕获，手动 grabMouse 容易导致窗口无法关闭。

    def _更新画布缩放预览(self, editor_pos: QPoint):
        dx_dir, dy_dir = self._画布缩放方向

        start = QRect(self._画布缩放起始矩形)
        offset = editor_pos - self._画布缩放起点

        min_w = 画布最小宽高
        min_h = 画布最小宽高
        max_w = 画布最大宽高
        max_h = 画布最大宽高

        left = start.left()
        top = start.top()
        right = start.left() + start.width()
        bottom = start.top() + start.height()

        new_left = left
        new_top = top
        new_right = right
        new_bottom = bottom

        if dx_dir == -1:
            candidate = left + offset.x()
            candidate = max(0, candidate)
            candidate = min(candidate, right - min_w)
            candidate = max(candidate, right - max_w)
            new_left = candidate

        elif dx_dir == 1:
            candidate = right + offset.x()
            candidate = max(candidate, left + min_w)
            candidate = min(candidate, left + max_w)
            new_right = candidate

        if dy_dir == -1:
            candidate = top + offset.y()
            candidate = max(0, candidate)
            candidate = min(candidate, bottom - min_h)
            candidate = max(candidate, bottom - max_h)
            new_top = candidate

        elif dy_dir == 1:
            candidate = bottom + offset.y()
            candidate = max(candidate, top + min_h)
            candidate = min(candidate, top + max_h)
            new_bottom = candidate

        new_w = new_right - new_left
        new_h = new_bottom - new_top

        new_w = _限制整数(new_w, 画布最小宽高, 画布最大宽高, 380)
        new_h = _限制整数(new_h, 画布最小宽高, 画布最大宽高, 550)

        self._画布位置 = QPoint(new_left, new_top)

        self._根表面.setGeometry(new_left, new_top, new_w, new_h)
        self.setMinimumSize(new_left + new_w + 10, new_top + new_h + 10)

        if getattr(self, "_根布局宿主", None) is not None:
            try:
                self._根布局宿主.setGeometry(self._根表面.rect())
            except RuntimeError:
                self._根布局宿主 = None
            except Exception:
                traceback.print_exc()

        self._实时同步画布尺寸到文档(new_w, new_h)

        self._根表面.update()
        self.update()

    def _实时同步画布尺寸到文档(self, w: int, h: int):
        w = _限制整数(w, 画布最小宽高, 画布最大宽高, 380)
        h = _限制整数(h, 画布最小宽高, 画布最大宽高, 550)

        root_node = self._文档.get_root_node()
        geo = root_node.props.setdefault("geometry", {})

        old_w = int(geo.get("width", 380))
        old_h = int(geo.get("height", 550))

        if old_w == w and old_h == h:
            return

        geo["width"] = w
        geo["height"] = h

        # 实时通知右侧属性面板和文档监听方。
        self.文档变化.emit(self._文档)

        try:
            self.选中节点变化.emit(self._节点属性面板字典(self._文档.root))
        except Exception:
            traceback.print_exc()

    def _提交画布缩放(self):
        if self._操作模式 != "canvas_scale":
            return

        rect = self._根表面.geometry()

        w = _限制整数(
            rect.width(),
            画布最小宽高,
            画布最大宽高,
            380,
        )
        h = _限制整数(
            rect.height(),
            画布最小宽高,
            画布最大宽高,
            550,
        )

        old_rect = self._画布缩放起始矩形

        if old_rect.width() == w and old_rect.height() == h:
            return

        # 拖动过程中已经实时写入文档；
        # 这里只把“拖动开始前”的快照压入撤销栈，避免 mouseMove 产生大量撤销记录。
        if self._画布缩放起始文档快照 is not None:
            self._提交快照(self._画布缩放起始文档快照)

        self._实时同步画布尺寸到文档(w, h)

        self.文档变化.emit(self._文档)

        try:
            self.选中节点变化.emit(self._节点属性面板字典(self._文档.root))
        except Exception:
            traceback.print_exc()

    def _开始拖拽(self, start_pos: QPoint, primary_node_id: str, node_ids: list[str]):
        node_ids = self._过滤被选中祖先包含的节点(node_ids)
        if not node_ids:
            return

        self._提升节点到最上层(node_ids)

        self._操作模式 = "drag"
        self._拖拽节点id = primary_node_id
        self._拖拽节点id列表 = list(node_ids)
        self._拖拽起始点 = QPoint(start_pos)

        self._拖拽节点原父控件映射 = {}
        self._拖拽节点起始是否布局管理 = {}
        self._拖拽节点起始ownerid映射 = {}
        self._拖拽节点起始矩形映射 = {
            nid: self._控件根表面矩形(self._节点到控件[nid])
            for nid in node_ids
            if nid in self._节点到控件
        }

        for nid in node_ids:
            widget = self._节点到控件.get(nid)
            if widget is None:
                continue

            old_parent = widget.parentWidget()
            self._拖拽节点原父控件映射[nid] = old_parent
            self._拖拽节点起始ownerid映射[nid] = self._由运行时父控件推断ownerid(old_parent)

            was_layout_managed = self._文档.is_layout_managed_widget(nid)
            self._拖拽节点起始是否布局管理[nid] = was_layout_managed

            if was_layout_managed:
                start_rect = self._拖拽节点起始矩形映射.get(nid)
                if start_rect is None:
                    continue

                widget.setParent(self._根表面)
                widget.setGeometry(start_rect)
                widget.show()
                widget.raise_()
                self._安全安装过滤器(widget)

        self._根表面.setCursor(Qt.SizeAllCursor)
        self.setCursor(Qt.SizeAllCursor)
        self._根表面.grabMouse()

    def _更新拖拽预览(self, canvas_pos: QPoint):
        if not self._拖拽节点起始矩形映射:
            return

        dx = canvas_pos.x() - self._拖拽起始点.x()
        dy = canvas_pos.y() - self._拖拽起始点.y()
        root_rect = QRect(QPoint(0, 0), self._根表面.size())

        group_rect = None
        for rect in self._拖拽节点起始矩形映射.values():
            group_rect = QRect(rect) if group_rect is None else group_rect.united(rect)

        if group_rect is None:
            return

        dx = max(root_rect.left() - group_rect.left(), min(dx, root_rect.right() - group_rect.right()))
        dy = max(root_rect.top() - group_rect.top(), min(dy, root_rect.bottom() - group_rect.bottom()))

        for node_id, start_rect in self._拖拽节点起始矩形映射.items():
            widget = self._节点到控件.get(node_id)
            if widget is None:
                continue

            new_rect = QRect(start_rect)
            new_rect.moveTopLeft(start_rect.topLeft() + QPoint(dx, dy))

            parent_widget = widget.parentWidget() or self._根表面
            if parent_widget is self._根表面:
                local_top_left = new_rect.topLeft()
            else:
                local_top_left = parent_widget.mapFrom(self._根表面, new_rect.topLeft())

            widget.move(local_top_left)
            widget.raise_()

        self._根表面.update()

    def _提交拖拽(self):
        self._提交快照(self._快照())
        moved_ids = self._过滤被选中祖先包含的节点(
            [nid for nid in self._拖拽节点id列表 if self._文档.has_node(nid)]
        )
        if not moved_ids:
            return

        group_rect = None
        for nid in moved_ids:
            widget = self._节点到控件.get(nid)
            if widget is None:
                continue
            rect = self._控件根表面矩形(widget)
            group_rect = QRect(rect) if group_rect is None else group_rect.united(rect)

        if group_rect is None:
            return

        primary_id = self._拖拽节点id if self._拖拽节点id in moved_ids else moved_ids[0]
        owner_id = self._解析最终落点owner(group_rect.center(), primary_id)
        real_owner_id = self._解析真实容器owner(owner_id)

        for nid in moved_ids:
            if real_owner_id == nid:
                real_owner_id = self._文档.root
                break
            try:
                if self._文档.is_descendant_of(real_owner_id, nid):
                    real_owner_id = self._文档.root
                    break
            except Exception:
                pass

        try:
            owner_node = self._文档.get_node(real_owner_id)
        except Exception:
            real_owner_id = self._文档.root
            owner_node = self._文档.get_node(real_owner_id)

        for node_id in moved_ids:
            widget = self._节点到控件.get(node_id)
            if widget is None or not self._文档.has_node(node_id):
                continue

            try:
                final_top_left = self._控件根表面矩形(widget).topLeft()
                if getattr(owner_node, "layout", None):
                    self._移动已有控件到布局容器(node_id, real_owner_id)
                else:
                    geometry = self._计算已有控件放置几何(real_owner_id, node_id, final_top_left)
                    self._移动已有控件到绝对容器(node_id, real_owner_id, geometry)
            except Exception:
                traceback.print_exc()

        self._重建画布()
        existing_moved_ids = [nid for nid in moved_ids if self._文档.has_node(nid)]
        self._设置多选节点(existing_moved_ids)
        self.文档变化.emit(self._文档)

    def _开始缩放(self, start_pos: QPoint, node_id: str, direction: tuple[int, int], widget: QWidget):
        if not self._节点可缩放(node_id):
            return

        self._提升节点到最上层([node_id])
        self._操作模式 = "scale"
        self._拖拽节点id = node_id
        self._缩放方向 = direction
        self._拖拽起始点 = QPoint(start_pos)
        self._拖拽节点起始画布矩形 = self._控件根表面矩形(widget)

        self._根表面.setCursor(self._手柄光标(direction))
        self._根表面.grabMouse()

    def _更新缩放预览(self, canvas_pos: QPoint):
        widget = self._节点到控件.get(self._拖拽节点id)
        if widget is None or not self._节点可缩放(self._拖拽节点id):
            return

        dx_dir, dy_dir = self._缩放方向
        offset = canvas_pos - self._拖拽起始点
        start = self._拖拽节点起始画布矩形

        x, y, w, h = start.x(), start.y(), start.width(), start.height()
        min_w, min_h = 20, 20
        root_w, root_h = self._根表面.width(), self._根表面.height()

        if dx_dir == -1:
            new_x = max(0, min(x + offset.x(), x + w - min_w))
            w = (x + w) - new_x
            x = new_x
        elif dx_dir == 1:
            w = min(max(min_w, w + offset.x()), root_w - x)

        if dy_dir == -1:
            new_y = max(0, min(y + offset.y(), y + h - min_h))
            h = (y + h) - new_y
            y = new_y
        elif dy_dir == 1:
            h = min(max(min_h, h + offset.y()), root_h - y)

        rect = QRect(x, y, w, h)
        parent_widget = widget.parentWidget() or self._根表面
        widget.setGeometry(QRect(parent_widget.mapFrom(self._根表面, rect.topLeft()), rect.size()))
        widget.raise_()

    def _提交缩放(self):
        self._提交快照(self._快照())
        if not self._拖拽节点id or not self._文档.has_node(self._拖拽节点id) or not self._节点可缩放(self._拖拽节点id):
            return

        widget = self._节点到控件.get(self._拖拽节点id)
        if widget is None:
            return

        local = widget.geometry()
        self._文档.update_node_props(
            self._拖拽节点id,
            {
                "geometry": {
                    "x": local.x(),
                    "y": local.y(),
                    "width": local.width(),
                    "height": local.height(),
                }
            },
        )

        self.文档变化.emit(self._文档)
        self.选中节点变化.emit(self._文档.get_node(self._拖拽节点id).to_dict())
        self._根表面.update()

    def _移动已有控件到布局容器(self, node_id: str, owner_id: str):
        if not self._文档.has_node(node_id) or not self._文档.has_node(owner_id):
            return

        owner_node = self._文档.get_node(owner_id)
        layout_id = getattr(owner_node, "layout", None)
        if not layout_id or not self._文档.has_node(layout_id):
            return

        node = self._文档.get_node(node_id)
        self._从旧父级摘除节点(node_id)

        item = self._文档.create_layout_item_node(
            "widget",
            node_id,
            parent=layout_id,
            props=self._默认布局项属性(layout_id),
        )
        node.parent = item.id

        layout_node = self._文档.get_node(layout_id)
        if item.id not in layout_node.items:
            layout_node.items.append(item.id)

    def _移动已有控件到绝对容器(self, node_id: str, owner_id: str, geometry: dict):
        if not self._文档.has_node(node_id) or not self._文档.has_node(owner_id):
            return

        node = self._文档.get_node(node_id)
        owner_node = self._文档.get_node(owner_id)
        self._从旧父级摘除节点(node_id)

        node.parent = owner_id
        node.props["geometry"] = {
            "x": _限制整数(geometry.get("x", 0), -画布最大宽高, 画布最大宽高, 0),
            "y": _限制整数(geometry.get("y", 0), -画布最大宽高, 画布最大宽高, 0),
            "width": _限制整数(geometry.get("width", 100), 1, 画布最大宽高, 100),
            "height": _限制整数(geometry.get("height", 30), 1, 画布最大宽高, 30),
        }

        if node_id not in owner_node.children:
            owner_node.children.append(node_id)

    def _从旧父级摘除节点(self, node_id: str):
        if not self._文档.has_node(node_id):
            return

        node = self._文档.get_node(node_id)
        parent_id = getattr(node, "parent", None)

        if parent_id and self._文档.has_node(parent_id):
            parent_node = self._文档.get_node(parent_id)

            if getattr(parent_node, "kind", None) == "widget":
                if node_id in getattr(parent_node, "children", []):
                    parent_node.children = [cid for cid in parent_node.children if cid != node_id]

            elif getattr(parent_node, "kind", None) == "layoutItem":
                layout_id = getattr(parent_node, "parent", None)
                if layout_id and self._文档.has_node(layout_id):
                    layout_node = self._文档.get_node(layout_id)
                    if parent_id in getattr(layout_node, "items", []):
                        layout_node.items = [iid for iid in layout_node.items if iid != parent_id]
                self._文档.nodes.pop(parent_id, None)

        for maybe_layout_node in list(self._文档.nodes.values()):
            if getattr(maybe_layout_node, "kind", None) != "layout":
                continue

            new_items = []
            changed = False
            for item_id in getattr(maybe_layout_node, "items", []):
                if not self._文档.has_node(item_id):
                    changed = True
                    continue

                item_node = self._文档.get_node(item_id)
                if getattr(item_node, "target", None) == node_id:
                    changed = True
                    self._文档.nodes.pop(item_id, None)
                    continue

                new_items.append(item_id)

            if changed:
                maybe_layout_node.items = new_items

        for maybe_owner_node in list(self._文档.nodes.values()):
            if getattr(maybe_owner_node, "kind", None) != "widget":
                continue
            if node_id in getattr(maybe_owner_node, "children", []):
                maybe_owner_node.children = [cid for cid in maybe_owner_node.children if cid != node_id]

        node.parent = None

    def _结束当前操作(self):
        try:
            self._根表面.releaseMouse()
        except Exception:
            pass

        try:
            self.releaseMouse()
        except Exception:
            pass

        self._操作模式 = None
        self._拖拽节点id = None
        self._拖拽节点id列表 = []

        self._拖拽节点起始矩形映射.clear()
        self._拖拽节点原父控件映射.clear()
        self._拖拽节点起始是否布局管理.clear()
        self._拖拽节点起始ownerid映射.clear()

        self._缩放方向 = (0, 0)

        self._画布缩放方向 = (0, 0)
        self._画布缩放起点 = QPoint()
        self._画布缩放起始矩形 = QRect()
        self._画布缩放起始文档快照 = None

        self._框选中 = False
        self._清除候选拖拽()

        self._根表面.setCursor(Qt.ArrowCursor)
        self.setCursor(Qt.ArrowCursor)

        self._根表面.update()
        self.update()


    def 删除当前选中(self):
        ids = self._过滤被选中祖先包含的节点(self.获取当前选中节点id列表())
        if not ids:
            return

        self._提交快照()

        for node_id in list(ids):
            if node_id != self._文档.root and self._文档.has_node(node_id):
                self._文档.remove_node(node_id)

        self._当前选中节点id = None
        self._多选节点id集合.clear()
        self._多选节点id列表.clear()

        self._结束当前操作()
        self._重建画布()
        self.文档变化.emit(self._文档)
        self.选中节点变化.emit(None)


    def 删除节点(self, node_id: str):
        if not node_id or not self._文档.has_node(node_id) or node_id == self._文档.root:
            return

        self._提交快照()

        self._文档.remove_node(node_id)

        if self._当前选中节点id == node_id:
            self._当前选中节点id = None

        if node_id in self._多选节点id集合:
            self._多选节点id集合.remove(node_id)
            self._多选节点id列表 = [nid for nid in self._多选节点id列表 if nid != node_id]

        self._结束当前操作()
        self._重建画布()
        self.文档变化.emit(self._文档)
        self.选中节点变化.emit(None)

    def 打印JSON(self):
        text = json.dumps(self._文档.to_dict(), ensure_ascii=False, indent=2)
        print(text)
        return text

    # -----------------------------------------------------
    # 绘制辅助
    # -----------------------------------------------------
    def _控件根表面矩形(self, widget: QWidget) -> QRect:
        try:
            return QRect(widget.mapTo(self._根表面, QPoint(0, 0)), widget.size())
        except RuntimeError:
            return QRect()

    def _是否点击容器切页区域(self, node_id: str, owner_widget: QWidget, surface_pos: QPoint) -> bool:
        if not self._文档.has_node(node_id):
            return False

        node = self._文档.get_node(node_id)
        local_pos = owner_widget.mapFrom(self._根表面, surface_pos)

        if node.widgetClass == "QTabWidget":
            try:
                tab_bar = owner_widget.tabBar()
                return tab_bar is not None and tab_bar.rect().contains(tab_bar.mapFrom(owner_widget, local_pos))
            except Exception:
                return False

        if node.widgetClass == "QToolBox":
            try:
                current_widget = owner_widget.widget(owner_widget.currentIndex())
                if current_widget is None:
                    return False
                content_rect = QRect(current_widget.mapTo(owner_widget, QPoint(0, 0)), current_widget.size())
                return not content_rect.contains(local_pos)
            except Exception:
                return False

        return False

    def _手柄方向(self, pos: QPoint, widget: QWidget):
        rect = self._控件根表面矩形(widget)
        size = 10
        gap = 4
        half = size // 2

        left = rect.left() - gap
        right = rect.right() + gap
        top = rect.top() - gap
        bottom = rect.bottom() + gap
        cx = rect.center().x()
        cy = rect.center().y()

        handle_map = {
            (-1, -1): QPoint(left, top),
            (0, -1): QPoint(cx, top),
            (1, -1): QPoint(right, top),
            (-1, 0): QPoint(left, cy),
            (1, 0): QPoint(right, cy),
            (-1, 1): QPoint(left, bottom),
            (0, 1): QPoint(cx, bottom),
            (1, 1): QPoint(right, bottom),
        }

        for direction, center in handle_map.items():
            if QRect(center.x() - half, center.y() - half, size, size).contains(pos):
                return direction

        return (0, 0)

    def _手柄光标(self, direction):
        return {
            (-1, -1): Qt.SizeFDiagCursor,
            (1, 1): Qt.SizeFDiagCursor,
            (1, -1): Qt.SizeBDiagCursor,
            (-1, 1): Qt.SizeBDiagCursor,
            (0, -1): Qt.SizeVerCursor,
            (0, 1): Qt.SizeVerCursor,
            (-1, 0): Qt.SizeHorCursor,
            (1, 0): Qt.SizeHorCursor,
        }.get(direction, Qt.ArrowCursor)

    def _绘制缩放控制点(self, qp: QPainter, rect: QRect):
        qp.setBrush(QColor(255, 0, 0))
        qp.setPen(Qt.NoPen)

        size = 4
        gap = 2
        half = size // 2

        points = [
            QPoint(rect.left() - gap, rect.top() - gap),
            QPoint(rect.center().x(), rect.top() - gap),
            QPoint(rect.right() + gap, rect.top() - gap),
            QPoint(rect.left() - gap, rect.center().y()),
            QPoint(rect.right() + gap, rect.center().y()),
            QPoint(rect.left() - gap, rect.bottom() + gap),
            QPoint(rect.center().x(), rect.bottom() + gap),
            QPoint(rect.right() + gap, rect.bottom() + gap),
        ]

        for p in points:
            qp.drawRect(QRect(p.x() - half, p.y() - half, size, size))

    def _绘制点阵网格(self, qp: QPainter, rect: QRect):
        if rect.width() * rect.height() > 8_000_000:
            return

        spacing = max(4, int(self._网格间距))

        qp.save()
        qp.setPen(Qt.NoPen)
        qp.setBrush(self._网格颜色)

        x = rect.left() + 3
        while x <= rect.right():
            y = rect.top() + 3
            while y <= rect.bottom():
                qp.drawRect(x, y, 1, 1)
                y += spacing
            x += spacing

        qp.restore()




if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    win = 画布编辑器()
    win.show()
    app.exec()
