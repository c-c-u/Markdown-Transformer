# -*- coding: utf-8 -*-
"""内置冒烟测试。"""
from __future__ import annotations

from .model import count_placeholders, normalize_formula, serialize_slot


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

        self.clear_formula()
        self.insert_matrix(1, 2)
        first_cell = self.active_slot
        self._move_caret(1)
        assert self.active_slot is not first_cell, "right arrow should cross to the next input box"
        self._move_caret(-1)
        assert self.active_slot is first_cell, "left arrow should cross back"
        print("SMOKE TEST PASSED")
        print(result)

