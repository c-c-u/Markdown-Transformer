# -*- coding: utf-8 -*-
"""内置冒烟测试。

``run_smoke_test`` 只是一串按功能分组的断言方法；每组失败时方法名直接指出
出问题的编辑/布局能力，新增功能时在对应分组里补断言即可。
"""
from __future__ import annotations

from types import SimpleNamespace

from .config import ACCENT_LATEX, SELECTION_FILL, SYMBOL_LATEX, iter_panel_glyphs
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

    # -- 小工具 ---------------------------------------------------------------

    def _latex(self) -> str:
        """当前公式导出的 LaTeX（已去掉多余的数学环境标记）。"""
        return normalize_formula(serialize_slot(self.root_slot))

    def _render(self) -> None:
        """重排一次画布并让 Tk 处理完事件，保证命中区域是最新的。"""
        self._render_canvas()
        self.root.update()

    def run_smoke_test(self) -> None:
        self.root.update()
        markdown = self._smoke_sum_source_and_preview()
        self._smoke_integral_preview()
        self._smoke_fraction()
        self._smoke_power()
        self._smoke_scripts_and_unwrap()
        self._smoke_accents()
        self._smoke_root_and_matrix()
        self._smoke_symbol_panels()
        self._smoke_left_right_caret()
        self._smoke_vertical_arrows()
        self._smoke_text_edge_input()
        self._smoke_plain_operator_text()
        self._smoke_delete_structures()
        self._smoke_unwrap_at_slot_front()
        self._smoke_text_char_delete()
        self._smoke_operator_char_delete()
        self._smoke_drag_selection()
        self._smoke_empty_box_and_highlights()
        print("SMOKE TEST PASSED")
        print(markdown)

    # -- 各功能分组 -----------------------------------------------------------

    def _smoke_sum_source_and_preview(self) -> str:
        """求和：编辑 → 源码 → 复制按钮 → 预览的完整链路，返回生成的 Markdown。"""
        self.insert_template("sum")
        self._insert_text("i=1")
        self._move_selection(1)
        self._insert_text("n")
        self._move_selection(1)
        self._insert_text("i^2")
        self.root.update()
        assert count_placeholders(self.root_slot) == 0
        latex = self._latex()
        assert latex == r"\sum_{i=1}^{n} i^2", latex
        self._render()
        assert self.canvas.find_all(), "canvas should contain formula items"
        assert self._hit_areas, "formula should contain clickable text areas"
        self._sync_markdown_source()
        result = self.output.get("1.0", "end-1c")
        assert result == "$$\n" + latex + "\n$$", result
        assert self._current_markdown == result
        assert self.copy_button.instate(["!disabled"])
        self._update_output_preview()
        assert self._output_preview_pil is not None, self._output_preview_error
        return result


    def _smoke_integral_preview(self) -> None:
        self.clear_formula()
        self.insert_template("integral")
        for value in ("0", r"\infty", r"e^{-x^2}", "x"):
            self._insert_text(value)
            self._move_selection(1)
        self._render()
        latex = self._latex()
        assert r"\int_{0}^{\infty}" in latex, latex
        self._update_output_preview()


    def _smoke_fraction(self) -> None:
        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("b")
        assert self._latex() == r"\frac{a}{b}"


    def _smoke_power(self) -> None:
        self.clear_formula()
        self.insert_template("power")
        self._insert_text("x")
        self._move_selection(1)
        self._insert_text("2")
        assert self._latex() == "{x}^{2}"
        self._update_output_preview()


    def _smoke_scripts_and_unwrap(self) -> None:
        # 角标：上角标两个空位（底数、上标），下角标两个空位（底数、下标），
        # 上下角标三个空位（底数、下标、上标）。
        self.clear_formula()
        self.insert_template("subscript")
        assert count_placeholders(self.root_slot) == 2
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("n")
        assert self._latex() == "{a}_{n}", self._latex()
        self._render()
        self._update_output_preview()
        assert self._output_preview_pil is not None, self._output_preview_error

        self.clear_formula()
        self.insert_template("sub_sup")
        assert count_placeholders(self.root_slot) == 3
        for value in ("x", "i", "2"):
            self._insert_text(value)
            self._move_selection(1)
        assert self._latex() == "{x}_{i}^{2}", self._latex()
        self._render()
        self._update_output_preview()
        assert self._output_preview_pil is not None, self._output_preview_error

        # 拆掉角标结构：在下角标格位最前方回格，整个角标删除并用该格位内容替换。
        self._set_active(self.root_slot.items[1].subscript, 0, 0)
        self._on_backspace()
        assert self._latex() == "i", (
            "backspace at the front of a subscript should unwrap the script structure"
        )


    def _smoke_accents(self) -> None:
        # 顶标：只有内容一个方框，标记画在内容上方，导出成对应 LaTeX 命令。
        for key, expected in (
            ("hat", r"\hat{x}"),
            ("bar", r"\bar{x}"),
            ("vec", r"\vec{x}"),
            ("overline", r"\overline{x}"),
        ):
            self.clear_formula()
            self.insert_template(key)
            assert count_placeholders(self.root_slot) == 1, key
            self._insert_text("x")
            assert self._latex() == expected, (key, self._latex())
            self._render()
            self._update_output_preview()
            assert self._output_preview_pil is not None, (key, self._output_preview_error)

        # 全部顶标命令都要能被 mathtext 渲染。
        accent_latex = " ".join(
            "a" + command + "{x}b" for command in ACCENT_LATEX.values()
        )
        self._render_latex_image(accent_latex)


    def _smoke_root_and_matrix(self) -> None:
        self.clear_formula()
        self.insert_template("nth_root")
        self._insert_text("x")
        self._move_selection(1)
        self._insert_text("3")
        assert self._latex() == r"\sqrt[3]{x}"

        self.clear_formula()
        self.insert_matrix(2, 2)
        for value in ("1", "2", "3", "4"):
            self._insert_text(value)
            self._move_selection(1)
        matrix_latex = self._latex()
        assert r"\begin{pmatrix}" in matrix_latex, matrix_latex
        self._render()
        self._update_output_preview()
        assert self._output_preview_custom, "matrix preview should use canvas renderer"
        assert self.output_preview_canvas.find_all(), "matrix preview should be drawn"


    def _smoke_symbol_panels(self) -> None:
        self.clear_formula()
        self.insert_symbol("·")
        self._insert_text("a")
        assert r"\cdot" in self._latex()

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
        ):
            self.clear_formula()
            self.insert_symbol(glyph)
            self._render()
            latex = self._latex()
            assert expected in latex, (glyph, latex)
            assert self.canvas.find_all(), f"符号 {glyph} 应该绘制到画布上"

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
            broken = [
                glyph
                for glyph in SYMBOL_LATEX
                if not self._can_render("a" + serialize_text(glyph) + "b")
            ]
            raise AssertionError(f"这些符号无法被 mathtext 渲染: {broken}") from exc


    def _can_render(self, latex: str) -> bool:
        try:
            self._render_latex_image(latex)
        except Exception:  # noqa: BLE001
            return False
        return True


    def _smoke_left_right_caret(self) -> None:
        self.clear_formula()
        self.insert_matrix(1, 2)
        first_cell = self.active_slot
        self._move_caret(1)
        assert self.active_slot is not first_cell, (
            "right arrow should cross to the next input box"
        )
        self._move_caret(-1)
        assert self.active_slot is first_cell, "left arrow should cross back"


    def _smoke_vertical_arrows(self) -> None:
        # ↑/↓：多行结构内部按预先写死的格位表切换到上/下方最近的格位；
        # 算符没有登记该方向（分式分子按 ↑、顶标、根行）时停在原地。
        assert self.canvas.bind("<Up>") and self.canvas.bind("<Down>"), (
            "up/down arrows must be bound on the canvas"
        )

        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("b")
        fraction = self.root_slot.items[1]
        self._set_active(fraction.denominator, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is fraction.numerator, (
            "up arrow in the denominator should go to the numerator"
        )
        self._move_caret_vertical(1)
        assert self.active_slot is fraction.denominator, (
            "down arrow in the numerator should go to the denominator"
        )
        self._set_active(fraction.numerator, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is fraction.numerator, (
            "up arrow above the numerator must stay inside the fraction"
        )

        self.clear_formula()
        self.insert_template("sum")
        for value in ("i=1", "n", "i^2"):
            self._insert_text(value)
            self._move_selection(1)
        sum_node = self.root_slot.items[1]
        self._set_active(sum_node.lower, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is sum_node.upper, (
            "up arrow in the lower limit should go to the upper limit"
        )
        self._move_caret_vertical(1)
        assert self.active_slot is sum_node.lower, (
            "down arrow in the upper limit should go to the lower limit"
        )
        self._set_active(sum_node.body, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is sum_node.upper, (
            "up arrow in the summand should go to the upper limit"
        )
        self._move_caret_vertical(1)
        assert self.active_slot is sum_node.lower, (
            "down arrow in the summand should go to the lower limit"
        )

        self.clear_formula()
        self.insert_template("integral")
        for value in ("0", "n", "x", "x"):
            self._insert_text(value)
            self._move_selection(1)
        integral = self.root_slot.items[1]
        self._set_active(integral.lower, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is integral.upper, (
            "up arrow in the integral lower limit should go to the upper limit"
        )
        self._set_active(integral.upper, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is integral.upper, (
            "up arrow above the integral upper limit must stay put"
        )
        self._set_active(integral.var, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is integral.upper, (
            "up arrow in the integration variable should go to the upper limit"
        )

        self.clear_formula()
        self.insert_template("sub_sup")
        subsup = self.root_slot.items[1]
        self._set_active(subsup.base, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is subsup.superscript, (
            "up arrow on the script base should go to the superscript"
        )
        self._move_caret_vertical(1)
        assert self.active_slot is subsup.base, (
            "down arrow in the superscript should go back to the base"
        )
        self._move_caret_vertical(1)
        assert self.active_slot is subsup.subscript, (
            "down arrow on the script base should go to the subscript"
        )
        self._move_caret_vertical(-1)
        assert self.active_slot is subsup.base, (
            "up arrow in the subscript should go back to the base"
        )

        self.clear_formula()
        self.insert_template("nth_root")
        root_node = self.root_slot.items[1]
        self._set_active(root_node.radicand, 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is root_node.index, (
            "up arrow in the radicand should go to the root index"
        )

        self.clear_formula()
        self.insert_matrix(2, 2)
        matrix = self.root_slot.items[1]
        self._set_active(matrix.rows[1][0], 0, 0)
        self._move_caret_vertical(-1)
        assert self.active_slot is matrix.rows[0][0], (
            "up arrow in a matrix cell should go to the same column above"
        )
        self._move_caret_vertical(-1)
        assert self.active_slot is matrix.rows[0][0], (
            "up arrow in the top matrix row must stay put"
        )
        self._move_caret_vertical(1)
        assert self.active_slot is matrix.rows[1][0], (
            "down arrow in a matrix cell should go to the same column below"
        )

        self.clear_formula()
        self.insert_template("hat")
        hat = self.root_slot.items[1]
        self._set_active(hat.body, 0, 0)
        self._move_caret_vertical(-1)
        self._move_caret_vertical(1)
        assert self.active_slot is hat.body, (
            "a single-slot accent has no vertical neighbor"
        )

        self.clear_formula()
        self._set_active(self.root_slot, 0, 0)
        self._move_caret_vertical(-1)
        self._move_caret_vertical(1)
        assert self.active_slot is self.root_slot and self.active_index == 0, (
            "the formula root row has no vertical neighbor"
        )


    def _smoke_text_edge_input(self) -> None:
        # 点击文本最右侧应添加一个新的输入位置。
        self.clear_formula()
        self._insert_text("x")
        self._render()
        edge = next(hit for hit in self._hit_areas if hit.kind == "text-edge-right")
        x = int((edge.x1 + edge.x2) / 2)
        y = int((edge.y1 + edge.y2) / 2)
        self._on_canvas_drag_start(SimpleNamespace(x=x, y=y))
        self._on_canvas_drag_end(SimpleNamespace(x=x, y=y))
        self.root.update()
        assert isinstance(self._active_item(), Placeholder), (
            "clicking text edge should add an input"
        )
        self._insert_text("+")
        assert self._latex() == "x+"


    def _smoke_plain_operator_text(self) -> None:
        # 四则运算按字符处理：整段文本不因算符拆成多个结构。
        self.clear_formula()
        self._insert_text("x+2")
        assert self._latex() == "x+2"


    def _smoke_delete_structures(self) -> None:
        # 回格/Delete：删除方向上只有结构时，把结构和内部内容整体删除。
        # 回格只往前看，Delete 只往后看，方向反了不能删到另一侧。
        self.clear_formula()
        self.insert_template("sum")
        for value in ("i=1", "n", "i^2"):
            self._insert_text(value)
            self._move_selection(1)
        self._render()
        # 结构最左侧的空位按回格：左边没有东西，不能删右侧的求和。
        self._set_active(self.root_slot, 0, 0)
        self._on_backspace()
        assert r"\sum" in self._latex(), (
            "backspace at the left edge must not delete the structure on the right"
        )
        # 结构右侧的空位按回格：整体删除左侧的求和。
        self._set_active(self.root_slot, len(self.root_slot.items) - 1, 0)
        self._on_backspace()
        assert self._latex() == "", "backspace should delete the whole structure"

        self.clear_formula()
        self.insert_template("integral")
        for value in ("0", "n", "x", "x"):
            self._insert_text(value)
            self._move_selection(1)
        self._render()
        # 结构左侧的空位按 Delete：整体删除右侧的积分。
        self._set_active(self.root_slot, 0, 0)
        self._on_delete()
        assert self._latex() == "", "delete should remove the whole structure"


    def _smoke_unwrap_at_slot_front(self) -> None:
        # 在算符任意格位最前方按回格：整个算符删除，并用该格位的内容替换。
        self.clear_formula()
        self.insert_template("sum")
        for value in ("i=1", "n", "i^2"):
            self._insert_text(value)
            self._move_selection(1)
        self._set_active(self.root_slot.items[1].body, 0, 0)
        self._on_backspace()
        assert self._latex() == "i^2", (
            "backspace at the front of a box should replace the operator with the box content"
        )

        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("b")
        self._set_active(self.root_slot.items[1].numerator, 0, 0)
        self._on_backspace()
        assert self._latex() == "a", (
            "backspace at the front of the numerator should replace the fraction with it"
        )

        # 结构内部的固定字符（微分的 d）属于算符本身，不随内容一起替换。
        self.clear_formula()
        self.insert_template("derivative")
        derivative_node = self.root_slot.items[1]
        self._set_active(derivative_node.numerator, 1, 0)
        self._on_backspace()
        assert self._latex() == "", (
            "unwrapping the derivative must not keep the fixed d"
        )

        # 文本正前方（但不在格位最前方）按回格：删除的是左侧的相邻结构，
        # 绝不反过来删掉右侧的字符。这里用「求和 + 文本」构造同一行里的相邻结构。
        self.clear_formula()
        self.insert_template("sum")
        self._set_active(self.root_slot, len(self.root_slot.items) - 1, 0)
        self._insert_text("x")
        text_index = next(
            index
            for index, item in enumerate(self.root_slot.items)
            if isinstance(item, TextRun) and item.text == "x"
        )
        self._set_active(self.root_slot, text_index, 0)
        self._on_backspace()
        assert self._latex() == "x", self._latex()


    def _smoke_text_char_delete(self) -> None:
        # 文本内部按 Delete / 回格仍然只删一个字符；在文本末尾按 Delete 不跨到右侧。
        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._move_selection(1)
        self._insert_text("b")
        inside_fraction = self.root_slot.items[1]
        self._set_active(inside_fraction.denominator, 0, 1)
        self._on_delete()
        assert [type(item).__name__ for item in inside_fraction.denominator.items] == [
            "TextRun"
        ], "delete at the end of text must not cross to the right"
        self._set_active(inside_fraction.denominator, 0, 1)
        self._on_backspace()
        assert [
            type(item).__name__ for item in inside_fraction.denominator.items
        ] == ["Placeholder"]


    def _smoke_operator_char_delete(self) -> None:
        self.clear_formula()
        self.insert_template("sum")
        for value in ("1", "n", "x"):
            self._insert_text(value)
            self._move_selection(1)
        self._insert_text("+")
        self._set_active(self.root_slot, len(self.root_slot.items) - 1, 0)
        self._on_backspace()
        assert self._latex().endswith("x"), "operator char should be removed alone"


    def _smoke_drag_selection(self) -> None:
        # 拖动选择：从文本拖到算符上时连同结构一起选中，Backspace 一并删除；
        # 从空方框上开始拖动不能产生选择，也不能删除方框。
        self.clear_formula()
        self._insert_text("x")
        self.insert_template("sum")
        self._render()
        sum_box = next(box for box in self._node_boxes if isinstance(box.node, SumNode))
        text_hit = next(
            hit
            for hit in self._hit_areas
            if hit.kind == "text" and hit.slot is self.root_slot
        )
        start_x = int(text_hit.char_positions[0]) + 2
        start_y = int((text_hit.y1 + text_hit.y2) / 2)
        mid_y = int((sum_box.y1 + sum_box.y2) / 2)
        end_x = int(sum_box.x2) + 4
        self._on_canvas_drag_start(SimpleNamespace(x=start_x, y=start_y))
        self._on_canvas_drag_motion(SimpleNamespace(x=end_x, y=mid_y))
        self._on_canvas_drag_end(SimpleNamespace(x=end_x, y=mid_y))
        assert self._has_selection(), "dragging from text onto the structure should select it"
        selected_items = [
            type(segment.item).__name__ for segment in self._selection_state()[1]
        ]
        assert "SumNode" in selected_items, "the dragged-over structure should be selected"
        highlights = [
            self.canvas.coords(item)
            for item in self.canvas.find_all()
            if self.canvas.type(item) == "rectangle"
            and self.canvas.itemcget(item, "fill") == SELECTION_FILL
        ]
        expected_bounds = (sum_box.x1, sum_box.y1, sum_box.x2, sum_box.y2)
        assert any(
            all(
                abs(actual - expected) <= 1.0
                for actual, expected in zip(rect, expected_bounds)
            )
            for rect in highlights
        ), "selection highlight should match the structure bounds exactly"
        self._on_backspace()
        assert self._latex() == "", "deleting a selection should clear it"

        # 在分式分子（微分 dx^2/dx 的上方）里拖选：只要指针还留在这一行，
        # 焦点就不能跳到整个分式上，否则会把下面的 x 也一起选中。
        self.clear_formula()
        self.insert_template("derivative")
        self._insert_text("x^2")
        self._move_selection(1)
        self._insert_text("x")
        self._render()
        derivative = self.root_slot.items[1]
        numerator_text = derivative.numerator.items[1]
        numerator_hit = next(
            hit
            for hit in self._hit_areas
            if hit.kind == "text"
            and hit.slot is derivative.numerator
            and hit.index == 1
        )
        drag_y = int((numerator_hit.y1 + numerator_hit.y2) / 2)
        start_x = int(numerator_hit.char_positions[0]) + 2
        end_x = int(numerator_hit.char_positions[-1]) + 8
        self._on_canvas_drag_start(SimpleNamespace(x=start_x, y=drag_y))
        self._on_canvas_drag_motion(SimpleNamespace(x=end_x, y=drag_y))
        self._on_canvas_drag_end(SimpleNamespace(x=end_x, y=drag_y))
        selected_items = [segment.item for segment in self._selection_state()[1]]
        assert selected_items == [numerator_text], (
            "dragging inside one row must not select the other row of the fraction",
            [type(item).__name__ for item in selected_items],
        )
        self._collapse_selection()


    def _smoke_empty_box_and_highlights(self) -> None:
        # 空方框不是内容：在它上面拖动不产生选择；在格位最前方按回格时
        # 按「删除整个算符并用该格位内容替换」处理，空方框本身不会单独留下。
        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._render()
        empty_box = next(
            hit
            for hit in self._hit_areas
            if hit.kind == "placeholder"
            and hit.slot is self.root_slot.items[1].denominator
        )
        box_x = int((empty_box.x1 + empty_box.x2) / 2)
        box_y = int((empty_box.y1 + empty_box.y2) / 2)
        self._on_canvas_drag_start(SimpleNamespace(x=box_x, y=box_y))
        self._on_canvas_drag_motion(SimpleNamespace(x=box_x + 40, y=box_y))
        self._on_canvas_drag_end(SimpleNamespace(x=box_x + 40, y=box_y))
        assert not self._has_selection(), (
            "dragging on an empty box must not create a selection"
        )
        # 重新点空方框，再按回格：整个分式删除，用该格位（空）的内容替换。
        self._on_canvas_drag_start(SimpleNamespace(x=box_x, y=box_y))
        self._on_canvas_drag_end(SimpleNamespace(x=box_x, y=box_y))
        self._on_backspace()
        assert self._latex() == "", self._latex()

        # 选中整个结构时，结构内部的方框也要用选中底色，不能被方框颜色盖住。
        self.clear_formula()
        self.insert_template("fraction")
        self._insert_text("a")
        self._render()
        fraction_hit = next(
            hit
            for hit in self._hit_areas
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
        assert box_fills.count(SELECTION_FILL) >= 2, (
            "selected structure boxes should use the selection color"
        )
        self._on_canvas_drag_end(SimpleNamespace(x=5, y=5))
        self._collapse_selection()
