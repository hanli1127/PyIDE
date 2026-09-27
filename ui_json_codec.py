from __future__ import annotations

import xml.etree.ElementTree as ET
import json
import keyword
import re
from xml.dom import minidom
from typing import Optional, Tuple

from model import UiDocument


设计期布局区域类名 = "__LayoutRegion__"
设计期布局区域角色 = "layoutRegion"


def 新建空白文档(width: int = 550, height: int = 380, title: str = "Form") -> UiDocument:
    return UiDocument.create_empty(width=width, height=height, title=title)


def 从ui文件读取(path: str) -> UiDocument:
    tree = ET.parse(path)
    root = tree.getroot()

    top_widget = root.find("widget")
    if top_widget is None:
        raise ValueError("无效 ui 文件：缺少顶层 widget")

    doc = UiDocument.create_empty()
    doc.meta["source"] = {"type": "ui", "path": path}
    doc.nodes.clear()

    root_node = _解析widget节点(doc, top_widget, parent_id=None, as_root=True)
    doc.root = root_node.id

    rect = _读取geometry(top_widget)
    if rect:
        _, _, w, h = rect
        doc.settings["designWidth"] = w
        doc.settings["designHeight"] = h

    window_title = _读取string属性(top_widget, "windowTitle")
    if window_title is not None:
        doc.meta["title"] = window_title

    return doc


def 保存为ui文件(path: str, doc: UiDocument):
    ui = ET.Element("ui", {"version": "4.0"})
    class_elem = ET.SubElement(ui, "class")
    class_elem.text = "Form"

    root_node = doc.get_root_node()
    root_elem = _生成widget元素(doc, root_node.id)
    root_elem.set("name", root_node.name or "Form")

    ui.append(root_elem)
    ET.SubElement(ui, "resources")
    ET.SubElement(ui, "connections")

    xml_bytes = ET.tostring(ui, encoding="utf-8")
    pretty = minidom.parseString(xml_bytes).toprettyxml(indent=" ", encoding="utf-8")

    with open(path, "wb") as f:
        f.write(pretty)


def 生成Python代码(doc: UiDocument) -> str:
    root = doc.get_root_node()
    widgets = {
        node.id: node
        for node in doc.nodes.values()
        if node.kind == "widget"
    }
    widget_names = {root.id: "self.form"}
    used_names = {"form"}

    def python_name(value: str, fallback: str) -> str:
        name = re.sub(r"[^0-9A-Za-z_]", "_", value or "")
        name = name.strip("_") or fallback
        if name[0].isdigit():
            name = f"widget_{name}"
        if keyword.iskeyword(name):
            name += "_widget"
        base = name
        index = 2
        while name in used_names:
            name = f"{base}_{index}"
            index += 1
        used_names.add(name)
        return name

    for node in widgets.values():
        if node.id != root.id:
            widget_names[node.id] = f"self.{python_name(node.name, node.id)}"

    def literal(value) -> str:
        return json.dumps(value if value is not None else "", ensure_ascii=False)

    def widget_parent_id(node_id: str) -> str:
        node = doc.get_node(node_id)
        parent = doc.try_get_node(node.parent)
        if parent is not None and parent.kind == "widget":
            return parent.id
        if parent is not None and parent.kind == "layoutItem":
            layout = doc.try_get_node(parent.parent)
            if layout is not None:
                owner = doc.get_layout_owner_widget(layout.id)
                if owner is not None:
                    return owner.id
        return root.id

    widget_order = []
    seen = set()

    def walk_owner(owner_id: str):
        owner = doc.try_get_node(owner_id)
        if owner is None:
            return
        for child_id in owner.children:
            if child_id in widgets and child_id not in seen:
                seen.add(child_id)
                widget_order.append(child_id)
                walk_owner(child_id)
        if owner.layout:
            walk_layout(owner.layout)

    def walk_layout(layout_id: str):
        layout = doc.try_get_node(layout_id)
        if layout is None:
            return
        for item_id in layout.items:
            item = doc.try_get_node(item_id)
            target = doc.try_get_node(item.target) if item is not None else None
            if target is None:
                continue
            if item.itemType == "widget" and target.id not in seen:
                seen.add(target.id)
                widget_order.append(target.id)
                walk_owner(target.id)
            elif item.itemType == "layout":
                walk_layout(target.id)

    walk_owner(root.id)
    for node_id in widgets:
        if node_id != root.id and node_id not in seen:
            seen.add(node_id)
            widget_order.append(node_id)

    lines = [
        "from PySide6.QtCore import QRect, QSize, Qt",
        "from PySide6.QtWidgets import (",
        "    QApplication, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,",
        "    QLabel, QLineEdit, QPushButton, QSizePolicy, QSpacerItem,",
        "    QStackedWidget, QTabWidget, QTextEdit, QToolBox, QVBoxLayout, QWidget,",
        ")",
        "",
        "",
        "class FormWindow(QWidget):",
        "    def __init__(self, parent=None):",
        "        super().__init__(parent)",
        f"        self.setObjectName({literal(root.name or 'Form')})",
    ]

    geometry = root.props.get("geometry", {})
    lines.append(
        "        self.resize("
        f"{int(geometry.get('width', 800))}, {int(geometry.get('height', 600))})"
    )
    lines.extend(
        [
            f"        self.setWindowTitle({literal(root.props.get('windowTitle', 'Form'))})",
            "        self.form = self",
            "        self._build_ui()",
            "",
            "    def _build_ui(self):",
        ]
    )

    for node_id in widget_order:
        node = widgets[node_id]
        class_name = "QWidget" if node.widgetClass == 设计期布局区域类名 else (node.widgetClass or "QWidget")
        parent_id = widget_parent_id(node_id)
        parent_expr = widget_names.get(parent_id, "self.form")
        if node.role == "page":
            lines.append(f"        {widget_names[node_id]} = QWidget({parent_expr})")
        else:
            lines.append(f"        {widget_names[node_id]} = {class_name}({parent_expr})")
        lines.append(f"        {widget_names[node_id]}.setObjectName({literal(node.name or node.id)})")

        if node.role != "page" and not doc.is_layout_managed_widget(node_id):
            geo = node.props.get("geometry")
            if geo:
                lines.append(
                    f"        {widget_names[node_id]}.setGeometry(QRect("
                    f"{int(geo.get('x', 0))}, {int(geo.get('y', 0))}, "
                    f"{int(geo.get('width', 100))}, {int(geo.get('height', 30))}))"
                )

        props = node.props
        if node.widgetClass in ("QPushButton", "QLabel", "QLineEdit"):
            lines.append(f"        {widget_names[node_id]}.setText({literal(props.get('text', ''))})")
        elif node.widgetClass == "QTextEdit":
            lines.append(f"        {widget_names[node_id]}.setPlainText({literal(props.get('plainText', ''))})")
        if node.widgetClass in ("QTextEdit", "QLineEdit") and props.get("placeholderText") is not None:
            lines.append(
                f"        {widget_names[node_id]}.setPlaceholderText("
                f"{literal(props.get('placeholderText', ''))})"
            )
        if node.widgetClass == "QGroupBox":
            lines.append(f"        {widget_names[node_id]}.setTitle({literal(props.get('title', 'GroupBox'))})")

    for node_id in widget_order:
        node = widgets[node_id]
        if node.widgetClass not in ("QTabWidget", "QToolBox", "QStackedWidget"):
            continue
        for page_id in node.children:
            page = widgets.get(page_id)
            if page is None or page.role != "page":
                continue
            page_expr = widget_names[page_id]
            if node.widgetClass == "QTabWidget":
                lines.append(
                    f"        {widget_names[node_id]}.addTab({page_expr}, "
                    f"{literal(page.props.get('title', '页'))})"
                )
            elif node.widgetClass == "QToolBox":
                lines.append(
                    f"        {widget_names[node_id]}.addItem({page_expr}, "
                    f"{literal(page.props.get('label', '页'))})"
                )
            else:
                lines.append(f"        {widget_names[node_id]}.addWidget({page_expr})")
        if node.widgetClass in ("QTabWidget", "QToolBox", "QStackedWidget"):
            lines.append(
                f"        {widget_names[node_id]}.setCurrentIndex("
                f"{int(node.props.get('currentIndex', 0))})"
            )

    layout_names = {}
    emitted_layouts = set()

    def emit_layout(layout_id: str, owner_expr: str | None = None):
        if layout_id in emitted_layouts:
            return
        layout = doc.try_get_node(layout_id)
        if layout is None:
            return
        emitted_layouts.add(layout_id)
        layout_var = f"self.layout_{re.sub(r'[^0-9A-Za-z_]', '_', layout.id)}"
        layout_names[layout_id] = layout_var
        layout_class = layout.layoutClass or "QVBoxLayout"
        ctor = f"{layout_class}({owner_expr})" if owner_expr else f"{layout_class}()"
        lines.append(f"        {layout_var} = {ctor}")
        if "spacing" in layout.props:
            lines.append(f"        {layout_var}.setSpacing({int(layout.props.get('spacing', 6))})")
        margins = [int(layout.props.get(key, 9)) for key in (
            "marginLeft", "marginTop", "marginRight", "marginBottom"
        )]
        lines.append(f"        {layout_var}.setContentsMargins({', '.join(map(str, margins))})")
        for item_id in layout.items:
            item = doc.try_get_node(item_id)
            if item is None or not item.target:
                continue
            if item.itemType == "widget" and item.target in widget_names:
                target_expr = widget_names[item.target]
                if layout_class == "QGridLayout":
                    lines.append(
                        f"        {layout_var}.addWidget({target_expr}, "
                        f"{int(item.props.get('row', 0))}, {int(item.props.get('column', 0))}, "
                        f"{int(item.props.get('rowSpan', 1))}, {int(item.props.get('columnSpan', 1))})"
                    )
                elif layout_class == "QFormLayout":
                    lines.append(f"        {layout_var}.addRow({target_expr})")
                else:
                    lines.append(f"        {layout_var}.addWidget({target_expr})")
            elif item.itemType == "layout":
                emit_layout(item.target)
                child_layout = layout_names.get(item.target)
                if child_layout:
                    if layout_class == "QGridLayout":
                        lines.append(
                            f"        {layout_var}.addLayout({child_layout}, "
                            f"{int(item.props.get('row', 0))}, {int(item.props.get('column', 0))}, "
                            f"{int(item.props.get('rowSpan', 1))}, {int(item.props.get('columnSpan', 1))})"
                        )
                    else:
                        lines.append(f"        {layout_var}.addLayout({child_layout})")
            elif item.itemType == "spacer":
                spacer = doc.try_get_node(item.target)
                if spacer is None:
                    continue
                hint = spacer.props.get("sizeHint", {"width": 20, "height": 40})
                orientation = "Qt.Horizontal" if spacer.props.get("orientation") == "horizontal" else "Qt.Vertical"
                lines.append(
                    f"        {layout_var}.addItem(QSpacerItem("
                    f"{int(hint.get('width', 20))}, {int(hint.get('height', 40))}, "
                    f"QSizePolicy.Minimum, QSizePolicy.Expanding))"
                )

    for node_id in [root.id] + widget_order:
        node = doc.get_node(node_id)
        if not node.layout:
            continue
        emit_layout(node.layout, widget_names.get(node_id, "self.form"))

    lines.extend(
        [
            "",
            "",
            "if __name__ == '__main__':",
            "    app = QApplication([])",
            "    window = FormWindow()",
            "    window.show()",
            "    app.exec()",
            "",
        ]
    )
    return "\n".join(lines)


def 保存为python文件(path: str, doc: UiDocument):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(生成Python代码(doc))


def _解析widget节点(doc: UiDocument, elem: ET.Element, parent_id: Optional[str], as_root: bool = False):
    raw_cls_name = elem.get("class", "QWidget")
    name = elem.get("name", raw_cls_name)

    is_layout_region = _是否QtDesigner布局包装控件(
        doc=doc,
        elem=elem,
        parent_id=parent_id,
        as_root=as_root,
    )

    cls_name = 设计期布局区域类名 if is_layout_region else raw_cls_name

    props = {}

    rect = _读取geometry(elem)
    if rect:
        x, y, w, h = rect
        props["geometry"] = {"x": x, "y": y, "width": w, "height": h}

    if as_root:
        window_title = _读取string属性(elem, "windowTitle")
        if window_title is not None:
            props["windowTitle"] = window_title

    text = _读取string属性(elem, "text")
    if text is not None:
        props["text"] = text

    title = _读取string属性(elem, "title")
    if title is not None:
        props["title"] = title

    plain_text = _读取string属性(elem, "plainText")
    if plain_text is not None:
        props["plainText"] = plain_text

    placeholder = _读取string属性(elem, "placeholderText")
    if placeholder is not None:
        props["placeholderText"] = placeholder

    current_index = _读取number属性(elem, "currentIndex")
    if current_index is not None:
        props["currentIndex"] = current_index

    if as_root:
        node = doc.create_widget_node(
            widget_class=cls_name,
            name=name,
            role="root",
            props=props,
            parent=None,
        )
    else:
        node = doc.create_widget_node(
            widget_class=cls_name,
            name=name,
            role=设计期布局区域角色 if is_layout_region else None,
            props=props,
            parent=parent_id,
        )

    if cls_name in ("QTabWidget", "QToolBox", "QStackedWidget"):
        for child in elem.findall("widget"):
            if child.get("class", "QWidget") != "QWidget":
                continue

            page_name = child.get("name", "page")
            page_props = {}

            page_rect = _读取geometry(child)
            if page_rect:
                x, y, w, h = page_rect
                page_props["geometry"] = {"x": x, "y": y, "width": w, "height": h}

            if cls_name == "QTabWidget":
                page_props["title"] = _读取attribute_string(child, "title") or "Page"
            elif cls_name == "QToolBox":
                page_props["label"] = _读取attribute_string(child, "label") or "Page"

            page_node = doc.create_widget_node(
                widget_class="QWidget",
                name=page_name,
                role="page",
                props=page_props,
                parent=node.id,
            )
            node.children.append(page_node.id)

            for page_child_widget in child.findall("widget"):
                page_sub = _解析widget节点(doc, page_child_widget, page_node.id, as_root=False)
                page_node.children.append(page_sub.id)

            for page_layout in child.findall("layout"):
                layout_id = _解析layout节点(doc, page_layout, page_node.id)
                page_node.layout = layout_id
                break

        return node

    for child_widget in elem.findall("widget"):
        child_node = _解析widget节点(doc, child_widget, node.id, as_root=False)
        node.children.append(child_node.id)

    for child_layout in elem.findall("layout"):
        layout_id = _解析layout节点(doc, child_layout, node.id)
        node.layout = layout_id
        break

    return node


def _解析layout节点(doc: UiDocument, elem: ET.Element, owner_widget_id: str) -> str:
    layout_class = elem.get("class", "QVBoxLayout")
    name = elem.get("name", layout_class)

    props = doc.default_layout_props(layout_class)

    margin_prop = _读取numberlist_margin(elem)
    if margin_prop:
        props.update(margin_prop)

    spacing = _读取number属性(elem, "spacing")
    if spacing is not None:
        props["spacing"] = spacing

    layout = doc.create_layout_node(
        layout_class=layout_class,
        name=name,
        props=props,
        parent=owner_widget_id,
    )

    for item_elem in elem.findall("item"):
        _解析layout_item(doc, item_elem, layout.id)

    return layout.id


def _解析layout_item(doc: UiDocument, item_elem: ET.Element, layout_id: str):
    widget_elem = item_elem.find("widget")
    if widget_elem is not None:
        widget_node = _解析widget节点(doc, widget_elem, parent_id=None, as_root=False)

        item = doc.create_layout_item_node(
            item_type="widget",
            target=widget_node.id,
            parent=layout_id,
            props=_解析layout_item属性(item_elem),
        )

        widget_node.parent = item.id
        doc.get_node(layout_id).items.append(item.id)
        return

    layout_elem = item_elem.find("layout")
    if layout_elem is not None:
        child_layout = _解析子布局节点(doc, layout_elem)

        item = doc.create_layout_item_node(
            item_type="layout",
            target=child_layout.id,
            parent=layout_id,
            props=_解析layout_item属性(item_elem),
        )

        child_layout.parent = item.id
        doc.get_node(layout_id).items.append(item.id)
        return

    spacer_elem = item_elem.find("spacer")
    if spacer_elem is not None:
        orientation = "vertical"
        size_hint = {"width": 20, "height": 40}

        for prop in spacer_elem.findall("property"):
            pname = prop.get("name")
            if pname == "orientation":
                enum_elem = prop.find("enum")
                if enum_elem is not None and enum_elem.text:
                    orientation = "horizontal" if "Horizontal" in enum_elem.text else "vertical"
            elif pname == "sizeHint":
                size_elem = prop.find("size")
                if size_elem is not None:
                    size_hint = {
                        "width": _读int节点(size_elem, "width", 20),
                        "height": _读int节点(size_elem, "height", 40),
                    }

        spacer = doc.create_spacer_node(orientation=orientation, size_hint=size_hint, parent=None)

        item = doc.create_layout_item_node(
            item_type="spacer",
            target=spacer.id,
            parent=layout_id,
            props=_解析layout_item属性(item_elem),
        )

        spacer.parent = item.id
        doc.get_node(layout_id).items.append(item.id)
        return


def _解析子布局节点(doc: UiDocument, elem: ET.Element):
    layout_class = elem.get("class", "QVBoxLayout")
    name = elem.get("name", layout_class)

    props = doc.default_layout_props(layout_class)

    margin_prop = _读取numberlist_margin(elem)
    if margin_prop:
        props.update(margin_prop)

    spacing = _读取number属性(elem, "spacing")
    if spacing is not None:
        props["spacing"] = spacing

    child_layout = doc.create_layout_node(
        layout_class=layout_class,
        name=name,
        props=props,
        parent=None,
    )

    for sub_item in elem.findall("item"):
        _解析layout_item(doc, sub_item, child_layout.id)

    return child_layout


def _解析layout_item属性(item_elem: ET.Element) -> dict:
    props = {}

    row = item_elem.get("row")
    column = item_elem.get("column")
    rowspan = item_elem.get("rowspan")
    colspan = item_elem.get("colspan")

    if row is not None:
        props["row"] = int(row)
    if column is not None:
        props["column"] = int(column)
    if rowspan is not None:
        props["rowSpan"] = int(rowspan)
    if colspan is not None:
        props["columnSpan"] = int(colspan)

    return props


def _生成widget元素(doc: UiDocument, node_id: str) -> ET.Element:
    node = doc.get_node(node_id)

    if _是否设计期布局区域(node):
        return _生成布局区域元素(doc, node_id)

    attrs = {
        "class": node.widgetClass or "QWidget",
        "name": node.name or node.id,
    }

    if _应该导出为nativeQWidget(node):
        attrs["native"] = "true"

    elem = ET.Element("widget", attrs)

    geometry = node.props.get("geometry")
    if geometry:
        _写geometry(
            elem,
            int(geometry.get("x", 0)),
            int(geometry.get("y", 0)),
            int(geometry.get("width", 100)),
            int(geometry.get("height", 30)),
        )

    if "windowTitle" in node.props:
        _写string属性(elem, "windowTitle", node.props["windowTitle"])

    if node.widgetClass in ("QPushButton", "QLabel", "QLineEdit"):
        if "text" in node.props:
            _写string属性(elem, "text", node.props["text"])

    if node.widgetClass == "QGroupBox":
        _写string属性(elem, "title", node.props.get("title", "GroupBox"))

    if node.widgetClass == "QTextEdit":
        if "plainText" in node.props:
            _写string属性(elem, "plainText", node.props["plainText"])
        if "placeholderText" in node.props:
            _写string属性(elem, "placeholderText", node.props["placeholderText"])

    if node.widgetClass == "QLineEdit":
        if "placeholderText" in node.props:
            _写string属性(elem, "placeholderText", node.props["placeholderText"])

    if node.widgetClass in ("QTabWidget", "QToolBox", "QStackedWidget"):
        _写number属性(elem, "currentIndex", int(node.props.get("currentIndex", 0)))

        for page_id in getattr(node, "children", []):
            if not _安全has_node(doc, page_id):
                continue

            page_node = doc.get_node(page_id)
            page_elem = ET.SubElement(elem, "widget", {
                "class": "QWidget",
                "name": page_node.name or page_node.id,
            })

            page_geo = page_node.props.get("geometry")
            if page_geo:
                _写geometry(
                    page_elem,
                    int(page_geo.get("x", 0)),
                    int(page_geo.get("y", 0)),
                    int(page_geo.get("width", 240)),
                    int(page_geo.get("height", 180)),
                )

            if node.widgetClass == "QTabWidget":
                _写attribute_string(page_elem, "title", page_node.props.get("title", "Page"))
            elif node.widgetClass == "QToolBox":
                _写attribute_string(page_elem, "label", page_node.props.get("label", "Page"))

            layout_targets = _布局管理目标集合(doc, getattr(page_node, "layout", None))

            for child_id in getattr(page_node, "children", []):
                if child_id in layout_targets or not _安全has_node(doc, child_id):
                    continue
                child_elem = _生成widget元素(doc, child_id)
                page_elem.append(child_elem)

            if getattr(page_node, "layout", None):
                layout_elem = _生成layout元素(doc, page_node.layout)
                page_elem.append(layout_elem)

        return elem

    layout_targets = _布局管理目标集合(doc, getattr(node, "layout", None))

    for child_id in getattr(node, "children", []):
        if child_id in layout_targets or not _安全has_node(doc, child_id):
            continue

        child_elem = _生成widget元素(doc, child_id)
        elem.append(child_elem)

    if getattr(node, "layout", None):
        layout_elem = _生成layout元素(doc, node.layout)
        elem.append(layout_elem)

    return elem


def _生成布局区域元素(doc: UiDocument, node_id: str) -> ET.Element:
    node = doc.get_node(node_id)

    # Qt Designer 的 QLayoutWidget 保存到 .ui 时就是 QWidget + layout。
    # 关键点：这里不要写 native="true"。
    elem = ET.Element("widget", {
        "class": "QWidget",
        "name": node.name or node.id or "layoutWidget",
    })

    geometry = node.props.get("geometry")
    if geometry:
        _写geometry(
            elem,
            int(geometry.get("x", 0)),
            int(geometry.get("y", 0)),
            int(geometry.get("width", 180)),
            int(geometry.get("height", 120)),
        )

    layout_targets = _布局管理目标集合(doc, getattr(node, "layout", None))

    for child_id in getattr(node, "children", []):
        if child_id in layout_targets or not _安全has_node(doc, child_id):
            continue

        child_elem = _生成widget元素(doc, child_id)
        elem.append(child_elem)

    if getattr(node, "layout", None) and _安全has_node(doc, node.layout):
        layout_elem = _生成layout元素(doc, node.layout)
        elem.append(layout_elem)

    return elem


def _生成layout元素(doc: UiDocument, layout_id: str) -> ET.Element:
    layout = doc.get_node(layout_id)

    elem = ET.Element("layout", {
        "class": layout.layoutClass or "QVBoxLayout",
        "name": layout.name or layout.id,
    })

    if "spacing" in layout.props:
        _写number属性(elem, "spacing", int(layout.props["spacing"]))

    margins = ["marginLeft", "marginTop", "marginRight", "marginBottom"]
    if any(k in layout.props for k in margins):
        if "marginLeft" in layout.props:
            _写number属性(elem, "leftMargin", int(layout.props["marginLeft"]))
        if "marginTop" in layout.props:
            _写number属性(elem, "topMargin", int(layout.props["marginTop"]))
        if "marginRight" in layout.props:
            _写number属性(elem, "rightMargin", int(layout.props["marginRight"]))
        if "marginBottom" in layout.props:
            _写number属性(elem, "bottomMargin", int(layout.props["marginBottom"]))

    for item_id in getattr(layout, "items", []):
        if not _安全has_node(doc, item_id):
            continue

        item_node = doc.get_node(item_id)
        item_elem = ET.SubElement(elem, "item")

        if "row" in item_node.props:
            item_elem.set("row", str(item_node.props["row"]))
        if "column" in item_node.props:
            item_elem.set("column", str(item_node.props["column"]))
        if "rowSpan" in item_node.props:
            item_elem.set("rowspan", str(item_node.props["rowSpan"]))
        if "columnSpan" in item_node.props:
            item_elem.set("colspan", str(item_node.props["columnSpan"]))

        if item_node.itemType == "widget" and item_node.target:
            if not _安全has_node(doc, item_node.target):
                continue

            child_widget = _生成widget元素(doc, item_node.target)
            item_elem.append(child_widget)

        elif item_node.itemType == "layout" and item_node.target:
            if not _安全has_node(doc, item_node.target):
                continue

            child_layout = _生成layout元素(doc, item_node.target)
            item_elem.append(child_layout)

        elif item_node.itemType == "spacer" and item_node.target:
            if not _安全has_node(doc, item_node.target):
                continue

            spacer_node = doc.get_node(item_node.target)
            spacer_elem = ET.SubElement(item_elem, "spacer", {
                "name": spacer_node.name or spacer_node.id,
            })

            prop_orientation = ET.SubElement(spacer_elem, "property", {"name": "orientation"})
            enum_elem = ET.SubElement(prop_orientation, "enum")
            enum_elem.text = (
                "Qt::Horizontal"
                if spacer_node.props.get("orientation") == "horizontal"
                else "Qt::Vertical"
            )

            size_hint = spacer_node.props.get("sizeHint", {"width": 20, "height": 40})
            prop_size = ET.SubElement(spacer_elem, "property", {"name": "sizeHint"})
            size_elem = ET.SubElement(prop_size, "size")

            w_elem = ET.SubElement(size_elem, "width")
            w_elem.text = str(size_hint.get("width", 20))

            h_elem = ET.SubElement(size_elem, "height")
            h_elem.text = str(size_hint.get("height", 40))

    return elem


def _是否设计期布局区域(node) -> bool:
    return (
        getattr(node, "widgetClass", None) == 设计期布局区域类名
        or getattr(node, "role", None) == 设计期布局区域角色
    )


def _是否QtDesigner布局包装控件(
    doc: UiDocument,
    elem: ET.Element,
    parent_id: Optional[str],
    as_root: bool,
) -> bool:
    if as_root:
        return False

    raw_cls_name = elem.get("class", "QWidget")

    # 兼容极少数内部/中间格式直接写 QLayoutWidget 的情况。
    if raw_cls_name == "QLayoutWidget":
        return bool(elem.findall("layout"))

    if raw_cls_name != "QWidget":
        return False

    # Qt Designer 的普通 QWidget 容器会写 native="true"。
    # QLayoutWidget 保存成 QWidget 时不会写 native。
    if elem.get("native") is not None:
        return False

    # 没有直接 layout，就不是独立布局包装控件。
    if not elem.findall("layout"):
        return False

    # QTabWidget / QToolBox / QStackedWidget 等容器扩展的页面，
    # 即使是 QWidget + layout + 无 native，也不是红色布局区域。
    if parent_id and _安全has_node(doc, parent_id):
        parent_node = doc.get_node(parent_id)
        if _是否QtDesigner容器扩展控件(parent_node):
            return False

    return True


def _是否QtDesigner容器扩展控件(node) -> bool:
    return getattr(node, "widgetClass", None) in {
        "QTabWidget",
        "QToolBox",
        "QStackedWidget",
        "QWizard",
    }


def _应该导出为nativeQWidget(node) -> bool:
    if _是否设计期布局区域(node):
        return False

    if getattr(node, "widgetClass", None) != "QWidget":
        return False

    # 根窗体和容器页面不是普通 native QWidget。
    if getattr(node, "role", None) in {"root", "page"}:
        return False

    return True


def _布局管理目标集合(doc: UiDocument, layout_id: Optional[str]) -> set[str]:
    targets = set()

    if not layout_id or not _安全has_node(doc, layout_id):
        return targets

    layout_node = doc.get_node(layout_id)

    for item_id in getattr(layout_node, "items", []):
        if not _安全has_node(doc, item_id):
            continue

        item_node = doc.get_node(item_id)
        target = getattr(item_node, "target", None)

        if target:
            targets.add(target)

    return targets


def _安全has_node(doc: UiDocument, node_id: Optional[str]) -> bool:
    if not node_id:
        return False

    try:
        return doc.has_node(node_id)
    except Exception:
        try:
            return node_id in doc.nodes
        except Exception:
            return False


def _读取geometry(elem: ET.Element) -> Optional[Tuple[int, int, int, int]]:
    for prop in elem.findall("property"):
        if prop.get("name") != "geometry":
            continue

        rect = prop.find("rect")
        if rect is None:
            continue

        return (
            _读int节点(rect, "x", 0),
            _读int节点(rect, "y", 0),
            _读int节点(rect, "width", 100),
            _读int节点(rect, "height", 30),
        )

    return None


def _读取string属性(elem: ET.Element, 属性名: str) -> Optional[str]:
    for prop in elem.findall("property"):
        if prop.get("name") == 属性名:
            s = prop.find("string")
            if s is not None:
                return s.text or ""

    return None


def _读取number属性(elem: ET.Element, 属性名: str) -> Optional[int]:
    for prop in elem.findall("property"):
        if prop.get("name") == 属性名:
            n = prop.find("number")
            if n is not None and n.text is not None:
                try:
                    return int(n.text)
                except ValueError:
                    return 0

    return None


def _读取attribute_string(elem: ET.Element, 属性名: str) -> Optional[str]:
    for attr in elem.findall("attribute"):
        if attr.get("name") == 属性名:
            s = attr.find("string")
            if s is not None:
                return s.text or ""

    return None


def _读取numberlist_margin(elem: ET.Element) -> dict:
    result = {}

    mapping = {
        "leftMargin": "marginLeft",
        "topMargin": "marginTop",
        "rightMargin": "marginRight",
        "bottomMargin": "marginBottom",
    }

    for prop in elem.findall("property"):
        pname = prop.get("name")
        if pname in mapping:
            n = prop.find("number")
            if n is not None and n.text is not None:
                try:
                    result[mapping[pname]] = int(n.text)
                except ValueError:
                    pass

    return result


def _读int节点(parent: ET.Element, tag: str, default: int) -> int:
    n = parent.find(tag)
    if n is None or n.text is None:
        return default

    try:
        return int(n.text)
    except ValueError:
        return default


def _写geometry(parent: ET.Element, x: int, y: int, w: int, h: int):
    prop = ET.SubElement(parent, "property", {"name": "geometry"})
    rect = ET.SubElement(prop, "rect")

    for tag, value in (("x", x), ("y", y), ("width", w), ("height", h)):
        e = ET.SubElement(rect, tag)
        e.text = str(value)


def _写string属性(parent: ET.Element, name: str, value: str):
    prop = ET.SubElement(parent, "property", {"name": name})
    s = ET.SubElement(prop, "string")
    s.text = value


def _写number属性(parent: ET.Element, name: str, value: int):
    prop = ET.SubElement(parent, "property", {"name": name})
    n = ET.SubElement(prop, "number")
    n.text = str(value)


def _写attribute_string(parent: ET.Element, name: str, value: str):
    attr = ET.SubElement(parent, "attribute", {"name": name})
    s = ET.SubElement(attr, "string")
    s.text = value
