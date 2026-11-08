# -*- coding: utf-8 -*-
"""主窗口、公式编辑交互与输出控制。"""
from __future__ import annotations

import tkinter as tk
from copy import deepcopy
from tkinter import font as tkfont
from tkinter import messagebox
from typing import Optional

from PIL import Image, ImageTk

from .clipboard import copy_text_to_clipboard
from .config import (
    APP_TITLE,
    AUTO_FIT_SIZES,
    BASE_FONT_SIZE,
    BG,
    CANVAS_PADDING,
    DANGER,
    MAX_CANVAS_HEIGHT,
    MIN_CANVAS_HEIGHT,
    MUTED,
    SUCCESS,
    TEMPLATE_LABELS,
    TEXT,
    WARNING,
)
from .layout import HitArea, Layout, LayoutEngine, NodeBox
from .model import (
    Element,
    Placeholder,
    SelectionRow,
    SelectionSegment,
    Slot,
    TextRun,
    adjacent_structure,
    apply_structure_unwrap,
    count_placeholders,
    delete_structure_toward,
    first_placeholder_in_node,
    first_target,
    is_editable_input,
    is_plain_operator_text,
    is_structure_item,
    iter_placeholders,
    iter_selectable_segments,
    iter_targets,
    make_matrix_node,
    make_template,
    normalize_formula,
    normalize_free_boundaries,
    plan_structure_unwrap,
    remove_selection,
    selected_segments_range,
    serialize_slot,
    slot_parents,
    text_caret_positions,
    text_offset_from_caret,
    to_markdown,
)
from .preview import PreviewMixin
from .smoke import SmokeTestMixin
from .ui import UIBuilderMixin


class FormulaEditorApp(LayoutEngine, PreviewMixin, SmokeTestMixin, UIBuilderMixin):
    """公式编辑器主窗口。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.minsize(880, 780)
        self._place_window()

        self.root_slot = Slot([Placeholder(free=True)], role="公式", row=True)
        self.active_slot: Optional[Slot] = self.root_slot
        self.active_index: int = 0
        self.caret: int = 0

        self._undo_stack: list[Slot] = []
        self._redo_stack: list[Slot] = []

        # 拖动选择：anchor 是按下鼠标的位置，focus 是当前拖动到的位置。
        self._selection_anchor: Optional[tuple[int, int]] = None
        self._selection_focus: Optional[tuple[int, int]] = None
        self._selection_anchor_point: Optional[tuple[float, float]] = None
        self._selection_dragging = False
        self._selection_segments: list[SelectionSegment] = []

        self._canvas_job: Optional[str] = None
        self._output_job: Optional[str] = None
        self._output_resize_job: Optional[str] = None
        self._canvas_size = (0, 0)
        self._requested_canvas_height = MIN_CANVAS_HEIGHT
        self._hit_areas: list[HitArea] = []
        self._node_boxes: list[NodeBox] = []
        self._font_cache: dict[tuple[str, int, bool], tkfont.Font] = {}
        self._base_size = BASE_FONT_SIZE

        self._output_preview_pil: Optional[Image.Image] = None
        self._output_preview_photo: Optional[ImageTk.PhotoImage] = None
        self._output_preview_error = ""
        self._output_preview_custom = False
        self._current_markdown = ""
        self._last_cursor = "arrow"

        self._pick_fonts()
        self._configure_style()
        self._build_ui()
        self._set_window_icon()
        self._bind_shortcuts()

        self._set_status("就绪：输入公式，或用按钮插入模板；←/→ 切换输入位置。", "muted")
        self._update_canvas_status()
        self._canvas_job = self.root.after(60, self._render_canvas)
        self._output_job = self.root.after(200, self._update_output_preview)
        self.root.after(150, self.canvas.focus_set)


    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-z>", lambda event: self.undo())
        self.root.bind("<Control-Z>", lambda event: self.undo())
        self.root.bind("<Control-y>", lambda event: self.redo())
        self.root.bind("<Control-Y>", lambda event: self.redo())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)


    def _schedule_canvas_render(self, delay: int = 40) -> None:
        if self._canvas_job is not None:
            self.root.after_cancel(self._canvas_job)
        self._canvas_job = self.root.after(delay, self._render_canvas)


    def _on_canvas_configure(self, event: tk.Event) -> None:
        size = (event.width, event.height)
        if size == self._canvas_size:
            return
        self._canvas_size = size
        self._schedule_canvas_render(50)


    def _canvas_max_height(self) -> int:
        """主画布最多能长到多高：随窗口高度变化，给下方输出区留出空间。"""
        root_height = self.root.winfo_height()
        if root_height < 400:
            root_height = 900
        return int(max(MIN_CANVAS_HEIGHT + 40, min(MAX_CANVAS_HEIGHT, root_height - 600)))


    def _render_canvas(self) -> None:
        self._canvas_job = None
        width = self.canvas.winfo_width()
        if width <= 20:
            self._canvas_job = self.root.after(50, self._render_canvas)
            return

        # 让方框在选中时也使用选中底色：渲染前告诉布局哪些方框被选中。
        selection_range, selected = self._selection_state()
        if selection_range is not None and self._selection_is_empty(selected):
            # 收拢到光标（宽度为 0）的选择不再算“选中”，方框按普通编辑态绘制。
            selection_range, selected = None, []
        if selection_range is not None:
            self._selection_paint_keys = {
                (id(segment.slot), segment.index) for segment in selected
            }
            self._selection_slots = set()
        else:
            self._selection_paint_keys = set()
            self._selection_slots = set()
        try:
            self._render_canvas_body(width)
        finally:
            self._selection_paint_keys = set()
            self._selection_slots = set()


    def _render_canvas_body(self, width: int) -> None:
        avail_w = width - 44
        max_height = self._canvas_max_height()
        chosen_size = AUTO_FIT_SIZES[-1]
        layout: Optional[Layout] = None

        # 先按较大字号试排；如果内容更高，画布会自动长高（最多 max_height）。
        for candidate in AUTO_FIT_SIZES:
            candidate_layout = self._layout_slot(self.root_slot, 0.0, 0.0, float(candidate))
            needed_height = candidate_layout.ascent + candidate_layout.descent + CANVAS_PADDING
            if candidate_layout.width <= avail_w and needed_height <= max_height:
                chosen_size = candidate
                layout = candidate_layout
                break

        if layout is None:
            chosen_size = AUTO_FIT_SIZES[-1]
            layout = self._layout_slot(self.root_slot, 0.0, 0.0, float(chosen_size))

        content_height = layout.ascent + layout.descent
        desired_height = int(
            round(min(max_height, max(MIN_CANVAS_HEIGHT, content_height + CANVAS_PADDING)))
        )
        if desired_height != self._requested_canvas_height:
            self._requested_canvas_height = desired_height
            self.canvas.configure(height=desired_height)

        self._base_size = chosen_size
        x_offset = (width - layout.width) / 2
        baseline_offset = (desired_height - content_height) / 2 + layout.ascent

        self._hit_areas = [
            HitArea(
                hit.slot,
                hit.index,
                hit.x1 + x_offset,
                hit.y1 + baseline_offset,
                hit.x2 + x_offset,
                hit.y2 + baseline_offset,
                [p + x_offset for p in hit.char_positions] if hit.char_positions else None,
                hit.kind,
            )
            for hit in layout.hits
        ]
        self._node_boxes = [
            NodeBox(
                node.node,
                node.parent_slot,
                node.index,
                node.x1 + x_offset,
                node.y1 + baseline_offset,
                node.x2 + x_offset,
                node.y2 + baseline_offset,
            )
            for node in layout.nodes
        ]

        layout.selection = self._selection_rows(layout)
        self._paint_layout(self.canvas, layout, x_offset, baseline_offset)
        self._base_size = chosen_size
        self._update_canvas_status()


    def _find_hit(self, x: float, y: float) -> Optional[HitArea]:
        candidates = [
            hit
            for hit in self._hit_areas
            if hit.x1 <= x <= hit.x2 and hit.y1 <= y <= hit.y2
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda hit: (hit.x2 - hit.x1) * (hit.y2 - hit.y1))


    # -- 拖动选择 -------------------------------------------------------------


    def _segment_key(self, slot: Slot, index: int) -> tuple[int, int]:
        return (id(slot), index)


    def _segments_missing_bounds(self) -> bool:
        """当前画布上的片段是否与最新的公式树一致（不一致时重新收集）。"""
        expected = 0
        text_keys = {
            self._segment_key(hit.slot, hit.index)
            for hit in self._hit_areas
            if hit.kind in ("text", "placeholder")
        }
        node_keys = {
            self._segment_key(node.parent_slot, node.index) for node in self._node_boxes
        }
        for slot, index, item in iter_selectable_segments(self.root_slot):
            expected += 1
            key = self._segment_key(slot, index)
            if key not in text_keys and key not in node_keys and not is_structure_item(item):
                return True
        return expected != len(self._selection_segments)


    def _collect_segments(self) -> list[SelectionSegment]:
        """把画布元素整理成按阅读顺序排列、可被选中的片段。

        结构以整体出现，它的包围盒覆盖内部内容；因此朝算符方向拖动时，
        算符和它内部的结构会一起被选中。
        """
        text_bounds = {
            self._segment_key(hit.slot, hit.index): (hit.x1, hit.y1, hit.x2, hit.y2)
            for hit in self._hit_areas
            if hit.kind in ("text", "placeholder")
        }
        node_bounds = {
            self._segment_key(node.parent_slot, node.index): node
            for node in self._node_boxes
        }

        segments: list[SelectionSegment] = []
        for slot, index, item in iter_selectable_segments(self.root_slot):
            key = self._segment_key(slot, index)
            bounds = text_bounds.get(key)
            if bounds is not None:
                segments.append(SelectionSegment(item, slot, index, *bounds))
                continue
            node = node_bounds.get(key)
            if node is not None:
                segments.append(
                    SelectionSegment(item, slot, index, node.x1, node.y1, node.x2, node.y2)
                )

        segments.sort(key=lambda seg: (seg.x1, seg.y1))
        return segments


    def _segment_at(self, segments: list[SelectionSegment], x: float, y: float):
        """找出鼠标下的最小片段；点在结构内部时返回最内层的元素。"""
        best: Optional[SelectionSegment] = None
        best_area = None
        for segment in segments:
            if not (segment.x1 - 1 <= x <= segment.x2 + 1):
                continue
            if not (segment.y1 - 1 <= y <= segment.y2 + 1):
                continue
            area = max(1.0, (segment.x2 - segment.x1) * (segment.y2 - segment.y1))
            if best_area is None or area < best_area:
                best, best_area = segment, area
        return best


    def _text_hit_for(self, segment: SelectionSegment) -> Optional[HitArea]:
        return next(
            (
                hit
                for hit in self._hit_areas
                if hit.slot is segment.slot
                and hit.index == segment.index
                and hit.kind == "text"
            ),
            None,
        )


    def _point_for_segment(self, segment: SelectionSegment, x: float) -> tuple[int, int]:
        offset = 0
        if isinstance(segment.item, TextRun):
            hit = self._text_hit_for(segment)
            if hit is not None and hit.char_positions:
                offset = min(
                    text_offset_from_caret(hit.char_positions, x),
                    len(segment.item.text),
                )
        return self._selection_segments.index(segment), offset


    def _selection_point_at(self, x: float, y: float):
        """把画布坐标换算成 (片段下标, 文本偏移)。"""
        segments = self._selection_segments
        if not segments:
            return None
        segment = self._segment_at(segments, x, y)
        if segment is None:
            # 点在空白处时取水平距离最近的片段，方便拖到行首/行尾。
            segment = min(
                segments,
                key=lambda seg: min(abs(seg.x1 - x), abs(seg.x2 - x)),
            )
        return self._point_for_segment(segment, x)


    def _selection_state(self):
        """返回 (选择范围, 选中片段列表)；选择为空时返回 (None, [])。"""
        if self._selection_anchor is None or self._selection_focus is None:
            return None, []
        return selected_segments_range(
            self._selection_segments,
            self._selection_anchor[0],
            self._selection_anchor[1],
            self._selection_focus[0],
            self._selection_focus[1],
        )


    def _selection_is_empty(self, selected: list[SelectionSegment]) -> bool:
        """选择收拢到光标（没有选中任何字符/方框）时返回 True。"""
        if not selected:
            return True
        if len(selected) > 1:
            return False
        return all(
            segment.offset is not None and segment.offset[0] == segment.offset[1]
            for segment in selected
        )


    def _has_selection(self) -> bool:
        selection_range, selected = self._selection_state()
        if selection_range is None or not selected:
            return False
        return not self._selection_is_empty(selected)


    def _collapse_selection(self) -> None:
        self._selection_anchor = None
        self._selection_focus = None
        self._selection_anchor_point = None
        self._selection_dragging = False
        self._selection_segments = []


    def _selection_rows(self, layout: Layout) -> list[SelectionRow]:
        """把选中内容换算成高亮矩形。

        坐标一律用布局坐标（未加画布偏移），由 ``_paint_layout`` 统一再加
        偏移；否则会和画布坐标重复相加，高亮位置就会偏移。
        """
        selection_range, selected = self._selection_state()
        if selection_range is None:
            return []

        hits = {
            (id(hit.slot), hit.index): hit
            for hit in layout.hits
            if hit.kind in ("text", "placeholder")
        }
        nodes = {
            (id(node.parent_slot), node.index): node
            for node in layout.nodes
        }

        rows: list[SelectionRow] = []
        for segment in selected:
            key = (id(segment.slot), segment.index)
            if is_structure_item(segment.item):
                node = nodes.get(key)
                if node is None:
                    continue
                x1, y1, x2, y2 = node.x1, node.y1, node.x2, node.y2
            else:
                hit = hits.get(key)
                if hit is None:
                    continue
                x1, y1, x2, y2 = hit.x1, hit.y1, hit.x2, hit.y2
                if (
                    hit.kind == "text"
                    and hit.char_positions
                    and isinstance(segment.item, TextRun)
                    and segment.offset is not None
                ):
                    x1, x2 = text_caret_positions(
                        hit.char_positions, segment.offset[0], segment.offset[1]
                    )
            if x2 - x1 < 2:
                x2 = x1 + 2
            rows.append(
                SelectionRow(
                    index=0,
                    offset=segment.offset,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                )
            )
        return rows


    def _segment_index_for(self, slot: Slot, index: int) -> Optional[int]:
        for position, segment in enumerate(self._selection_segments):
            if segment.slot is slot and segment.index == index:
                return position
        return None


    def _on_canvas_drag_start(self, event: tk.Event) -> str:
        x = float(event.x)
        y = float(event.y)
        hit = self._find_hit(x, y)
        # 选择只能从“内容”（已填写的文本）上开始：空方框、空位以及它们周围的
        # 空白都不能作为选择起点，避免拖选空方框后把它删掉。
        item = (
            hit.slot.items[hit.index]
            if hit is not None and 0 <= hit.index < len(hit.slot.items)
            else None
        )
        text_hit = None
        if isinstance(item, TextRun) and hit.kind in ("text", "text-edge-left", "text-edge-right"):
            text_hit = next(
                (
                    candidate
                    for candidate in self._hit_areas
                    if candidate.slot is hit.slot
                    and candidate.index == hit.index
                    and candidate.kind == "text"
                ),
                None,
            )
        self._collapse_selection()
        self._selection_segments = self._collect_segments()
        segment_index = (
            self._segment_index_for(hit.slot, hit.index) if text_hit is not None else None
        )
        if text_hit is None or segment_index is None:
            return self._handle_plain_click(x, y)
        offset = 0
        if text_hit.char_positions:
            offset = min(
                text_offset_from_caret(text_hit.char_positions, x),
                len(item.text),
            )
        self._selection_anchor = (segment_index, offset)
        self._selection_focus = (segment_index, offset)
        self._selection_anchor_point = (x, y)
        self._selection_dragging = False
        return "break"


    def _on_canvas_drag_motion(self, event: tk.Event) -> str:
        if self._selection_anchor is None or self._selection_anchor_point is None:
            return "break"
        x = float(event.x)
        y = float(event.y)
        hit = self._find_hit(x, y)
        if hit is not None and hit.kind == "placeholder":
            # 鼠标停在空方框上：不把选择扩展到它所属的结构，空方框不参与选择。
            return "break"
        ax, ay = self._selection_anchor_point
        if not self._selection_dragging:
            if abs(x - ax) < 4 and abs(y - ay) < 4:
                return "break"
            self._selection_dragging = True
        point = self._selection_point_at(x, y)
        if point is None or point == self._selection_focus:
            return "break"
        self._selection_focus = point
        self._render_canvas()
        return "break"


    def _on_canvas_drag_end(self, event: tk.Event) -> str:
        x = float(event.x)
        y = float(event.y)
        self._selection_anchor_point = None
        if not self._selection_dragging:
            self._collapse_selection()
            return self._handle_plain_click(x, y)
        self._selection_dragging = False
        self._render_canvas()
        if self._has_selection():
            self.canvas.focus_set()
            self._set_status("已选中一段内容；直接输入可替换，Backspace/Delete 可删除。", "info")
        else:
            self._collapse_selection()
            self._render_canvas()
        return "break"


    def _add_text_edge_input(self, hit: HitArea, side: str) -> str:
        """点击文本最左/最右侧时，在该侧添加（或聚焦）一个输入位置。"""
        slot = hit.slot
        index = hit.index
        if not (0 <= index < len(slot.items)) or not isinstance(slot.items[index], TextRun):
            return "break"

        neighbor_index = index - 1 if side == "left" else index + 1
        if 0 <= neighbor_index < len(slot.items):
            neighbor = slot.items[neighbor_index]
            if isinstance(neighbor, Placeholder):
                self._set_active(slot, neighbor_index, 0)
                self._set_status(
                    f"已定位到文本{'左' if side == 'left' else '右'}侧的输入位置；直接输入即可。",
                    "info",
                )
                self.canvas.focus_set()
                return "break"

        insert_at = index if side == "left" else index + 1
        self._push_undo()
        slot.items.insert(insert_at, Placeholder(free=True))
        self.active_slot = slot
        self.active_index = insert_at
        self.caret = 0
        self._after_formula_change()
        self._set_status(
            f"已在文本{'左' if side == 'left' else '右'}侧添加输入位置；可直接输入或插入模板。",
            "info",
        )
        self.canvas.focus_set()
        return "break"

    def _on_canvas_click(self, event: tk.Event) -> str:
        return self._on_canvas_drag_start(event)


    def _handle_plain_click(self, x: float, y: float) -> str:
        """没有拖动时的普通点击：定位光标或插入位置。"""
        self._collapse_selection()
        self.canvas.focus_set()
        hit = self._find_hit(x, y)
        if hit is not None and hit.kind in ("text-edge-left", "text-edge-right"):
            if hit.slot.row:
                return self._add_text_edge_input(hit, "left" if hit.kind.endswith("left") else "right")
            # 非行内槽位（上下限、分子分母、角标底数/上下标、矩阵单元格等）里
            # 不新增输入位置：点击文本前后只定位光标，不能在方框外长出新的结构。
            item = (
                hit.slot.items[hit.index]
                if 0 <= hit.index < len(hit.slot.items)
                else None
            )
            if not isinstance(item, TextRun):
                return "break"
            self.active_slot = hit.slot
            self.active_index = hit.index
            self.caret = 0 if hit.kind == "text-edge-left" else len(item.text)
            self._render_canvas()
            self._set_status(f"正在编辑：{hit.slot.role}；输入数字或字母即可。", "info")
            return "break"

        if hit is not None:
            item = (
                hit.slot.items[hit.index]
                if 0 <= hit.index < len(hit.slot.items)
                else None
            )
            if not isinstance(item, (Placeholder, TextRun)):
                return "break"
            self.active_slot = hit.slot
            self.active_index = hit.index
            if hit.kind == "text" and hit.char_positions:
                edge_left = hit.char_positions[0]
                edge_right = hit.char_positions[-1]
                width = max(1.0, edge_right - edge_left)
                if x <= edge_left + width * 0.35:
                    # 点在这段文本的左半部分（含左侧边缘扩展区）：光标落在文本开头。
                    self.caret = 0
                else:
                    offset = min(
                        text_offset_from_caret(hit.char_positions, x),
                        len(item.text),
                    )
                    # 光标是“字符之间”的位置：点第 i 个字符左半边时落在 i 处。
                    for char_index in range(
                        min(len(item.text), len(hit.char_positions) - 2)
                    ):
                        left = hit.char_positions[char_index]
                        right = hit.char_positions[char_index + 1]
                        if left <= x < (left + right) / 2:
                            offset = char_index
                            break
                    self.caret = min(offset, len(item.text))
            else:
                self.caret = 0
            self._render_canvas()
            self._set_status(
                f"正在编辑：{hit.slot.role}；输入数字或字母即可。",
                "info",
            )
            return "break"

        # 点在结构（算符）左右两侧：光标进入该结构前后的隐藏位置。
        side = self._structure_side_at(x, y)
        if side is not None:
            node, side_name = side
            self._focus_structure_side(node, side_name)
            return "break"

        # 点在结构（算符）上：落到它第一个空方框，或它右侧的隐藏位置。
        segment = self._segment_at(self._collect_segments(), x, y)
        if segment is not None and is_structure_item(segment.item):
            self._select_first_placeholder_of(segment.item)
            self.canvas.focus_set()
            return "break"
        self._render_canvas()
        return "break"


    def _structure_side_at(self, x: float, y: float):
        """找出鼠标所在的结构侧边区域，返回 (结构包围盒, "left"/"right")。"""
        margin = getattr(self, "STRUCTURE_SIDE_MARGIN", 12.0)
        best = None
        for node in self._node_boxes:
            if not (node.y1 - margin <= y <= node.y2 + margin):
                continue
            if node.x1 - margin <= x < node.x1:
                distance, side = node.x1 - x, "left"
            elif node.x2 < x <= node.x2 + margin:
                distance, side = x - node.x2, "right"
            else:
                continue
            if best is None or distance < best[0]:
                best = (distance, node, side)
        if best is None:
            return None
        return best[1], best[2]


    def _focus_structure_side(self, node: NodeBox, side: str) -> None:
        """把光标放到结构左侧/右侧的隐藏位置（必要时补一个隐藏空位）。"""
        slot = node.parent_slot
        index = node.index
        if not (0 <= index < len(slot.items)) or slot.items[index] is not node.node:
            self._render_canvas()
            return

        if side == "left":
            position = index - 1
            need_insert = position < 0 or not is_editable_input(slot.items[position])
            if need_insert:
                self._push_undo()
                slot.items.insert(index, Placeholder(free=True))
                position = index
                self.active_slot = slot
                self.active_index = position
                self.caret = 0
                self._after_formula_change()
            else:
                item = slot.items[position]
                self._set_active(
                    slot,
                    position,
                    len(item.text) if isinstance(item, TextRun) else 0,
                )
        else:
            position = index + 1
            need_insert = position >= len(slot.items) or not is_editable_input(slot.items[position])
            if need_insert:
                self._push_undo()
                slot.items.insert(index + 1, Placeholder(free=True))
                position = index + 1
                self.active_slot = slot
                self.active_index = position
                self.caret = 0
                self._after_formula_change()
            else:
                self._set_active(slot, position, 0)
        self._set_status("已定位到算符旁边的输入位置；直接输入或插入结构即可。", "info")
        self.canvas.focus_set()


    def _on_canvas_motion(self, event: tk.Event) -> None:
        x = float(event.x)
        y = float(event.y)
        hit = self._find_hit(x, y)
        if (
            hit is not None
            and hit.kind in ("text-edge-left", "text-edge-right")
            and hit.slot.row
        ):
            cursor = "hand2"
        elif hit is not None:
            cursor = "xterm"
        elif self._structure_side_at(x, y) is not None:
            cursor = "xterm"
        elif any(
            segment.x1 <= x <= segment.x2 and segment.y1 <= y <= segment.y2
            for segment in self._selection_segments
        ):
            cursor = "xterm"
        else:
            cursor = "arrow"
        if cursor != self._last_cursor:
            self._last_cursor = cursor
            self.canvas.configure(cursor=cursor)


    def _on_canvas_leave(self, _event: Optional[tk.Event] = None) -> None:
        if self._selection_dragging:
            return
        if self._last_cursor != "arrow":
            self._last_cursor = "arrow"
            self.canvas.configure(cursor="arrow")


    def _active_item(self):
        if self.active_slot is None or self.active_index is None:
            return None
        if not (0 <= self.active_index < len(self.active_slot.items)):
            return None
        return self.active_slot.items[self.active_index]


    def _set_active(self, slot: Slot, index: int, caret: int = 0) -> None:
        self.active_slot = slot
        self.active_index = index
        self.caret = caret
        self.canvas.focus_set()
        self._render_canvas()
        self._update_canvas_status()


    def _select_first_target(self) -> None:
        target = first_target(self.root_slot)
        if target is None:
            self.active_slot = None
            self.active_index = 0
            self.caret = 0
            return
        slot, index, item = target
        caret = len(item.text) if isinstance(item, TextRun) else 0
        self.active_slot = slot
        self.active_index = index
        self.caret = caret


    def _select_first_placeholder_of(self, node: Element) -> None:
        target = first_placeholder_in_node(node)
        if target is not None:
            self._set_active(target[0], target[1], 0)
        else:
            self._select_first_target()
            self._update_canvas_status()


    def _push_undo(self) -> None:
        self._undo_stack.append(deepcopy(self.root_slot))
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()


    def _sync_markdown_source(self) -> None:
        """把当前公式同步到 Markdown 源码框；这是即时更新，不做防抖。"""
        placeholders = count_placeholders(self.root_slot)
        latex = normalize_formula(serialize_slot(self.root_slot))
        markdown = "" if placeholders or not latex else to_markdown(latex)

        if markdown == self._current_markdown:
            if markdown:
                self.copy_button.state(["!disabled"])
            else:
                self.copy_button.state(["disabled"])
            return

        self._current_markdown = markdown
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        if markdown:
            self.output.insert("1.0", markdown)
        self.output.configure(state="disabled")

        if markdown:
            self.output.see("1.0")
            self.copy_button.state(["!disabled"])
        else:
            self.copy_button.state(["disabled"])


    def _schedule_output_preview(self, delay: int = 260) -> None:
        if self._output_job is not None:
            self.root.after_cancel(self._output_job)
        self._output_job = self.root.after(delay, self._update_output_preview)


    def _normalize_free_boundaries(self) -> None:
        active_item = self._active_item()
        active_slot = self.active_slot
        normalize_free_boundaries(self.root_slot)
        if active_item is not None and active_slot is not None:
            for index, item in enumerate(active_slot.items):
                if item is active_item:
                    self.active_index = index
                    break


    def _after_formula_change(self) -> None:
        self._collapse_selection()
        self._normalize_free_boundaries()
        self._sync_markdown_source()
        self._render_canvas()
        # 未填写完整时只需切换提示文字，可以立即更新；完整公式的渲染稍作防抖。
        self._schedule_output_preview(0 if not self._current_markdown else 260)
        self._update_canvas_status()


    def _replace_selection(self, text: str):
        """有选择时先删掉选中内容，返回插入点 (槽位, 下标, 光标)。"""
        selection_range, selected = self._selection_state()
        if selection_range is None:
            return None
        target = remove_selection(selected)
        self._collapse_selection()
        return target


    def _insert_text(self, text: str) -> None:
        text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
        if not text:
            return

        if self._has_selection():
            self._push_undo()
            target = self._replace_selection(text)
            if target is not None:
                slot, index, caret = target
                self.active_slot = slot
                self.active_index = index
                self.caret = caret
                item = self._active_item()
                if isinstance(item, TextRun) and item.editable:
                    item.text = item.text[:caret] + text + item.text[caret:]
                    self.caret = caret + len(text)
                elif isinstance(item, Placeholder):
                    self.active_slot.items[self.active_index] = TextRun(text, free=item.free)
                    self.caret = len(text)
            self._after_formula_change()
            self.canvas.focus_set()
            return

        item = self._active_item()
        if item is None:
            self._select_first_target()
            item = self._active_item()
            if item is None:
                return

        if isinstance(item, Placeholder):
            self._push_undo()
            self.active_slot.items[self.active_index] = TextRun(text, free=item.free)
            self.caret = len(text)
        elif isinstance(item, TextRun) and item.editable:
            self._push_undo()
            caret = max(0, min(self.caret, len(item.text)))
            item.text = item.text[:caret] + text + item.text[caret:]
            self.caret = caret + len(text)
        else:
            return

        self._after_formula_change()
        self.canvas.focus_set()


    def _on_canvas_key(self, event: tk.Event) -> str:
        char = event.char
        if char and char.isprintable():
            self._insert_text(char)
        return "break"


    def _delete_selected(self) -> bool:
        selection_range, selected = self._selection_state()
        if selection_range is None:
            return False
        self._push_undo()
        target = self._replace_selection("")
        if target is not None:
            slot, index, caret = target
            self.active_slot = slot
            self.active_index = index
            self.caret = caret
        self._after_formula_change()
        self.canvas.focus_set()
        return True


    def _delete_structure(self, direction: int) -> bool:
        """删除方向只有算符时，把算符和它内部的结构整体删除。"""
        if self.active_slot is None:
            return False
        target = delete_structure_toward(
            self.active_slot,
            self.active_index,
            self.caret,
            direction,
            self._active_item(),
        )
        if target is None:
            return False
        slot, index = target
        if not (0 <= index < len(slot.items)):
            return False
        self._push_undo()
        slot.items.pop(index)
        index = min(index, max(0, len(slot.items) - 1))
        if not slot.items:
            slot.items.append(Placeholder(free=True))
            index = 0
        elif not is_editable_input(slot.items[index]):
            for candidate in range(index - 1, -1, -1):
                if is_editable_input(slot.items[candidate]):
                    index = candidate
                    break
        self.active_slot = slot
        self.active_index = index
        self.caret = 0
        self._after_formula_change()
        self._set_status("已删除相邻的算符及其内部结构；可用 Ctrl+Z 撤销。", "muted")
        self.canvas.focus_set()
        return True


    def _unwrap_structure(self) -> bool:
        """在算符任意格位最前方回格：删除整个算符，并用该格位的内容替换。"""
        if self.active_slot is None:
            return False
        plan = plan_structure_unwrap(
            self.active_slot,
            self.active_index,
            self.caret,
            slot_parents(self.root_slot),
        )
        if plan is None:
            return False
        self._push_undo()
        parent_slot, start, count = apply_structure_unwrap(plan)
        self.active_slot = parent_slot
        self.active_index = start
        self.caret = 0
        self._select_front_of(parent_slot, start, count)
        self._after_formula_change()
        self._set_status("已删除整个算符，并用该格位的内容替换；可用 Ctrl+Z 撤销。", "muted")
        self.canvas.focus_set()
        return True


    def _select_front_of(self, slot: Slot, start: int, count: int) -> None:
        """把光标放到刚替换进来的内容最前面。"""
        for offset in range(count):
            position = start + offset
            if position >= len(slot.items):
                return
            item = slot.items[position]
            if isinstance(item, (Placeholder, TextRun)):
                self.active_index = position
                self.caret = 0
                return
            if is_structure_item(item):
                target = first_placeholder_in_node(item)
                if target is not None:
                    self.active_slot, self.active_index, self.caret = (
                        target[0],
                        target[1],
                        0,
                    )
                    return
                # 结构已经填满：把光标放在它右侧的隐藏位置。
                following = position + 1
                if following >= len(slot.items) or not is_editable_input(
                    slot.items[following]
                ):
                    slot.items.insert(following, Placeholder(free=True))
                self.active_index = following
                self.caret = 0
                return
        self.active_index = min(start, max(0, len(slot.items) - 1))
        self.caret = 0


    def _remove_at_caret(self, backward: bool) -> bool:
        """删除光标一侧的相邻元素。

        规则优先级：
        1. 文本内部：删一个字符；
        2. 在算符任意格位最前方按回格：删除整个算符，并用该格位的内容替换；
        3. 删除方向上只有结构时：把该结构连同内部内容整体删除；
        4. 纯算符文本：只删这个算符字符本身。
        绝不在删除方向上跨过文本去删更远的内容。
        """
        item = self._active_item()
        if isinstance(item, TextRun) and item.editable:
            if backward and self.caret > 0:
                return self._remove_text_char(item, self.caret - 1)
            if not backward and self.caret < len(item.text):
                return self._remove_text_char(item, self.caret)
            if backward:
                if self._unwrap_structure():
                    return True
                # 纯算符文本（如单独键入的 +）：删掉这个算符字符本身。
                if item.text and is_plain_operator_text(item.text):
                    return self._remove_text_char(item, 0)
                return self._delete_structure(-1)
            return self._delete_structure(1)
        if backward:
            if self._unwrap_structure():
                return True
            return self._delete_structure(-1)
        return self._delete_structure(1)


    def _remove_text_char(self, item: TextRun, position: int) -> bool:
        self._push_undo()
        position = max(0, min(position, len(item.text) - 1))
        item.text = item.text[:position] + item.text[position + 1 :]
        self.caret = position
        if not item.text:
            self.active_slot.items[self.active_index] = Placeholder(free=item.free)
            self.caret = 0
        self._after_formula_change()
        self.canvas.focus_set()
        return True


    def _on_backspace(self, _event: Optional[tk.Event] = None) -> str:
        if self._delete_selected():
            return "break"
        self._remove_at_caret(backward=True)
        self.canvas.focus_set()
        return "break"


    def _on_delete(self, _event: Optional[tk.Event] = None) -> str:
        if self._delete_selected():
            return "break"
        self._remove_at_caret(backward=False)
        self.canvas.focus_set()
        return "break"


    def _move_caret(self, step: int) -> str:
        if self._selection_anchor is not None:
            # 有选择时方向键先把选择收拢到一端，再继续移动。
            selection_range, selected = self._selection_state()
            if selected:
                first = selected[0]
                last = selected[-1]
                if step > 0:
                    slot, index, offset = last.slot, last.index, (
                        last.offset[1] if last.offset else 0
                    )
                else:
                    slot, index, offset = first.slot, first.index, (
                        first.offset[0] if first.offset else 0
                    )
                self._collapse_selection()
                self.active_slot = slot
                self.active_index = index
                self.caret = offset
                self._render_canvas()
                self._update_canvas_status()
                self.canvas.focus_set()
                return "break"
            self._collapse_selection()

        item = self._active_item()
        if isinstance(item, TextRun) and item.editable:
            new_caret = self.caret + step
            if 0 <= new_caret <= len(item.text):
                if new_caret != self.caret:
                    self.caret = new_caret
                    self._render_canvas()
                    self._update_canvas_status()
                self.canvas.focus_set()
                return "break"

            # 光标已到这一段文本的尽头：先进入同一行里紧挨着的相邻结构；
            # 没有相邻结构就停在原地，不要跳到别的方框去。
            node = adjacent_structure(self.active_slot, self.active_index, step)
            if node is not None:
                if step < 0:
                    self._select_first_placeholder_of(node)
                else:
                    target = first_target(node)
                    if target is not None:
                        self._set_active(target[0], target[1], 0)
                self._set_status("已进入相邻结构；继续按方向键可移动光标。", "info")
                return "break"
            at_text_edge = (step < 0 and self.caret == 0) or (
                step > 0 and self.caret >= len(item.text)
            )
            if at_text_edge:
                self.canvas.focus_set()
                return "break"

        # 光标已经在文本边界，或当前是空位/空方框：切换到相邻输入位置。
        targets = list(iter_targets(self.root_slot))
        if not targets:
            self.canvas.focus_set()
            return "break"

        current_index = None
        for i, (slot, index, _target) in enumerate(targets):
            if slot is self.active_slot and index == self.active_index:
                current_index = i
                break

        if current_index is None:
            next_index = 0 if step > 0 else len(targets) - 1
        else:
            next_index = current_index + step
            if next_index < 0 or next_index >= len(targets):
                self.canvas.focus_set()
                return "break"

        slot, index, target_item = targets[next_index]
        if isinstance(target_item, TextRun):
            caret = len(target_item.text) if step < 0 else 0
        else:
            caret = 0
        self._set_active(slot, index, caret)
        self._set_status(f"正在编辑：{slot.role}；←/→ 可继续切换输入位置。", "info")
        return "break"


    def _move_selection(self, direction: int) -> str:
        self._collapse_selection()
        targets = list(iter_targets(self.root_slot))
        if not targets:
            return "break"
        current_index = None
        for i, (slot, index, item) in enumerate(targets):
            if slot is self.active_slot and index == self.active_index:
                current_index = i
                break
        if current_index is None:
            next_index = 0 if direction > 0 else len(targets) - 1
        else:
            next_index = (current_index + direction) % len(targets)
        slot, index, item = targets[next_index]
        caret = len(item.text) if isinstance(item, TextRun) else 0
        self._set_active(slot, index, caret)
        self._update_canvas_status()
        return "break"


    def _paste_formula(self, _event: Optional[tk.Event] = None) -> str:
        try:
            data = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        data = data.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()
        if data:
            self._insert_text(data)
        return "break"


    def _insert_node(self, node: Element, label: str) -> None:
        item = self._active_item()
        slot = self.active_slot

        if (
            slot is not None
            and not slot.row
            and isinstance(item, TextRun)
            and item.text
        ):
            # 上下限、分子分母、角标底数/上下标、矩阵单元格等方框只放一个结构：
            # 已经填了内容时不能再往里塞新结构（否则结构会“长”到方框外面）。
            self._set_status(
                f"{slot.role}里已经有内容，这个位置只能放一个结构；请先清空再插入{label}。",
                "warning",
            )
            self.canvas.focus_set()
            return

        self._push_undo()

        if isinstance(item, Placeholder):
            assert slot is not None
            slot.items[self.active_index] = node
        elif isinstance(item, TextRun) and item.editable:
            assert slot is not None
            slot.items.insert(self.active_index + 1, node)
        else:
            self.root_slot.items.append(node)

        self._select_first_placeholder_of(node)
        self._after_formula_change()
        self._set_status(f"已插入{label}，依次填写方框即可。", "info")
        self.canvas.focus_set()


    def insert_template(self, key: str) -> None:
        node = make_template(key)
        self._insert_node(node, TEMPLATE_LABELS[key])


    def insert_matrix(self, rows: int, cols: int, kind: str = "matrix") -> None:
        role = "向量元素" if kind == "vector" else "矩阵元素"
        node = make_matrix_node(rows, cols, role)
        label = f"{rows}×{cols} {'列向量' if kind == 'vector' else '矩阵'}"
        self._insert_node(node, label)


    def insert_symbol(self, glyph: str) -> None:
        self._insert_text(glyph)
        self.canvas.focus_set()


    def clear_formula(self) -> None:
        if not self.root_slot.items:
            return
        self._push_undo()
        self.root_slot = Slot([Placeholder(free=True)], role="公式", row=True)
        self.active_slot = self.root_slot
        self.active_index = 0
        self.caret = 0
        self._after_formula_change()
        self._set_status("已清空公式，可用 Ctrl+Z 撤销。", "muted")
        self.canvas.focus_set()


    def undo(self) -> str:
        if not self._undo_stack:
            self._set_status("没有可撤销的操作。", "muted")
            return "break"
        self._redo_stack.append(deepcopy(self.root_slot))
        self.root_slot = self._undo_stack.pop()
        self._select_first_target()
        self._after_formula_change()
        self._set_status("已撤销一步编辑。", "muted")
        self.canvas.focus_set()
        return "break"


    def redo(self) -> str:
        if not self._redo_stack:
            self._set_status("没有可重做的操作。", "muted")
            return "break"
        self._undo_stack.append(deepcopy(self.root_slot))
        self.root_slot = self._redo_stack.pop()
        self._select_first_target()
        self._after_formula_change()
        self._set_status("已重做一步编辑。", "muted")
        self.canvas.focus_set()
        return "break"


    def _update_canvas_status(self) -> None:
        selection_range, selected = self._selection_state()
        if selection_range is not None and selected:
            structures = sum(1 for seg in selected if is_structure_item(seg.item))
            if structures:
                message = f"已选中 {len(selected)} 段内容（含 {structures} 个算符/结构）；输入可替换，Backspace 可删除"
            else:
                message = f"已选中 {len(selected)} 段文本；输入可替换，Backspace 可删除"
            self.canvas_status.configure(text=message)
            return

        item = self._active_item()
        if item is None:
            message = "点击画布中的输入位置开始输入"
        elif isinstance(item, Placeholder):
            kind = "空位" if item.free else "空方框"
            message = f"正在编辑：{self.active_slot.role}（{kind}）"
        elif isinstance(item, TextRun):
            content = item.text if item.text else "空"
            if len(content) > 24:
                content = content[:21] + "..."
            message = f"正在编辑：{self.active_slot.role} · {content}"
        else:
            message = "点击画布中的输入位置开始输入"
        remaining = count_placeholders(self.root_slot)
        if remaining:
            message += f" · 还有 {remaining} 个必填方框待填写"
        elif normalize_formula(serialize_slot(self.root_slot)):
            message += " · 所有必填方框已填写，可以复制"
        else:
            message += " · 输入公式后可复制"
        self.canvas_status.configure(text=message)


    def copy_markdown(self) -> None:
        if not self._current_markdown:
            placeholders = count_placeholders(self.root_slot)
            if placeholders:
                target = next(iter_placeholders(self.root_slot), None)
                if target is not None:
                    slot, index, _item = target
                    self._set_active(slot, index, 0)
                messagebox.showwarning(
                    "还有方框未填写",
                    f"公式中还有 {placeholders} 个方框没有填写。\n请点击方框（或按 Tab）补齐内容后再复制。",
                    parent=self.root,
                )
                self._set_status(f"复制未完成：还有 {placeholders} 个必填方框待填写。", "warning")
            else:
                messagebox.showwarning("还没有公式", "请先在公式中填写内容。", parent=self.root)
                self._set_status("复制未完成：公式为空。", "warning")
            self.canvas.focus_set()
            return

        if not copy_text_to_clipboard(self._current_markdown):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(self._current_markdown)
                self.root.update_idletasks()
            except tk.TclError as exc:
                messagebox.showerror("复制失败", f"无法访问剪贴板：{exc}", parent=self.root)
                return
        self._set_status("Markdown 已复制到剪贴板。", "success")


    def _select_all_output(self, _event: Optional[tk.Event] = None) -> str:
        self.output.tag_add("sel", "1.0", "end-1c")
        self.output.mark_set("insert", "1.0")
        return "break"


    def _set_status(self, message: str, kind: str = "muted") -> None:
        colors = {
            "muted": MUTED,
            "info": TEXT,
            "success": SUCCESS,
            "warning": WARNING,
            "danger": DANGER,
        }
        self.status_label.configure(text=message, fg=colors.get(kind, MUTED))


    def _on_close(self) -> None:
        for job in (self._canvas_job, self._output_job, self._output_resize_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self.root.destroy()

