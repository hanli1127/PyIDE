#// 文件2：原路径/pyide_model.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import copy



支持布局类 = ("QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout")





@dataclass
class NodeModel:
    id: str
    kind: str  # widget / layout / layoutItem / spacer / action ...
    name: str = ""
    parent: Optional[str] = None

    # widget
    widgetClass: Optional[str] = None
    role: Optional[str] = None  # root / page / layoutRegion / normal / ...

    # layout
    layoutClass: Optional[str] = None

    # layoutItem
    itemType: Optional[str] = None  # widget / layout / spacer
    target: Optional[str] = None

    # relationships
    children: List[str] = field(default_factory=list)
    layout: Optional[str] = None
    items: List[str] = field(default_factory=list)

    # data
    props: Dict[str, Any] = field(default_factory=dict)
    style: Dict[str, Any] = field(default_factory=dict)
    events: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    locks: Dict[str, Any] = field(default_factory=dict)
    extensions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "parent": self.parent,
            "widgetClass": self.widgetClass,
            "role": self.role,
            "layoutClass": self.layoutClass,
            "itemType": self.itemType,
            "target": self.target,
            "children": list(self.children),
            "layout": self.layout,
            "items": list(self.items),
            "props": copy.deepcopy(self.props),
            "style": copy.deepcopy(self.style),
            "events": copy.deepcopy(self.events),
            "meta": copy.deepcopy(self.meta),
            "locks": copy.deepcopy(self.locks),
            "extensions": copy.deepcopy(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NodeModel":
        return cls(
            id=data["id"],
            kind=data["kind"],
            name=data.get("name", ""),
            parent=data.get("parent"),
            widgetClass=data.get("widgetClass"),
            role=data.get("role"),
            layoutClass=data.get("layoutClass"),
            itemType=data.get("itemType"),
            target=data.get("target"),
            children=list(data.get("children", [])),
            layout=data.get("layout"),
            items=list(data.get("items", [])),
            props=copy.deepcopy(data.get("props", {})),
            style=copy.deepcopy(data.get("style", {})),
            events=copy.deepcopy(data.get("events", {})),
            meta=copy.deepcopy(data.get("meta", {})),
            locks=copy.deepcopy(data.get("locks", {})),
            extensions=copy.deepcopy(data.get("extensions", {})),
        )


class UiDocument:
    def __init__(self):
        self.format = "pyide.ui-document"
        self.version = "2.0"
        self.meta = {
            "title": "Form",
            "source": {
                "type": "ui",
                "path": "",
            },
        }
        self.settings = {
            "designWidth": 380,
            "designHeight": 550,
            "snapToGrid": True,
            "gridSize": 10,
        }
        self.root: str = ""
        self.nodes: Dict[str, NodeModel] = {}
        self.assets: Dict[str, Any] = {}
        self.extensions: Dict[str, Any] = {}
        self._id_counter = 1
        self._build_default_document()

    # -----------------------------------------------------
    # 初始化 / 序列化
    # -----------------------------------------------------
    def _build_default_document(self):
        root_id = self.next_id("node_form")
        root_node = NodeModel(
            id=root_id,
            kind="widget",
            name="Form",
            parent=None,
            widgetClass="QWidget",
            role="root",
            props={
                "geometry": {"x": 0, "y": 0, "width": 550, "height": 380},
                "windowTitle": "Form",
            },
        )
        self.root = root_id
        self.nodes[root_id] = root_node

    @classmethod
    def create_empty(cls, width: int = 550, height: int = 380, title: str = "Form") -> "UiDocument":
        doc = cls()
        root = doc.get_root_node()
        root.props["geometry"] = {"x": 0, "y": 0, "width": width, "height": height}
        root.props["windowTitle"] = title
        doc.meta["title"] = title
        doc.settings["designWidth"] = width
        doc.settings["designHeight"] = height
        return doc

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "version": self.version,
            "meta": copy.deepcopy(self.meta),
            "settings": copy.deepcopy(self.settings),
            "root": self.root,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "assets": copy.deepcopy(self.assets),
            "extensions": copy.deepcopy(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UiDocument":
        doc = cls.__new__(cls)
        doc.format = data.get("format", "pyide.ui-document")
        doc.version = data.get("version", "2.0")
        doc.meta = copy.deepcopy(data.get("meta", {}))
        doc.settings = copy.deepcopy(data.get("settings", {}))
        doc.root = data["root"]
        doc.nodes = {k: NodeModel.from_dict(v) for k, v in data.get("nodes", {}).items()}
        doc.assets = copy.deepcopy(data.get("assets", {}))
        doc.extensions = copy.deepcopy(data.get("extensions", {}))
        doc._id_counter = 1
        doc._recalc_counter()
        return doc

    def clone(self) -> "UiDocument":
        return UiDocument.from_dict(self.to_dict())

    # -----------------------------------------------------
    # 基础访问
    # -----------------------------------------------------
    def _recalc_counter(self):
        max_num = 0
        for node_id in self.nodes:
            parts = node_id.split("_")
            for p in reversed(parts):
                if p.isdigit():
                    max_num = max(max_num, int(p))
                    break
        self._id_counter = max_num + 1

    def next_id(self, prefix: str = "node") -> str:
        value = f"{prefix}_{self._id_counter}"
        self._id_counter += 1
        return value

    def get_root_node(self) -> NodeModel:
        return self.nodes[self.root]

    def get_node(self, node_id: str) -> NodeModel:
        return self.nodes[node_id]

    def try_get_node(self, node_id: Optional[str]) -> Optional[NodeModel]:
        if not node_id:
            return None
        return self.nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    def get_parent_id(self, node_id: str) -> Optional[str]:
        node = self.try_get_node(node_id)
        return node.parent if node is not None else None

    def get_parent_node(self, node_id: str) -> Optional[NodeModel]:
        node = self.try_get_node(node_id)
        if node is None or node.parent is None:
            return None
        return self.try_get_node(node.parent)

    # -----------------------------------------------------
    # 节点创建
    # -----------------------------------------------------
    def create_widget_node(
        self,
        widget_class: str,
        name: Optional[str] = None,
        role: Optional[str] = None,
        props: Optional[dict] = None,
        parent: Optional[str] = None,
    ) -> NodeModel:
        node_id = self.next_id("node")
        node = NodeModel(
            id=node_id,
            kind="widget",
            name=name or node_id,
            parent=parent,
            widgetClass=widget_class,
            role=role,
            props=copy.deepcopy(props or {}),
        )
        self.nodes[node_id] = node
        return node

    def create_layout_node(
        self,
        layout_class: str,
        name: Optional[str] = None,
        props: Optional[dict] = None,
        parent: Optional[str] = None,
    ) -> NodeModel:
        self._校验布局类(layout_class)
        node_id = self.next_id("node_layout")
        node = NodeModel(
            id=node_id,
            kind="layout",
            name=name or node_id,
            parent=parent,
            layoutClass=layout_class,
            props=copy.deepcopy(props or {}),
        )
        self.nodes[node_id] = node
        return node

    def create_layout_item_node(
        self,
        item_type: str,
        target: str,
        props: Optional[dict] = None,
        parent: Optional[str] = None,
    ) -> NodeModel:
        if item_type not in ("widget", "layout", "spacer"):
            raise ValueError(f"不支持的 layout itemType: {item_type}")

        node_id = self.next_id("node_item")
        node = NodeModel(
            id=node_id,
            kind="layoutItem",
            name=node_id,
            parent=parent,
            itemType=item_type,
            target=target,
            props=copy.deepcopy(props or {}),
        )
        self.nodes[node_id] = node
        return node

    def create_spacer_node(
        self,
        orientation: str = "vertical",
        size_hint: Optional[dict] = None,
        parent: Optional[str] = None,
    ) -> NodeModel:
        if orientation not in ("vertical", "horizontal"):
            raise ValueError("orientation 只能是 vertical 或 horizontal")

        node_id = self.next_id("node_spacer")
        node = NodeModel(
            id=node_id,
            kind="spacer",
            name=node_id,
            parent=parent,
            props={
                "orientation": orientation,
                "sizeHint": size_hint or {"width": 20, "height": 40},
                "sizeTypeH": "Minimum",
                "sizeTypeV": "Expanding",
            },
        )
        self.nodes[node_id] = node
        return node

    # -----------------------------------------------------
    # 默认属性
    # -----------------------------------------------------
    def default_widget_props(self, widget_class: str) -> dict:
        if widget_class == "QPushButton":
            return {"geometry": {"x": 0, "y": 0, "width": 100, "height": 36}, "text": "按钮"}
        if widget_class == "QLabel":
            return {"geometry": {"x": 0, "y": 0, "width": 100, "height": 28}, "text": "标签"}
        if widget_class == "QTextEdit":
            return {
                "geometry": {"x": 0, "y": 0, "width": 180, "height": 90},
                "plainText": "",
                "placeholderText": "多行输入框",
            }
        if widget_class == "QLineEdit":
            return {
                "geometry": {"x": 0, "y": 0, "width": 180, "height": 32},
                "text": "",
                "placeholderText": "单行输入框",
            }
        if widget_class == "QGroupBox":
            return {"geometry": {"x": 0, "y": 0, "width": 220, "height": 140}, "title": "GroupBox"}
        if widget_class == "QTabWidget":
            return {"geometry": {"x": 0, "y": 0, "width": 280, "height": 220}, "currentIndex": 0}
        if widget_class == "QToolBox":
            return {"geometry": {"x": 0, "y": 0, "width": 280, "height": 220}, "currentIndex": 0}
        if widget_class == "__LayoutRegion__":
            return {
                "geometry": {"x": 0, "y": 0, "width": 180, "height": 120},
                "layoutClass": "QVBoxLayout",
            }
        return {"geometry": {"x": 0, "y": 0, "width": 120, "height": 40}}

    def default_layout_props(self, layout_class: str) -> dict:
        self._校验布局类(layout_class)
        return {
            "spacing": 6,
            "marginLeft": 9,
            "marginTop": 9,
            "marginRight": 9,
            "marginBottom": 9,
        }

    # -----------------------------------------------------
    # 校验辅助
    # -----------------------------------------------------
    def _校验布局类(self, layout_class: str):
        if layout_class not in 支持布局类:
            raise ValueError(f"不支持的布局类：{layout_class}")

    def _校验目标是widget(self, node_id: str) -> NodeModel:
        node = self.get_node(node_id)
        if node.kind != "widget":
            raise ValueError("目标节点必须是 widget")
        return node

    def _校验目标是layout(self, node_id: str) -> NodeModel:
        node = self.get_node(node_id)
        if node.kind != "layout":
            raise ValueError("目标节点必须是 layout")
        return node

    # -----------------------------------------------------
    # 关系操作
    # -----------------------------------------------------
    def add_absolute_widget(self, owner_widget_id: str, widget_class: str, geometry: dict, name: Optional[str] = None) -> str:
        owner = self._校验目标是widget(owner_widget_id)
        props = self.default_widget_props(widget_class)
        props["geometry"] = copy.deepcopy(geometry)
        widget = self.create_widget_node(widget_class, name=name, props=props, parent=owner.id)
        owner.children.append(widget.id)

        if widget_class in ("QTabWidget", "QToolBox"):
            self.ensure_default_pages(widget.id)

        return widget.id

    def add_widget_to_layout(self, owner_widget_id: str, widget_class: str, name: Optional[str] = None) -> str:
        owner = self._校验目标是widget(owner_widget_id)
        if owner.layout is None:
            raise ValueError("目标 owner 没有 layout")
        return self.add_widget_item_to_layout(owner.layout, widget_class, name=name)

    def add_widget_item_to_layout(
        self,
        layout_id: str,
        widget_class: str,
        name: Optional[str] = None,
        item_props: Optional[dict] = None,
        widget_props: Optional[dict] = None,
    ) -> str:
        layout_node = self._校验目标是layout(layout_id)

        props = self.default_widget_props(widget_class)
        if widget_props:
            props.update(copy.deepcopy(widget_props))

        widget = self.create_widget_node(widget_class, name=name, props=props, parent=None)
        item = self.create_layout_item_node("widget", widget.id, props=item_props, parent=layout_node.id)
        layout_node.items.append(item.id)
        widget.parent = item.id

        if widget_class in ("QTabWidget", "QToolBox"):
            self.ensure_default_pages(widget.id)

        return widget.id

    def ensure_default_pages(self, container_id: str):
        container = self.get_node(container_id)
        if container.widgetClass not in ("QTabWidget", "QToolBox"):
            return
        if container.children:
            return

        if container.widgetClass == "QTabWidget":
            self.add_page(container_id, title="页1")
            self.add_page(container_id, title="页2")
        else:
            self.add_page(container_id, label="页1")
            self.add_page(container_id, label="页2")

    def add_page(
        self,
        container_id: str,
        title: Optional[str] = None,
        label: Optional[str] = None,
        name: Optional[str] = None,
    ) -> str:
        container = self.get_node(container_id)
        if container.widgetClass not in ("QTabWidget", "QToolBox"):
            raise ValueError("只有 QTabWidget / QToolBox 可以添加页面")

        page_props = {"geometry": {"x": 0, "y": 0, "width": 240, "height": 180}}
        if container.widgetClass == "QTabWidget":
            page_props["title"] = title or "页"
        else:
            page_props["label"] = label or "页"

        page = self.create_widget_node(
            widget_class="QWidget",
            name=name or self.next_id("page"),
            role="page",
            props=page_props,
            parent=container.id,
        )
        container.children.append(page.id)
        return page.id

    def set_widget_layout(
        self,
        owner_widget_id: str,
        layout_class: str,
        name: Optional[str] = None,
        props: Optional[dict] = None,
    ) -> str:
        owner = self._校验目标是widget(owner_widget_id)
        self._校验布局类(layout_class)

        if owner.layout:
            return owner.layout

        merged_props = self.default_layout_props(layout_class)
        if props:
            merged_props.update(copy.deepcopy(props))

        layout = self.create_layout_node(layout_class, name=name, props=merged_props, parent=owner.id)
        owner.layout = layout.id
        return layout.id

    def add_layout_to_layout(
        self,
        layout_owner_id: str,
        child_layout_class: str,
        name: Optional[str] = None,
        props: Optional[dict] = None,
        item_props: Optional[dict] = None,
    ) -> str:
        owner_layout = self._校验目标是layout(layout_owner_id)
        self._校验布局类(child_layout_class)

        merged_props = self.default_layout_props(child_layout_class)
        if props:
            merged_props.update(copy.deepcopy(props))

        child_layout = self.create_layout_node(child_layout_class, name=name, props=merged_props, parent=None)
        item = self.create_layout_item_node("layout", child_layout.id, props=item_props, parent=owner_layout.id)
        owner_layout.items.append(item.id)
        child_layout.parent = item.id
        return child_layout.id

    def add_spacer_to_layout(
        self,
        layout_id: str,
        orientation: str = "vertical",
        size_hint: Optional[dict] = None,
        item_props: Optional[dict] = None,
    ) -> str:
        layout_node = self._校验目标是layout(layout_id)
        spacer = self.create_spacer_node(orientation=orientation, size_hint=size_hint, parent=None)
        item = self.create_layout_item_node("spacer", spacer.id, props=item_props, parent=layout_node.id)
        layout_node.items.append(item.id)
        spacer.parent = item.id
        return spacer.id

    # -----------------------------------------------------
    # 查询
    # -----------------------------------------------------
    def find_owner_widget(self, node_id: str) -> Optional[NodeModel]:
        current = self.try_get_node(node_id)
        while current is not None:
            if current.kind == "widget":
                return current
            current = self.get_parent_node(current.id)
        return None

    def get_layout_owner_widget(self, layout_id: str) -> Optional[NodeModel]:
        layout_node = self.try_get_node(layout_id)
        if layout_node is None or layout_node.kind != "layout":
            return None

        parent = self.get_parent_node(layout_id)
        if parent is not None and parent.kind == "widget":
            return parent

        current = parent
        while current is not None:
            if current.kind == "widget":
                return current
            current = self.get_parent_node(current.id)
        return None

    def is_layout_managed_widget(self, node_id: str) -> bool:
        node = self.try_get_node(node_id)
        if node is None or node.kind != "widget":
            return False
        parent = self.get_parent_node(node.id)
        return parent is not None and parent.kind == "layoutItem"

    def get_page_nodes(self, container_id: str) -> List[NodeModel]:
        container = self.get_node(container_id)
        return [self.get_node(cid) for cid in container.children if self.has_node(cid) and self.get_node(cid).role == "page"]

    def get_direct_widget_children(self, owner_widget_id: str) -> List[NodeModel]:
        owner = self.get_node(owner_widget_id)
        return [self.get_node(cid) for cid in owner.children if self.has_node(cid)]

    def get_layout_items(self, layout_id: str) -> List[NodeModel]:
        layout = self.get_node(layout_id)
        return [self.get_node(iid) for iid in layout.items if self.has_node(iid)]

    def find_node_path(self, node_id: str) -> List[str]:
        result = []
        current = self.try_get_node(node_id)
        while current is not None:
            result.append(current.id)
            current = self.get_parent_node(current.id)
        return list(reversed(result))

    def is_descendant_of(self, node_id: str, ancestor_id: str) -> bool:
        current = self.try_get_node(node_id)
        while current is not None:
            if current.id == ancestor_id:
                return True
            current = self.get_parent_node(current.id)
        return False

    def can_accept_widget_drop(self, owner_id: str) -> bool:
        owner = self.try_get_node(owner_id)
        if owner is None or owner.kind != "widget":
            return False
        if owner.role == "page":
            return True
        return owner.widgetClass in ("QWidget", "QGroupBox", "QTabWidget", "QToolBox", "__LayoutRegion__")

    def can_accept_layout_drop(self, owner_id: str) -> bool:
        return self.can_accept_widget_drop(owner_id)

    def resolve_container_drop_owner(self, owner_id: str) -> str:
        owner = self.get_node(owner_id)
        if owner.widgetClass not in ("QTabWidget", "QToolBox"):
            return owner_id

        pages = self.get_page_nodes(owner_id)
        if not pages:
            self.ensure_default_pages(owner_id)
            pages = self.get_page_nodes(owner_id)

        if not pages:
            return owner_id

        current_index = int(owner.props.get("currentIndex", 0))
        if 0 <= current_index < len(pages):
            return pages[current_index].id
        return pages[0].id

    def get_widget_owner_id(self, node_id: str) -> Optional[str]:
        node = self.try_get_node(node_id)
        if node is None or node.kind != "widget":
            return None

        parent = self.get_parent_node(node.id)
        if parent is None:
            return None

        if parent.kind == "widget":
            return parent.id

        if parent.kind == "layoutItem":
            layout_node = self.get_parent_node(parent.id)
            if layout_node and layout_node.kind == "layout":
                owner_widget = self.get_parent_node(layout_node.id)
                if owner_widget and owner_widget.kind == "widget":
                    return owner_widget.id

        return None

    # -----------------------------------------------------
    # 模型层重挂载
    # -----------------------------------------------------
    def detach_node_from_parent(self, node_id: str):
        node = self.get_node(node_id)
        parent = self.get_parent_node(node_id)
        if parent is None:
            return

        if parent.kind == "widget":
            if node_id in parent.children:
                parent.children.remove(node_id)
            if parent.layout == node_id:
                parent.layout = None
            node.parent = None
            return

        if parent.kind == "layout":
            if node_id in parent.items:
                parent.items.remove(node_id)
            node.parent = None
            return

        if parent.kind == "layoutItem":
            layout_node = self.get_parent_node(parent.id)
            if layout_node and layout_node.kind == "layout" and parent.id in layout_node.items:
                layout_node.items.remove(parent.id)

            if parent.target == node_id:
                parent.target = None

            node.parent = None
            self.nodes.pop(parent.id, None)

    def attach_widget_to_owner(self, widget_id: str, owner_id: str, geometry: Optional[dict] = None) -> str:
        widget = self.get_node(widget_id)
        if widget.kind != "widget":
            raise ValueError("只能挂载 widget 节点")

        owner_id = self.resolve_container_drop_owner(owner_id)
        owner = self.get_node(owner_id)

        if not self.can_accept_widget_drop(owner_id):
            raise ValueError("目标 owner 不能接收 widget")

        if self.is_descendant_of(owner_id, widget_id):
            raise ValueError("不能把节点挂到自己或自己的后代下面")

        self.detach_node_from_parent(widget_id)

        if owner.layout:
            item = self.create_layout_item_node("widget", widget.id, parent=owner.layout)
            self.get_node(owner.layout).items.append(item.id)
            widget.parent = item.id
            return owner_id

        widget.parent = owner.id
        if widget.id not in owner.children:
            owner.children.append(widget.id)

        if geometry is not None:
            self.update_node_props(widget.id, {"geometry": geometry})

        return owner_id

    def move_widget_to_owner(self, widget_id: str, owner_id: str, geometry: Optional[dict] = None) -> str:
        widget = self.get_node(widget_id)
        if widget.kind != "widget":
            raise ValueError("只能移动 widget 节点")
        if widget.id == self.root:
            raise ValueError("不能移动根节点")
        return self.attach_widget_to_owner(widget_id, owner_id, geometry)


    # -----------------------------------------------------
    # 属性修改
    # -----------------------------------------------------
    def update_node_props(self, node_id: str, props: dict):
        node = self.get_node(node_id)
        for k, v in props.items():
            if k == "geometry":
                node.props.setdefault("geometry", {})
                node.props["geometry"].update(v)
            else:
                node.props[k] = v

    def update_layout_class(self, layout_id: str, layout_class: str):
        self._校验布局类(layout_class)
        layout = self.get_node(layout_id)
        if layout.kind != "layout":
            raise ValueError("只能修改 layout 节点的 layoutClass")
        layout.layoutClass = layout_class

    def update_document_props(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        window_title: Optional[str] = None,
    ):
        root = self.get_root_node()
        geometry = root.props.setdefault("geometry", {})
        if width is not None:
            geometry["width"] = width
            self.settings["designWidth"] = width
        if height is not None:
            geometry["height"] = height
            self.settings["designHeight"] = height
        if window_title is not None:
            root.props["windowTitle"] = window_title
            self.meta["title"] = window_title

    # -----------------------------------------------------
    # 删除
    # -----------------------------------------------------
    def remove_node(self, node_id: str):
        if node_id == self.root:
            raise ValueError("不能删除根节点")
        if node_id not in self.nodes:
            return

        node = self.get_node(node_id)
        parent = self.get_parent_node(node_id)

        if parent:
            if parent.kind == "widget":
                if node_id in parent.children:
                    parent.children.remove(node_id)
                if parent.layout == node_id:
                    parent.layout = None
            elif parent.kind == "layout":
                if node_id in parent.items:
                    parent.items.remove(node_id)
            elif parent.kind == "layoutItem" and parent.target == node_id:
                parent.target = None

        if node.kind == "layoutItem" and node.target and self.has_node(node.target):
            self._remove_subtree(node.target)

        self._remove_subtree(node_id)

    def _remove_subtree(self, node_id: str):
        if node_id not in self.nodes:
            return

        node = self.get_node(node_id)

        for cid in list(node.children):
            self._remove_subtree(cid)

        if node.layout:
            self._remove_subtree(node.layout)

        for iid in list(node.items):
            self._remove_subtree(iid)

        if node.kind == "layoutItem" and node.target and self.has_node(node.target):
            self._remove_subtree(node.target)

        self.nodes.pop(node_id, None)

    def pretty_summary(self) -> str:
        return f"format={self.format} version={self.version}\nroot={self.root}\nnodes={len(self.nodes)}"
