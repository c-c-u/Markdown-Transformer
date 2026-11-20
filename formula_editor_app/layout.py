# -*- coding: utf-8 -*-
"""画布布局引擎：文本、方框、求和/积分/分式/根式/矩阵等结构的尺寸与位置。"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import font as tkfont
from typing import Optional, Union

from .config import (
    ACCENT,
    AUTO_FIT_SIZES,
    ITEM_GAP,
    PLACEHOLDER_FILL,
    PLACEHOLDER_OUTLINE,
    SELECTION_FILL,
    SOFT_ACCENT,
    SYMBOL_FONT_CHARS,
    TEXT,
)
from .model import (
    AccentNode,
    Element,
    FractionNode,
    IntegralNode,
    MatrixNode,
    Placeholder,
    RootNode,
    SelectionRow,
    Slot,
    SubSuperscriptNode,
    SubscriptNode,
    SumNode,
    SuperscriptNode,
    TextRun,
    child_slots,
)

@dataclass
class DrawText:
    x: float
    y: float
    text: str
    font: tkfont.Font
    fill: str
    anchor: str = "sw"


@dataclass
class DrawRect:
    x1: float
    y1: float
    x2: float
    y2: float
    fill: str
    outline: str
    width: float
    dash: tuple[int, ...]


@dataclass
class DrawLine:
    x1: float
    y1: float
    x2: float
    y2: float
    fill: str
    width: float


DrawOp = Union[DrawText, DrawRect, DrawLine]


@dataclass
class HitArea:
    slot: Slot
    index: int
    x1: float
    y1: float
    x2: float
    y2: float
    char_positions: Optional[list[float]]
    kind: str


@dataclass
class NodeBox:
    """大型运算符/分式在画布上的整体包围盒及其所在父行。"""

    node: Element
    parent_slot: Slot
    index: int
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Layout:
    width: float
    ascent: float
    descent: float
    draws: list[DrawOp]
    hits: list[HitArea]
    nodes: list[NodeBox] = field(default_factory=list)
    selection: Optional[list[SelectionRow]] = None


def empty_layout() -> Layout:
    """空的布局结果：没有尺寸、绘制项或命中项。"""
    return Layout(0.0, 0.0, 0.0, [], [])


def _merge(*layouts: Layout) -> tuple[list[DrawOp], list[HitArea], list[NodeBox]]:
    """按顺序把若干子布局的绘制项、命中区域和结构包围盒拼成三张表。"""
    draws: list[DrawOp] = []
    hits: list[HitArea] = []
    nodes: list[NodeBox] = []
    for layout in layouts:
        draws.extend(layout.draws)
        hits.extend(layout.hits)
        nodes.extend(layout.nodes)
    return draws, hits, nodes


# 结构类型 -> 布局方法名。新增结构时在这里补一条，再写对应的 _layout_* 方法。
_STRUCTURE_LAYOUT = {
    SumNode: "_layout_sum",
    IntegralNode: "_layout_integral",
    FractionNode: "_layout_fraction",
    SuperscriptNode: "_layout_power",
    SubscriptNode: "_layout_subscript",
    SubSuperscriptNode: "_layout_subsup",
    AccentNode: "_layout_accent",
    RootNode: "_layout_root",
    MatrixNode: "_layout_matrix",
}


def shift_layout(layout: Layout, dx: float, dy: float) -> Layout:
    draws: list[DrawOp] = []
    for draw in layout.draws:
        if isinstance(draw, DrawText):
            draws.append(
                DrawText(
                    draw.x + dx,
                    draw.y + dy,
                    draw.text,
                    draw.font,
                    draw.fill,
                    draw.anchor,
                )
            )
        elif isinstance(draw, DrawRect):
            draws.append(
                DrawRect(
                    draw.x1 + dx,
                    draw.y1 + dy,
                    draw.x2 + dx,
                    draw.y2 + dy,
                    draw.fill,
                    draw.outline,
                    draw.width,
                    draw.dash,
                )
            )
        else:
            draws.append(
                DrawLine(
                    draw.x1 + dx,
                    draw.y1 + dy,
                    draw.x2 + dx,
                    draw.y2 + dy,
                    draw.fill,
                    draw.width,
                )
            )

    hits: list[HitArea] = []
    for hit in layout.hits:
        positions = [p + dx for p in hit.char_positions] if hit.char_positions else None
        hits.append(
            HitArea(
                hit.slot,
                hit.index,
                hit.x1 + dx,
                hit.y1 + dy,
                hit.x2 + dx,
                hit.y2 + dy,
                positions,
                hit.kind,
            )
        )
    nodes = [
        NodeBox(
            node.node,
            node.parent_slot,
            node.index,
            node.x1 + dx,
            node.y1 + dy,
            node.x2 + dx,
            node.y2 + dy,
        )
        for node in layout.nodes
    ]
    selection = None
    if layout.selection:
        selection = [
            SelectionRow(
                row.index,
                row.offset,
                row.x1 + dx,
                row.y1 + dy,
                row.x2 + dx,
                row.y2 + dy,
            )
            for row in layout.selection
        ]
    return Layout(layout.width, layout.ascent, layout.descent, draws, hits, nodes, selection)


class LayoutEngine:
    """提供布局计算与 Canvas 绘制方法；由主应用继承。"""

    # 顶标在画布上绘制的字形；空字符串表示画一条与内容等宽的横线。
    ACCENT_GLYPHS = {
        "hat": "ˆ",
        "widehat": "ˆ",
        "bar": "",
        "overline": "",
        "tilde": "˜",
        "widetilde": "˜",
        "dot": "˙",
        "ddot": "¨",
        "vec": "→",
    }

    # 文本最左/最右侧的可点击扩展区：点击后在该文本旁添加新的输入位置。
    TEXT_EDGE_INSIDE = 4.0
    TEXT_EDGE_OUTSIDE = 8.0
    # 结构（算符）左右两侧的可点击扩展区：点击后光标进入该结构前后的隐藏位置。
    STRUCTURE_SIDE_MARGIN = 12.0
    # 正在被选中的方框（(id(slot), index) 集合），用于让方框改用选中底色。
    _selection_paint_keys: set[tuple[int, int]] = set()
    # 被整体选中的结构，其内部这些槽位的方框同样改用选中底色。
    _selection_slots: set[int] = set()

    def _font(self, size: float, italic: bool = False, family: Optional[str] = None) -> tkfont.Font:
        size = max(8, int(round(size)))
        family = family or self.math_font
        key = (family, size, italic)
        font = self._font_cache.get(key)
        if font is None:
            font = tkfont.Font(
                family=family,
                size=size,
                slant="italic" if italic else "roman",
            )
            self._font_cache[key] = font
        return font


    def _char_font(self, char: str, size: float, upright: bool) -> tkfont.Font:
        if char in SYMBOL_FONT_CHARS:
            return self._font(size, italic=False, family=self.symbol_font)
        italic = (not upright) and char.isalpha()
        return self._font(size, italic=italic)


    def _measure(self, font: tkfont.Font, text: str = "x") -> tuple[float, float, float]:
        return float(font.measure(text)), float(font.metrics("ascent")), float(font.metrics("descent"))


    def _child(self, slot: Slot, x: float, baseline: float, size: float) -> Layout:
        """在局部坐标里排好一个子槽位，再整体平移到 (x, baseline) 处。

        返回的 width/ascent/descent 与局部布局一致，可以直接参与外层尺寸计算。
        """
        return shift_layout(self._layout_slot(slot, 0.0, 0.0, size), x, baseline)


    def _fit_layout(
        self,
        slot: Slot,
        avail_w: float,
        avail_h: float,
        sizes: tuple[int, ...] = AUTO_FIT_SIZES,
    ) -> tuple[Layout, int]:
        """从大到小试排，返回第一个宽高都放得下的布局及其字号。

        全部放不下时退回 ``sizes`` 里的最小字号，保证调用方总有布局可用。
        """
        for size in sizes:
            layout = self._layout_slot(slot, 0.0, 0.0, float(size))
            if layout.width <= avail_w and layout.ascent + layout.descent <= avail_h:
                return layout, size
        smallest = sizes[-1]
        return self._layout_slot(slot, 0.0, 0.0, float(smallest)), smallest


    def _layout_item(
        self,
        item: Element,
        parent_slot: Slot,
        index: int,
        x: float,
        baseline: float,
        size: float,
    ) -> Layout:
        if isinstance(item, TextRun):
            return self._layout_text(item, parent_slot, index, x, baseline, size)
        if isinstance(item, Placeholder):
            return self._layout_placeholder(parent_slot, index, x, baseline, size)

        # 结构被选中时，它内部的方框也改用选中底色，避免黄色方框盖住选中效果。
        # 要在布局子槽位之前登记，才能让结构内部的方框也生效。
        paint_keys = getattr(self, "_selection_paint_keys", ())
        if (id(parent_slot), index) in paint_keys:
            selected_slots = getattr(self, "_selection_slots", None)
            if selected_slots is not None:
                for slot in child_slots(item):
                    selected_slots.add(id(slot))

        method_name = _STRUCTURE_LAYOUT.get(type(item))
        if method_name is None:
            return empty_layout()
        child = getattr(self, method_name)(item, x, baseline, size)

        # 记录这个结构的整体包围盒（布局信息）。
        child.nodes.append(
            NodeBox(
                item,
                parent_slot,
                index,
                x,
                baseline - child.ascent,
                x + child.width,
                baseline + child.descent,
            )
        )
        return child


    def _layout_slot(self, slot: Slot, x: float, baseline: float, size: float) -> Layout:
        draws: list[DrawOp] = []
        hits: list[HitArea] = []
        nodes: list[NodeBox] = []
        cursor = x
        ascent = 0.0
        descent = 0.0
        count = len(slot.items)

        for index, item in enumerate(slot.items):
            child = self._layout_item(item, slot, index, cursor, baseline, size)
            draws.extend(child.draws)
            hits.extend(child.hits)
            nodes.extend(child.nodes)
            ascent = max(ascent, child.ascent)
            descent = max(descent, child.descent)
            cursor += child.width
            if index < count - 1:
                cursor += ITEM_GAP

        return Layout(cursor - x, ascent, descent, draws, hits, nodes)


    def _layout_text(
        self,
        item: TextRun,
        slot: Slot,
        index: int,
        x: float,
        baseline: float,
        size: float,
    ) -> Layout:
        text = item.text
        if not text:
            return empty_layout()

        groups: list[tuple[str, tkfont.Font]] = []
        for char in text:
            font = self._char_font(char, size, item.upright)
            if groups and groups[-1][1] == font:
                groups[-1] = (groups[-1][0] + char, font)
            else:
                groups.append((char, font))

        draws: list[DrawOp] = []
        caret_positions = [x]
        cursor = x
        ascent = 0.0
        descent = 0.0

        for group_text, font in groups:
            width, font_ascent, font_descent = self._measure(font, group_text)
            ascent = max(ascent, font_ascent)
            descent = max(descent, font_descent)
            draws.append(DrawText(cursor, baseline + font_descent, group_text, font, TEXT))
            for k in range(1, len(group_text) + 1):
                caret_positions.append(cursor + font.measure(group_text[:k]))
            cursor += width

        active = (
            item.editable
            and slot is self.active_slot
            and index == self.active_index
        )
        y1 = baseline - ascent - 3
        y2 = baseline + descent + 3

        if active:
            # 已经处于选中状态时不再画浅色底，否则会盖住选中高亮；只保留光标线。
            paint_keys = getattr(self, "_selection_paint_keys", ())
            selected_slots = getattr(self, "_selection_slots", ())
            selected = (id(slot), index) in paint_keys or id(slot) in selected_slots
            if not selected:
                background = DrawRect(x - 3, y1, cursor + 3, y2, SOFT_ACCENT, "", 0, ())
                draws.insert(0, background)
            caret = max(0, min(self.caret, len(text)))
            cx = caret_positions[caret]
            draws.append(DrawLine(cx, y1 + 2, cx, y2 - 2, ACCENT, 1.6))

        hits: list[HitArea] = []
        if item.editable:
            # 两端各补一个边缘位置，使字符偏移与点击位置一一对应。
            caret_edges = [x] + caret_positions[1:] + [cursor]
            hits.append(
                HitArea(slot, index, x - 2, y1, cursor + 2, y2, caret_edges, "text")
            )
            # 文本左右两端额外提供“添加新项”的可点击区域。
            inside = self.TEXT_EDGE_INSIDE
            outside = self.TEXT_EDGE_OUTSIDE
            hits.append(
                HitArea(
                    slot,
                    index,
                    x - outside,
                    y1,
                    x + inside,
                    y2,
                    None,
                    "text-edge-left",
                )
            )
            hits.append(
                HitArea(
                    slot,
                    index,
                    cursor - inside,
                    y1,
                    cursor + outside,
                    y2,
                    None,
                    "text-edge-right",
                )
            )

        return Layout(cursor - x, ascent, descent, draws, hits)


    def _layout_placeholder(
        self,
        slot: Slot,
        index: int,
        x: float,
        baseline: float,
        size: float,
    ) -> Layout:
        font = self._font(size, italic=False)
        _, ascent, descent = self._measure(font, "0")
        active = slot is self.active_slot and index == self.active_index
        item = slot.items[index] if 0 <= index < len(slot.items) else Placeholder()

        if item.free:
            # 非结构型空位不画方框；只在获得焦点时显示光标。
            top = baseline - ascent - 4
            bottom = baseline + descent + 4
            draws: list[DrawOp] = []
            if active:
                draws.append(DrawLine(x, top + 3, x, bottom - 3, ACCENT, 1.6))
            return Layout(0.0, ascent + 4, descent + 4, draws, [])

        box_width = max(26.0, float(font.measure("0")) * 2.3)
        top = baseline - ascent - 4
        bottom = baseline + descent + 4
        paint_keys = getattr(self, "_selection_paint_keys", ())
        selected_slots = getattr(self, "_selection_slots", ())
        selected = (id(slot), index) in paint_keys or id(slot) in selected_slots

        if active and selected:
            # 光标在方框里、同时方框又被选中：保留选中底色，只叠加高亮边框和光标。
            fill = SELECTION_FILL
            outline = ACCENT
            border_width = 2.0
            dash: tuple[int, ...] = ()
        elif active:
            fill = SOFT_ACCENT
            outline = ACCENT
            border_width = 2.0
            dash = ()
        elif selected:
            # 选中时方框用与选中高亮相同的底色，避免方框颜色盖住选中效果。
            fill = SELECTION_FILL
            outline = ACCENT
            border_width = 1.4
            dash = ()
        else:
            fill = PLACEHOLDER_FILL
            outline = PLACEHOLDER_OUTLINE
            border_width = 1.4
            dash = (4, 2)

        draws: list[DrawOp] = [
            DrawRect(x, top, x + box_width, bottom, fill, outline, border_width, dash)
        ]
        if active:
            if selected:
                # 只画一条内边框表示“正在编辑”，不再覆盖整块底色。
                draws.append(
                    DrawRect(x + 2.5, top + 2.5, x + box_width - 2.5, bottom - 2.5, "", ACCENT, 1.2, ())
                )
            else:
                draws.append(DrawLine(x + 8, top + 6, x + 8, bottom - 6, ACCENT, 1.6))

        hits = [HitArea(slot, index, x, top, x + box_width, bottom, None, "placeholder")]
        return Layout(box_width, ascent + 4, descent + 4, draws, hits)


    def _layout_sum(self, node: SumNode, x: float, baseline: float, size: float) -> Layout:
        limit_size = max(12.0, size * 0.68)
        upper = self._layout_slot(node.upper, 0.0, 0.0, limit_size)
        lower = self._layout_slot(node.lower, 0.0, 0.0, limit_size)
        body = self._layout_slot(node.body, 0.0, 0.0, size)

        glyph_font = self._font(size * 1.75, family=self.symbol_font)
        glyph_width, glyph_ascent, glyph_descent = self._measure(glyph_font, "∑")

        column_width = max(glyph_width, upper.width, lower.width)
        glyph_x = x + (column_width - glyph_width) / 2
        upper_baseline = -glyph_ascent - 4 - upper.descent
        lower_baseline = glyph_descent + 4 + lower.ascent
        body_x = x + column_width + 10

        upper_shifted = shift_layout(
            upper, x + (column_width - upper.width) / 2, baseline + upper_baseline
        )
        lower_shifted = shift_layout(
            lower, x + (column_width - lower.width) / 2, baseline + lower_baseline
        )
        body_shifted = shift_layout(body, body_x, baseline)

        draws, hits, nodes = _merge(upper_shifted, lower_shifted, body_shifted)
        draws.insert(
            0, DrawText(glyph_x, baseline + glyph_descent, "∑", glyph_font, TEXT)
        )
        ascent = max(glyph_ascent, -upper_baseline + upper.ascent, body.ascent)
        descent = max(glyph_descent, lower_baseline + lower.descent, body.descent)
        width = column_width + 10 + body.width
        return Layout(width, ascent, descent, draws, hits, nodes)


    def _layout_integral(self, node: IntegralNode, x: float, baseline: float, size: float) -> Layout:
        limit_size = max(11.0, size * 0.62)
        upper = self._layout_slot(node.upper, 0.0, 0.0, limit_size)
        lower = self._layout_slot(node.lower, 0.0, 0.0, limit_size)
        body = self._layout_slot(node.body, 0.0, 0.0, size)

        glyph_font = self._font(size * 2.15, family=self.symbol_font)
        glyph_width, glyph_ascent, glyph_descent = self._measure(glyph_font, "∫")

        limit_x = x + glyph_width + 2
        upper_baseline = -glyph_ascent + 2 + upper.ascent
        lower_baseline = glyph_descent - 2 - lower.descent
        upper_shifted = shift_layout(upper, limit_x, baseline + upper_baseline)
        lower_shifted = shift_layout(lower, limit_x, baseline + lower_baseline)

        body_x = x + glyph_width + max(upper.width, lower.width) + 9
        body_shifted = shift_layout(body, body_x, baseline)

        d_font = self._font(size, italic=False)
        d_width, d_ascent, d_descent = self._measure(d_font, "d")
        d_x = body_x + body.width + 6
        d_draw = DrawText(d_x, baseline + d_descent, "d", d_font, TEXT)

        var_shifted = self._child(node.var, d_x + d_width + 2, baseline, size)

        draws, hits, nodes = _merge(upper_shifted, lower_shifted, body_shifted)
        draws = [
            DrawText(x, baseline + glyph_descent, "∫", glyph_font, TEXT),
            *draws,
            d_draw,
            *var_shifted.draws,
        ]
        hits = hits + var_shifted.hits
        nodes = nodes + var_shifted.nodes

        ascent = max(
            glyph_ascent,
            upper_baseline + upper.ascent,
            body.ascent,
            d_ascent,
            var_shifted.ascent,
        )
        descent = max(
            glyph_descent,
            lower_baseline + lower.descent,
            body.descent,
            d_descent,
            var_shifted.descent,
        )
        width = d_x + d_width + 2 + var_shifted.width - x
        return Layout(width, ascent, descent, draws, hits, nodes)


    def _layout_fraction(self, node: FractionNode, x: float, baseline: float, size: float) -> Layout:
        numerator = self._layout_slot(node.numerator, 0.0, 0.0, size)
        denominator = self._layout_slot(node.denominator, 0.0, 0.0, size)
        gap = 7.0
        padding = 12.0
        width = max(numerator.width, denominator.width) + padding * 2

        numerator_baseline = -gap - numerator.descent
        denominator_baseline = gap + denominator.ascent
        numerator_shifted = shift_layout(
            numerator,
            x + (width - numerator.width) / 2,
            baseline + numerator_baseline,
        )
        denominator_shifted = shift_layout(
            denominator,
            x + (width - denominator.width) / 2,
            baseline + denominator_baseline,
        )

        draws, hits, nodes = _merge(numerator_shifted, denominator_shifted)
        draws.append(DrawLine(x + 2, baseline, x + width - 2, baseline, TEXT, 1.4))

        ascent = max(0.0, -numerator_baseline + numerator.ascent)
        descent = max(0.0, denominator_baseline + denominator.descent)
        return Layout(width, ascent, descent, draws, hits, nodes)


    def _layout_power(self, node: SuperscriptNode, x: float, baseline: float, size: float) -> Layout:
        exponent_size = max(11.0, size * 0.64)
        base = self._child(node.base, x, baseline, size)
        exponent_baseline = -max(base.ascent * 0.52, size * 0.38)
        exponent = self._child(
            node.exponent,
            x + base.width + 2,
            baseline + exponent_baseline,
            exponent_size,
        )

        draws, hits, nodes = _merge(base, exponent)
        ascent = max(base.ascent, -exponent_baseline + exponent.ascent)
        descent = max(base.descent, exponent_baseline + exponent.descent)
        width = base.width + 2 + exponent.width
        return Layout(width, ascent, descent, draws, hits, nodes)


    def _layout_subscript(self, node: SubscriptNode, x: float, baseline: float, size: float) -> Layout:
        script_size = max(11.0, size * 0.64)
        base = self._child(node.base, x, baseline, size)
        subscript_baseline = max(base.descent * 0.55, size * 0.22)
        subscript = self._child(
            node.subscript,
            x + base.width + 2,
            baseline + subscript_baseline,
            script_size,
        )

        draws, hits, nodes = _merge(base, subscript)
        ascent = max(base.ascent, -subscript_baseline + subscript.ascent)
        descent = max(base.descent, subscript_baseline + subscript.descent)
        width = base.width + 2 + subscript.width
        return Layout(width, ascent, descent, draws, hits, nodes)


    def _layout_subsup(self, node: SubSuperscriptNode, x: float, baseline: float, size: float) -> Layout:
        script_size = max(11.0, size * 0.64)
        base = self._child(node.base, x, baseline, size)
        script_x = x + base.width + 2
        superscript_baseline = -max(base.ascent * 0.52, size * 0.38)
        subscript_baseline = max(base.descent * 0.55, size * 0.22)
        superscript = self._child(
            node.superscript, script_x, baseline + superscript_baseline, script_size
        )
        subscript = self._child(
            node.subscript, script_x, baseline + subscript_baseline, script_size
        )

        draws, hits, nodes = _merge(base, superscript, subscript)
        ascent = max(base.ascent, -superscript_baseline + superscript.ascent)
        descent = max(base.descent, subscript_baseline + subscript.descent)
        width = base.width + 2 + max(subscript.width, superscript.width)
        return Layout(width, ascent, descent, draws, hits, nodes)


    def _layout_accent(self, node: AccentNode, x: float, baseline: float, size: float) -> Layout:
        body = self._child(node.body, x, baseline, size)

        glyph = self.ACCENT_GLYPHS.get(node.mark, "ˆ")
        gap = max(2.0, size * 0.12)
        top = -body.ascent - gap

        draws = list(body.draws)
        if glyph:
            font = self._font(max(10.0, size * 0.62), italic=False)
            mark_width, mark_ascent, mark_descent = self._measure(font, glyph)
            mark_baseline = top - mark_descent
            draws.append(
                DrawText(
                    x + (body.width - mark_width) / 2,
                    mark_baseline,
                    glyph,
                    font,
                    TEXT,
                )
            )
            ascent_total = -mark_baseline + mark_ascent
        else:
            # 横线：紧贴内容上方画一条与内容同宽的线。
            line_y = top - 1
            draws.append(DrawLine(x, line_y, x + body.width, line_y, TEXT, 1.6))
            ascent_total = -line_y + 1.6

        ascent = max(ascent_total, body.ascent)
        return Layout(
            body.width,
            ascent,
            body.descent,
            draws,
            body.hits,
            body.nodes,
        )


    def _layout_root(self, node: RootNode, x: float, baseline: float, size: float) -> Layout:
        radicand = self._layout_slot(node.radicand, 0.0, 0.0, size)
        index_layout: Optional[Layout] = None
        if node.index is not None:
            index_layout = self._layout_slot(node.index, 0.0, 0.0, max(11.0, size * 0.55))

        index_width = index_layout.width if index_layout is not None else 0.0
        stem_width = max(18.0, index_width + 6.0 if index_layout is not None else 18.0)
        content_x = x + stem_width + 2
        rad_top = -radicand.ascent - 4
        rad_bottom = radicand.descent + 4
        lift = min(11.0, max(4.0, (rad_bottom - rad_top) * 0.3))

        draws: list[DrawOp] = [
            DrawLine(x, baseline + rad_bottom - lift, x + 6, baseline + rad_bottom, TEXT, 1.6),
            DrawLine(x + 6, baseline + rad_bottom, x + stem_width - 2, baseline + rad_top, TEXT, 1.6),
            DrawLine(
                x + stem_width - 2,
                baseline + rad_top,
                content_x + radicand.width + 2,
                baseline + rad_top,
                TEXT,
                1.6,
            ),
        ]

        radicand_shifted = shift_layout(radicand, content_x, baseline)
        draws.extend(radicand_shifted.draws)
        hits = list(radicand_shifted.hits)
        nodes = list(radicand_shifted.nodes)

        index_baseline = rad_top
        if index_layout is not None:
            index_baseline = rad_top - 6 - index_layout.descent
            index_shifted = shift_layout(index_layout, x + 2, baseline + index_baseline)
            draws.extend(index_shifted.draws)
            hits.extend(index_shifted.hits)
            nodes.extend(index_shifted.nodes)

        ascent = max(radicand.ascent + 4, -index_baseline + (index_layout.ascent if index_layout else 0))
        descent = radicand.descent + 4
        width = stem_width + radicand.width + 4
        return Layout(width, ascent, descent, draws, hits, nodes)


    def _layout_matrix(self, node: MatrixNode, x: float, baseline: float, size: float) -> Layout:
        cell_size = max(10.0, size * 0.88)
        cell_layouts: list[list[Layout]] = [
            [self._layout_slot(cell, 0.0, 0.0, cell_size) for cell in row]
            for row in node.rows
        ]
        if not cell_layouts or not cell_layouts[0]:
            return empty_layout()

        row_count = len(cell_layouts)
        col_count = max(len(row) for row in cell_layouts)
        col_widths = [
            max(
                cell_layouts[r][c].width
                for r in range(row_count)
                if c < len(cell_layouts[r])
            )
            + 14.0
            for c in range(col_count)
        ]
        row_heights = [
            max(cell.ascent + cell.descent for cell in cell_layouts[r]) + 10.0
            for r in range(row_count)
        ]
        inner_width = sum(col_widths) + 5.0 * (col_count - 1)
        inner_height = sum(row_heights) + 5.0 * (row_count - 1)
        top = -inner_height / 2

        paren_size = max(size * 0.9, inner_height / 1.55)
        paren_font = self._font(paren_size, family=self.symbol_font)
        left_w, left_a, left_d = self._measure(paren_font, "(")
        right_w, right_a, right_d = self._measure(paren_font, ")")
        paren_half = max(left_a + left_d, right_a + right_d) / 2

        left_x = x
        inner_x = x + left_w + 6
        right_x = inner_x + inner_width + 6
        width = right_x + right_w - x

        draws: list[DrawOp] = [
            DrawText(left_x + left_w / 2, baseline, "(", paren_font, TEXT, anchor="center"),
            DrawText(right_x + right_w / 2, baseline, ")", paren_font, TEXT, anchor="center"),
        ]
        hits: list[HitArea] = []
        nodes: list[NodeBox] = []

        row_top = top
        for r in range(row_count):
            row = cell_layouts[r]
            row_height = row_heights[r]
            max_ascent = max(cell.ascent for cell in row)
            row_baseline = row_top + 5 + max_ascent
            col_x = inner_x
            for c, cell in enumerate(row):
                cell_x = col_x + (col_widths[c] - cell.width) / 2
                shifted = shift_layout(cell, cell_x, baseline + row_baseline)
                draws.extend(shifted.draws)
                hits.extend(shifted.hits)
                nodes.extend(shifted.nodes)
                col_x += col_widths[c] + 5
            row_top += row_height + 5

        half_height = max(inner_height / 2, paren_half) + 4
        return Layout(width, half_height, half_height, draws, hits, nodes)


    def _paint_layout(
        self,
        canvas: tk.Canvas,
        layout: Layout,
        x_offset: float,
        baseline_offset: float,
    ) -> None:
        canvas.delete("all")
        if layout.selection:
            for row in layout.selection:
                canvas.create_rectangle(
                    row.x1 + x_offset,
                    row.y1 + baseline_offset,
                    row.x2 + x_offset,
                    row.y2 + baseline_offset,
                    fill=SELECTION_FILL,
                    outline="",
                    width=0,
                )
        for draw in layout.draws:
            if isinstance(draw, DrawText):
                canvas.create_text(
                    draw.x + x_offset,
                    draw.y + baseline_offset,
                    text=draw.text,
                    font=draw.font,
                    fill=draw.fill,
                    anchor=draw.anchor,
                )
            elif isinstance(draw, DrawRect):
                canvas.create_rectangle(
                    draw.x1 + x_offset,
                    draw.y1 + baseline_offset,
                    draw.x2 + x_offset,
                    draw.y2 + baseline_offset,
                    fill=draw.fill,
                    outline=draw.outline,
                    width=draw.width,
                    dash=draw.dash or "",
                )
            else:
                canvas.create_line(
                    draw.x1 + x_offset,
                    draw.y1 + baseline_offset,
                    draw.x2 + x_offset,
                    draw.y2 + baseline_offset,
                    fill=draw.fill,
                    width=draw.width,
                )

