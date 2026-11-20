/* 无头一致性测试：在 Node 里加载 web/formula_editor.html 的内联脚本，
 * 用假 DOM / 假 Canvas 运行完整控制器，逐组验证与 desktop smoke.py 等价的行为。
 * 用法：node web/parity_test.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, 'formula_editor.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/);
if (!script) { console.error('找不到内联脚本'); process.exit(1); }

// -- 假浏览器环境 -----------------------------------------------------------
const drawnTexts = [];
const paintedRects = [];

function fakeElement() {
  return {
    style: {},
    textContent: '',
    innerHTML: '',
    disabled: false,
    hidden: false,
    className: '',
    addEventListener() {},
    appendChild() {},
    append() {},
    setAttribute() {},
    getAttribute() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    classList: { add() {}, remove() {}, toggle() {} },
    focus() {},
    remove() {},
    select() {},
  };
}

const ctxStub = {
  fillStyle: '',
  setTransform() {},
  clearRect() {},
  fillText(text) { drawnTexts.push({ text }); },
  setLineDash() {},
  fillRect(x, y, w, h) { paintedRects.push({ fill: this.fillStyle, x, y, w, h }); },
  strokeRect() {},
  beginPath() {},
  moveTo() {},
  lineTo() {},
  stroke() {},
  measureText(text) {
    const w = Array.from(String(text)).length * 10;
    return {
      width: w,
      fontBoundingBoxAscent: 10,
      fontBoundingBoxDescent: 3,
      actualBoundingBoxAscent: 10,
      actualBoundingBoxDescent: 3,
    };
  },
};

const canvasEl = Object.assign(fakeElement(), {
  width: 900,
  height: 200,
  clientWidth: 900,
  clientHeight: 200,
  getContext() { return ctxStub; },
  getBoundingClientRect() { return { left: 0, top: 0 }; },
});

const elements = {
  canvas: canvasEl,
  status: fakeElement(),
  'canvas-status': fakeElement(),
  markdown: fakeElement(),
  preview: fakeElement(),
  copy: fakeElement(),
  toast: fakeElement(),
  toolbar: fakeElement(),
  symbols: fakeElement(),
  categories: fakeElement(),
};

const document = {
  readyState: 'complete',
  getElementById(id) { return elements[id] || (elements[id] = fakeElement()); },
  createElement(tag) { return tag === 'canvas' ? canvasEl : fakeElement(); },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  head: { appendChild() {} },
  body: { appendChild() {}, removeChild() {} },
  addEventListener() {},
  execCommand() { return true; },
};

const nodeClone = globalThis.structuredClone;
const sandbox = {
  console,
  document,
  window: {
    __NO_UI_BOOT__: true,
    devicePixelRatio: 1,
    innerHeight: 900,
    addEventListener() {},
    __editorApp: null,
  },
  navigator: { clipboard: { writeText() { return Promise.resolve(); } } },
  setTimeout,
  clearTimeout,
  structuredClone: nodeClone,
};
sandbox.globalThis = sandbox;

const context = vm.createContext(sandbox);
vm.runInContext(script[1], context, { filename: 'formula_editor.html' });

// -- 假宿主 -----------------------------------------------------------------
function makeHost() {
  const host = {
    canvas: canvasEl,
    ctx: ctxStub,
    alerts: [],
    statuses: [],
    canvasStatuses: [],
    cursors: [],
    lastMarkdown: '',
    lastPreview: { latex: '', message: '', rendered: false },
    copyEnabled: false,
    copied: null,

    setStatus(text, kind) { this.statuses.push({ text, kind }); },
    setCanvasStatus(text) { this.canvasStatuses.push(text); },
    alert(title, message) { this.alerts.push({ title, message }); },
    focus() {},
    setCursor(name) { this.cursors.push(name); },
    canvasWidth() { return 900; },
    windowHeight() { return 900; },
    devicePixelRatio() { return 1; },
    prepareCanvas() {},
    syncMarkdown(markdown) {
      this.lastMarkdown = markdown;
      this.copyEnabled = !!markdown;
    },
    renderPreview(latex, message) {
      this.lastPreview = {
        latex: latex,
        message: message,
        rendered: !!latex && !message,
      };
    },
    schedule(callback) {
      // 同步执行，避免测试里等待计时器；渲染/预览都是幂等的。
      callback();
      return 0;
    },
    cancel() {},
    copyToClipboard(text, done) {
      this.copied = text;
      if (done) done(true);
    },
  };
  return host;
}

const host = makeHost();
const AppClass = vm.runInContext('EditorApp', context);
const app = new AppClass(host);
sandbox.app = app;

// -- 断言工具 ---------------------------------------------------------------
let failed = 0;
function check(name, actual, expected) {
  const ok = actual === expected;
  if (!ok) {
    failed += 1;
    console.log('FAIL ' + name + '\n  期望: ' + JSON.stringify(expected) + '\n  实际: ' + JSON.stringify(actual));
  } else {
    console.log('ok   ' + name);
  }
}

function checkTrue(name, actual, detail) {
  if (!actual) {
    failed += 1;
    console.log('FAIL ' + name + (detail ? '\n  ' + JSON.stringify(detail) : ''));
  } else {
    console.log('ok   ' + name);
  }
}

const run = (code) => vm.runInContext(code, context, { filename: 'test' });
const latex = () => run('normalizeFormula(serializeSlot(app.rootSlot))');
const render = () => { app._render_canvas(); };
const preview = () => { app._update_output_preview(); };
const SELECTION = run('SELECTION_FILL');

// -- 1. 求和：编辑 → 源码 → 复制按钮 → 预览 ----------------------------------
app.insert_template('sum');
app._insert_text('i=1');
app._move_selection(1);
app._insert_text('n');
app._move_selection(1);
app._insert_text('i^2');
check('求和：必填方框清空', run('countPlaceholders(app.rootSlot)'), 0);
check('求和：LaTeX', latex(), '\\sum_{i=1}^{n} i^2');
render();
checkTrue('求和：画布有绘制项', app.lastLayout.draws.length > 0);
checkTrue('求和：有可点击热区', app.hitAreas.length > 0);
check('求和：Markdown', host.lastMarkdown, '$$\n\\sum_{i=1}^{n} i^2\n$$');
check('求和：复制按钮可用', host.copyEnabled, true);
preview();
checkTrue('求和：预览已渲染', host.lastPreview.rendered, host.lastPreview);

// -- 2. 积分 ---------------------------------------------------------------
app.clear_formula();
app.insert_template('integral');
for (const value of ['0', '\\infty', 'e^{-x^2}', 'x']) {
  app._insert_text(value);
  app._move_selection(1);
}
render();
checkTrue('积分：下限上限正确', latex().includes('\\int_{0}^{\\infty}'), latex());
checkTrue('积分：预览已渲染', (preview(), host.lastPreview.rendered));

// -- 3. 分式与乘方 ----------------------------------------------------------
app.clear_formula();
app.insert_template('fraction');
app._insert_text('a');
app._move_selection(1);
app._insert_text('b');
check('分式：LaTeX', latex(), '\\frac{a}{b}');

app.clear_formula();
app.insert_template('power');
app._insert_text('x');
app._move_selection(1);
app._insert_text('2');
check('乘方：LaTeX', latex(), '{x}^{2}');

// -- 4. 角标与拆结构 ---------------------------------------------------------
app.clear_formula();
app.insert_template('subscript');
check('下角标：两个空位', run('countPlaceholders(app.rootSlot)'), 2);
app._insert_text('a');
app._move_selection(1);
app._insert_text('n');
check('下角标：LaTeX', latex(), '{a}_{n}');
render();
checkTrue('下角标：预览已渲染', (preview(), host.lastPreview.rendered));

app.clear_formula();
app.insert_template('sub_sup');
check('上下角标：三个空位', run('countPlaceholders(app.rootSlot)'), 3);
for (const value of ['x', 'i', '2']) {
  app._insert_text(value);
  app._move_selection(1);
}
check('上下角标：LaTeX', latex(), '{x}_{i}^{2}');
render();
checkTrue('上下角标：预览已渲染', (preview(), host.lastPreview.rendered));

// 拆掉角标结构：在下角标格位最前方回格，整个角标删除并用该格位内容替换。
app._set_active(app.rootSlot.items[1].subscript, 0, 0);
app._on_backspace();
check('拆结构：下角标回格还原成内容', latex(), 'i');

// -- 5. 顶标 ---------------------------------------------------------------
for (const [key, expected] of [
  ['hat', '\\hat{x}'],
  ['bar', '\\bar{x}'],
  ['vec', '\\vec{x}'],
  ['overline', '\\overline{x}'],
]) {
  app.clear_formula();
  app.insert_template(key);
  check('顶标 ' + key + '：一个空位', run('countPlaceholders(app.rootSlot)'), 1);
  app._insert_text('x');
  check('顶标 ' + key + '：LaTeX', latex(), expected);
  render();
  checkTrue('顶标 ' + key + '：预览已渲染', (preview(), host.lastPreview.rendered));
}

// 全部顶标命令都要能序列化。
checkTrue('顶标：全部命令可序列化', run(`
  Object.keys(ACCENT_LATEX).every((key) => serializeItem({ kind: 'accent', mark: key, body: { items: [textRun('x')] } }).includes(ACCENT_LATEX[key]))
`));

// -- 6. n 次根与矩阵 ---------------------------------------------------------
app.clear_formula();
app.insert_template('nth_root');
app._insert_text('x');
app._move_selection(1);
app._insert_text('3');
check('n 次根：LaTeX', latex(), '\\sqrt[3]{x}');

app.clear_formula();
app.insert_matrix(2, 2);
for (const value of ['1', '2', '3', '4']) {
  app._insert_text(value);
  app._move_selection(1);
}
checkTrue('矩阵：pmatrix 序列化', latex().includes('\\begin{pmatrix}'), latex());
render();
preview();
checkTrue('矩阵：预览已渲染', host.lastPreview.rendered);

// -- 7. 符号面板 ------------------------------------------------------------
app.clear_formula();
app.insert_symbol('·');
app._insert_text('a');
checkTrue('符号：· 映射为 \\cdot', latex().includes('\\cdot'), latex());
for (const [glyph, expected] of [
  ['÷', '\\div'],
  ['∉', '\\notin'],
  ['ℕ', '\\mathbb{N}'],
  ['∬', '\\iint'],
  ['′', '\\prime'],
  ['α', '\\alpha'],
  ['Ω', '\\Omega'],
  ['⇔', '\\Leftrightarrow'],
]) {
  app.clear_formula();
  app.insert_symbol(glyph);
  render();
  checkTrue('符号 ' + glyph + ' 导出正确', latex().includes(expected), latex());
  checkTrue('符号 ' + glyph + ' 绘制到画布', app.lastLayout.draws.length > 0);
}
check('符号：面板符号全部有 LaTeX 映射', run(`
  iterPanelGlyphs().filter((glyph) => Array.from(glyph).some((ch) => ch.codePointAt(0) > 127) && !(glyph in SYMBOL_LATEX)).length
`), 0);

// -- 8. 左右方向键跨框 -------------------------------------------------------
app.clear_formula();
app.insert_matrix(1, 2);
const firstCell = app.activeSlot;
app._move_caret(1);
checkTrue('方向键：右移到下一格', app.activeSlot !== firstCell);
app._move_caret(-1);
checkTrue('方向键：左移回来', app.activeSlot === firstCell);

// -- 9. 上下方向键 -----------------------------------------------------------
checkTrue('上下键：handleKeyDown 已绑定 ArrowUp', typeof app.handleKeyDown === 'function');

app.clear_formula();
app.insert_template('fraction');
app._insert_text('a');
app._move_selection(1);
app._insert_text('b');
const fraction = app.rootSlot.items[1];
app._set_active(fraction.denominator, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：分母 ↑ 到分子', app.activeSlot === fraction.numerator);
app._move_caret_vertical(1);
checkTrue('上下键：分子 ↓ 到分母', app.activeSlot === fraction.denominator);
app._set_active(fraction.numerator, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：分子 ↑ 停在原地', app.activeSlot === fraction.numerator);

// 用真实 keydown 入口验证 ArrowUp / ArrowDown 已接线。
const beforeKey = app.activeSlot;
app.handleKeyDown({ key: 'ArrowDown', ctrlKey: false, metaKey: false, shiftKey: false, altKey: false });
checkTrue('上下键：keydown ArrowDown 触发移动', app.activeSlot === fraction.denominator);
app.handleKeyDown({ key: 'ArrowUp', ctrlKey: false, metaKey: false, shiftKey: false, altKey: false });
checkTrue('上下键：keydown ArrowUp 触发移动', app.activeSlot === fraction.numerator);

app.clear_formula();
app.insert_template('sum');
for (const value of ['i=1', 'n', 'i^2']) {
  app._insert_text(value);
  app._move_selection(1);
}
const sumNode = app.rootSlot.items[1];
app._set_active(sumNode.lower, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：求和下限 ↑ 到上限', app.activeSlot === sumNode.upper);
app._move_caret_vertical(1);
checkTrue('上下键：求和上限 ↓ 到下限', app.activeSlot === sumNode.lower);
app._set_active(sumNode.body, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：求和项 ↑ 到上限', app.activeSlot === sumNode.upper);
app._move_caret_vertical(1);
checkTrue('上下键：求和项 ↓ 到下限', app.activeSlot === sumNode.lower);

app.clear_formula();
app.insert_template('integral');
for (const value of ['0', 'n', 'x', 'x']) {
  app._insert_text(value);
  app._move_selection(1);
}
const integral = app.rootSlot.items[1];
app._set_active(integral.lower, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：积分下限 ↑ 到上限', app.activeSlot === integral.upper);
app._set_active(integral.upper, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：积分上限 ↑ 停在原地', app.activeSlot === integral.upper);
app._set_active(integral.var, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：积分变量 ↑ 到上限', app.activeSlot === integral.upper);

app.clear_formula();
app.insert_template('sub_sup');
const subsup = app.rootSlot.items[1];
app._set_active(subsup.base, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：上下标底数 ↑ 到上标', app.activeSlot === subsup.superscript);
app._move_caret_vertical(1);
checkTrue('上下键：上标 ↓ 回底数', app.activeSlot === subsup.base);
app._move_caret_vertical(1);
checkTrue('上下键：底数 ↓ 到下标', app.activeSlot === subsup.subscript);
app._move_caret_vertical(-1);
checkTrue('上下键：下标 ↑ 回底数', app.activeSlot === subsup.base);

app.clear_formula();
app.insert_template('nth_root');
const rootNode = app.rootSlot.items[1];
app._set_active(rootNode.radicand, 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：被开方数 ↑ 到根指数', app.activeSlot === rootNode.index);

app.clear_formula();
app.insert_matrix(2, 2);
const matrix = app.rootSlot.items[1];
app._set_active(matrix.rows[1][0], 0, 0);
app._move_caret_vertical(-1);
checkTrue('上下键：矩阵格 ↑ 到同一列上一行', app.activeSlot === matrix.rows[0][0]);
app._move_caret_vertical(-1);
checkTrue('上下键：矩阵首行 ↑ 停在原地', app.activeSlot === matrix.rows[0][0]);
app._move_caret_vertical(1);
checkTrue('上下键：矩阵格 ↓ 到同一列下一行', app.activeSlot === matrix.rows[1][0]);

app.clear_formula();
app.insert_template('hat');
const hat = app.rootSlot.items[1];
app._set_active(hat.body, 0, 0);
app._move_caret_vertical(-1);
app._move_caret_vertical(1);
checkTrue('上下键：单格顶标没有上下邻格', app.activeSlot === hat.body);

app.clear_formula();
app._set_active(app.rootSlot, 0, 0);
app._move_caret_vertical(-1);
app._move_caret_vertical(1);
checkTrue('上下键：公式根行没有上下邻格', app.activeSlot === app.rootSlot && app.activeIndex === 0);

// -- 10. 点击文本边缘添加输入位置 --------------------------------------------
app.clear_formula();
app._insert_text('x');
render();
const edge = app.hitAreas.find((hit) => hit.kind === 'text-edge-right');
const edgeX = (edge.x1 + edge.x2) / 2;
const edgeY = (edge.y1 + edge.y2) / 2;
app._on_canvas_drag_start({ x: edgeX, y: edgeY });
app._on_canvas_drag_end({ x: edgeX, y: edgeY });
check('点击边缘：新增输入位置', run('app._active_item().kind'), 'placeholder');
app._insert_text('+');
check('点击边缘：输入后 LaTeX', latex(), 'x+');

// -- 11. 四则运算按字符处理 ---------------------------------------------------
app.clear_formula();
app._insert_text('x+2');
check('四则运算：x+2 不拆分', latex(), 'x+2');

// -- 12. 删除整结构 ----------------------------------------------------------
app.clear_formula();
app.insert_template('sum');
for (const value of ['i=1', 'n', 'i^2']) {
  app._insert_text(value);
  app._move_selection(1);
}
render();
app._set_active(app.rootSlot, 0, 0);
app._on_backspace();
checkTrue('删除：结构左侧回格不删右侧结构', latex().includes('\\sum'), latex());
app._set_active(app.rootSlot, app.rootSlot.items.length - 1, 0);
app._on_backspace();
check('删除：结构右侧回格整体删除', latex(), '');

app.clear_formula();
app.insert_template('integral');
for (const value of ['0', 'n', 'x', 'x']) {
  app._insert_text(value);
  app._move_selection(1);
}
render();
app._set_active(app.rootSlot, 0, 0);
app._on_delete();
check('删除：结构左侧 Delete 整体删除', latex(), '');

// -- 13. 格位最前方回格：拆整个算符 ------------------------------------------
app.clear_formula();
app.insert_template('sum');
for (const value of ['i=1', 'n', 'i^2']) {
  app._insert_text(value);
  app._move_selection(1);
}
app._set_active(app.rootSlot.items[1].body, 0, 0);
app._on_backspace();
check('拆结构：求和项回格还原成内容', latex(), 'i^2');

app.clear_formula();
app.insert_template('fraction');
app._insert_text('a');
app._move_selection(1);
app._insert_text('b');
app._set_active(app.rootSlot.items[1].numerator, 0, 0);
app._on_backspace();
check('拆结构：分子回格还原成分式内容', latex(), 'a');

app.clear_formula();
app.insert_template('derivative');
const derivative = app.rootSlot.items[1];
app._set_active(derivative.numerator, 1, 0);
app._on_backspace();
check('拆结构：微分内部固定 d 不保留', latex(), '');

app.clear_formula();
app.insert_template('sum');
app._set_active(app.rootSlot, app.rootSlot.items.length - 1, 0);
app._insert_text('x');
const textIndex = app.rootSlot.items.findIndex((item) => item.kind === 'text' && item.text === 'x');
app._set_active(app.rootSlot, textIndex, 0);
app._on_backspace();
check('拆结构：文本正前方回格删除相邻结构', latex(), 'x');

// -- 14. 文本内删字符 --------------------------------------------------------
app.clear_formula();
app.insert_template('fraction');
app._insert_text('a');
app._move_selection(1);
app._insert_text('b');
const insideFraction = app.rootSlot.items[1];
app._set_active(insideFraction.denominator, 0, 1);
app._on_delete();
check('文本内：Delete 不跨到右侧', run('app.rootSlot.items[1].denominator.items.map((item) => item.kind).join(",")'), 'text');
app._set_active(insideFraction.denominator, 0, 1);
app._on_backspace();
check('文本内：回格删空后变回方框', run('app.rootSlot.items[1].denominator.items.map((item) => item.kind).join(",")'), 'placeholder');

// -- 15. 纯算符文本只删字符本身 ----------------------------------------------
app.clear_formula();
app.insert_template('sum');
for (const value of ['1', 'n', 'x']) {
  app._insert_text(value);
  app._move_selection(1);
}
app._insert_text('+');
app._set_active(app.rootSlot, app.rootSlot.items.length - 1, 0);
app._on_backspace();
checkTrue('纯算符：只删字符本身', latex().endsWith('x'), latex());

// -- 16. 拖动选择 ------------------------------------------------------------
app.clear_formula();
app._insert_text('x');
app.insert_template('sum');
render();
const sumBox = app.nodeBoxes.find((box) => box.node.kind === 'sum');
const textHit = app.hitAreas.find((hit) => hit.kind === 'text' && hit.slot === app.rootSlot);
const startX = textHit.charPositions[0] + 2;
const startY = (textHit.y1 + textHit.y2) / 2;
const midY = (sumBox.y1 + sumBox.y2) / 2;
const endX = sumBox.x2 + 4;
app._on_canvas_drag_start({ x: startX, y: startY });
app._on_canvas_drag_motion({ x: endX, y: midY });
app._on_canvas_drag_end({ x: endX, y: midY });
checkTrue('拖选：从文本拖到结构上选中结构', app._has_selection());
const selectedKinds = app._selection_state()[1].map((segment) => segment.item.kind);
checkTrue('拖选：选中片段含求和结构', selectedKinds.includes('sum'), selectedKinds);
const highlights = paintedRects.filter((rect) => rect.fill === SELECTION);
const expectedBounds = [sumBox.x1, sumBox.y1, sumBox.x2 - sumBox.x1, sumBox.y2 - sumBox.y1];
checkTrue(
  '拖选：高亮包围盒与结构一致',
  highlights.some((rect) => Math.abs(rect.x - expectedBounds[0]) <= 1
    && Math.abs(rect.y - expectedBounds[1]) <= 1
    && Math.abs(rect.w - expectedBounds[2]) <= 1
    && Math.abs(rect.h - expectedBounds[3]) <= 1),
  highlights,
);
app._on_backspace();
check('拖选：删除选择后公式清空', latex(), '');

// -- 17. 空方框与选中底色 ----------------------------------------------------
app.clear_formula();
app.insert_template('fraction');
app._insert_text('a');
render();
const emptyBox = app.hitAreas.find((hit) => hit.kind === 'placeholder' && hit.slot === app.rootSlot.items[1].denominator);
const boxX = (emptyBox.x1 + emptyBox.x2) / 2;
const boxY = (emptyBox.y1 + emptyBox.y2) / 2;
app._on_canvas_drag_start({ x: boxX, y: boxY });
app._on_canvas_drag_motion({ x: boxX + 40, y: boxY });
app._on_canvas_drag_end({ x: boxX + 40, y: boxY });
checkTrue('空方框：在上面拖动不产生选择', !app._has_selection());
// 重新点空方框，再按回格：整个分式删除，用该格位（空）的内容替换。
app._on_canvas_drag_start({ x: boxX, y: boxY });
app._on_canvas_drag_end({ x: boxX, y: boxY });
app._on_backspace();
check('空方框：格位最前方回格拆掉外层结构', latex(), '');

app.clear_formula();
app.insert_template('fraction');
app._insert_text('a');
render();
const fractionHit = app.hitAreas.find((hit) => hit.kind === 'text' && hit.slot === app.rootSlot.items[1].numerator);
const fractionBox = app.nodeBoxes.find((box) => box.node.kind === 'fraction');
const fracMidY = (fractionBox.y1 + fractionBox.y2) / 2;
app._on_canvas_drag_start({ x: fractionHit.charPositions[0] + 1, y: (fractionHit.y1 + fractionHit.y2) / 2 });
app._on_canvas_drag_motion({ x: fractionBox.x2 + 30, y: fracMidY });
app._on_canvas_drag_end({ x: fractionBox.x2 + 30, y: fracMidY });
checkTrue('选中结构：从文本拖动选中分式', app._has_selection());
const boxFills = paintedRects.filter((rect) => rect.fill === SELECTION).length;
checkTrue('选中结构：内部方框用选中底色', boxFills >= 2, boxFills);
app._on_canvas_drag_end({ x: 5, y: 5 });
app._collapse_selection();

// -- 17b. 拖选不会跨行 -------------------------------------------------------
// 在分式分子（微分 dx^2/dx 的上方）里拖选：只要指针还留在这一行，
// 焦点就不能跳到整个分式上，否则会把下面的 x 也一起选中。
app.clear_formula();
app.insert_template('derivative');
app._insert_text('x^2');
app._move_selection(1);
app._insert_text('x');
render();
const deriv = app.rootSlot.items[1];
const derivNumHit = app.hitAreas.find(
  (hit) => hit.kind === 'text' && hit.slot === deriv.numerator && hit.index === 1,
);
const derivY = (derivNumHit.y1 + derivNumHit.y2) / 2;
const derivStartX = derivNumHit.charPositions[0] + 2;
const derivEndX = derivNumHit.charPositions[derivNumHit.charPositions.length - 1] + 8;
app._on_canvas_drag_start({ x: derivStartX, y: derivY });
app._on_canvas_drag_motion({ x: derivEndX, y: derivY });
app._on_canvas_drag_end({ x: derivEndX, y: derivY });
const rowSelected = app._selection_state()[1].map((segment) => segment.item);
checkTrue(
  '拖选：分子里拖动只选中这一行',
  rowSelected.length === 1 && rowSelected[0] === deriv.numerator.items[1],
  rowSelected.map((item) => item.kind || item.text),
);
app._collapse_selection();

// -- 17c. 选中内容后插入带方框的结构：内容进「主要方框」 ----------------------
function selectSegments(segments, anchor, focus) {
  app._collapse_selection();
  app.selectionSegments = segments.slice();
  app.selectionAnchor = anchor;
  app.selectionFocus = focus;
}

app.clear_formula();
app.insert_template('sum');
for (const value of ['i=1', 'n', 'i^2']) {
  app._insert_text(value);
  app._move_selection(1);
}
render();
let mainSegs = app._collect_segments();
const sumSeg = mainSegs.find((segment) => segment.item.kind === 'sum');
selectSegments(mainSegs, [mainSegs.indexOf(sumSeg), 0], [mainSegs.indexOf(sumSeg), 0]);
app.insert_template('sqrt');
check('选中结构 → 根式：求和进被开方数', latex(), '\\sqrt{\\sum_{i=1}^{n} i^2}');

app.clear_formula();
app._insert_text('x+1');
render();
mainSegs = app._collect_segments();
selectSegments(mainSegs, [0, 0], [0, 3]);
app.insert_template('integral');
check('选中文本 → 积分：文本进被积函数', latex(), '\\int_{□}^{□} x+1\\,\\mathrm{d}□');

app.clear_formula();
app._insert_text('abc');
render();
mainSegs = app._collect_segments();
selectSegments(mainSegs, [0, 1], [0, 2]);
app.insert_template('fraction');
check('文本中段 → 分式：只移动选中的字符', latex(), 'a\\frac{b}{□}c');

app.clear_formula();
app._insert_text('v');
render();
mainSegs = app._collect_segments();
selectSegments(mainSegs, [0, 0], [0, 1]);
app.insert_template('hat');
check('选中文本 → 顶标：进顶标内容', latex(), '\\hat{v}');

app.clear_formula();
app._insert_text('y');
render();
mainSegs = app._collect_segments();
selectSegments(mainSegs, [0, 0], [0, 1]);
app.insert_template('nth_root');
check('选中文本 → n 次根：进被开方数', latex(), '\\sqrt[□]{y}');

app.clear_formula();
app.insert_matrix(2, 2);
for (const value of ['1', '2', '3', '4']) {
  app._insert_text(value);
  app._move_selection(1);
}
render();
mainSegs = app._collect_segments();
const matrixSeg = mainSegs.find((segment) => segment.item.kind === 'matrix');
selectSegments(mainSegs, [mainSegs.indexOf(matrixSeg), 0], [mainSegs.indexOf(matrixSeg), 0]);
app.insert_template('sqrt');
checkTrue('选中矩阵 → 根式：矩阵进第一个单元格', latex().includes('\\sqrt{\\begin{pmatrix}'), latex());
app._collapse_selection();

// -- 18. 撤销 / 重做 ---------------------------------------------------------
app.clear_formula();
const emptyLatex = latex();
app.insert_template('sum');
const withSumLatex = latex();
checkTrue('撤销：插入求和后公式非空', withSumLatex !== '');
app.undo();
check('撤销：撤销插入求和后回到空公式', latex(), emptyLatex);
app.redo();
check('重做：恢复插入求和后的状态', latex(), withSumLatex);

// -- 19. 复制 ----------------------------------------------------------------
app.clear_formula();
app.insert_template('sum');
for (const value of ['i=1', 'n', 'i^2']) {
  app._insert_text(value);
  app._move_selection(1);
}
app.copy_markdown();
check('复制：剪贴板内容为 Markdown', host.copied, '$$\n\\sum_{i=1}^{n} i^2\n$$');

app.clear_formula();
app.insert_template('fraction');
app.copy_markdown();
checkTrue('复制：未填满时给出提示', host.alerts.length > 0);

console.log('');
if (failed) {
  console.log(failed + ' 个用例失败');
  process.exit(1);
}
console.log('全部用例通过；画布共绘制 ' + drawnTexts.length + ' 个文本片段');
