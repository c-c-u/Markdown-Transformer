# -*- coding: utf-8 -*-
"""最小可复现实例：在求和结构最左侧按回格，删掉了右侧的内容。

样例（对应用户描述）：画布里一个求和结构，它的右侧空位写有 x+1。

复现步骤（纯 Python，不启动 Tkinter 窗口）：

    1. 构造公式（等价于在画布上插入求和、再在它右侧空位键入 x+1）：
           [空位]  [求和结构]  [文本 x+1]
            0        1          2
    2. 把光标放在最左侧的空位（下标 0），按一次回格。
    3. 旧实现会把下标 1 的求和当成“删除方向上的结构”整体删掉 ——
       求和位于光标**右侧**，这就是 bug。

本脚本同时演示：
    * 旧实现为什么错（old_backspace_target：从行尾往行首扫、只跳过光标元素）；
    * 当前实现为什么对（delete_structure_toward：只在回格方向即左侧查找）。

运行：python repro_backspace/repro.py（需要项目根目录在 sys.path 中）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from formula_editor_app.model import (  # noqa: E402
    Placeholder,
    Slot,
    TextRun,
    delete_structure_toward,
    is_structure_item,
    make_sum_node,
    normalize_formula,
    serialize_item,
    serialize_slot,
)


def build_formula() -> Slot:
    """输入：求和结构 + 右下空位里的 x+1。"""
    return Slot(
        [Placeholder(free=True), make_sum_node(), TextRun("x+1", free=True)],
        role="公式",
        row=True,
    )


def old_backspace_target(root: Slot, index: int):
    """旧实现（有 bug）的最小提取：回格也从行尾往行首扫，只跳过光标元素。

    于是光标在行首（下标 0）时，会在它的右侧找到求和结构并返回，
    回格就把右侧的求和删掉了。
    """
    i = len(root.items) - 1
    while 0 <= i < len(root.items):
        if i == index:
            i -= 1
            continue
        item = root.items[i]
        if is_structure_item(item):
            return root, i
        i -= 1
    return None


def describe(latex: str) -> str:
    return latex if latex else "<空公式>"


def main() -> int:
    print("=" * 60)
    print("输入公式（求和结构 + 右侧空位写有 x+1）")
    formula = build_formula()
    print("  ", describe(normalize_formula(serialize_slot(formula))))
    print("  元素：", [type(item).__name__ for item in formula.items])
    print()

    failures = 0

    # ---- 复现 bug：光标在行首空位，按回格 ----
    target = old_backspace_target(formula, 0)
    if target is not None:
        print("[BUG] 旧实现：光标在行首空位按回格，会删除下标", target[1],
              "的元素（", type(formula.items[target[1]]).__name__,
              "），它位于光标**右侧**。")
        print("      （这是已修复的旧行为，仅用于演示，不计入失败）")
    else:
        print("[OK] 旧实现没有命中右侧内容（与 bug 描述不符，请检查提取的代码）")

    # ---- 当前实现：同一操作应该什么都不删 ----
    target = delete_structure_toward(formula, 0, 0, -1)
    if target is None:
        print("[OK] 当前实现：行首空位按回格 -> 不删除任何内容")
    else:
        print("[FAIL] 当前实现仍会删除下标", target[1], "的元素")
        failures += 1

    # ---- 对照：回格应该删除左侧相邻结构（光标在 x+1 开头） ----
    formula = build_formula()
    target = delete_structure_toward(formula, 2, 0, -1)
    if target is not None and target[1] == 1:
        print("[OK] 当前实现：x+1 开头按回格 -> 整体删除左侧的求和")
    else:
        print("[FAIL] 当前实现没有删除左侧的求和：", target)
        failures += 1

    # ---- 对照：删除后公式内容 ----
    formula = build_formula()
    target = delete_structure_toward(formula, 2, 0, -1)
    if target is not None:
        slot, index = target
        slot.items.pop(index)
        latex = normalize_formula(serialize_slot(formula))
        print("     删除后公式：", describe(latex),
              "（右侧的 x+1 保留，这是正确的）")

    print()
    if failures:
        print("RESULT: 仍存在问题（", failures, " 项）")
        return 1
    print("RESULT: 通过 —— 回格只删左侧内容，不再误删右侧结构")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
