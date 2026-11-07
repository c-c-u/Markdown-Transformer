# -*- coding: utf-8 -*-
"""Tkinter 界面构建：窗口、主题、工具栏、菜单、输出区和状态栏。"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from .config import (
    ACCENT,
    ACCENT_DARK,
    APP_TITLE,
    AUTO_FIT_SIZES,
    BASE_FONT_SIZE,
    BG,
    BORDER,
    CANVAS_BG,
    CANVAS_PADDING,
    CARD,
    DANGER,
    EDITOR_BG,
    ITEM_GAP,
    MAX_CANVAS_HEIGHT,
    MIN_CANVAS_HEIGHT,
    MORE_SYMBOLS,
    MUTED,
    PLACEHOLDER,
    PLACEHOLDER_FILL,
    PLACEHOLDER_OUTLINE,
    PREVIEW_BG,
    PRIMARY_SYMBOLS,
    SOFT_ACCENT,
    SUCCESS,
    SYMBOL_LATEX,
    TEMPLATE_LABELS,
    TEXT,
    WARNING,
)


class UIBuilderMixin:
    """构建主窗口及全部控件；事件处理由主应用提供。"""

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
            padding=(9, 6),
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
            padding=(8, 5),
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

        style.configure(
            "Tool.TMenubutton",
            font=(self.ui_font, 10),
            padding=(8, 6),
            background="#f8faff",
            foreground=TEXT,
            borderwidth=1,
            bordercolor=BORDER,
            lightcolor="#f8faff",
            darkcolor="#f8faff",
            relief="flat",
        )
        style.map(
            "Tool.TMenubutton",
            background=[("pressed", "#e6e9f5"), ("active", "#eef2ff")],
            foreground=[("active", ACCENT), ("disabled", "#9ca3af")],
            bordercolor=[("active", "#c7d2fe")],
            lightcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
            darkcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
        )

        style.configure(
            "Symbol.TButton",
            font=(self.symbol_font, 12),
            padding=(7, 3),
            background="#fbfcff",
            foreground=TEXT,
            borderwidth=1,
            bordercolor=BORDER,
            lightcolor="#fbfcff",
            darkcolor="#fbfcff",
            relief="flat",
        )
        style.map(
            "Symbol.TButton",
            background=[("pressed", "#e6e9f5"), ("active", "#eef2ff")],
            foreground=[("active", ACCENT)],
            bordercolor=[("active", "#c7d2fe")],
            lightcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
            darkcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
        )

        style.configure(
            "SymbolMore.TMenubutton",
            font=(self.ui_font, 9),
            padding=(8, 5),
            background="#fbfcff",
            foreground=MUTED,
            borderwidth=1,
            bordercolor=BORDER,
            lightcolor="#fbfcff",
            darkcolor="#fbfcff",
            relief="flat",
        )
        style.map(
            "SymbolMore.TMenubutton",
            background=[("pressed", "#e6e9f5"), ("active", "#eef2ff")],
            foreground=[("active", ACCENT)],
            bordercolor=[("active", "#c7d2fe")],
            lightcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
            darkcolor=[("active", "#eef2ff"), ("pressed", "#e6e9f5")],
        )


    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(24, 18))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=0, minsize=0)
        outer.rowconfigure(3, weight=1, minsize=200)

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
            text="结构两侧空位不显示方框；←/→ 切换输入位置",
            style="CardMuted.TLabel",
        ).grid(row=0, column=1, sticky="e")

        toolbar = ttk.Frame(body, style="Card.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        structure_row = ttk.Frame(toolbar, style="Card.TFrame")
        structure_row.pack(fill="x")

        for key, text in (
            ("sum", "∑ 求和"),
            ("integral", "∫ 积分"),
            ("derivative", "d/dx 微分"),
            ("fraction", "a/b 分式"),
            ("power", "xⁿ 乘方"),
        ):
            button = ttk.Button(
                structure_row,
                text=text,
                width=0,
                style="Tool.TButton",
                command=lambda k=key: self.insert_template(k),
            )
            button.pack(side="left", padx=(0, 6))
            button.configure(cursor="hand2")

        self._make_menu_button(
            structure_row,
            "√ 开方",
            (
                ("平方根  √", lambda: self.insert_template("sqrt")),
                ("n 次根  ⁿ√", lambda: self.insert_template("nth_root")),
            ),
        )
        self._make_menu_button(
            structure_row,
            "矩阵",
            (
                ("2 × 2 矩阵", lambda: self.insert_matrix(2, 2)),
                ("3 × 3 矩阵", lambda: self.insert_matrix(3, 3)),
                ("2 × 3 矩阵", lambda: self.insert_matrix(2, 3)),
                ("3 × 2 矩阵", lambda: self.insert_matrix(3, 2)),
            ),
        )
        self._make_menu_button(
            structure_row,
            "向量",
            (
                ("2 × 1 列向量", lambda: self.insert_matrix(2, 1, kind="vector")),
                ("3 × 1 列向量", lambda: self.insert_matrix(3, 1, kind="vector")),
                ("1 × 2 行向量", lambda: self.insert_matrix(1, 2, kind="vector")),
                ("1 × 3 行向量", lambda: self.insert_matrix(1, 3, kind="vector")),
            ),
        )

        ttk.Separator(structure_row, orient="vertical").pack(side="left", fill="y", padx=(3, 8), pady=3)

        clear_button = ttk.Button(
            structure_row,
            text="清空",
            width=0,
            style="Ghost.TButton",
            command=self.clear_formula,
        )
        clear_button.pack(side="right", padx=(6, 0))
        clear_button.configure(cursor="hand2")

        undo_button = ttk.Button(
            structure_row,
            text="撤销",
            width=0,
            style="Ghost.TButton",
            command=self.undo,
        )
        undo_button.pack(side="right")
        undo_button.configure(cursor="hand2")

        symbol_row = ttk.Frame(toolbar, style="Card.TFrame")
        symbol_row.pack(fill="x", pady=(6, 0))
        ttk.Label(symbol_row, text="运算符", style="CardMuted.TLabel").pack(side="left", padx=(2, 7))

        for glyph in PRIMARY_SYMBOLS:
            button = ttk.Button(
                symbol_row,
                text=glyph,
                width=0,
                style="Symbol.TButton",
                command=lambda g=glyph: self.insert_symbol(g),
            )
            button.pack(side="left", padx=(0, 3))
            button.configure(cursor="hand2")

        ttk.Separator(symbol_row, orient="vertical").pack(side="left", fill="y", padx=(4, 6), pady=2)
        self._make_menu_button(
            symbol_row,
            "更多符号",
            tuple((glyph, lambda g=glyph: self.insert_symbol(g)) for glyph in MORE_SYMBOLS),
            style="SymbolMore.TMenubutton",
            padx=(0, 0),
            menu_font=(self.symbol_font, 12),
        )

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
            height=MIN_CANVAS_HEIGHT,
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
        self.canvas.bind("<Return>", lambda event: (self.copy_markdown(), "break")[1])
        self.canvas.bind("<KP_Enter>", lambda event: (self.copy_markdown(), "break")[1])
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
            text="←/→ 切换输入位置 · Backspace 删除 · Enter 复制",
            bg=CARD,
            fg="#9ca3af",
            font=(self.ui_font, 9),
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))


    def _make_menu_button(
        self,
        parent: ttk.Frame,
        text: str,
        items,
        style: str = "Tool.TMenubutton",
        padx: tuple[int, int] = (0, 7),
        menu_font: Optional[tuple] = None,
    ) -> ttk.Menubutton:
        menu = tk.Menu(parent, tearoff=0, font=menu_font or (self.ui_font, 10))
        for label, command in items:
            menu.add_command(label=label, command=command)
        button = ttk.Menubutton(parent, text=text, width=0, style=style, menu=menu)
        button.pack(side="left", padx=padx)
        button.configure(cursor="hand2")
        return button


    def _build_action_row(self, parent: ttk.Frame, row: int) -> None:
        bar = ttk.Frame(parent, style="App.TFrame")
        bar.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        bar.columnconfigure(0, weight=1)

        ttk.Label(
            bar,
            text="Markdown 源码与渲染预览会随公式实时更新；填满所有方框后即可复制。",
            style="Sub.TLabel",
        ).grid(row=0, column=0, sticky="w")

        self.copy_button = ttk.Button(
            bar,
            text="复制 Markdown",
            style="Accent.TButton",
            command=self.copy_markdown,
            state=["disabled"],
        )
        self.copy_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.copy_button.configure(cursor="hand2")


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
            text="源码与预览实时同步",
            style="CardMuted.TLabel",
        ).grid(row=0, column=1, sticky="e")

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
        ttk.Label(preview_pane, text="实时预览", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")

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

