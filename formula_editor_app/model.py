# -*- coding: utf-8 -*-
"""公式树模型、遍历、模板工厂、序列化与纯函数。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from .config import PLACEHOLDER, SYMBOL_LATEX

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
    free: bool = False


@dataclass
class Placeholder:
    """空位；free=True 表示结构两侧的非结构型空位，不绘制方框。"""

    free: bool = False


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


@dataclass
class SuperscriptNode:
    """乘方：底数 + 上标指数。"""

    base: Slot
    exponent: Slot


@dataclass
class RootNode:
    """平方根或 n 次根；index 为 None 时是平方根。"""

    radicand: Slot
    index: Optional[Slot] = None


@dataclass
class MatrixNode:
    """矩阵或列向量；rows 中的每个单元格都是可编辑的 Slot。"""

    rows: list[list[Slot]]


Element = Union[
    TextRun,
    Placeholder,
    SumNode,
    IntegralNode,
    FractionNode,
    SuperscriptNode,
    RootNode,
    MatrixNode,
]


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


def make_fraction_node() -> FractionNode:
    return FractionNode(
        numerator=new_slot("分子"),
        denominator=new_slot("分母"),
    )


def make_power_node() -> SuperscriptNode:
    return SuperscriptNode(base=new_slot("乘方底数"), exponent=new_slot("乘方指数"))


def make_sqrt_node() -> RootNode:
    return RootNode(radicand=new_slot("被开方数"), index=None)


def make_nth_root_node() -> RootNode:
    return RootNode(radicand=new_slot("被开方数"), index=new_slot("根指数"))


def make_matrix_node(rows: int, cols: int, role: str = "矩阵元素") -> MatrixNode:
    return MatrixNode(
        rows=[
            [new_slot(role) for _ in range(cols)]
            for _ in range(rows)
        ]
    )


def make_template(key: str) -> Element:
    if key == "sum":
        return make_sum_node()
    if key == "integral":
        return make_integral_node()
    if key == "derivative":
        return make_derivative_node()
    if key == "fraction":
        return make_fraction_node()
    if key == "power":
        return make_power_node()
    if key == "sqrt":
        return make_sqrt_node()
    if key == "nth_root":
        return make_nth_root_node()
    raise KeyError(key)


# -- 遍历 -------------------------------------------------------------------


def _iter_placeholders(slot: Slot):
    for index, item in enumerate(slot.items):
        if isinstance(item, Placeholder):
            if not item.free:
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
        elif isinstance(item, SuperscriptNode):
            yield from _iter_placeholders(item.base)
            yield from _iter_placeholders(item.exponent)
        elif isinstance(item, RootNode):
            yield from _iter_placeholders(item.radicand)
            if item.index is not None:
                yield from _iter_placeholders(item.index)
        elif isinstance(item, MatrixNode):
            for row in item.rows:
                for cell in row:
                    yield from _iter_placeholders(cell)


def iter_placeholders(slot: Slot):
    yield from _iter_placeholders(slot)


def child_slots(node: Element) -> tuple[Slot, ...]:
    if isinstance(node, SumNode):
        return (node.lower, node.upper, node.body)
    if isinstance(node, IntegralNode):
        return (node.lower, node.upper, node.body, node.var)
    if isinstance(node, FractionNode):
        return (node.numerator, node.denominator)
    if isinstance(node, SuperscriptNode):
        return (node.base, node.exponent)
    if isinstance(node, RootNode):
        if node.index is None:
            return (node.radicand,)
        return (node.radicand, node.index)
    if isinstance(node, MatrixNode):
        return tuple(cell for row in node.rows for cell in row)
    return ()


def is_editable_input(item: Element) -> bool:
    if isinstance(item, Placeholder):
        return True
    return isinstance(item, TextRun) and item.editable


def is_structure_item(item: Element) -> bool:
    return isinstance(
        item,
        (SumNode, IntegralNode, FractionNode, SuperscriptNode, RootNode, MatrixNode),
    )


def normalize_free_boundaries(slot: Slot) -> None:
    """保证每个结构左右都有可编辑位置。

    已有空位或可编辑文本时直接复用，不再额外插入；空位不绘制方框。
    """
    for item in list(slot.items):
        for child in child_slots(item):
            normalize_free_boundaries(child)

    items = slot.items
    index = 0
    while index < len(items):
        item = items[index]
        if not is_structure_item(item):
            index += 1
            continue

        if index == 0 or not is_editable_input(items[index - 1]):
            items.insert(index, Placeholder(free=True))
            index += 1

        if index + 1 >= len(items) or not is_editable_input(items[index + 1]):
            items.insert(index + 1, Placeholder(free=True))

        index += 2


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
        elif isinstance(item, SuperscriptNode):
            yield from iter_targets(item.base)
            yield from iter_targets(item.exponent)
        elif isinstance(item, RootNode):
            yield from iter_targets(item.radicand)
            if item.index is not None:
                yield from iter_targets(item.index)
        elif isinstance(item, MatrixNode):
            for row in item.rows:
                for cell in row:
                    yield from iter_targets(cell)


def first_target(slot: Slot):
    return next(iter_targets(slot), None)


def first_placeholder_in_node(node: Element):
    if isinstance(node, SumNode):
        slots = (node.lower, node.upper, node.body)
    elif isinstance(node, IntegralNode):
        slots = (node.lower, node.upper, node.body, node.var)
    elif isinstance(node, FractionNode):
        slots = (node.numerator, node.denominator)
    elif isinstance(node, SuperscriptNode):
        slots = (node.base, node.exponent)
    elif isinstance(node, RootNode):
        slots = (node.radicand, node.index) if node.index is not None else (node.radicand,)
    elif isinstance(node, MatrixNode):
        slots = tuple(cell for row in node.rows for cell in row)
    else:
        return None
    for slot in slots:
        target = first_target(slot)
        if isinstance(target[2], Placeholder):
            return target
    return None


def count_placeholders(slot: Slot) -> int:
    return sum(1 for _ in iter_placeholders(slot))


def contains_matrix(slot: Slot) -> bool:
    """输出预览使用 mathtext，遇到矩阵时应切换到画布渲染。"""
    for item in slot.items:
        if isinstance(item, MatrixNode):
            return True
        for child in child_slots(item):
            if contains_matrix(child):
                return True
    return False


def serialize_text(text: str) -> str:
    return "".join(SYMBOL_LATEX.get(char, char) for char in text)


# -- LaTeX 序列化 ------------------------------------------------------------


def serialize_slot(slot: Slot) -> str:
    return "".join(serialize_item(item) for item in slot.items)


def serialize_item(item: Element) -> str:
    if isinstance(item, TextRun):
        if item.upright:
            return rf"\mathrm{{{item.text}}}"
        return serialize_text(item.text)
    if isinstance(item, Placeholder):
        return "" if item.free else PLACEHOLDER
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
    if isinstance(item, SuperscriptNode):
        return (
            f"{{{serialize_slot(item.base)}}}"
            f"^{{{serialize_slot(item.exponent)}}}"
        )
    if isinstance(item, RootNode):
        radicand = serialize_slot(item.radicand)
        if item.index is None:
            return rf"\sqrt{{{radicand}}}"
        return rf"\sqrt[{serialize_slot(item.index)}]{{{radicand}}}"
    if isinstance(item, MatrixNode):
        rows = [
            " & ".join(serialize_slot(cell) for cell in row)
            for row in item.rows
        ]
        body = r" \\ ".join(rows)
        return rf"\begin{{pmatrix}} {body} \end{{pmatrix}}"
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

