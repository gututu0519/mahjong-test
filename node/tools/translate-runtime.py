"""One-time, explicit Python AST -> checked-in TypeScript migration.

Never invoked by npm build/test or a running service. Unsupported syntax fails
closed. Outputs ordinary JavaScript functions, not an AST interpreter or a
Python subprocess. Reference exports test the resulting Node implementation.
"""
import ast
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'node/migrated'
BUILTINS = set('abs all any bool bytearray bytes chr dict enumerate float getattr hasattr int isinstance iter len list map max min next ord print range reversed round set sorted str sum tuple type zip super ValueError TypeError KeyError IndexError RuntimeError OverflowError UnicodeError UnicodeDecodeError OSError EOFError BaseException Exception BrokenPipeError ConnectionResetError KeyboardInterrupt staticmethod classmethod'.split())
def ident(x): return '__py_' + x if x in {'new','default','delete','class','function','var','let','const','switch','case','package','yield','await','arguments'} else x
def js(x): return json.dumps(x, ensure_ascii=True)

class Compiler:
    def __init__(self, path):
        self.path = path
        self.module = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
        self.tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        if self.module=='server.merchant.prebet':
            self.tree.body=[n for n in self.tree.body if isinstance(n,ast.FunctionDef) and n.name in ('external_username','multiplier_range') or isinstance(n,ast.ImportFrom) and n.module in ('decimal','server.core.contracts')]
        self.imports = {}
        self.serial = 0
        self.class_name = None
        self.exception = None
        self.breakflags = []
    def temp(self):
        self.serial += 1
        return '__t' + str(self.serial)
    def locals(self, body, params=()):
        result, external = set(), set(params)
        def visit(n):
            if isinstance(n, (ast.Nonlocal, ast.Global)): external.update(n.names)
            elif isinstance(n, (ast.FunctionDef, ast.ClassDef)): result.add(n.name)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store): result.add(n.id)
            elif isinstance(n, ast.Import): result.update(a.asname or a.name.split('.')[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom): result.update(a.asname or a.name for a in n.names)
            elif not isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Lambda)):
                for child in ast.iter_child_nodes(n): visit(child)
        for n in body: visit(n)
        return sorted(result - external)
    def source_import(self, name):
        if name not in self.imports: self.imports[name] = '__m' + str(len(self.imports))
        return self.imports[name]
    def exp(self, n):
        if n is None: return 'null'
        e = self.exp
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bytes): return 'Buffer.from(' + js(list(n.value)) + ')'
            if isinstance(n.value, float): return '__rt.float(' + repr(n.value) + ')'
            return js(n.value)
        if isinstance(n, ast.Name):
            if n.id == '__doc__': return js(ast.get_docstring(self.tree))
            if n.id == '__name__': return js(self.module)
            return '__rt.b[' + js(n.id) + ']' if n.id in BUILTINS else ident(n.id)
        if isinstance(n, (ast.List, ast.Tuple, ast.Set)):
            arr = '[' + ','.join('...__rt.iter('+e(x.value)+')' if isinstance(x, ast.Starred) else e(x) for x in n.elts) + ']'
            return ('__rt.set('+arr+')') if isinstance(n, ast.Set) else ('__rt.tuple('+arr+')') if isinstance(n, ast.Tuple) else arr
        if isinstance(n, ast.Dict):
            return '__rt.dict([' + ','.join('[null,'+e(v)+']' if k is None else '['+e(k)+','+e(v)+']' for k,v in zip(n.keys,n.values)) + '])'
        if isinstance(n, ast.Attribute): return '__rt.attr('+e(n.value)+','+js(n.attr)+')'
        if isinstance(n, ast.Subscript): return '__rt.item('+e(n.value)+','+e(n.slice)+')'
        if isinstance(n, ast.Slice): return '__rt.slice('+','.join(e(x) for x in [n.lower,n.upper,n.step])+')'
        if isinstance(n, ast.BinOp): return '__rt.bin('+js(type(n.op).__name__)+','+e(n.left)+','+e(n.right)+')'
        if isinstance(n, ast.UnaryOp): return '__rt.unary('+js(type(n.op).__name__)+','+e(n.operand)+')'
        if isinstance(n, ast.BoolOp): return '__rt.'+('and' if isinstance(n.op,ast.And) else 'or')+'_('+','.join('()=>'+e(x) for x in n.values)+')'
        if isinstance(n, ast.Compare): return '__rt.compare('+js([type(x).__name__ for x in n.ops])+',['+','.join('()=>'+e(x) for x in [n.left]+n.comparators)+'])'
        if isinstance(n, ast.IfExp): return '(__rt.truth('+e(n.test)+')?'+e(n.body)+':'+e(n.orelse)+')'
        if isinstance(n, ast.Call):
            if isinstance(n.func,ast.Name) and n.func.id == 'super' and not n.args:
                return '__rt.super_('+self.class_name+',self)'
            return '__rt.call('+e(n.func)+',['+','.join('...__rt.iter('+e(x.value)+')' if isinstance(x,ast.Starred) else e(x) for x in n.args)+'],__rt.kw(['+','.join('[null,'+e(k.value)+']' if k.arg is None else '['+js(k.arg)+','+e(k.value)+']' for k in n.keywords)+']))'
        if isinstance(n, ast.Lambda): return self.function(n.args, [ast.Return(n.body)], '<lambda>')
        if isinstance(n, (ast.ListComp, ast.GeneratorExp, ast.DictComp, ast.SetComp)):
            names = sorted({x.id for g in n.generators for x in ast.walk(g.target) if isinstance(x, ast.Name)})
            decl = 'let '+','.join(map(ident,names))+';' if names else ''
            gen = isinstance(n,ast.GeneratorExp)
            head = '(function*(){' if gen else '(()=>{'
            code = head+decl+('' if gen else 'const __out:any[]=[];')
            for g in n.generators:
                v=self.temp(); code += 'for(const '+v+' of __rt.iter('+e(g.iter)+')){'+self.assign(g.target,v)
                for cond in g.ifs: code+='if(__rt.truth('+e(cond)+')){'
            val='['+e(n.key)+','+e(n.value)+']' if isinstance(n,ast.DictComp) else e(n.elt)
            code += ('yield '+val+';' if gen else '__out.push('+val+');')
            code += '}'*sum(1+len(g.ifs) for g in n.generators)
            if not gen: code+='return '+('__rt.dict(__out)' if isinstance(n,ast.DictComp) else '__rt.set(__out)' if isinstance(n,ast.SetComp) else '__out')+';'
            return code+'})()'
        if isinstance(n, ast.JoinedStr): return '('+'+'.join('__rt.format('+e(x.value)+','+(e(x.format_spec) if x.format_spec else '""')+','+str(x.conversion)+')' if isinstance(x,ast.FormattedValue) else e(x) for x in n.values)+')'
        if isinstance(n, ast.NamedExpr): return '('+self.assign(n.target,e(n.value)).rstrip(';')+')'
        if isinstance(n,ast.Yield): return '(yield '+e(n.value)+')'
        raise NotImplementedError((self.path,n.lineno,ast.dump(n)))
    def assign(self, target, value):
        e=self.exp
        if isinstance(target,ast.Name): return ident(target.id)+'='+value+';'
        if isinstance(target,ast.Attribute): return '__rt.setattr('+e(target.value)+','+js(target.attr)+','+value+');'
        if isinstance(target,ast.Subscript): return '__rt.setitem('+e(target.value)+','+e(target.slice)+','+value+');'
        if isinstance(target,(ast.Tuple,ast.List)):
            t=self.temp(); code='const '+t+'=Array.from(__rt.iter('+value+'));'
            for i,x in enumerate(target.elts): code+=self.assign(x,t+'['+str(i)+']')
            return '{'+code+'}'
        raise NotImplementedError(ast.dump(target))
    def function(self, args, body, name):
        names = [x.arg for x in args.posonlyargs+args.args]
        kwonly=[x.arg for x in args.kwonlyargs]
        params=names+kwonly+([args.vararg.arg] if args.vararg else [])+([args.kwarg.arg] if args.kwarg else [])
        defaults={name:self.exp(v) for name,v in zip(names[len(names)-len(args.defaults):],args.defaults)}
        defaults.update({name:self.exp(v) for name,v in zip(kwonly,args.kw_defaults) if v is not None})
        spec='{names:'+js(names)+',kwonly:'+js(kwonly)+',defaults:{'+','.join(js(k)+':'+v for k,v in defaults.items())+'},vararg:'+js(args.vararg.arg if args.vararg else None)+',kwarg:'+js(args.kwarg.arg if args.kwarg else None)+'}'
        locals_=self.locals(body,params)
        generator=any(isinstance(n,(ast.Yield,ast.YieldFrom)) for stmt in body for n in ast.walk(stmt))
        return '__rt.fn('+js(name)+','+spec+',function'+('*' if generator else '')+'('+','.join(map(ident,params))+'){'+('let '+','.join(map(ident,locals_))+';' if locals_ else '')+self.block(body)+'return null;})'
    def block(self, body): return '\n'.join(self.stmt(n) for n in body)
    def stmt(self,n):
        e=self.exp
        if isinstance(n,ast.Expr): return '' if isinstance(n.value,ast.Constant) and isinstance(n.value.value,str) else e(n.value)+';'
        if isinstance(n,ast.Assign):
            if len(n.targets)==1:return self.assign(n.targets[0],e(n.value))
            t=self.temp();return '{const '+t+'='+e(n.value)+';'+''.join(self.assign(x,t) for x in n.targets)+'}'
        if isinstance(n,ast.AnnAssign): return self.assign(n.target,e(n.value)) if n.value else ''
        if isinstance(n,ast.AugAssign): return self.assign(n.target,'__rt.bin('+js(type(n.op).__name__)+','+e(n.target)+','+e(n.value)+')')
        if isinstance(n,ast.If):
            if isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__':return ''
            return 'if(__rt.truth('+e(n.test)+')){'+self.block(n.body)+'}'+('else{'+self.block(n.orelse)+'}' if n.orelse else '')
        if isinstance(n,ast.For):
            flag=self.temp() if n.orelse else None
            self.breakflags.append(flag)
            t=self.temp();code=('let '+flag+'=true;' if flag else '')+'for(const '+t+' of __rt.iter('+e(n.iter)+')){'+self.assign(n.target,t)+self.block(n.body)+'}'
            self.breakflags.pop()
            return code+('if('+flag+'){'+self.block(n.orelse)+'}' if flag else '')
        if isinstance(n,ast.While):
            self.breakflags.append(None)
            code='while(__rt.truth('+e(n.test)+')){'+self.block(n.body)+'}'
            self.breakflags.pop()
            return code
        if isinstance(n,ast.Return):return 'return '+e(n.value)+';'
        if isinstance(n,ast.Break):return (self.breakflags[-1]+'=false;' if self.breakflags and self.breakflags[-1] else '')+'break;'
        if isinstance(n,ast.Continue):return 'continue;'
        if isinstance(n,(ast.Pass,ast.Nonlocal,ast.Global)):return ''
        if isinstance(n,ast.Raise):return 'throw '+(e(n.exc) if n.exc else self.exception or 'new Error("No active exception")')+';'
        if isinstance(n,ast.Assert):return '__rt.assert('+e(n.test)+','+e(n.msg)+');'
        if isinstance(n,ast.Delete):return ''.join('__rt.delitem('+e(x.value)+','+e(x.slice)+');' for x in n.targets)
        if isinstance(n,ast.FunctionDef):
            result=self.function(n.args,n.body,n.name)
            for d in reversed(n.decorator_list):result='__rt.call('+e(d)+',['+result+'])'
            return n.name+'='+result+';'
        if isinstance(n,ast.ClassDef):
            old=self.class_name;self.class_name=n.name
            fields=[];methods=[]
            for s in n.body:
                if isinstance(s,ast.FunctionDef):
                    func=self.function(s.args,s.body,s.name)
                    for d in reversed(s.decorator_list):func='__rt.call('+e(d)+',['+func+'])'
                    methods.append(js(s.name)+':'+func)
                elif isinstance(s,ast.Assign):
                    if len(s.targets)!=1:raise NotImplementedError('class assign')
                    target=s.targets[0]
                    if isinstance(target,ast.Name):fields.append(js(target.id)+':'+e(s.value))
                    elif isinstance(target,ast.Tuple):
                        for i,x in enumerate(target.elts):fields.append(js(x.id)+':__rt.item('+e(s.value)+','+str(i)+')')
                elif not isinstance(s,(ast.Expr,ast.Pass)):raise NotImplementedError(ast.dump(s))
            self.class_name=old
            return n.name+'=__rt.cls('+js(n.name)+',['+','.join(e(x) for x in n.bases)+'],{'+','.join(fields+methods)+'});'
        if isinstance(n,ast.Try):
            err=self.temp();old=self.exception;self.exception=err
            result='try{'+self.block(n.body)+'}'
            if n.handlers:
                result+='catch('+err+'){'
                for i,h in enumerate(n.handlers):
                    result+=('else ' if i else '')+'if('+(('__rt.matches('+err+','+e(h.type)+')') if h.type else 'true')+'){'+('let '+h.name+'='+err+';' if h.name else '')+self.block(h.body)+'}'
                result+='else{throw '+err+';}}'
            if n.finalbody:result+='finally{'+self.block(n.finalbody)+'}'
            self.exception=old
            if n.orelse:raise NotImplementedError('try else')
            return result
        if isinstance(n,ast.With):
            def nest(i):
                if i==len(n.items):return self.block(n.body)
                w=n.items[i];t=self.temp();err=self.temp();done=self.temp()
                return '{const '+t+'=__rt.context('+e(w.context_expr)+');let '+done+'=false;'+(self.assign(w.optional_vars,t+'.value') if w.optional_vars else '')+'try{'+nest(i+1)+'}catch('+err+'){'+done+'=true;if(!'+t+'.exit('+err+'))throw '+err+';}finally{if(!'+done+')'+t+'.exit(null);}}'
            return nest(0)
        if isinstance(n,ast.Import):return '\n'.join((a.asname or a.name.split('.')[0])+'='+self.module_ref(a.name)+';' for a in n.names)
        if isinstance(n,ast.ImportFrom):
            name=n.module or ''
            if n.level:
                base=self.module.split('.')[:-n.level]
                name='.'.join(base+([name] if name else []))
            ref=self.module_ref(name)
            return '\n'.join((a.asname or a.name)+'=__rt.attr('+ref+','+js(a.name)+');' for a in n.names)
        raise NotImplementedError((self.path,getattr(n,'lineno',0),ast.dump(n)))
    def module_ref(self,name):
        if name.startswith('server.') and name not in ('server.core.contracts','server.run','server.adapters.pg.client_modules','server.adapters.tada.life_service','server.adapters.playngo.player_events'):return self.source_import(name)
        return '__rt.modules['+js(name)+']'
    def emit(self):
        declarations=self.locals(self.tree.body)
        code=self.block(self.tree.body)
        target=OUT/Path(*self.module.split('.')).with_suffix('.ts')
        import os
        def rel(path):
            value=Path(os.path.relpath(path,target.parent)).as_posix()
            return value if value.startswith('.') else './'+value
        header='// Migrated from '+self.path.relative_to(ROOT).as_posix()+'. Runtime is Node.js only.\n'
        header+='import * as __rt from '+js(rel(ROOT/'node/compat/runtime.js'))+';\n'
        for name,alias in self.imports.items():header+='import * as '+alias+' from '+js(rel(OUT/Path(*name.split('.')).with_suffix('.js')))+';\n'
        header+='const __file__=__rt.sourcePath('+js(self.path.relative_to(ROOT).as_posix())+');\n'
        header+='export let '+','.join(ident(x)+':any' for x in declarations)+';\n'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(header+code+'\n',encoding='utf-8')
        return target

def main():
    paths=list((ROOT/'server/games').glob('*/engine.py'))
    paths += [p for p in (ROOT/'server/core').glob('*.py') if p.name not in ('contracts.py','__init__.py')]
    paths += [p for p in (ROOT/'server/adapters').rglob('*.py') if p.name not in ('client_modules.py','life_service.py','player_events.py','__init__.py')]
    paths += [p for p in (ROOT/'server/services').glob('*.py') if p.name!='__init__.py']
    paths += [ROOT/'server/paths.py',ROOT/'server/transport/http.py']
    paths += [ROOT/'server/merchant/common.py',ROOT/'server/merchant/mock_wallet.py',ROOT/'server/merchant/prebet.py']
    for path in paths:Compiler(path).emit()
    manifest={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (OUT/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    from server.games.catalog import GAMES
    imports=[];entries=[]
    for i,(gid,spec) in enumerate(GAMES.items()):
        module,name=spec['factory'].split(':')
        imports.append(f'import {{ {name} as G{i} }} from "./{module.split(".")[-1]}/engine.js";')
        entries.append(js(gid)+':{factory:G'+str(i)+',metadata:'+json.dumps({k:v for k,v in spec.items() if k!='factory'})+'}')
    catalog='\n'.join(imports)+'\nimport * as p from "../../../compat/runtime.js";\nexport const definitions:any={'+','.join(entries)+'};\n'
    catalog+='export const create_registry=p.native(([ids=null,configs=null],kwargs)=>{configs=kwargs.configs??configs;const selected=ids??Object.keys(definitions);if(!selected.length||new Set(selected).size!==selected.length)throw new p.ValueError("Explicit unique game selection required");if(configs)for(const id of p.iter(configs))if(!selected.includes(id))throw new p.ValueError("Configuration for unselected game "+id);const games=new Map();for(const id of selected){if(!definitions[id])throw new p.ValueError("Unknown game "+id);const path=configs?p.call(p.attr(configs,"get"),[id]):null;games.set(id,p.call(definitions[id].factory,[path]));}return {games:()=>[...games.values()],get:(id)=>{if(!games.has(id))throw p.call(p.modules["server.core.contracts"].ServiceError,["GAME_NOT_FOUND","Unknown game",404]);return games.get(id);},catalog:()=>[...games].map(([id,g])=>p.from({...definitions[id].metadata,id,title:p.attr(g,"title"),engine_version:p.attr(g,"version"),ruleset_id:p.attr(g,"ruleset_id")}))};});\n'
    (OUT/'server/games/catalog.ts').write_text(catalog)
    print('Emitted',len(paths),'Node modules')
if __name__=='__main__':main()
