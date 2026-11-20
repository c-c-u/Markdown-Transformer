/* 主控制器：公式编辑交互与输出控制（对应 formula_editor_app/app.py）。
 *
 * 通过一个 host 接口与平台解耦：
 *   host.setStatus(message, kind)          状态栏文字
 *   host.alert(title, message)             警告弹窗
 *   host.focus()                           让画布获得键盘焦点
 *   host.setCursor(name)                   'arrow' | 'text' | 'hand'
 *   host.canvasWidth()                     画布 CSS 宽度
 *   host.windowHeight()                    窗口高度（决定画布最高能长到多少）
 *   host.prepareCanvas(cssWidth, cssHeight)  调整画布的像素尺寸
 *   host.devicePixelRatio()
 *   host.syncMarkdown(markdown)            更新 Markdown 源码区与复制按钮
 *   host.renderPreview(latex, message)     更新渲染预览区
 *   host.schedule(callback, delayMs) -> id 延时任务（防抖）
 *   host.cancel(id)
 *   host.copyToClipboard(text, done)       done(ok: boolean)
 *   host.canvas / host.ctx                 画布元素与 2D 上下文
 */
'use strict';

function smallestOverlap(items, x, y, margin) {
  const slack = margin || 0;
  let best = null;
  let bestArea = null;
  for (const item of items) {
    if (!(item.x1 - slack <= x && x <= item.x2 + slack)) continue;
    if (!(item.y1 - slack <= y && y <= item.y2 + slack)) continue;
    const area = (item.x2 - item.x1) * (item.y2 - item.y1);
    if (bestArea === null || area < bestArea) {
      best = item;
      bestArea = area;
    }
  }
  return best;
}

class EditorApp {
  constructor(host) {
    this.host = host;
    this.canvas = host.canvas;
    this.ctx = host.ctx;

    this.rootSlot = {
      items: [{ kind: 'placeholder', free: true }],
      role: '公式',
      row: true,
    };
    this.activeSlot = this.rootSlot;
    this.activeIndex = 0;
    this.caret = 0;

    this.undoStack = [];
    this.redoStack = [];

    // 拖动选择：anchor 是按下鼠标的位置，focus 是当前拖动到的位置。
    this.selectionAnchor = null;
    this.selectionFocus = null;
    this.selectionAnchorPoint = null;
    this.selectionDragging = false;
    this.selectionSegments = [];

    this.canvasJob = null;
    this.outputJob = null;
    this.canvasSize = [0, 0];
    this.requestedCanvasHeight = MIN_CANVAS_HEIGHT;
    this.hitAreas = [];
    this.nodeBoxes = [];
    this.baseSize = BASE_FONT_SIZE;
    this.currentMarkdown = '';
    this.lastCursor = 'arrow';
    this.lastLayout = null;

    this.selectionPaintKeys = new Map();
    this.selectionSlots = new Set();
    this.engine = {
      activeSlot: this.activeSlot,
      activeIndex: this.activeIndex,
      caret: this.caret,
      selectionPaintKeys: this.selectionPaintKeys,
      selectionSlots: this.selectionSlots,
      mathFont: MATH_FONT,
      symbolFont: SYMBOL_FONT,
    };
  }

  /** 初始化：设置初始状态并排一次画布。 */
  start() {
    this.host.setStatus(
      '就绪：输入公式，或用按钮插入模板；←/→ 切换输入位置，↑/↓ 在算符内的上下格位间移动。',
      'muted',
    );
    this._update_canvas_status();
    this._sync_markdown_source();
    this._schedule_output_preview(0);
    this._schedule_canvas_render(60);
  }

  // -- 调度 -----------------------------------------------------------------

  _schedule_canvas_render(delay) {
    if (this.canvasJob !== null) this.host.cancel(this.canvasJob);
    this.canvasJob = this.host.schedule(() => this._render_canvas(), delay === undefined ? 40 : delay);
  }

  _schedule_output_preview(delay) {
    if (this.outputJob !== null) this.host.cancel(this.outputJob);
    this.outputJob = this.host.schedule(() => this._update_output_preview(), delay === undefined ? 260 : delay);
  }

  handleResize() {
    this._schedule_canvas_render(50);
  }

  // -- 画布渲染 ---------------------------------------------------------------

  _canvas_max_height() {
    let rootHeight = this.host.windowHeight();
    if (rootHeight < 400) rootHeight = 900;
    return Math.max(MIN_CANVAS_HEIGHT + 40, Math.min(MAX_CANVAS_HEIGHT, rootHeight - 600));
  }

  _render_canvas() {
    this.canvasJob = null;
    const width = this.host.canvasWidth();
    if (width <= 20) {
      this.canvasJob = this.host.schedule(() => this._render_canvas(), 50);
      return;
    }

    // 让方框在选中时也使用选中底色：渲染前告诉布局哪些方框被选中。
    let state = this._selection_state();
    let selectionRange = state[0];
    let selected = state[1];
    if (selectionRange !== null && this._selection_is_empty(selected)) {
      // 收拢到光标（宽度为 0）的选择不再算“选中”，方框按普通编辑态绘制。
      selectionRange = null;
      selected = [];
    }
    this.selectionPaintKeys = new Map();
    this.selectionSlots = new Set();
    if (selectionRange !== null) {
      for (const segment of selected) {
        if (!this.selectionPaintKeys.has(segment.slot)) this.selectionPaintKeys.set(segment.slot, new Set());
        this.selectionPaintKeys.get(segment.slot).add(segment.index);
      }
    }
    this.engine.selectionPaintKeys = this.selectionPaintKeys;
    this.engine.selectionSlots = this.selectionSlots;
    try {
      this._render_canvas_body(width);
    } finally {
      this.selectionPaintKeys = new Map();
      this.selectionSlots = new Set();
      this.engine.selectionPaintKeys = this.selectionPaintKeys;
      this.engine.selectionSlots = this.selectionSlots;
    }
  }

  _render_canvas_body(width) {
    this.engine.activeSlot = this.activeSlot;
    this.engine.activeIndex = this.activeIndex;
    this.engine.caret = this.caret;

    const availW = width - 44;
    const maxHeight = this._canvas_max_height();

    // 先按较大字号试排；内容放不下时画布会自动长高（最多 maxHeight）。
    const fitted = fitLayout(this.engine, this.rootSlot, availW, maxHeight - CANVAS_PADDING, AUTO_FIT_SIZES);
    let layout = fitted[0];
    const chosenSize = fitted[1];

    const contentHeight = layout.ascent + layout.descent;
    const desiredHeight = Math.round(
      Math.min(maxHeight, Math.max(MIN_CANVAS_HEIGHT, contentHeight + CANVAS_PADDING)),
    );
    this.requestedCanvasHeight = desiredHeight;
    this.host.prepareCanvas(width, desiredHeight);

    this.baseSize = chosenSize;
    // 布局先平移到画布坐标，再统一绘制：命中区域和结构包围盒一并跟着平移。
    const xOffset = (width - layout.width) / 2;
    const baselineOffset = (desiredHeight - contentHeight) / 2 + layout.ascent;
    layout = shiftLayout(layout, xOffset, baselineOffset);
    this.hitAreas = layout.hits;
    this.nodeBoxes = layout.nodes;
    this.lastLayout = layout;

    layout.selection = this._selection_rows(layout);
    paintLayoutToCanvas(this.ctx, this.canvas, layout, 0.0, 0.0, width, desiredHeight, this.host.devicePixelRatio());
    this._update_canvas_status();
  }

  _find_hit(x, y) {
    return smallestOverlap(this.hitAreas, x, y, 0);
  }

  // -- 拖动选择 ---------------------------------------------------------------

  _collect_segments() {
    const maps = this._bounds_maps(this.hitAreas, this.nodeBoxes);
    const textBounds = maps[0];
    const nodeBounds = maps[1];

    const segments = [];
    for (const [slot, index, item] of iterSelectableSegments(this.rootSlot)) {
      const hit = textBounds.get(slot) ? textBounds.get(slot).get(index) : null;
      if (hit) {
        segments.push(makeSelectionSegment(item, slot, index, hit.x1, hit.y1, hit.x2, hit.y2));
        continue;
      }
      const node = nodeBounds.get(slot) ? nodeBounds.get(slot).get(index) : null;
      if (node) {
        segments.push(makeSelectionSegment(item, slot, index, node.x1, node.y1, node.x2, node.y2));
      }
    }

    segments.sort((a, b) => (a.x1 - b.x1) || (a.y1 - b.y1));
    return segments;
  }

  /** 按槽位/下标建索引：文本/方框的命中区 与 结构包围盒各一张表。 */
  _bounds_maps(hits, nodes) {
    const textBounds = new Map();
    for (const hit of hits) {
      if (hit.kind !== 'text' && hit.kind !== 'placeholder') continue;
      if (!textBounds.has(hit.slot)) textBounds.set(hit.slot, new Map());
      textBounds.get(hit.slot).set(hit.index, hit);
    }
    const nodeBounds = new Map();
    for (const node of nodes) {
      if (!nodeBounds.has(node.parentSlot)) nodeBounds.set(node.parentSlot, new Map());
      nodeBounds.get(node.parentSlot).set(node.index, node);
    }
    return [textBounds, nodeBounds];
  }

  _segment_at(segments, x, y) {
    return smallestOverlap(segments, x, y, 1.0);
  }

  _text_hit_for(segment) {
    for (const hit of this.hitAreas) {
      if (hit.slot === segment.slot && hit.index === segment.index && hit.kind === 'text') {
        return hit;
      }
    }
    return null;
  }

  _point_for_segment(segment, x) {
    let offset = 0;
    if (segment.item.kind === 'text') {
      const hit = this._text_hit_for(segment);
      if (hit !== null && hit.charPositions) {
        offset = Math.min(
          textOffsetFromCaret(hit.charPositions, x),
          textLength(segment.item.text),
        );
      }
    }
    return [this.selectionSegments.indexOf(segment), offset];
  }

  /**
   * 拖选时不能作为焦点目标的片段（Map<slot, Set<index>>）：锚点所在格位的外层结构。
   *
   * 指针还停在锚点文字所在的这一行里时，锚点所在格位的外层结构不参与焦点
   * 判定：否则在分式分子里拖出一点点（还没离开这一行），焦点就会跳到整个
   * 分式上，把分母里的内容也一起选中。指针离开这一行后恢复正常，把文本
   * 拖到算符上仍然会整体选中它。
   */
  _anchor_row_exclusions(y) {
    if (this.selectionAnchor === null) return null;
    const position = this.selectionAnchor[0];
    if (!(position >= 0 && position < this.selectionSegments.length)) return null;
    const anchor = this.selectionSegments[position];
    if (!(anchor.y1 <= y && y <= anchor.y2)) return null;
    const parents = slotParents(this.rootSlot);
    const excluded = new Map();
    let slot = anchor.slot;
    while (parents.has(slot)) {
      const [parentSlot, index] = parents.get(slot);
      if (!excluded.has(parentSlot)) excluded.set(parentSlot, new Set());
      excluded.get(parentSlot).add(index);
      slot = parentSlot;
    }
    return excluded.size ? excluded : null;
  }

  _selection_point_at(x, y) {
    const segments = this.selectionSegments;
    if (!segments.length) return null;
    const excluded = this._anchor_row_exclusions(y);
    let candidates = segments;
    if (excluded !== null) {
      candidates = segments.filter((segment) => {
        const indexes = excluded.get(segment.slot);
        return !(indexes && indexes.has(segment.index));
      });
      if (!candidates.length) candidates = segments;
    }
    let segment = this._segment_at(candidates, x, y);
    if (segment === null) {
      // 点在空白处时取水平距离最近的片段，方便拖到行首/行尾。
      segment = candidates.reduce((best, seg) => {
        const distance = Math.min(Math.abs(seg.x1 - x), Math.abs(seg.x2 - x));
        const bestDistance = Math.min(Math.abs(best.x1 - x), Math.abs(best.x2 - x));
        return distance < bestDistance ? seg : best;
      });
    }
    return this._point_for_segment(segment, x);
  }

  /** 返回 [选择范围, 选中片段列表]；选择为空时返回 [null, []]。 */
  _selection_state() {
    if (this.selectionAnchor === null || this.selectionFocus === null) return [null, []];
    return selectedSegmentsRange(
      this.selectionSegments,
      this.selectionAnchor[0],
      this.selectionAnchor[1],
      this.selectionFocus[0],
      this.selectionFocus[1],
    );
  }

  /** 选择收拢到光标（没有选中任何字符/方框）时返回 true。 */
  _selection_is_empty(selected) {
    if (!selected.length) return true;
    if (selected.length > 1) return false;
    return selected.every((segment) => segment.offset !== null && segment.offset[0] === segment.offset[1]);
  }

  _has_selection() {
    const state = this._selection_state();
    if (state[0] === null || !state[1].length) return false;
    return !this._selection_is_empty(state[1]);
  }

  _collapse_selection() {
    this.selectionAnchor = null;
    this.selectionFocus = null;
    this.selectionAnchorPoint = null;
    this.selectionDragging = false;
    this.selectionSegments = [];
  }

  /** 把选中内容换算成高亮矩形（坐标用布局坐标，由绘制统一加偏移）。 */
  _selection_rows(layout) {
    const state = this._selection_state();
    if (state[0] === null) return [];

    const maps = this._bounds_maps(layout.hits, layout.nodes);
    const textBounds = maps[0];
    const nodeBounds = maps[1];

    const rows = [];
    for (const segment of state[1]) {
      const hit = textBounds.get(segment.slot) ? textBounds.get(segment.slot).get(segment.index) : null;
      const node = nodeBounds.get(segment.slot) ? nodeBounds.get(segment.slot).get(segment.index) : null;
      let x1;
      let y1;
      let x2;
      let y2;
      if (isStructureItem(segment.item)) {
        if (!node) continue;
        x1 = node.x1;
        y1 = node.y1;
        x2 = node.x2;
        y2 = node.y2;
      } else {
        if (!hit) continue;
        x1 = hit.x1;
        y1 = hit.y1;
        x2 = hit.x2;
        y2 = hit.y2;
        if (hit.kind === 'text' && hit.charPositions && segment.item.kind === 'text' && segment.offset !== null) {
          const edges = textCaretPositions(hit.charPositions, segment.offset[0], segment.offset[1]);
          x1 = edges[0];
          x2 = edges[1];
        }
      }
      if (x2 - x1 < 2) x2 = x1 + 2;
      rows.push({ index: 0, offset: segment.offset, x1: x1, y1: y1, x2: x2, y2: y2 });
    }
    return rows;
  }

  _segment_index_for(slot, index) {
    for (let position = 0; position < this.selectionSegments.length; position += 1) {
      const segment = this.selectionSegments[position];
      if (segment.slot === slot && segment.index === index) return position;
    }
    return null;
  }

  _target_index(targets) {
    for (let position = 0; position < targets.length; position += 1) {
      if (targets[position][0] === this.activeSlot && targets[position][1] === this.activeIndex) {
        return position;
      }
    }
    return null;
  }

  // -- 鼠标 -------------------------------------------------------------------

  _on_canvas_drag_start(event) {
    const x = event.x;
    const y = event.y;
    const hit = this._find_hit(x, y);
    // 选择只能从“内容”（已填写的文本）上开始：空方框、空位以及它们周围的
    // 空白都不能作为选择起点，避免拖选空方框后把它删掉。
    const item = hit !== null && hit.index >= 0 && hit.index < hit.slot.items.length
      ? hit.slot.items[hit.index]
      : null;
    let textHit = null;
    if (item !== null && item.kind === 'text' && (hit.kind === 'text' || hit.kind === 'text-edge-left' || hit.kind === 'text-edge-right')) {
      textHit = this._text_hit_for({ slot: hit.slot, index: hit.index, item: item });
    }
    this._collapse_selection();
    this.selectionSegments = this._collect_segments();
    const segmentIndex = textHit !== null ? this._segment_index_for(hit.slot, hit.index) : null;
    if (textHit === null || segmentIndex === null) {
      return this._handle_plain_click(x, y);
    }
    let offset = 0;
    if (textHit.charPositions) {
      offset = Math.min(textOffsetFromCaret(textHit.charPositions, x), textLength(item.text));
    }
    this.selectionAnchor = [segmentIndex, offset];
    this.selectionFocus = [segmentIndex, offset];
    this.selectionAnchorPoint = [x, y];
    this.selectionDragging = false;
    return 'break';
  }

  _on_canvas_drag_motion(event) {
    if (this.selectionAnchor === null || this.selectionAnchorPoint === null) return 'break';
    const x = event.x;
    const y = event.y;
    const hit = this._find_hit(x, y);
    if (hit !== null && hit.kind === 'placeholder') {
      // 鼠标停在空方框上：不把选择扩展到它所属的结构，空方框不参与选择。
      return 'break';
    }
    const ax = this.selectionAnchorPoint[0];
    const ay = this.selectionAnchorPoint[1];
    if (!this.selectionDragging) {
      if (Math.abs(x - ax) < 4 && Math.abs(y - ay) < 4) return 'break';
      this.selectionDragging = true;
    }
    const point = this._selection_point_at(x, y);
    if (point === null) return 'break';
    if (this.selectionFocus !== null && point[0] === this.selectionFocus[0] && point[1] === this.selectionFocus[1]) {
      return 'break';
    }
    this.selectionFocus = point;
    this._render_canvas();
    return 'break';
  }

  _on_canvas_drag_end(event) {
    const x = event.x;
    const y = event.y;
    this.selectionAnchorPoint = null;
    if (!this.selectionDragging) {
      this._collapse_selection();
      return this._handle_plain_click(x, y);
    }
    this.selectionDragging = false;
    this._render_canvas();
    if (this._has_selection()) {
      this.host.focus();
      this.host.setStatus('已选中一段内容；直接输入可替换，Backspace/Delete 可删除。', 'info');
    } else {
      this._collapse_selection();
      this._render_canvas();
    }
    return 'break';
  }

  _handle_plain_click(x, y) {
    this._collapse_selection();
    this.host.focus();
    const hit = this._find_hit(x, y);
    if (hit !== null && (hit.kind === 'text-edge-left' || hit.kind === 'text-edge-right')) {
      if (hit.slot.row) {
        return this._add_text_edge_input(hit, hit.kind.endsWith('left') ? 'left' : 'right');
      }
      // 非行内槽位（上下限、分子分母、角标底数/上下标、矩阵单元格等）里
      // 不新增输入位置：点击文本前后只定位光标，不能在方框外长出新的结构。
      const item = hit.index >= 0 && hit.index < hit.slot.items.length ? hit.slot.items[hit.index] : null;
      if (item === null || item.kind !== 'text') return 'break';
      this.activeSlot = hit.slot;
      this.activeIndex = hit.index;
      this.caret = hit.kind === 'text-edge-left' ? 0 : textLength(item.text);
      this._render_canvas();
      this.host.setStatus('正在编辑：' + hit.slot.role + '；输入数字或字母即可。', 'info');
      return 'break';
    }

    if (hit !== null) {
      const item = hit.index >= 0 && hit.index < hit.slot.items.length ? hit.slot.items[hit.index] : null;
      if (item === null || (item.kind !== 'placeholder' && item.kind !== 'text')) return 'break';
      this.activeSlot = hit.slot;
      this.activeIndex = hit.index;
      if (hit.kind === 'text' && hit.charPositions) {
        const edgeLeft = hit.charPositions[0];
        const edgeRight = hit.charPositions[hit.charPositions.length - 1];
        const width = Math.max(1.0, edgeRight - edgeLeft);
        if (x <= edgeLeft + width * 0.35) {
          // 点在这段文本的左半部分（含左侧边缘扩展区）：光标落在文本开头。
          this.caret = 0;
        } else {
          let offset = Math.min(textOffsetFromCaret(hit.charPositions, x), textLength(item.text));
          // 光标是“字符之间”的位置：点第 i 个字符左半边时落在 i 处。
          const limit = Math.min(textLength(item.text), hit.charPositions.length - 2);
          for (let charIndex = 0; charIndex < limit; charIndex += 1) {
            const leftPos = hit.charPositions[charIndex];
            const rightPos = hit.charPositions[charIndex + 1];
            if (leftPos <= x && x < (leftPos + rightPos) / 2) {
              offset = charIndex;
              break;
            }
          }
          this.caret = Math.min(offset, textLength(item.text));
        }
      } else {
        this.caret = 0;
      }
      this._render_canvas();
      this.host.setStatus('正在编辑：' + hit.slot.role + '；输入数字或字母即可。', 'info');
      return 'break';
    }

    // 点在结构（算符）左右两侧：光标进入该结构前后的隐藏位置。
    const side = this._structure_side_at(x, y);
    if (side !== null) {
      this._focus_structure_side(side[0], side[1]);
      return 'break';
    }

    // 点在结构（算符）上：落到它第一个空方框，或它右侧的隐藏位置。
    const segment = this._segment_at(this._collect_segments(), x, y);
    if (segment !== null && isStructureItem(segment.item)) {
      this._select_first_placeholder_of(segment.item);
      this.host.focus();
      return 'break';
    }
    this._render_canvas();
    return 'break';
  }

  /** 找出鼠标所在的结构侧边区域，返回 [结构包围盒, "left"/"right"]。 */
  _structure_side_at(x, y) {
    const margin = STRUCTURE_SIDE_MARGIN;
    let best = null;
    for (const node of this.nodeBoxes) {
      if (!(node.y1 - margin <= y && y <= node.y2 + margin)) continue;
      let distance;
      let side;
      if (node.x1 - margin <= x && x < node.x1) {
        distance = node.x1 - x;
        side = 'left';
      } else if (node.x2 < x && x <= node.x2 + margin) {
        distance = x - node.x2;
        side = 'right';
      } else {
        continue;
      }
      if (best === null || distance < best[0]) best = [distance, node, side];
    }
    if (best === null) return null;
    return [best[1], best[2]];
  }

  /** 把光标放到结构左侧/右侧的隐藏位置（必要时补一个隐藏空位）。 */
  _focus_structure_side(node, side) {
    const slot = node.parentSlot;
    const index = node.index;
    if (!(index >= 0 && index < slot.items.length) || slot.items[index] !== node.node) {
      this._render_canvas();
      return;
    }

    if (side === 'left') {
      let position = index - 1;
      const needInsert = position < 0 || !isEditableInput(slot.items[position]);
      if (needInsert) {
        this._push_undo();
        slot.items.splice(index, 0, { kind: 'placeholder', free: true });
        position = index;
        this.activeSlot = slot;
        this.activeIndex = position;
        this.caret = 0;
        this._after_formula_change();
      } else {
        const item = slot.items[position];
        this._set_active(slot, position, item.kind === 'text' ? textLength(item.text) : 0);
      }
    } else {
      let position = index + 1;
      const needInsert = position >= slot.items.length || !isEditableInput(slot.items[position]);
      if (needInsert) {
        this._push_undo();
        slot.items.splice(index + 1, 0, { kind: 'placeholder', free: true });
        position = index + 1;
        this.activeSlot = slot;
        this.activeIndex = position;
        this.caret = 0;
        this._after_formula_change();
      } else {
        this._set_active(slot, position, 0);
      }
    }
    this.host.setStatus('已定位到算符旁边的输入位置；直接输入或插入结构即可。', 'info');
    this.host.focus();
  }

  _add_text_edge_input(hit, side) {
    const slot = hit.slot;
    const index = hit.index;
    if (!(index >= 0 && index < slot.items.length) || slot.items[index].kind !== 'text') return 'break';

    const neighborIndex = side === 'left' ? index - 1 : index + 1;
    if (neighborIndex >= 0 && neighborIndex < slot.items.length) {
      const neighbor = slot.items[neighborIndex];
      if (neighbor.kind === 'placeholder') {
        this._set_active(slot, neighborIndex, 0);
        this.host.setStatus('已定位到文本' + (side === 'left' ? '左' : '右') + '侧的输入位置；直接输入即可。', 'info');
        this.host.focus();
        return 'break';
      }
    }

    const insertAt = side === 'left' ? index : index + 1;
    this._push_undo();
    slot.items.splice(insertAt, 0, { kind: 'placeholder', free: true });
    this.activeSlot = slot;
    this.activeIndex = insertAt;
    this.caret = 0;
    this._after_formula_change();
    this.host.setStatus('已在文本' + (side === 'left' ? '左' : '右') + '侧添加输入位置；可直接输入或插入模板。', 'info');
    this.host.focus();
    return 'break';
  }

  _on_canvas_motion(x, y) {
    const hit = this._find_hit(x, y);
    let cursor;
    if (hit !== null && (hit.kind === 'text-edge-left' || hit.kind === 'text-edge-right') && hit.slot.row) {
      cursor = 'hand';
    } else if (hit !== null) {
      cursor = 'text';
    } else if (this._structure_side_at(x, y) !== null) {
      cursor = 'text';
    } else if (this.selectionSegments.some((segment) => segment.x1 <= x && x <= segment.x2 && segment.y1 <= y && y <= segment.y2)) {
      cursor = 'text';
    } else {
      cursor = 'arrow';
    }
    if (cursor !== this.lastCursor) {
      this.lastCursor = cursor;
      this.host.setCursor(cursor);
    }
  }

  _on_canvas_leave() {
    if (this.selectionDragging) return;
    if (this.lastCursor !== 'arrow') {
      this.lastCursor = 'arrow';
      this.host.setCursor('arrow');
    }
  }

  // -- 活动位置 ---------------------------------------------------------------

  _active_item() {
    if (this.activeSlot === null || this.activeIndex === null) return null;
    if (!(this.activeIndex >= 0 && this.activeIndex < this.activeSlot.items.length)) return null;
    return this.activeSlot.items[this.activeIndex];
  }

  _set_active(slot, index, caret) {
    this.activeSlot = slot;
    this.activeIndex = index;
    this.caret = caret || 0;
    this.host.focus();
    this._render_canvas();
    this._update_canvas_status();
  }

  _select_first_target() {
    const target = firstTarget(this.rootSlot);
    if (target === null) {
      this.activeSlot = null;
      this.activeIndex = 0;
      this.caret = 0;
      return;
    }
    this.activeSlot = target[0];
    this.activeIndex = target[1];
    this.caret = target[2].kind === 'text' ? textLength(target[2].text) : 0;
  }

  _select_first_placeholder_of(node) {
    const target = firstPlaceholderInNode(node);
    if (target !== null) {
      this._set_active(target[0], target[1], 0);
    } else {
      this._select_first_target();
      this._update_canvas_status();
    }
  }

  // -- 撤销/重做 --------------------------------------------------------------

  _push_undo() {
    this.undoStack.push(structuredClone(this.rootSlot));
    if (this.undoStack.length > 100) this.undoStack.shift();
    this.redoStack = [];
  }

  undo() {
    if (!this.undoStack.length) {
      this.host.setStatus('没有可撤销的操作。', 'muted');
      return 'break';
    }
    this.redoStack.push(structuredClone(this.rootSlot));
    this.rootSlot = this.undoStack.pop();
    this._select_first_target();
    this._after_formula_change();
    this.host.setStatus('已撤销一步编辑。', 'muted');
    this.host.focus();
    return 'break';
  }

  redo() {
    if (!this.redoStack.length) {
      this.host.setStatus('没有可重做的操作。', 'muted');
      return 'break';
    }
    this.undoStack.push(structuredClone(this.rootSlot));
    this.rootSlot = this.redoStack.pop();
    this._select_first_target();
    this._after_formula_change();
    this.host.setStatus('已重做一步编辑。', 'muted');
    this.host.focus();
    return 'break';
  }

  // -- 输出 -------------------------------------------------------------------

  _sync_markdown_source() {
    const placeholders = countPlaceholders(this.rootSlot);
    const latex = normalizeFormula(serializeSlot(this.rootSlot));
    const markdown = placeholders > 0 || !latex ? '' : toMarkdown(latex);
    this.currentMarkdown = markdown;
    this.host.syncMarkdown(markdown);
  }

  _update_output_preview() {
    this.outputJob = null;
    const placeholders = countPlaceholders(this.rootSlot);
    const latex = normalizeFormula(serializeSlot(this.rootSlot));

    if (placeholders) {
      this.host.renderPreview('', '还有 ' + placeholders + ' 个方框未填写\n完成全部方框后显示实时预览');
      return;
    }
    if (!latex) {
      this.host.renderPreview('', '填写公式后\n这里显示渲染预览');
      return;
    }
    this.host.renderPreview(latex, '');
  }

  _normalize_free_boundaries() {
    const activeItem = this._active_item();
    const activeSlot = this.activeSlot;
    normalizeFreeBoundaries(this.rootSlot);
    if (activeItem !== null && activeSlot !== null) {
      for (let index = 0; index < activeSlot.items.length; index += 1) {
        if (activeSlot.items[index] === activeItem) {
          this.activeIndex = index;
          break;
        }
      }
    }
  }

  _after_formula_change() {
    this._collapse_selection();
    this._normalize_free_boundaries();
    this._sync_markdown_source();
    this._render_canvas();
    // 未填写完整时只需切换提示文字，可以立即更新；完整公式的渲染稍作防抖。
    this._schedule_output_preview(this.currentMarkdown ? 260 : 0);
    this._update_canvas_status();
  }

  _replace_selection() {
    const state = this._selection_state();
    if (state[0] === null) return null;
    const target = removeSelection(state[1]);
    this._collapse_selection();
    return target;
  }

  // -- 键入 -------------------------------------------------------------------

  _insert_text(text) {
    text = flattenText(text);
    if (!text) return;

    if (this._has_selection()) {
      this._push_undo();
      const target = this._replace_selection();
      if (target !== null) {
        this.activeSlot = target[0];
        this.activeIndex = target[1];
        this.caret = target[2];
        const item = this._active_item();
        if (item !== null && item.kind === 'text' && item.editable) {
          item.text = textInsertAt(item.text, this.caret, text);
          this.caret = this.caret + textLength(text);
        } else if (item !== null && item.kind === 'placeholder') {
          this.activeSlot.items[this.activeIndex] = textRun(text, { free: item.free });
          this.caret = textLength(text);
        }
      }
      this._after_formula_change();
      this.host.focus();
      return;
    }

    let item = this._active_item();
    if (item === null) {
      this._select_first_target();
      item = this._active_item();
      if (item === null) return;
    }

    if (item.kind === 'placeholder') {
      this._push_undo();
      this.activeSlot.items[this.activeIndex] = textRun(text, { free: item.free });
      this.caret = textLength(text);
    } else if (item.kind === 'text' && item.editable) {
      this._push_undo();
      const position = Math.max(0, Math.min(this.caret, textLength(item.text)));
      item.text = textInsertAt(item.text, position, text);
      this.caret = position + textLength(text);
    } else {
      return;
    }

    this._after_formula_change();
    this.host.focus();
  }

  _on_canvas_key(char) {
    if (char && char.length === 1) {
      this._insert_text(char);
    }
    return 'break';
  }

  // -- 删除 -------------------------------------------------------------------

  _delete_selected() {
    const state = this._selection_state();
    if (state[0] === null) return false;
    this._push_undo();
    const target = this._replace_selection();
    if (target !== null) {
      this.activeSlot = target[0];
      this.activeIndex = target[1];
      this.caret = target[2];
    }
    this._after_formula_change();
    this.host.focus();
    return true;
  }

  _delete_structure(direction) {
    if (this.activeSlot === null) return false;
    const target = deleteStructureToward(
      this.activeSlot,
      this.activeIndex,
      this.caret,
      direction,
      this._active_item(),
    );
    if (target === null) return false;
    const slot = target[0];
    let index = target[1];
    if (!(index >= 0 && index < slot.items.length)) return false;
    this._push_undo();
    slot.items.splice(index, 1);
    index = Math.min(index, Math.max(0, slot.items.length - 1));
    if (!slot.items.length) {
      slot.items.push({ kind: 'placeholder', free: true });
      index = 0;
    } else if (!isEditableInput(slot.items[index])) {
      const found = editablePositionLeft(slot, index);
      if (found !== null) index = found;
    }
    this.activeSlot = slot;
    this.activeIndex = index;
    this.caret = 0;
    this._after_formula_change();
    this.host.setStatus('已删除相邻的算符及其内部结构；可用 Ctrl+Z 撤销。', 'muted');
    this.host.focus();
    return true;
  }

  /** 在算符任意格位最前方回格：删除整个算符，并用该格位的内容替换。 */
  _unwrap_structure() {
    if (this.activeSlot === null) return false;
    const plan = planStructureUnwrap(this.activeSlot, this.activeIndex, this.caret, slotParents(this.rootSlot));
    if (plan === null) return false;
    this._push_undo();
    const applied = applyStructureUnwrap(plan);
    const parentSlot = applied[0];
    const start = applied[1];
    const count = applied[2];
    this.activeSlot = parentSlot;
    this.activeIndex = start;
    this.caret = 0;
    this._select_front_of(parentSlot, start, count);
    this._after_formula_change();
    this.host.setStatus('已删除整个算符，并用该格位的内容替换；可用 Ctrl+Z 撤销。', 'muted');
    this.host.focus();
    return true;
  }

  /** 把光标放到刚替换进来的内容最前面。 */
  _select_front_of(slot, start, count) {
    for (let offset = 0; offset < count; offset += 1) {
      const position = start + offset;
      if (position >= slot.items.length) return;
      const item = slot.items[position];
      if (item.kind === 'placeholder' || item.kind === 'text') {
        this.activeIndex = position;
        this.caret = 0;
        return;
      }
      if (isStructureItem(item)) {
        const target = firstPlaceholderInNode(item);
        if (target !== null) {
          this.activeSlot = target[0];
          this.activeIndex = target[1];
          this.caret = 0;
          return;
        }
        // 结构已经填满：把光标放在它右侧的隐藏位置。
        const following = position + 1;
        if (following >= slot.items.length || !isEditableInput(slot.items[following])) {
          slot.items.splice(following, 0, { kind: 'placeholder', free: true });
        }
        this.activeIndex = following;
        this.caret = 0;
        return;
      }
    }
    this.activeIndex = Math.min(start, Math.max(0, slot.items.length - 1));
    this.caret = 0;
  }

  /**
   * 删除光标一侧的相邻元素。
   *
   * 规则优先级：
   * 1. 文本内部：删一个字符；
   * 2. 在算符任意格位最前方按回格：删除整个算符，并用该格位的内容替换；
   * 3. 删除方向上只有结构时：把该结构连同内部内容整体删除；
   * 4. 纯算符文本：只删这个算符字符本身。
   * 绝不在删除方向上跨过文本去删更远的内容。
   */
  _remove_at_caret(backward) {
    const item = this._active_item();
    if (item !== null && item.kind === 'text' && item.editable) {
      if (backward && this.caret > 0) {
        return this._remove_text_char(item, this.caret - 1);
      }
      if (!backward && this.caret < textLength(item.text)) {
        return this._remove_text_char(item, this.caret);
      }
      if (backward) {
        if (this._unwrap_structure()) return true;
        // 纯算符文本（如单独键入的 +）：删掉这个算符字符本身。
        if (item.text && isPlainOperatorText(item.text)) {
          return this._remove_text_char(item, 0);
        }
        return this._delete_structure(-1);
      }
      return this._delete_structure(1);
    }
    if (backward) {
      if (this._unwrap_structure()) return true;
      return this._delete_structure(-1);
    }
    return this._delete_structure(1);
  }

  _remove_text_char(item, position) {
    this._push_undo();
    position = Math.max(0, Math.min(position, textLength(item.text) - 1));
    item.text = textRemoveAt(item.text, position);
    this.caret = position;
    if (!item.text) {
      this.activeSlot.items[this.activeIndex] = { kind: 'placeholder', free: item.free };
      this.caret = 0;
    }
    this._after_formula_change();
    this.host.focus();
    return true;
  }

  _on_backspace() {
    if (this._delete_selected()) return 'break';
    this._remove_at_caret(true);
    this.host.focus();
    return 'break';
  }

  _on_delete() {
    if (this._delete_selected()) return 'break';
    this._remove_at_caret(false);
    this.host.focus();
    return 'break';
  }

  // -- 方向键 -----------------------------------------------------------------

  /**
   * 有选择时把选择收拢到远端（forward）或近端，返回是否收拢过。
   *
   * 收拢后返回 true，调用方据此停止这一次移动：与常见编辑器一致，
   * 方向键的第一下只负责取消选择。
   */
  _collapse_selection_to_edge(forward) {
    if (this.selectionAnchor === null) return false;
    const state = this._selection_state();
    const selected = state[1];
    if (selected.length) {
      const first = selected[0];
      const last = selected[selected.length - 1];
      let slot;
      let index;
      let offset;
      if (forward) {
        slot = last.slot;
        index = last.index;
        offset = last.offset ? last.offset[1] : 0;
      } else {
        slot = first.slot;
        index = first.index;
        offset = first.offset ? first.offset[0] : 0;
      }
      this._collapse_selection();
      this.activeSlot = slot;
      this.activeIndex = index;
      this.caret = offset;
      this._render_canvas();
      this._update_canvas_status();
      this.host.focus();
      return true;
    }
    this._collapse_selection();
    return false;
  }

  _move_caret(step) {
    if (this._collapse_selection_to_edge(step > 0)) return 'break';

    const item = this._active_item();
    if (item !== null && item.kind === 'text' && item.editable) {
      const newCaret = this.caret + step;
      if (newCaret >= 0 && newCaret <= textLength(item.text)) {
        if (newCaret !== this.caret) {
          this.caret = newCaret;
          this._render_canvas();
          this._update_canvas_status();
        }
        this.host.focus();
        return 'break';
      }

      // 光标已到这一段文本的尽头：先进入同一行里紧挨着的相邻结构；
      // 没有相邻结构就停在原地，不要跳到别的方框去。
      const node = adjacentStructure(this.activeSlot, this.activeIndex, step);
      if (node !== null) {
        if (step < 0) {
          this._select_first_placeholder_of(node);
        } else {
          const target = firstTarget(node);
          if (target !== null) this._set_active(target[0], target[1], 0);
        }
        this.host.setStatus('已进入相邻结构；继续按方向键可移动光标。', 'info');
        return 'break';
      }
      const atTextEdge = (step < 0 && this.caret === 0)
        || (step > 0 && this.caret >= textLength(item.text));
      if (atTextEdge) {
        this.host.focus();
        return 'break';
      }
    }

    // 光标已经在文本边界，或当前是空位/空方框：切换到相邻输入位置。
    const targets = [...iterTargets(this.rootSlot)];
    if (!targets.length) {
      this.host.focus();
      return 'break';
    }

    const currentIndex = this._target_index(targets);
    let nextIndex;
    if (currentIndex === null) {
      nextIndex = step > 0 ? 0 : targets.length - 1;
    } else {
      nextIndex = currentIndex + step;
      if (nextIndex < 0 || nextIndex >= targets.length) {
        this.host.focus();
        return 'break';
      }
    }

    const target = targets[nextIndex];
    const targetItem = target[2];
    const caret = targetItem.kind === 'text' ? (step < 0 ? textLength(targetItem.text) : 0) : 0;
    this._set_active(target[0], target[1], caret);
    this.host.setStatus('正在编辑：' + target[0].role + '；←/→ 可继续切换输入位置。', 'info');
    return 'break';
  }

  /**
   * ↑ / ↓：在算符内部按预先写死的格位表切到上/下方最近的格位。
   *
   * direction=-1 是上，1 是下。只在该格位直接所属的算符里找；算符没有
   * 登记这个方向的格位（例如分式分子按 ↑、顶标按 ↓）时停在原地。
   */
  _move_caret_vertical(direction) {
    if (this._collapse_selection_to_edge(direction > 0)) return 'break';
    this.host.focus();
    if (this.activeSlot === null) return 'break';

    const target = verticalNeighbor(this.activeSlot, direction, slotParents(this.rootSlot));
    if (target === null) {
      this.host.setStatus('当前位置所在的结构没有上/下相邻的格位。', 'muted');
      return 'break';
    }

    const position = this._vertical_target_position(target);
    this._set_active(target, position[0], position[1]);
    const arrow = direction < 0 ? '上' : '下';
    this.host.setStatus('已切换到' + arrow + '方的「' + target.role + '」；↑/↓ 可继续切换。', 'info');
    return 'break';
  }

  /** 在目标格位里选一个和当前下标最接近的可编辑位置。 */
  _vertical_target_position(slot) {
    const items = slot.items;
    if (!items.length) return [0, 0];
    const wanted = Math.max(0, Math.min(this.activeIndex, items.length - 1));
    const editable = [];
    for (let position = 0; position < items.length; position += 1) {
      if (isEditableInput(items[position])) editable.push(position);
    }
    if (!editable.length) return [wanted, 0];
    let index = editable[0];
    let best = [Math.abs(editable[0] - wanted), editable[0]];
    for (const position of editable) {
      const key = [Math.abs(position - wanted), position];
      if (key[0] < best[0] || (key[0] === best[0] && key[1] < best[1])) {
        best = key;
        index = position;
      }
    }
    const item = items[index];
    if (item.kind === 'text' && item.editable) {
      return [index, Math.max(0, Math.min(this.caret, textLength(item.text)))];
    }
    return [index, 0];
  }

  _move_selection(direction) {
    this._collapse_selection();
    const targets = [...iterTargets(this.rootSlot)];
    if (!targets.length) return 'break';
    const currentIndex = this._target_index(targets);
    let nextIndex;
    if (currentIndex === null) {
      nextIndex = direction > 0 ? 0 : targets.length - 1;
    } else {
      nextIndex = (currentIndex + direction + targets.length) % targets.length;
    }
    const target = targets[nextIndex];
    const caret = target[2].kind === 'text' ? textLength(target[2].text) : 0;
    this._set_active(target[0], target[1], caret);
    this._update_canvas_status();
    return 'break';
  }

  // -- 插入结构 / 符号 ---------------------------------------------------------

  _insert_node(node, label) {
    const item = this._active_item();
    const slot = this.activeSlot;

    if (slot !== null && slot.row === false && item !== null && item.kind === 'text' && item.text) {
      // 上下限、分子分母、角标底数/上下标、矩阵单元格等方框只放一个结构：
      // 已经填了内容时不能再往里塞新结构（否则结构会“长”到方框外面）。
      this.host.setStatus(
        slot.role + '里已经有内容，这个位置只能放一个结构；请先清空再插入' + label + '。',
        'warning',
      );
      this.host.focus();
      return;
    }

    this._push_undo();

    let placed = false;
    if (item !== null && item.kind === 'placeholder') {
      slot.items[this.activeIndex] = node;
      placed = true;
    } else if (item !== null && item.kind === 'text' && item.editable) {
      slot.items.splice(this.activeIndex + 1, 0, node);
      placed = true;
    }
    if (!placed) this.rootSlot.items.push(node);

    this._select_first_placeholder_of(node);
    this._after_formula_change();
    this.host.setStatus('已插入' + label + '，依次填写方框即可。', 'info');
    this.host.focus();
  }

  insert_template(key) {
    const node = makeTemplate(key);
    this._insert_node(node, TEMPLATE_LABELS[key]);
  }

  insert_matrix(rows, cols, kind) {
    const role = kind === 'vector' ? '向量元素' : '矩阵元素';
    const node = makeMatrixNode(rows, cols, role);
    const label = rows + '×' + cols + ' ' + (kind === 'vector' ? '列向量' : '矩阵');
    this._insert_node(node, label);
  }

  insert_symbol(glyph) {
    this._insert_text(glyph);
    this.host.focus();
  }

  clear_formula() {
    if (!this.rootSlot.items.length) return;
    this._push_undo();
    this.rootSlot = { items: [{ kind: 'placeholder', free: true }], role: '公式', row: true };
    this.activeSlot = this.rootSlot;
    this.activeIndex = 0;
    this.caret = 0;
    this._after_formula_change();
    this.host.setStatus('已清空公式，可用 Ctrl+Z 撤销。', 'muted');
    this.host.focus();
  }

  // -- 复制与状态 -------------------------------------------------------------

  _update_canvas_status() {
    const state = this._selection_state();
    const selectionRange = state[0];
    const selected = state[1];
    let message;
    if (selectionRange !== null && selected.length) {
      const structures = selected.filter((segment) => isStructureItem(segment.item)).length;
      if (structures) {
        message = '已选中 ' + selected.length + ' 段内容（含 ' + structures + ' 个算符/结构）；输入可替换，Backspace 可删除';
      } else {
        message = '已选中 ' + selected.length + ' 段文本；输入可替换，Backspace 可删除';
      }
      this.host.setCanvasStatus(message);
      return;
    }

    const item = this._active_item();
    if (item === null) {
      message = '点击画布中的输入位置开始输入';
    } else if (item.kind === 'placeholder') {
      const kind = item.free ? '空位' : '空方框';
      message = '正在编辑：' + this.activeSlot.role + '（' + kind + '）';
    } else if (item.kind === 'text') {
      let content = item.text || '空';
      if (textLength(content) > 24) content = textSlice(content, 0, 21) + '...';
      message = '正在编辑：' + this.activeSlot.role + ' · ' + content;
    } else {
      message = '点击画布中的输入位置开始输入';
    }
    const remaining = countPlaceholders(this.rootSlot);
    if (remaining) {
      message += ' · 还有 ' + remaining + ' 个必填方框待填写';
    } else if (normalizeFormula(serializeSlot(this.rootSlot))) {
      message += ' · 所有必填方框已填写，可以复制';
    } else {
      message += ' · 输入公式后可复制';
    }
    this.host.setCanvasStatus(message);
  }

  copy_markdown() {
    if (!this.currentMarkdown) {
      const placeholders = countPlaceholders(this.rootSlot);
      if (placeholders) {
        let firstPlaceholder = null;
        for (const entry of iterPlaceholders(this.rootSlot)) {
          firstPlaceholder = entry;
          break;
        }
        if (firstPlaceholder !== null) {
          this._set_active(firstPlaceholder[0], firstPlaceholder[1], 0);
        }
        this.host.alert(
          '还有方框未填写',
          '公式中还有 ' + placeholders + ' 个方框没有填写。\n请点击方框（或按 Tab）补齐内容后再复制。',
        );
        this.host.setStatus('复制未完成：还有 ' + placeholders + ' 个必填方框待填写。', 'warning');
      } else {
        this.host.alert('还没有公式', '请先在公式中填写内容。');
        this.host.setStatus('复制未完成：公式为空。', 'warning');
      }
      this.host.focus();
      return;
    }

    this.host.copyToClipboard(this.currentMarkdown, (ok) => {
      if (ok) {
        this.host.setStatus('Markdown 已复制到剪贴板。', 'success');
      } else {
        this.host.alert('复制失败', '无法访问剪贴板：浏览器拒绝了复制请求。');
      }
    });
  }

  // -- 键盘事件入口（由 UI 层调用） -------------------------------------------

  handleKeyDown(event) {
    const key = event.key;
    if (event.ctrlKey || event.metaKey) {
      if (key === 'z' || key === 'Z') {
        return this.undo();
      }
      if (key === 'y' || key === 'Y') {
        return this.redo();
      }
      return undefined;
    }
    switch (key) {
      case 'Backspace': return this._on_backspace();
      case 'Delete': return this._on_delete();
      case 'ArrowLeft': return this._move_caret(-1);
      case 'ArrowRight': return this._move_caret(1);
      case 'ArrowUp': return this._move_caret_vertical(-1);
      case 'ArrowDown': return this._move_caret_vertical(1);
      case 'Tab': return this._move_selection(event.shiftKey ? -1 : 1);
      case 'Enter': return this._copy_enter();
      default:
        if (key && key.length === 1 && !event.altKey) {
          return this._on_canvas_key(key);
        }
        return undefined;
    }
  }

  _copy_enter() {
    this.copy_markdown();
    return 'break';
  }

  /** 粘贴：由 UI 层从 paste 事件里取出纯文本再交给这里。 */
  paste_text(text) {
    const data = flattenText(text).trim();
    if (data) this._insert_text(data);
  }
}
