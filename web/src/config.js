/* 全局常量、主题色、符号表和模板名称（对应 formula_editor_app/config.py）。 */
'use strict';

const APP_TITLE = '公式编辑器 · Markdown 实时输出';
const PLACEHOLDER = '□';

const TEMPLATE_LABELS = {
  sum: '求和',
  integral: '积分',
  derivative: '微分',
  fraction: '分式',
  power: '上角标',
  subscript: '下角标',
  sub_sup: '上下角标',
  hat: '帽子',
  widehat: '宽帽子',
  bar: '横线',
  overline: '上划线',
  tilde: '波浪',
  widetilde: '宽波浪',
  dot: '单点',
  ddot: '双点',
  vec: '矢量',
  sqrt: '开方',
  nth_root: 'n 次根',
};

// 顶标：结构内部的内容上方加一个标记，导出为对应的 LaTeX 命令。
const ACCENT_LATEX = {
  hat: '\\hat',
  widehat: '\\widehat',
  bar: '\\bar',
  overline: '\\overline',
  tilde: '\\tilde',
  widetilde: '\\widetilde',
  dot: '\\dot',
  ddot: '\\ddot',
  vec: '\\vec',
};

// 单符号运算符：画布显示 Unicode 字形，导出时替换为对应的 LaTeX 命令。
// LaTeX 命令一律带尾随空格，避免与后面的字母粘成一个未知命令。
const SYMBOL_LATEX = {
  // -- 基本运算：四则运算与比较 -----------------------------------------
  '·': '\\cdot ',
  '×': '\\times ',
  '÷': '\\div ',
  '±': '\\pm ',
  '∓': '\\mp ',
  '≤': '\\leq ',
  '≥': '\\geq ',
  '≠': '\\neq ',
  '≈': '\\approx ',
  '≡': '\\equiv ',
  '∝': '\\propto ',
  '≅': '\\cong ',
  '≪': '\\ll ',
  '≫': '\\gg ',
  '∘': '\\circ ',
  '⊥': '\\perp ',
  '∥': '\\parallel ',
  // -- 集合 -------------------------------------------------------------
  '∈': '\\in ',
  '∉': '\\notin ',
  '∋': '\\ni ',
  '⊂': '\\subset ',
  '⊆': '\\subseteq ',
  '⊄': '\\not\\subset ',
  '⊊': '\\subsetneq ',
  '⊃': '\\supset ',
  '⊇': '\\supseteq ',
  '∪': '\\cup ',
  '∩': '\\cap ',
  '∖': '\\setminus ',
  '∅': '\\emptyset ',
  'ℕ': '\\mathbb{N}',
  'ℤ': '\\mathbb{Z}',
  'ℚ': '\\mathbb{Q}',
  'ℝ': '\\mathbb{R}',
  'ℂ': '\\mathbb{C}',
  // -- 微积分 -----------------------------------------------------------
  '∫': '\\int ',
  '∬': '\\iint ',
  '∭': '\\iiint ',
  '∮': '\\oint ',
  '∂': '\\partial ',
  '∇': '\\nabla ',
  '∞': '\\infty ',
  'Δ': '\\Delta ',
  '′': '^{\\prime}',
  '″': '^{\\prime\\prime}',
  // -- 逻辑与箭头 -------------------------------------------------------
  '∧': '\\wedge ',
  '∨': '\\vee ',
  '¬': '\\neg ',
  '∀': '\\forall ',
  '∃': '\\exists ',
  '∴': '\\therefore ',
  '∵': '\\because ',
  '→': '\\to ',
  '←': '\\leftarrow ',
  '↔': '\\leftrightarrow ',
  '⇒': '\\Rightarrow ',
  '⇐': '\\Leftarrow ',
  '⇔': '\\Leftrightarrow ',
  // -- 变量符号：希腊字母 ----------------------------------------------
  'α': '\\alpha ',
  'β': '\\beta ',
  'γ': '\\gamma ',
  'δ': '\\delta ',
  'ε': '\\varepsilon ',
  'ζ': '\\zeta ',
  'η': '\\eta ',
  'θ': '\\theta ',
  'ι': '\\iota ',
  'κ': '\\kappa ',
  'λ': '\\lambda ',
  'μ': '\\mu ',
  'ν': '\\nu ',
  'ξ': '\\xi ',
  'π': '\\pi ',
  'ρ': '\\rho ',
  'σ': '\\sigma ',
  'τ': '\\tau ',
  'υ': '\\upsilon ',
  'φ': '\\phi ',
  'χ': '\\chi ',
  'ψ': '\\psi ',
  'ω': '\\omega ',
  'Γ': '\\Gamma ',
  'Θ': '\\Theta ',
  'Λ': '\\Lambda ',
  'Ξ': '\\Xi ',
  'Π': '\\Pi ',
  'Σ': '\\Sigma ',
  'Υ': '\\Upsilon ',
  'Φ': '\\Phi ',
  'Ψ': '\\Psi ',
  'Ω': '\\Omega ',
};

// 数集符号（字母类字形，但按正体符号绘制）。
const NUMBER_SET_SYMBOLS = ['ℕ', 'ℤ', 'ℚ', 'ℝ', 'ℂ'];

// 画布上用「符号字体」正体绘制的字符：非字母类符号 + 数集字母。
// 拉丁字母、希腊字母仍然使用数学字体，小写字母按变量斜体排版。
const SYMBOL_FONT_CHARS = new Set(
  Object.keys(SYMBOL_LATEX)
    .filter((char) => !/\p{L}/u.test(char))
    .concat(NUMBER_SET_SYMBOLS),
);

// 四则运算等单行算符按「字符」处理：它们不携带结构位置，也不参与自动拆分；
// 删除时作为普通字符删掉，不会连带删除相邻的结构。
// 由符号表中所有非字母符号自动汇总，再补上 ASCII 四则运算字符。
const PLAIN_OPERATOR_CHARS = new Set(
  '+-*/=<>'.split('').concat(
    Object.keys(SYMBOL_LATEX).filter((char) => !/\p{L}/u.test(char)),
  ),
);

const PRIMARY_SYMBOLS = ['·', '×', '±', '∓', '≤', '≥', '≠', '∞', '∂', '∇'];

// 「更多符号」面板按类别拆分成多个下拉菜单。
// 每一项是 [菜单名, 条目数组]；条目既可以是单个符号，也可以是
// [子菜单名, 条目数组]，用于把较长的分类（如希腊字母）收进级联菜单。
const SYMBOL_GROUPS = [
  [
    '基本运算',
    ['+', '-', '*', '/', '=', '<', '>', '≠', '≤', '≥', '≈', '≡', '∝', '×', '÷', '·', '±', '∓', '≅', '≪', '≫', '∘'],
  ],
  [
    '集合',
    ['∈', '∉', '∋', '⊂', '⊆', '⊄', '⊊', '⊃', '⊇', '∪', '∩', '∖', '∅'].concat(NUMBER_SET_SYMBOLS),
  ],
  [
    '微积分',
    ['∫', '∬', '∭', '∮', '∂', '∇', '∞', 'Δ', '′', '″'],
  ],
  [
    '变量',
    [
      ['希腊字母（小写）', ['α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η', 'θ', 'ι', 'κ', 'λ', 'μ', 'ν', 'ξ', 'π', 'ρ', 'σ', 'τ', 'υ', 'φ', 'χ', 'ψ', 'ω']],
      ['希腊字母（大写）', ['Γ', 'Δ', 'Θ', 'Λ', 'Ξ', 'Π', 'Σ', 'Υ', 'Φ', 'Ψ', 'Ω']],
    ],
  ],
  [
    '逻辑与箭头',
    ['∧', '∨', '¬', '∀', '∃', '∴', '∵', '→', '←', '↔', '⇒', '⇐', '⇔', '⊥', '∥'],
  ],
];

// 「更多符号」里的结构分类：菜单项是 [显示名, 模板键]，点击后插入对应结构。
const TEMPLATE_GROUPS = [
  [
    '角标',
    [
      ['上角标（乘方）  x^n', 'power'],
      ['下角标  x_n', 'subscript'],
      ['上下角标  x_n^m', 'sub_sup'],
    ],
  ],
  [
    '顶标',
    [
      ['帽子（hat）', 'hat'],
      ['宽帽子（widehat）', 'widehat'],
      ['横线（bar）', 'bar'],
      ['上划线（overline）', 'overline'],
      ['波浪（tilde）', 'tilde'],
      ['宽波浪（widetilde）', 'widetilde'],
      ['单点（dot）', 'dot'],
      ['双点（ddot）', 'ddot'],
      ['矢量（vec）', 'vec'],
    ],
  ],
];

/** 按面板顺序给出全部可插入符号，级联子菜单里的符号也会展开。 */
function iterPanelGlyphs() {
  const out = [];
  const walk = (entries) => {
    for (const entry of entries) {
      if (Array.isArray(entry)) walk(entry[1]);
      else out.push(entry);
    }
  };
  for (const [, entries] of SYMBOL_GROUPS) walk(entries);
  return out;
}

const BG = '#f3f5fb';
const CARD = '#ffffff';
const BORDER = '#dfe4f1';
const TEXT = '#1f2937';
const MUTED = '#6b7280';
const ACCENT = '#4f46e5';
const ACCENT_DARK = '#4338ca';
const SUCCESS = '#15803d';
const WARNING = '#b45309';
const DANGER = '#b91c1c';
const SOFT_ACCENT = '#eef2ff';
const CANVAS_BG = '#fcfcff';
const PREVIEW_BG = '#fcfcff';
const EDITOR_BG = '#fbfcff';
const PLACEHOLDER_FILL = '#fff7dd';
const PLACEHOLDER_OUTLINE = '#d99a2b';
const SELECTION_FILL = '#dbe2fe';

const BASE_FONT_SIZE = 28;
// 主画布按顺序试排字号；输出预览区更小，允许再缩两档。
const AUTO_FIT_SIZES = [28, 26, 24, 22, 20, 18, 16, 14, 12];
const PREVIEW_FIT_SIZES = AUTO_FIT_SIZES.concat([10, 8]);
const ITEM_GAP = 4;
const MIN_CANVAS_HEIGHT = 120;
const MAX_CANVAS_HEIGHT = 320;
const CANVAS_PADDING = 28;

// 画布字体：与桌面版保持一致（Windows 自带字体），度量可以直接沿用。
const MATH_FONT = 'Cambria, "Times New Roman", Georgia, serif';
const SYMBOL_FONT = '"Segoe UI Symbol", "Cambria Math", "Arial Unicode MS", Arial, sans-serif';
const UI_FONT = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif';
const MONO_FONT = '"Cascadia Code", Consolas, "Courier New", monospace';
