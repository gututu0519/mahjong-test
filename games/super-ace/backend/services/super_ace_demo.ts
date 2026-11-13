// Migrated from py/services/super_ace_demo.py. Runtime is Node.js only.
import * as __rt from "../../../../other/shared/compat/runtime.js";
import * as __m0 from "../adapters/jili/super_ace.js";
import * as __m1 from "../../../../other/shared/migrated/py/core/service.js";
import * as __m2 from "../../../../other/shared/migrated/py/games/catalog.js";
import * as __m3 from "../../../../other/shared/migrated/py/transport/http.js";
const __file__=__rt.sourcePath("py/services/super_ace_demo.py");
export let Adapter:any,CLIENT:any,GameService:any,Handler:any,PAGE_BACK:any,Path:any,PlatformRoutes:any,ROOT:any,ServiceError:any,SimpleHTTPRequestHandler:any,ThreadingHTTPServer:any,build_server:any,create_registry:any,html:any,json:any,logging:any,mimetypes:any,parse_qs:any,partial:any,urlencode:any,urlsplit:any;

html=__rt.modules["html"];
json=__rt.modules["json"];
logging=__rt.modules["logging"];
mimetypes=__rt.modules["mimetypes"];
partial=__rt.attr(__rt.modules["functools"],"partial");
SimpleHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"SimpleHTTPRequestHandler");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
Adapter=__rt.attr(__m0,"Adapter");
CLIENT=__rt.attr(__m0,"CLIENT");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
GameService=__rt.attr(__m1,"GameService");
create_registry=__rt.attr(__m2,"create_registry");
PlatformRoutes=__rt.attr(__m3,"PlatformRoutes");
ROOT=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),2);
PAGE_BACK="<button type=\"button\" aria-label=\"Back to game\" style=\"position:fixed;right:12px;top:12px;z-index:10;padding:8px 14px;border:1px solid #c79b45;border-radius:6px;background:#24180d;color:#f9dfaa;cursor:pointer\" onclick=\"parent.postMessage('CloseWebView',location.origin)\">Back to game</button>";
Handler=__rt.cls("Handler",[SimpleHTTPRequestHandler],{"_json":__rt.attr(PlatformRoutes,"_json"),"_response":__rt.attr(PlatformRoutes,"_response"),"_token":__rt.attr(PlatformRoutes,"_token"),"log_message":__rt.fn("log_message",{names:["self", "format"],kwonly:[],defaults:{},vararg:"args",kwarg:null},function(self,format,args){let re;re=__rt.modules["re"];
__rt.call(__rt.attr(logging,"info"),["%s %s",__rt.call(__rt.attr(self,"address_string"),[],__rt.kw([])),__rt.call(__rt.attr(re,"sub"),["\\?[^ ]*","",__rt.bin("Mod",format,args)],__rt.kw([]))],__rt.kw([]));return null;}),"respond":__rt.fn("respond",{names:["self", "status", "data", "mime"],kwonly:[],defaults:{"mime":"application/json; charset=utf-8"},vararg:null,kwarg:null},function(self,status,data,mime){if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[data,__rt.b["bytes"]],__rt.kw([]))))){data=__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[data],__rt.kw([["ensure_ascii",false]])),"encode"),["utf-8"],__rt.kw([]));}
__rt.call(__rt.attr(self,"send_response"),[status],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type",mime],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[data],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["X-Content-Type-Options","nosniff"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Referrer-Policy","no-referrer"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Security-Policy","connect-src 'self' blob: data:; frame-src 'self'; img-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; worker-src 'self' blob:"],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
__rt.call(__rt.attr(__rt.attr(self,"wfile"),"write"),[data],__rt.kw([]));return null;}),"guard":__rt.fn("guard",{names:["self", "action"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,action){try{__rt.call(action,[],__rt.kw([]));}catch(__t1){if(__rt.matches(__t1,ServiceError)){let error=__t1;__rt.call(__rt.attr(self,"respond"),[__rt.attr(error,"status"),__rt.dict([["error",__rt.attr(error,"code")],["message",__rt.call(__rt.b["str"],[error],__rt.kw([]))]])],__rt.kw([]));}else if(__rt.matches(__t1,__rt.tuple([__rt.b["ValueError"],__rt.b["TypeError"],__rt.b["KeyError"],__rt.b["UnicodeError"]]))){__rt.call(__rt.attr(self,"respond"),[400,__rt.dict([["error","INVALID_REQUEST"]])],__rt.kw([]));}else if(__rt.matches(__t1,__rt.tuple([__rt.b["BrokenPipeError"],__rt.b["ConnectionResetError"]]))){}else if(__rt.matches(__t1,__rt.b["Exception"])){__rt.call(__rt.attr(logging,"exception"),["Super Ace request failed"],__rt.kw([]));
__rt.call(__rt.attr(self,"respond"),[500,__rt.dict([["error","INTERNAL_ERROR"]])],__rt.kw([]));}else{throw __t1;}}return null;}),"launch":__rt.fn("launch",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){return __rt.bin("Add","/fullhouse/?",__rt.call(urlencode,[__rt.call(__rt.b["dict"],[],__rt.kw([["ops",token],["ssoKey","local"],["lang","en-US"],["legalLang","true"],["gameId",49],["loginFrom","trial"],["gs",__rt.item(__rt.item(__rt.attr(self,"headers"),"Host"),__rt.slice(null,null,__rt.unary("USub",1)))],["domain_platform",__rt.item(__rt.item(__rt.attr(self,"headers"),"Host"),__rt.slice(null,null,__rt.unary("USub",1)))],["domain_gs","localhost"],["be",__rt.item(__rt.item(__rt.attr(self,"headers"),"Host"),__rt.slice(null,null,__rt.unary("USub",1)))],["iu","true"],["apiId",2],["demo","true"],["skin",0]]))],__rt.kw([])));return null;}),"do_GET":__rt.fn("do_GET",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){__rt.call(__rt.attr(self,"guard"),[__rt.attr(self,"get")],__rt.kw([]));return null;}),"get":__rt.fn("get",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let allowed,body,document,mime,path,re,relative,rows,target,token,url;url=__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([]));
path=__rt.attr(url,"path");
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/"]))){token=__rt.item(__rt.call(__rt.attr(__rt.call(parse_qs,[__rt.attr(url,"query")],__rt.kw([])),"get"),["ops",[""]],__rt.kw([])),0);
if(__rt.truth(token)){__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));}else{token=__rt.item(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([])),"token");}
__rt.call(__rt.attr(self,"send_response"),[302],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Location",__rt.call(__rt.attr(self,"launch"),[token],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length","0"],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
return null;}
if(__rt.truth(__rt.or_(()=>__rt.compare(["Eq"],[()=>path,()=>"/health"]),()=>__rt.call(__rt.attr(path,"startswith"),["/api/"],__rt.kw([]))))){return __rt.call(__rt.attr(PlatformRoutes,"_get"),[self],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/history"]))){token=__rt.item(__rt.call(__rt.attr(__rt.call(parse_qs,[__rt.attr(url,"query")],__rt.kw([])),"get"),["ops",[""]],__rt.kw([])),0);
rows=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"history"),[token,100],__rt.kw([]));
body=__rt.call(__rt.attr("","join"),[(function*(){let row;for(const __t2 of __rt.iter(rows)){row=__t2;yield __rt.call(__rt.attr("<tr><td>{}</td><td>{:.4f}</td><td>{:.4f}</td><td>{:.4f}</td></tr>","format"),[__rt.call(__rt.attr(html,"escape"),[__rt.item(row,"round_id")],__rt.kw([])),__rt.bin("Div",__rt.item(__rt.item(row,"wallet"),"debit_minor"),10000),__rt.bin("Div",__rt.item(__rt.item(row,"wallet"),"credit_minor"),10000),__rt.bin("Div",__rt.item(__rt.item(row,"wallet"),"after_minor"),10000)],__rt.kw([]));}})()],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.bin("Add",__rt.bin("Add",__rt.bin("Add",__rt.bin("Add","<!doctype html><meta name=\"viewport\" content=\"width=device-width\"><title>Super Ace History</title><style>body{background:#24180d;color:#f9dfaa;font:16px system-ui;padding:20px}table{width:100%;border-collapse:collapse}td,th{padding:12px;text-align:right;border-bottom:1px solid #70532c}</style>",PAGE_BACK),"<h1>Super Ace</h1><table><tr><th>Round</th><th>Bet</th><th>Win</th><th>Balance</th></tr>"),body),"</table>"),"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/rules","/en-US/intro"])]))){document=__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"rules.html"),"read_text"),[],__rt.kw([["encoding","utf-8"]])),"replace"),["<h1>",__rt.bin("Add",PAGE_BACK,"<h1>"),1],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(document,"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
relative=__rt.call(__rt.attr(path,"lstrip"),["/"],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/fullhouse/"]))){token=__rt.item(__rt.call(__rt.attr(__rt.call(parse_qs,[__rt.attr(url,"query")],__rt.kw([])),"get"),["ops",[""]],__rt.kw([])),0);
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",token),()=>__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Sec-Fetch-Dest"],__rt.kw([])),()=>"empty"])))){return __rt.call(__rt.attr(self,"respond"),[204,Buffer.from([])],__rt.kw([]));}
__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));
document=__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fullhouse/index.html"),"read_text"),[],__rt.kw([["encoding","utf-8"]]));
document=__rt.call(__rt.attr(document,"replace"),["<head>","<head><script src=\"/local-adapter.js\"></script>",1],__rt.kw([]));
document=__rt.call(__rt.attr(document,"replace"),["<!-- Import map -->","<script>installSuperAceAdapter()</script><!-- Import map -->",1],__rt.kw([]));
re=__rt.modules["re"];
document=__rt.call(__rt.attr(re,"sub"),["<script[^>]+src=\"https://www\\.googletagmanager\\.com/[^>]+></script>","",document],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(document,"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
allowed=__rt.or_(()=>__rt.call(__rt.attr(relative,"startswith"),[__rt.tuple(["fullhouse/","astarte2/","smallicon/","static/"])],__rt.kw([])),()=>__rt.compare(["Eq"],[()=>relative,()=>"local-adapter.js"]));
target=__rt.call(__rt.attr(__rt.bin("Div",CLIENT,relative),"resolve"),[],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>allowed,()=>__rt.call(__rt.attr(target,"is_relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([])),()=>__rt.call(__rt.attr(target,"is_file"),[],__rt.kw([]))))){mime=__rt.or_(()=>__rt.item(__rt.call(__rt.attr(mimetypes,"guess_type"),[__rt.attr(target,"name")],__rt.kw([])),0),()=>"application/octet-stream");
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(target,"suffix"),()=>".js"]))){mime="application/javascript";}
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(target,"read_bytes"),[],__rt.kw([])),mime],__rt.kw([]));}
if(__rt.truth(__rt.call(__rt.attr(path,"startswith"),[__rt.tuple(["/webservice/event/","/g/collect","/lifeservice/"])],__rt.kw([])))){return __rt.call(__rt.attr(self,"respond"),[200,__rt.dict([])],__rt.kw([]));}
throw __rt.call(ServiceError,["NOT_FOUND","Unknown resource.",404],__rt.kw([]));return null;}),"do_POST":__rt.fn("do_POST",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){__rt.call(__rt.attr(self,"guard"),[__rt.attr(self,"post")],__rt.kw([]));return null;}),"post":__rt.fn("post",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let body,data,length,path,session,token;if(__rt.truth(__rt.and_(()=>__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Origin"],__rt.kw([])),()=>__rt.compare(["NotEq"],[()=>__rt.item(__rt.attr(self,"headers"),"Origin"),()=>__rt.bin("Add","http://",__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Host",""],__rt.kw([])))])))){throw __rt.call(ServiceError,["ORIGIN_REJECTED","Cross-origin writes are not enabled.",403],__rt.kw([]));}
length=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Content-Length",0],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>length,()=>131072])))){throw __rt.call(ServiceError,["BODY_TOO_LARGE","Request exceeds limit.",413],__rt.kw([]));}
body=__rt.call(__rt.attr(__rt.attr(self,"rfile"),"read"),[length],__rt.kw([]));
path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.call(__rt.attr(path,"startswith"),[__rt.tuple(["/webservice/event/","/g/collect","/subagentservice/"])],__rt.kw([])))){return __rt.call(__rt.attr(self,"respond"),[200,__rt.dict([])],__rt.kw([]));}
data=__rt.call(__rt.attr(json,"loads"),[__rt.or_(()=>body,()=>Buffer.from([123, 125]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[data,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/api/v1/sessions","/api/v1/games/super-ace/launch"])]))){if(__rt.truth(__rt.compare(["NotIn"],[()=>__rt.call(__rt.attr(data,"get"),["language","en"],__rt.kw([])),()=>__rt.tuple(["en","zh"])]))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
session=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[201,(__rt.truth(__rt.call(__rt.attr(path,"endswith"),["/launch"],__rt.kw([])))?__rt.dict([["game_id","super-ace"],["language",__rt.call(__rt.attr(data,"get"),["language","en"],__rt.kw([]))],["client_language","en"],["mode","generated"],["launch_url",__rt.bin("Add","/?",__rt.call(urlencode,[__rt.dict([["mock","1"],["ops",__rt.item(session,"token")]])],__rt.kw([])))],[null,(()=>{let k,v;const __out:any[]=[];for(const __t3 of __rt.iter(__rt.call(__rt.attr(session,"items"),[],__rt.kw([])))){{const __t4=Array.from(__rt.iter(__t3));k=__t4[0];v=__t4[1];}if(__rt.truth(__rt.compare(["NotIn"],[()=>k,()=>__rt.tuple(["token","player_id"])]))){__out.push([k,v]);}}return __rt.dict(__out);})()]]):session)],__rt.kw([]));}
token=__rt.call(__rt.attr(data,"get"),["token",""],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/jili/login"]))){return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"jili"),"login"),[token],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/jili/command"]))){return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"jili"),"handle"),[token,__rt.item(data,"ack"),__rt.call(__rt.attr(data,"get"),["payload",[]],__rt.kw([])),__rt.call(__rt.attr(data,"get"),["key"],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/api/v1/games/super-ace/spin"]))){return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"spin"),[__rt.call(__rt.attr(self,"_token"),[],__rt.kw([])),"super-ace",__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Idempotency-Key"],__rt.kw([])),__rt.call(__rt.attr(data,"get"),["previous_sid"],__rt.kw([])),__rt.call(__rt.attr(data,"get"),["bet",__rt.dict([])],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));}
throw __rt.call(ServiceError,["NOT_FOUND","Unknown endpoint.",404],__rt.kw([]));return null;})});
build_server=__rt.fn("build_server",{names:["port", "database", "config"],kwonly:[],defaults:{"port":8088,"database":null,"config":null},vararg:null,kwarg:null},function(port,database,config){let http,service;service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",ROOT,"services/super-ace/data/games.sqlite3")),__rt.call(create_registry,[["super-ace"],__rt.dict([["super-ace",__rt.or_(()=>config,()=>__rt.bin("Div",ROOT,"services/super-ace/config/super-ace.json"))]])],__rt.kw([]))],__rt.kw([]));
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),__rt.call(partial,[Handler],__rt.kw([["directory",__rt.call(__rt.b["str"],[CLIENT],__rt.kw([]))]]))],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
{const __t5=Array.from(__rt.iter(__rt.tuple([service,__rt.call(Adapter,[service],__rt.kw([]))])));__rt.setattr(http,"service",__t5[0]);__rt.setattr(http,"jili",__t5[1]);}
{const __t6=Array.from(__rt.iter(__rt.tuple([true,"super-ace"])));__rt.setattr(http,"generated",__t6[0]);__rt.setattr(http,"service_id",__t6[1]);}
return http;return null;});
