# -*- coding: utf-8 -*-
"""内置冒烟测试。"""
from __future__ import annotations

from types import SimpleNamespace

from .config import SELECTION_FILL, SYMBOL_LATEX, iter_panel_glyphs
from .model import (
    Placeholder,
    SumNode,
    TextRun,
    count_placeholders,
    normalize_formula,
    serialize_slot,
    serialize_text,
)


class SmokeTestMixin:
    """通过真实窗口操作验证主要编辑、布局、源码和预览功能。"""

    def run_smoke_test(self) -> None:
        self.root.update()
        self.insert_template("sum")
        self._insert_text("i=1")
        self._move_selection(1)
        self._insert_text("n")
        self._move_selection(1)
        self._insert_text("i^2")
        self.root.update()
        assert count_placeholders(self.root_slot) == 0
        latex = normalize_formula(serialize_slot(self.root_slot))
        assert latex == r"\sum_{i=1}^{n} i^2", latex
        self._render_canvas()
        self.root.update()
        assert self.canvas.find_all(), "canvas should contain formula items"
        assert self._hit_areas, "formula should contain clickable text areas"
        self._sync_markdown_source()
        result = self.output.get("1.0", "end-1c")
        assert result == "$$\n" + latex + "\n$$", result
        assert self._current_markdown == result
        assert self.copy_button.instate(["!disabled"])
        self._update_output_preview()
        assert self._output_preview_pil is not None, self._output_preview_error

        self.clear_formula()
        self.insert_template("integral")
        for value in ("0", r"\infty", r"e^{-x^2}", "x"):
            self._insert_text(value)
            self._move_selection(1)
        self._render_canvas()
        self.root.update()
        latex2 = normalize_formula(serialize_slot(self.root_slot))
        assert r"\int_{0}^{\infty}" in latex2, latex2
        self._update_output_preview()

        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("b")
        assert normalize_formula(serialize_slot(self.root_slot)) == r"\frac{a}{b}"

        self.clear_formula()
        self.insert_template("power")
        self._insert_text("x")
        self._move_selection(1)
        self._insert_text("2")
        assert normalize_formula(serialize_slot(self.root_slot)) == "{x}^{2}"
        self._update_output_preview()

        # 角标：上角标两个空位（底数、上标），下角标两个空位（底数、下标），
        # 上下角标三个空位（底数、下标、上标）。
        self.clear_formula()
        self.insert_template("subscript")
        assert count_placeholders(self.root_slot) == 2
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("n")
        assert normalize_formula(serialize_slot(self.root_slot)) == "{a}_{n}", (
            normalize_formula(serialize_slot(self.root_slot))
        )
        self._render_canvas()
        self.root.update()
        self._update_output_preview()
        assert self._output_preview_pil is not None, self._output_preview_error

        self.clear_formula()
        self.insert_template("sub_sup")
        assert count_placeholders(self.root_slot) == 3
        for value in ("x", "i", "2"):
            self._insert_text(value)
            self._move_selection(1)
        assert normalize_formula(serialize_slot(self.root_slot)) == "{x}_{i}^{2}", (
            normalize_formula(serialize_slot(self.root_slot))
        )
        self._render_canvas()
        self.root.update()
        self._update_output_preview()
        assert self._output_preview_pil is not None, self._output_preview_error

        # 拆掉角标结构：在下角标格位最前方回格，整个角标删除并用该格位内容替换。
        self._set_active(self.root_slot.items[1].subscript, 0, 0)
        self._on_backspace()
        assert normalize_formula(serialize_slot(self.root_slot)) == "i", (
            "backspace at the front of a subscript should unwrap the script structure"
        )

        self.clear_formula()
        self.insert_template("nth_root")
        self._insert_text("x")
        self._move_selection(1)
        self._insert_text("3")
        assert normalize_formula(serialize_slot(self.root_slot)) == r"\sqrt[3]{x}"

        self.clear_formula()
        self.insert_matrix(2, 2)
        for value in ("1", "2", "3", "4"):
            self._insert_text(value)
            self._move_selection(1)
        matrix_latex = normalize_formula(serialize_slot(self.root_slot))
        assert r"\begin{pmatrix}" in matrix_latex, matrix_latex
        self._render_canvas()
        self.root.update()
        self._update_output_preview()
        assert self._output_preview_custom, "matrix preview should use canvas renderer"
        assert self.output_preview_canvas.find_all(), "matrix preview should be drawn"

        self.clear_formula()
        self.insert_symbol("·")
        self._insert_text("a")
        assert r"\cdot" in normalize_formula(serialize_slot(self.root_slot))

        # 分类符号面板：每个分类菜单里的符号都能插入并导出为 LaTeX 命令。
        for glyph, expected in (
            ("÷", r"\div"),
            ("∉", r"\notin"),
            ("ℕ", r"\mathbb{N}"),
            ("∬", r"\iint"),
            ("′", r"\prime"),
            ("α", r"\alpha"),
            ("Ω", r"\Omega"),
            ("⇔", r"\Leftrightarrow"),
            ("²", r"^{2}"),
            ("ₙ", r"_{n}"),
            ("°", r"^{\circ}"),
        ):
            self.clear_formula()
            self.insert_symbol(glyph)
            self._render_canvas()
            self.root.update()
            latex_symbol = normalize_formula(serialize_slot(self.root_slot))
            assert expected in latex_symbol, (glyph, latex_symbol)
            assert self.canvas.find_all(), f"符号 {glyph} 应该绘制到画布上"

        # 「标识」里的上/下标字形跟在变量后面时，导出成标准的 ^{} / _{}。
        self.clear_formula()
        self._insert_text("x")
        self.insert_symbol("²")
        assert normalize_formula(serialize_slot(self.root_slot)) == "x^{2}", (
            normalize_formula(serialize_slot(self.root_slot))
        )
        self.clear_formula()
        self._insert_text("a")
        self.insert_symbol("ₙ")
        assert normalize_formula(serialize_slot(self.root_slot)) == "a_{n}", (
            normalize_formula(serialize_slot(self.root_slot))
        )

        # 面板里的每个符号都必须有 LaTeX 映射（ASCII 四则运算原样进 LaTeX，不需要映射）。
        unmapped = [
            glyph
            for glyph in iter_panel_glyphs()
            if not glyph.isascii() and glyph not in SYMBOL_LATEX
        ]
        assert not unmapped, f"这些面板符号缺少 LaTeX 映射: {unmapped}"

        # 每个面板符号的 LaTeX 都必须是 mathtext 能渲染的，否则输出区会报错。
        symbol_latex = " ".join(
            "a" + serialize_text(glyph) + "b" for glyph in SYMBOL_LATEX
        )
        try:
            self._render_latex_image(symbol_latex)
        except Exception as exc:  # noqa: BLE001
            broken = []
            for glyph in SYMBOL_LATEX:
                try:
                    self._render_latex_image("a" + serialize_text(glyph) + "b")
                except Exception:  # noqa: BLE001
                    broken.append(glyph)
            raise AssertionError(f"这些符号无法被 mathtext 渲染: {broken}") from exc

        self.clear_formula()
        self.insert_matrix(1, 2)
        first_cell = self.active_slot
        self._move_caret(1)
        assert self.active_slot is not first_cell, "right arrow should cross to the next input box"
        self._move_caret(-1)
        assert self.active_slot is first_cell, "left arrow should cross back"

        # 点击文本最右侧应添加一个新的输入位置。
        self.clear_formula()
        self._insert_text("x")
        self._render_canvas()
        self.root.update()
        edge = next(
            hit for hit in self._hit_areas if hit.kind == "text-edge-right"
        )
        x = int((edge.x1 + edge.x2) / 2)
        y = int((edge.y1 + edge.y2) / 2)
        self._on_canvas_drag_start(SimpleNamespace(x=x, y=y))
        self._on_canvas_drag_end(SimpleNamespace(x=x, y=y))
        self.root.update()
        assert isinstance(self._active_item(), Placeholder), "clicking text edge should add an input"
        self._insert_text("+")
        assert normalize_formula(serialize_slot(self.root_slot)) == "x+"

        # 四则运算按字符处理：整段文本不因算符拆成多个结构。
        self.clear_formula()
        self._insert_text("x+2")
        assert normalize_formula(serialize_slot(self.root_slot)) == "x+2"

        # 回格/Delete：删除方向上只有结构时，把结构和内部内容整体删除。
        # 回格只往前看，Delete 只往后看，方向反了不能删到另一侧。
        self.clear_formula()
        self.insert_template("sum")
        for value in ("i=1", "n", "i^2"):
            self._insert_text(value)
            self._move_selection(1)
        self._render_canvas()
        self.root.update()
        # 结构最左侧的空位按回格：左边没有东西，不能删右侧的求和。
        self._set_active(self.root_slot, 0, 0)
        self._on_backspace()
        assert r"\sum" in normalize_formula(serialize_slot(self.root_slot)), (
            "backspace at the left edge must not delete the structure on the right"
        )
        # 结构右侧的空位按回格：整体删除左侧的求和。
        self._set_active(self.root_slot, len(self.root_slot.items) - 1, 0)
        self._on_backspace()
        assert normalize_formula(serialize_slot(self.root_slot)) == "", "backspace should delete the whole structure"

        self.clear_formula()
        self.insert_template("integral")
        for value in ("0", "n", "x", "x"):
            self._insert_text(value)
            self._move_selection(1)
        self._render_canvas()
        self.root.update()
        # 结构左侧的空位按 Delete：整体删除右侧的积分。
        self._set_active(self.root_slot, 0, 0)
        self._on_delete()
        assert normalize_formula(serialize_slot(self.root_slot)) == "", "delete should remove the whole structure"

        # 在算符任意格位最前方按回格：整个算符删除，并用该格位的内容替换。
        self.clear_formula()
        self.insert_template("sum")
        for value in ("i=1", "n", "i^2"):
            self._insert_text(value)
            self._move_selection(1)
        self._set_active(self.root_slot.items[1].body, 0, 0)
        self._on_backspace()
        assert normalize_formula(serialize_slot(self.root_slot)) == "i^2", (
            "backspace at the front of a box should replace the operator with the box content"
        )

        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("b")
        self._set_active(self.root_slot.items[1].numerator, 0, 0)
        self._on_backspace()
        assert normalize_formula(serialize_slot(self.root_slot)) == "a", (
            "backspace at the front of the numerator should replace the fraction with it"
        )

        # 结构内部的固定字符（微分的 d）属于算符本身，不随内容一起替换。
        self.clear_formula()
        self.insert_template("derivative")
        derivative_node = self.root_slot.items[1]
        self._set_active(derivative_node.numerator, 1, 0)
        self._on_backspace()
        assert normalize_formula(serialize_slot(self.root_slot)) == "", (
            "unwrapping the derivative must not keep the fixed d"
        )

        # 文本正前方（但不在格位最前方）按回格：删除的是左侧的相邻结构，
        # 绝不反过来删掉右侧的字符。这里用「求和 + 文本」构造同一行里的相邻结构。
        self.clear_formula()
        self.insert_template("sum")
        self._set_active(self.root_slot, len(self.root_slot.items) - 1, 0)
        self._insert_text("x")
        text_index = next(
            index for index, item in enumerate(self.root_slot.items)
            if isinstance(item, TextRun) and item.text == "x"
        )
        self._set_active(self.root_slot, text_index, 0)
        self._on_backspace()
        latex_after = normalize_formula(serialize_slot(self.root_slot))
        assert latex_after == "x", latex_after

        # 文本内部按 Delete / 回格仍然只删一个字符；在文本末尾按 Delete 不跨到右侧。
        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("b")
        inside_fraction = self.root_slot.items[1]
        self._set_active(inside_fraction.denominator, 0, 1)
        self._on_delete()
        assert [type(item).__name__ for item in inside_fraction.denominator.items] == ["TextRun"], (
            "delete at the end of text must not cross to the right"
        )
        self._set_active(inside_fraction.denominator, 0, 1)
        self._on_backspace()
        assert [type(item).__name__ for item in inside_fraction.denominator.items] == ["Placeholder"]

        self.clear_formula()
        self.insert_template("sum")
        for value in ("1", "n", "x"):
            self._insert_text(value)
            self._move_selection(1)
        self._insert_text("+")
        self._set_active(self.root_slot, len(self.root_slot.items) - 1, 0)
        self._on_backspace()
        assert normalize_formula(serialize_slot(self.root_slot)).endswith("x"), "operator char should be removed alone"

        # 拖动选择：从文本拖到算符上时连同结构一起选中，Backspace 一并删除；
        # 从空方框上开始拖动不能产生选择，也不能删除方框。
        self.clear_formula()
        self._insert_text("x")
        self.insert_template("sum")
        self._render_canvas()
        self.root.update()
        sum_box = next(box for box in self._node_boxes if isinstance(box.node, SumNode))
        text_hit = next(
            hit for hit in self._hit_areas if hit.kind == "text" and hit.slot is self.root_slot
        )
        start_x = int(text_hit.char_positions[0]) + 2
        start_y = int((text_hit.y1 + text_hit.y2) / 2)
        mid_y = int((sum_box.y1 + sum_box.y2) / 2)
        end_x = int(sum_box.x2) + 4
        self._on_canvas_drag_start(SimpleNamespace(x=start_x, y=start_y))
        self._on_canvas_drag_motion(SimpleNamespace(x=end_x, y=mid_y))
        self._on_canvas_drag_end(SimpleNamespace(x=end_x, y=mid_y))
        assert self._has_selection(), "dragging from text onto the structure should select it"
        selected_items = [type(segment.item).__name__ for segment in self._selection_state()[1]]
        assert "SumNode" in selected_items, "the dragged-over structure should be selected"
        highlights = [
            self.canvas.coords(item)
            for item in self.canvas.find_all()
            if self.canvas.type(item) == "rectangle"
            and self.canvas.itemcget(item, "fill") == SELECTION_FILL
        ]
        assert any(
            all(abs(actual - expected) <= 1.0 for actual, expected in zip(rect, (
                sum_box.x1, sum_box.y1, sum_box.x2, sum_box.y2
            )))
            for rect in highlights
        ), "selection highlight should match the structure bounds exactly"
        self._on_backspace()
        assert normalize_formula(serialize_slot(self.root_slot)) == "", "deleting a selection should clear it"

        # 空方框不是内容：在它上面拖动不产生选择；在格位最前方按回格时
        # 按「删除整个算符并用该格位内容替换」处理，空方框本身不会单独留下。
        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._render_canvas()
        self.root.update()
        empty_box = next(
            hit for hit in self._hit_areas
            if hit.kind == "placeholder" and hit.slot is self.root_slot.items[1].denominator
        )
        box_x = int((empty_box.x1 + empty_box.x2) / 2)
        box_y = int((empty_box.y1 + empty_box.y2) / 2)
        self._on_canvas_drag_start(SimpleNamespace(x=box_x, y=box_y))
        self._on_canvas_drag_motion(SimpleNamespace(x=box_x + 40, y=box_y))
        self._on_canvas_drag_end(SimpleNamespace(x=box_x + 40, y=box_y))
        assert not self._has_selection(), "dragging on an empty box must not create a selection"
        # 重新点空方框，再按回格：整个分式删除，用该格位（空）的内容替换。
        self._on_canvas_drag_start(SimpleNamespace(x=box_x, y=box_y))
        self._on_canvas_drag_end(SimpleNamespace(x=box_x, y=box_y))
        self._on_backspace()
        latex_after = normalize_formula(serialize_slot(self.root_slot))
        assert latex_after == "", latex_after

        # 选中整个结构时，结构内部的方框也要用选中底色，不能被方框颜色盖住。
        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._render_canvas()
        self.root.update()
        fraction_hit = next(
            hit for hit in self._hit_areas
            if hit.kind == "text" and hit.slot is self.root_slot.items[1].numerator
        )
        fraction_box = next(
            box for box in self._node_boxes if type(box.node).__name__ == "FractionNode"
        )
        mid_y = int((fraction_box.y1 + fraction_box.y2) / 2)
        self._on_canvas_drag_start(
            SimpleNamespace(
                x=int(fraction_hit.char_positions[0]) + 1,
                y=int((fraction_hit.y1 + fraction_hit.y2) / 2),
            )
        )
        self._on_canvas_drag_motion(SimpleNamespace(x=int(fraction_box.x2) + 30, y=mid_y))
        self._on_canvas_drag_end(SimpleNamespace(x=int(fraction_box.x2) + 30, y=mid_y))
        assert self._has_selection(), "dragging from text should select the fraction"
        box_fills = [
            self.canvas.itemcget(item, "fill")
            for item in self.canvas.find_all()
            if self.canvas.type(item) == "rectangle"
        ]
        assert box_fills.count(SELECTION_FILL) >= 2, "selected structure boxes should use the selection color"
        self._on_canvas_drag_end(SimpleNamespace(x=5, y=5))
        self._collapse_selection()

        print("SMOKE TEST PASSED")
        print(result)

