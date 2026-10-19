// Offline inspection only. Original client files are never rewritten.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'clients/fortune-rabbit/1543462/assets/main/index.533e0.js'), 'utf8');
const context = {};
vm.runInNewContext(source.slice(0, source.indexOf('window[')) + 'globalThis.decodeString=Y;})()', context, {timeout: 3000});
const aliases = new Set(['Y']);
let changed = true;
while (changed) {
  changed = false;
  for (const m of source.matchAll(/\b([A-Za-z_$][\w$]*)=([A-Za-z_$][\w$]*)[;,]/g)) {
    if (aliases.has(m[2]) && !aliases.has(m[1])) { aliases.add(m[1]); changed = true; }
  }
}
let result = source.replace(/\b([A-Za-z_$][\w$]*)\((0x[0-9a-f]+)\)/g,
  (full, name, value) => aliases.has(name) ? JSON.stringify(context.decodeString(Number(value))) : full);
const literals = /(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')(?:\+(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'))+/g;
result = result.replace(literals, text => JSON.stringify(vm.runInNewContext(text, {}, {timeout:100})));
fs.mkdirSync(path.join(root, 'diagnostics'), {recursive: true});
fs.writeFileSync(path.join(root, 'diagnostics/fortune-rabbit-client.js'), result);
console.log('Saved offline client inspection, aliases:', aliases.size);
