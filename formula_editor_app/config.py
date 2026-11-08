# -*- coding: utf-8 -*-
"""全局常量、主题色、符号表和模板名称。"""

APP_TITLE = "公式编辑器 · Markdown 实时输出"
PLACEHOLDER = "□"

TEMPLATE_LABELS = {
    "sum": "求和",
    "integral": "积分",
    "derivative": "微分",
    "fraction": "分式",
    "power": "上角标",
    "subscript": "下角标",
    "sub_sup": "上下角标",
    "sqrt": "开方",
    "nth_root": "n 次根",
}

# 单符号运算符：画布显示 Unicode 字形，导出时替换为对应的 LaTeX 命令。
# LaTeX 命令一律带尾随空格，避免与后面的字母粘成一个未知命令。
SYMBOL_LATEX = {
    # -- 基本运算：四则运算与比较 -----------------------------------------
    "·": r"\cdot ",
    "×": r"\times ",
    "÷": r"\div ",
    "±": r"\pm ",
    "∓": r"\mp ",
    "≤": r"\leq ",
    "≥": r"\geq ",
    "≠": r"\neq ",
    "≈": r"\approx ",
    "≡": r"\equiv ",
    "∝": r"\propto ",
    "≅": r"\cong ",
    "≪": r"\ll ",
    "≫": r"\gg ",
    "∘": r"\circ ",
    "⊥": r"\perp ",
    "∥": r"\parallel ",
    # -- 集合 -------------------------------------------------------------
    "∈": r"\in ",
    "∉": r"\notin ",
    "∋": r"\ni ",
    "⊂": r"\subset ",
    "⊆": r"\subseteq ",
    "⊄": r"\not\subset ",
    "⊊": r"\subsetneq ",
    "⊃": r"\supset ",
    "⊇": r"\supseteq ",
    "∪": r"\cup ",
    "∩": r"\cap ",
    "∖": r"\setminus ",
    "∅": r"\emptyset ",
    "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}",
    "ℚ": r"\mathbb{Q}",
    "ℝ": r"\mathbb{R}",
    "ℂ": r"\mathbb{C}",
    # -- 微积分 -----------------------------------------------------------
    "∫": r"\int ",
    "∬": r"\iint ",
    "∭": r"\iiint ",
    "∮": r"\oint ",
    "∂": r"\partial ",
    "∇": r"\nabla ",
    "∞": r"\infty ",
    "Δ": r"\Delta ",
    "′": r"^{\prime}",
    "″": r"^{\prime\prime}",
    # -- 逻辑与箭头 -------------------------------------------------------
    "∧": r"\wedge ",
    "∨": r"\vee ",
    "¬": r"\neg ",
    "∀": r"\forall ",
    "∃": r"\exists ",
    "∴": r"\therefore ",
    "∵": r"\because ",
    "→": r"\to ",
    "←": r"\leftarrow ",
    "↔": r"\leftrightarrow ",
    "⇒": r"\Rightarrow ",
    "⇐": r"\Leftarrow ",
    "⇔": r"\Leftrightarrow ",
    # -- 变量符号：希腊字母 ----------------------------------------------
    "α": r"\alpha ",
    "β": r"\beta ",
    "γ": r"\gamma ",
    "δ": r"\delta ",
    "ε": r"\varepsilon ",
    "ζ": r"\zeta ",
    "η": r"\eta ",
    "θ": r"\theta ",
    "ι": r"\iota ",
    "κ": r"\kappa ",
    "λ": r"\lambda ",
    "μ": r"\mu ",
    "ν": r"\nu ",
    "ξ": r"\xi ",
    "π": r"\pi ",
    "ρ": r"\rho ",
    "σ": r"\sigma ",
    "τ": r"\tau ",
    "υ": r"\upsilon ",
    "φ": r"\phi ",
    "χ": r"\chi ",
    "ψ": r"\psi ",
    "ω": r"\omega ",
    "Γ": r"\Gamma ",
    "Θ": r"\Theta ",
    "Λ": r"\Lambda ",
    "Ξ": r"\Xi ",
    "Π": r"\Pi ",
    "Σ": r"\Sigma ",
    "Υ": r"\Upsilon ",
    "Φ": r"\Phi ",
    "Ψ": r"\Psi ",
    "Ω": r"\Omega ",
    # -- 标识：角度与上/下标字形 -------------------------------------------
    "°": r"^{\circ}",
    "⁰": r"^{0}",
    "¹": r"^{1}",
    "²": r"^{2}",
    "³": r"^{3}",
    "⁴": r"^{4}",
    "⁵": r"^{5}",
    "⁶": r"^{6}",
    "⁷": r"^{7}",
    "⁸": r"^{8}",
    "⁹": r"^{9}",
    "⁺": r"^{+}",
    "⁻": r"^{-}",
    "⁼": r"^{=}",
    "ⁿ": r"^{n}",
    "ⁱ": r"^{i}",
    "₀": r"_{0}",
    "₁": r"_{1}",
    "₂": r"_{2}",
    "₃": r"_{3}",
    "₄": r"_{4}",
    "₅": r"_{5}",
    "₆": r"_{6}",
    "₇": r"_{7}",
    "₈": r"_{8}",
    "₉": r"_{9}",
    "₊": r"_{+}",
    "₋": r"_{-}",
    "₌": r"_{=}",
    "ₐ": r"_{a}",
    "ₑ": r"_{e}",
    "ₒ": r"_{o}",
    "ₓ": r"_{x}",
    "ₕ": r"_{h}",
    "ₖ": r"_{k}",
    "ₗ": r"_{l}",
    "ₘ": r"_{m}",
    "ₙ": r"_{n}",
    "ₚ": r"_{p}",
    "ₛ": r"_{s}",
    "ₜ": r"_{t}",
}

# 数集符号（字母类字形，但按正体符号绘制）。
NUMBER_SET_SYMBOLS = ("ℕ", "ℤ", "ℚ", "ℝ", "ℂ")

# 「标识」分类：角度符号与 Unicode 自带的上/下标字形。
# 它们在画布上直接显示为小号字形，导出时还原成 ``^{...}`` / ``_{...}``。
SCRIPT_SUPERSCRIPT_SYMBOLS = (
    "⁰",
    "¹",
    "²",
    "³",
    "⁴",
    "⁵",
    "⁶",
    "⁷",
    "⁸",
    "⁹",
    "⁺",
    "⁻",
    "⁼",
    "ⁿ",
    "ⁱ",
)
SCRIPT_SUBSCRIPT_SYMBOLS = (
    "₀",
    "₁",
    "₂",
    "₃",
    "₄",
    "₅",
    "₆",
    "₇",
    "₈",
    "₉",
    "₊",
    "₋",
    "₌",
    "ₐ",
    "ₑ",
    "ₒ",
    "ₓ",
    "ₕ",
    "ₖ",
    "ₗ",
    "ₘ",
    "ₙ",
    "ₚ",
    "ₛ",
    "ₜ",
)
SCRIPT_SYMBOLS = ("°",) + SCRIPT_SUPERSCRIPT_SYMBOLS + SCRIPT_SUBSCRIPT_SYMBOLS

# 画布上用「符号字体」正体绘制的字符：非字母类符号 + 数集字母 + 上/下标字形。
# 拉丁字母、希腊字母仍然使用数学字体，小写字母按变量斜体排版。
SYMBOL_FONT_CHARS = frozenset(
    {char for char in SYMBOL_LATEX if not char.isalpha()}
    | set(NUMBER_SET_SYMBOLS)
    | set(SCRIPT_SYMBOLS)
)

# 四则运算等单行算符按「字符」处理：它们不携带结构位置，也不参与自动拆分；
# 删除时作为普通字符删掉，不会连带删除相邻的结构。
# 由符号表中所有非字母符号自动汇总，再补上 ASCII 四则运算字符。
PLAIN_OPERATOR_CHARS = set("+-*/=<>") | {
    char for char in SYMBOL_LATEX if not char.isalpha()
}

PRIMARY_SYMBOLS = ("·", "×", "±", "∓", "≤", "≥", "≠", "∞", "∂", "∇")

# 「更多符号」面板按类别拆分成多个下拉菜单。
# 每一项是 (菜单名, 条目元组)；条目既可以是单个符号，也可以是
# (子菜单名, 条目元组)，用于把较长的分类（如希腊字母）收进级联菜单。
SYMBOL_GROUPS = (
    (
        "基本运算",
        (
            "+",
            "-",
            "*",
            "/",
            "=",
            "<",
            ">",
            "≠",
            "≤",
            "≥",
            "≈",
            "≡",
            "∝",
            "×",
            "÷",
            "·",
            "±",
            "∓",
            "≅",
            "≪",
            "≫",
            "∘",
        ),
    ),
    (
        "集合",
        (
            "∈",
            "∉",
            "∋",
            "⊂",
            "⊆",
            "⊄",
            "⊊",
            "⊃",
            "⊇",
            "∪",
            "∩",
            "∖",
            "∅",
        )
        + NUMBER_SET_SYMBOLS,
    ),
    (
        "微积分",
        (
            "∫",
            "∬",
            "∭",
            "∮",
            "∂",
            "∇",
            "∞",
            "Δ",
            "′",
            "″",
        ),
    ),
    (
        "变量",
        (
            (
                "希腊字母（小写）",
                (
                    "α",
                    "β",
                    "γ",
                    "δ",
                    "ε",
                    "ζ",
                    "η",
                    "θ",
                    "ι",
                    "κ",
                    "λ",
                    "μ",
                    "ν",
                    "ξ",
                    "π",
                    "ρ",
                    "σ",
                    "τ",
                    "υ",
                    "φ",
                    "χ",
                    "ψ",
                    "ω",
                ),
            ),
            (
                "希腊字母（大写）",
                ("Γ", "Δ", "Θ", "Λ", "Ξ", "Π", "Σ", "Υ", "Φ", "Ψ", "Ω"),
            ),
        ),
    ),
    (
        "标识",
        (
            "°",
            ("上标", SCRIPT_SUPERSCRIPT_SYMBOLS),
            ("下标", SCRIPT_SUBSCRIPT_SYMBOLS),
        ),
    ),
    (
        "逻辑与箭头",
        (
            "∧",
            "∨",
            "¬",
            "∀",
            "∃",
            "∴",
            "∵",
            "→",
            "←",
            "↔",
            "⇒",
            "⇐",
            "⇔",
            "⊥",
            "∥",
        ),
    ),
)


def iter_panel_glyphs():
    """按面板顺序给出全部可插入符号，级联子菜单里的符号也会展开。"""

    def walk(entries):
        for entry in entries:
            if isinstance(entry, tuple):
                yield from walk(entry[1])
            else:
                yield entry

    for _label, entries in SYMBOL_GROUPS:
        yield from walk(entries)


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
SELECTION_FILL = "#dbe2fe"

BASE_FONT_SIZE = 28
AUTO_FIT_SIZES = (28, 26, 24, 22, 20, 18, 16, 14, 12)
ITEM_GAP = 4
MIN_CANVAS_HEIGHT = 120
MAX_CANVAS_HEIGHT = 320
CANVAS_PADDING = 28
