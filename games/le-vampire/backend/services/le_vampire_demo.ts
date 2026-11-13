// Migrated from py/services/le_vampire_demo.py. Runtime is Node.js only.
import * as __rt from "../../../../other/shared/compat/runtime.js";
import * as __m0 from "../adapters/hacksaw/le_vampire.js";
import * as __m1 from "../../../../other/shared/migrated/py/core/service.js";
import * as __m2 from "../../../../other/shared/migrated/py/games/catalog.js";
import * as __m3 from "../../../../other/shared/migrated/py/transport/http.js";
const __file__=__rt.sourcePath("py/services/le_vampire_demo.py");
export let Adapter:any,BaseHTTPRequestHandler:any,CLIENT:any,GameService:any,Handler:any,PREFIX:any,PlatformRoutes:any,ServiceError:any,ThreadingHTTPServer:any,build_server:any,create_registry:any,html:any,json:any,logging:any,mimetypes:any,parse_qs:any,unquote:any,urlencode:any,urlsplit:any;

html=__rt.modules["html"];
json=__rt.modules["json"];
logging=__rt.modules["logging"];
mimetypes=__rt.modules["mimetypes"];
BaseHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"BaseHTTPRequestHandler");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
unquote=__rt.attr(__rt.modules["urllib.parse"],"unquote");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
Adapter=__rt.attr(__m0,"Adapter");
CLIENT=__rt.attr(__m0,"CLIENT");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
GameService=__rt.attr(__m1,"GameService");
create_registry=__rt.attr(__m2,"create_registry");
PlatformRoutes=__rt.attr(__m3,"PlatformRoutes");
PREFIX="/2582/1.36.0/";
Handler=__rt.cls("Handler",[PlatformRoutes,BaseHTTPRequestHandler],{"log_message":__rt.fn("log_message",{names:["self", "format"],kwonly:[],defaults:{},vararg:"args",kwarg:null},function(self,format,args){let re;re=__rt.modules["re"];
__rt.call(__rt.attr(logging,"info"),["%s %s",__rt.call(__rt.attr(self,"address_string"),[],__rt.kw([])),__rt.call(__rt.attr(re,"sub"),["\\?[^ ]*","",__rt.bin("Mod",format,args)],__rt.kw([]))],__rt.kw([]));return null;}),"_response":__rt.fn("_response",{names:["self", "status", "body", "content_type"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,status,body,content_type){__rt.call(__rt.attr(self,"send_response"),[status],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type",content_type],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[body],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Referrer-Policy","no-referrer"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["X-Content-Type-Options","nosniff"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Security-Policy","default-src 'self' blob: data:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' blob: data:; worker-src 'self' blob:; frame-src 'self';"],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
__rt.call(__rt.attr(__rt.attr(self,"wfile"),"write"),[body],__rt.kw([]));return null;}),"redirect":__rt.fn("redirect",{names:["self", "url"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,url){__rt.call(__rt.attr(self,"send_response"),[302],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Location",url],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length","0"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Referrer-Policy","no-referrer"],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));return null;}),"launch_game":__rt.fn("launch_game",{names:["self", "game_id", "language"],kwonly:[],defaults:{"language":"zh"},vararg:null,kwarg:null},function(self,game_id,language){let session;if(__rt.truth(__rt.compare(["NotEq"],[()=>game_id,()=>"le-vampire"]))){throw __rt.call(ServiceError,["NOT_FOUND","Unknown game.",404],__rt.kw([]));}
if(__rt.truth(__rt.compare(["NotIn"],[()=>language,()=>__rt.tuple(["en","zh"])]))){throw __rt.call(ServiceError,["LANGUAGE_INVALID","Supported languages: en, zh."],__rt.kw([]));}
session=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]));
return __rt.dict([["game_id",game_id],["language",language],["client_language",(__rt.truth(__rt.compare(["Eq"],[()=>language,()=>"zh"]))?"zh-cn":"en-us")],["launch_url",__rt.bin("Add","/?",__rt.call(urlencode,[__rt.call(__rt.b["dict"],[],__rt.kw([["mock",1],["ops",__rt.item(session,"token")],["lang",language]]))],__rt.kw([])))],[null,(()=>{let k,v;const __out:any[]=[];for(const __t1 of __rt.iter(__rt.call(__rt.attr(session,"items"),[],__rt.kw([])))){{const __t2=Array.from(__rt.iter(__t1));k=__t2[0];v=__t2[1];}if(__rt.truth(__rt.compare(["NotIn"],[()=>k,()=>__rt.tuple(["token","player_id"])]))){__out.push([k,v]);}}return __rt.dict(__out);})()]]);return null;}),"_get":__rt.fn("_get",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let args,body,db,document,grouped,item,keys,lang,pending,player,query,rid,row,rows,sequence,token,url;url=__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([]));
query=__rt.call(parse_qs,[__rt.attr(url,"query")],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(url,"path"),()=>"/"]))){token=__rt.or_(()=>__rt.item(__rt.call(__rt.attr(query,"get"),["ops",[""]],__rt.kw([])),0),()=>__rt.item(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([])),"token"));
__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));
{const __t3=__rt.context(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"connection"),[],__rt.kw([])));let __t5=false;db=__t3.value;try{player=__rt.call(__rt.attr(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"sessions"),"_player"),[db,token],__rt.kw([]));
keys=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT request_key FROM spins WHERE player_id=? AND game_id='le-vampire'",__rt.tuple([__rt.item(player,"id")])],__rt.kw([])),"fetchall"),[],__rt.kw([]));
sequence=__rt.call(__rt.b["max"],[(function*(){let row;for(const __t6 of __rt.iter(keys)){row=__t6;if(__rt.truth(__rt.call(__rt.attr(__rt.item(row,"request_key"),"startswith"),["hacksaw:"],__rt.kw([])))){yield __rt.call(__rt.b["int"],[__rt.item(__rt.call(__rt.attr(__rt.item(row,"request_key"),"split"),[":"],__rt.kw([])),1)],__rt.kw([]));}}})()],__rt.kw([["default",0]]));}catch(__t4){__t5=true;if(!__t3.exit(__t4))throw __t4;}finally{if(!__t5)__t3.exit(null);}}
lang=(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(query,"get"),["lang"],__rt.kw([])),()=>["zh"]]))?"zh-cn":"en-us");
args=__rt.call(__rt.b["dict"],[],__rt.kw([["gameid",2582],["token",token],["sessionuuid",token],["seq",sequence],["language",lang],["currency","EUR"],["country","US"],["partner","demo"],["mode",2],["backend",1],["env","/api"],["apienv","/api"],["channel",__rt.item(__rt.call(__rt.attr(query,"get"),["channel",["desktop"]],__rt.kw([])),0)],["branding","default"],["disableddemotext","true"],["historyurl",__rt.bin("Add","/history?",__rt.call(urlencode,[__rt.dict([["ops",token]])],__rt.kw([])))],["lobbyurl","http://127.0.0.1:8080/demo/"]]));
return __rt.call(__rt.attr(self,"redirect"),[__rt.bin("Add",__rt.bin("Add",PREFIX,"index.html?"),__rt.call(urlencode,[args],__rt.kw([])))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(url,"path"),()=>"/api/meta/gameInfo"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.attr(__rt.attr(__rt.attr(self,"server"),"hacksaw"),"info")],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(url,"path"),()=>"/history"]))){token=__rt.item(__rt.call(__rt.attr(query,"get"),["ops",[""]],__rt.kw([])),0);
rows=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"history"),[token,100],__rt.kw([]));
pending=__rt.item(__rt.item(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"state"),[token,"le-vampire"],__rt.kw([])),"state"),"pending");
grouped=__rt.dict([]);
for(const __t7 of __rt.iter(rows)){row=__t7;rid=__rt.item(row,"round_id");
if(__rt.truth(__rt.and_(()=>pending,()=>__rt.compare(["Eq"],[()=>rid,()=>__rt.item(pending,"round_id")])))){continue;}
item=__rt.call(__rt.attr(grouped,"setdefault"),[rid,__rt.dict([["round_id",rid],["wallet",__rt.dict([["debit_minor",0],["credit_minor",0],["after_minor",__rt.item(__rt.item(row,"wallet"),"after_minor")]])]])],__rt.kw([]));
__rt.setitem(__rt.item(item,"wallet"),"debit_minor",__rt.bin("Add",__rt.item(__rt.item(item,"wallet"),"debit_minor"),__rt.item(__rt.item(row,"wallet"),"debit_minor")));
__rt.setitem(__rt.item(item,"wallet"),"credit_minor",__rt.bin("Add",__rt.item(__rt.item(item,"wallet"),"credit_minor"),__rt.item(__rt.item(row,"wallet"),"credit_minor")));}
rows=__rt.call(__rt.b["list"],[__rt.call(__rt.attr(grouped,"values"),[],__rt.kw([]))],__rt.kw([]));
body=__rt.call(__rt.attr("","join"),[(function*(){let row;for(const __t8 of __rt.iter(rows)){row=__t8;yield __rt.call(__rt.attr("<tr><td>{}</td><td>{:.2f}</td><td>{:.2f}</td><td>{:.2f}</td></tr>","format"),[__rt.call(__rt.attr(html,"escape"),[__rt.item(row,"round_id")],__rt.kw([])),__rt.bin("Div",__rt.item(__rt.item(row,"wallet"),"debit_minor"),100),__rt.bin("Div",__rt.item(__rt.item(row,"wallet"),"credit_minor"),100),__rt.bin("Div",__rt.item(__rt.item(row,"wallet"),"after_minor"),100)],__rt.kw([]));}})()],__rt.kw([]));
document=__rt.bin("Add",__rt.bin("Add","<!doctype html><meta name=\"viewport\" content=\"width=device-width\"><title>Le Vampire History</title><style>body{font:16px system-ui;background:#141414;color:#fff;padding:24px}td,th{padding:12px;text-align:right}table{width:100%}</style><h1>Le Vampire</h1><table><tr><th>Round</th><th>Bet</th><th>Paid</th><th>Balance</th></tr>",body),"</table>");
return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(document,"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
return __rt.call(__rt.attr(__rt.super_(Handler,self),"_get"),[],__rt.kw([]));return null;}),"serve_assets":__rt.fn("serve_assets",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let allowed,data,document,mime,re,relative,target;relative=__rt.call(__rt.attr(__rt.call(unquote,[__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path")],__rt.kw([])),"lstrip"),["/"],__rt.kw([]));
target=__rt.call(__rt.attr(__rt.bin("Div",CLIENT,relative),"resolve"),[],__rt.kw([]));
allowed=__rt.or_(()=>__rt.call(__rt.attr(relative,"startswith"),[__rt.tuple(["2582/","integrations/"])],__rt.kw([])),()=>__rt.compare(["Eq"],[()=>relative,()=>"local-adapter.js"]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",allowed),()=>__rt.unary("Not",__rt.call(__rt.attr(target,"is_relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([]))),()=>__rt.unary("Not",__rt.call(__rt.attr(target,"is_file"),[],__rt.kw([])))))){throw __rt.call(ServiceError,["NOT_FOUND","Unknown resource.",404],__rt.kw([]));}
data=__rt.call(__rt.attr(target,"read_bytes"),[],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>relative,()=>__rt.bin("Add",__rt.call(__rt.attr(PREFIX,"lstrip"),["/"],__rt.kw([])),"index.html")]))){document=__rt.call(__rt.attr(__rt.call(__rt.attr(data,"decode"),["utf-8"],__rt.kw([])),"replace"),["<head>","<head><script src=\"/local-adapter.js\"></script>",1],__rt.kw([]));
re=__rt.modules["re"];
document=__rt.call(__rt.attr(re,"sub"),["<script[^>]+src=\"https://static\\.cloudflareinsights\\.com/[^>]*></script>","",document],__rt.kw([]));
data=__rt.call(__rt.attr(document,"encode"),["utf-8"],__rt.kw([]));}
mime=__rt.call(__rt.attr(__rt.dict([[".js","application/javascript"],[".wasm","application/wasm"],[".ktx2","image/ktx2"],[".json","application/json"]]),"get"),[__rt.attr(target,"suffix"),__rt.or_(()=>__rt.item(__rt.call(__rt.attr(mimetypes,"guess_type"),[__rt.attr(target,"name")],__rt.kw([])),0),()=>"application/octet-stream")],__rt.kw([]));
__rt.call(__rt.attr(self,"_response"),[200,data,mime],__rt.kw([]));return null;}),"_post":__rt.fn("_post",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let adapter,data,details,endpoint,length,path,result;path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.attr(path,"startswith"),[__rt.tuple(["/api/play/","/telemetry/"])],__rt.kw([]))))){return __rt.call(__rt.attr(__rt.super_(Handler,self),"_post"),[],__rt.kw([]));}
__rt.call(__rt.attr(self,"_guard_origin"),[],__rt.kw([]));
length=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Content-Length","0"],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>length,()=>65536])))){throw __rt.call(ServiceError,["BODY_TOO_LARGE","Request exceeds 64 KiB.",413],__rt.kw([]));}
data=__rt.call(__rt.attr(json,"loads"),[__rt.or_(()=>__rt.call(__rt.attr(__rt.attr(self,"rfile"),"read"),[length],__rt.kw([])),()=>Buffer.from([123, 125]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[data,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],["Expected an object"],__rt.kw([]));}
adapter=__rt.attr(__rt.attr(self,"server"),"hacksaw");
endpoint=__rt.item(__rt.call(__rt.attr(path,"rsplit"),["/",1],__rt.kw([])),__rt.unary("USub",1));
if(__rt.truth(__rt.call(__rt.attr(path,"startswith"),["/telemetry/"],__rt.kw([])))){result=__rt.call(__rt.attr(adapter,"response"),[],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>endpoint,()=>"authenticate"]))){result=__rt.call(__rt.attr(adapter,"authenticate"),[__rt.call(__rt.attr(data,"get"),["token"],__rt.kw([]))],__rt.kw([]));
__rt.setitem(result,"languageCode",__rt.call(__rt.attr(data,"get"),["languageCode","en-us"],__rt.kw([])));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>endpoint,()=>"partnerSettings"]))){result=__rt.attr(adapter,"partner");}else{if(__rt.truth(__rt.compare(["Eq"],[()=>endpoint,()=>"bet"]))){result=__rt.call(__rt.attr(adapter,"bet"),[data],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["In"],[()=>endpoint,()=>__rt.tuple(["balance","keepAlive","gameLaunch","endSessionBeacon","logError","logEvent","gameError"])]))){if(__rt.truth(__rt.compare(["Eq"],[()=>endpoint,()=>"gameError"]))){details=(()=>{let k,v;const __out:any[]=[];for(const __t9 of __rt.iter(__rt.call(__rt.attr(data,"items"),[],__rt.kw([])))){{const __t10=Array.from(__rt.iter(__t9));k=__t10[0];v=__t10[1];}if(__rt.truth(__rt.compare(["NotIn"],[()=>k,()=>__rt.tuple(["token","sessionUuid","playerId"])]))){__out.push([k,v]);}}return __rt.dict(__out);})();
__rt.call(__rt.attr(logging,"warning"),["Le Vampire client error: %s",__rt.item(__rt.call(__rt.attr(json,"dumps"),[details],__rt.kw([])),__rt.slice(null,8000,null))],__rt.kw([]));}
result=__rt.call(__rt.attr(adapter,"response"),[__rt.or_(()=>__rt.call(__rt.attr(data,"get"),["sessionUuid"],__rt.kw([])),()=>__rt.call(__rt.attr(data,"get"),["token"],__rt.kw([])))],__rt.kw([]));}else{throw __rt.call(ServiceError,["NOT_FOUND","Unknown Hacksaw endpoint.",404],__rt.kw([]));}}}}}
__rt.call(__rt.attr(self,"_json"),[200,result],__rt.kw([]));return null;}),"do_POST":__rt.fn("do_POST",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let codes;if(__rt.truth(__rt.unary("Not",__rt.call(__rt.attr(__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path"),"startswith"),["/api/play/"],__rt.kw([]))))){return __rt.call(__rt.attr(__rt.super_(Handler,self),"do_POST"),[],__rt.kw([]));}
try{__rt.call(__rt.attr(self,"_post"),[],__rt.kw([]));}catch(__t11){if(__rt.matches(__t11,ServiceError)){let error=__t11;codes=__rt.dict([["INSUFFICIENT_BALANCE",5],["BET_INVALID",13],["REQUEST_INVALID",11],["IDEMPOTENCY_CONFLICT",14],["STALE_STATE",14],["ROUND_PENDING",14],["ROUND_INVALID",14],["ORIGIN_REJECTED",11]]);
__rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.b["dict"],[],__rt.kw([["statusCode",__rt.call(__rt.attr(codes,"get"),[__rt.attr(error,"code"),(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(error,"status"),()=>401]))?2:1)],__rt.kw([]))],["statusMessage",__rt.call(__rt.b["str"],[error],__rt.kw([]))],["accountBalance",null]]))],__rt.kw([]));}else if(__rt.matches(__t11,__rt.tuple([__rt.b["ValueError"],__rt.b["TypeError"],__rt.b["KeyError"],__rt.b["UnicodeError"]]))){__rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.b["dict"],[],__rt.kw([["statusCode",11],["statusMessage","Invalid request."],["accountBalance",null]]))],__rt.kw([]));}else if(__rt.matches(__t11,__rt.tuple([__rt.b["BrokenPipeError"],__rt.b["ConnectionResetError"]]))){}else if(__rt.matches(__t11,__rt.b["Exception"])){__rt.call(__rt.attr(logging,"exception"),["Le Vampire request failed"],__rt.kw([]));
__rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.b["dict"],[],__rt.kw([["statusCode",1],["statusMessage","Request was not committed."],["accountBalance",null]]))],__rt.kw([]));}else{throw __t11;}}return null;})});
build_server=__rt.fn("build_server",{names:["port", "database", "config"],kwonly:[],defaults:{"port":8096,"database":null,"config":null},vararg:null,kwarg:null},function(port,database,config){let http,root,service,service_dir;root=__rt.item(__rt.attr(CLIENT,"parents"),1);
service_dir=__rt.bin("Div",root,"services/le-vampire");
service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",service_dir,"data/games.sqlite3")),__rt.call(create_registry,[["le-vampire"],(__rt.truth(config)?__rt.dict([["le-vampire",config]]):__rt.dict([]))],__rt.kw([]))],__rt.kw([]));
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),Handler],__rt.kw([]));
{const __t12=Array.from(__rt.iter(__rt.tuple([service,__rt.call(Adapter,[service],__rt.kw([]))])));__rt.setattr(http,"service",__t12[0]);__rt.setattr(http,"hacksaw",__t12[1]);}
{const __t13=Array.from(__rt.iter(__rt.tuple(["le-vampire","generated"])));__rt.setattr(http,"service_id",__t13[0]);__rt.setattr(http,"engine_mode",__t13[1]);}
return http;return null;});
