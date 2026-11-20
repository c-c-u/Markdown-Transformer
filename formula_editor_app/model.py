# -*- coding: utf-8 -*-
"""公式树模型、遍历、模板工厂、序列化与纯函数。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from .config import ACCENT_LATEX, PLACEHOLDER, PLAIN_OPERATOR_CHARS, SYMBOL_LATEX

@dataclass
class Slot:
    """一段可编辑的行，按顺序放置文本、方框和公式结构。

    ``row=True`` 表示这一行里的结构与前后内容处在同一行、可以并排出现
    （公式根行、求和项、被积函数、微分分子分母等）；分子分母、上下限、
    乘方/上角标底数与指数、下角标、上下角标等 ``row=False``。
    ``row`` 决定「删除时是否把相邻的整个结构一并删除」，见
    ``delete_structure_toward``。
    """

    items: list["Element"] = field(default_factory=list)
    role: str = "公式"
    row: bool = False


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
    """上角标（乘方）：底数 + 上标。"""

    base: Slot
    exponent: Slot


@dataclass
class SubscriptNode:
    """下角标：底数 + 下标。"""

    base: Slot
    subscript: Slot


@dataclass
class SubSuperscriptNode:
    """上下角标：底数 + 下标 + 上标。"""

    base: Slot
    subscript: Slot
    superscript: Slot


@dataclass
class AccentNode:
    """顶标：内容上方加帽子、横线、波浪、点、矢量箭头等标记。

    ``mark`` 是 ``config.ACCENT_LATEX`` 里的键（hat、bar、vec …），
    决定画布上画哪种标记、导出成哪条 LaTeX 命令。
    """

    body: Slot
    mark: str = "hat"


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
    SubscriptNode,
    SubSuperscriptNode,
    AccentNode,
    RootNode,
    MatrixNode,
]


def new_slot(role: str) -> Slot:
    return Slot([Placeholder()], role=role)


def row_slot(role: str) -> Slot:
    """行内槽位：结构与前后内容并排出现。"""
    return Slot([Placeholder()], role=role, row=True)


def make_sum_node() -> SumNode:
    return SumNode(
        lower=new_slot("求和下限"),
        upper=new_slot("求和上限"),
        body=row_slot("求和项"),
    )


def make_integral_node() -> IntegralNode:
    return IntegralNode(
        lower=new_slot("积分下限"),
        upper=new_slot("积分上限"),
        body=row_slot("被积函数"),
        var=new_slot("积分变量"),
    )


def make_derivative_node() -> FractionNode:
    return FractionNode(
        numerator=Slot(
            [TextRun("d", upright=True, editable=False), Placeholder()],
            role="微分分子",
            row=True,
        ),
        denominator=Slot(
            [TextRun("d", upright=True, editable=False), Placeholder()],
            role="微分分母",
            row=True,
        ),
    )


def make_fraction_node() -> FractionNode:
    return FractionNode(
        numerator=new_slot("分子"),
        denominator=new_slot("分母"),
    )


def make_power_node() -> SuperscriptNode:
    return SuperscriptNode(base=new_slot("上标底数"), exponent=new_slot("上标"))


def make_subscript_node() -> SubscriptNode:
    return SubscriptNode(base=new_slot("下标底数"), subscript=new_slot("下标"))


def make_subsup_node() -> SubSuperscriptNode:
    return SubSuperscriptNode(
        base=new_slot("上下标底数"),
        subscript=new_slot("下标"),
        superscript=new_slot("上标"),
    )


def make_accent_node(mark: str) -> AccentNode:
    return AccentNode(body=new_slot("顶标内容"), mark=mark)


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
    if key == "subscript":
        return make_subscript_node()
    if key == "sub_sup":
        return make_subsup_node()
    if key in ACCENT_LATEX:
        return make_accent_node(key)
    if key == "sqrt":
        return make_sqrt_node()
    if key == "nth_root":
        return make_nth_root_node()
    raise KeyError(key)


# -- 遍历 -------------------------------------------------------------------
# 所有「按槽位递归」的遍历都用 child_slots() 展开：新增结构只改这一处，
# 方框统计、Tab 切换、选择范围、首格定位就会一起生效。


def child_slots(node: Element) -> tuple[Slot, ...]:
    if isinstance(node, SumNode):
        return (node.lower, node.upper, node.body)
    if isinstance(node, IntegralNode):
        return (node.lower, node.upper, node.body, node.var)
    if isinstance(node, FractionNode):
        return (node.numerator, node.denominator)
    if isinstance(node, SuperscriptNode):
        return (node.base, node.exponent)
    if isinstance(node, SubscriptNode):
        return (node.base, node.subscript)
    if isinstance(node, SubSuperscriptNode):
        return (node.base, node.subscript, node.superscript)
    if isinstance(node, AccentNode):
        return (node.body,)
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
        (
            SumNode,
            IntegralNode,
            FractionNode,
            SuperscriptNode,
            SubscriptNode,
            SubSuperscriptNode,
            AccentNode,
            RootNode,
            MatrixNode,
        ),
    )


def iter_placeholders(slot: Slot):
    """按阅读顺序给出还没填写的方框（结构两侧的隐藏空位不算）。"""
    for index, item in enumerate(slot.items):
        if isinstance(item, Placeholder):
            if not item.free:
                yield slot, index, item
        else:
            for child in child_slots(item):
                yield from iter_placeholders(child)


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

    # 整行都是空位时只保留一个，避免连续出现隐藏空位（结构内部的必填方框不受影响）。
    while (
        len(items) >= 2
        and all(isinstance(item, Placeholder) and item.free for item in items)
    ):
        items.pop()


def iter_targets(slot: Slot):
    """按阅读/填写顺序返回可点击的方框和可编辑文本。"""
    for index, item in enumerate(slot.items):
        if is_editable_input(item):
            yield slot, index, item
        elif is_structure_item(item):
            for child in child_slots(item):
                yield from iter_targets(child)


def first_target(slot: Slot):
    return next(iter_targets(slot), None)


def first_placeholder_in_node(node: Element):
    """结构里第一个还没填的方框；结构已经填满时返回 None。"""
    for slot in child_slots(node):
        target = first_target(slot)
        if target is not None and isinstance(target[2], Placeholder):
            return target
    return None


def count_placeholders(slot: Slot) -> int:
    return sum(1 for _ in iter_placeholders(slot))


# -- 选择、删除与光标 ---------------------------------------------------------


def slot_parents(root: Slot) -> dict[int, tuple[Slot, int]]:
    """子槽位 -> (父槽位, 该槽位在父槽位中的位置)。"""
    parents: dict[int, tuple[Slot, int]] = {}

    def walk(slot: Slot) -> None:
        for index, item in enumerate(slot.items):
            for child in child_slots(item):
                parents[id(child)] = (slot, index)
                walk(child)

    walk(root)
    return parents


# -- 上下方向键：算符内部预先写死的格位上下关系 -------------------------------


def main_slot(node: Element) -> Optional[Slot]:
    """结构算符的「主要方框」：填内容时优先放进去的位置。

    拖动选中一段内容后再插入带方框的算符时，选中内容会整体放进这个格位：
    积分放「被积函数」、根式放「被开方数」（根号里面）、分式/微分放「分子」、
    求和放「求和项」、上标/下标/上下标放「底数」、顶标放「内容」、
    矩阵/向量放「第一个单元格」。新增结构时在这里补一条即可。
    """
    if isinstance(node, SumNode):
        return node.body
    if isinstance(node, IntegralNode):
        return node.body
    if isinstance(node, FractionNode):
        return node.numerator
    if isinstance(node, SuperscriptNode):
        return node.base
    if isinstance(node, SubscriptNode):
        return node.base
    if isinstance(node, SubSuperscriptNode):
        return node.base
    if isinstance(node, AccentNode):
        return node.body
    if isinstance(node, RootNode):
        return node.radicand
    if isinstance(node, MatrixNode) and node.rows and node.rows[0]:
        return node.rows[0][0]
    return None



def vertical_slot_neighbors(
    node: Element,
) -> dict[int, tuple[Optional[Slot], Optional[Slot]]]:
    """算符内部各格位的「上/下相邻格位」表。

    这张表是**预先写死**的：每个多行算符的每个格位都显式登记按 ↑ / ↓
    能去的格位，``None`` 表示该方向没有格位。移动结果只看这张表，不看
    画布上的实际坐标，因此与字号、行高以及格位里填了多少内容都无关。

    键是子槽位的 ``id()``，值是 ``(上方格位, 下方格位)``。只有多行结构
    登记：求和的上下限与求和项、积分的上下限与被积函数/积分变量、分子
    分母、角标底数与上/下标、n 次根的根指数、矩阵同一列的相邻行；顶标
    和平方根只有一个格位，返回空表。

    新增结构时在这里补一条即可（只登记需要 ↑ / ↓ 的格位）。
    """
    if isinstance(node, SumNode):
        # ∑ 的上下限叠在上方和下方，求和项在右侧同一行。
        return {
            id(node.lower): (node.upper, None),
            id(node.upper): (None, node.lower),
            id(node.body): (node.upper, node.lower),
        }
    if isinstance(node, IntegralNode):
        # 被积函数和积分变量在主线上，向上/向下回到上下限。
        return {
            id(node.lower): (node.upper, None),
            id(node.upper): (None, node.lower),
            id(node.body): (node.upper, node.lower),
            id(node.var): (node.upper, node.lower),
        }
    if isinstance(node, FractionNode):
        return {
            id(node.numerator): (None, node.denominator),
            id(node.denominator): (node.numerator, None),
        }
    if isinstance(node, SuperscriptNode):
        return {
            id(node.base): (node.exponent, None),
            id(node.exponent): (None, node.base),
        }
    if isinstance(node, SubscriptNode):
        return {
            id(node.base): (None, node.subscript),
            id(node.subscript): (node.base, None),
        }
    if isinstance(node, SubSuperscriptNode):
        return {
            id(node.base): (node.superscript, node.subscript),
            id(node.subscript): (node.base, None),
            id(node.superscript): (None, node.base),
        }
    if isinstance(node, RootNode) and node.index is not None:
        return {
            id(node.radicand): (node.index, None),
            id(node.index): (None, node.radicand),
        }
    if isinstance(node, MatrixNode):
        table: dict[int, tuple[Optional[Slot], Optional[Slot]]] = {}
        for row_index, row in enumerate(node.rows):
            for col_index, cell in enumerate(row):
                above = None
                below = None
                if row_index > 0 and col_index < len(node.rows[row_index - 1]):
                    above = node.rows[row_index - 1][col_index]
                if (
                    row_index + 1 < len(node.rows)
                    and col_index < len(node.rows[row_index + 1])
                ):
                    below = node.rows[row_index + 1][col_index]
                table[id(cell)] = (above, below)
        return table
    return {}


def vertical_neighbor(
    slot: Slot,
    direction: int,
    parents: dict[int, tuple[Slot, int]],
) -> Optional[Slot]:
    """按 ↑（``direction < 0``）/ ↓（``direction > 0``）取该格位的上下相邻格位。

    只查该格位**直接所属**的算符：算符内部没有登记这个方向时返回 None，
    不会继续向外层结构里找，也不会退回到普通的阅读顺序切换。
    """
    info = parents.get(id(slot))
    if info is None:
        return None
    parent_slot, node_index = info
    if not (0 <= node_index < len(parent_slot.items)):
        return None
    node = parent_slot.items[node_index]
    if not is_structure_item(node):
        return None
    above, below = vertical_slot_neighbors(node).get(id(slot), (None, None))
    return above if direction < 0 else below


def iter_selectable_segments(root: Slot):
    """按阅读顺序给出可被选中的元素：可编辑文本、结构。

    结构以整体作为一个元素出现，因此选中它就会连同内部内容一起选中。
    空方框（``Placeholder``）是结构内部规定的输入位置，不是内容，
    因此不参与选择，也不能通过拖选删除。
    """
    def walk(slot: Slot):
        for index, item in enumerate(slot.items):
            if isinstance(item, TextRun):
                if item.editable:
                    yield slot, index, item
            elif isinstance(item, Placeholder):
                continue
            else:
                yield slot, index, item
                for child in child_slots(item):
                    yield from walk(child)

    yield from walk(root)


@dataclass
class SelectionSegment:
    """一段可被选中的元素及其画布包围盒。

    ``parent_slot`` / ``parent_index`` 只在结构元素上有意义；``offset`` 表示
    文本元素被选中的字符区间，结构被选中时恒为 None（整体选中）。
    """

    item: object
    slot: Slot
    index: int
    x1: float
    y1: float
    x2: float
    y2: float
    parent_slot: Optional[Slot] = None
    parent_index: int = -1
    offset: Optional[tuple[int, int]] = None


@dataclass
class SelectionRow:
    """画布上的一行选择单元；``offset`` 是这一行被选中的字符区间。"""

    index: int
    offset: Optional[tuple[int, int]]
    x1: float
    y1: float
    x2: float
    y2: float


def _structure_target(
    slot: Slot,
    start: int,
    step: int,
):
    """在同一个槽位里、沿删除方向查找紧邻的结构元素。

    只扫 ``start`` 一侧：回格只看它前面，Delete 只看它后面。
    遇到可编辑文本就停下（文本挡在中间时不能跨过去删更远的结构），
    遇到隐藏空位继续往前找。返回元素下标，找不到返回 None。
    """
    index = start - 1 if step < 0 else start + 1
    while 0 <= index < len(slot.items):
        item = slot.items[index]
        if is_structure_item(item):
            return index
        if isinstance(item, TextRun):
            return None
        index += step
    return None


def is_plain_operator_text(text: str) -> bool:
    """四则运算等单行算符按字符处理：整段都是算符字符时不算「结构」。"""
    return bool(text) and all(char in PLAIN_OPERATOR_CHARS for char in text)


def is_slot_front(slot: Slot, index: int, caret: int) -> bool:
    """光标是否位于该格位（槽位）的最前方。

    结构内部的固定字符（如微分里的 d）属于算符本身，不算作前方内容；
    前方只有空位时也算最前方。
    """
    if not (0 <= index < len(slot.items)):
        return False
    item = slot.items[index]
    if isinstance(item, TextRun):
        if not item.editable or caret != 0:
            return False
    elif not isinstance(item, Placeholder):
        return False
    for previous in slot.items[:index]:
        if isinstance(previous, Placeholder):
            continue
        if isinstance(previous, TextRun) and not previous.editable:
            continue
        return False
    return True


def plan_structure_unwrap(
    slot: Slot,
    index: int,
    caret: int,
    parents: dict[int, tuple[Slot, int]],
):
    """在大型算符内任意格位最前方回格：删除整个算符，并用该格位的内容替换。

    返回 (父槽位, 算符在父槽位中的下标, 用来替换的内容元素)；不满足条件时
    返回 None。结构内部的固定字符（如微分的 d）不随内容一起替换。
    """
    info = parents.get(id(slot))
    if info is None:
        return None
    parent_slot, node_index = info
    if not (0 <= node_index < len(parent_slot.items)):
        return None
    if not is_structure_item(parent_slot.items[node_index]):
        return None
    if not is_slot_front(slot, index, caret):
        return None
    content = [
        item
        for item in slot.items
        if not (isinstance(item, TextRun) and not item.editable)
        and not (isinstance(item, Placeholder) and item.free)
    ]
    return parent_slot, node_index, content


def apply_structure_unwrap(plan) -> tuple[Slot, int, int]:
    """执行 ``plan_structure_unwrap`` 的替换，返回 (父槽位, 起始下标, 内容个数)。"""
    parent_slot, node_index, content = plan
    parent_slot.items.pop(node_index)
    if not content:
        parent_slot.items.insert(node_index, Placeholder(free=True))
        return parent_slot, node_index, 1
    for item in content:
        if isinstance(item, Placeholder):
            item.free = parent_slot.row
    parent_slot.items[node_index:node_index] = content
    return parent_slot, node_index, len(content)


def adjacent_structure(slot: Slot, index: int, step: int):
    """同一行里与 index 处元素相邻、且紧挨着的那个结构。

    回格/Delete 在文本边界上用它进入相邻结构；中间隔着空位的，
    由 ``delete_structure_toward`` 负责整体删除，不算“紧挨着”。
    """
    neighbor = index + step
    if 0 <= neighbor < len(slot.items) and is_structure_item(slot.items[neighbor]):
        return slot.items[neighbor]
    return None


def delete_structure_toward(
    slot: Slot,
    index: int,
    caret: int,
    direction: int,
    active_item: Optional[Element] = None,
):
    """处理「删除方向只有一个算符」的情形。

    direction=-1 为回格（向前删），1 为 Delete（向后删）。
    当当前输入位置在删除方向上已经没有可删的字符、只与某个结构相邻时，
    返回该结构的 (所在槽位, 下标)，以便把算符和它内部的结构整体删除。

    只在**同一个槽位内、沿删除方向**查找：回格只往前、Delete 只往后，
    绝不回头去删另一侧的字符或结构。
    四则运算等「按字符处理」的单行算符不触发这条规则，只删字符本身。
    """
    item = active_item
    if item is None and 0 <= index < len(slot.items):
        item = slot.items[index]

    if isinstance(item, TextRun):
        if is_plain_operator_text(item.text):
            return None
        if item.editable:
            at_edge = len(item.text) == 0 or (
                caret == 0 if direction < 0 else caret >= len(item.text)
            )
            if not at_edge:
                return None
    elif not isinstance(item, Placeholder):
        return None

    target = _structure_target(slot, index, direction)
    if target is None:
        return None
    return slot, target


def text_offset_from_caret(caret_positions: list[float], x: float) -> int:
    """把点击位置换算成文本内的字符偏移。

    ``caret_positions`` 的格式为 [左边缘, 第 1 个字符后, ..., 右边缘]，
    因此字符数为 ``len(caret_positions) - 2``。
    """
    if len(caret_positions) <= 2:
        return 0
    best_index = 0
    best_distance = abs(caret_positions[0] - x)
    for offset in range(1, len(caret_positions) - 1):
        distance = abs(caret_positions[offset] - x)
        if distance < best_distance:
            best_distance = distance
            best_index = offset
    return best_index


def text_caret_positions(caret_positions: list[float], start: int, end: int) -> tuple[float, float]:
    """返回文本中 [start, end) 这一段的左右边缘坐标。"""
    if not caret_positions:
        return 0.0, 0.0
    left = caret_positions[max(0, min(start, len(caret_positions) - 1))]
    right = caret_positions[max(0, min(end, len(caret_positions) - 1))]
    return left, right


def selected_segments_range(
    segments: list[SelectionSegment],
    anchor_index: int,
    anchor_text_offset: int,
    focus_index: int,
    focus_text_offset: int,
) -> tuple[Optional[tuple[int, int]], list[SelectionSegment]]:
    """根据锚点/焦点算出选择范围和其中每个片段的内容。

    结构片段参与选择时总是整体选中；文本片段按字符区间选中。
    范围为空的文本选择（例如只选中 0 个字符）视为没有选择。
    """
    if not segments:
        return None, []
    low = max(0, min(anchor_index, focus_index))
    high = min(len(segments) - 1, max(anchor_index, focus_index))
    if low > high:
        return None, []

    selected: list[SelectionSegment] = []
    for position in range(low, high + 1):
        segment = segments[position]
        if isinstance(segment.item, TextRun) and segment.item.editable:
            start = 0
            end = len(segment.item.text)
            if position == low:
                start = anchor_text_offset if anchor_index <= focus_index else focus_text_offset
            if position == high:
                end = focus_text_offset if anchor_index <= focus_index else anchor_text_offset
            start = max(0, min(start, len(segment.item.text)))
            end = max(start, min(end, len(segment.item.text)))
            if start == end:
                continue
            segment.offset = (start, end)
        else:
            segment.offset = None
        selected.append(segment)

    if not selected:
        return None, []
    return (low, high), selected


def remove_selection(
    segments: list[SelectionSegment],
) -> Optional[tuple[Slot, int, int]]:
    """删除一段选择，返回删除后光标应落在的位置。

    结构连同内部内容整体删除；文本只删除被选中的字符，保留未选部分。
    空方框是结构规定的输入位置，**永远不参与删除**（结构被删时随结构一起消失）。
    """
    entries: list[tuple[Slot, int, object, Optional[str]]] = []
    seen: set[int] = set()
    for segment in segments:
        if isinstance(segment.item, TextRun) and segment.item.editable:
            text = segment.item.text
            start, end = segment.offset if segment.offset is not None else (0, len(text))
            start = max(0, min(start, len(text)))
            end = max(start, min(end, len(text)))
            if end <= start:
                continue
            if id(segment.item) in seen:
                continue
            seen.add(id(segment.item))
            entries.append((segment.slot, segment.index, segment.item, text[:start] + text[end:]))
        elif isinstance(segment.item, Placeholder):
            # 空方框不是内容，不能被拖选删除。
            continue
        else:
            if id(segment.item) in seen:
                continue
            seen.add(id(segment.item))
            entries.append((segment.slot, segment.index, segment.item, None))

    if not entries:
        return None

    caret_position: Optional[tuple[Slot, int, int]] = None
    for slot, index, item, new_text in entries:
        if not (0 <= index < len(slot.items) and slot.items[index] is item):
            continue
        if caret_position is None:
            caret_position = (slot, index, 0)
        if new_text is None:
            slot.items.pop(index)
        elif new_text:
            item.text = new_text
        else:
            slot.items[index] = Placeholder(free=item.free)

    if caret_position is None:
        return None
    slot, index, _caret = caret_position
    index = max(0, min(index, len(slot.items)))
    if index >= len(slot.items):
        slot.items.append(Placeholder(free=True))
        return slot, len(slot.items) - 1, 0
    if not is_editable_input(slot.items[index]):
        candidate = editable_position_left(slot, index)
        if candidate is not None:
            return slot, candidate, 0
        slot.items.insert(index, Placeholder(free=True))
        return slot, index, 0
    return slot, index, 0


def replace_selection_with_node(
    segments: list[SelectionSegment],
    node: Element,
    target: Slot,
    root: Slot,
) -> Optional[tuple[Slot, int]]:
    """把选中的内容取出来放进 ``target`` 格位，并在原来的位置放入 ``node``。

    ``target`` 是新结构的「主要方框」（见 ``main_slot``）。返回 ``node`` 插入后
    所在的 (槽位, 下标)；没有可移动的内容时返回 None，调用方按普通插入处理。

    移动规则：
    - 整体选中的结构连同内部内容一起移动；被选中结构内部的片段不再单独
      移动，避免同一段内容被移动两次。
    - 文本只移动被选中的字符，两侧未被选中的部分留在原处（必要时拆成两段）。
    - 空方框是结构规定的输入位置，不参与移动。
    """
    parents = slot_parents(root)
    selected_structures = {
        (id(segment.slot), segment.index)
        for segment in segments
        if is_structure_item(segment.item)
    }

    def inside_selected_structure(slot: Slot) -> bool:
        """该槽位是否位于某个被选中的结构里（那里面的内容随结构一起移动）。"""
        current = slot
        while id(current) in parents:
            parent_slot, index = parents[id(current)]
            if (id(parent_slot), index) in selected_structures:
                return True
            current = parent_slot
        return False

    moves: list[tuple[Slot, int, Element, Optional[tuple[str, str]]]] = []
    for segment in segments:
        item = segment.item
        if isinstance(item, Placeholder):
            continue
        if not (0 <= segment.index < len(segment.slot.items)):
            continue
        if segment.slot.items[segment.index] is not item:
            continue
        if inside_selected_structure(segment.slot):
            continue
        if is_structure_item(item):
            moves.append((segment.slot, segment.index, item, None))
            continue
        if not (isinstance(item, TextRun) and item.editable) or not item.text:
            continue
        text = item.text
        start, end = segment.offset if segment.offset is not None else (0, len(text))
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))
        if end <= start:
            continue
        if start == 0 and end == len(text):
            moves.append((segment.slot, segment.index, item, None))
            continue
        # 只移动被选中的字符：没选中的部分留在原处，必要时拆成前后两段。
        before, middle, after = text[:start], text[start:end], text[end:]
        moves.append(
            (
                segment.slot,
                segment.index,
                TextRun(middle, upright=item.upright, free=False),
                (before, after),
            )
        )

    if not moves:
        return None

    # 从后往前处理：原位删除 / 截断文本，下标不会互相影响。
    moved: list[Element] = []
    for slot, index, item, split in reversed(moves):
        if isinstance(item, TextRun):
            item.free = False
        moved.append(item)
        if not (0 <= index < len(slot.items)):
            continue
        if split is None:
            if slot.items[index] is item:
                slot.items.pop(index)
            continue
        original = slot.items[index]
        if not (isinstance(original, TextRun) and original.editable):
            continue
        before, after = split
        original.text = before if before else after
        if before and after:
            slot.items.insert(
                index + 1,
                TextRun(after, upright=original.upright, free=original.free),
            )
    moved.reverse()

    first_slot, first_index, _first_item, first_split = moves[0]
    place_after = first_split is not None and bool(first_split[0])
    position = max(0, min(first_index + (1 if place_after else 0), len(first_slot.items)))
    first_slot.items.insert(position, node)
    target.items = moved
    return first_slot, position


def editable_position_left(slot: Slot, index: int) -> Optional[int]:
    """从 ``index`` 往左找最近的可编辑位置；找不到返回 None。"""
    for candidate in range(index - 1, -1, -1):
        if is_editable_input(slot.items[candidate]):
            return candidate
    return None


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
    if isinstance(item, SubscriptNode):
        return (
            f"{{{serialize_slot(item.base)}}}"
            f"_{{{serialize_slot(item.subscript)}}}"
        )
    if isinstance(item, SubSuperscriptNode):
        return (
            f"{{{serialize_slot(item.base)}}}"
            f"_{{{serialize_slot(item.subscript)}}}"
            f"^{{{serialize_slot(item.superscript)}}}"
        )
    if isinstance(item, AccentNode):
        command = ACCENT_LATEX.get(item.mark, r"\hat")
        return f"{command}{{{serialize_slot(item.body)}}}"
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


def flatten_text(text: str) -> str:
    """把换行、制表符统一换成普通空格：画布上的文本不保留排版空白。"""
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return text.replace("\t", " ")


def normalize_formula(source: str) -> str:
    return strip_math_delimiters(flatten_text(source)).strip()


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

