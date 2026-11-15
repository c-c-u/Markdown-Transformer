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
    "hat": "帽子",
    "widehat": "宽帽子",
    "bar": "横线",
    "overline": "上划线",
    "tilde": "波浪",
    "widetilde": "宽波浪",
    "dot": "单点",
    "ddot": "双点",
    "vec": "矢量",
    "sqrt": "开方",
    "nth_root": "n 次根",
}

# 顶标：结构内部的内容上方加一个标记，导出为对应的 LaTeX 命令。
ACCENT_LATEX = {
    "hat": r"\hat",
    "widehat": r"\widehat",
    "bar": r"\bar",
    "overline": r"\overline",
    "tilde": r"\tilde",
    "widetilde": r"\widetilde",
    "dot": r"\dot",
    "ddot": r"\ddot",
    "vec": r"\vec",
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
}

# 数集符号（字母类字形，但按正体符号绘制）。
NUMBER_SET_SYMBOLS = ("ℕ", "ℤ", "ℚ", "ℝ", "ℂ")

# 画布上用「符号字体」正体绘制的字符：非字母类符号 + 数集字母。
# 拉丁字母、希腊字母仍然使用数学字体，小写字母按变量斜体排版。
SYMBOL_FONT_CHARS = frozenset(
    {char for char in SYMBOL_LATEX if not char.isalpha()} | set(NUMBER_SET_SYMBOLS)
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

# 「更多符号」里的结构分类：菜单项是 (显示名, 模板键)，点击后插入对应结构。
# 角标、顶标都需要填写方框，所以放在结构分类里，而不是单字符符号分类里。
TEMPLATE_GROUPS = (
    (
        "角标",
        (
            ("上角标（乘方）  x^n", "power"),
            ("下角标  x_n", "subscript"),
            ("上下角标  x_n^m", "sub_sup"),
        ),
    ),
    (
        "顶标",
        (
            ("帽子（hat）", "hat"),
            ("宽帽子（widehat）", "widehat"),
            ("横线（bar）", "bar"),
            ("上划线（overline）", "overline"),
            ("波浪（tilde）", "tilde"),
            ("宽波浪（widetilde）", "widetilde"),
            ("单点（dot）", "dot"),
            ("双点（ddot）", "ddot"),
            ("矢量（vec）", "vec"),
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
