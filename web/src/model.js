/* 公式树模型、遍历、模板工厂、序列化与纯函数（对应 formula_editor_app/model.py）。 */
'use strict';

// -- 文本按码点处理的辅助函数（Python 的字符串下标按码点计） -----------------
function textChars(text) {
  return Array.from(text);
}

function textLength(text) {
  return Array.from(text).length;
}

function textSlice(text, start, end) {
  return Array.from(text).slice(start, end).join('');
}

function textInsertAt(text, position, insert) {
  const chars = Array.from(text);
  return chars.slice(0, position).join('') + insert + chars.slice(position).join('');
}

function textRemoveAt(text, position) {
  const chars = Array.from(text);
  chars.splice(position, 1);
  return chars.join('');
}

// -- 节点与工厂 ---------------------------------------------------------------

function newSlot(role) {
  return { items: [{ kind: 'placeholder', free: false }], role: role || '公式', row: false };
}

function rowSlot(role) {
  return { items: [{ kind: 'placeholder', free: false }], role: role || '公式', row: true };
}

function textRun(text, opts) {
  return Object.assign(
    { kind: 'text', text: text || '', upright: false, editable: true, free: false },
    opts || {},
  );
}

function makeSumNode() {
  return {
    kind: 'sum',
    lower: newSlot('求和下限'),
    upper: newSlot('求和上限'),
    body: rowSlot('求和项'),
  };
}

function makeIntegralNode() {
  return {
    kind: 'integral',
    lower: newSlot('积分下限'),
    upper: newSlot('积分上限'),
    body: rowSlot('被积函数'),
    var: newSlot('积分变量'),
  };
}

function makeDerivativeNode() {
  return {
    kind: 'fraction',
    numerator: { items: [textRun('d', { upright: true, editable: false }), { kind: 'placeholder', free: false }], role: '微分分子', row: true },
    denominator: { items: [textRun('d', { upright: true, editable: false }), { kind: 'placeholder', free: false }], role: '微分分母', row: true },
  };
}

function makeFractionNode() {
  return { kind: 'fraction', numerator: newSlot('分子'), denominator: newSlot('分母') };
}

function makePowerNode() {
  return { kind: 'power', base: newSlot('上标底数'), exponent: newSlot('上标') };
}

function makeSubscriptNode() {
  return { kind: 'subscript', base: newSlot('下标底数'), subscript: newSlot('下标') };
}

function makeSubsupNode() {
  return {
    kind: 'sub_sup',
    base: newSlot('上下标底数'),
    subscript: newSlot('下标'),
    superscript: newSlot('上标'),
  };
}

function makeAccentNode(mark) {
  return { kind: 'accent', body: newSlot('顶标内容'), mark: mark };
}

function makeSqrtNode() {
  return { kind: 'root', radicand: newSlot('被开方数'), index: null };
}

function makeNthRootNode() {
  return { kind: 'root', radicand: newSlot('被开方数'), index: newSlot('根指数') };
}

function makeMatrixNode(rows, cols, role) {
  const cellRole = role || '矩阵元素';
  const grid = [];
  for (let r = 0; r < rows; r += 1) {
    const row = [];
    for (let c = 0; c < cols; c += 1) row.push(newSlot(cellRole));
    grid.push(row);
  }
  return { kind: 'matrix', rows: grid };
}

function makeTemplate(key) {
  switch (key) {
    case 'sum': return makeSumNode();
    case 'integral': return makeIntegralNode();
    case 'derivative': return makeDerivativeNode();
    case 'fraction': return makeFractionNode();
    case 'power': return makePowerNode();
    case 'subscript': return makeSubscriptNode();
    case 'sub_sup': return makeSubsupNode();
    case 'sqrt': return makeSqrtNode();
    case 'nth_root': return makeNthRootNode();
    default:
      if (Object.prototype.hasOwnProperty.call(ACCENT_LATEX, key)) return makeAccentNode(key);
      throw new Error('unknown template: ' + key);
  }
}

// -- 遍历 ---------------------------------------------------------------------
// 所有「按槽位递归」的遍历都用 childSlots() 展开：新增结构只改这一处，
// 方框统计、Tab 切换、选择范围、首格定位就会一起生效。

function childSlots(node) {
  switch (node.kind) {
    case 'sum': return [node.lower, node.upper, node.body];
    case 'integral': return [node.lower, node.upper, node.body, node.var];
    case 'fraction': return [node.numerator, node.denominator];
    case 'power': return [node.base, node.exponent];
    case 'subscript': return [node.base, node.subscript];
    case 'sub_sup': return [node.base, node.subscript, node.superscript];
    case 'accent': return [node.body];
    case 'root': return node.index ? [node.radicand, node.index] : [node.radicand];
    case 'matrix': {
      const slots = [];
      for (const row of node.rows) for (const cell of row) slots.push(cell);
      return slots;
    }
    default: return [];
  }
}

function isEditableInput(item) {
  if (!item) return false;
  if (item.kind === 'placeholder') return true;
  return item.kind === 'text' && item.editable;
}

function isStructureItem(item) {
  return (
    item.kind === 'sum'
    || item.kind === 'integral'
    || item.kind === 'fraction'
    || item.kind === 'power'
    || item.kind === 'subscript'
    || item.kind === 'sub_sup'
    || item.kind === 'accent'
    || item.kind === 'root'
    || item.kind === 'matrix'
  );
}

/** 按阅读顺序给出还没填写的方框（结构两侧的隐藏空位不算）。 */
function* iterPlaceholders(slot) {
  for (let index = 0; index < slot.items.length; index += 1) {
    const item = slot.items[index];
    if (item.kind === 'placeholder') {
      if (!item.free) yield [slot, index, item];
    } else {
      for (const child of childSlots(item)) yield* iterPlaceholders(child);
    }
  }
}

/** 保证每个结构左右都有可编辑位置：已有空位或可编辑文本时直接复用。 */
function normalizeFreeBoundaries(slot) {
  for (const item of slot.items.slice()) {
    for (const child of childSlots(item)) normalizeFreeBoundaries(child);
  }

  const items = slot.items;
  let index = 0;
  while (index < items.length) {
    const item = items[index];
    if (!isStructureItem(item)) {
      index += 1;
      continue;
    }

    if (index === 0 || !isEditableInput(items[index - 1])) {
      items.splice(index, 0, { kind: 'placeholder', free: true });
      index += 1;
    }

    if (index + 1 >= items.length || !isEditableInput(items[index + 1])) {
      items.splice(index + 1, 0, { kind: 'placeholder', free: true });
    }

    index += 2;
  }

  // 整行都是空位时只保留一个，避免连续出现隐藏空位（结构内部的必填方框不受影响）。
  while (
    items.length >= 2
    && items.every((item) => item.kind === 'placeholder' && item.free)
  ) {
    items.pop();
  }
}

/** 按阅读/填写顺序返回可点击的方框和可编辑文本。 */
function* iterTargets(slot) {
  for (let index = 0; index < slot.items.length; index += 1) {
    const item = slot.items[index];
    if (isEditableInput(item)) {
      yield [slot, index, item];
    } else if (isStructureItem(item)) {
      for (const child of childSlots(item)) yield* iterTargets(child);
    }
  }
}

function firstTarget(slot) {
  for (const target of iterTargets(slot)) return target;
  return null;
}

/** 结构里第一个还没填的方框；结构已经填满时返回 null。 */
function firstPlaceholderInNode(node) {
  for (const slot of childSlots(node)) {
    const target = firstTarget(slot);
    if (target !== null && target[2].kind === 'placeholder') return target;
  }
  return null;
}

function countPlaceholders(slot) {
  let count = 0;
  for (const _ of iterPlaceholders(slot)) count += 1;
  return count;
}

/**
 * 结构算符的「主要方框」：填内容时优先放进去的位置。
 *
 * 拖动选中一段内容后再插入带方框的算符时，选中内容会整体放进这个格位：
 * 积分放「被积函数」、根式放「被开方数」（根号里面）、分式/微分放「分子」、
 * 求和放「求和项」、上标/下标/上下标放「底数」、顶标放「内容」、
 * 矩阵/向量放「第一个单元格」。新增结构时在这里补一条即可。
 */
function mainSlot(node) {
  switch (node.kind) {
    case 'sum':
      return node.body;
    case 'integral':
      return node.body;
    case 'fraction':
      return node.numerator;
    case 'power':
      return node.base;
    case 'subscript':
      return node.base;
    case 'sub_sup':
      return node.base;
    case 'accent':
      return node.body;
    case 'root':
      return node.radicand;
    case 'matrix':
      return node.rows.length && node.rows[0].length ? node.rows[0][0] : null;
    default:
      return null;
  }
}

// -- 选择、删除与光标 ---------------------------------------------------------

function slotParents(root) {
  const parents = new Map();
  const walk = (slot) => {
    for (let index = 0; index < slot.items.length; index += 1) {
      for (const child of childSlots(slot.items[index])) {
        parents.set(child, [slot, index]);
        walk(child);
      }
    }
  };
  walk(root);
  return parents;
}

// -- 上下方向键：算符内部预先写死的格位上下关系 -------------------------------

/**
 * 算符内部各格位的「上/下相邻格位」表。
 *
 * 这张表是**预先写死**的：每个多行算符的每个格位都显式登记按 ↑ / ↓
 * 能去的格位，``null`` 表示该方向没有格位。移动结果只看这张表，不看
 * 画布上的实际坐标，因此与字号、行高以及格位里填了多少内容都无关。
 */
function verticalSlotNeighbors(node) {
  const table = new Map();
  switch (node.kind) {
    case 'sum':
      // ∑ 的上下限叠在上方和下方，求和项在右侧同一行。
      table.set(node.lower, [node.upper, null]);
      table.set(node.upper, [null, node.lower]);
      table.set(node.body, [node.upper, node.lower]);
      break;
    case 'integral':
      // 被积函数和积分变量在主线上，向上/向下回到上下限。
      table.set(node.lower, [node.upper, null]);
      table.set(node.upper, [null, node.lower]);
      table.set(node.body, [node.upper, node.lower]);
      table.set(node.var, [node.upper, node.lower]);
      break;
    case 'fraction':
      table.set(node.numerator, [null, node.denominator]);
      table.set(node.denominator, [node.numerator, null]);
      break;
    case 'power':
      table.set(node.base, [node.exponent, null]);
      table.set(node.exponent, [null, node.base]);
      break;
    case 'subscript':
      table.set(node.base, [null, node.subscript]);
      table.set(node.subscript, [node.base, null]);
      break;
    case 'sub_sup':
      table.set(node.base, [node.superscript, node.subscript]);
      table.set(node.subscript, [node.base, null]);
      table.set(node.superscript, [null, node.base]);
      break;
    case 'root':
      if (node.index) {
        table.set(node.radicand, [node.index, null]);
        table.set(node.index, [null, node.radicand]);
      }
      break;
    case 'matrix': {
      for (let rowIndex = 0; rowIndex < node.rows.length; rowIndex += 1) {
        for (let colIndex = 0; colIndex < node.rows[rowIndex].length; colIndex += 1) {
          const cell = node.rows[rowIndex][colIndex];
          let above = null;
          let below = null;
          if (rowIndex > 0 && colIndex < node.rows[rowIndex - 1].length) {
            above = node.rows[rowIndex - 1][colIndex];
          }
          if (rowIndex + 1 < node.rows.length && colIndex < node.rows[rowIndex + 1].length) {
            below = node.rows[rowIndex + 1][colIndex];
          }
          table.set(cell, [above, below]);
        }
      }
      break;
    }
    default:
      break;
  }
  return table;
}

/**
 * 按 ↑（direction < 0）/ ↓（direction > 0）取该格位的上下相邻格位。
 *
 * 只查该格位**直接所属**的算符：算符内部没有登记这个方向时返回 null，
 * 不会继续向外层结构里找，也不会退回到普通的阅读顺序切换。
 */
function verticalNeighbor(slot, direction, parents) {
  const info = parents.get(slot);
  if (!info) return null;
  const parentSlot = info[0];
  const nodeIndex = info[1];
  if (!(nodeIndex >= 0 && nodeIndex < parentSlot.items.length)) return null;
  const node = parentSlot.items[nodeIndex];
  if (!isStructureItem(node)) return null;
  const entry = verticalSlotNeighbors(node).get(slot) || [null, null];
  return direction < 0 ? entry[0] : entry[1];
}

/** 按阅读顺序给出可被选中的元素：可编辑文本、结构。 */
function* iterSelectableSegments(root) {
  const walk = function* (slot) {
    for (let index = 0; index < slot.items.length; index += 1) {
      const item = slot.items[index];
      if (item.kind === 'text') {
        if (item.editable) yield [slot, index, item];
      } else if (item.kind === 'placeholder') {
        continue;
      } else {
        yield [slot, index, item];
        for (const child of childSlots(item)) yield* walk(child);
      }
    }
  };
  yield* walk(root);
}

function makeSelectionSegment(item, slot, index, x1, y1, x2, y2) {
  return {
    item: item,
    slot: slot,
    index: index,
    x1: x1,
    y1: y1,
    x2: x2,
    y2: y2,
    parentSlot: null,
    parentIndex: -1,
    offset: null,
  };
}

/** 在同一个槽位里、沿删除方向查找紧邻的结构元素。 */
function structureTarget(slot, start, step) {
  let index = step < 0 ? start - 1 : start + 1;
  while (index >= 0 && index < slot.items.length) {
    const item = slot.items[index];
    if (isStructureItem(item)) return index;
    if (item.kind === 'text') return null;
    index += step;
  }
  return null;
}

/** 四则运算等单行算符按字符处理：整段都是算符字符时不算「结构」。 */
function isPlainOperatorText(text) {
  return !!text && Array.from(text).every((char) => PLAIN_OPERATOR_CHARS.has(char));
}

/**
 * 光标是否位于该格位（槽位）的最前方。
 *
 * 结构内部的固定字符（如微分里的 d）属于算符本身，不算作前方内容；
 * 前方只有空位时也算最前方。
 */
function isSlotFront(slot, index, caret) {
  if (!(index >= 0 && index < slot.items.length)) return false;
  const item = slot.items[index];
  if (item.kind === 'text') {
    if (!item.editable || caret !== 0) return false;
  } else if (item.kind !== 'placeholder') {
    return false;
  }
  for (let previous = 0; previous < index; previous += 1) {
    const prior = slot.items[previous];
    if (prior.kind === 'placeholder') continue;
    if (prior.kind === 'text' && !prior.editable) continue;
    return false;
  }
  return true;
}

/**
 * 在大型算符内任意格位最前方回格：删除整个算符，并用该格位的内容替换。
 *
 * 返回 [父槽位, 算符在父槽位中的下标, 用来替换的内容元素数组]；不满足条件时
 * 返回 null。结构内部的固定字符（如微分的 d）不随内容一起替换。
 */
function planStructureUnwrap(slot, index, caret, parents) {
  const info = parents.get(slot);
  if (!info) return null;
  const parentSlot = info[0];
  const nodeIndex = info[1];
  if (!(nodeIndex >= 0 && nodeIndex < parentSlot.items.length)) return null;
  if (!isStructureItem(parentSlot.items[nodeIndex])) return null;
  if (!isSlotFront(slot, index, caret)) return null;
  const content = slot.items.filter(
    (item) => !(item.kind === 'text' && !item.editable)
      && !(item.kind === 'placeholder' && item.free),
  );
  return [parentSlot, nodeIndex, content];
}

/** 执行 planStructureUnwrap 的替换，返回 [父槽位, 起始下标, 内容个数]。 */
function applyStructureUnwrap(plan) {
  const parentSlot = plan[0];
  const nodeIndex = plan[1];
  const content = plan[2];
  parentSlot.items.splice(nodeIndex, 1);
  if (!content.length) {
    parentSlot.items.splice(nodeIndex, 0, { kind: 'placeholder', free: true });
    return [parentSlot, nodeIndex, 1];
  }
  for (const item of content) {
    if (item.kind === 'placeholder') item.free = parentSlot.row;
  }
  parentSlot.items.splice(nodeIndex, 0, ...content);
  return [parentSlot, nodeIndex, content.length];
}

/** 同一行里与 index 处元素相邻、且紧挨着的那个结构。 */
function adjacentStructure(slot, index, step) {
  const neighbor = index + step;
  if (neighbor >= 0 && neighbor < slot.items.length && isStructureItem(slot.items[neighbor])) {
    return slot.items[neighbor];
  }
  return null;
}

/**
 * 处理「删除方向只有一个算符」的情形。
 *
 * direction=-1 为回格（向前删），1 为 Delete（向后删）。
 * 当当前输入位置在删除方向上已经没有可删的字符、只与某个结构相邻时，
 * 返回该结构的 [所在槽位, 下标]，以便把算符和它内部的结构整体删除。
 *
 * 只在**同一个槽位内、沿删除方向**查找：回格只往前、Delete 只往后，
 * 绝不回头去删另一侧的字符或结构。
 * 四则运算等「按字符处理」的单行算符不触发这条规则，只删字符本身。
 */
function deleteStructureToward(slot, index, caret, direction, activeItem) {
  let item = activeItem;
  if (item === undefined || item === null) {
    if (index >= 0 && index < slot.items.length) item = slot.items[index];
  }

  if (item && item.kind === 'text') {
    if (isPlainOperatorText(item.text)) return null;
    if (item.editable) {
      const atEdge = item.text.length === 0
        || (direction < 0 ? caret === 0 : caret >= textLength(item.text));
      if (!atEdge) return null;
    }
  } else if (!(item && item.kind === 'placeholder')) {
    return null;
  }

  const target = structureTarget(slot, index, direction);
  if (target === null) return null;
  return [slot, target];
}

/** 把点击位置换算成文本内的字符偏移。 */
function textOffsetFromCaret(caretPositions, x) {
  if (caretPositions.length <= 2) return 0;
  let bestIndex = 0;
  let bestDistance = Math.abs(caretPositions[0] - x);
  for (let offset = 1; offset < caretPositions.length - 1; offset += 1) {
    const distance = Math.abs(caretPositions[offset] - x);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = offset;
    }
  }
  return bestIndex;
}

/** 返回文本中 [start, end) 这一段的左右边缘坐标。 */
function textCaretPositions(caretPositions, start, end) {
  if (!caretPositions.length) return [0.0, 0.0];
  const left = caretPositions[Math.max(0, Math.min(start, caretPositions.length - 1))];
  const right = caretPositions[Math.max(0, Math.min(end, caretPositions.length - 1))];
  return [left, right];
}

/** 根据锚点/焦点算出选择范围和其中每个片段的内容。 */
function selectedSegmentsRange(
  segments,
  anchorIndex,
  anchorTextOffset,
  focusIndex,
  focusTextOffset,
) {
  if (!segments.length) return [null, []];
  const low = Math.max(0, Math.min(anchorIndex, focusIndex));
  const high = Math.min(segments.length - 1, Math.max(anchorIndex, focusIndex));
  if (low > high) return [null, []];

  const selected = [];
  for (let position = low; position <= high; position += 1) {
    const segment = segments[position];
    if (segment.item.kind === 'text' && segment.item.editable) {
      let start = 0;
      let end = textLength(segment.item.text);
      if (position === low) {
        start = anchorIndex <= focusIndex ? anchorTextOffset : focusTextOffset;
      }
      if (position === high) {
        end = anchorIndex <= focusIndex ? focusTextOffset : anchorTextOffset;
      }
      start = Math.max(0, Math.min(start, textLength(segment.item.text)));
      end = Math.max(start, Math.min(end, textLength(segment.item.text)));
      if (start === end) continue;
      segment.offset = [start, end];
    } else {
      segment.offset = null;
    }
    selected.push(segment);
  }

  if (!selected.length) return [null, []];
  return [[low, high], selected];
}

/**
 * 删除一段选择，返回删除后光标应落在的位置。
 *
 * 结构连同内部内容整体删除；文本只删除被选中的字符，保留未选部分。
 * 空方框是结构规定的输入位置，**永远不参与删除**（结构被删时随结构一起消失）。
 */
function removeSelection(segments) {
  const entries = [];
  const seen = new Set();
  for (const segment of segments) {
    if (segment.item.kind === 'text' && segment.item.editable) {
      const text = segment.item.text;
      const offset = segment.offset !== null ? segment.offset : [0, textLength(text)];
      let start = Math.max(0, Math.min(offset[0], textLength(text)));
      let end = Math.max(start, Math.min(offset[1], textLength(text)));
      if (end <= start) continue;
      if (seen.has(segment.item)) continue;
      seen.add(segment.item);
      entries.push([segment.slot, segment.index, segment.item, textSlice(text, 0, start) + textSlice(text, end)]);
    } else if (segment.item.kind === 'placeholder') {
      // 空方框不是内容，不能被拖选删除。
      continue;
    } else {
      if (seen.has(segment.item)) continue;
      seen.add(segment.item);
      entries.push([segment.slot, segment.index, segment.item, null]);
    }
  }

  if (!entries.length) return null;

  let caretPosition = null;
  for (const entry of entries) {
    const slot = entry[0];
    const index = entry[1];
    const item = entry[2];
    const newText = entry[3];
    if (!(index >= 0 && index < slot.items.length && slot.items[index] === item)) continue;
    if (caretPosition === null) caretPosition = [slot, index, 0];
    if (newText === null) {
      slot.items.splice(index, 1);
    } else if (newText) {
      item.text = newText;
    } else {
      slot.items[index] = { kind: 'placeholder', free: item.free };
    }
  }

  if (caretPosition === null) return null;
  const slot = caretPosition[0];
  let index = caretPosition[1];
  index = Math.max(0, Math.min(index, slot.items.length));
  if (index >= slot.items.length) {
    slot.items.push({ kind: 'placeholder', free: true });
    return [slot, slot.items.length - 1, 0];
  }
  if (!isEditableInput(slot.items[index])) {
    const candidate = editablePositionLeft(slot, index);
    if (candidate !== null) return [slot, candidate, 0];
    slot.items.splice(index, 0, { kind: 'placeholder', free: true });
    return [slot, index, 0];
  }
  return [slot, index, 0];
}

/** 从 index 往左找最近的可编辑位置；找不到返回 null。 */
function editablePositionLeft(slot, index) {
  for (let candidate = index - 1; candidate >= 0; candidate -= 1) {
    if (isEditableInput(slot.items[candidate])) return candidate;
  }
  return null;
}

/**
 * 把选中的内容取出来放进 target 格位，并在原来的位置放入 node。
 *
 * target 是新结构的「主要方框」（见 mainSlot）。返回 node 插入后所在的
 * [槽位, 下标]；没有可移动的内容时返回 null，调用方按普通插入处理。
 *
 * 移动规则：
 * - 整体选中的结构连同内部内容一起移动；被选中结构内部的片段不再单独
 *   移动，避免同一段内容被移动两次。
 * - 文本只移动被选中的字符，两侧未被选中的部分留在原处（必要时拆成两段）。
 * - 空方框是结构规定的输入位置，不参与移动。
 */
function replaceSelectionWithNode(segments, node, target, root) {
  const parents = slotParents(root);
  // 被选中的结构按 (父槽位, 下标) 记录，位置和槽位链上的父级位置一一对应。
  const selectedStructureSlots = new Map();
  for (const segment of segments) {
    if (!isStructureItem(segment.item)) continue;
    if (!selectedStructureSlots.has(segment.slot)) {
      selectedStructureSlots.set(segment.slot, new Set());
    }
    selectedStructureSlots.get(segment.slot).add(segment.index);
  }

  const insideSelectedStructure = (slot) => {
    let current = slot;
    while (parents.has(current)) {
      const [parentSlot, index] = parents.get(current);
      const indexes = selectedStructureSlots.get(parentSlot);
      if (indexes && indexes.has(index)) return true;
      current = parentSlot;
    }
    return false;
  };

  const moves = [];
  for (const segment of segments) {
    const item = segment.item;
    if (item.kind === 'placeholder') continue;
    if (!(segment.index >= 0 && segment.index < segment.slot.items.length)) continue;
    if (segment.slot.items[segment.index] !== item) continue;
    if (insideSelectedStructure(segment.slot)) continue;
    if (isStructureItem(item)) {
      moves.push([segment.slot, segment.index, item, null]);
      continue;
    }
    if (!(item.kind === 'text' && item.editable) || !item.text) continue;
    const text = item.text;
    const offset = segment.offset !== null ? segment.offset : [0, textLength(text)];
    const start = Math.max(0, Math.min(offset[0], textLength(text)));
    const end = Math.max(start, Math.min(offset[1], textLength(text)));
    if (end <= start) continue;
    if (start === 0 && end === textLength(text)) {
      moves.push([segment.slot, segment.index, item, null]);
      continue;
    }
    // 只移动被选中的字符：没选中的部分留在原处，必要时拆成前后两段。
    const before = textSlice(text, 0, start);
    const middle = textSlice(text, start, end);
    const after = textSlice(text, end);
    moves.push([segment.slot, segment.index, textRun(middle, { upright: item.upright }), [before, after]]);
  }

  if (!moves.length) return null;

  // 从后往前处理：原位删除 / 截断文本，下标不会互相影响。
  const moved = [];
  for (let position = moves.length - 1; position >= 0; position -= 1) {
    const [slot, index, item, split] = moves[position];
    if (item.kind === 'text') item.free = false;
    moved.push(item);
    if (!(index >= 0 && index < slot.items.length)) continue;
    if (split === null) {
      if (slot.items[index] === item) slot.items.splice(index, 1);
      continue;
    }
    const original = slot.items[index];
    if (!(original.kind === 'text' && original.editable)) continue;
    const [before, after] = split;
    original.text = before || after;
    if (before && after) {
      slot.items.splice(index + 1, 0, textRun(after, { upright: original.upright, free: original.free }));
    }
  }
  moved.reverse();

  const [firstSlot, firstIndex, , firstSplit] = moves[0];
  const placeAfter = firstSplit !== null && !!firstSplit[0];
  const position = Math.max(0, Math.min(firstIndex + (placeAfter ? 1 : 0), firstSlot.items.length));
  firstSlot.items.splice(position, 0, node);
  target.items = moved;
  return [firstSlot, position];
}

/** 输出预览使用 mathtext，遇到矩阵时应切换到画布渲染（网页版由 KaTeX 处理）。 */
function containsMatrix(slot) {
  for (const item of slot.items) {
    if (item.kind === 'matrix') return true;
    for (const child of childSlots(item)) {
      if (containsMatrix(child)) return true;
    }
  }
  return false;
}

function serializeText(text) {
  let out = '';
  for (const char of text) {
    out += Object.prototype.hasOwnProperty.call(SYMBOL_LATEX, char) ? SYMBOL_LATEX[char] : char;
  }
  return out;
}

// -- LaTeX 序列化 -------------------------------------------------------------

function serializeItem(item) {
  switch (item.kind) {
    case 'text':
      return item.upright ? '\\mathrm{' + item.text + '}' : serializeText(item.text);
    case 'placeholder':
      return item.free ? '' : PLACEHOLDER;
    case 'sum':
      return '\\sum_{' + serializeSlot(item.lower) + '}^{' + serializeSlot(item.upper) + '} ' + serializeSlot(item.body);
    case 'integral':
      return '\\int_{' + serializeSlot(item.lower) + '}^{' + serializeSlot(item.upper) + '} '
        + serializeSlot(item.body) + '\\,\\mathrm{d}' + serializeSlot(item.var);
    case 'fraction':
      return '\\frac{' + serializeSlot(item.numerator) + '}{' + serializeSlot(item.denominator) + '}';
    case 'power':
      return '{' + serializeSlot(item.base) + '}^{' + serializeSlot(item.exponent) + '}';
    case 'subscript':
      return '{' + serializeSlot(item.base) + '}_{' + serializeSlot(item.subscript) + '}';
    case 'sub_sup':
      return '{' + serializeSlot(item.base) + '}_{' + serializeSlot(item.subscript) + '}^{' + serializeSlot(item.superscript) + '}';
    case 'accent': {
      const command = ACCENT_LATEX[item.mark] || '\\hat';
      return command + '{' + serializeSlot(item.body) + '}';
    }
    case 'root':
      if (item.index === null) return '\\sqrt{' + serializeSlot(item.radicand) + '}';
      return '\\sqrt[' + serializeSlot(item.index) + ']{' + serializeSlot(item.radicand) + '}';
    case 'matrix': {
      const rows = item.rows.map((row) => row.map((cell) => serializeSlot(cell)).join(' & '));
      return '\\begin{pmatrix} ' + rows.join(' \\\\ ') + ' \\end{pmatrix}';
    }
    default:
      return '';
  }
}

function serializeSlot(slot) {
  return slot.items.map((item) => serializeItem(item)).join('');
}

// -- 纯函数 -------------------------------------------------------------------

function stripMathDelimiters(source) {
  let s = source.trim();
  const pairs = [['$$', '$$'], ['$', '$'], ['\\[', '\\]'], ['\\(', '\\)']];
  for (const [left, right] of pairs) {
    if (s.length > left.length + right.length && s.startsWith(left) && s.endsWith(right)) {
      s = s.slice(left.length, s.length - right.length).trim();
    }
  }
  return s;
}

/** 把换行、制表符统一换成普通空格：画布上的文本不保留排版空白。 */
function flattenText(text) {
  return text.replace(/\r\n/g, ' ').replace(/\r/g, ' ').replace(/\n/g, ' ').replace(/\t/g, ' ');
}

function normalizeFormula(source) {
  return stripMathDelimiters(flattenText(source)).trim();
}

function toMarkdown(latex) {
  return '$$\n' + normalizeFormula(latex) + '\n$$';
}

function formatPreviewError(error) {
  const message = String((error && error.message) || error || '').trim();
  if (!message) return '无法解析该公式。';
  const lines = message.split('\n').map((line) => line.trim()).filter((line) => line);
  let last = lines.length ? lines[lines.length - 1] : '无法解析该公式。';
  if (last.length > 180) last = last.slice(0, 177) + '...';
  return last;
}
