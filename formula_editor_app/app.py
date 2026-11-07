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
    Slot,
    TextRun,
    count_placeholders,
    first_placeholder_in_node,
    first_target,
    iter_targets,
    make_matrix_node,
    make_template,
    normalize_formula,
    normalize_free_boundaries,
    serialize_slot,
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

        self.root_slot = Slot([Placeholder(free=True)], role="公式")
        self.active_slot: Optional[Slot] = self.root_slot
        self.active_index: int = 0
        self.caret: int = 0

        self._undo_stack: list[Slot] = []
        self._redo_stack: list[Slot] = []

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

        x_offset = (width - layout.width) / 2
        baseline_offset = (desired_height - content_height) / 2 + layout.ascent
        self._paint_layout(self.canvas, layout, x_offset, baseline_offset)

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


    def _on_canvas_click(self, event: tk.Event) -> str:
        x = float(event.x)
        y = float(event.y)
        hit = self._find_hit(x, y)
        self.canvas.focus_set()
        if hit is None:
            return "break"
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
            positions = hit.char_positions
            self.caret = min(
                range(len(positions)),
                key=lambda i: abs(positions[i] - x),
            )
        else:
            self.caret = 0
        self._render_canvas()
        self._set_status(
            f"正在编辑：{hit.slot.role}；输入数字或字母即可。",
            "info",
        )
        return "break"


    def _on_canvas_motion(self, event: tk.Event) -> None:
        x = float(event.x)
        y = float(event.y)
        cursor = "xterm" if self._find_hit(x, y) else "arrow"
        if cursor != self._last_cursor:
            self._last_cursor = cursor
            self.canvas.configure(cursor=cursor)


    def _on_canvas_leave(self, _event: Optional[tk.Event] = None) -> None:
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
        self._normalize_free_boundaries()
        self._sync_markdown_source()
        self._render_canvas()
        # 未填写完整时只需切换提示文字，可以立即更新；完整公式的渲染稍作防抖。
        self._schedule_output_preview(0 if not self._current_markdown else 260)
        self._update_canvas_status()


    def _insert_text(self, text: str) -> None:
        text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
        if not text:
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


    def _on_backspace(self, _event: Optional[tk.Event] = None) -> str:
        item = self._active_item()
        if isinstance(item, TextRun) and item.editable and self.caret > 0:
            self._push_undo()
            caret = self.caret
            item.text = item.text[: caret - 1] + item.text[caret:]
            self.caret = caret - 1
            if not item.text:
                self.active_slot.items[self.active_index] = Placeholder(free=item.free)
                self.caret = 0
            self._after_formula_change()
        self.canvas.focus_set()
        return "break"


    def _on_delete(self, _event: Optional[tk.Event] = None) -> str:
        item = self._active_item()
        if isinstance(item, TextRun) and item.editable:
            if self.caret < len(item.text):
                self._push_undo()
                caret = self.caret
                item.text = item.text[:caret] + item.text[caret + 1 :]
                if not item.text:
                    self.active_slot.items[self.active_index] = Placeholder(free=item.free)
                    self.caret = 0
                self._after_formula_change()
        self.canvas.focus_set()
        return "break"


    def _move_caret(self, step: int) -> str:
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
        self._push_undo()

        if isinstance(item, Placeholder):
            slot = self.active_slot
            assert slot is not None
            slot.items[self.active_index] = node
        elif isinstance(item, TextRun) and item.editable:
            slot = self.active_slot
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
        self.root_slot = Slot([Placeholder(free=True)], role="公式")
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

