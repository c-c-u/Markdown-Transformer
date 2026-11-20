/* 构建脚本：把 web/src/*.js 内联进 index.template.html，生成可双击打开的单文件网页版。
 * 用法：node web/build.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.join(here, 'src');
const order = ['config.js', 'model.js', 'layout.js', 'controller.js', 'ui.js'];

const parts = order.map((name) => {
  const file = path.join(srcDir, name);
  return '// ===== ' + name + ' =====\n' + fs.readFileSync(file, 'utf8');
});
const script = parts.join('\n\n');

const template = fs.readFileSync(path.join(here, 'index.template.html'), 'utf8');
const marker = '/*__APP_JS__*/';
if (!template.includes(marker)) {
  console.error('模板里找不到 ' + marker);
  process.exit(1);
}

const html = template.replace(marker, () => script);
const output = path.join(here, 'formula_editor.html');
fs.writeFileSync(output, html, 'utf8');
console.log('已生成 ' + output + '（' + html.length + ' 字符）');
