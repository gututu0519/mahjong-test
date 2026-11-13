import ts from 'typescript';
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, lstatSync, realpathSync, symlinkSync, copyFileSync, rmSync, renameSync, openSync, closeSync } from 'node:fs';
import { resolve, dirname, relative, posix, basename } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

export const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const runtime = resolve(repo, 'other/runtime/server');
const view = dirname(runtime);
const unix = p => p.replaceAll('\\', '/');
const key = p => process.platform === 'win32' ? unix(p).toLowerCase() : unix(p);
function write(path, value) {
  mkdirSync(dirname(path), {recursive:true});
  writeFileSync(path, value);
}
// Directory links only: resources and databases retain one physical owner.
function link(path, target) {
  mkdirSync(dirname(path), {recursive:true});
  if (existsSync(path)) {
    if (!lstatSync(path).isSymbolicLink() || key(realpathSync(path)) !== key(realpathSync(target)))
      throw Error(`Refusing to replace an unexpected resource path: ${path}`);
    return;
  }
  symlinkSync(process.platform === 'win32' ? target : relative(dirname(path),target), path, process.platform === 'win32' ? 'junction' : 'dir');
}
function copy(from, to) { mkdirSync(dirname(to),{recursive:true}); copyFileSync(from,to); }
function prepare(layout) {
  mkdirSync(runtime,{recursive:true});
  mkdirSync(resolve(repo,'other/diagnostics'),{recursive:true});
  for (const game of layout.games) {
    link(resolve(view,'clients',game),resolve(repo,'games',game,'frontend'));
    link(resolve(view,'services',game),resolve(repo,'games',game,'instance'));
  }
  for (const [name,target] of Object.entries({
    'services/gtt-gateway':'gateway/instance','services/gtt-admin':'admin/instance',
    'services/gtt-mock-platform':'other/mock-platform/instance','services/game-api':'other/game-api',
    py:'other/legacy/py',demo:'other/demo',diagnostics:'other/diagnostics',
    deploy:'other/deploy/legacy',tools:'other/capture/tools','response-capture':'other/capture/response-capture',
  })) link(resolve(view,name),resolve(repo,target));
  for(const name of ['clients','services','py','demo','diagnostics','tools'])
    link(resolve(runtime,'resources',name),resolve(view,name));
  link(resolve(runtime,'frontend/admin'),resolve(repo,'admin/frontend'));
  link(resolve(runtime,'frontend/platform'),resolve(repo,'other/mock-platform/frontend'));
  link(resolve(runtime,'fixtures'),resolve(repo,'other/tests/fixtures'));
  link(resolve(runtime,'tests'),resolve(repo,'other/tests'));
  link(resolve(runtime,'node_modules'),resolve(repo,'other/tooling/node_modules'));
  for (const [old,source] of Object.entries(layout.files)) {
    if (old.endsWith('.ts') || ['package.json','package-lock.json','tsconfig.json','.gitignore'].includes(old)) continue;
    copy(resolve(repo,source),resolve(runtime,old));
  }
  for(const name of readdirSync(resolve(repo,'other/docs/project'))) {
    const path=resolve(repo,'other/docs/project',name);
    if(lstatSync(path).isFile()) copy(path,resolve(view,'docs',name));
  }
  for(const [name,source] of Object.entries(layout.documents)) {
    const target=resolve(repo,source), destination=resolve(view,'docs',name);
    if(lstatSync(target).isDirectory()) link(destination,target);
    else copy(target,destination);
  }
  copy(resolve(repo,'README.md'),resolve(view,'README.md'));
  write(resolve(runtime,'package.json'),JSON.stringify({name:'gtt-runtime',version:'0.1.0',private:true,type:'module',engines:{node:'>=24.17.0'}},null,2));
}
export async function build() {
  const lock=resolve(repo,'other/tooling/.build-lock');
  let fd;
  for(let n=0;n<240;n++) {
    try { fd=openSync(lock,'wx'); break; }
    catch(e) { if(e.code!=='EEXIST') throw e; await new Promise(r=>setTimeout(r,500)); }
  }
  if(fd===undefined) throw Error('Another build holds other/tooling/.build-lock; wait for it to finish.');
  try {
    const layout=JSON.parse(readFileSync(resolve(repo,'other/tooling/layout.json'),'utf8'));
    prepare(layout);
    const bySource=new Map(Object.entries(layout.modules).map(([old,source])=>[key(resolve(repo,source)),old]));
    const options={target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.NodeNext,moduleResolution:ts.ModuleResolutionKind.NodeNext,
      rootDir:repo,outDir:resolve(runtime,'dist'),strict:true,noImplicitAny:false,skipLibCheck:true,noEmitOnError:true,sourceMap:true,
      types:['node'],typeRoots:[resolve(repo,'other/tooling/node_modules/@types')]};
    const program=ts.createProgram(Object.values(layout.modules).map(p=>resolve(repo,p)),options);
    const diagnostics=ts.getPreEmitDiagnostics(program);
    if(diagnostics.length) {
      console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics,{getCanonicalFileName:p=>p,getCurrentDirectory:()=>repo,getNewLine:()=> '\n'}));
      throw Error('TypeScript validation failed');
    }
    const staging=resolve(runtime,'dist-next');
    rmSync(staging,{recursive:true,force:true});
    // Source modules have ordinary relative imports in the four-domain tree.
    // Emit to the stable release layout so workers and existing release contracts
    // keep their import.meta.url paths; never expose this layout as source code.
    const transformer=context=>source=>{
      const old=bySource.get(key(source.fileName));
      const visitor=node=>{
        if(ts.isStringLiteral(node) && node.text.startsWith('.') &&
          ((ts.isImportDeclaration(node.parent)||ts.isExportDeclaration(node.parent)) && node.parent.moduleSpecifier===node ||
           ts.isCallExpression(node.parent)&&node.parent.expression.kind===ts.SyntaxKind.ImportKeyword)) {
          const target=bySource.get(key(resolve(dirname(source.fileName),node.text.replace(/\.js$/,'.ts'))));
          if(target) {
            let spec=posix.relative(posix.dirname(old),target).replace(/\.ts$/,'.js');
            if(!spec.startsWith('.')) spec='./'+spec;
            return context.factory.createStringLiteral(spec);
          }
        }
        return ts.visitEachChild(node,visitor,context);
      };
      return ts.visitNode(source,visitor);
    };
    const result=program.emit(undefined,(_path,data,_bom,_error,sources)=>{
      const old=sources?.length===1?bySource.get(key(sources[0].fileName)):undefined;
      if(!old) throw Error(`Unmapped compiler output: ${_path}`);
      const output=old.replace(/\.ts$/,'.js');
      if(_path.endsWith('.map')) {
        const map=JSON.parse(data);
        map.file=basename(output);
        map.sources=[unix(relative(dirname(resolve(runtime,'dist',output)),sources[0].fileName))];
        write(resolve(staging,output+'.map'),JSON.stringify(map));
      } else write(resolve(staging,output),data);
    },undefined,false,{before:[transformer]});
    if(result.emitSkipped) throw Error('Compiler skipped emission');
    rmSync(resolve(runtime,'dist'),{recursive:true,force:true});
    renameSync(staging,resolve(runtime,'dist'));
    execFileSync(process.execPath,[resolve(runtime,'tools/build-descriptors.mjs')],{cwd:runtime,stdio:'inherit'});
    copy(resolve(runtime,'config/game-descriptors.json'),resolve(repo,'gateway/config/game-descriptors.json'));
    write(resolve(runtime,'dist/.built'),String(Date.now()));
    console.log(`Built ${bySource.size} modules from games/, gateway/, admin/, other/.`);
  } finally { closeSync(fd); rmSync(lock); }
}
if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) await build();
