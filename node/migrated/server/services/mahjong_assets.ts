// Migrated from server/services/mahjong_assets.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
const __file__=__rt.sourcePath("server/services/mahjong_assets.py");
export let BytesIO:any,MahjongAssetHandler:any,Path:any,SimpleHTTPRequestHandler:any,hashlib:any,parse_qs:any,prepare_module:any,urlsplit:any;

hashlib=__rt.modules["hashlib"];
SimpleHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"SimpleHTTPRequestHandler");
BytesIO=__rt.attr(__rt.modules["io"],"BytesIO");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
prepare_module=__rt.attr(__rt.modules["server.adapters.pg.client_modules"],"prepare_module");
MahjongAssetHandler=__rt.cls("MahjongAssetHandler",[SimpleHTTPRequestHandler],{"send_head":__rt.fn("send_head",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let content,entry,local_script,mock_script,original,replacement,requested,revision,shared;
requested=__rt.call(Path,[__rt.call(__rt.attr(self,"translate_path"),[__rt.attr(self,"path")],__rt.kw([]))],__rt.kw([]));
shared=__rt.call(__rt.attr(__rt.bin("Div",__rt.call(Path,[__rt.attr(self,"directory")],__rt.kw([])),"shared"),"resolve"),[],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.attr(requested,"name"),()=>"index.js"]),()=>__rt.compare(["In"],[()=>shared,()=>__rt.attr(__rt.call(__rt.attr(requested,"resolve"),[],__rt.kw([])),"parents")])))){try{{const __t2=Array.from(__rt.iter(__rt.call(prepare_module,[__rt.call(__rt.attr(requested,"read_bytes"),[],__rt.kw([]))],__rt.kw([]))));content=__t2[0];revision=__t2[1];}}catch(__t1){if(__rt.matches(__t1,__rt.b["OSError"])){__rt.call(__rt.attr(self,"send_error"),[404,"Module file not found"],__rt.kw([]));
return null;}else if(__rt.matches(__t1,__rt.b["ValueError"])){let error=__t1;__rt.call(__rt.attr(self,"log_error"),["%s: %s",requested,error],__rt.kw([]));
__rt.call(__rt.attr(self,"send_error"),[422,"Module initialization failed; see server log"],__rt.kw([]));
return null;}else{throw __t1;}}
__rt.call(__rt.attr(self,"send_response"),[200],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type","application/javascript; charset=utf-8"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[content],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["X-Local-Module-Fix","auto-1"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["X-Local-Module-Revision",revision],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
return __rt.call(BytesIO,[content],__rt.kw([]));}
if(__rt.truth(__rt.compare(["NotIn"],[()=>__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path"),()=>__rt.tuple(["/","/index.html"])]))){return __rt.call(__rt.attr(__rt.super_(MahjongAssetHandler,self),"send_head"),[],__rt.kw([]));}
entry=__rt.bin("Div",__rt.call(Path,[__rt.attr(self,"directory")],__rt.kw([])),"index.html");
try{content=__rt.call(__rt.attr(entry,"read_bytes"),[],__rt.kw([]));}catch(__t3){if(__rt.matches(__t3,__rt.b["OSError"])){__rt.call(__rt.attr(self,"send_error"),[404,"Entry file not found"],__rt.kw([]));
return null;}else{throw __t3;}}
original=Buffer.from([120, 116, 61, 105, 44, 107, 116, 61, 39, 39]);
replacement=Buffer.from([120, 116, 61, 110, 101, 119, 32, 85, 82, 76, 40, 105, 44, 108, 111, 99, 97, 116, 105, 111, 110, 46, 104, 114, 101, 102, 41, 46, 104, 114, 101, 102, 44, 107, 116, 61, 110, 101, 119, 32, 85, 82, 76, 40, 39, 46, 39, 44, 108, 111, 99, 97, 116, 105, 111, 110, 46, 104, 114, 101, 102, 41, 46, 104, 114, 101, 102]);
if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(content,"count"),[original],__rt.kw([])),()=>1]))){__rt.call(__rt.attr(self,"send_error"),[500,"Entry path configuration changed; review local path fix"],__rt.kw([]));
return null;}
content=__rt.call(__rt.attr(content,"replace"),[original,replacement,1],__rt.kw([]));
local_script=__rt.fn("local_script",{names:["name"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(name){let revision;revision=__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.bin("Div",__rt.call(Path,[__rt.attr(self,"directory")],__rt.kw([])),name),"read_bytes"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,12,null));
return __rt.call(__rt.attr(("<script src=\"/"+__rt.format(name,"",-1)+"?v="+__rt.format(revision,"",-1)+"\"></script>"),"encode"),["ascii"],__rt.kw([]));return null;});
mock_script=(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(__rt.call(parse_qs,[__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"query")],__rt.kw([])),"get"),["mock"],__rt.kw([])),()=>["1"]]))?__rt.bin("Add",__rt.call(local_script,["local-frame-clock.js"],__rt.kw([])),__rt.call(local_script,["local-auth-bootstrap.js"],__rt.kw([]))):Buffer.from([]));
content=__rt.call(__rt.attr(__rt.call(__rt.attr(content,"replace"),[Buffer.from([60, 115, 99, 114, 105, 112, 116, 32, 105, 100, 61, 34, 109, 97, 105, 110, 45, 115, 99, 114, 105, 112, 116, 34]),Buffer.from([60, 115, 99, 114, 105, 112, 116, 32, 116, 121, 112, 101, 61, 34, 97, 112, 112, 108, 105, 99, 97, 116, 105, 111, 110, 47, 120, 45, 108, 111, 99, 97, 108, 45, 103, 97, 109, 101, 34, 32, 105, 100, 61, 34, 109, 97, 105, 110, 45, 115, 99, 114, 105, 112, 116, 34]),1],__rt.kw([])),"replace"),[Buffer.from([60, 47, 98, 111, 100, 121, 62]),__rt.bin("Add",__rt.bin("Add",mock_script,__rt.call(local_script,["local-cache-bootstrap.js"],__rt.kw([]))),Buffer.from([60, 47, 98, 111, 100, 121, 62])),1],__rt.kw([]));
__rt.call(__rt.attr(self,"send_response"),[200],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type","text/html; charset=utf-8"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[content],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
return __rt.call(BytesIO,[content],__rt.kw([]));return null;}),"end_headers":__rt.fn("end_headers",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path"),()=>"/shared/service-worker/sw.js"]))){__rt.call(__rt.attr(self,"send_header"),["Service-Worker-Allowed","/"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-cache"],__rt.kw([]));}
__rt.call(__rt.attr(__rt.super_(MahjongAssetHandler,self),"end_headers"),[],__rt.kw([]));return null;})});
