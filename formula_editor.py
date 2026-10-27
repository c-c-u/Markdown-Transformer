# -*- coding: utf-8 -*-
"""公式编辑器（可视化编辑版）。

直接在公式预览中点击黄色方框输入字符，使用工具栏插入求和、积分、微分模板；
公式会实时排版到画布中。导出时生成 Markdown 块级公式，并在输出区同时展示
Markdown 源码和渲染预览。

运行：
    python formula_editor.py

环境：transcript conda 环境（Python 3.12 + Tkinter + matplotlib + Pillow）。
"""

from __future__ import annotations

import argparse
import ctypes
import io
import os
import sys
import tkinter as tk
from copy import deepcopy
from dataclasses import dataclass, field
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Optional, Union

import matplotlib

matplotlib.use("Agg")

from matplotlib import rcParams
from matplotlib.figure import Figure
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

APP_TITLE = "公式编辑器 · Markdown 导出"
PLACEHOLDER = "□"

TEMPLATE_LABELS = {
    "sum": "求和",
    "integral": "积分",
    "derivative": "微分",
}

BG = "#f3f5fb"
CARD = "#ffffff"
BORDER = "#dfe4f1"
TEXT = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#4f46e5"
ACCENT_DARK = "#4338ca"
SUCCESS = "#15803d"
WARNING = "#b45309"
DANGER = "#b91c1c"
SOFT_ACCENT = "#eef2ff"
CANVAS_BG = "#fcfcff"
PREVIEW_BG = "#fcfcff"
EDITOR_BG = "#fbfcff"
PLACEHOLDER_FILL = "#fff7dd"
PLACEHOLDER_OUTLINE = "#d99a2b"

BASE_FONT_SIZE = 28
AUTO_FIT_SIZES = (28, 26, 24, 22, 20, 18, 16, 14, 12)
ITEM_GAP = 4

rcParams["mathtext.fontset"] = "stix"
rcParams["font.family"] = "STIXGeneral"
rcParams["text.usetex"] = False


# ---------------------------------------------------------------------------
# 公式树模型
# ---------------------------------------------------------------------------


@dataclass
class Slot:
    """一段可编辑的行，按顺序放置文本、方框和公式结构。"""

    items: list["Element"] = field(default_factory=list)
    role: str = "公式"


@dataclass
class TextRun:
    text: str = ""
    upright: bool = False
    editable: bool = True


@dataclass
class Placeholder:
    """公式结构中的空方框。"""


@dataclass
class SumNode:
    lower: Slot
    upper: Slot
    body: Slot


@dataclass
class IntegralNode:
    lower: Slot
    upper: Slot
    body: Slot
    var: Slot


@dataclass
class FractionNode:
    numerator: Slot
    denominator: Slot


Element = Union[TextRun, Placeholder, SumNode, IntegralNode, FractionNode]


def new_slot(role: str) -> Slot:
    return Slot([Placeholder()], role=role)


def make_sum_node() -> SumNode:
    return SumNode(
        lower=new_slot("求和下限"),
        upper=new_slot("求和上限"),
        body=new_slot("求和项"),
    )


def make_integral_node() -> IntegralNode:
    return IntegralNode(
        lower=new_slot("积分下限"),
        upper=new_slot("积分上限"),
        body=new_slot("被积函数"),
        var=new_slot("积分变量"),
    )


def make_derivative_node() -> FractionNode:
    return FractionNode(
        numerator=Slot([TextRun("d", upright=True, editable=False), Placeholder()], role="微分分子"),
        denominator=Slot([TextRun("d", upright=True, editable=False), Placeholder()], role="微分分母"),
    )


def make_template(key: str) -> Element:
    if key == "sum":
        return make_sum_node()
    if key == "integral":
        return make_integral_node()
    if key == "derivative":
        return make_derivative_node()
    raise KeyError(key)


# -- 遍历 -------------------------------------------------------------------


def _iter_placeholders(slot: Slot):
    for index, item in enumerate(slot.items):
        if isinstance(item, Placeholder):
            yield slot, index, item
        elif isinstance(item, SumNode):
            yield from _iter_placeholders(item.lower)
            yield from _iter_placeholders(item.upper)
            yield from _iter_placeholders(item.body)
        elif isinstance(item, IntegralNode):
            yield from _iter_placeholders(item.lower)
            yield from _iter_placeholders(item.upper)
            yield from _iter_placeholders(item.body)
            yield from _iter_placeholders(item.var)
        elif isinstance(item, FractionNode):
            yield from _iter_placeholders(item.numerator)
            yield from _iter_placeholders(item.denominator)


def iter_placeholders(slot: Slot):
    yield from _iter_placeholders(slot)


def iter_targets(slot: Slot):
    """按阅读/填写顺序返回可点击的方框和可编辑文本。"""
    for index, item in enumerate(slot.items):
        if isinstance(item, Placeholder):
            yield slot, index, item
        elif isinstance(item, TextRun) and item.editable:
            yield slot, index, item
        elif isinstance(item, SumNode):
            yield from iter_targets(item.lower)
            yield from iter_targets(item.upper)
            yield from iter_targets(item.body)
        elif isinstance(item, IntegralNode):
            yield from iter_targets(item.lower)
            yield from iter_targets(item.upper)
            yield from iter_targets(item.body)
            yield from iter_targets(item.var)
        elif isinstance(item, FractionNode):
            yield from iter_targets(item.numerator)
            yield from iter_targets(item.denominator)


def first_target(slot: Slot):
    return next(iter_targets(slot), None)


def first_placeholder_in_node(node: Element):
    if isinstance(node, SumNode):
        slots = (node.lower, node.upper, node.body)
    elif isinstance(node, IntegralNode):
        slots = (node.lower, node.upper, node.body, node.var)
    elif isinstance(node, FractionNode):
        slots = (node.numerator, node.denominator)
    else:
        return None
    for slot in slots:
        target = first_target(slot)
        if isinstance(target[2], Placeholder):
            return target
    return None


def count_placeholders(slot: Slot) -> int:
    return sum(1 for _ in iter_placeholders(slot))


# -- LaTeX 序列化 ------------------------------------------------------------


def serialize_slot(slot: Slot) -> str:
    return "".join(serialize_item(item) for item in slot.items)


def serialize_item(item: Element) -> str:
    if isinstance(item, TextRun):
        if item.upright:
            return rf"\mathrm{{{item.text}}}"
        return item.text
    if isinstance(item, Placeholder):
        return PLACEHOLDER
    if isinstance(item, SumNode):
        return (
            rf"\sum_{{{serialize_slot(item.lower)}}}^{{{serialize_slot(item.upper)}}}"
            f" {serialize_slot(item.body)}"
        )
    if isinstance(item, IntegralNode):
        return (
            rf"\int_{{{serialize_slot(item.lower)}}}^{{{serialize_slot(item.upper)}}}"
            f" {serialize_slot(item.body)}\\,\\mathrm{{d}}{serialize_slot(item.var)}"
        )
    if isinstance(item, FractionNode):
        return rf"\frac{{{serialize_slot(item.numerator)}}}{{{serialize_slot(item.denominator)}}}"
    return ""


# -- 纯函数 ------------------------------------------------------------------


def strip_math_delimiters(source: str) -> str:
    s = source.strip()
    for left, right in (("$$", "$$"), ("$", "$"), (r"\[", r"\]"), (r"\(", r"\)")):
        if (
            len(s) > len(left) + len(right)
            and s.startswith(left)
            and s.endswith(right)
        ):
            return s[len(left) : -len(right)].strip()
    return s


def normalize_formula(source: str) -> str:
    s = source.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    s = s.replace("\t", " ")
    return strip_math_delimiters(s).strip()


def to_markdown(latex: str) -> str:
    return f"$$\n{normalize_formula(latex)}\n$$"


def format_preview_error(exc: BaseException) -> str:
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    if not lines:
        return "无法解析该公式。"
    message = lines[-1]
    if len(message) > 180:
        message = message[:177] + "..."
    return message


# -- Windows 剪贴板 ----------------------------------------------------------

_WIN_CLIPBOARD_READY = False
_WIN_USER32 = None
_WIN_KERNEL32 = None
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


def _win_clipboard_api():
    global _WIN_CLIPBOARD_READY, _WIN_USER32, _WIN_KERNEL32
    if _WIN_CLIPBOARD_READY:
        return _WIN_USER32, _WIN_KERNEL32
    if sys.platform != "win32":
        return None, None
    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL

        _WIN_USER32, _WIN_KERNEL32 = user32, kernel32
        _WIN_CLIPBOARD_READY = True
    except Exception:
        _WIN_USER32 = None
        _WIN_KERNEL32 = None
    return _WIN_USER32, _WIN_KERNEL32


def copy_text_to_clipboard(text: str) -> bool:
    """Windows 下写入系统剪贴板，关闭程序后仍可粘贴；其他平台返回 False。"""
    user32, kernel32 = _win_clipboard_api()
    if user32 is None or kernel32 is None:
        return False
    handle = None
    try:
        if not user32.OpenClipboard(None):
            return False
        try:
            if not user32.EmptyClipboard():
                return False
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
            if not handle:
                return False
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                kernel32.GlobalFree(handle)
                handle = None
                return False
            try:
                ctypes.memmove(pointer, data, len(data))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
                return False
            handle = None
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False
    finally:
        if handle:
            kernel32.GlobalFree(handle)


# ---------------------------------------------------------------------------
# 画布布局数据结构
# ---------------------------------------------------------------------------


@dataclass
class DrawText:
    x: float
    y: float
    text: str
    font: tkfont.Font
    fill: str


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
class Layout:
    width: float
    ascent: float
    descent: float
    draws: list[DrawOp]
    hits: list[HitArea]


def shift_layout(layout: Layout, dx: float, dy: float) -> Layout:
    draws: list[DrawOp] = []
    for draw in layout.draws:
        if isinstance(draw, DrawText):
            draws.append(DrawText(draw.x + dx, draw.y + dy, draw.text, draw.font, draw.fill))
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
    return Layout(layout.width, layout.ascent, layout.descent, draws, hits)


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------


class FormulaEditorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.minsize(880, 780)
        self._place_window()

        self.root_slot = Slot([Placeholder()], role="公式")
        self.active_slot: Optional[Slot] = self.root_slot
        self.active_index: int = 0
        self.caret: int = 0

        self._undo_stack: list[Slot] = []
        self._redo_stack: list[Slot] = []

        self._canvas_job: Optional[str] = None
        self._output_job: Optional[str] = None
        self._output_resize_job: Optional[str] = None
        self._canvas_size = (0, 0)
        self._hit_areas: list[HitArea] = []
        self._font_cache: dict[tuple[str, int, bool], tkfont.Font] = {}
        self._base_size = BASE_FONT_SIZE

        self._output_preview_pil: Optional[Image.Image] = None
        self._output_preview_photo: Optional[ImageTk.PhotoImage] = None
        self._output_preview_error = ""
        self._last_export = ""
        self._last_cursor = "arrow"

        self._pick_fonts()
        self._configure_style()
        self._build_ui()
        self._set_window_icon()
        self._bind_shortcuts()

        self._set_status("就绪：点击公式中的黄色方框输入，或用按钮插入模板。", "muted")
        self._update_canvas_status()
        self._canvas_job = self.root.after(60, self._render_canvas)
        self._output_job = self.root.after(200, self._update_output_preview)
        self.root.after(150, self.canvas.focus_set)

    # -- 初始化 ------------------------------------------------------------

    def _place_window(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(1060, max(880, screen_w - 120))
        height = min(950, max(700, screen_h - 90))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 18)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _pick_fonts(self) -> None:
        families = set(tkfont.families(self.root))

        def first_available(*names: str) -> str:
            for name in names:
                if name in families:
                    return name
            return "TkDefaultFont"

        self.ui_font = first_available("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")
        self.mono_font = first_available("Cascadia Code", "Consolas", "Courier New")
        self.math_font = first_available("Cambria", "Times New Roman", "Georgia", "DejaVu Serif")
        self.symbol_font = first_available(
            "Segoe UI Symbol", "Cambria Math", "Arial Unicode MS", "Arial"
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".",
            background=BG,
            foreground=TEXT,
            font=(self.ui_font, 10),
            focuscolor=ACCENT,
        )
        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)

        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=(self.ui_font, 21, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=(self.ui_font, 10))
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=(self.ui_font, 12, "bold"))
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=(self.ui_font, 10))
        style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=(self.ui_font, 9))
        style.configure("Badge.TLabel", background=SOFT_ACCENT, foreground=ACCENT, font=(self.ui_font, 9, "bold"))

        style.configure(
            "Tool.TButton",
            font=(self.ui_font, 10),
            padding=(13, 8),
            background="#f8faff",
            foreground=TEXT,
            borderwidth=1,
            bordercolor=BORDER,
            lightcolor="#f8faff",
            darkcolor="#f8faff",
            relief="flat",
        )
        style.map(
            "Tool.TButton",
            background=[("pressed", "#e6e9f5"), ("active", "#eef2ff")],
            foreground=[("active", ACCENT), ("disabled", "#9ca3af")],
            bordercolor=[("active", "#c7d2fe"), ("disabled", "#e5e7eb")],
            lightcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
            darkcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
        )

        style.configure(
            "Accent.TButton",
            font=(self.ui_font, 10, "bold"),
            padding=(20, 10),
            background=ACCENT,
            foreground="#ffffff",
            borderwidth=0,
            bordercolor=ACCENT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            relief="flat",
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", "#3730a3"), ("active", ACCENT_DARK)],
            foreground=[("disabled", "#e5e7eb")],
            lightcolor=[("pressed", "#3730a3"), ("active", ACCENT_DARK)],
            darkcolor=[("pressed", "#3730a3"), ("active", ACCENT_DARK)],
        )

        style.configure(
            "Ghost.TButton",
            font=(self.ui_font, 9),
            padding=(10, 7),
            background=CARD,
            foreground=MUTED,
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Ghost.TButton",
            background=[("pressed", "#eef2ff"), ("active", "#f5f7ff")],
            foreground=[("active", ACCENT)],
        )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(24, 18))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=4, minsize=300)
        outer.rowconfigure(3, weight=4, minsize=260)

        self._build_header(outer)
        self._build_editor_card(outer, row=1)
        self._build_action_row(outer, row=2)
        self._build_output_card(outer, row=3)
        self._build_status_bar(outer, row=4)

    def _new_card(self, parent: ttk.Frame, row: int, pady: tuple[int, int]) -> ttk.Frame:
        border = tk.Frame(parent, bg=BORDER, bd=0, highlightthickness=0)
        border.grid(row=row, column=0, sticky="nsew", pady=pady)
        body = ttk.Frame(border, style="Card.TFrame", padding=(18, 15))
        body.pack(fill="both", expand=True, padx=1, pady=1)
        return body

    def _build_header(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew")

        left = ttk.Frame(header, style="App.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="公式编辑器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="点击方框直接输入 · 插入模板 · Markdown 源码与预览",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        badge = ttk.Label(
            header,
            text="可视化编辑  →  Markdown",
            style="Badge.TLabel",
            padding=(12, 6),
        )
        badge.pack(side="right", anchor="n", pady=(4, 0))

    def _build_editor_card(self, parent: ttk.Frame, row: int) -> None:
        body = self._new_card(parent, row, (14, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        head = ttk.Frame(body, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="公式编辑 · 实时预览", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            head,
            text="画布即实时预览：点击黄色方框后直接键入数字/字母",
            style="CardMuted.TLabel",
        ).grid(row=0, column=1, sticky="e")

        toolbar = ttk.Frame(body, style="Card.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        for key, text in (
            ("sum", "∑   求和"),
            ("integral", "∫   积分"),
            ("derivative", "d/dx   微分"),
        ):
            button = ttk.Button(
                toolbar,
                text=text,
                style="Tool.TButton",
                command=lambda k=key: self.insert_template(k),
            )
            button.pack(side="left", padx=(0, 8))
            button.configure(cursor="hand2")

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=(3, 10), pady=3)

        clear_button = ttk.Button(toolbar, text="清空", style="Ghost.TButton", command=self.clear_formula)
        clear_button.pack(side="right", padx=(8, 0))
        clear_button.configure(cursor="hand2")

        undo_button = ttk.Button(toolbar, text="撤销", style="Ghost.TButton", command=self.undo)
        undo_button.pack(side="right")
        undo_button.configure(cursor="hand2")

        canvas_shell = tk.Frame(body, bg=BORDER, bd=0)
        canvas_shell.grid(row=2, column=0, sticky="nsew", pady=(10, 0))

        canvas_inner = tk.Frame(canvas_shell, bg=CANVAS_BG, padx=1, pady=1)
        canvas_inner.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            canvas_inner,
            bg=CANVAS_BG,
            highlightthickness=0,
            bd=0,
            takefocus=True,
            cursor="arrow",
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<Key>", self._on_canvas_key)
        self.canvas.bind("<BackSpace>", self._on_backspace)
        self.canvas.bind("<Delete>", self._on_delete)
        self.canvas.bind("<Tab>", lambda event: self._move_selection(1))
        self.canvas.bind("<Shift-Tab>", lambda event: self._move_selection(-1))
        self.canvas.bind("<ISO_Left_Tab>", lambda event: self._move_selection(-1))
        self.canvas.bind("<Left>", lambda event: self._move_caret(-1))
        self.canvas.bind("<Right>", lambda event: self._move_caret(1))
        self.canvas.bind("<Return>", lambda event: (self.export_markdown(), "break")[1])
        self.canvas.bind("<KP_Enter>", lambda event: (self.export_markdown(), "break")[1])
        self.canvas.bind("<Control-v>", self._paste_formula)
        self.canvas.bind("<Control-V>", self._paste_formula)
        self.canvas.bind("<Control-z>", lambda event: self.undo())
        self.canvas.bind("<Control-Z>", lambda event: self.undo())
        self.canvas.bind("<Control-y>", lambda event: self.redo())
        self.canvas.bind("<Control-Y>", lambda event: self.redo())

        footer = ttk.Frame(body, style="Card.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)

        self.canvas_status = tk.Label(
            footer,
            text="",
            bg=CARD,
            fg=MUTED,
            font=(self.ui_font, 9),
            anchor="w",
        )
        self.canvas_status.grid(row=0, column=0, sticky="ew")

        tk.Label(
            footer,
            text="Tab 切换方框 · Backspace 删除 · Ctrl+Z 撤销 · Enter 导出",
            bg=CARD,
            fg="#9ca3af",
            font=(self.ui_font, 9),
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))

    def _build_action_row(self, parent: ttk.Frame, row: int) -> None:
        bar = ttk.Frame(parent, style="App.TFrame")
        bar.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        bar.columnconfigure(0, weight=1)

        ttk.Label(
            bar,
            text="导出后，左侧显示 Markdown 源码，右侧同步显示渲染预览。",
            style="Sub.TLabel",
        ).grid(row=0, column=0, sticky="w")

        self.export_button = ttk.Button(
            bar,
            text="导出 Markdown",
            style="Accent.TButton",
            command=self.export_markdown,
        )
        self.export_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.export_button.configure(cursor="hand2")

    def _build_output_card(self, parent: ttk.Frame, row: int) -> None:
        body = self._new_card(parent, row, (14, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        head = ttk.Frame(body, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Markdown 输出", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            head,
            text="源码可直接复制；预览随公式自动更新",
            style="CardMuted.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(0, 10))

        self.copy_button = ttk.Button(
            head,
            text="复制",
            style="Tool.TButton",
            command=self.copy_markdown,
            state=["disabled"],
        )
        self.copy_button.grid(row=0, column=2, sticky="e")
        self.copy_button.configure(cursor="hand2")

        content = ttk.Frame(body, style="Card.TFrame")
        content.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        # 左侧：Markdown 源码
        code_pane = ttk.Frame(content, style="Card.TFrame")
        code_pane.grid(row=0, column=0, sticky="nsew")
        code_pane.columnconfigure(0, weight=1)
        code_pane.rowconfigure(1, weight=1)
        ttk.Label(code_pane, text="Markdown 源码", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")

        code_shell = tk.Frame(code_pane, bg=BORDER, bd=0)
        code_shell.grid(row=1, column=0, sticky="nsew", pady=(5, 0))

        code_inner = tk.Frame(code_shell, bg=CARD, padx=1, pady=1)
        code_inner.pack(fill="both", expand=True)

        self.output = tk.Text(
            code_inner,
            width=1,
            height=4,
            wrap="word",
            font=(self.mono_font, 11),
            bg=EDITOR_BG,
            fg="#111827",
            selectbackground="#c7d2fe",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=9,
            cursor="arrow",
        )
        self.output.pack(side="left", fill="both", expand=True)
        self.output.configure(state="disabled")

        v_scroll = ttk.Scrollbar(code_inner, orient="vertical", command=self.output.yview)
        v_scroll.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=v_scroll.set)
        self.output.bind("<Control-a>", self._select_all_output)
        self.output.bind("<Control-A>", self._select_all_output)

        # 右侧：公式渲染预览
        preview_pane = ttk.Frame(content, style="Card.TFrame")
        preview_pane.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        preview_pane.columnconfigure(0, weight=1)
        preview_pane.rowconfigure(1, weight=1)
        ttk.Label(preview_pane, text="导出预览", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")

        preview_shell = tk.Frame(preview_pane, bg=BORDER, bd=0)
        preview_shell.grid(row=1, column=0, sticky="nsew", pady=(5, 0))

        self.output_preview_canvas = tk.Canvas(
            preview_shell,
            bg=PREVIEW_BG,
            highlightthickness=0,
            bd=0,
            width=10,
            height=10,
        )
        self.output_preview_canvas.pack(fill="both", expand=True, padx=1, pady=1)
        self.output_preview_canvas.bind("<Configure>", self._on_output_preview_configure)
        self._output_preview_message = "填写全部方框后\n这里显示渲染预览"

    def _build_status_bar(self, parent: ttk.Frame, row: int) -> None:
        bar = ttk.Frame(parent, style="App.TFrame")
        bar.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        bar.columnconfigure(0, weight=1)

        self.status_label = tk.Label(
            bar,
            text="",
            bg=BG,
            fg=MUTED,
            font=(self.ui_font, 9),
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew")

        env_name = os.path.basename(sys.prefix.rstrip("\\/")) or "Python"
        tk.Label(
            bar,
            text=f"{env_name} 环境 · Python {sys.version_info.major}.{sys.version_info.minor}",
            bg=BG,
            fg="#9ca3af",
            font=(self.ui_font, 9),
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))

    def _set_window_icon(self) -> None:
        try:
            size = 64
            image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((2, 2, size - 2, size - 2), radius=14, fill=ACCENT)
            font_path = r"C:\Windows\Fonts\seguisym.ttf"
            if not os.path.exists(font_path):
                font_path = r"C:\Windows\Fonts\segoeuib.ttf"
            try:
                icon_font = ImageFont.truetype(font_path, 40)
            except OSError:
                icon_font = ImageFont.load_default()
            draw.text((size / 2, size / 2 - 2), "∑", fill="white", font=icon_font, anchor="mm")
            self._icon_photo = ImageTk.PhotoImage(image)
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            self._icon_photo = None

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-z>", lambda event: self.undo())
        self.root.bind("<Control-Z>", lambda event: self.undo())
        self.root.bind("<Control-y>", lambda event: self.redo())
        self.root.bind("<Control-Y>", lambda event: self.redo())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- 字体与绘制 --------------------------------------------------------

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
        italic = (not upright) and char.isalpha()
        return self._font(size, italic=italic)

    def _measure(self, font: tkfont.Font, text: str = "x") -> tuple[float, float, float]:
        return float(font.measure(text)), float(font.metrics("ascent")), float(font.metrics("descent"))

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
        if isinstance(item, SumNode):
            return self._layout_sum(item, x, baseline, size)
        if isinstance(item, IntegralNode):
            return self._layout_integral(item, x, baseline, size)
        if isinstance(item, FractionNode):
            return self._layout_fraction(item, x, baseline, size)
        return Layout(0, 0, 0, [], [])

    def _layout_slot(self, slot: Slot, x: float, baseline: float, size: float) -> Layout:
        draws: list[DrawOp] = []
        hits: list[HitArea] = []
        cursor = x
        ascent = 0.0
        descent = 0.0
        count = len(slot.items)

        for index, item in enumerate(slot.items):
            child = self._layout_item(item, slot, index, cursor, baseline, size)
            draws.extend(child.draws)
            hits.extend(child.hits)
            ascent = max(ascent, child.ascent)
            descent = max(descent, child.descent)
            cursor += child.width
            if index < count - 1:
                cursor += ITEM_GAP

        return Layout(cursor - x, ascent, descent, draws, hits)

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
            return Layout(0, 0, 0, [], [])

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
            and isinstance(item, TextRun)
        )
        y1 = baseline - ascent - 3
        y2 = baseline + descent + 3

        if active:
            background = DrawRect(x - 3, y1, cursor + 3, y2, SOFT_ACCENT, "", 0, ())
            draws.insert(0, background)
            caret = max(0, min(self.caret, len(text)))
            cx = caret_positions[caret]
            draws.append(DrawLine(cx, y1 + 2, cx, y2 - 2, ACCENT, 1.6))

        hits: list[HitArea] = []
        if item.editable:
            hits.append(
                HitArea(slot, index, x - 2, y1, cursor + 2, y2, caret_positions, "text")
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
        box_width = max(26.0, float(font.measure("0")) * 2.3)
        top = baseline - ascent - 4
        bottom = baseline + descent + 4
        active = slot is self.active_slot and index == self.active_index

        if active:
            fill = SOFT_ACCENT
            outline = ACCENT
            border_width = 2.0
            dash: tuple[int, ...] = ()
        else:
            fill = PLACEHOLDER_FILL
            outline = PLACEHOLDER_OUTLINE
            border_width = 1.4
            dash = (4, 2)

        draws: list[DrawOp] = [
            DrawRect(x, top, x + box_width, bottom, fill, outline, border_width, dash)
        ]
        if active:
            draws.append(DrawLine(x + 8, top + 6, x + 8, bottom - 6, ACCENT, 1.6))

        hits = [HitArea(slot, index, x, top, x + box_width, bottom, None, "placeholder")]
        return Layout(box_width, ascent + 4, descent + 4, draws, hits)

    def _layout_sum(self, node: SumNode, x: float, baseline: float, size: float) -> Layout:
        limit_size = max(12.0, size * 0.68)
        upper = self._layout_slot(node.upper, 0.0, 0.0, limit_size)
        lower = self._layout_slot(node.lower, 0.0, 0.0, limit_size)
        body = self._layout_slot(node.body, 0.0, 0.0, size)

        glyph_size = size * 1.75
        glyph_font = self._font(glyph_size, family=self.symbol_font)
        glyph_width, glyph_ascent, glyph_descent = self._measure(glyph_font, "∑")

        column_width = max(glyph_width, upper.width, lower.width)
        upper_x = x + (column_width - upper.width) / 2
        lower_x = x + (column_width - lower.width) / 2
        glyph_x = x + (column_width - glyph_width) / 2

        upper_baseline = -glyph_ascent - 4 - upper.descent
        lower_baseline = glyph_descent + 4 + lower.ascent
        body_x = x + column_width + 10

        upper_shifted = shift_layout(upper, upper_x, baseline + upper_baseline)
        lower_shifted = shift_layout(lower, lower_x, baseline + lower_baseline)
        body_shifted = shift_layout(body, body_x, baseline)

        draws: list[DrawOp] = [
            DrawText(glyph_x, baseline + glyph_descent, "∑", glyph_font, TEXT)
        ]
        draws.extend(upper_shifted.draws)
        draws.extend(lower_shifted.draws)
        draws.extend(body_shifted.draws)

        ascent = max(glyph_ascent, -upper_baseline + upper.ascent, body.ascent)
        descent = max(glyph_descent, lower_baseline + lower.descent, body.descent)
        width = column_width + 10 + body.width

        hits = upper_shifted.hits + lower_shifted.hits + body_shifted.hits
        return Layout(width, ascent, descent, draws, hits)

    def _layout_integral(self, node: IntegralNode, x: float, baseline: float, size: float) -> Layout:
        limit_size = max(11.0, size * 0.62)
        upper = self._layout_slot(node.upper, 0.0, 0.0, limit_size)
        lower = self._layout_slot(node.lower, 0.0, 0.0, limit_size)
        body = self._layout_slot(node.body, 0.0, 0.0, size)

        glyph_size = size * 2.15
        glyph_font = self._font(glyph_size, family=self.symbol_font)
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

        var_x = d_x + d_width + 2
        var = self._layout_slot(node.var, 0.0, 0.0, size)
        var_shifted = shift_layout(var, var_x, baseline)

        draws: list[DrawOp] = [
            DrawText(x, baseline + glyph_descent, "∫", glyph_font, TEXT)
        ]
        draws.extend(upper_shifted.draws)
        draws.extend(lower_shifted.draws)
        draws.extend(body_shifted.draws)
        draws.append(d_draw)
        draws.extend(var_shifted.draws)

        ascent = max(
            glyph_ascent,
            upper_baseline + upper.ascent,
            body.ascent,
            d_ascent,
            var.ascent,
        )
        descent = max(
            glyph_descent,
            lower_baseline + lower.descent,
            body.descent,
            d_descent,
            var.descent,
        )
        width = var_x + var.width - x

        hits = upper_shifted.hits + lower_shifted.hits + body_shifted.hits + var_shifted.hits
        return Layout(width, ascent, descent, draws, hits)

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

        draws: list[DrawOp] = []
        draws.extend(numerator_shifted.draws)
        draws.extend(denominator_shifted.draws)
        draws.append(
            DrawLine(x + 2, baseline, x + width - 2, baseline, TEXT, 1.4)
        )

        ascent = max(0.0, -numerator_baseline + numerator.ascent)
        descent = max(0.0, denominator_baseline + denominator.descent)
        hits = numerator_shifted.hits + denominator_shifted.hits
        return Layout(width, ascent, descent, draws, hits)

    # -- 画布渲染 ----------------------------------------------------------

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

    def _render_canvas(self) -> None:
        self._canvas_job = None
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 20 or height <= 20:
            self._canvas_job = self.root.after(50, self._render_canvas)
            return

        avail_w = width - 44
        avail_h = height - 28
        chosen_size = AUTO_FIT_SIZES[-1]
        layout: Optional[Layout] = None

        for candidate in AUTO_FIT_SIZES:
            candidate_layout = self._layout_slot(self.root_slot, 0.0, 0.0, float(candidate))
            if (
                candidate_layout.width <= avail_w
                and candidate_layout.ascent + candidate_layout.descent <= avail_h
            ):
                chosen_size = candidate
                layout = candidate_layout
                break
        if layout is None:
            chosen_size = AUTO_FIT_SIZES[-1]
            layout = self._layout_slot(self.root_slot, 0.0, 0.0, float(chosen_size))

        x_offset = (width - layout.width) / 2
        baseline_offset = (height - (layout.ascent + layout.descent)) / 2 + layout.ascent
        self.canvas.delete("all")

        for draw in layout.draws:
            if isinstance(draw, DrawText):
                self.canvas.create_text(
                    draw.x + x_offset,
                    draw.y + baseline_offset,
                    text=draw.text,
                    font=draw.font,
                    fill=draw.fill,
                    anchor="sw",
                )
            elif isinstance(draw, DrawRect):
                self.canvas.create_rectangle(
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
                self.canvas.create_line(
                    draw.x1 + x_offset,
                    draw.y1 + baseline_offset,
                    draw.x2 + x_offset,
                    draw.y2 + baseline_offset,
                    fill=draw.fill,
                    width=draw.width,
                )

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
        hit = self._find_hit(float(event.x), float(event.y))
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
                key=lambda i: abs(positions[i] - float(event.x)),
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
        hit = self._find_hit(float(event.x), float(event.y))
        cursor = "xterm" if hit else "arrow"
        if cursor != self._last_cursor:
            self._last_cursor = cursor
            self.canvas.configure(cursor=cursor)

    def _on_canvas_leave(self, _event: Optional[tk.Event] = None) -> None:
        if self._last_cursor != "arrow":
            self._last_cursor = "arrow"
            self.canvas.configure(cursor="arrow")

    # -- 编辑操作 ----------------------------------------------------------

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

    def _invalidate_output_code(self) -> None:
        if not self._last_export:
            return
        self._last_export = ""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.copy_button.state(["disabled"])
        self._set_status("公式已修改，请重新导出 Markdown。", "warning")

    def _schedule_output_preview(self, delay: int = 320) -> None:
        if self._output_job is not None:
            self.root.after_cancel(self._output_job)
        self._output_job = self.root.after(delay, self._update_output_preview)

    def _after_formula_change(self) -> None:
        self._invalidate_output_code()
        self._render_canvas()
        self._schedule_output_preview()
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
            self.active_slot.items[self.active_index] = TextRun(text)
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
                self.active_slot.items[self.active_index] = Placeholder()
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
                    self.active_slot.items[self.active_index] = Placeholder()
                    self.caret = 0
                self._after_formula_change()
        self.canvas.focus_set()
        return "break"

    def _move_caret(self, step: int) -> str:
        item = self._active_item()
        if isinstance(item, TextRun) and item.editable:
            new_caret = max(0, min(len(item.text), self.caret + step))
            if new_caret != self.caret:
                self.caret = new_caret
                self._render_canvas()
                self._update_canvas_status()
        self.canvas.focus_set()
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

    def insert_template(self, key: str) -> None:
        node = make_template(key)
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
        self._set_status(
            f"已插入{TEMPLATE_LABELS[key]}模板，依次填写方框即可。",
            "info",
        )
        self.canvas.focus_set()

    def clear_formula(self) -> None:
        if not self.root_slot.items:
            return
        self._push_undo()
        self.root_slot = Slot([Placeholder()], role="公式")
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
            message = "点击公式中的黄色方框开始输入"
        elif isinstance(item, Placeholder):
            message = f"正在编辑：{self.active_slot.role}（空方框）"
        elif isinstance(item, TextRun):
            content = item.text if item.text else "空"
            if len(content) > 24:
                content = content[:21] + "..."
            message = f"正在编辑：{self.active_slot.role} · {content}"
        else:
            message = "点击公式中的黄色方框开始输入"
        remaining = count_placeholders(self.root_slot)
        if remaining:
            message += f" · 还有 {remaining} 个方框待填写"
        else:
            message += " · 所有方框已填写，可以导出"
        self.canvas_status.configure(text=message)

    # -- 输出预览 / 导出 ---------------------------------------------------

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

    def _display_output_preview_image(self) -> None:
        self._output_resize_job = None
        if self._output_preview_pil is None:
            self._draw_output_preview_message()
            return
        canvas = self.output_preview_canvas
        width = max(100, canvas.winfo_width() - 24)
        height = max(60, canvas.winfo_height() - 20)
        image = self._output_preview_pil.copy()
        scale = min(width / image.width, height / image.height)
        if scale > 1.0:
            scale = min(scale, 1.35)
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
        self._output_resize_job = self.root.after(80, self._display_output_preview_image)

    def _update_output_preview(self) -> None:
        self._output_job = None
        placeholders = count_placeholders(self.root_slot)
        latex = normalize_formula(serialize_slot(self.root_slot))

        if placeholders:
            self._output_preview_error = ""
            self._output_preview_pil = None
            self._output_preview_photo = None
            self._output_preview_message = (
                f"还有 {placeholders} 个方框未填写\n完成全部方框后显示导出预览"
            )
            self._draw_output_preview_message()
            return

        if not latex:
            self._output_preview_error = ""
            self._output_preview_pil = None
            self._output_preview_photo = None
            self._output_preview_message = "填写公式后\n这里显示渲染预览"
            self._draw_output_preview_message()
            return

        try:
            image = self._render_latex_image(latex)
        except Exception as exc:
            self._output_preview_error = format_preview_error(exc)
            self._output_preview_pil = None
            self._output_preview_photo = None
            self._output_preview_message = "渲染预览失败\n" + self._output_preview_error
            self._draw_output_preview_message()
            return

        self._output_preview_error = ""
        self._output_preview_pil = image
        self._display_output_preview_image()

    def export_markdown(self) -> bool:
        placeholders = count_placeholders(self.root_slot)
        if placeholders:
            target = next(iter_placeholders(self.root_slot), None)
            if target is not None:
                slot, index, _item = target
                self._set_active(slot, index, 0)
            messagebox.showwarning(
                "还有方框未填写",
                f"公式中还有 {placeholders} 个方框没有填写。\n请点击方框（或按 Tab）补齐内容后再导出。",
                parent=self.root,
            )
            self._set_status(f"导出未完成：还有 {placeholders} 个方框待填写。", "warning")
            return False

        latex = normalize_formula(serialize_slot(self.root_slot))
        if not latex:
            messagebox.showwarning("还没有公式", "请先在公式中填写内容。", parent=self.root)
            self._set_status("导出未完成：公式为空。", "warning")
            self.canvas.focus_set()
            return False

        if self._output_job is not None:
            self.root.after_cancel(self._output_job)
            self._output_job = None
        self._update_output_preview()

        if self._output_preview_error:
            proceed = messagebox.askyesno(
                "公式渲染失败",
                "当前公式无法被预览渲染（可能包含 mathtext 不支持的语法）。\n仍要导出 Markdown 吗？",
                parent=self.root,
            )
            if not proceed:
                self._set_status("已取消导出。", "muted")
                return False

        markdown = to_markdown(latex)
        self._last_export = markdown
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", markdown)
        self.output.configure(state="disabled")
        self.output.see("1.0")
        self.copy_button.state(["!disabled"])
        self._set_status("Markdown 已生成；右侧为渲染预览，可点击“复制”。", "success")
        self.canvas.focus_set()
        return True

    def copy_markdown(self) -> None:
        if not self._last_export:
            return
        if not copy_text_to_clipboard(self._last_export):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(self._last_export)
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

    # -- 冒烟测试 / 退出 ---------------------------------------------------

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
        assert self.export_markdown() is True
        result = self.output.get("1.0", "end-1c")
        assert result == "$$\n" + latex + "\n$$", result
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
        print("SMOKE TEST PASSED")
        print(result)

    def _on_close(self) -> None:
        for job in (self._canvas_job, self._output_job, self._output_resize_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self.root.destroy()


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="公式编辑器：可视化编辑、预览并导出 Markdown 公式")
    parser.add_argument("--smoke-test", action="store_true", help="构建窗口并执行一轮公式编辑/导出测试后退出")
    args = parser.parse_args(argv)

    enable_dpi_awareness()
    root = tk.Tk()
    app = FormulaEditorApp(root)

    def report_callback_exception(exc_type, exc_value, exc_tb) -> None:
        import traceback

        traceback.print_exception(exc_type, exc_value, exc_tb)
        messagebox.showerror("程序错误", str(exc_value), parent=root)

    root.report_callback_exception = report_callback_exception

    if args.smoke_test:
        try:
            app.run_smoke_test()
        finally:
            root.destroy()
        return 0

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
