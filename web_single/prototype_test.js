// 无头逻辑测试：用假 DOM / 假 Canvas 直接运行 formula_editor.html 的内联脚本，
// 验证公式树、编辑规则与 LaTeX 输出。用法：node prototype_test.js
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, 'formula_editor.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/);
if (!script) { console.error('找不到内联脚本'); process.exit(1); }

// -- 假的浏览器环境 ---------------------------------------------------------
const drawnTexts = [];
const ctxStub = {
  setTransform() {},
  clearRect() {},
  fillText(text, x, y) { drawnTexts.push({ text, x, y }); },
  setLineDash() {},
  fillRect() {},
  strokeRect() {},
  beginPath() {},
  moveTo() {},
  lineTo() {},
  stroke() {},
  measureText(text) {
    const w = String(text).length * 10;
    return { width: w, fontBoundingBoxAscent: 10, fontBoundingBoxDescent: 3, actualBoundingBoxAscent: 10, actualBoundingBoxDescent: 3 };
  },
};

function fakeElement() {
  return {
    style: {},
    textContent: '',
    innerHTML: '',
    disabled: false,
    className: '',
    addEventListener() {},
    appendChild() {},
    setAttribute() {},
    getAttribute() { return null; },
    focus() {},
  };
}

const canvasEl = Object.assign(fakeElement(), {
  width: 900,
  height: 120,
  clientWidth: 900,
  getContext() { return ctxStub; },
  getBoundingClientRect() { return { left: 0, top: 0 }; },
});

const elements = { canvas: canvasEl, symbols: fakeElement(), status: fakeElement(), markdown: fakeElement(), preview: fakeElement(), copy: fakeElement(), clear: fakeElement() };

const document = {
  getElementById(id) { return elements[id] || (elements[id] = fakeElement()); },
  createElement(tag) {
    if (tag === 'canvas') return canvasEl;
    return fakeElement();
  },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  head: { appendChild() {} },
  body: { appendChild() {}, removeChild() {} },
};

const sandbox = {
  console,
  document,
  window: { devicePixelRatio: 1, addEventListener() {} },
  navigator: { clipboard: { writeText() { return Promise.resolve(); } } },
  requestAnimationFrame(fn) { fn(); },
};
sandbox.globalThis = sandbox;

const context = vm.createContext(sandbox);
vm.runInContext(script[1], context, { filename: 'formula_editor.html' });

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

const run = (code) => vm.runInContext(code, context, { filename: 'test' });

// -- 用例：求和 --------------------------------------------------------------
run(`
  insertNode(makeTemplate('sum'), '求和');
  insertText('i=1');
  moveSelection(1);
  insertText('n');
  moveSelection(1);
  insertText('i^2');
`);
check('求和 LaTeX', run('serializeSlot(rootSlot).trim()'), '\\sum_{i=1}^{n} i^2');
check('必填方框已清空', run('countPlaceholders(rootSlot)'), 0);
check('Markdown 输出', elements.markdown.textContent, '$$\n\\sum_{i=1}^{n} i^2\n$$');
check('复制按钮可用', elements.copy.disabled, false);
check('画布确实画出了 ∑ 字形', drawnTexts.some((d) => d.text === '∑'), true);

// -- 撤销/清空后重来 ----------------------------------------------------------
run('clearFormula();');
check('清空后无内容', run('serializeSlot(rootSlot).trim()'), '');
check('清空后有一个空位', run('rootSlot.items.length'), 1);

// -- 结构整体删除（Delete 只往右看） -----------------------------------------
run(`
  insertNode(makeTemplate('sum'), '求和');
  setActive(rootSlot, 0, 0);
  removeAtCaret(false);
`);
check('结构左侧 Delete 删除右侧结构', run('serializeSlot(rootSlot).trim()'), '');

// -- 结构整体删除（回格只往左看） --------------------------------------------
run(`
  insertNode(makeTemplate('sum'), '求和');
  setActive(rootSlot, rootSlot.items.length - 1, 0);
  removeAtCaret(true);
`);
check('结构右侧回格删除左侧结构', run('serializeSlot(rootSlot).trim()'), '');

// -- 四则运算按字符处理 -------------------------------------------------------
run(`clearFormula(); insertText('x+2');`);
check('x+2 不拆分结构', run('serializeSlot(rootSlot).trim()'), 'x+2');
check('x+2 无必填方框', run('countPlaceholders(rootSlot)'), 0);

// -- 分式 + 方框内拒绝嵌套结构 ------------------------------------------------
run(`
  clearFormula();
  insertNode(makeTemplate('fraction'), '分式');
  insertText('a');
  insertNode(makeTemplate('power'), '乘方');
`);
check('方框内已有内容时拒绝插入结构', run('serializeSlot(rootSlot).trim()'), '\\frac{a}{□}');
check('拒绝时有提示', elements.status.textContent.includes('已经有内容'), true);

// -- 方向键跨框 ---------------------------------------------------------------
run(`
  clearFormula();
  insertNode(makeTemplate('fraction'), '分式');
  insertText('a');
  moveSelection(1);
  insertText('b');
`);
check('分式 LaTeX', run('serializeSlot(rootSlot).trim()'), '\\frac{a}{b}');

// -- 点击命中：点击方框中心应聚焦该方框 ----------------------------------------
run(`
  clearFormula();
  insertNode(makeTemplate('sum'), '求和');
`);
const hit = run('lastHits.find((h) => h.kind === "placeholder")');
check('存在可点击方框热区', !!hit, true);
run(`handleClick(${(hit.x1 + hit.x2) / 2}, ${(hit.y1 + hit.y2) / 2});`);
check('点击后聚焦到方框', run('activeItem().kind'), 'placeholder');

// -- 点击文本：光标落在最近的字符间隙 ------------------------------------------
run(`
  clearFormula();
  insertText('abc');
`);
const textHit = run('lastHits.find((h) => h.kind === "text")');
run(`handleClick(${textHit.carets[textHit.carets.length - 1] - 1}, ${(textHit.y1 + textHit.y2) / 2});`);
check('点击文本右端时光标在末尾', run('caret'), 3);

// -- 布局几何：上下限在符号两侧、分式线在基线上 --------------------------------
const geo = run(`
  (() => {
    clearFormula();
    insertNode(makeTemplate('sum'), '求和');
    insertText('i=1'); moveSelection(1); insertText('n'); moveSelection(1); insertText('i^2');
    const L = layoutSlot(rootSlot, 0, 0, 28);
    const sumNode = rootSlot.items.find((it) => it && it.kind === 'sum');
    const upHit = L.hits.find((h) => h.slot === sumNode.upper);
    const loHit = L.hits.find((h) => h.slot === sumNode.lower);
    const bodyHit = L.hits.find((h) => h.slot === sumNode.body);
    const node = L.nodes.find((n) => n.node === sumNode);
    const glyph = L.draws.find((d) => d.type === 'text' && d.text === '∑');
    return {
      hasNode: !!node,
      hasGlyph: !!glyph && glyph.y === 0,
      upperAboveLower: (upHit.y1 + upHit.y2) / 2 < (loHit.y1 + loHit.y2) / 2,
      bodyRightOfColumn: bodyHit.x1 > upHit.x1,
      nodeHeight: node ? node.y2 - node.y1 : 0,
      nodeWidth: node ? node.x2 - node.x1 : 0,
    };
  })()
`);
check('求和结构有包围盒', geo.hasNode, true);
check('∑ 字形画在基线上', geo.hasGlyph, true);
check('求和上限在积分下限上方', geo.upperAboveLower, true);
check('求和项在符号列右侧', geo.bodyRightOfColumn, true);
check('结构包围盒有高度', geo.nodeHeight > 20, true);
check('结构包围盒有宽度', geo.nodeWidth > 40, true);

const fracGeo = run(`
  (() => {
    clearFormula();
    insertNode(makeTemplate('fraction'), '分式');
    insertText('a'); moveSelection(1); insertText('b');
    const L = layoutSlot(rootSlot, 0, 0, 28);
    const line = L.draws.find((d) => d.type === 'line' && Math.abs(d.y1) < 0.01 && Math.abs(d.y2) < 0.01);
    const node = L.nodes.find((n) => n.node.kind === 'fraction');
    return { hasLine: !!line, lineWidth: line ? line.x2 - line.x1 : 0, height: node ? node.y2 - node.y1 : 0 };
  })()
`);
check('分式分数线画在基线上', fracGeo.hasLine, true);
check('分式线宽度覆盖分子分母', fracGeo.lineWidth > 20, true);
check('分式结构有高度（上下两行）', fracGeo.height > 30, true);

// -- 其余模板 ----------------------------------------------------------------
run(`clearFormula(); insertNode(makeTemplate('integral'), '积分');
     insertText('0'); moveSelection(1); insertText('n'); moveSelection(1); insertText('x'); moveSelection(1); insertText('x');`);
check('积分 LaTeX', run('serializeSlot(rootSlot).trim()'), '\\int_{0}^{n} x\\,\\mathrm{d}x');

run(`clearFormula(); insertNode(makeTemplate('power'), '乘方'); insertText('x'); moveSelection(1); insertText('2');`);
check('乘方 LaTeX', run('serializeSlot(rootSlot).trim()'), '{x}^{2}');

run(`clearFormula(); insertNode(makeTemplate('sqrt'), '开方'); insertText('a');`);
check('平方根 LaTeX', run('serializeSlot(rootSlot).trim()'), '\\sqrt{a}');
check('平方根画出了根号横线', run('layoutSlot(rootSlot,0,0,28).draws.filter((d) => d.type === "line").length >= 3'), true);

run(`clearFormula(); insertText('·'); insertText('a');`);
check('符号 · 映射为 \\cdot', run('serializeSlot(rootSlot).trim()'), '\\cdot a');

console.log('');
if (failed) {
  console.log(failed + ' 个用例失败');
  process.exit(1);
}
console.log('全部用例通过：' + (drawnTexts.length ? '画布绘制 ' + drawnTexts.length + ' 个文本' : ''));
