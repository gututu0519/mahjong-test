// Migrated from py/services/buffalo_preview.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "../transport/http.js";
const __file__=__rt.sourcePath("py/services/buffalo_preview.py");
export let BytesIO:any,CLIENT:any,Handler:any,Path:any,PlatformRoutes:any,ROOT:any,ServiceError:any,SimpleHTTPRequestHandler:any,ThreadingHTTPServer:any,argparse:any,build_server:any,copy:any,json:any,logging:any,main:any,parse_qs:any,partial:any,prepare_module:any,secrets:any,time:any,urlencode:any,urlsplit:any;

argparse=__rt.modules["argparse"];
copy=__rt.modules["copy"];
json=__rt.modules["json"];
logging=__rt.modules["logging"];
secrets=__rt.modules["secrets"];
time=__rt.modules["time"];
partial=__rt.attr(__rt.modules["functools"],"partial");
SimpleHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"SimpleHTTPRequestHandler");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
BytesIO=__rt.attr(__rt.modules["io"],"BytesIO");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
ROOT=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),2);
CLIENT=__rt.bin("Div",ROOT,"clients/buffalo-win");
prepare_module=__rt.attr(__rt.modules["py.adapters.pg.client_modules"],"prepare_module");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
PlatformRoutes=__rt.attr(__m0,"PlatformRoutes");
Handler=__rt.cls("Handler",[PlatformRoutes,SimpleHTTPRequestHandler],{"bootstrap_script":"local-preview.js","_get":__rt.fn("_get",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let path;path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/health"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["status","ok"],["service_id","buffalo-win-preview"],["mode","frontend-preview"]])],__rt.kw([]));}
__rt.call(__rt.attr(SimpleHTTPRequestHandler,"do_GET"),[self],__rt.kw([]));return null;}),"_post":__rt.fn("_post",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let body,data,expiry,form,language,length,name,now,path,payload,query,token;__rt.call(__rt.attr(self,"_guard_origin"),[],__rt.kw([]));
length=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Content-Length","0"],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>length,()=>16384])))){throw __rt.call(ServiceError,["BODY_TOO_LARGE","Request body exceeds 16 KiB.",413],__rt.kw([]));}
body=__rt.call(__rt.attr(__rt.attr(self,"rfile"),"read"),[length],__rt.kw([]));
path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/api/v1/games/buffalo-win/launch"]))){if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(__rt.attr(self,"headers"),"get_content_type"),[],__rt.kw([])),()=>"application/json"]))){throw __rt.call(ServiceError,["CONTENT_TYPE","Use application/json.",415],__rt.kw([]));}
payload=__rt.call(__rt.attr(json,"loads"),[__rt.or_(()=>body,()=>Buffer.from([123, 125]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(ServiceError,["BAD_REQUEST","Expected an object."],__rt.kw([]));}
language=__rt.call(__rt.attr(payload,"get"),["language","zh"],__rt.kw([]));
if(__rt.truth(__rt.compare(["NotEq"],[()=>language,()=>"zh"]))){throw __rt.call(ServiceError,["LANGUAGE_UNAVAILABLE","English assets are not captured yet. Chinese preview is available."],__rt.kw([]));}
now=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))],__rt.kw([]));
for(const __t1 of __rt.iter(__rt.call(__rt.b["list"],[__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"sessions"),"items"),[],__rt.kw([]))],__rt.kw([])))){{const __t2=Array.from(__rt.iter(__t1));token=__t2[0];expiry=__t2[1];}if(__rt.truth(__rt.compare(["LtE"],[()=>expiry,()=>now]))){__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"sessions"),"pop"),[token,null],__rt.kw([]));}}
if(__rt.truth(__rt.compare(["GtE"],[()=>__rt.call(__rt.b["len"],[__rt.attr(__rt.attr(self,"server"),"sessions")],__rt.kw([])),()=>1000]))){throw __rt.call(ServiceError,["SESSION_LIMIT","Restart the local preview to clear sessions.",429],__rt.kw([]));}
token=__rt.call(__rt.attr(secrets,"token_urlsafe"),[32],__rt.kw([]));
__rt.setitem(__rt.attr(__rt.attr(self,"server"),"sessions"),token,__rt.bin("Add",now,86400));
query=__rt.call(urlencode,[__rt.dict([["mock",1],["l",language],["ops",token],["btt",2]])],__rt.kw([]));
return __rt.call(__rt.attr(self,"_json"),[201,__rt.dict([["game_id","buffalo-win"],["language",language],["launch_url",__rt.bin("Add","/?",query)],["mode","frontend-preview"],["expires_at",__rt.bin("Add",now,86400)]])],__rt.kw([]));}
form=__rt.call(parse_qs,[__rt.call(__rt.attr(body,"decode"),["utf-8"],__rt.kw([]))],__rt.kw([["keep_blank_values",true]]));
token=__rt.or_(()=>__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["X-Local-Preview-Session"],__rt.kw([])),()=>__rt.item(__rt.call(__rt.attr(form,"get"),["atk",[""]],__rt.kw([])),0));
if(__rt.truth(__rt.compare(["LtE"],[()=>__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"sessions"),"get"),[token,0],__rt.kw([])),()=>__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))]))){throw __rt.call(ServiceError,["SESSION_INVALID","Invalid preview session.",401],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/web-api/auth/session/v2/verifySession","/web-api/auth/session/v2/verifyOperatorPlayerSession"])]))){data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(__rt.attr(self,"server"),"auth")],__rt.kw([]));
__rt.call(__rt.attr(data,"update"),[],__rt.kw([["tk",token],["pid","local-preview"],["pcd","local-preview"],["nkn","Preview"],["ioph","local-preview"],["oj",__rt.dict([["jid",1]])],["bl",2000]]));
return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",data],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/game-api/buffalo-win/v2/GameInfo/Get"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.attr(__rt.attr(self,"server"),"info")],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameName/Get"]))){name=(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(__rt.call(__rt.attr(form,"get"),["lang",["zh"]],__rt.kw([])),0),()=>"en"]))?"Buffalo Win":"\u7f8e\u6d32\u91ce\u725b");
return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",__rt.dict([["108",name]])],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",[]],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/ServerManager/RefreshWallet"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",null],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameWallet/Get"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",__rt.dict([["cc","PGC"],["tb",2000],["pb",0],["cb",2000],["tbb",0],["tfgb",0],["rfgc",0],["inbe",false],["infge",false],["iebe",false],["iefge",false],["ch",__rt.dict([["k","0_C"],["cid",0],["cb",2000]])],["p",null],["ocr",null],["bwc",0],["fgwc",0]])],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.call(__rt.attr(path,"endswith"),["/Spin"],__rt.kw([])))){throw __rt.call(ServiceError,["PREVIEW_ONLY","Frontend preview only. The spin engine is not connected.",501],__rt.kw([]));}
throw __rt.call(ServiceError,["NOT_IMPLEMENTED","This endpoint is not available in the frontend preview.",501],__rt.kw([]));return null;}),"list_directory":__rt.fn("list_directory",{names:["self", "path"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;return null;}),"send_head":__rt.fn("send_head",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let _,bootstrap,content,original,path,relative;path=__rt.call(__rt.attr(__rt.call(Path,[__rt.call(__rt.attr(self,"translate_path"),[__rt.attr(self,"path")],__rt.kw([]))],__rt.kw([])),"resolve"),[],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.attr(path,"is_relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([]))))){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;}
relative=__rt.call(__rt.attr(path,"relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.compare(["In"],[()=>"fixtures",()=>__rt.attr(relative,"parts")]),()=>__rt.compare(["In"],[()=>__rt.call(__rt.attr(__rt.attr(path,"suffix"),"lower"),[],__rt.kw([])),()=>__rt.tuple([".py",".pyc",".bat",".md",".har",".txt"])])))){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;}
if(__rt.truth(__rt.compare(["In"],[()=>__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path"),()=>__rt.tuple(["/","/index.html"])]))){content=__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"index.html"),"read_bytes"),[],__rt.kw([]));
original=Buffer.from([120, 116, 61, 105, 44, 107, 116, 61, 39, 39]);
if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(content,"count"),[original],__rt.kw([])),()=>1]))){throw __rt.call(__rt.b["ValueError"],["Entry base configuration changed"],__rt.kw([]));}
content=__rt.call(__rt.attr(content,"replace"),[original,Buffer.from([120, 116, 61, 110, 101, 119, 32, 85, 82, 76, 40, 105, 44, 108, 111, 99, 97, 116, 105, 111, 110, 46, 104, 114, 101, 102, 41, 46, 104, 114, 101, 102, 44, 107, 116, 61, 110, 101, 119, 32, 85, 82, 76, 40, 39, 46, 39, 44, 108, 111, 99, 97, 116, 105, 111, 110, 46, 104, 114, 101, 102, 41, 46, 104, 114, 101, 102]),1],__rt.kw([]));
bootstrap=__rt.call(__rt.attr(("<script src=\"/"+__rt.format(__rt.attr(self,"bootstrap_script"),"",-1)+"\"></script><script src=\"/local-frame-clock.js\"></script>"),"encode"),[],__rt.kw([]));
content=__rt.call(__rt.attr(content,"replace"),[Buffer.from([60, 115, 99, 114, 105, 112, 116, 32, 105, 100, 61, 34, 109, 97, 105, 110, 45, 115, 99, 114, 105, 112, 116, 34]),__rt.bin("Add",bootstrap,Buffer.from([60, 115, 99, 114, 105, 112, 116, 32, 105, 100, 61, 34, 109, 97, 105, 110, 45, 115, 99, 114, 105, 112, 116, 34])),1],__rt.kw([]));
return __rt.call(__rt.attr(self,"_asset"),[content,"text/html; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.attr(path,"name"),()=>"index.js"]),()=>__rt.compare(["In"],[()=>"shared",()=>__rt.attr(relative,"parts")]),()=>__rt.call(__rt.attr(path,"is_file"),[],__rt.kw([]))))){{const __t3=Array.from(__rt.iter(__rt.call(prepare_module,[__rt.call(__rt.attr(path,"read_bytes"),[],__rt.kw([]))],__rt.kw([]))));content=__t3[0];_=__t3[1];}
return __rt.call(__rt.attr(self,"_asset"),[content,"application/javascript; charset=utf-8"],__rt.kw([]));}
return __rt.call(__rt.attr(__rt.super_(Handler,self),"send_head"),[],__rt.kw([]));return null;}),"_asset":__rt.fn("_asset",{names:["self", "content", "mime"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,content,mime){__rt.call(__rt.attr(self,"send_response"),[200],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type",mime],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[content],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
return __rt.call(BytesIO,[content],__rt.kw([]));return null;})});
build_server=__rt.fn("build_server",{names:["port"],kwonly:[],defaults:{"port":8083},vararg:null,kwarg:null},function(port){let http;http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),__rt.call(partial,[Handler],__rt.kw([["directory",__rt.call(__rt.b["str"],[CLIENT],__rt.kw([]))]]))],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
__rt.setattr(http,"engine_mode","frontend-preview");
__rt.setattr(http,"sessions",__rt.dict([["local-preview-session",253402300799]]));
__rt.setattr(http,"auth",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/auth-metadata.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(http,"info",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/game-info.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
return http;return null;});
main=__rt.fn("main",{names:[],kwonly:[],defaults:{},vararg:null,kwarg:null},function(){let args,http,logs,parser;parser=__rt.call(__rt.attr(argparse,"ArgumentParser"),[],__rt.kw([["description","Isolated Buffalo Win frontend preview. No spin engine or settlement is provided."]]));
__rt.call(__rt.attr(parser,"add_argument"),["--port"],__rt.kw([["type",__rt.b["int"]],["default",8083]]));
args=__rt.call(__rt.attr(parser,"parse_args"),[],__rt.kw([]));
logs=__rt.bin("Div",ROOT,"services/buffalo-win/logs");
__rt.call(__rt.attr(logs,"mkdir"),[],__rt.kw([["parents",true],["exist_ok",true]]));
__rt.call(__rt.attr(logging,"basicConfig"),[],__rt.kw([["level",__rt.attr(logging,"INFO")],["handlers",[__rt.call(__rt.attr(logging,"FileHandler"),[__rt.bin("Div",logs,"service.log")],__rt.kw([["encoding","utf-8"]]))]]]));
{const __t4=__rt.context(__rt.call(build_server,[__rt.attr(args,"port")],__rt.kw([])));let __t6=false;http=__t4.value;try{__rt.call(__rt.b["print"],[("Buffalo Win frontend preview: http://127.0.0.1:"+__rt.format(__rt.attr(http,"server_port"),"",-1)+"/?mock=1&l=zh")],__rt.kw([["flush",true]]));
try{__rt.call(__rt.attr(http,"serve_forever"),[],__rt.kw([]));}catch(__t7){if(__rt.matches(__t7,__rt.b["KeyboardInterrupt"])){}else{throw __t7;}}}catch(__t5){__t6=true;if(!__t4.exit(__t5))throw __t5;}finally{if(!__t6)__t4.exit(null);}}return null;});
