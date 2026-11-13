// Migrated from py/services/buffalo_demo.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "../core/service.js";
import * as __m1 from "../games/catalog.js";
import * as __m2 from "../adapters/pg/buffalo_win.js";
import * as __m3 from "./buffalo_preview.js";
import * as __m4 from "../transport/http.js";
const __file__=__rt.sourcePath("py/services/buffalo_demo.py");
export let AssetHandler:any,CLIENT:any,GameService:any,Handler:any,PGAdapter:any,PlatformRoutes:any,ROOT:any,ServiceError:any,SimpleHTTPRequestHandler:any,ThreadingHTTPServer:any,build_server:any,copy:any,create_registry:any,json:any,main:any,parse_qs:any,partial:any,sys:any,urlencode:any;

copy=__rt.modules["copy"];
json=__rt.modules["json"];
partial=__rt.attr(__rt.modules["functools"],"partial");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
SimpleHTTPRequestHandler=__rt.attr(__rt.modules["http.server"],"SimpleHTTPRequestHandler");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
GameService=__rt.attr(__m0,"GameService");
create_registry=__rt.attr(__m1,"create_registry");
PGAdapter=__rt.attr(__m2,"PGAdapter");
AssetHandler=__rt.attr(__m3,"Handler");
ROOT=__rt.attr(__m3,"ROOT");
CLIENT=__rt.attr(__m3,"CLIENT");
PlatformRoutes=__rt.attr(__m4,"PlatformRoutes");
Handler=__rt.cls("Handler",[AssetHandler],{"bootstrap_script":"local-auth-bootstrap.js","_get":__rt.attr(PlatformRoutes,"_get"),"_post":__rt.attr(PlatformRoutes,"_post"),"serve_assets":__rt.fn("serve_assets",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){__rt.call(__rt.attr(SimpleHTTPRequestHandler,"do_GET"),[self],__rt.kw([]));return null;}),"launch_game":__rt.fn("launch_game",{names:["self", "game_id", "language"],kwonly:[],defaults:{"language":"zh"},vararg:null,kwarg:null},function(self,game_id,language){let query,session;__rt.call(__rt.attr(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"registry"),"get"),[game_id],__rt.kw([]));
if(__rt.truth(__rt.compare(["NotIn"],[()=>language,()=>__rt.tuple(["zh","en"])]))){throw __rt.call(ServiceError,["LANGUAGE_INVALID","Supported languages: zh, en."],__rt.kw([]));}
session=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]));
query=__rt.call(urlencode,[__rt.dict([["mock",1],["l",language],["ops",__rt.item(session,"token")],["btt",2]])],__rt.kw([]));
return __rt.dict([["game_id",game_id],["language",language],["launch_url",__rt.bin("Add","/?",query)],["mode","generated"],["expires_at",__rt.item(session,"expires_at")],["balance_minor",__rt.item(session,"balance_minor")],["currency","DEMO"],["minor_unit",100]]);return null;}),"compatibility_post":__rt.fn("compatibility_post",{names:["self", "path", "body"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path,body){let data,form,name,token,wallet;form=__rt.call(parse_qs,[__rt.call(__rt.attr(body,"decode"),["utf-8"],__rt.kw([]))],__rt.kw([["keep_blank_values",true]]));
token=__rt.or_(()=>__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["X-Local-Game-Session"],__rt.kw([])),()=>__rt.item(__rt.call(__rt.attr(form,"get"),["atk",[null]],__rt.kw([])),0));
wallet=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/web-api/auth/session/v2/verifySession","/web-api/auth/session/v2/verifyOperatorPlayerSession"])]))){data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(__rt.attr(self,"server"),"auth")],__rt.kw([]));
__rt.call(__rt.attr(data,"update"),[],__rt.kw([["tk",token],["pid",__rt.item(wallet,"player_id")],["pcd",__rt.item(wallet,"player_id")],["nkn","Local demo"],["ioph","local-demo"],["oj",__rt.dict([["jid",1]])],["bl",__rt.bin("Div",__rt.item(wallet,"balance_minor"),100)]]));
__rt.setitem(__rt.item(data,"uiogc"),"bf",1);
return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",data],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/game-api/buffalo-win/v2/GameInfo/Get"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pg"),"game_info"),[token],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/game-api/buffalo-win/v2/Spin"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pg"),"spin"),[body,token],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameWallet/Get"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pg"),"wallet"),[token],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameName/Get"]))){name=(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(__rt.call(__rt.attr(form,"get"),["lang",["zh"]],__rt.kw([])),0),()=>"en"]))?"Buffalo Win":"\u7f8e\u6d32\u91ce\u725b");
return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",__rt.dict([["108",name]])],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameRule/Get"]))){if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.item(__rt.call(__rt.attr(form,"get"),["gid",["108"]],__rt.kw([])),0),()=>"108"]))){throw __rt.call(ServiceError,["GAME_NOT_FOUND","Unknown game.",404],__rt.kw([]));}
return __rt.call(__rt.attr(self,"_json"),[200,__rt.attr(__rt.attr(self,"server"),"game_rule")],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",[]],["err",null]])],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/ServerManager/RefreshWallet"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["dt",null],["err",null]])],__rt.kw([]));}
throw __rt.call(ServiceError,["NOT_IMPLEMENTED","This local endpoint is not implemented.",501],__rt.kw([]));return null;})});
build_server=__rt.fn("build_server",{names:["port", "database", "config"],kwonly:[],defaults:{"port":8083,"database":null,"config":null},vararg:null,kwarg:null},function(port,database,config){let http,registry,service;config=__rt.or_(()=>config,()=>__rt.bin("Div",ROOT,"services/buffalo-win/config/buffalo-win.json"));
registry=__rt.call(create_registry,[["buffalo-win"],__rt.dict([["buffalo-win",config]])],__rt.kw([]));
service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",ROOT,"services/buffalo-win/data/games.sqlite3")),registry],__rt.kw([]));
__rt.call(__rt.attr(service,"ensure_local_demo"),[],__rt.kw([]));
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),__rt.call(partial,[Handler],__rt.kw([["directory",__rt.call(__rt.b["str"],[CLIENT],__rt.kw([]))]]))],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
{const __t1=Array.from(__rt.iter(__rt.tuple([service,__rt.call(PGAdapter,[service],__rt.kw([]))])));__rt.setattr(http,"service",__t1[0]);__rt.setattr(http,"pg",__t1[1]);}
__rt.setattr(http,"auth",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/auth-metadata.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(http,"game_rule",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/game-rule.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(http,"service_id","buffalo-win");
return http;return null;});
