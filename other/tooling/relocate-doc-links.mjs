// One-time link migration; uses the physical move journal rather than guesses.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, dirname, posix } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const moves=JSON.parse(readFileSync(resolve(root,'other/diagnostics/layout/moves.json'),'utf8'));
const relocated=old=>{for(const {from,to} of moves) if(old===from||old.startsWith(from+'/')) old=to+old.slice(from.length);return old;};
const tracked=execFileSync('git',['ls-files','-z'],{cwd:root,encoding:'utf8'}).split('\0').filter(p=>p.endsWith('.md')&&p!=='AGENTS.md'&&p!=='server/config/guide.md');
let count=0;
for(const old of tracked) {
  const current=old==='README.md'?'other/docs/README-before-layout.md':relocated(old);
  if(!existsSync(resolve(root,current))) continue;
  const original=readFileSync(resolve(root,current),'utf8');
  let text=original.replace(/(\]\()([^\s)]+)(\))/g,(all,start,url,end)=>{
    if(/^(?:[a-z]+:|#|\/)/i.test(url)) return all;
    const [path,fragment]=url.split('#');
    const target=relocated(posix.normalize(posix.join(posix.dirname(old),path)));
    return start+(posix.relative(posix.dirname(current),target)||'.')+(fragment?'#'+fragment:'')+end;
  });
  if(current!==old) {
    const guide=posix.relative(posix.dirname(current),'other/docs/project-layout.md');
    text=text.replace(/^(# [^\n]+\n)/,`$1\n> 目录已重组。当前启动命令与路径见[四目录说明](${guide})；本文中的旧命令保留为历史记录。\n`);
  }
  if(text!==original) {writeFileSync(resolve(root,current),text);count++;}
}
console.log(`Updated Markdown links in ${count} relocated documents.`);
