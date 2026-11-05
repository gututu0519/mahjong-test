// Migrated from server/services/sweet_bonanza_pop_demo.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "../core/service.js";
import * as __m1 from "../games/catalog.js";
import * as __m2 from "../adapters/pp/sweet_bonanza_pop.js";
import * as __m3 from "./olympus_preview.js";
import * as __m4 from "../transport/http.js";
const __file__=__rt.sourcePath("server/services/sweet_bonanza_pop_demo.py");
export let AssetHandler:any,CLIENT:any,GameService:any,Handler:any,PPAdapter:any,PlatformRoutes:any,ROOT:any,ServiceError:any,ThreadingHTTPServer:any,build_server:any,create_registry:any,json:any,logging:any,money:any,parse_qs:any,partial:any,urlencode:any,urlsplit:any;

json=__rt.modules["json"];
logging=__rt.modules["logging"];
partial=__rt.attr(__rt.modules["functools"],"partial");
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
parse_qs=__rt.attr(__rt.modules["urllib.parse"],"parse_qs");
urlencode=__rt.attr(__rt.modules["urllib.parse"],"urlencode");
urlsplit=__rt.attr(__rt.modules["urllib.parse"],"urlsplit");
ServiceError=__rt.attr(__rt.modules["server.core.contracts"],"ServiceError");
GameService=__rt.attr(__m0,"GameService");
create_registry=__rt.attr(__m1,"create_registry");
PPAdapter=__rt.attr(__m2,"PPAdapter");
money=__rt.attr(__m2,"money");
AssetHandler=__rt.attr(__m3,"Handler");
ROOT=__rt.attr(__m3,"ROOT");
CLIENT=__rt.bin("Div",ROOT,"clients/sweet-bonanza-pop");
PlatformRoutes=__rt.attr(__m4,"PlatformRoutes");
Handler=__rt.cls("Handler",[AssetHandler],{"client_root":CLIENT,"asset_base":"/hub-demo/common/v3/games-html5/games/vs/vs10swtbnz/","default_language":"en","_json":__rt.attr(PlatformRoutes,"_json"),"_response":__rt.attr(PlatformRoutes,"_response"),"_token":__rt.attr(PlatformRoutes,"_token"),"valid_session":__rt.fn("valid_session",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){if(__rt.truth(__rt.unary("Not",token))){return false;}
__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([]));
return true;return null;}),"new_session":__rt.fn("new_session",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){return __rt.item(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([])),"token");return null;}),"guard":__rt.fn("guard",{names:["self", "action"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,action){try{__rt.call(action,[],__rt.kw([]));}catch(__t1){if(__rt.matches(__t1,ServiceError)){let e=__t1;__rt.call(__rt.attr(self,"respond"),[__rt.attr(e,"status"),__rt.dict([["error",__rt.attr(e,"code")],["message",__rt.call(__rt.b["str"],[e],__rt.kw([]))]])],__rt.kw([]));}else if(__rt.matches(__t1,__rt.tuple([__rt.b["ValueError"],__rt.b["UnicodeError"],__rt.b["TypeError"],__rt.b["KeyError"]]))){__rt.call(__rt.attr(self,"respond"),[400,__rt.dict([["error","INVALID_REQUEST"]])],__rt.kw([]));}else if(__rt.matches(__t1,__rt.tuple([__rt.b["BrokenPipeError"],__rt.b["ConnectionResetError"]]))){}else if(__rt.matches(__t1,__rt.b["Exception"])){__rt.call(__rt.attr(logging,"exception"),["Sweet Bonanza POP request failed"],__rt.kw([]));
__rt.call(__rt.attr(self,"respond"),[500,__rt.dict([["error","INTERNAL_ERROR"]])],__rt.kw([]));}else{throw __t1;}}return null;}),"do_GET":__rt.fn("do_GET",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){__rt.call(__rt.attr(self,"guard"),[__rt.attr(self,"get")],__rt.kw([]));return null;}),"get":__rt.fn("get",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let balance,path,token;path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/hub-demo/ge/v3/reloadBalance.do"]))){token=__rt.item(__rt.call(__rt.attr(__rt.call(parse_qs,[__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"query")],__rt.kw([])),"get"),["mgckey",[""]],__rt.kw([])),0);
balance=__rt.item(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"wallet"),[token],__rt.kw([])),"balance_minor");
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.call(urlencode,[__rt.dict([["balance",__rt.call(money,[balance],__rt.kw([]))],["balance_cash",__rt.call(money,[balance],__rt.kw([]))],["balance_bonus","0.00"]])],__rt.kw([])),"encode"),[],__rt.kw([])),"text/plain; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.or_(()=>__rt.compare(["Eq"],[()=>path,()=>"/health"]),()=>__rt.call(__rt.attr(path,"startswith"),["/api/"],__rt.kw([]))))){return __rt.call(__rt.attr(PlatformRoutes,"_get"),[self],__rt.kw([]));}
return __rt.call(__rt.attr(AssetHandler,"do_GET"),[self],__rt.kw([]));return null;}),"serve_assets":__rt.fn("serve_assets",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){return __rt.call(__rt.attr(AssetHandler,"do_GET"),[self],__rt.kw([]));return null;}),"do_POST":__rt.fn("do_POST",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){__rt.call(__rt.attr(self,"guard"),[__rt.attr(self,"post")],__rt.kw([]));return null;}),"post":__rt.fn("post",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){let body,data,db,form,key,length,origin,path,payload,player,q,result,row,session;origin=__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Origin"],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>origin,()=>__rt.compare(["NotEq"],[()=>origin,()=>__rt.bin("Add","http://",__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Host",""],__rt.kw([])))])))){throw __rt.call(ServiceError,["ORIGIN_REJECTED","Cross-origin writes are not enabled.",403],__rt.kw([]));}
length=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Content-Length","0"],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>length,()=>16384])))){throw __rt.call(ServiceError,["BODY_TOO_LARGE","Request exceeds 16 KiB.",413],__rt.kw([]));}
body=__rt.call(__rt.attr(__rt.attr(self,"rfile"),"read"),[length],__rt.kw([]));
path=__rt.attr(__rt.call(urlsplit,[__rt.attr(self,"path")],__rt.kw([])),"path");
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/api/v1/sessions","/api/v1/games/sweet-bonanza-pop/spin"])]))){payload=__rt.call(__rt.attr(json,"loads"),[__rt.or_(()=>body,()=>Buffer.from([123, 125]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/api/v1/sessions"]))){return __rt.call(__rt.attr(self,"respond"),[201,__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]))],__rt.kw([]));}
result=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"spin"),[__rt.call(__rt.attr(self,"_token"),[],__rt.kw([])),"sweet-bonanza-pop",__rt.call(__rt.attr(__rt.attr(self,"headers"),"get"),["Idempotency-Key"],__rt.kw([])),__rt.call(__rt.attr(payload,"get"),["previous_sid"],__rt.kw([])),__rt.call(__rt.attr(payload,"get"),["bet",__rt.dict([])],__rt.kw([]))],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[200,result],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/api/v1/games/sweet-bonanza-pop/launch"]))){q=__rt.call(__rt.attr(json,"loads"),[__rt.or_(()=>body,()=>Buffer.from([123, 125]))],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[q,__rt.b["dict"]],__rt.kw([]))),()=>__rt.compare(["NotIn"],[()=>__rt.call(__rt.attr(q,"get"),["language","en"],__rt.kw([])),()=>__rt.tuple(["zh","en"])])))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
session=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"create_session"),[],__rt.kw([]));
__rt.call(__rt.attr(self,"respond"),[201,__rt.dict([["game_id","sweet-bonanza-pop"],["language","en"],["mode","generated"],["launch_url",__rt.bin("Add","/?",__rt.call(urlencode,[__rt.dict([["mock",1],["ops",__rt.item(session,"token")],["lang","en"],["symbol","vs10swtbnz"]])],__rt.kw([])))],[null,(()=>{let k,v;const __out:any[]=[];for(const __t2 of __rt.iter(__rt.call(__rt.attr(session,"items"),[],__rt.kw([])))){{const __t3=Array.from(__rt.iter(__t2));k=__t3[0];v=__t3[1];}if(__rt.truth(__rt.compare(["NotIn"],[()=>k,()=>__rt.tuple(["token","player_id"])]))){__out.push([k,v]);}}return __rt.dict(__out);})()]])],__rt.kw([]));
return null;}
form=__rt.call(parse_qs,[__rt.call(__rt.attr(body,"decode"),["utf-8"],__rt.kw([]))],__rt.kw([["keep_blank_values",true]]));
if(__rt.truth(__rt.compare(["Eq"],[()=>path,()=>"/hub-demo/ge/v3/gameService"]))){data=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"pp"),"handle"),[form],__rt.kw([]));
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr(__rt.call(__rt.attr("&","join"),[(function*(){let k,v;for(const __t4 of __rt.iter(__rt.call(__rt.attr(data,"items"),[],__rt.kw([])))){{const __t5=Array.from(__rt.iter(__t4));k=__t5[0];v=__t5[1];}yield __rt.bin("Add",__rt.bin("Add",k,"="),__rt.call(__rt.b["str"],[v],__rt.kw([])));}})()],__rt.kw([])),"encode"),[],__rt.kw([])),"text/plain; charset=utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>path,()=>__rt.tuple(["/hub-demo/saveSettings.do","/hub-demo/ge/v3/saveSettings.do"])]))){if(__rt.truth(__rt.call(__rt.b["any"],[(function*(){let v;for(const __t6 of __rt.iter(__rt.call(__rt.attr(form,"values"),[],__rt.kw([])))){v=__t6;yield __rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[v],__rt.kw([])),()=>1]);}})()],__rt.kw([])))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
{const __t7=__rt.context(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"connection"),[true],__rt.kw([])));let __t9=false;db=__t7.value;try{player=__rt.call(__rt.attr(__rt.attr(__rt.attr(__rt.attr(self,"server"),"service"),"sessions"),"_player"),[db,__rt.item(__rt.call(__rt.attr(form,"get"),["mgckey",[""]],__rt.kw([])),0)],__rt.kw([]));
key=__rt.item(__rt.call(__rt.attr(form,"get"),["id",["game"]],__rt.kw([])),0);
if(__rt.truth(__rt.compare(["In"],[()=>"settings",()=>form]))){__rt.call(__rt.attr(db,"execute"),["INSERT OR REPLACE INTO pp_settings VALUES (?,?,?)",__rt.tuple([__rt.item(player,"id"),key,__rt.item(__rt.item(form,"settings"),0)])],__rt.kw([]));}
row=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT value FROM pp_settings WHERE player_id=? AND name=?",__rt.tuple([__rt.item(player,"id"),key])],__rt.kw([])),"fetchone"),[],__rt.kw([]));}catch(__t8){__t9=true;if(!__t7.exit(__t8))throw __t8;}finally{if(!__t9)__t7.exit(null);}}
return __rt.call(__rt.attr(self,"respond"),[200,__rt.call(__rt.attr((__rt.truth(row)?__rt.item(row,0):""),"encode"),[],__rt.kw([])),"text/plain; charset=utf-8"],__rt.kw([]));}
throw __rt.call(ServiceError,["NOT_FOUND","Unknown endpoint.",404],__rt.kw([]));return null;})});
build_server=__rt.fn("build_server",{names:["port", "database", "config"],kwonly:[],defaults:{"port":8086,"database":null,"config":null},vararg:null,kwarg:null},function(port,database,config){let db,http,initial,service;config=__rt.or_(()=>config,()=>__rt.bin("Div",ROOT,"services/sweet-bonanza-pop/config/sweet-bonanza-pop.json"));
service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",ROOT,"services/sweet-bonanza-pop/data/games.sqlite3")),__rt.call(create_registry,[["sweet-bonanza-pop"],__rt.dict([["sweet-bonanza-pop",config]])],__rt.kw([]))],__rt.kw([]));
{const __t10=__rt.context(__rt.call(__rt.attr(service,"connection"),[true],__rt.kw([])));let __t12=false;db=__t10.value;try{__rt.call(__rt.attr(db,"execute"),["CREATE TABLE IF NOT EXISTS pp_settings (player_id TEXT NOT NULL REFERENCES players(id), name TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(player_id,name))"],__rt.kw([]));}catch(__t11){__t12=true;if(!__t10.exit(__t11))throw __t11;}finally{if(!__t12)__t10.exit(null);}}
initial=(()=>{let k,v;const __out:any[]=[];for(const __t13 of __rt.iter(__rt.call(__rt.attr(__rt.call(parse_qs,[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/init.txt"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])),"items"),[],__rt.kw([])))){{const __t14=Array.from(__rt.iter(__t13));k=__t14[0];v=__t14[1];}__out.push([k,__rt.item(v,0)]);}return __rt.dict(__out);})();
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),__rt.call(partial,[Handler],__rt.kw([["directory",__rt.call(__rt.b["str"],[CLIENT],__rt.kw([]))]]))],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
{const __t15=Array.from(__rt.iter(__rt.tuple([service,__rt.call(PPAdapter,[service,initial],__rt.kw([]))])));__rt.setattr(http,"service",__t15[0]);__rt.setattr(http,"pp",__t15[1]);}
{const __t16=Array.from(__rt.iter(__rt.tuple([true,"sweet-bonanza-pop"])));__rt.setattr(http,"generated",__t16[0]);__rt.setattr(http,"service_id",__t16[1]);}
return http;return null;});
