import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
import {resolve,dirname,relative,sep} from 'node:path';
import ts from 'typescript';

// Follow emitted JS dependencies, rather than copying every game and service.
export function packageAdmin(root,destination) {
  const dist=resolve(root,'dist'),seen=new Set();
  function visit(path) {
    if(seen.has(path))return;
    const rel=relative(dist,path);
    if(rel.startsWith('..')||rel.startsWith(sep))throw Error('Admin dependency escaped dist: '+path);
    seen.add(path);
    const text=readFileSync(path,'utf8');
    const file=ts.createSourceFile(path,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
    function scan(node) {
      let spec;
      if((ts.isImportDeclaration(node)||ts.isExportDeclaration(node))&&node.moduleSpecifier&&ts.isStringLiteral(node.moduleSpecifier))spec=node.moduleSpecifier.text;
      else if(ts.isCallExpression(node)&&node.expression.kind===ts.SyntaxKind.ImportKeyword&&node.arguments.length===1&&ts.isStringLiteral(node.arguments[0]))spec=node.arguments[0].text;
      if(spec?.startsWith('.'))visit(resolve(dirname(path),spec));
      ts.forEachChild(node,scan);
    }
    scan(file);
    const target=resolve(destination,'dist',rel);mkdirSync(dirname(target),{recursive:true});writeFileSync(target,text);
  }
  for(const entry of ['admin-cli.js','shared/database/worker.js','shared/database/runner.js'])visit(resolve(dist,entry));
  const data=resolve(destination,'dist/data');mkdirSync(data,{recursive:true});
  for(const file of ['control.sql','game.sql','buffalo-win.json','rtp-models.json','game-descriptors.json','game-readiness.json','guide.html','guide.md','integration.json','openapi.json'])copyFileSync(resolve(root,'config',file),resolve(data,file));
  writeFileSync(resolve(destination,'dist/cli.js'),`import {resolve} from 'node:path';\nimport {fileURLToPath} from 'node:url';\nimport {main} from './admin-cli.js';\nexport {main};\nif(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(error=>{console.error(error.code??error.name,error.message);process.exitCode=1;});\n`);
  return {modules:seen.size,data_directory:'dist/data'};
}
