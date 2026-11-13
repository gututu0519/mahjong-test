// Migrated from py/services/local_demo.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "../core/service.js";
import * as __m1 from "../games/catalog.js";
import * as __m2 from "../adapters/pg/mahjong_ways2.js";
import * as __m3 from "../transport/http.js";
import * as __m4 from "../paths.js";
import * as __m5 from "./mahjong_assets.js";
import * as __m6 from "../adapters/pg/mahjong_metadata.js";
const __file__=__rt.sourcePath("py/services/local_demo.py");
export let CLIENT:any,GameService:any,Handler:any,MahjongAssetHandler:any,PGAdapter:any,Path:any,PlatformRoutes:any,ROOT:any,Request:any,ServiceError:any,ThreadingHTTPServer:any,URLError:any,argparse:any,build_server:any,create_registry:any,get_game_names:any,get_game_rule:any,json:any,main:any,parse_qs:any,partial:any,urlencode:any,urlopen:any,urlsplit:any,verify_operator_session:any;

argparse=__rt.modules["argparse"];
json=__rt.modules["json"];
partial=__rt.attr(__rt.modules["functools"],"partial");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
Request=__rt.attr(__rt.modules["urllib.request"],"Request");
urlopen=__rt.attr(__rt.modules["urllib.request"],"urlopen");
URLError=__rt.attr(__rt.modules["urllib.error"],"URLError");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
GameService=__rt.attr(__m0,"GameService");
create_registry=__rt.attr(__m1,"create_registry");
PGAdapter=__rt.attr(__m2,"PGAdapter");
PlatformRoutes=__rt.attr(__m3,"PlatformRoutes");
ROOT=__rt.attr(__m4,"ROOT");
CLIENT=__rt.attr(__m4,"MAHJONG_CLIENT");
MahjongAssetHandler=__rt.attr(__m5,"MahjongAssetHandler");
verify_operator_session=__rt.attr(__m6,"verify_operator_session");
get_game_names=__rt.attr(__m6,"get_game_names");
get_game_rule=__rt.attr(__m6,"get_game_rule");
Handler=__rt.cls("Handler",[PlatformRoutes,MahjongAssetHandler],{"_get":__rt.fn("_get",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path"),()=>"/api/v1/demo/games"]))){return __rt.call(__rt.attr(self,"_json"),[200,__rt.dict([["games",[__rt.dict([["id","mahjong-ways2"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","wild-bandito"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","captains-bounty"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","fortune-rabbit"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","buffalo-win"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","gates-of-olympus"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","big-bass-bonanza"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","sweet-bonanza-pop"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","super-ace"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","money-pot-deluxe"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","tower-run-treasure-steps"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","great-game-serengeti"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","dr-zappo"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","le-vampire"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","wicked-grin"],["mode","playable"],["languages",["zh","en"]]]),__rt.dict([["id","roma-x-10000"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","3-billion-vaults"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","jokers-fortune-winx"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]]),__rt.dict([["id","fortune-gems2"],["mode","playable"],["languages",["zh","en"]],["client_language","en"]])]]])],__rt.kw([]));}
return __rt.call(__rt.attr(__rt.super_(Handler,self),"_get"),[],__rt.kw([]));return null;}),"serve_assets":__rt.fn("serve_assets",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let content_type,demo_files,name,path;path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
demo_files=__rt.dict([["/demo",__rt.tuple(["index.html","text/html; charset=utf-8"])],["/demo/",__rt.tuple(["index.html","text/html; charset=utf-8"])],["/demo/style.css",__rt.tuple(["style.css","text/css; charset=utf-8"])],["/demo/i18n.js",__rt.tuple(["i18n.js","application/javascript; charset=utf-8"])],["/demo/app.js",__rt.tuple(["app.js","application/javascript; charset=utf-8"])],["/demo/mahjong-cover.jpg",__rt.tuple(["mahjong-cover.jpg","image/jpeg"])],["/demo/olympus-cover.webp",__rt.tuple(["olympus-cover.webp","image/webp"])],["/demo/big-bass-cover.webp",__rt.tuple(["big-bass-cover.webp","image/webp"])],["/demo/sweet-pop-cover.webp",__rt.tuple(["sweet-pop-cover.webp","image/webp"])],["/demo/money-pot-deluxe-cover.png",__rt.tuple(["money-pot-deluxe-cover.png","image/png"])],["/demo/wild-bandito-cover.webp",__rt.tuple(["wild-bandito-cover.webp","image/webp"])],["/demo/captains-bounty-cover.webp",__rt.tuple(["captains-bounty-cover.webp","image/webp"])],["/demo/fortune-rabbit-cover.webp",__rt.tuple(["fortune-rabbit-cover.webp","image/webp"])],["/demo/tower-run-cover.webp",__rt.tuple(["tower-run-cover.webp","image/webp"])],["/demo/great-game-serengeti-cover.jpg",__rt.tuple(["great-game-serengeti-cover.jpg","image/jpeg"])],["/demo/dr-zappo-cover.jpg",__rt.tuple(["dr-zappo-cover.jpg","image/jpeg"])],["/demo/le-vampire-cover.jpg",__rt.tuple(["le-vampire-cover.jpg","image/jpeg"])],["/demo/wicked-grin-cover.jpg",__rt.tuple(["wicked-grin-cover.jpg","image/jpeg"])],["/demo/roma-x-10000-cover.png",__rt.tuple(["roma-x-10000-cover.png","image/png"])],["/demo/3-billion-vaults-cover.webp",__rt.tuple(["3-billion-vaults-cover.webp","image/webp"])],["/demo/jokers-fortune-winx-cover.webp",__rt.tuple(["jokers-fortune-winx-cover.webp","image/webp"])],["/demo/fortune-gems2-cover.webp",__rt.tuple(["fortune-gems2-cover.webp","image/webp"])],["/demo/super-ace-cover.png",__rt.tuple(["super-ace-cover.png","image/png"])],["/demo/buffalo-cover.jpg",__rt.tuple(["buffalo-cover.jpg","image/jpeg"])]]);
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>demo_files]))){{const __t1=Array.from(__rt.iter(__rt.item(demo_files,path)));name=__t1[0];content_type=__t1[1];}
__rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(__rt.bin("Div",__rt.bin("Div",ROOT,"demo"),name),"read_bytes"),[],__rt.kw([])),content_type],__rt.kw([]));
return null;}
__rt.call(__rt.attr(MahjongAssetHandler,"do_GET"),[self],__rt.kw([]));return null;}),"launch_game":__rt.fn("launch_game",{names:["self", "game_id", "language"],kwonly:[],defaults:{"language":"zh"},vararg:null,kwarg:null},function(self,game_id,language){let link,origin,query,request,response,result,session;if(__rt.truth(__rt.compare(["In"],[()=>game_id,()=>__rt.tuple(["captains-bounty","fortune-rabbit","wild-bandito","buffalo-win","gates-of-olympus","sweet-bonanza-pop","big-bass-bonanza","super-ace","fortune-gems2","jokers-fortune-winx","3-billion-vaults","money-pot-deluxe","roma-x-10000","wicked-grin","le-vampire","dr-zappo","great-game-serengeti","tower-run-treasure-steps"])]))){if(__rt.truth(__rt.compare(["NotIn"],[()=>language,()=>__rt.tuple(["zh","en"])]))){throw __rt.call(ServiceError,["LANGUAGE_INVALID","Supported languages: zh, en."],__rt.kw([]));}
origin=__rt.bin("Add","http://127.0.0.1:",__rt.item(__rt.dict([["captains-bounty","8102"],["fortune-rabbit","8101"],["wild-bandito","8100"],["buffalo-win","8083"],["gates-of-olympus","8085"],["sweet-bonanza-pop","8086"],["big-bass-bonanza","8087"],["super-ace","8088"],["fortune-gems2","8089"],["jokers-fortune-winx","8091"],["3-billion-vaults","8092"],["money-pot-deluxe","8093"],["roma-x-10000","8094"],["wicked-grin","8095"],["le-vampire","8096"],["dr-zappo","8097"],["great-game-serengeti","8098"],["tower-run-treasure-steps","8099"]]),game_id));
request=__rt.call(Request,[__rt.bin("Add",__rt.bin("Add",__rt.bin("Add",origin,"/api/v1/games/"),game_id),"/launch")],__rt.kw([["data",__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[__rt.dict([["language",language]])],__rt.kw([])),"encode"),[],__rt.kw([]))],["headers",__rt.dict([["Content-Type","application/json"]])],["method","POST"]]));
try{{const __t3=__rt.context(__rt.call(urlopen,[request],__rt.kw([["timeout",5]])));let __t5=false;response=__t3.value;try{result=__rt.call(__rt.attr(json,"load"),[response],__rt.kw([]));}catch(__t4){__t5=true;if(!__t3.exit(__t4))throw __t4;}finally{if(!__t5)__t3.exit(null);}}
link=__rt.call(urlsplit,[__rt.item(result,"launch_url")],__rt.kw([]));
query=__rt.call(parse_qs,[__rt.attr(link,"query")],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.attr(link,"scheme"),()=>__rt.attr(link,"netloc"),()=>__rt.compare(["NotEq"],[()=>__rt.attr(link,"path"),()=>"/"]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(query,"get"),["mock"],__rt.kw([])),()=>["1"]]),()=>__rt.unary("Not",__rt.call(__rt.attr(query,"get"),["ops"],__rt.kw([])))))){throw __rt.call(__rt.b["ValueError"],["Invalid game link"],__rt.kw([]));}
__rt.setitem(result,"launch_url",__rt.bin("Add",origin,__rt.item(result,"launch_url")));
return result;}catch(__t2){if(__rt.matches(__t2,__rt.tuple([URLError,__rt.b["OSError"],__rt.b["ValueError"],__rt.b["KeyError"]]))){throw __rt.call(ServiceError,["GAME_UNAVAILABLE",__rt.bin("Add",game_id," service is unavailable."),503],__rt.kw([]));}else{throw __t2;}}}
__rt.call(__rt.attr(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"registry"),"get"),[game_id],__rt.kw([]));
if(__rt.truth(__rt.compare(["NotEq"],[()=>game_id,()=>"mahjong-ways2"]))){throw __rt.call(ServiceError,["NOT_FOUND","This game has no web client.",404],__rt.kw([]));}
if(__rt.truth(__rt.compare(["NotIn"],[()=>language,()=>__rt.tuple(["zh","en"])]))){throw __rt.call(ServiceError,["LANGUAGE_INVALID","Supported languages: zh, en."],__rt.kw([]));}
session=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]));
query=__rt.call(urlencode,[__rt.dict([["mock","1"],["btt","1"],["ot","local-demo"],["ops",__rt.item(session,"token")],["l",language]])],__rt.kw([]));
return __rt.dict([["game_id",game_id],["launch_url",__rt.bin("Add","/?",query)],["language",language],["expires_at",__rt.item(session,"expires_at")],["balance_minor",__rt.item(session,"balance_minor")],["currency",__rt.item(session,"currency")],["minor_unit",__rt.item(session,"minor_unit")]]);return null;}),"compatibility_post":__rt.fn("compatibility_post",{names:["self", "path", "body"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path,body){let adapter,form,result,service,status,token,wallet;service=__rt.attr(__rt.attr(self,"server"),"service");
adapter=__rt.attr(__rt.attr(self,"server"),"pg");
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/game-api/74/v4/Spin","/game-api/mahjong-ways2/v4/Spin"])]))){__rt.call(__rt.attr(self,"_response"),[200,__rt.call(__rt.attr(adapter,"spin"),[body],__rt.kw([])),"application/octet-stream"],__rt.kw([]));
return null;}
form=__rt.call(parse_qs,[__rt.call(__rt.attr(body,"decode"),[],__rt.kw([]))],__rt.kw([["keep_blank_values",true]]));
token=__rt.item(__rt.call(__rt.attr(form,"get"),["atk",[null]],__rt.kw([])),0);
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/auth/session/v2/verifyOperatorPlayerSession"]))){token=__rt.item(__rt.call(__rt.attr(form,"get"),["os",[null]],__rt.kw([])),0);
wallet=__rt.call(__rt.attr(service,"wallet"),[token],__rt.kw([]));
{const __t6=Array.from(__rt.iter(__rt.call(verify_operator_session,[__rt.dict([[null,form],["os",["local-demo-session"]]])],__rt.kw([]))));status=__t6[0];result=__t6[1];}
if(__rt.truth(__rt.compare(["Eq"],[()=>status,()=>200]))){__rt.call(__rt.attr(__rt.item(result,"dt"),"update"),[],__rt.kw([["tk",token],["bl",__rt.bin("Div",__rt.item(wallet,"balance_minor"),100)],["pid",__rt.item(wallet,"player_id")],["pcd",__rt.item(wallet,"player_id")]]));}
__rt.call(__rt.attr(self,"_json"),[status,result],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/game-api/74/v4/GameInfo/Get"]))){if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["btt"],__rt.kw([])),()=>["1"]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["pf"],__rt.kw([])),()=>["1"]])))){throw __rt.call(ServiceError,["SESSION_INVALID","Only the local demo is supported."],__rt.kw([]));}
__rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(adapter,"game_info"),[token],__rt.kw([]))],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameWallet/Get"]))){__rt.call(__rt.attr(self,"_json"),[200,__rt.call(__rt.attr(adapter,"wallet"),[token],__rt.kw([]))],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameName/Get"]))){__rt.call(__rt.attr(service,"wallet"),[token],__rt.kw([]));
{const __t7=Array.from(__rt.iter(__rt.call(get_game_names,[__rt.dict([[null,form],["atk",["local-demo-session"]]])],__rt.kw([]))));status=__t7[0];result=__t7[1];}
__rt.call(__rt.attr(self,"_json"),[status,result],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/web-api/game-proxy/v2/GameRule/Get"]))){__rt.call(__rt.attr(service,"wallet"),[token],__rt.kw([]));
{const __t8=Array.from(__rt.iter(__rt.call(get_game_rule,[__rt.dict([[null,form],["atk",["local-demo-session"]]])],__rt.kw([]))));status=__t8[0];result=__t8[1];}
__rt.call(__rt.attr(self,"_json"),[status,result],__rt.kw([]));}else{throw __rt.call(ServiceError,["NOT_IMPLEMENTED","This compatibility endpoint is not implemented.",501],__rt.kw([]));}}}}}return null;}),"list_directory":__rt.fn("list_directory",{names:["self", "path"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;return null;}),"send_head":__rt.fn("send_head",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let path,relative;path=__rt.call(__rt.attr(__rt.call(Path,[__rt.call(__rt.attr(self,"translate_path"),[__rt.attr(self,"path")],__rt.kw([]))],__rt.kw([])),"resolve"),[],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.attr(path,"is_relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([]))))){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;}
relative=__rt.call(__rt.attr(path,"relative_to"),[__rt.call(__rt.attr(CLIENT,"resolve"),[],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.compare(["In"],[()=>"diagnostics",()=>__rt.attr(relative,"parts")]),()=>__rt.compare(["In"],[()=>"fixtures",()=>__rt.attr(relative,"parts")]),()=>__rt.compare(["In"],[()=>__rt.call(__rt.attr(__rt.attr(path,"suffix"),"lower"),[],__rt.kw([])),()=>__rt.tuple([".py",".pyc",".cjs",".bat",".har",".txt"])])))){__rt.call(__rt.attr(self,"send_error"),[404],__rt.kw([]));
return null;}
return __rt.call(__rt.attr(__rt.super_(Handler,self),"send_head"),[],__rt.kw([]));return null;})});
build_server=__rt.fn("build_server",{names:["port", "database", "config"],kwonly:[],defaults:{"port":8080,"database":null,"config":null},vararg:null,kwarg:null},function(port,database,config){let http,registry,service;config=__rt.or_(()=>config,()=>__rt.bin("Div",ROOT,"services/mahjong-ways2/config/mahjong-ways2.json"));
registry=__rt.call(create_registry,[["mahjong-ways2"]],__rt.kw([["configs",(__rt.truth(config)?__rt.dict([["mahjong-ways2",config]]):null)]]));
service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",ROOT,"services/mahjong-ways2/data/games.sqlite3")),registry],__rt.kw([]));
__rt.call(__rt.attr(service,"ensure_local_demo"),[],__rt.kw([]));
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),__rt.call(partial,[Handler],__rt.kw([["directory",__rt.call(__rt.b["str"],[CLIENT],__rt.kw([]))]]))],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
__rt.setattr(http,"service",service);
__rt.setattr(http,"pg",__rt.call(PGAdapter,[service],__rt.kw([])));
return http;return null;});
main=__rt.fn("main",{names:[],kwonly:[],defaults:{},vararg:null,kwarg:null},function(){let args,http,parser;parser=__rt.call(__rt.attr(argparse,"ArgumentParser"),[],__rt.kw([["description","Local multi-game service with generated outcomes"]]));
__rt.call(__rt.attr(parser,"add_argument"),["--port"],__rt.kw([["type",__rt.b["int"]],["default",8080]]));
__rt.call(__rt.attr(parser,"add_argument"),["--database"],__rt.kw([["type",Path]]));
__rt.call(__rt.attr(parser,"add_argument"),["--config"],__rt.kw([["type",Path],["help","Mahjong probability configuration"]]));
args=__rt.call(__rt.attr(parser,"parse_args"),[],__rt.kw([]));
{const __t9=__rt.context(__rt.call(build_server,[__rt.attr(args,"port"),__rt.attr(args,"database"),__rt.attr(args,"config")],__rt.kw([])));let __t11=false;http=__t9.value;try{__rt.call(__rt.b["print"],[("Generated game server: http://localhost:"+__rt.format(__rt.attr(http,"server_port"),"",-1)+"/?mock=1")],__rt.kw([["flush",true]]));
__rt.call(__rt.b["print"],[("Platform API: http://localhost:"+__rt.format(__rt.attr(http,"server_port"),"",-1)+"/api/v1/games")],__rt.kw([["flush",true]]));
try{__rt.call(__rt.attr(http,"serve_forever"),[],__rt.kw([]));}catch(__t12){if(__rt.matches(__t12,__rt.b["KeyboardInterrupt"])){}else{throw __t12;}}}catch(__t10){__t11=true;if(!__t9.exit(__t10))throw __t10;}finally{if(!__t11)__t9.exit(null);}}return null;});
