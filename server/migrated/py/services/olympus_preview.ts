// Migrated from py/services/olympus_preview.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
const __file__=__rt.sourcePath("py/services/olympus_preview.py");
export let BASE:any,CLIENT:any,Handler:any,Path:any,ROOT:any,SimpleHTTPRequestHandler:any,ThreadingHTTPServer:any,argparse:any,build_server:any,json:any,logging:any,main:any,parse_qs:any,partial:any,secrets:any,time:any,urlencode:any,urlsplit:any;

argparse=__rt.modules["argparse"];
json=__rt.modules["json"];
logging=__rt.modules["logging"];
secrets=__rt.modules["secrets"];
time=__rt.modules["time"];
partial=__rt.attr(__rt.modules["functools"],"partial");
SimpleHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"SimpleHTTPRequestHandler");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
ROOT=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),2);
CLIENT=__rt.bin("Div",ROOT,"clients/gates-of-olympus");
BASE="/hub-demo/common/v3/games-html5/games/vs/vs20olympgate/";
Handler=__rt.cls("Handler",[SimpleHTTPRequestHandler],{"client_root":CLIENT,"asset_base":BASE,"default_language":"zh","end_headers":__rt.fn("end_headers",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["X-Content-Type-Options","nosniff"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["X-Game-Engine",(__rt.truth(__rt.call(__rt.b["getattr"],[__rt.attr(self,"server"),"generated",false],__rt.kw([])))?"generated":"frontend-preview")],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Security-Policy","default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' data: blob:; frame-ancestors http://127.0.0.1:8080 http://localhost:8080 http://127.0.0.1:8081 http://localhost:8081 'self'"],__rt.kw([]));
__rt.call(__rt.attr(__rt.super_(Handler,self),"end_headers"),[],__rt.kw([]));return null;}),"respond":__rt.fn("respond",{names:["self", "status", "body", "mime"],kwonly:[],defaults:{"mime":"application/json; charset=utf-8"},vararg:null,kwarg:null},function(self,status,body,mime){if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[body,__rt.b["bytes"]],__rt.kw([]))))){body=__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[body],__rt.kw([])),"encode"),[],__rt.kw([]));}
__rt.call(__rt.attr(self,"send_response"),[status],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type",mime],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[body],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
__rt.call(__rt.attr(__rt.attr(self,"wfile"),"write"),[body],__rt.kw([]));return null;}),"list_directory":__rt.fn("list_directory",{names:["self", "path"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;return null;}),"do_GET":__rt.fn("do_GET",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let BASE,CLIENT,config,data,html,language,origin,path,query,relative,target,token;{const __t1=Array.from(__rt.iter(__rt.tuple([__rt.attr(self,"client_root"),__rt.attr(self,"asset_base")])));CLIENT=__t1[0];BASE=__t1[1];}
path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/health"]))){return __rt.call(__rt.attr(self,"respond"),[200,__rt.dict([["status","ok"],["service_id","gates-of-olympus-preview"],["mode","frontend-preview"]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/","/index.html"])]))){query=__rt.call(parse_qs,[__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"query")],__rt.kw([]));
language=__rt.item(__rt.call(__rt.attr(query,"get"),["lang",[__rt.attr(self,"default_language")]],__rt.kw([])),0);
if(__rt.truth(__rt.compare(["NotIn"],[()=>language,()=>__rt.tuple(["zh","en"])]))){return __rt.call(__rt.attr(self,"respond"),[400,__rt.dict([["error","Invalid language"]])],__rt.kw([]));}
token=__rt.item(__rt.call(__rt.attr(query,"get"),["ops",[""]],__rt.kw([])),0);
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.attr(self,"valid_session"),[token],__rt.kw([]))))){token=__rt.call(__rt.attr(self,"new_session"),[],__rt.kw([]));}
origin=("http://127.0.0.1:"+__rt.format(__rt.attr(__rt.attr(self,"server"),"server_port"),"",-1));
config=__rt.dict([["accountType","R"],["currency","USD"],["currencyOriginal","USD"],["datapath",__rt.bin("Add",origin,BASE)],["gameService",__rt.bin("Add",origin,"/hub-demo/ge/v3/gameService")],["lang",language],["vendor","T"],["showRealCash","1"],["clock","0"],["mgckey",token],["styleName","generic"],["extend_events","1"],["jurisdiction","99"],["langSelectorEnabled","0"],["demoMode","0"],["umpcEnabled",false],["lcEnabled",false],["SETTINGS","/hub-demo/saveSettings.do"],["announcementsUpdateSeconds",0],["announcementsUpdateSecondsDefault",0],["localGenerated",__rt.call(__rt.b["getattr"],[__rt.attr(self,"server"),"generated",false],__rt.kw([]))]]);
html=__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"index.html"),"read_text"),[],__rt.kw([["encoding","utf-8"]])),"replace"),["__LOCAL_CONFIG__",__rt.call(__rt.attr(json,"dumps"),[config],__rt.kw([]))],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(html,"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.call(__rt.attr(path,"startswith"),["/gs2c/announcements/"],__rt.kw([])))){return __rt.call(__rt.attr(self,"respond"),[200,Buffer.from([60, 63, 120, 109, 108, 32, 118, 101, 114, 115, 105, 111, 110, 61, 34, 49, 46, 48, 34, 63, 62, 60, 97, 110, 110, 111, 117, 110, 99, 101, 109, 101, 110, 116, 115, 62, 60, 47, 97, 110, 110, 111, 117, 110, 99, 101, 109, 101, 110, 116, 115, 62]),"application/xml"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/hub-demo/common/v3/games-html5/operator_logos/logo_info.js"]))){return __rt.call(__rt.attr(self,"respond"),[200,Buffer.from([119, 105, 110, 100, 111, 119, 46, 85, 72, 84, 76, 111, 103, 111, 116, 121, 112, 101, 73, 110, 102, 111, 32, 61, 32, 123, 125, 59]),"application/javascript"],__rt.kw([]));}
target=__rt.call(__rt.attr(__rt.call(Path,[__rt.call(__rt.attr(self,"translate_path"),[__rt.attr(self,"path")],__rt.kw([]))],__rt.kw([])),"resolve"),[],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.attr(target,"is_relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([]))))){return __rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));}
relative=__rt.call(__rt.attr(__rt.call(__rt.attr(target,"relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([])),"as_posix"),[],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.compare(["NotEq"],[()=>relative,()=>"local-preview.js"]),()=>__rt.unary("Not",__rt.call(__rt.attr(relative,"startswith"),["hub-demo/common/"],__rt.kw([])))))){return __rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple([__rt.bin("Add",BASE,"desktop/build.js"),__rt.bin("Add",BASE,"mobile/build.js")])]))){data=__rt.call(__rt.attr(__rt.call(__rt.attr(target,"read_bytes"),[],__rt.kw([])),"replace"),[Buffer.from([99, 97, 112, 97, 98, 105, 108, 105, 116, 105, 101, 115, 91, 34, 111, 103, 103, 34, 93, 63, 83, 111, 117, 110, 100, 72, 101, 108, 112, 101, 114, 46, 65, 117, 100, 105, 111, 70, 111, 114, 109, 97, 116, 46, 111, 103, 103, 58, 83, 111, 117, 110, 100, 72, 101, 108, 112, 101, 114, 46, 65, 117, 100, 105, 111, 70, 111, 114, 109, 97, 116, 46, 109, 112, 51]),Buffer.from([83, 111, 117, 110, 100, 72, 101, 108, 112, 101, 114, 46, 65, 117, 100, 105, 111, 70, 111, 114, 109, 97, 116, 46, 109, 112, 51])],__rt.kw([]));
data=__rt.bin("Add",data,__rt.bin("Add",Buffer.from([10]),__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"local-deserializer.js"),"read_bytes"),[],__rt.kw([]))));
return __rt.call(__rt.attr(self,"respond"),[200,data,"application/javascript; charset=utf-8"],__rt.kw([]));}
return __rt.call(__rt.attr(__rt.super_(Handler,self),"do_GET"),[],__rt.kw([]));return null;}),"do_HEAD":__rt.fn("do_HEAD",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){return __rt.call(__rt.attr(self,"send_error"),[405],__rt.kw([]));return null;}),"new_session":__rt.fn("new_session",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let now,token;now=__rt.call(__rt.attr(time,"time"),[],__rt.kw([]));
__rt.setattr(__rt.attr(self,"server"),"sessions",(()=>{let k,v;const __out:any[]=[];for(const __t2 of __rt.iter(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"sessions"),"items"),[],__rt.kw([])))){{const __t3=Array.from(__rt.iter(__t2));k=__t3[0];v=__t3[1];}if(__rt.truth(__rt.compare(["Gt"],[()=>__rt.item(v,"expires"),()=>now]))){__out.push([k,v]);}}return __rt.dict(__out);})());
token=__rt.call(__rt.attr(secrets,"token_urlsafe"),[32],__rt.kw([]));
__rt.setitem(__rt.attr(__rt.attr(self,"server"),"sessions"),token,__rt.dict([["expires",__rt.bin("Add",now,86400)],["settings",""]]));
return token;return null;}),"valid_session":__rt.fn("valid_session",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){return __rt.compare(["Gt"],[()=>__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"sessions"),"get"),[token,__rt.dict([])],__rt.kw([])),"get"),["expires",0],__rt.kw([])),()=>__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))]);return null;}),"do_POST":__rt.fn("do_POST",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let body,form,key,length,origin,path,payload,settings,token,values;origin=__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Origin"],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>origin,()=>__rt.compare(["NotIn"],[()=>origin,()=>__rt.tuple([("http://127.0.0.1:"+__rt.format(__rt.attr(__rt.attr(self,"server"),"server_port"),"",-1)),("http://localhost:"+__rt.format(__rt.attr(__rt.attr(self,"server"),"server_port"),"",-1))])])))){return __rt.call(__rt.attr(self,"respond"),[403,__rt.dict([["error","Invalid origin"]])],__rt.kw([]));}
try{length=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Content-Length","0"],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>length,()=>16384])))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
body=__rt.call(__rt.attr(__rt.attr(self,"rfile"),"read"),[length],__rt.kw([]));
path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/api/v1/games/gates-of-olympus/launch"]))){payload=__rt.call(__rt.attr(json,"loads"),[__rt.or_(()=>body,()=>Buffer.from([123, 125]))],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([]))),()=>__rt.compare(["NotIn"],[()=>__rt.call(__rt.attr(payload,"get"),["language","en"],__rt.kw([])),()=>__rt.tuple(["zh","en"])])))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
token=__rt.call(__rt.attr(self,"new_session"),[],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[201,__rt.dict([["game_id","gates-of-olympus"],["language",__rt.call(__rt.attr(payload,"get"),["language","zh"],__rt.kw([]))],["mode","frontend-preview"],["launch_url",__rt.bin("Add","/?",__rt.call(urlencode,[__rt.dict([["mock",1],["ops",token],["lang",__rt.call(__rt.attr(payload,"get"),["language","zh"],__rt.kw([]))],["symbol","vs20olympgate"]])],__rt.kw([])))],["expires_at",__rt.call(__rt.b["int"],[__rt.item(__rt.item(__rt.attr(__rt.attr(self,"server"),"sessions"),token),"expires")],__rt.kw([]))]])],__rt.kw([]));}
form=__rt.call(parse_qs,[__rt.call(__rt.attr(body,"decode"),["utf-8"],__rt.kw([]))],__rt.kw([["keep_blank_values",true]]));
token=__rt.item(__rt.call(__rt.attr(form,"get"),["mgckey",[""]],__rt.kw([])),0);
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.attr(self,"valid_session"),[token],__rt.kw([]))))){return __rt.call(__rt.attr(self,"respond"),[401,__rt.dict([["error","Invalid preview session"]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/hub-demo/ge/v3/gameService"]))){if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["symbol"],__rt.kw([])),()=>["vs20olympgate"]]))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["action"],__rt.kw([])),()=>["doInit"]]))){return __rt.call(__rt.attr(self,"respond"),[501,__rt.dict([["error","PREVIEW_ONLY"],["message","Spins are not connected."]])],__rt.kw([]));}
values=__rt.call(__rt.b["dict"],[__rt.attr(__rt.attr(self,"server"),"initial")],__rt.kw([]));
__rt.call(__rt.attr(values,"update"),[],__rt.kw([["balance","2,000.00"],["balance_cash","2,000.00"],["balance_bonus","0.00"],["index",__rt.item(__rt.call(__rt.attr(form,"get"),["index",["1"]],__rt.kw([])),0)],["counter",__rt.item(__rt.call(__rt.attr(form,"get"),["counter",["1"]],__rt.kw([])),0)],["stime",__rt.call(__rt.b["str"],[__rt.call(__rt.b["int"],[__rt.bin("Mult",__rt.call(__rt.attr(time,"time"),[],__rt.kw([])),1000)],__rt.kw([]))],__rt.kw([]))]]));
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.call(__rt.attr("&","join"),[(function*(){let k,v;for(const __t5 of __rt.iter(__rt.call(__rt.attr(values,"items"),[],__rt.kw([])))){{const __t6=Array.from(__rt.iter(__t5));k=__t6[0];v=__t6[1];}yield __rt.bin("Add",__rt.bin("Add",k,"="),v);}})()],__rt.kw([])),"encode"),[],__rt.kw([])),"text/plain; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/hub-demo/saveSettings.do","/hub-demo/ge/v3/saveSettings.do"])]))){settings=__rt.item(__rt.attr(__rt.attr(self,"server"),"sessions"),token);
key=__rt.item(__rt.call(__rt.attr(form,"get"),["id",["game"]],__rt.kw([])),0);
if(__rt.truth(__rt.compare(["In"],[()=>"settings",()=>form]))){__rt.setitem(__rt.call(__rt.attr(settings,"setdefault"),["values",__rt.dict([])],__rt.kw([])),key,__rt.item(__rt.item(form,"settings"),0));}
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.call(__rt.attr(settings,"get"),["values",__rt.dict([])],__rt.kw([])),"get"),[key,""],__rt.kw([])),"encode"),[],__rt.kw([])),"text/plain; charset=utf-8"],__rt.kw([]));}
return __rt.call(__rt.attr(self,"respond"),[404,__rt.dict([["error","Unknown endpoint"]])],__rt.kw([]));}catch(__t4){if(__rt.matches(__t4,__rt.tuple([__rt.b["ValueError"],__rt.b["UnicodeError"]]))){return __rt.call(__rt.attr(self,"respond"),[400,__rt.dict([["error","Invalid request"]])],__rt.kw([]));}else{throw __t4;}}return null;})});
build_server=__rt.fn("build_server",{names:["port"],kwonly:[],defaults:{"port":8085},vararg:null,kwarg:null},function(port){let PreviewServer,http,initial;initial=__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/init.txt"),"read_text"),[],__rt.kw([["encoding","utf-8"]]));
PreviewServer=__rt.cls("PreviewServer",[ThreadingHTTPServer],{"allow_reuse_address":false});
http=__rt.call(PreviewServer,[__rt.tuple(["127.0.0.1",port]),__rt.call(partial,[Handler],__rt.kw([["directory",__rt.call(__rt.b["str"],[CLIENT],__rt.kw([]))]]))],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
__rt.setattr(http,"sessions",__rt.dict([]));
__rt.setattr(http,"initial",__rt.call(__rt.b["dict"],[(function*(){let part;for(const __t7 of __rt.iter(__rt.call(__rt.attr(initial,"split"),["&"],__rt.kw([])))){part=__t7;if(__rt.truth(__rt.compare(["In"],[()=>"=",()=>part]))){yield __rt.call(__rt.attr(part,"split"),["=",1],__rt.kw([]));}}})()],__rt.kw([])));
return http;return null;});
main=__rt.fn("main",{names:[],kwonly:[],defaults:{},vararg:null,kwarg:null},function(){let args,http,parser;parser=__rt.call(__rt.attr(argparse,"ArgumentParser"),[],__rt.kw([["description","Local captured PP frontend. Initialization only; no spins or wallet settlement."]]));
__rt.call(__rt.attr(parser,"add_argument"),["--port"],__rt.kw([["type",__rt.b["int"]],["default",8085]]));
args=__rt.call(__rt.attr(parser,"parse_args"),[],__rt.kw([]));
{const __t8=__rt.context(__rt.call(build_server,[__rt.attr(args,"port")],__rt.kw([])));let __t10=false;http=__t8.value;try{__rt.call(__rt.attr(logging,"warning"),["Olympus frontend preview: http://127.0.0.1:%s/",__rt.attr(http,"server_port")],__rt.kw([]));
try{__rt.call(__rt.attr(http,"serve_forever"),[],__rt.kw([]));}catch(__t11){if(__rt.matches(__t11,__rt.b["KeyboardInterrupt"])){}else{throw __t11;}}}catch(__t9){__t10=true;if(!__t8.exit(__t9))throw __t9;}finally{if(!__t10)__t8.exit(null);}}return null;});
