/* 画布布局引擎：文本、方框、求和/积分/分式/角标/顶标/根式/矩阵的尺寸与位置。
 * 对应 formula_editor_app/layout.py；去掉了 tkfont，改为 Canvas measureText。 */
'use strict';

// 顶标在画布上绘制的字形；空字符串表示画一条与内容等宽的横线。
const ACCENT_GLYPHS = {
  hat: 'ˆ',
  widehat: 'ˆ',
  bar: '',
  overline: '',
  tilde: '˜',
  widetilde: '˜',
  dot: '˙',
  ddot: '¨',
  vec: '→',
};

// 文本最左/最右侧的可点击扩展区：点击后在该文本旁添加新的输入位置。
const TEXT_EDGE_INSIDE = 4.0;
const TEXT_EDGE_OUTSIDE = 8.0;
// 结构（算符）左右两侧的可点击扩展区：点击后光标进入该结构前后的隐藏位置。
const STRUCTURE_SIDE_MARGIN = 12.0;

// 结构类型 -> 布局方法名。新增结构时在这里补一条，再写对应的 _layout_* 方法。
const STRUCTURE_LAYOUT = {
  sum: 'layoutSum',
  integral: 'layoutIntegral',
  fraction: 'layoutFraction',
  power: 'layoutPower',
  subscript: 'layoutSubscript',
  sub_sup: 'layoutSubsup',
  accent: 'layoutAccent',
  root: 'layoutRoot',
  matrix: 'layoutMatrix',
};

// -- 字体与测量 ---------------------------------------------------------------

let measureContext = null;
const fontMetricsCache = new Map();
const measureCache = new Map();

function getMeasureContext() {
  if (measureContext === null) {
    const canvas = document.createElement('canvas');
    measureContext = canvas.getContext('2d');
  }
  return measureContext;
}

function fontString(size, italic, family) {
  const px = Math.max(8, Math.round(size));
  return (italic ? 'italic ' : '') + px + 'px ' + family;
}

function fontSizeFrom(font) {
  const found = /(\d+(?:\.\d+)?)px/.exec(font);
  return found ? Number(found[1]) : 16;
}

function fontMetrics(font) {
  const cached = fontMetricsCache.get(font);
  if (cached) return cached;
  const ctx = getMeasureContext();
  ctx.font = font;
  const probe = ctx.measureText('x');
  let ascent = probe.fontBoundingBoxAscent;
  let descent = probe.fontBoundingBoxDescent;
  if (!(ascent > 0)) ascent = probe.actualBoundingBoxAscent;
  if (!(descent > 0)) descent = probe.actualBoundingBoxDescent;
  const size = fontSizeFrom(font);
  if (!(ascent > 0)) ascent = size * 0.8;
  if (!(descent > 0)) descent = size * 0.2;
  const result = { ascent: ascent, descent: descent };
  fontMetricsCache.set(font, result);
  return result;
}

function measureFont(font, text) {
  const key = font + '\u0001' + text;
  const cached = measureCache.get(key);
  if (cached) return cached;
  const ctx = getMeasureContext();
  ctx.font = font;
  const metrics = fontMetrics(font);
  const width = text ? ctx.measureText(text).width : 0;
  const result = { width: width, ascent: metrics.ascent, descent: metrics.descent };
  measureCache.set(key, result);
  return result;
}

/** 与桌面版 _font + _measure 等价：返回 [文字宽度, 字体 ascent, 字体 descent]。 */
function measure(engine, size, italic, family, text) {
  const font = fontString(size, italic, family || engine.mathFont);
  const metrics = measureFont(font, text);
  return [metrics.width, metrics.ascent, metrics.descent];
}

/** 与桌面版 _char_font 等价：符号字体正体；非字母正体；有字母判定才斜体。 */
function charFont(engine, char, size, upright) {
  if (SYMBOL_FONT_CHARS.has(char)) {
    return fontString(size, false, engine.symbolFont);
  }
  const italic = !upright && /\p{L}/u.test(char);
  return fontString(size, italic, engine.mathFont);
}

// -- 布局数据结构 -------------------------------------------------------------

function emptyLayout() {
  return { width: 0.0, ascent: 0.0, descent: 0.0, draws: [], hits: [], nodes: [], selection: null };
}

/** 按顺序把若干子布局的绘制项、命中区域和结构包围盒拼成三张表。 */
function mergeLayouts(layouts) {
  const draws = [];
  const hits = [];
  const nodes = [];
  for (const layout of layouts) {
    draws.push(...layout.draws);
    hits.push(...layout.hits);
    nodes.push(...layout.nodes);
  }
  return [draws, hits, nodes];
}

function shiftLayout(layout, dx, dy) {
  const draws = layout.draws.map((draw) => {
    if (draw.type === 'text') {
      return Object.assign({}, draw, { x: draw.x + dx, y: draw.y + dy });
    }
    return Object.assign({}, draw, { x1: draw.x1 + dx, y1: draw.y1 + dy, x2: draw.x2 + dx, y2: draw.y2 + dy });
  });
  const hits = layout.hits.map((hit) => Object.assign({}, hit, {
    x1: hit.x1 + dx,
    y1: hit.y1 + dy,
    x2: hit.x2 + dx,
    y2: hit.y2 + dy,
    charPositions: hit.charPositions ? hit.charPositions.map((p) => p + dx) : null,
  }));
  const nodes = layout.nodes.map((node) => Object.assign({}, node, {
    x1: node.x1 + dx,
    y1: node.y1 + dy,
    x2: node.x2 + dx,
    y2: node.y2 + dy,
  }));
  const selection = layout.selection
    ? layout.selection.map((row) => Object.assign({}, row, {
      x1: row.x1 + dx,
      y1: row.y1 + dy,
      x2: row.x2 + dx,
      y2: row.y2 + dy,
    }))
    : null;
  return {
    width: layout.width,
    ascent: layout.ascent,
    descent: layout.descent,
    draws: draws,
    hits: hits,
    nodes: nodes,
    selection: selection,
  };
}

function isPaintKeySelected(engine, slot, index) {
  const set = engine.selectionPaintKeys.get(slot);
  if (set && set.has(index)) return true;
  return engine.selectionSlots.has(slot);
}

// -- 布局计算 -----------------------------------------------------------------

/**
 * 从大到小试排，返回第一个宽高都放得下的布局及其字号。
 * 全部放不下时退回 sizes 里的最小字号，保证调用方总有布局可用。
 */
function fitLayout(engine, slot, availW, availH, sizes) {
  const trySizes = sizes || AUTO_FIT_SIZES;
  for (const size of trySizes) {
    const layout = layoutSlot(engine, slot, 0.0, 0.0, size);
    if (layout.width <= availW && layout.ascent + layout.descent <= availH) {
      return [layout, size];
    }
  }
  const smallest = trySizes[trySizes.length - 1];
  return [layoutSlot(engine, slot, 0.0, 0.0, smallest), smallest];
}

function childLayout(engine, slot, x, baseline, size) {
  return shiftLayout(layoutSlot(engine, slot, 0.0, 0.0, size), x, baseline);
}

function layoutItem(engine, item, parentSlot, index, x, baseline, size) {
  if (item.kind === 'text') return layoutText(engine, item, parentSlot, index, x, baseline, size);
  if (item.kind === 'placeholder') return layoutPlaceholder(engine, parentSlot, index, x, baseline, size);

  // 结构被选中时，它内部的方框也改用选中底色，避免黄色方框盖住选中效果。
  // 要在布局子槽位之前登记，才能让结构内部的方框也生效。
  const set = engine.selectionPaintKeys.get(parentSlot);
  if (set && set.has(index)) {
    for (const slot of childSlots(item)) engine.selectionSlots.add(slot);
  }

  const methodName = STRUCTURE_LAYOUT[item.kind];
  if (!methodName) return emptyLayout();
  const child = layoutMethods[methodName](engine, item, x, baseline, size);

  // 记录这个结构的整体包围盒（布局信息）。
  child.nodes.push({
    node: item,
    parentSlot: parentSlot,
    index: index,
    x1: x,
    y1: baseline - child.ascent,
    x2: x + child.width,
    y2: baseline + child.descent,
  });
  return child;
}

function layoutSlot(engine, slot, x, baseline, size) {
  const draws = [];
  const hits = [];
  const nodes = [];
  let cursor = x;
  let ascent = 0.0;
  let descent = 0.0;
  const count = slot.items.length;

  for (let index = 0; index < count; index += 1) {
    const child = layoutItem(engine, slot.items[index], slot, index, cursor, baseline, size);
    draws.push(...child.draws);
    hits.push(...child.hits);
    nodes.push(...child.nodes);
    ascent = Math.max(ascent, child.ascent);
    descent = Math.max(descent, child.descent);
    cursor += child.width;
    if (index < count - 1) cursor += ITEM_GAP;
  }

  return { width: cursor - x, ascent: ascent, descent: descent, draws: draws, hits: hits, nodes: nodes, selection: null };
}

function layoutText(engine, item, slot, index, x, baseline, size) {
  const chars = textChars(item.text);
  if (!chars.length) return emptyLayout();

  const groups = [];
  for (const char of chars) {
    const font = charFont(engine, char, size, item.upright);
    const last = groups[groups.length - 1];
    if (last && last.font === font) {
      last.text += char;
    } else {
      groups.push({ text: char, font: font });
    }
  }

  const draws = [];
  const caretPositions = [x];
  let cursor = x;
  let ascent = 0.0;
  let descent = 0.0;

  for (const group of groups) {
    const info = measureFont(group.font, group.text);
    ascent = Math.max(ascent, info.ascent);
    descent = Math.max(descent, info.descent);
    draws.push({ type: 'text', x: cursor, y: baseline + info.descent, text: group.text, font: group.font, fill: TEXT, anchor: 'sw' });
    const groupChars = textChars(group.text);
    for (let k = 1; k <= groupChars.length; k += 1) {
      caretPositions.push(cursor + measureFont(group.font, groupChars.slice(0, k).join('')).width);
    }
    cursor += info.width;
  }

  const active = item.editable && slot === engine.activeSlot && index === engine.activeIndex;
  const y1 = baseline - ascent - 3;
  const y2 = baseline + descent + 3;

  if (active) {
    // 已经处于选中状态时不再画浅色底，否则会盖住选中高亮；只保留光标线。
    const selected = isPaintKeySelected(engine, slot, index);
    if (!selected) {
      draws.unshift({ type: 'rect', x1: x - 3, y1: y1, x2: cursor + 3, y2: y2, fill: SOFT_ACCENT, outline: '', width: 0, dash: null });
    }
    const caretIndex = Math.max(0, Math.min(engine.caret, chars.length));
    const cx = caretPositions[caretIndex];
    draws.push({ type: 'line', x1: cx, y1: y1 + 2, x2: cx, y2: y2 - 2, fill: ACCENT, width: 1.6 });
  }

  const hits = [];
  if (item.editable) {
    // 两端各补一个边缘位置，使字符偏移与点击位置一一对应。
    const caretEdges = [x].concat(caretPositions.slice(1), [cursor]);
    hits.push({ slot: slot, index: index, x1: x - 2, y1: y1, x2: cursor + 2, y2: y2, charPositions: caretEdges, kind: 'text' });
    // 文本左右两端额外提供“添加新项”的可点击区域。
    const inside = TEXT_EDGE_INSIDE;
    const outside = TEXT_EDGE_OUTSIDE;
    hits.push({ slot: slot, index: index, x1: x - outside, y1: y1, x2: x + inside, y2: y2, charPositions: null, kind: 'text-edge-left' });
    hits.push({ slot: slot, index: index, x1: cursor - inside, y1: y1, x2: cursor + outside, y2: y2, charPositions: null, kind: 'text-edge-right' });
  }

  return { width: cursor - x, ascent: ascent, descent: descent, draws: draws, hits: hits, nodes: [], selection: null };
}

function layoutPlaceholder(engine, slot, index, x, baseline, size) {
  const font = fontString(size, false, engine.mathFont);
  const metrics = fontMetrics(font);
  const ascent = metrics.ascent;
  const descent = metrics.descent;
  const active = slot === engine.activeSlot && index === engine.activeIndex;
  const item = index >= 0 && index < slot.items.length ? slot.items[index] : { kind: 'placeholder', free: false };

  if (item.free) {
    // 非结构型空位不画方框；只在获得焦点时显示光标。
    const top = baseline - ascent - 4;
    const bottom = baseline + descent + 4;
    const draws = [];
    if (active) draws.push({ type: 'line', x1: x, y1: top + 3, x2: x, y2: bottom - 3, fill: ACCENT, width: 1.6 });
    return { width: 0.0, ascent: ascent + 4, descent: descent + 4, draws: draws, hits: [], nodes: [], selection: null };
  }

  const boxWidth = Math.max(26.0, measureFont(font, '0').width * 2.3);
  const top = baseline - ascent - 4;
  const bottom = baseline + descent + 4;
  const selected = isPaintKeySelected(engine, slot, index);

  let fill;
  let outline;
  let borderWidth;
  let dash;
  if (active && selected) {
    // 光标在方框里、同时方框又被选中：保留选中底色，只叠加高亮边框和光标。
    fill = SELECTION_FILL;
    outline = ACCENT;
    borderWidth = 2.0;
    dash = null;
  } else if (active) {
    fill = SOFT_ACCENT;
    outline = ACCENT;
    borderWidth = 2.0;
    dash = null;
  } else if (selected) {
    // 选中时方框用与选中高亮相同的底色，避免方框颜色盖住选中效果。
    fill = SELECTION_FILL;
    outline = ACCENT;
    borderWidth = 1.4;
    dash = null;
  } else {
    fill = PLACEHOLDER_FILL;
    outline = PLACEHOLDER_OUTLINE;
    borderWidth = 1.4;
    dash = [4, 2];
  }

  const draws = [
    { type: 'rect', x1: x, y1: top, x2: x + boxWidth, y2: bottom, fill: fill, outline: outline, width: borderWidth, dash: dash },
  ];
  if (active) {
    if (selected) {
      // 只画一条内边框表示“正在编辑”，不再覆盖整块底色。
      draws.push({ type: 'rect', x1: x + 2.5, y1: top + 2.5, x2: x + boxWidth - 2.5, y2: bottom - 2.5, fill: '', outline: ACCENT, width: 1.2, dash: null });
    } else {
      draws.push({ type: 'line', x1: x + 8, y1: top + 6, x2: x + 8, y2: bottom - 6, fill: ACCENT, width: 1.6 });
    }
  }

  const hits = [{ slot: slot, index: index, x1: x, y1: top, x2: x + boxWidth, y2: bottom, charPositions: null, kind: 'placeholder' }];
  return { width: boxWidth, ascent: ascent + 4, descent: descent + 4, draws: draws, hits: hits, nodes: [], selection: null };
}

const layoutMethods = {
  layoutSum(engine, node, x, baseline, size) {
    const limitSize = Math.max(12.0, size * 0.68);
    const upper = layoutSlot(engine, node.upper, 0.0, 0.0, limitSize);
    const lower = layoutSlot(engine, node.lower, 0.0, 0.0, limitSize);
    const body = layoutSlot(engine, node.body, 0.0, 0.0, size);

    const glyphFont = fontString(size * 1.75, false, engine.symbolFont);
    const glyph = measureFont(glyphFont, '∑');

    const columnWidth = Math.max(glyph.width, upper.width, lower.width);
    const glyphX = x + (columnWidth - glyph.width) / 2;
    const upperBaseline = -glyph.ascent - 4 - upper.descent;
    const lowerBaseline = glyph.descent + 4 + lower.ascent;
    const bodyX = x + columnWidth + 10;

    const upperShifted = shiftLayout(upper, x + (columnWidth - upper.width) / 2, baseline + upperBaseline);
    const lowerShifted = shiftLayout(lower, x + (columnWidth - lower.width) / 2, baseline + lowerBaseline);
    const bodyShifted = shiftLayout(body, bodyX, baseline);

    const merged = mergeLayouts([upperShifted, lowerShifted, bodyShifted]);
    const draws = merged[0];
    const hits = merged[1];
    const nodes = merged[2];
    draws.unshift({ type: 'text', x: glyphX, y: baseline + glyph.descent, text: '∑', font: glyphFont, fill: TEXT, anchor: 'sw' });

    const ascent = Math.max(glyph.ascent, -upperBaseline + upper.ascent, body.ascent);
    const descent = Math.max(glyph.descent, lowerBaseline + lower.descent, body.descent);
    const width = columnWidth + 10 + body.width;
    return { width: width, ascent: ascent, descent: descent, draws: draws, hits: hits, nodes: nodes, selection: null };
  },

  layoutIntegral(engine, node, x, baseline, size) {
    const limitSize = Math.max(11.0, size * 0.62);
    const upper = layoutSlot(engine, node.upper, 0.0, 0.0, limitSize);
    const lower = layoutSlot(engine, node.lower, 0.0, 0.0, limitSize);
    const body = layoutSlot(engine, node.body, 0.0, 0.0, size);

    const glyphFont = fontString(size * 2.15, false, engine.symbolFont);
    const glyph = measureFont(glyphFont, '∫');

    const limitX = x + glyph.width + 2;
    const upperBaseline = -glyph.ascent + 2 + upper.ascent;
    const lowerBaseline = glyph.descent - 2 - lower.descent;
    const upperShifted = shiftLayout(upper, limitX, baseline + upperBaseline);
    const lowerShifted = shiftLayout(lower, limitX, baseline + lowerBaseline);

    const bodyX = x + glyph.width + Math.max(upper.width, lower.width) + 9;
    const bodyShifted = shiftLayout(body, bodyX, baseline);

    const dFont = fontString(size, false, engine.mathFont);
    const dMetrics = measureFont(dFont, 'd');
    const dX = bodyX + body.width + 6;
    const varShifted = childLayout(engine, node.var, dX + dMetrics.width + 2, baseline, size);

    const merged = mergeLayouts([upperShifted, lowerShifted, bodyShifted]);
    const draws = [
      { type: 'text', x: x, y: baseline + glyph.descent, text: '∫', font: glyphFont, fill: TEXT, anchor: 'sw' },
      ...merged[0],
      { type: 'text', x: dX, y: baseline + dMetrics.descent, text: 'd', font: dFont, fill: TEXT, anchor: 'sw' },
      ...varShifted.draws,
    ];
    const hits = merged[1].concat(varShifted.hits);
    const nodes = merged[2].concat(varShifted.nodes);

    const ascent = Math.max(glyph.ascent, upperBaseline + upper.ascent, body.ascent, dMetrics.ascent, varShifted.ascent);
    const descent = Math.max(glyph.descent, lowerBaseline + lower.descent, body.descent, dMetrics.descent, varShifted.descent);
    const width = dX + dMetrics.width + 2 + varShifted.width - x;
    return { width: width, ascent: ascent, descent: descent, draws: draws, hits: hits, nodes: nodes, selection: null };
  },

  layoutFraction(engine, node, x, baseline, size) {
    const numerator = layoutSlot(engine, node.numerator, 0.0, 0.0, size);
    const denominator = layoutSlot(engine, node.denominator, 0.0, 0.0, size);
    const gap = 7.0;
    const padding = 12.0;
    const width = Math.max(numerator.width, denominator.width) + padding * 2;

    const numeratorBaseline = -gap - numerator.descent;
    const denominatorBaseline = gap + denominator.ascent;
    const numeratorShifted = shiftLayout(numerator, x + (width - numerator.width) / 2, baseline + numeratorBaseline);
    const denominatorShifted = shiftLayout(denominator, x + (width - denominator.width) / 2, baseline + denominatorBaseline);

    const merged = mergeLayouts([numeratorShifted, denominatorShifted]);
    merged[0].push({ type: 'line', x1: x + 2, y1: baseline, x2: x + width - 2, y2: baseline, fill: TEXT, width: 1.4 });

    const ascent = Math.max(0.0, -numeratorBaseline + numerator.ascent);
    const descent = Math.max(0.0, denominatorBaseline + denominator.descent);
    return { width: width, ascent: ascent, descent: descent, draws: merged[0], hits: merged[1], nodes: merged[2], selection: null };
  },

  layoutPower(engine, node, x, baseline, size) {
    const exponentSize = Math.max(11.0, size * 0.64);
    const base = childLayout(engine, node.base, x, baseline, size);
    const exponentBaseline = -Math.max(base.ascent * 0.52, size * 0.38);
    const exponent = childLayout(engine, node.exponent, x + base.width + 2, baseline + exponentBaseline, exponentSize);

    const merged = mergeLayouts([base, exponent]);
    const ascent = Math.max(base.ascent, -exponentBaseline + exponent.ascent);
    const descent = Math.max(base.descent, exponentBaseline + exponent.descent);
    const width = base.width + 2 + exponent.width;
    return { width: width, ascent: ascent, descent: descent, draws: merged[0], hits: merged[1], nodes: merged[2], selection: null };
  },

  layoutSubscript(engine, node, x, baseline, size) {
    const scriptSize = Math.max(11.0, size * 0.64);
    const base = childLayout(engine, node.base, x, baseline, size);
    const subscriptBaseline = Math.max(base.descent * 0.55, size * 0.22);
    const subscript = childLayout(engine, node.subscript, x + base.width + 2, baseline + subscriptBaseline, scriptSize);

    const merged = mergeLayouts([base, subscript]);
    const ascent = Math.max(base.ascent, -subscriptBaseline + subscript.ascent);
    const descent = Math.max(base.descent, subscriptBaseline + subscript.descent);
    const width = base.width + 2 + subscript.width;
    return { width: width, ascent: ascent, descent: descent, draws: merged[0], hits: merged[1], nodes: merged[2], selection: null };
  },

  layoutSubsup(engine, node, x, baseline, size) {
    const scriptSize = Math.max(11.0, size * 0.64);
    const base = childLayout(engine, node.base, x, baseline, size);
    const scriptX = x + base.width + 2;
    const superscriptBaseline = -Math.max(base.ascent * 0.52, size * 0.38);
    const subscriptBaseline = Math.max(base.descent * 0.55, size * 0.22);
    const superscript = childLayout(engine, node.superscript, scriptX, baseline + superscriptBaseline, scriptSize);
    const subscript = childLayout(engine, node.subscript, scriptX, baseline + subscriptBaseline, scriptSize);

    const merged = mergeLayouts([base, superscript, subscript]);
    const ascent = Math.max(base.ascent, -superscriptBaseline + superscript.ascent);
    const descent = Math.max(base.descent, subscriptBaseline + subscript.descent);
    const width = base.width + 2 + Math.max(subscript.width, superscript.width);
    return { width: width, ascent: ascent, descent: descent, draws: merged[0], hits: merged[1], nodes: merged[2], selection: null };
  },

  layoutAccent(engine, node, x, baseline, size) {
    const body = childLayout(engine, node.body, x, baseline, size);

    const glyph = Object.prototype.hasOwnProperty.call(ACCENT_GLYPHS, node.mark) ? ACCENT_GLYPHS[node.mark] : 'ˆ';
    const gap = Math.max(2.0, size * 0.12);
    const top = -body.ascent - gap;

    const draws = body.draws.slice();
    let ascentTotal;
    if (glyph) {
      const font = fontString(Math.max(10.0, size * 0.62), false, engine.mathFont);
      const mark = measureFont(font, glyph);
      const markBaseline = top - mark.descent;
      draws.push({
        type: 'text',
        x: x + (body.width - mark.width) / 2,
        y: markBaseline + mark.descent,
        text: glyph,
        font: font,
        fill: TEXT,
        anchor: 'sw',
      });
      ascentTotal = -markBaseline + mark.ascent;
    } else {
      // 横线：紧贴内容上方画一条与内容同宽的线。
      const lineY = top - 1;
      draws.push({ type: 'line', x1: x, y1: lineY, x2: x + body.width, y2: lineY, fill: TEXT, width: 1.6 });
      ascentTotal = -lineY + 1.6;
    }

    const ascent = Math.max(ascentTotal, body.ascent);
    return { width: body.width, ascent: ascent, descent: body.descent, draws: draws, hits: body.hits, nodes: body.nodes, selection: null };
  },

  layoutRoot(engine, node, x, baseline, size) {
    const radicand = layoutSlot(engine, node.radicand, 0.0, 0.0, size);
    const indexLayout = node.index ? layoutSlot(engine, node.index, 0.0, 0.0, Math.max(11.0, size * 0.55)) : null;

    const indexWidth = indexLayout ? indexLayout.width : 0.0;
    const stemWidth = Math.max(18.0, indexLayout ? indexWidth + 6.0 : 18.0);
    const contentX = x + stemWidth + 2;
    const radTop = -radicand.ascent - 4;
    const radBottom = radicand.descent + 4;
    const lift = Math.min(11.0, Math.max(4.0, (radBottom - radTop) * 0.3));

    const draws = [
      { type: 'line', x1: x, y1: baseline + radBottom - lift, x2: x + 6, y2: baseline + radBottom, fill: TEXT, width: 1.6 },
      { type: 'line', x1: x + 6, y1: baseline + radBottom, x2: x + stemWidth - 2, y2: baseline + radTop, fill: TEXT, width: 1.6 },
      { type: 'line', x1: x + stemWidth - 2, y1: baseline + radTop, x2: contentX + radicand.width + 2, y2: baseline + radTop, fill: TEXT, width: 1.6 },
    ];

    const radicandShifted = shiftLayout(radicand, contentX, baseline);
    draws.push(...radicandShifted.draws);
    const hits = radicandShifted.hits.slice();
    const nodes = radicandShifted.nodes.slice();

    let indexBaseline = radTop;
    if (indexLayout !== null) {
      indexBaseline = radTop - 6 - indexLayout.descent;
      const indexShifted = shiftLayout(indexLayout, x + 2, baseline + indexBaseline);
      draws.push(...indexShifted.draws);
      hits.push(...indexShifted.hits);
      nodes.push(...indexShifted.nodes);
    }

    const ascent = Math.max(radicand.ascent + 4, indexLayout ? -indexBaseline + indexLayout.ascent : 0);
    const descent = radicand.descent + 4;
    const width = stemWidth + radicand.width + 4;
    return { width: width, ascent: ascent, descent: descent, draws: draws, hits: hits, nodes: nodes, selection: null };
  },

  layoutMatrix(engine, node, x, baseline, size) {
    const cellSize = Math.max(10.0, size * 0.88);
    const cellLayouts = node.rows.map((row) => row.map((cell) => layoutSlot(engine, cell, 0.0, 0.0, cellSize)));
    if (!cellLayouts.length || !cellLayouts[0].length) return emptyLayout();

    const rowCount = cellLayouts.length;
    let colCount = 0;
    for (const row of cellLayouts) colCount = Math.max(colCount, row.length);
    const colWidths = [];
    for (let c = 0; c < colCount; c += 1) {
      let maxWidth = 0;
      for (let r = 0; r < rowCount; r += 1) {
        if (c < cellLayouts[r].length) maxWidth = Math.max(maxWidth, cellLayouts[r][c].width);
      }
      colWidths.push(maxWidth + 14.0);
    }
    const rowHeights = [];
    for (let r = 0; r < rowCount; r += 1) {
      let maxHeight = 0;
      for (const cell of cellLayouts[r]) maxHeight = Math.max(maxHeight, cell.ascent + cell.descent);
      rowHeights.push(maxHeight + 10.0);
    }
    const innerWidth = colWidths.reduce((sum, w) => sum + w, 0) + 5.0 * (colCount - 1);
    const innerHeight = rowHeights.reduce((sum, h) => sum + h, 0) + 5.0 * (rowCount - 1);
    const top = -innerHeight / 2;

    const parenSize = Math.max(size * 0.9, innerHeight / 1.55);
    const parenFont = fontString(parenSize, false, engine.symbolFont);
    const left = measureFont(parenFont, '(');
    const right = measureFont(parenFont, ')');
    const parenHalf = Math.max(left.ascent + left.descent, right.ascent + right.descent) / 2;

    const leftX = x;
    const innerX = x + left.width + 6;
    const rightX = innerX + innerWidth + 6;
    const width = rightX + right.width - x;

    const draws = [
      { type: 'text', x: leftX + left.width / 2, y: baseline, text: '(', font: parenFont, fill: TEXT, anchor: 'center' },
      { type: 'text', x: rightX + right.width / 2, y: baseline, text: ')', font: parenFont, fill: TEXT, anchor: 'center' },
    ];
    const hits = [];
    const nodes = [];

    let rowTop = top;
    for (let r = 0; r < rowCount; r += 1) {
      const row = cellLayouts[r];
      const rowHeight = rowHeights[r];
      let maxAscent = 0;
      for (const cell of row) maxAscent = Math.max(maxAscent, cell.ascent);
      const rowBaseline = rowTop + 5 + maxAscent;
      let colX = innerX;
      for (let c = 0; c < row.length; c += 1) {
        const cell = row[c];
        const cellX = colX + (colWidths[c] - cell.width) / 2;
        const shifted = shiftLayout(cell, cellX, baseline + rowBaseline);
        draws.push(...shifted.draws);
        hits.push(...shifted.hits);
        nodes.push(...shifted.nodes);
        colX += colWidths[c] + 5;
      }
      rowTop += rowHeight + 5;
    }

    const halfHeight = Math.max(innerHeight / 2, parenHalf) + 4;
    return { width: width, ascent: halfHeight, descent: halfHeight, draws: draws, hits: hits, nodes: nodes, selection: null };
  },
};

// -- 绘制（PaintBackend 的 Canvas2D 实现） ------------------------------------

function paintLayoutToCanvas(ctx, canvas, layout, xOffset, baselineOffset, cssW, cssH, dpr) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  if (layout.selection) {
    for (const row of layout.selection) {
      ctx.fillStyle = SELECTION_FILL;
      ctx.fillRect(row.x1 + xOffset, row.y1 + baselineOffset, row.x2 - row.x1, row.y2 - row.y1);
    }
  }

  for (const draw of layout.draws) {
    if (draw.type === 'text') {
      ctx.font = draw.font;
      ctx.fillStyle = draw.fill;
      const metrics = fontMetrics(draw.font);
      const desc = metrics.descent;
      if (draw.anchor === 'center') {
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(draw.text, draw.x + xOffset, draw.y + baselineOffset);
      } else {
        ctx.textAlign = 'left';
        ctx.textBaseline = 'alphabetic';
        // 桌面版 DrawText 的 y 是文字包围盒底部（anchor="sw"），换算成基线。
        ctx.fillText(draw.text, draw.x + xOffset, draw.y + baselineOffset - desc);
      }
    } else if (draw.type === 'rect') {
      ctx.lineWidth = draw.width || 0;
      ctx.setLineDash(draw.dash && draw.dash.length ? draw.dash : []);
      if (draw.outline) {
        if (draw.fill) {
          ctx.fillStyle = draw.fill;
          ctx.fillRect(draw.x1 + xOffset, draw.y1 + baselineOffset, draw.x2 - draw.x1, draw.y2 - draw.y1);
        }
        ctx.strokeStyle = draw.outline;
        ctx.strokeRect(draw.x1 + xOffset, draw.y1 + baselineOffset, draw.x2 - draw.x1, draw.y2 - draw.y1);
      } else if (draw.fill) {
        ctx.fillStyle = draw.fill;
        ctx.fillRect(draw.x1 + xOffset, draw.y1 + baselineOffset, draw.x2 - draw.x1, draw.y2 - draw.y1);
      }
      ctx.setLineDash([]);
    } else {
      ctx.strokeStyle = draw.fill;
      ctx.lineWidth = draw.width || 1;
      ctx.beginPath();
      ctx.moveTo(draw.x1 + xOffset, draw.y1 + baselineOffset);
      ctx.lineTo(draw.x2 + xOffset, draw.y2 + baselineOffset);
      ctx.stroke();
    }
  }
}
