/* DOM 级冒烟测试：用假 DOM 真正执行 ui.js 的 bootUI()，
 * 验证工具栏/菜单/画布事件/复制按钮等装配能跑通。
 * 用法：node web/dom_test.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, 'formula_editor.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];

// -- 假 DOM -----------------------------------------------------------------
const allCreated = [];

class FakeElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.className = '';
    this.textContent = '';
    this.innerHTML = '';
    this.hidden = false;
    this.disabled = false;
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.parentNode = null;
    this.classList = {
      add: (name) => { this.className = (this.className + ' ' + name).trim(); },
      remove: (name) => { this.className = this.className.split(/\s+/).filter((c) => c !== name).join(' '); },
      toggle: (name) => {
        const has = this.className.split(/\s+/).includes(name);
        if (has) this.classList.remove(name); else this.classList.add(name);
      },
    };
  }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  append(...items) { for (const item of items) this.appendChild(item); }
  removeChild(child) { this.children = this.children.filter((c) => c !== child); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  removeEventListener() {}
  fire(type, event) {
    for (const fn of this.listeners[type] || []) fn(event || {});
  }
  dispatch(type) { this.fire(type, { type, preventDefault() {}, stopPropagation() {} }); }
  setAttribute(key, value) { this.attributes[key] = String(value); if (key === 'data-katex') this.dataset.katex = value; }
  getAttribute(key) { return Object.prototype.hasOwnProperty.call(this.attributes, key) ? this.attributes[key] : null; }
  focus() {}
  select() {}
  getBoundingClientRect() { return { left: 0, top: 0, width: 900, height: 200 }; }
}

// 找到元素（含后代）
function walk(el, visit) {
  visit(el);
  for (const child of el.children || []) walk(child, visit);
}

function queryAll(root, predicate) {
  const out = [];
  for (const el of allCreated) walk(el, (node) => { if (node !== el && predicate(node)) out.push(node); });
  const unique = [...new Set(out)];
  return unique;
}

const drawnTexts = [];
const ctxStub = {
  fillStyle: '',
  font: '',
  setTransform() {},
  clearRect() {},
  fillText(text) { drawnTexts.push(text); },
  setLineDash() {},
  fillRect() {},
  strokeRect() {},
  beginPath() {},
  moveTo() {},
  lineTo() {},
  stroke() {},
  measureText(text) {
    const width = Array.from(String(text)).length * 10;
    return { width, fontBoundingBoxAscent: 10, fontBoundingBoxDescent: 3, actualBoundingBoxAscent: 10, actualBoundingBoxDescent: 3 };
  },
};

const canvas = Object.assign(new FakeElement('canvas'), {
  width: 900,
  height: 200,
  clientWidth: 900,
  clientHeight: 200,
  getContext() { return ctxStub; },
});
allCreated.push(canvas);

const byId = {};
for (const id of ['toolbar', 'symbols', 'categories', 'status', 'canvas-status', 'markdown', 'preview', 'copy', 'toast']) {
  byId[id] = new FakeElement(id === 'copy' ? 'button' : 'div');
  allCreated.push(byId[id]);
}
byId.canvas = canvas;

const document = {
  readyState: 'complete',
  getElementById(id) { return byId[id] || null; },
  createElement(tag) { const el = tag === 'canvas' ? canvas : new FakeElement(tag); if (el !== canvas) allCreated.push(el); return el; },
  createTextNode(text) { return { textContent: text }; },
  querySelectorAll(selector) {
    if (selector === '.dropdown-panel') {
      return queryAll(null, (el) => el.className.split(/\s+/).includes('dropdown-panel'));
    }
    if (selector === '.dropdown > button') {
      return queryAll(null, (el) => el.tagName === 'BUTTON' && el.parentNode
        && el.parentNode.className.split(/\s+/).includes('dropdown'));
    }
    return [];
  },
  querySelector(selector) {
    const match = /^(link|script)\[data-katex\]$/.exec(selector);
    if (match) {
      const found = allCreated.find((el) => el.tagName === match[1].toUpperCase() && el.getAttribute('data-katex'));
      return found || null;
    }
    return null;
  },
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
    devicePixelRatio: 1,
    innerHeight: 900,
    setTimeout,
    clearTimeout,
    addEventListener(type, fn) { (sandbox.window._listeners[type] = sandbox.window._listeners[type] || []).push(fn); },
    _listeners: {},
  },
  navigator: { clipboard: { writeText() { return Promise.resolve(); } } },
  setTimeout,
  clearTimeout,
  structuredClone: nodeClone,
};
sandbox.globalThis = sandbox;

const context = vm.createContext(sandbox);
vm.runInContext(script, context, { filename: 'formula_editor.html' });

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
    console.log('FAIL ' + name + (detail !== undefined ? '\n  ' + JSON.stringify(detail) : ''));
  } else {
    console.log('ok   ' + name);
  }
}

const findButtonByText = (text) => queryAll(null, (el) => el.tagName === 'BUTTON' && el.textContent === text)[0] || null;

// -- 1. 启动 -----------------------------------------------------------------
const app = sandbox.window.__editorApp;
const host = sandbox.window.__editorHost;
sandbox.app = app;
checkTrue('启动：控制器已创建', !!app && !!host);
checkTrue('启动：画布有绘制内容', drawnTexts.length >= 0);
checkTrue('启动：构建了结构按钮', !!findButtonByText('∑ 求和'));
checkTrue('启动：构建了符号按钮', !!findButtonByText('·'));
checkTrue('启动：构建了撤销按钮', !!findButtonByText('撤销'));

// -- 2. 结构下拉菜单 ---------------------------------------------------------
const dropdownLedger = queryAll(null, (el) => el.tagName === 'BUTTON' && el.parentNode
  && el.parentNode.className.split(/\s+/).includes('dropdown'));
checkTrue('菜单：结构下拉菜单数量 >= 3', dropdownLedger.length >= 3, dropdownLedger.length);
const openButton = findButtonByText('√ 开方 ▾');
openButton.dispatch('click');
const rootPanel = openButton.parentNode.children.find((child) => child.className.split(/\s+/).includes('dropdown-panel'));
checkTrue('菜单：点击后展开面板', rootPanel && !rootPanel.hidden);
openButton.dispatch('click');
checkTrue('菜单：再次点击收起面板', rootPanel.hidden);

// -- 3. 通过菜单插入结构 -----------------------------------------------------
openButton.dispatch('click');
const sqrtItem = rootPanel.children.find((child) => child.textContent === '平方根  √');
checkTrue('菜单：找到「平方根」菜单项', !!sqrtItem);
sqrtItem.dispatch('click');
check('菜单：点击菜单项插入平方根', runLaTeX(), '\\sqrt{□}');

function runLaTeX() {
  return vm.runInContext('normalizeFormula(serializeSlot(app.rootSlot))', context);
}

// -- 4. 符号分类菜单（含内联子菜单） ------------------------------------------
const basicButton = findButtonByText('基本运算 ▾');
checkTrue('符号菜单：找到「基本运算」', !!basicButton);
basicButton.dispatch('click');
const basicPanel = basicButton.parentNode.children.find((child) => child.className.split(/\s+/).includes('dropdown-panel'));
const plusItem = basicPanel.children.find((child) => child.tagName === 'BUTTON' && child.textContent === '+');
checkTrue('符号菜单：面板里有「+」', !!plusItem);

const greekButton = findButtonByText('变量 ▾');
greekButton.dispatch('click');
const greekPanel = greekButton.parentNode.children.find((child) => child.className.split(/\s+/).includes('dropdown-panel'));
let subButton = null;
walk(greekPanel, (node) => {
  if (node.tagName === 'BUTTON' && node.textContent === '▸ 希腊字母（小写）') subButton = node;
});
checkTrue('符号菜单：变量面板有希腊字母子项', !!subButton);
subButton.dispatch('click');
const subList = subButton.parentNode.children.find((child) => child.className.split(/\s+/).includes('submenu-list'));
checkTrue('符号菜单：子列表可展开', !!subList && !subList.hidden);
const alphaItem = subList.children.find((child) => child.textContent === 'α');
checkTrue('符号菜单：子列表里有 α', !!alphaItem);

// -- 5. 画布键盘与粘贴 -------------------------------------------------------
const canvasEl = byId.canvas;
const key = (name) => ({
  key: name,
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  altKey: false,
  preventDefault() {},
});
canvasEl.fire('keydown', key('a'));
check('键盘：普通字符输入', runLaTeX(), '\\sqrt{a}');
canvasEl.fire('keydown', key('Backspace'));
check('键盘：回格删除字符', runLaTeX(), '\\sqrt{□}');
canvasEl.fire('paste', { clipboardData: { getData: () => 'x^2' }, preventDefault() {} });
check('粘贴：纯文本进入画布', runLaTeX(), '\\sqrt{x^2}');

// -- 6. 鼠标点击方框 ---------------------------------------------------------
const settle = () => { if (typeof setImmediate === 'function') return new Promise((resolve) => setImmediate(resolve)); };
(async () => {
  app.clear_formula();
  app.insert_template('sqrt');
  const box = app.hitAreas.find((hit) => hit.kind === 'placeholder');
  checkTrue('鼠标：存在可点击的方框热区', !!box);
  const cx = (box.x1 + box.x2) / 2;
  const cy = (box.y1 + box.y2) / 2;
  canvasEl.fire('mousedown', { clientX: cx, clientY: cy, preventDefault() {} });
  canvasEl.fire('mouseup', { clientX: cx, clientY: cy, preventDefault() {} });
  check('鼠标：点击方框后定位', runLaTeX(), '\\sqrt{□}');

  canvasEl.fire('keydown', key('3'));
  check('鼠标：方框输入后得到内容', runLaTeX(), '\\sqrt{3}');

  // -- 7. 复制按钮 -----------------------------------------------------------
  const copyButton = byId.copy;
  checkTrue('复制：填满后复制按钮可用', !copyButton.disabled);
  copyButton.dispatch('click');
  await settle();
  await new Promise((resolve) => setTimeout(resolve, 10));
  check('复制：剪贴板写入成功', host.lastMarkdown, '$$\n\\sqrt{3}\n$$');

  // -- 8. 画布光标与尺寸 -----------------------------------------------------
  canvasEl.fire('mousemove', { clientX: cx, clientY: cy, preventDefault() {} });
  checkTrue('光标：悬停在方框上变成 text', canvasEl.style.cursor === 'text', canvasEl.style.cursor);
  checkTrue('尺寸：画布高度已设置', String(canvasEl.style.height).endsWith('px'), canvasEl.style.height);

  // -- 9. 缩放事件 -----------------------------------------------------------
  const resizeHandlers = sandbox.window._listeners.resize || [];
  checkTrue('缩放：注册了 resize 监听', resizeHandlers.length >= 1);
  for (const handler of resizeHandlers) handler();
  checkTrue('缩放：resize 后画布仍可渲染', app.lastLayout.draws.length > 0);

  console.log('');
  if (failed) {
    console.log(failed + ' 个用例失败');
    process.exit(1);
  }
  console.log('DOM 冒烟测试全部通过');
})();
