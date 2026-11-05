// Migrated from server/services/tower_run_treasure_steps_demo.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "../adapters/playngo/tower_run.js";
import * as __m1 from "../core/service.js";
import * as __m2 from "../games/catalog.js";
import * as __m3 from "../transport/http.js";
const __file__=__rt.sourcePath("server/services/tower_run_treasure_steps_demo.py");
export let Adapter:any,BaseHTTPRequestHandler:any,CLIENT:any,GameService:any,Handler:any,PlatformRoutes:any,ServiceError:any,SimpleCookie:any,ThreadingHTTPServer:any,build_server:any,create_registry:any,json:any,logging:any,mimetypes:any,parse_qs:any,re:any,unquote:any,urlencode:any,urlsplit:any;

BaseHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"BaseHTTPRequestHandler");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
SimpleCookie=__rt.attr(__rt.modules["http.cookies"],"SimpleCookie");
json=__rt.modules["json"];
logging=__rt.modules["logging"];
mimetypes=__rt.modules["mimetypes"];
re=__rt.modules["re"];
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
unquote=__rt.attr(__rt.modules["urllib.parse"],"unquote");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
Adapter=__rt.attr(__m0,"Adapter");
CLIENT=__rt.attr(__m0,"CLIENT");
ServiceError=__rt.attr(__rt.modules["server.core.contracts"],"ServiceError");
GameService=__rt.attr(__m1,"GameService");
create_registry=__rt.attr(__m2,"create_registry");
PlatformRoutes=__rt.attr(__m3,"PlatformRoutes");
Handler=__rt.cls("Handler",[PlatformRoutes,BaseHTTPRequestHandler],{"log_message":__rt.fn("log_message",{names:["self", "fmt"],kwonly:[],defaults:{},vararg:"args",kwarg:null},function(self,fmt,args){__rt.call(__rt.attr(logging,"info"),["%s %s",__rt.call(__rt.attr(self,"address_string"),[],__rt.kw([])),__rt.call(__rt.attr(re,"sub"),["\\?[^ ]*","",__rt.bin("Mod",fmt,args)],__rt.kw([]))],__rt.kw([]));return null;}),"_response":__rt.fn("_response",{names:["self", "status", "body", "content_type"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,status,body,content_type){__rt.call(__rt.attr(self,"send_response"),[status],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type",content_type],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[body],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Referrer-Policy","no-referrer"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["X-Content-Type-Options","nosniff"],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Security-Policy","default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' data: blob:; frame-src 'self'; worker-src 'self' blob:"],__rt.kw([]));
if(__rt.truth(__rt.call(__rt.b["getattr"],[self,"new_token",null],__rt.kw([])))){__rt.call(__rt.attr(self,"send_header"),["Set-Cookie",__rt.bin("Add",__rt.bin("Add","tower-session=",__rt.attr(self,"new_token")),"; Path=/; HttpOnly; SameSite=Lax")],__rt.kw([]));}
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
__rt.call(__rt.attr(__rt.attr(self,"wfile"),"write"),[body],__rt.kw([]));return null;}),"token":__rt.fn("token",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let cookies,item;cookies=__rt.call(SimpleCookie,[__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Cookie",""],__rt.kw([]))],__rt.kw([]));
item=__rt.call(__rt.attr(cookies,"get"),["tower-session"],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",item))){throw __rt.call(ServiceError,["SESSION_INVALID","Open the game first.",401],__rt.kw([]));}
__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[__rt.attr(item,"value")],__rt.kw([]));
return __rt.attr(item,"value");return null;}),"launch_game":__rt.fn("launch_game",{names:["self", "game_id", "language"],kwonly:[],defaults:{"language":"en"},vararg:null,kwarg:null},function(self,game_id,language){let session;if(__rt.truth(__rt.compare(["NotEq"],[()=>game_id,()=>"tower-run-treasure-steps"]))){throw __rt.call(ServiceError,["NOT_FOUND","Unknown game.",404],__rt.kw([]));}
if(__rt.truth(__rt.compare(["NotIn"],[()=>language,()=>__rt.tuple(["zh","en"])]))){throw __rt.call(ServiceError,["LANGUAGE_INVALID","Supported languages: zh, en."],__rt.kw([]));}
session=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]));
return __rt.call(__rt.b["dict"],[],__rt.kw([["game_id",game_id],["language",language],["client_language",(__rt.truth(__rt.compare(["Eq"],[()=>language,()=>"zh"]))?"zh_CN":"en_GB")],["launch_url",__rt.bin("Add","/?",__rt.call(urlencode,[__rt.call(__rt.b["dict"],[],__rt.kw([["mock",1],["ops",__rt.item(session,"token")],["lang",language]]))],__rt.kw([])))]]));return null;}),"localize":__rt.fn("localize",{names:["self", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,value){let host,prefix;if(__rt.truth(__rt.call(__rt.b["isinstance"],[value,__rt.b["dict"]],__rt.kw([])))){return (()=>{let k,v;const __out:any[]=[];for(const __t1 of __rt.iter(__rt.call(__rt.attr(value,"items"),[],__rt.kw([])))){{const __t2=Array.from(__rt.iter(__t1));k=__t2[0];v=__t2[1];}__out.push([k,__rt.call(__rt.attr(self,"localize"),[v],__rt.kw([]))]);}return __rt.dict(__out);})();}
if(__rt.truth(__rt.call(__rt.b["isinstance"],[value,__rt.b["list"]],__rt.kw([])))){return (()=>{let v;const __out:any[]=[];for(const __t3 of __rt.iter(value)){v=__t3;__out.push(__rt.call(__rt.attr(self,"localize"),[v],__rt.kw([])));}return __out;})();}
if(__rt.truth(__rt.call(__rt.b["isinstance"],[value,__rt.b["str"]],__rt.kw([])))){for(const __t4 of __rt.iter(__rt.tuple([__rt.tuple(["https://cdn.playngonetwork.com","/cdn"]),__rt.tuple(["https://pc-prod-eu.playngonetwork.com","/platform"]),__rt.tuple(["https://asccw.playngonetwork.com",""]),__rt.tuple(["https://ascflyp.playngonetwork.com",""]),__rt.tuple(["https://released.playngonetwork.com",""])]))){{const __t5=Array.from(__rt.iter(__t4));host=__t5[0];prefix=__t5[1];}value=__rt.call(__rt.attr(value,"replace"),[host,prefix],__rt.kw([]));}
return value;}
return value;return null;}),"_get":__rt.fn("_get",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let body,data,db,grouped,history,html,item,keys,name,pending,player,q,row,rows,seq,serve,text,token,u;u=__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([]));
q=__rt.call(parse_qs,[__rt.attr(u,"query")],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(u,"path"),()=>"/platform/player-events"]))){serve=__rt.attr(__rt.modules["server.adapters.playngo.player_events"],"serve");
return __rt.call(serve,[self],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>__rt.attr(u,"path"),()=>__rt.tuple(["/","/casino/ContainerLauncher"])]))){token=__rt.item(__rt.call(__rt.attr(q,"get"),["ops",[""]],__rt.kw([])),0);
if(__rt.truth(__rt.unary("Not",token))){token=__rt.item(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([])),"token");}
__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));
__rt.setattr(self,"new_token",token);
{const __t6=__rt.context(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"connection"),[],__rt.kw([])));let __t8=false;db=__t6.value;try{player=__rt.call(__rt.attr(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"sessions"),"_player"),[db,token],__rt.kw([]));
keys=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT request_key FROM spins WHERE player_id=? AND game_id='tower-run-treasure-steps'",__rt.tuple([__rt.item(player,"id")])],__rt.kw([])),"fetchall"),[],__rt.kw([]));
seq=__rt.call(__rt.b["max"],[(function*(){let r;for(const __t9 of __rt.iter(keys)){r=__t9;if(__rt.truth(__rt.call(__rt.attr(__rt.item(r,"request_key"),"startswith"),["playngo:"],__rt.kw([])))){yield __rt.call(__rt.b["int"],[__rt.item(__rt.call(__rt.attr(__rt.item(r,"request_key"),"split"),[":"],__rt.kw([])),1)],__rt.kw([]));}}})()],__rt.kw([["default",0]]));}catch(__t7){__t8=true;if(!__t6.exit(__t7))throw __t7;}finally{if(!__t8)__t6.exit(null);}}
html=__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/launcher.html"),"read_text"),[],__rt.kw([["encoding","utf-8"]]));
html=__rt.call(__rt.attr(re,"sub"),["window.serverUrl\\s*=\\s*\"[^\"]+\"","window.serverUrl = location.origin",html],__rt.kw([]));
html=__rt.call(__rt.attr(html,"replace"),["https://cdn.playngonetwork.com","/cdn"],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(q,"get"),["lang"],__rt.kw([])),()=>["zh"]]))){html=__rt.call(__rt.attr(html,"replace"),["lang: \"en_GB\"","lang: \"zh_CN\""],__rt.kw([]));}
html=__rt.call(__rt.attr(html,"replace"),["<head>",__rt.bin("Add",__rt.bin("Add",__rt.bin("Add",__rt.bin("Add","<head><title>Tower Run Treasure Steps</title><script>window.localTowerOps=",__rt.call(__rt.attr(json,"dumps"),[token],__rt.kw([]))),";window.localTowerSequence="),__rt.call(__rt.b["str"],[seq],__rt.kw([]))),";</script><script src=\"/local-adapter.js\"></script>")],__rt.kw([]));
return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(html,"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>__rt.attr(u,"path"),()=>__rt.tuple(["/games/1098","/games/getgamebygid/towerruntreasuresteps"])]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/game.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>__rt.attr(u,"path"),()=>__rt.tuple(["/configuration/prelaunchconfiguration","/configuration/v2"])]))){name=(__rt.truth(__rt.compare(["In"],[()=>"prelaunch",()=>__rt.attr(u,"path")]))?"prelaunch.json":"configuration.json");
data=__rt.call(__rt.attr(self,"localize"),[__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",__rt.bin("Div",CLIENT,"fixtures"),name),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>name,()=>"prelaunch.json"]))){__rt.setitem(data,"Server",__rt.bin("Add",__rt.bin("Add","http://",__rt.item(__rt.attr(self,"headers"),"Host")),"/"));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(q,"get"),["lang"],__rt.kw([])),()=>["zh_CN"]]))){__rt.setitem(data,"Language","zh_CN");}}else{history="/history";
if(__rt.truth(__rt.call(__rt.attr(q,"get"),["ops"],__rt.kw([])))){__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[__rt.item(__rt.item(q,"ops"),0)],__rt.kw([]));
history=__rt.bin("Add",history,__rt.bin("Add","?",__rt.call(urlencode,[__rt.call(__rt.b["dict"],[],__rt.kw([["ops",__rt.item(__rt.item(q,"ops"),0)]]))],__rt.kw([]))));}
__rt.call(__rt.attr(data,"update"),[],__rt.kw([["defaultProtocol","http"],["lobbyUrl","http://127.0.0.1:8080/demo/"],["desktopGameHistoryUrl",history],["mobileGameHistoryUrl",history]]));}
return __rt.call(__rt.attr(self,"_json"),[200,data],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(u,"path"),()=>"/casino/gamehelp"]))){name=(__rt.truth(__rt.compare(["In"],[()=>__rt.item(__rt.call(__rt.attr(q,"get"),["lang",[""]],__rt.kw([])),0),()=>__rt.tuple(["zh","zh_CN"])]))?"help-zh.html":"help.html");
text=__rt.call(__rt.attr(self,"localize"),[__rt.call(__rt.attr(__rt.bin("Div",__rt.bin("Div",CLIENT,"fixtures"),name),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]));
text=__rt.call(__rt.attr(__rt.call(__rt.attr(text,"replace"),["/Content/","/released/Content/"],__rt.kw([])),"replace"),["/casino/gamehelp/","/released/casino/gamehelp/"],__rt.kw([]));
return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(text,"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(u,"path"),()=>"/history"]))){token=__rt.or_(()=>__rt.item(__rt.call(__rt.attr(q,"get"),["ops",[null]],__rt.kw([])),0),()=>__rt.call(__rt.attr(self,"token"),[],__rt.kw([])));
rows=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"history"),[token,100],__rt.kw([]));
pending=__rt.item(__rt.item(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"state"),[token,"tower-run-treasure-steps"],__rt.kw([])),"state"),"pending");
grouped=__rt.dict([]);
for(const __t10 of __rt.iter(rows)){row=__t10;if(__rt.truth(__rt.and_(()=>pending,()=>__rt.compare(["Eq"],[()=>__rt.item(row,"round_id"),()=>__rt.item(pending,"round_id")])))){continue;}
item=__rt.call(__rt.attr(grouped,"setdefault"),[__rt.item(row,"round_id"),__rt.call(__rt.b["dict"],[],__rt.kw([["debit",0],["credit",0],["balance",__rt.item(__rt.item(row,"wallet"),"after_minor")]]))],__rt.kw([]));
__rt.setitem(item,"debit",__rt.bin("Add",__rt.item(item,"debit"),__rt.item(__rt.item(row,"wallet"),"debit_minor")));
__rt.setitem(item,"credit",__rt.bin("Add",__rt.item(item,"credit"),__rt.item(__rt.item(row,"wallet"),"credit_minor")));}
html=__rt.modules["html"];
body=__rt.call(__rt.attr("","join"),[(function*(){let item,rid;for(const __t11 of __rt.iter(__rt.call(__rt.attr(grouped,"items"),[],__rt.kw([])))){{const __t12=Array.from(__rt.iter(__t11));rid=__t12[0];item=__t12[1];}yield __rt.call(__rt.attr("<tr><td>{}</td><td>{:.2f}</td><td>{:.2f}</td><td>{:.2f}</td></tr>","format"),[__rt.call(__rt.attr(html,"escape"),[rid],__rt.kw([])),__rt.bin("Div",__rt.item(item,"debit"),100),__rt.bin("Div",__rt.item(item,"credit"),100),__rt.bin("Div",__rt.item(item,"balance"),100)],__rt.kw([]));}})()],__rt.kw([]));
text=__rt.bin("Add",__rt.bin("Add","<!doctype html><meta name=\"viewport\" content=\"width=device-width\"><title>Tower Run History</title><style>body{background:#14202b;color:#fff;font:16px system-ui;padding:24px}table{width:100%}td,th{text-align:right;padding:12px}</style><h1>Tower Run Treasure Steps</h1><table><tr><th>Round</th><th>Bet</th><th>Win</th><th>Balance</th></tr>",body),"</table>");
return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(text,"encode"),[],__rt.kw([])),"text/html; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.call(__rt.attr(__rt.attr(u,"path"),"endswith"),["/promotions/player/available"],__rt.kw([])))){return __rt.call(__rt.attr(self,"_json"),[200,[]],__rt.kw([]));}
return __rt.call(__rt.attr(__rt.super_(Handler,self),"_get"),[],__rt.kw([]));return null;}),"serve_assets":__rt.fn("serve_assets",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let asset_root,mime,name,target;name=__rt.call(__rt.attr(__rt.call(unquote,[__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path")],__rt.kw([])),"lstrip"),["/"],__rt.kw([]));
target=__rt.call(__rt.attr(__rt.bin("Div",CLIENT,name),"resolve"),[],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",__rt.call(__rt.attr(name,"startswith"),[__rt.tuple(["cdn/","platform/","released/"])],__rt.kw([]))),()=>__rt.compare(["NotEq"],[()=>name,()=>"local-adapter.js"])))){throw __rt.call(ServiceError,["NOT_FOUND","Unknown resource.",404],__rt.kw([]));}
asset_root=(__rt.truth(__rt.compare(["In"],[()=>"/",()=>name]))?__rt.call(__rt.attr(__rt.bin("Div",CLIENT,__rt.item(__rt.call(__rt.attr(name,"split"),["/"],__rt.kw([])),0)),"resolve"),[],__rt.kw([])):__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([])));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.attr(target,"is_relative_to"),[asset_root],__rt.kw([]))),()=>__rt.unary("Not",__rt.call(__rt.attr(target,"is_file"),[],__rt.kw([])))))){throw __rt.call(ServiceError,["NOT_FOUND","Unknown resource.",404],__rt.kw([]));}
mime=__rt.call(__rt.attr(__rt.dict([[".js","application/javascript"],[".json","application/json"],[".atlas","text/plain"]]),"get"),[__rt.attr(target,"suffix"),__rt.or_(()=>__rt.item(__rt.call(__rt.attr(mimetypes,"guess_type"),[__rt.attr(target,"name")],__rt.kw([])),0),()=>"application/octet-stream")],__rt.kw([]));
return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(target,"read_bytes"),[],__rt.kw([])),mime],__rt.kw([]));return null;}),"_post":__rt.fn("_post",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let command,commands,form,length,output,packet,sequence,token;if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path"),()=>"/"]))){return __rt.call(__rt.attr(__rt.super_(Handler,self),"_post"),[],__rt.kw([]));}
__rt.call(__rt.attr(self,"_guard_origin"),[],__rt.kw([]));
length=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Content-Length","0"],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.compare(["Lt", "LtE"],[()=>0,()=>length,()=>65536])))){throw __rt.call(ServiceError,["REQUEST_INVALID","Invalid request size."],__rt.kw([]));}
form=__rt.call(parse_qs,[__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.attr(self,"rfile"),"read"),[length],__rt.kw([])),"decode"),["utf-8"],__rt.kw([]))],__rt.kw([["keep_blank_values",true]]));
packet=__rt.call(__rt.attr(__rt.item(__rt.call(__rt.attr(form,"get"),["d",[""]],__rt.kw([])),0),"splitlines"),[],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.b["len"],[packet],__rt.kw([])),()=>3]),()=>__rt.unary("Not",__rt.call(__rt.attr(__rt.item(packet,0),"isdigit"),[],__rt.kw([])))))){throw __rt.call(ServiceError,["REQUEST_INVALID","Invalid packet."],__rt.kw([]));}
token=__rt.item(__rt.call(__rt.attr(__rt.item(packet,1),"split"),["!",1],__rt.kw([])),0);
__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));
sequence=__rt.call(__rt.b["int"],[__rt.item(packet,0)],__rt.kw([]));
commands=(()=>{let s;const __out:any[]=[];for(const __t13 of __rt.iter(__rt.item(packet,__rt.slice(2,null,null)))){s=__t13;if(__rt.truth(__rt.call(__rt.attr(s,"strip"),[],__rt.kw([])))){__out.push(s);}}return __out;})();
output=[];
for(const __t14 of __rt.iter(commands)){command=__t14;__rt.call(__rt.attr(output,"extend"),[__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"playngo"),"call"),[token,sequence,command],__rt.kw([]))],__rt.kw([]));}
return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(__rt.bin("Add",__rt.bin("Add","d=",__rt.call(__rt.attr("\r\n","join"),[output],__rt.kw([]))),"\r\n\r\n"),"encode"),[],__rt.kw([])),"text/plain; charset=utf-8"],__rt.kw([]));return null;})});
build_server=__rt.fn("build_server",{names:["port", "database", "config"],kwonly:[],defaults:{"port":8099,"database":null,"config":null},vararg:null,kwarg:null},function(port,database,config){let http,service,service_dir;service_dir=__rt.bin("Div",__rt.item(__rt.attr(CLIENT,"parents"),1),"services/tower-run-treasure-steps");
service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",service_dir,"data/games.sqlite3")),__rt.call(create_registry,[["tower-run-treasure-steps"],(__rt.truth(config)?__rt.dict([["tower-run-treasure-steps",config]]):__rt.dict([]))],__rt.kw([]))],__rt.kw([]));
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),Handler],__rt.kw([]));
{const __t15=Array.from(__rt.iter(__rt.tuple([service,__rt.call(Adapter,[service],__rt.kw([]))])));__rt.setattr(http,"service",__t15[0]);__rt.setattr(http,"playngo",__t15[1]);}
{const __t16=Array.from(__rt.iter(__rt.tuple(["tower-run-treasure-steps","generated"])));__rt.setattr(http,"service_id",__t16[0]);__rt.setattr(http,"engine_mode",__t16[1]);}
return http;return null;});
