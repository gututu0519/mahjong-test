// Migrated from py/services/fortune_rabbit_demo.py. Runtime is Node.js only.
import * as __rt from "../../../../other/shared/compat/runtime.js";
import * as __m0 from "../../../../other/shared/migrated/py/core/service.js";
import * as __m1 from "../../../../other/shared/migrated/py/games/catalog.js";
import * as __m2 from "../adapters/pg/fortune_rabbit.js";
import * as __m3 from "../../../../other/shared/migrated/py/transport/http.js";
const __file__=__rt.sourcePath("py/services/fortune_rabbit_demo.py");
export let CLIENT:any,GameService:any,Handler:any,PGAdapter:any,Path:any,PlatformRoutes:any,ROOT:any,ServiceError:any,SimpleHTTPRequestHandler:any,ThreadingHTTPServer:any,build_server:any,copy:any,create_registry:any,hashlib:any,json:any,parse_qs:any,partial:any,prepare_module:any,urlencode:any,urlsplit:any;

copy=__rt.modules["copy"];
hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
partial=__rt.attr(__rt.modules["functools"],"partial");
SimpleHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"SimpleHTTPRequestHandler");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
GameService=__rt.attr(__m0,"GameService");
create_registry=__rt.attr(__m1,"create_registry");
PGAdapter=__rt.attr(__m2,"PGAdapter");
PlatformRoutes=__rt.attr(__m3,"PlatformRoutes");
ROOT=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),2);
CLIENT=__rt.bin("Div",ROOT,"clients/fortune-rabbit");
prepare_module=__rt.attr(__rt.modules["py.adapters.pg.client_modules"],"prepare_module");
Handler=__rt.cls("Handler",[PlatformRoutes,SimpleHTTPRequestHandler],{"launch_game":__rt.fn("launch_game",{names:["self", "game_id", "language"],kwonly:[],defaults:{"language":"zh"},vararg:null,kwarg:null},function(self,game_id,language){let query,session;__rt.call(__rt.attr(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"registry"),"get"),[game_id],__rt.kw([]));
if(__rt.truth(__rt.compare(["NotIn"],[()=>language,()=>__rt.tuple(["zh","en"])]))){throw __rt.call(ServiceError,["LANGUAGE_INVALID","Supported languages: zh, en."],__rt.kw([]));}
session=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]));
query=__rt.call(urlencode,[__rt.call(__rt.b["dict"],[],__rt.kw([["mock",1],["l","en"],["ops",__rt.item(session,"token")],["btt",2]]))],__rt.kw([]));
return __rt.call(__rt.b["dict"],[],__rt.kw([["game_id",game_id],["language",language],["client_language","en"],["launch_url",__rt.bin("Add","/?",query)],["mode","generated"],["expires_at",__rt.item(session,"expires_at")],["balance_minor",__rt.item(session,"balance_minor")],["currency","DEMO"],["minor_unit",100]]));return null;}),"compatibility_post":__rt.fn("compatibility_post",{names:["self", "path", "body"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path,body){let data,form,token,wallet;token=__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["X-Local-Game-Session"],__rt.kw([]));
form=(__rt.truth(__rt.call(__rt.attr(path,"startswith"),["/web-api/"],__rt.kw([])))?__rt.call(parse_qs,[__rt.call(__rt.attr(body,"decode"),["utf-8"],__rt.kw([]))],__rt.kw([["keep_blank_values",true]])):__rt.dict([]));
token=__rt.or_(()=>token,()=>__rt.item(__rt.call(__rt.attr(form,"get"),["atk",[null]],__rt.kw([])),0));
wallet=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/web-api/auth/session/v2/verifySession","/web-api/auth/session/v2/verifyOperatorPlayerSession"])]))){data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(__rt.attr(self,"server"),"auth")],__rt.kw([]));
__rt.call(__rt.attr(data,"update"),[],__rt.kw([["tk",token],["pid",__rt.item(wallet,"player_id")],["pcd",__rt.item(wallet,"player_id")],["bl",__rt.bin("Div",__rt.item(wallet,"balance_minor"),100)]]));
return __rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.b["dict"],[],__rt.kw([["dt",data],["err",null]]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/game-api/fortune-rabbit/v4/GameInfo/Get"]))){return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pg"),"game_info"),[body,token],__rt.kw([])),"application/octet-stream"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/game-api/fortune-rabbit/v4/Spin"]))){return __rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pg"),"spin"),[body,token],__rt.kw([])),"application/octet-stream"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameWallet/Get"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pg"),"wallet"),[token],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/web-api/game-proxy/v2/BetSummary/Get","/web-api/game-proxy/v2/BetHistory/Get"])]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pg"),"history"),[token,form],__rt.kw([["summary",__rt.compare(["In"],[()=>"/BetSummary/",()=>path])]]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameName/Get"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",__rt.dict([["1543462","Fortune Rabbit"]])],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameRule/Get"]))){if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.item(__rt.call(__rt.attr(form,"get"),["gid",["1543462"]],__rt.kw([])),0),()=>"1543462"]))){throw __rt.call(ServiceError,["GAME_NOT_FOUND","Unknown game.",404],__rt.kw([]));}
return __rt.call(__rt.attr(self,"_json"),[200,__rt.attr(__rt.attr(self,"server"),"game_rule")],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",[]],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/ServerManager/RefreshWallet"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",null],["err",null]])],__rt.kw([]));}
throw __rt.call(ServiceError,["NOT_IMPLEMENTED","Unknown endpoint.",501],__rt.kw([]));return null;}),"serve_assets":__rt.fn("serve_assets",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){return __rt.call(__rt.attr(SimpleHTTPRequestHandler,"do_GET"),[self],__rt.kw([]));return null;}),"list_directory":__rt.fn("list_directory",{names:["self", "path"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;return null;}),"send_head":__rt.fn("send_head",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let _,data,original,path,scripts,url_path;url_path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.compare(["Eq"],[()=>url_path,()=>"/"]))){__rt.call(__rt.attr(self,"send_response"),[302],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Location",__rt.bin("Add","/1543462/index.html?",__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"query"))],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
return null;}
path=__rt.call(__rt.attr(__rt.call(Path,[__rt.call(__rt.attr(self,"translate_path"),[__rt.attr(self,"path")],__rt.kw([]))],__rt.kw([])),"resolve"),[],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.attr(path,"is_relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([]))),()=>__rt.compare(["In"],[()=>"fixtures",()=>__rt.attr(__rt.call(__rt.attr(path,"relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([])),"parts")])))){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;}
if(__rt.truth(__rt.compare(["In"],[()=>__rt.call(__rt.attr(__rt.attr(path,"suffix"),"lower"),[],__rt.kw([])),()=>__rt.tuple([".py",".pyc",".md",".bat",".har",".txt"])]))){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;}
if(__rt.truth(__rt.compare(["Eq"],[()=>url_path,()=>"/local-bootstrap.js"]))){return __rt.call(__rt.attr(self,"_asset"),[__rt.call(__rt.attr(path,"read_bytes"),[],__rt.kw([])),"application/javascript; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>url_path,()=>"/1543462/index.html"]))){data=__rt.call(__rt.attr(path,"read_bytes"),[],__rt.kw([]));
original=Buffer.from([120, 116, 61, 105, 44, 107, 116, 61, 39, 39]);
if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(data,"count"),[original],__rt.kw([])),()=>1]))){throw __rt.call(__rt.b["ValueError"],["Entry base changed"],__rt.kw([]));}
data=__rt.call(__rt.attr(data,"replace"),[original,Buffer.from([120, 116, 61, 110, 101, 119, 32, 85, 82, 76, 40, 39, 47, 115, 104, 97, 114, 101, 100, 47, 39, 44, 108, 111, 99, 97, 116, 105, 111, 110, 46, 104, 114, 101, 102, 41, 46, 104, 114, 101, 102, 44, 107, 116, 61, 110, 101, 119, 32, 85, 82, 76, 40, 39, 47, 49, 53, 52, 51, 52, 54, 50, 47, 39, 44, 108, 111, 99, 97, 116, 105, 111, 110, 46, 104, 114, 101, 102, 41, 46, 104, 114, 101, 102]),1],__rt.kw([]));
scripts=__rt.call(__rt.attr("","join"),[(function*(){let name;for(const __t1 of __rt.iter(__rt.tuple(["local-bootstrap.js","local-frame-clock.js"]))){name=__t1;yield ("<script src=\"/"+__rt.format(name,"",-1)+"?v="+__rt.format(__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,name),"read_bytes"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,12,null)),"",-1)+"\"></script>");}})()],__rt.kw([]));
data=__rt.call(__rt.attr(data,"replace"),[Buffer.from([60, 115, 99, 114, 105, 112, 116, 32, 105, 100, 61, 34, 109, 97, 105, 110, 45, 115, 99, 114, 105, 112, 116, 34]),__rt.bin("Add",__rt.call(__rt.attr(scripts,"encode"),[],__rt.kw([])),Buffer.from([60, 115, 99, 114, 105, 112, 116, 32, 105, 100, 61, 34, 109, 97, 105, 110, 45, 115, 99, 114, 105, 112, 116, 34])),1],__rt.kw([]));
return __rt.call(__rt.attr(self,"_asset"),[data,"text/html; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.attr(path,"name"),()=>"index.js"]),()=>__rt.compare(["In"],[()=>"shared",()=>__rt.attr(path,"parts")]),()=>__rt.call(__rt.attr(path,"is_file"),[],__rt.kw([]))))){{const __t2=Array.from(__rt.iter(__rt.call(prepare_module,[__rt.call(__rt.attr(path,"read_bytes"),[],__rt.kw([]))],__rt.kw([]))));data=__t2[0];_=__t2[1];}
return __rt.call(__rt.attr(self,"_asset"),[data,"application/javascript; charset=utf-8"],__rt.kw([]));}
return __rt.call(__rt.attr(__rt.super_(Handler,self),"send_head"),[],__rt.kw([]));return null;}),"_asset":__rt.fn("_asset",{names:["self", "data", "mime"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,data,mime){let BytesIO;BytesIO=__rt.attr(__rt.modules["io"],"BytesIO");
__rt.call(__rt.attr(self,"send_response"),[200],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Type",mime],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Content-Length",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[data],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(self,"send_header"),["Cache-Control","no-store"],__rt.kw([]));
__rt.call(__rt.attr(self,"end_headers"),[],__rt.kw([]));
return __rt.call(BytesIO,[data],__rt.kw([]));return null;})});
build_server=__rt.fn("build_server",{names:["port", "database", "config"],kwonly:[],defaults:{"port":8101,"database":null,"config":null},vararg:null,kwarg:null},function(port,database,config){let http,registry,service;registry=__rt.call(create_registry,[["fortune-rabbit"],__rt.dict([["fortune-rabbit",__rt.or_(()=>config,()=>__rt.bin("Div",ROOT,"services/fortune-rabbit/config/fortune-rabbit.json"))]])],__rt.kw([]));
service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",ROOT,"services/fortune-rabbit/data/games.sqlite3")),registry],__rt.kw([]));
__rt.call(__rt.attr(service,"ensure_local_demo"),[],__rt.kw([]));
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),__rt.call(partial,[Handler],__rt.kw([["directory",__rt.call(__rt.b["str"],[CLIENT],__rt.kw([]))]]))],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
{const __t3=Array.from(__rt.iter(__rt.tuple([service,__rt.call(PGAdapter,[service],__rt.kw([]))])));__rt.setattr(http,"service",__t3[0]);__rt.setattr(http,"pg",__t3[1]);}
__rt.setattr(http,"auth",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/auth-metadata.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(http,"game_rule",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/game-rule.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(http,"service_id","fortune-rabbit");
return http;return null;});
