# 公式编辑器 · 网页版迁移方案

> 状态：方案分析（未改动任何现有代码）
> 目标读者：本项目维护者
> 结论摘要：可行性高；推荐"路线 A：Pyodide 保留 Python 逻辑，换掉 Tk 外壳"；预估 5 人日，另需 0.5 天字体探针先行验证。

---

## 1. 背景与目标

现有成果是一个 **Python 3.12 + Tkinter** 的桌面公式编辑器：

- 画布是自绘的自定义编辑器，不是 LaTeX 源码预览；
- 公式树 + 编辑语义（结构化删除、隐藏空位、拖选、LaTeX 序列化）已完成并有冒烟测试覆盖；
- 实时输出 Markdown（`$$ ... $$`），右侧用 matplotlib mathtext 渲染预览。

已确认的使用场景（影响取舍）：

| 维度 | 结论 |
| --- | --- |
| 运行环境 | **桌面浏览器即可**（Chrome / Edge 等现代浏览器） |
| 用户 | 自己 / 团队内部使用，非公开发布 |
| 移动端 | **不需要**（触摸手势、屏幕键盘、hover 退化方案全部不进 v1） |
| 交付形态 | 静态站点即可，**不需要后端服务** |

因此本方案的核心取舍是：**首屏加载可以慢一点（1–3 秒可接受），交互只保证桌面键盘 + 鼠标**。这直接决定了 Pyodide 路线优先于 TypeScript 重写路线。

---

## 2. 现状盘点

### 2.1 模块与耦合度

代码总量约 **4,164 行**（不含 README 与复现目录）：

| 模块 | 行数 | 对 Tk 的依赖 | 迁移性质 |
| --- | --- | --- | --- |
| `formula_editor_app/model.py` | 739 | **无**（仅 import `config`） | 原样复用 |
| `formula_editor_app/config.py` | 120 | 无（纯常量） | 原样复用，颜色另导 CSS 变量 |
| `formula_editor_app/layout.py` | 783 | **仅** `tkfont.Font` 的创建与 `measure()/metrics()`；`_paint_layout` 用 `canvas.create_*` | 布局数学保留，测量与绘制抽象化 |
| `formula_editor_app/app.py` | 1262 | 事件对象 `event.x/y/char`、`root.after`、`messagebox`、`focus_set`、`configure(cursor/height)`、剪贴板 | 交互逻辑保留，宿主能力抽象化 |
| `formula_editor_app/ui.py` | 607 | 全部 | 重写（ttk → HTML/CSS） |
| `formula_editor_app/preview.py` | 215 | matplotlib mathtext + PIL + `ImageTk` | 重写为 KaTeX |
| `formula_editor_app/clipboard.py` | 89 | Win32 ctypes | 重写为 `navigator.clipboard` |
| `formula_editor_app/smoke.py` | 294 | 断言直接读 `canvas.find_all()` / `itemcget` | 断言逻辑保留，断言目标改为绘制指令 |
| `formula_editor_app/main.py` | 55 | DPI 感知 + Tk 主循环 | 桌面入口保留，web 另写引导脚本 |

### 2.2 支撑"高可行性"的两个事实

**事实一：布局引擎的输出已经是数据，只有测量和刷屏沾了 Tk。**

`layout.py` 的产出是 `Layout(width, ascent, descent, draws, hits, nodes)`，其中 `draws` 是
`DrawText` / `DrawRect` / `DrawLine` 的列表，`_paint_layout()` 只是把这份数据映射到
`canvas.create_text/create_rectangle/create_line`。换成 Canvas2D 时，这个函数几乎是逐行对应的。

`layout.py` 里唯一的 Tk API 是：

```python
tkfont.Font(family=..., size=..., slant=...)   # _font()
font.measure(text)                              # 文本宽度
font.metrics("ascent") / font.metrics("descent")# 行高
```

**事实二：`app.py` 是一台纯状态机，Tk 调用都是"叶子操作"。**

`event.x` / `event.y` / `event.char` 这三个属性在 Tk 事件对象上存在——只要 web 桥接层传入一个
**具有 `.x` / `.y` / `.char` 属性的对象**，`_on_canvas_click`、`_on_canvas_drag_*`、
`_on_canvas_key`、`_on_backspace` 等处理函数**一行都不用改签名**。
其余 Tk 调用（调度、提示、焦点、光标、剪贴板、画布尺寸）集中在约 20 处，全部可收进宿主接口。

### 2.3 必须搬动的顶部 import（关键约束）

`app.py` 顶部目前有：

```python
from PIL import Image, ImageTk            # 仅用于预览图缓存类型与显示
from .clipboard import copy_text_to_clipboard
from .preview import PreviewMixin          # 拖入 matplotlib
from .smoke import SmokeTestMixin
from .ui import UIBuilderMixin             # 拖入 ttk
```

**Pyodide 里没有 tkinter，也不引入 matplotlib/PIL。** 因此迁移的第一步不是"写网页"，而是把
`core`（model / 布局计算 / 交互控制器）与 `platform`（Tk 外壳 / web 外壳）彻底分开，
让核心包只依赖标准库。

---

## 3. 路线对比与选择

| 路线 | 做法 | 复用度 | 冷启动 | 工作量 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **A. Pyodide** | 核心逻辑留在 Python，浏览器内运行 | 约 2,800 行逻辑可继承 | 6–11MB，1–3 秒 | ~5 人日 | **采用** |
| B. TypeScript 重写 | 算法逐条翻译成 TS | 仅"规格"（README + 冒烟断言） | 秒开 | ~7–8 人日 | 不进 v1 |
| C. Python 后端 + RPC | 模型在服务器，前端发请求 | 逻辑 100% | 每键一次网络往返 | ~3 人日 | 否决 |
| D. 只做只读渲染页 | 贴 LaTeX → KaTeX 渲染 | 0 | 秒开 | ~0.5 人日 | 仅作探针参考 |

否决 C 的理由：编辑器每次按键都要跨网络，延迟和离线都不可接受，且要长期维护服务端。
否决 B（v1 阶段）的理由：本项目大半复杂度在**编辑语义的边角规则**（回格只往左找、空方框不能拖选删除、
方框里已有内容时拒绝插入结构……），`smoke.py` 里近 20 条断言就是在钉这些行为；重写一遍并逐条重新验证，
风险与收益不如直接复用。

> Python 语法层面无阻碍：`dataclasses`、`copy.deepcopy`、`typing`、`Optional`、递归遍历/序列化
> 在 Pyodide 下都正常工作。

---

## 4. 目标架构

### 4.1 目录与分层

```
project/
├── formula_editor.py                 # 桌面入口（不变）
├── formula_editor_app/
│   ├── config.py                     # 常量（不变；颜色额外导出为 CSS 变量）
│   ├── core/                         # ← 只依赖标准库，桌面与网页共用
│   │   ├── model.py                  # 公式树、遍历、编辑语义、LaTeX 序列化（原样搬运）
│   │   ├── layout.py                 # 布局计算（去掉 tkfont，改为注入 Metrics）
│   │   ├── controller.py             # 原 app.py 的交互状态机（改为通过 Host 做事）
│   │   ├── paint.py                  # PaintBackend 协议 + DrawOp 定义
│   │   ├── host.py                   # EditorHost 协议 + FakeHost（测试用）
│   │   └── smoke.py                  # 冒烟断言（改为面向 FakeHost）
│   ├── tk_app/                       # 桌面外壳（保留现有行为）
│   │   ├── host_tk.py                # EditorHost 的 Tk 实现
│   │   ├── paint_tk.py               # PaintBackend 的 Tk 实现
│   │   ├── ui.py                     # 现有 ttk 界面（基本不变）
│   │   ├── preview.py                # 现有 matplotlib 预览（不变）
│   │   ├── clipboard.py              # 现有 Win32 剪贴板（不变）
│   │   └── main.py                   # 现有入口（不变）
│   └── web_app/
│       ├── host_web.py               # EditorHost 的浏览器实现（Pyodide 侧）
│       ├── paint_canvas2d.py         # PaintBackend 的 Canvas2D 实现
│       └── boot.py                   # Pyodide 加载、JS 函数暴露
└── web/                              # 纯静态前端
    ├── index.html
    ├── editor.css                    # 由 config.py 的颜色导出
    ├── bridge.js                     # DOM 事件 → Python 回调；键盘/拖动/粘贴
    ├── canvas.js                     # Canvas2D 画笔（可选，也可全在 Python 侧）
    ├── katex/                        # KaTeX（本地副本）
    └── pyodide/                      # Pyodide 本地副本（内网/离线可用）
```

### 4.2 运行时数据流

```
用户按键 ──> bridge.js ──> py._on_canvas_key(Ev(char))   (Pyodide)
                                  │
                                  ├─ 修改公式树（core/model.py）
                                  ├─ core/layout.py 计算 → DrawOp 列表 + HitArea
                                  └─ paint_canvas2d.py → ctx.* 绘制指令
                                  │
               <── 返回 Markdown / 状态文字 / 未填方框数 ──
                                  │
bridge.js ──> 更新状态栏、Markdown 文本、KaTeX 预览
```

---

## 5. 关键接口（设计草案）

### 5.1 事件对象（最小侵入的关键）

```python
@dataclass
class Ev:
    x: float = 0.0
    y: float = 0.0
    char: str = ""
```

Tk 适配器直接传原生事件（它有 `.x/.y/.char`）；web 桥接构造 `Ev`。
`app.py` 里所有 `def _on_xxx(self, event: tk.Event)` 的函数体**不用改**，只需把类型标注改掉。

### 5.2 EditorHost（宿主能力）

```python
class EditorHost(Protocol):
    def schedule(self, callback, delay_ms: int) -> int: ...   # 替代 root.after
    def cancel(self, handle: int) -> None: ...                # 替代 root.after_cancel
    def set_status(self, text: str, kind: str) -> None: ...   # 替代 _set_status 里的控件写入
    def alert(self, title: str, message: str, kind: str) -> None: ...  # 替代 messagebox
    def focus_canvas(self) -> None: ...                       # 替代 canvas.focus_set
    def set_cursor(self, name: str) -> None: ...              # "arrow" / "text" / "pointer"
    def canvas_size(self) -> tuple[float, float]: ...         # 替代 winfo_width/height
    def window_height(self) -> float: ...                     # 替代 root.winfo_height
    def set_canvas_height(self, height: int) -> None: ...     # 替代 canvas.configure(height=)
    def copy_text(self, text: str) -> None: ...               # 复制 Markdown（异步实现也可）
    def read_clipboard(self, callback) -> None: ...           # 粘贴（web 下由 paste 事件驱动）
    def on_markdown(self, markdown: str, complete: bool) -> None: ...  # 输出区 & 按钮状态
    def on_preview(self, slots: Slot, unfilled: int) -> None: ...      # KaTeX 渲染或提示文字
```

### 5.3 Metrics（文本度量）

```python
class Metrics(Protocol):
    def font(self, size: float, italic: bool, family: str | None) -> object: ...
    def measure(self, font, text: str = "x") -> tuple[float, float, float]: ...
```

- Tk 实现：`tkfont.Font` + `measure()` / `metrics()`（缓存已有，直接搬）。
- Web 实现：把 `(family, px, italic)` 映射成 `ctx.font` 字符串，调用 JS 侧批量测量，
  结果按 `(font_key, text)` 缓存——**这是性能关键点，见 §7.2**。

### 5.4 PaintBackend

```python
class PaintBackend(Protocol):
    def clear(self) -> None: ...
    def rect(self, x1, y1, x2, y2, fill, outline, width, dash) -> None: ...
    def line(self, x1, y1, x2, y2, fill, width) -> None: ...
    def text(self, x, y, text, font, fill, anchor) -> None: ...
```

Tk 实现即现有 `_paint_layout` 的主体；Canvas2D 实现按 `anchor`（`"sw"` → `textBaseline="alphabetic"`，
`"center"` → `"middle"`）与 `dash`（元组 → `setLineDash`）逐项映射。

---

## 6. 逐模块迁移清单

| 现有模块 | 目标位置 | 改动性质 | 备注 |
| --- | --- | --- | --- |
| `model.py` | `core/model.py` | **零改动**（仅 import 路径从 `.config` 变 `.config`） | 公式树、编辑语义、序列化的全部 |
| `config.py` | 原地 | 增加 `to_css_vars()` 导出颜色 | 布局常量（`ITEM_GAP=4`、箱体 26px、1.75×/2.15× 字号）继续留在 Python，保证两版共用 |
| `layout.py` | `core/layout.py` | 去 tkfont：`_font/_measure` → 注入 `Metrics`；`_paint_layout` → `PaintBackend` | 布局数学、`HitArea`、`NodeBox`、`shift_layout` 全部保留 |
| `app.py` | `core/controller.py` | 约 20 处 Tk 调用 → `Host` 方法；签名标注 `tk.Event` → `Ev` | `_on_canvas_*`、删除规则、方向键、撤销/重做、拖选逻辑原样保留 |
| `ui.py` | `tk_app/ui.py` | 原地保留（桌面用） | 另有一份 web 版：`web/index.html` + `editor.css` |
| `preview.py` | `tk_app/preview.py`（桌面）+ KaTeX（web） | 桌面不变；web 用 `katex.render()` | 矩阵自绘回退在 web 版**整体删除** |
| `clipboard.py` | `tk_app/clipboard.py`（桌面）；web 用 `navigator.clipboard` | 原地保留 + 新增 | 见 §7.4 |
| `smoke.py` | `core/smoke.py` | 断言从"读画布对象"改为"读 FakeHost 记录的绘制指令" | 同一套断言在桌面、CI、web 三处运行 |
| `main.py` | `tk_app/main.py` | 原地保留 | web 引导另写 `web_app/boot.py` |

### 6.1 web 页面外壳需要实现的内容

- 工具栏：`∑ 求和`、`∫ 积分`、`d/dx 微分`、`a/b 分式`、`角标`（下拉：上角标（乘方）/ 下角标 / 上下角标）、`√ 开方`（下拉：平方根 / n 次根）、
  `矩阵`（2×2 / 3×3 / 2×3 / 3×2）、`向量`（2×1 / 3×1 / 1×2 / 1×3）、`撤销`、`重做`、`清空`；
- 符号面板：直接按钮 `· × ± ∓ ≤ ≥ ≠ ∞ ∂ ∇` + 「更多符号」分类菜单（`基本运算` / `集合` / `微积分` / `变量` / `标识` / `逻辑与箭头`，数据直接来自 `config.py` 的 `SYMBOL_GROUPS`）；
- 画布区：`<canvas>`，按 `devicePixelRatio` 放大像素、逻辑坐标不变；
- 输出区：Markdown 源码（只读 `<pre>`，随树实时同步）+ KaTeX 预览（`displayMode: true`）；
- 状态栏：沿用 `正在编辑：{role}` / `还有 N 个必填方框待填写` 等文案；
- 「复制 Markdown」按钮：`navigator.clipboard.writeText()`。

---

## 7. 风险登记册与对策

按严重度排序。**§7.1 是唯一可能推翻方案的一条，建议先做探针。**

### 7.1 字体度量不一致（高风险）

现状：画布正文用 Cambria，符号用 Segoe UI Symbol；`∑`/`∫`/`√`/括号都是**按测量宽度手绘**的——
求和符号 1.75× 字号、积分 2.15×、积分上下限 0.62×、根号竖线最小 18px、矩阵括号按 `inner_height/1.55` 撑高。
这些常数是围绕上述字体的字宽标定出来的。

网页上没有这两个字体。对策：

1. 打包开源数学字体（STIX Two Text + STIX Two Math，或 KaTeX 自带字体组，均为 OFL/MIT 许可）；
2. **首帧必须等 `document.fonts.ready`**，否则会按回退字体测量，结构错位；
3. 标定一轮：对比 `∑ ∫ √ ( )` 的 advance width 与 ascent/descent，必要时只调整 `layout.py` 中那组
   比例常数（不改结构）。

**决策门**：若开源字体与 Tk 版的字宽差异超过约 15% 且需要大量改动常数，则重新评估路线 B。

### 7.2 Pyodide 边界开销（中高风险）

`_layout_text` 会对每个字符按前缀测量 `measure(group[:k])` 来算光标位——文本越长，调用次数越接近 O(n²)；
而 `_render_canvas_body` 的自动适配会遍历 `AUTO_FIT_SIZES`（28→12 共 9 档），最坏情况是 9 × 全树的测量量。
在 Tk 里这是本地调用，跨到 JS 每次都有解释器开销，可能在长公式的每次按键出现几十毫秒抖动。

对策：

- 桥接层提供**批量接口**：`measure_runs([(font_key, text), ...]) -> [(w, a, d), ...]`，
  以及 `caret_positions(font_key, text) -> [x0, x1, ..., xn]`（JS 侧一次循环算完前缀宽度）；
- `core/layout.py` 内对 `(font_key, text)` 做字典缓存（长文本的子串会重复出现）；
- 自动适配循环先估宽度、命中后再精排，避免 9 次全量测量。

### 7.3 `measureText` 语义与基线（中风险）

Tk 的 `font.metrics("ascent"/"descent")` 与浏览器 `actualBoundingBoxAscent/Descent` 起点不同，
整体基线可能偏移几像素。对策：把 `baseline_offset` 收敛为一个可标定常量，首帧后按视觉微调。

### 7.4 剪贴板（中风险）

- 复制：`navigator.clipboard.writeText()` 是异步且要求**安全上下文**（HTTPS 或 `localhost`）；
  用 `file://` 直接打开会失败。对策：接口改为"发起 + 回调改状态"，并在失败时给明确提示。
- 粘贴：现有 `_paste_formula` 同步读剪贴板，web 下 `readText()` 需要权限。对策：改由
  canvas 上的 `paste` 事件驱动（`event.clipboardData.getData('text')`），再调用 `_insert_text()`。

### 7.5 首屏体积（中风险，可接受）

Pyodide 运行核约 6–11MB。对策：本地副本（内网可能无法访问 CDN）+ Service Worker 缓存 +
加载期间显示"正在加载编辑器"占位。内部工具场景下 1–3 秒冷启动可接受（已确认）。

### 7.6 中文输入法（中风险）

现有实现靠 `keydown` 的字符事件，中文输入法的合成过程不会逐字触发。对策：监听
`compositionstart` / `compositionend`，在合成结束的瞬间把整段文本交给 `_insert_text()`；
合成期间保持画布焦点不动。

### 7.7 高 DPI（低风险）

`canvas.width = cssWidth * devicePixelRatio`，绘制前 `ctx.scale(dpr, dpr)`；布局仍然全部使用逻辑像素，
`layout.py` 的坐标体系完全不用改。

### 7.8 焦点与键盘（低风险）

Tk 里靠 `canvas.focus_set()` 抢键盘焦点；web 里键盘事件挂在 `window` 上，用一个
`editorFocused` 标志切换，避免在 Markdown 框里打字时抢走按键。方向键/Backspace/Delete 需要
`preventDefault()`，否则会触发页面滚动或浏览器返回。

### 7.9 窗口高度与画布自适应（低风险）

`_canvas_max_height()` 依赖 `winfo_height()`；web 下换成 `window.innerHeight`，语义相同。
移动端不需要考虑。

### 7.10 双外壳维护（低风险）

桌面版和网页版会各有一个外壳。对策：`core/` 只放共用逻辑、`smoke.py` 在两种宿主上跑同一套断言；
外壳本身不含公式语义。

---

## 8. 验收标准（从 `smoke.py` 提炼）

迁移后需逐条通过（用 `FakeHost` 记录绘制指令与状态，替代 `canvas.find_all()` / `itemcget`）：

| # | 断言 |
| --- | --- |
| 1 | 求和公式填充后 LaTeX 精确等于 `\sum_{i=1}^{n} i^2` |
| 2 | Markdown 输出等于 `$$\n…\n$$`，且复制按钮可用 |
| 3 | 未填满时源码为空、按钮禁用、预览显示剩余方框数 |
| 4 | 积分、分式、角标、n 次根 的序列化结果正确 |
| 5 | 矩阵序列化为 `\begin{pmatrix} … \end{pmatrix}` |
| 6 | 单符号 `·` 序列化为 `\cdot` |
| 7 | 方向键可跨方框切换（右进左回） |
| 8 | 点击文本右边缘新增输入位置，随后输入 `+` 得到 `x+` |
| 9 | 四则运算按字符处理：`x+2` 不拆分结构 |
| 10 | 结构左侧空位按回格**不**删除右侧结构 |
| 11 | 结构右侧空位按回格整体删除求和 |
| 12 | 结构左侧空位按 Delete 整体删除积分 |
| 13 | 结构内部（分子）按回格不删除外层结构 |
| 14 | 分母内部按回格不删除右侧字符 |
| 15 | 文本末尾按 Delete 不跨到右侧 |
| 16 | 纯算符文本只删字符本身 |
| 17 | 从文本拖到算符上：结构整体被选中，高亮包围盒与结构包围盒一致 |
| 18 | 删除选中内容后公式为空 |
| 19 | 空方框上拖动不产生选择，回格不删方框 |
| 20 | 结构被选中时内部方框改用选中底色 |

此外新增 web 专属验收：KaTeX 能渲染 `pmatrix`、复制到剪贴板的文本只含 Markdown 源码、
加载失败时给出可读提示。

---

## 9. 阶段计划与工时

| 阶段 | 内容 | 交付物 | 估算 |
| --- | --- | --- | --- |
| 0 | **字体探针**：新建独立 `probe/` 目录，用候选 webfont 画 `∑ ∫ √ ( ) i^2`，与 Tk 版截图对比字宽/基线 | 探针页 + 结论 | 0.5 天 |
| 1 | 抽接口：`core/` 与 `tk_app/` 分离，`Host`/`Metrics`/`PaintBackend`/`FakeHost`；桌面版回归 | 重构后的包，桌面可用 | 1 天 |
| 2 | Canvas2D 画笔 + 字体度量桥 + DPR | 画布在浏览器中正确绘制 | 0.5 天 |
| 3 | web 页面外壳（工具栏/符号面板/输出区/状态栏）+ KaTeX + 剪贴板 | 可编辑的最小页面 | 1 天 |
| 4 | Pyodide 引导、事件桥、IME、防抖、提示 | 端到端可用的网页版 | 1–1.5 天 |
| 5 | 测试迁移（20 条断言）、视觉走查（各结构 × 各字号）、静态部署 | 可交付版本 | 1 天 |
| **合计** | | | **约 5 人日** |

阶段 0 是决策门：探针不过则在阶段 1 之前重新评估路线 B。

---

## 10. 不做什么（明确排除）

- **移动端 / 触摸手势 / 屏幕键盘** —— 已确认不需要；
- **后端服务、账号、云端存储、协作** —— 静态站点足矣，持久化可用 URL hash / localStorage 以后再说；
- **自建 LaTeX 排版引擎** —— 预览交给 KaTeX；
- **重写公式语义** —— `model.py` 一行不改是本次迁移的主要目标；
- **在 web 版保留矩阵自绘预览回退** —— KaTeX 原生支持 `pmatrix`，该分支整体删除；
- **离线桌面安装包** —— 保持现有 `python formula_editor.py` 入口即可。

---

## 11. 待定问题

1. 探针字体选型：STIX Two（衬线感更接近 Cambria）还是 KaTeX 字体组（体积更小）？
2. 网页版是否需要"打开即带一个示例公式"（默认填好求和示例）？
3. 是否需要在网页版保留"矩阵自绘预览"作为 KaTeX 失败时的兜底（会增加少量代码）？
4. 部署位置：GitHub Pages / 内网静态服务器 / 本机双击打开（后者受剪贴板安全上下文限制）。
