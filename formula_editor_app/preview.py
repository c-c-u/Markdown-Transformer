# -*- coding: utf-8 -*-
"""输出区的实时预览：matplotlib 图片预览与矩阵自绘预览。"""
from __future__ import annotations

import io
import tkinter as tk
from typing import Optional

import matplotlib

matplotlib.use("Agg")
from matplotlib import rcParams
from matplotlib.figure import Figure
from PIL import Image, ImageTk

from .config import MUTED, PREVIEW_BG, TEXT
from .layout import Layout
from .model import (
    contains_matrix,
    count_placeholders,
    format_preview_error,
    normalize_formula,
    serialize_slot,
)

rcParams["mathtext.fontset"] = "stix"
rcParams["font.family"] = "STIXGeneral"
rcParams["text.usetex"] = False


class PreviewMixin:
    """输出预览方法；与主窗口的 Canvas、状态属性配合使用。"""

    def _render_latex_image(self, latex: str) -> Image.Image:
        figure = Figure(figsize=(10, 2.6), dpi=180)
        figure.patch.set_facecolor(PREVIEW_BG)
        figure.text(
            0.5,
            0.5,
            f"${latex}$",
            ha="center",
            va="center",
            fontsize=28,
            color=TEXT,
        )
        buffer = io.BytesIO()
        figure.savefig(
            buffer,
            format="png",
            dpi=180,
            bbox_inches="tight",
            pad_inches=0.12,
            facecolor=PREVIEW_BG,
        )
        buffer.seek(0)
        image = Image.open(buffer).convert("RGB")
        buffer.close()
        return image


    def _draw_output_preview_custom(self) -> None:
        """mathtext 不支持矩阵环境，矩阵公式改用画布布局直接绘制预览。"""
        self._output_resize_job = None
        if not self._output_preview_custom:
            return
        canvas = self.output_preview_canvas
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 20 or height <= 20:
            self._output_resize_job = self.root.after(50, self._draw_output_preview_custom)
            return

        avail_w = width - 24
        avail_h = height - 18
        layout: Optional[Layout] = None
        chosen_size = 8
        saved_active_slot = self.active_slot
        saved_active_index = self.active_index
        self.active_slot = None
        try:
            for candidate in (24, 22, 20, 18, 16, 14, 12, 10, 8):
                candidate_layout = self._layout_slot(
                    self.root_slot, 0.0, 0.0, float(candidate)
                )
                if (
                    candidate_layout.width <= avail_w
                    and candidate_layout.ascent + candidate_layout.descent <= avail_h
                ):
                    layout = candidate_layout
                    chosen_size = candidate
                    break
            if layout is None:
                chosen_size = 8
                layout = self._layout_slot(self.root_slot, 0.0, 0.0, float(chosen_size))
        finally:
            self.active_slot = saved_active_slot
            self.active_index = saved_active_index

        x_offset = (width - layout.width) / 2
        baseline_offset = (height - (layout.ascent + layout.descent)) / 2 + layout.ascent
        self._paint_layout(canvas, layout, x_offset, baseline_offset)


    def _display_output_preview_image(self) -> None:
        self._output_resize_job = None
        if self._output_preview_custom:
            self._draw_output_preview_custom()
            return
        if self._output_preview_pil is None:
            self._draw_output_preview_message()
            return
        canvas = self.output_preview_canvas
        width = max(100, canvas.winfo_width() - 24)
        height = max(60, canvas.winfo_height() - 20)
        image = self._output_preview_pil.copy()
        scale = min(width / image.width, height / image.height)
        if scale > 1.0:
            scale = min(scale, 2.0)
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        else:
            image.thumbnail((width, height), Image.Resampling.LANCZOS)
        self._output_preview_photo = ImageTk.PhotoImage(image)
        canvas.delete("all")
        canvas.create_image(
            canvas.winfo_width() / 2,
            canvas.winfo_height() / 2,
            image=self._output_preview_photo,
            anchor="center",
        )


    def _draw_output_preview_message(self) -> None:
        self._output_resize_job = None
        canvas = self.output_preview_canvas
        canvas.delete("all")
        width = max(80, canvas.winfo_width())
        height = max(50, canvas.winfo_height())
        canvas.create_text(
            width / 2,
            height / 2,
            text=self._output_preview_message,
            fill=MUTED,
            font=(self.ui_font, 10),
            justify="center",
            width=max(80, width - 24),
        )


    def _on_output_preview_configure(self, _event: tk.Event) -> None:
        if self._output_resize_job is not None:
            self.root.after_cancel(self._output_resize_job)
        if self._output_preview_custom:
            callback = self._draw_output_preview_custom
        elif self._output_preview_pil is not None:
            callback = self._display_output_preview_image
        else:
            callback = self._draw_output_preview_message
        self._output_resize_job = self.root.after(80, callback)


    def _update_output_preview(self) -> None:
        self._output_job = None
        if self._output_resize_job is not None:
            self.root.after_cancel(self._output_resize_job)
            self._output_resize_job = None
        placeholders = count_placeholders(self.root_slot)
        latex = normalize_formula(serialize_slot(self.root_slot))

        if placeholders:
            self._output_preview_error = ""
            self._output_preview_custom = False
            self._output_preview_pil = None
            self._output_preview_photo = None
            self._output_preview_message = (
                f"还有 {placeholders} 个方框未填写\n完成全部方框后显示实时预览"
            )
            self._draw_output_preview_message()
            return

        if not latex:
            self._output_preview_error = ""
            self._output_preview_custom = False
            self._output_preview_pil = None
            self._output_preview_photo = None
            self._output_preview_message = "填写公式后\n这里显示渲染预览"
            self._draw_output_preview_message()
            return

        if contains_matrix(self.root_slot):
            self._output_preview_error = ""
            self._output_preview_custom = True
            self._output_preview_pil = None
            self._output_preview_photo = None
            self._draw_output_preview_custom()
            return

        try:
            image = self._render_latex_image(latex)
        except Exception as exc:
            self._output_preview_error = format_preview_error(exc)
            self._output_preview_custom = False
            self._output_preview_pil = None
            self._output_preview_photo = None
            self._output_preview_message = "渲染预览失败\n" + self._output_preview_error
            self._draw_output_preview_message()
            return

        self._output_preview_error = ""
        self._output_preview_custom = False
        self._output_preview_pil = image
        self._display_output_preview_image()

