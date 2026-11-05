// Migrated from server/services/game_api.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "../core/service.js";
import * as __m1 from "../games/catalog.js";
import * as __m2 from "../transport/http.js";
const __file__=__rt.sourcePath("server/services/game_api.py");
export let APIHandler:any,GameService:any,Path:any,ROOT:any,ThreadingHTTPServer:any,argparse:any,build_server:any,create_registry:any,main:any;

argparse=__rt.modules["argparse"];
ThreadingHTTPServer=__rt.attr(__rt.modules["http.server"],"ThreadingHTTPServer");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
GameService=__rt.attr(__m0,"GameService");
create_registry=__rt.attr(__m1,"create_registry");
APIHandler=__rt.attr(__m2,"APIHandler");
ROOT=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),2);
build_server=__rt.fn("build_server",{names:["port", "database", "game_ids", "configs"],kwonly:[],defaults:{"port":8082,"database":null,"game_ids":null,"configs":null},vararg:null,kwarg:null},function(port,database,game_ids,configs){let http,registry,service;if(__rt.truth(__rt.compare(["Is"],[()=>game_ids,()=>null]))){game_ids=["mahjong-ways2"];}
if(__rt.truth(__rt.compare(["Is"],[()=>configs,()=>null]))){configs=(()=>{let game_id;const __out:any[]=[];for(const __t1 of __rt.iter(game_ids)){game_id=__t1;__out.push([game_id,__rt.bin("Div",__rt.bin("Div",ROOT,"services/game-api/config"),__rt.bin("Add",game_id,".json"))]);}return __rt.dict(__out);})();}
registry=__rt.call(create_registry,[game_ids,configs],__rt.kw([]));
service=__rt.call(GameService,[__rt.or_(()=>database,()=>__rt.bin("Div",ROOT,"services/game-api/data/games.sqlite3")),registry],__rt.kw([]));
http=__rt.call(ThreadingHTTPServer,[__rt.tuple(["127.0.0.1",port]),APIHandler],__rt.kw([]));
__rt.setattr(http,"daemon_threads",true);
__rt.setattr(http,"service",service);
return http;return null;});
main=__rt.fn("main",{names:[],kwonly:[],defaults:{},vararg:null,kwarg:null},function(){let args,http,parser;parser=__rt.call(__rt.attr(argparse,"ArgumentParser"),[],__rt.kw([["description","Independent JSON game API service"]]));
__rt.call(__rt.attr(parser,"add_argument"),["--port"],__rt.kw([["type",__rt.b["int"]],["default",8082]]));
__rt.call(__rt.attr(parser,"add_argument"),["--database"],__rt.kw([["type",Path]]));
__rt.call(__rt.attr(parser,"add_argument"),["--games"],__rt.kw([["nargs","+"],["help","Game IDs from the explicit catalog"]]));
args=__rt.call(__rt.attr(parser,"parse_args"),[],__rt.kw([]));
{const __t2=__rt.context(__rt.call(build_server,[__rt.attr(args,"port"),__rt.attr(args,"database"),__rt.attr(args,"games")],__rt.kw([])));let __t4=false;http=__t2.value;try{__rt.call(__rt.b["print"],[("Game API: http://localhost:"+__rt.format(__rt.attr(http,"server_port"),"",-1)+"/api/v1/games")],__rt.kw([["flush",true]]));
try{__rt.call(__rt.attr(http,"serve_forever"),[],__rt.kw([]));}catch(__t5){if(__rt.matches(__t5,__rt.b["KeyboardInterrupt"])){}else{throw __t5;}}}catch(__t3){__t4=true;if(!__t2.exit(__t3))throw __t3;}finally{if(!__t4)__t2.exit(null);}}return null;});
