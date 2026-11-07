# -*- coding: utf-8 -*-
"""全局常量、主题色、符号表和模板名称。"""

APP_TITLE = "公式编辑器 · Markdown 实时输出"
PLACEHOLDER = "□"

TEMPLATE_LABELS = {
    "sum": "求和",
    "integral": "积分",
    "derivative": "微分",
    "fraction": "分式",
    "power": "乘方",
    "sqrt": "开方",
    "nth_root": "n 次根",
}

# 单符号运算符：画布显示 Unicode 字形，导出时替换为对应的 LaTeX 命令。
SYMBOL_LATEX = {
    "·": r"\cdot ",
    "×": r"\times ",
    "±": r"\pm ",
    "∓": r"\mp ",
    "÷": r"\div ",
    "≤": r"\leq ",
    "≥": r"\geq ",
    "≠": r"\neq ",
    "≈": r"\approx ",
    "≡": r"\equiv ",
    "∝": r"\propto ",
    "∞": r"\infty ",
    "∂": r"\partial ",
    "∇": r"\nabla ",
    "∈": r"\in ",
    "∉": r"\notin ",
    "⊂": r"\subset ",
    "⊆": r"\subseteq ",
    "⊃": r"\supset ",
    "⊇": r"\supseteq ",
    "∪": r"\cup ",
    "∩": r"\cap ",
    "∖": r"\setminus ",
    "∅": r"\emptyset ",
    "∧": r"\wedge ",
    "∨": r"\vee ",
    "¬": r"\neg ",
    "∀": r"\forall ",
    "∃": r"\exists ",
    "→": r"\to ",
    "⇒": r"\Rightarrow ",
    "⇔": r"\Leftrightarrow ",
    "∘": r"\circ ",
    "⊥": r"\perp ",
    "∥": r"\parallel ",
    "≅": r"\cong ",
    "≪": r"\ll ",
    "≫": r"\gg ",
}

PRIMARY_SYMBOLS = ("·", "×", "±", "∓", "≤", "≥", "≠", "∞", "∂", "∇")
MORE_SYMBOLS = (
    "÷",
    "≈",
    "≡",
    "∝",
    "∈",
    "∉",
    "⊂",
    "⊆",
    "⊃",
    "⊇",
    "∪",
    "∩",
    "∖",
    "∅",
    "∧",
    "∨",
    "¬",
    "∀",
    "∃",
    "→",
    "⇒",
    "⇔",
    "∘",
    "⊥",
    "∥",
    "≅",
    "≪",
    "≫",
)


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
MIN_CANVAS_HEIGHT = 120
MAX_CANVAS_HEIGHT = 320
CANVAS_PADDING = 28

