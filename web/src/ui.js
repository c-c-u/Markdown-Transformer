/* 网页外壳：DOM 界面、画布事件、KaTeX 预览与剪贴板（对应 ui.py + preview.py + clipboard.py）。
 * 由 build.mjs 与其余源码一起内联进单个 HTML 文件。 */
'use strict';

function showToast(title, message) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = title + (message ? '：' + message : '');
  toast.classList.add('show');
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.remove('show'), 4200);
}

function ensureKatex() {
  if (window.katex) return;
  if (!document.querySelector('link[data-katex]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css';
    link.setAttribute('data-katex', '1');
    document.head.appendChild(link);
  }
  if (!document.querySelector('script[data-katex]')) {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js';
    script.setAttribute('data-katex', '1');
    script.onload = () => {
      const pending = bootUI._pending;
      if (pending && pending.latex) renderPreviewInto(pending.host, pending.latex, '');
    };
    document.head.appendChild(script);
  }
}

function bootUI() {
  const canvas = document.getElementById('canvas');
  const ctx = canvas.getContext('2d');
  const statusEl = document.getElementById('status');
  const canvasStatusEl = document.getElementById('canvas-status');
  const markdownEl = document.getElementById('markdown');
  const previewEl = document.getElementById('preview');
  const copyBtn = document.getElementById('copy');

  const host = {
    canvas: canvas,
    ctx: ctx,
    lastMarkdown: '',
    lastPreview: { latex: '', message: '', rendered: false },

    setStatus(text, kind) {
      statusEl.textContent = text;
      statusEl.className = 'status-text ' + (kind || 'muted');
    },
    setCanvasStatus(text) {
      canvasStatusEl.textContent = text;
    },
    alert(title, message) {
      showToast(title, message);
    },
    focus() {
      try { canvas.focus({ preventScroll: true }); } catch (err) { canvas.focus(); }
    },
    setCursor(name) {
      canvas.style.cursor = name === 'text' ? 'text' : name === 'hand' ? 'pointer' : 'default';
    },
    canvasWidth() {
      return canvas.clientWidth || 640;
    },
    windowHeight() {
      return window.innerHeight || 900;
    },
    devicePixelRatio() {
      return window.devicePixelRatio || 1;
    },
    prepareCanvas(cssWidth, cssHeight) {
      const dpr = this.devicePixelRatio();
      canvas.width = Math.round(cssWidth * dpr);
      canvas.height = Math.round(cssHeight * dpr);
      canvas.style.height = cssHeight + 'px';
    },
    syncMarkdown(markdown) {
      this.lastMarkdown = markdown;
      markdownEl.textContent = markdown;
      copyBtn.disabled = !markdown;
    },
    renderPreview(latex, message) {
      renderPreviewInto(this, latex, message);
    },
    schedule(callback, delayMs) {
      return setTimeout(callback, delayMs);
    },
    cancel(id) {
      clearTimeout(id);
    },
    copyToClipboard(text, done) {
      const finish = (ok) => { if (typeof done === 'function') done(ok); };
      const fallback = () => {
        try {
          const area = document.createElement('textarea');
          area.value = text;
          area.style.position = 'fixed';
          area.style.opacity = '0';
          document.body.appendChild(area);
          area.select();
          const ok = document.execCommand('copy');
          document.body.removeChild(area);
          finish(!!ok);
        } catch (err) {
          finish(false);
        }
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => finish(true)).catch(fallback);
      } else {
        fallback();
      }
    },
  };

  const app = new EditorApp(host);

  // -- 工具栏 --------------------------------------------------------------

  const toolbar = document.getElementById('toolbar');
  const symbolRow = document.getElementById('symbols');
  const categoryRow = document.getElementById('categories');

  const makeButton = (label, onClick, className) => {
    const button = document.createElement('button');
    button.className = className || 'tool-btn';
    button.textContent = label;
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      onClick();
      canvas.focus();
    });
    return button;
  };

  const structureRow = document.createElement('div');
  structureRow.className = 'row';
  toolbar.appendChild(structureRow);

  for (const [key, label] of [
    ['sum', '∑ 求和'],
    ['integral', '∫ 积分'],
    ['derivative', 'd/dx 微分'],
    ['fraction', 'a/b 分式'],
  ]) {
    structureRow.appendChild(makeButton(label, () => app.insert_template(key)));
  }

  const makeDropdown = (parent, label, buildPanel, extraClass) => {
    const wrap = document.createElement('div');
    wrap.className = 'dropdown';
    const button = document.createElement('button');
    button.className = extraClass || 'tool-btn';
    button.textContent = label;
    const panel = document.createElement('div');
    panel.className = 'dropdown-panel';
    panel.hidden = true;
    buildPanel(panel, () => { panel.hidden = true; });
    wrap.append(button, panel);
    parent.appendChild(wrap);

    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const willOpen = panel.hidden;
      closeAllPanels();
      panel.hidden = !willOpen;
      button.classList.toggle('open', willOpen);
    });
    return wrap;
  };

  const closeAllPanels = () => {
    for (const panel of document.querySelectorAll('.dropdown-panel')) panel.hidden = true;
    for (const button of document.querySelectorAll('.dropdown > button')) button.classList.remove('open');
  };

  makeDropdown(structureRow, '√ 开方 ▾', (panel, close) => {
    for (const [label, key] of [['平方根  √', 'sqrt'], ['n 次根  ⁿ√', 'nth_root']]) {
      const item = document.createElement('button');
      item.className = 'menu-item';
      item.textContent = label;
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        close();
        app.insert_template(key);
        canvas.focus();
      });
      panel.appendChild(item);
    }
  });

  makeDropdown(structureRow, '矩阵 ▾', (panel, close) => {
    for (const [label, rows, cols] of [
      ['2 × 2 矩阵', 2, 2],
      ['3 × 3 矩阵', 3, 3],
      ['2 × 3 矩阵', 2, 3],
      ['3 × 2 矩阵', 3, 2],
    ]) {
      const item = document.createElement('button');
      item.className = 'menu-item';
      item.textContent = label;
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        close();
        app.insert_matrix(rows, cols);
        canvas.focus();
      });
      panel.appendChild(item);
    }
  });

  makeDropdown(structureRow, '向量 ▾', (panel, close) => {
    for (const [label, rows, cols] of [
      ['2 × 1 列向量', 2, 1],
      ['3 × 1 列向量', 3, 1],
      ['1 × 2 行向量', 1, 2],
      ['1 × 3 行向量', 1, 3],
    ]) {
      const item = document.createElement('button');
      item.className = 'menu-item';
      item.textContent = label;
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        close();
        app.insert_matrix(rows, cols, 'vector');
        canvas.focus();
      });
      panel.appendChild(item);
    }
  });

  const separator = document.createElement('span');
  separator.className = 'sep';
  structureRow.appendChild(separator);
  structureRow.appendChild(makeButton('撤销', () => app.undo(), 'ghost-btn'));
  structureRow.appendChild(makeButton('清空', () => app.clear_formula(), 'ghost-btn'));

  // -- 符号面板 -------------------------------------------------------------

  const primaryRow = document.createElement('div');
  primaryRow.className = 'row';
  const primaryLabel = document.createElement('span');
  primaryLabel.className = 'row-label';
  primaryLabel.textContent = '运算符';
  primaryRow.appendChild(primaryLabel);
  for (const glyph of PRIMARY_SYMBOLS) {
    primaryRow.appendChild(makeButton(glyph, () => app.insert_symbol(glyph), 'symbol-btn'));
  }
  symbolRow.appendChild(primaryRow);

  const categoryLabelRow = document.createElement('div');
  categoryLabelRow.className = 'row';
  const categoryLabel = document.createElement('span');
  categoryLabel.className = 'row-label';
  categoryLabel.textContent = '更多符号';
  categoryLabelRow.appendChild(categoryLabel);

  const buildSymbolMenuEntries = (panel, entries) => {
    for (const entry of entries) {
      if (Array.isArray(entry)) {
        // 级联子菜单：变量 → 希腊字母（小写 / 大写）。用内联展开，
        // 避免被面板的滚动容器裁切。
        const subWrap = document.createElement('div');
        subWrap.className = 'submenu';
        const subButton = document.createElement('button');
        subButton.className = 'menu-item sub';
        subButton.textContent = '▸ ' + entry[0];
        const subList = document.createElement('div');
        subList.className = 'submenu-list';
        subList.hidden = true;
        buildSymbolMenuEntries(subList, entry[1]);
        subWrap.append(subButton, subList);
        subButton.addEventListener('click', (event) => {
          event.stopPropagation();
          subList.hidden = !subList.hidden;
        });
        panel.appendChild(subWrap);
      } else {
        const item = document.createElement('button');
        item.className = 'menu-item glyph';
        item.textContent = entry;
        item.addEventListener('click', (event) => {
          event.stopPropagation();
          closeAllPanels();
          app.insert_symbol(entry);
          canvas.focus();
        });
        panel.appendChild(item);
      }
    }
  };

  for (const [groupLabel, entries] of SYMBOL_GROUPS) {
    makeDropdown(categoryLabelRow, groupLabel + ' ▾', (panel) => buildSymbolMenuEntries(panel, entries));
  }

  for (const [groupLabel, entries] of TEMPLATE_GROUPS) {
    makeDropdown(categoryLabelRow, groupLabel + ' ▾', (panel, close) => {
      for (const [label, key] of entries) {
        const item = document.createElement('button');
        item.className = 'menu-item';
        item.textContent = label;
        item.addEventListener('click', (event) => {
          event.stopPropagation();
          close();
          app.insert_template(key);
          canvas.focus();
        });
        panel.appendChild(item);
      }
    });
  }

  categoryRow.appendChild(categoryLabelRow);

  document.addEventListener('click', () => closeAllPanels());

  // -- 画布事件 -------------------------------------------------------------

  const point = (event) => {
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  let pressing = false;

  canvas.addEventListener('mousedown', (event) => {
    event.preventDefault();
    canvas.focus();
    pressing = true;
    const p = point(event);
    app._on_canvas_drag_start({ x: p.x, y: p.y });
  });

  canvas.addEventListener('mousemove', (event) => {
    const p = point(event);
    app._on_canvas_motion(p.x, p.y);
    if (pressing) app._on_canvas_drag_motion({ x: p.x, y: p.y });
  });

  canvas.addEventListener('mouseup', (event) => {
    const p = point(event);
    pressing = false;
    app._on_canvas_drag_end({ x: p.x, y: p.y });
    canvas.focus();
  });

  canvas.addEventListener('mouseleave', () => {
    pressing = false;
    app._on_canvas_leave();
  });

  canvas.addEventListener('keydown', (event) => {
    if (event.isComposing || event.key === 'Process') return;
    const result = app.handleKeyDown(event);
    if (result === 'break') event.preventDefault();
  });

  let composing = false;
  canvas.addEventListener('compositionstart', () => { composing = true; });
  canvas.addEventListener('compositionend', (event) => {
    composing = false;
    if (event.data) app._insert_text(event.data);
  });

  canvas.addEventListener('paste', (event) => {
    if (composing) return;
    const data = event.clipboardData || window.clipboardData;
    if (!data) return;
    event.preventDefault();
    const text = data.getData('text');
    if (text) app.paste_text(text);
  });

  window.addEventListener('resize', () => app.handleResize());

  copyBtn.addEventListener('click', () => app.copy_markdown());

  ensureKatex();
  app.start();
  app._render_canvas();

  // 供调试与无头测试使用
  window.__editorApp = app;
  window.__editorHost = host;
}

/** 渲染预览区：KaTeX 可用时渲染公式，否则回退成源码（离线可用）。 */
function renderPreviewInto(host, latex, message) {
  const previewEl = document.getElementById('preview');
  previewEl.innerHTML = '';
  bootUI._pending = { host: host, latex: latex || '' };
  if (message) {
    const div = document.createElement('div');
    div.className = 'preview-msg';
    div.textContent = message;
    previewEl.appendChild(div);
    host.lastPreview = { latex: latex, message: message, rendered: false };
    return;
  }
  if (!latex) {
    const div = document.createElement('div');
    div.className = 'preview-msg';
    div.textContent = '填写公式后\n这里显示渲染预览';
    previewEl.appendChild(div);
    host.lastPreview = { latex: '', message: '', rendered: false };
    return;
  }
  if (window.katex) {
    try {
      window.katex.render(latex, previewEl, { displayMode: true, throwOnError: false });
      host.lastPreview = { latex: latex, message: '', rendered: true };
      return;
    } catch (err) {
      // 落到源码回退
    }
  }
  const note = document.createElement('div');
  note.className = 'preview-msg';
  note.textContent = '未加载 KaTeX，显示 LaTeX 源码：';
  const pre = document.createElement('pre');
  pre.className = 'preview-fallback';
  pre.textContent = latex;
  previewEl.append(note, pre);
  host.lastPreview = { latex: latex, message: '', rendered: true, fallback: true };
}

if (typeof window !== 'undefined' && !window.__NO_UI_BOOT__) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => bootUI());
  } else {
    bootUI();
  }
}
