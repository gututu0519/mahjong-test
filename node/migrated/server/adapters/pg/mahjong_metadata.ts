// Migrated from server/adapters/pg/mahjong_metadata.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
import * as __m0 from "../../paths.js";
const __file__=__rt.sourcePath("server/adapters/pg/mahjong_metadata.py");
export let AUTH_PATH:any,GAME_INFO_PATH:any,GAME_NAME_PATH:any,GAME_RULE_PATH:any,MAHJONG_CLIENT:any,OPERATOR_TOKEN:any,SESSION_TOKEN:any,get_game_info:any,get_game_names:any,get_game_rule:any,json:any,verify_operator_session:any;

json=__rt.modules["json"];
MAHJONG_CLIENT=__rt.attr(__m0,"MAHJONG_CLIENT");
OPERATOR_TOKEN="local-demo";
SESSION_TOKEN="local-demo-session";
AUTH_PATH="/web-api/auth/session/v2/verifyOperatorPlayerSession";
GAME_NAME_PATH="/web-api/game-proxy/v2/GameName/Get";
GAME_INFO_PATH="/game-api/74/v4/GameInfo/Get";
GAME_RULE_PATH="/web-api/game-proxy/v2/GameRule/Get";
get_game_rule=__rt.fn("get_game_rule",{names:["form"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(form){let fixture;if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["atk"],__rt.kw([])),()=>[SESSION_TOKEN]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["gid"],__rt.kw([])),()=>["74"]])))){return __rt.tuple([400,__rt.dict([["dt",null],["err",__rt.dict([["cd","LOCAL_SESSION_INVALID"],["msg","Only the synthetic local session is supported."]])]])]);}
fixture=__rt.bin("Div",__rt.bin("Div",MAHJONG_CLIENT,"fixtures"),"game-rule.json");
return __rt.tuple([200,__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(fixture,"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]))]);return null;});
get_game_info=__rt.fn("get_game_info",{names:["form"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(form){let fixture;if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["atk"],__rt.kw([])),()=>[SESSION_TOKEN]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["btt"],__rt.kw([])),()=>["1"]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["pf"],__rt.kw([])),()=>["1"]])))){return __rt.tuple([400,__rt.dict([["dt",null],["err",__rt.dict([["cd","LOCAL_SESSION_INVALID"],["msg","Only the synthetic local session is supported."]])]])]);}
fixture=__rt.bin("Div",__rt.bin("Div",MAHJONG_CLIENT,"fixtures"),"game-info.json");
return __rt.tuple([200,__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(fixture,"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]))]);return null;});
get_game_names=__rt.fn("get_game_names",{names:["form"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(form){let fixture;if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["atk"],__rt.kw([])),()=>[SESSION_TOKEN]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["gid"],__rt.kw([])),()=>["74"]])))){return __rt.tuple([400,__rt.dict([["dt",null],["err",__rt.dict([["cd","LOCAL_SESSION_INVALID"],["msg","Only the synthetic local session is supported."]])]])]);}
fixture=__rt.bin("Div",__rt.bin("Div",MAHJONG_CLIENT,"fixtures"),"game-names.en.json");
return __rt.tuple([200,__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(fixture,"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]))]);return null;});
verify_operator_session=__rt.fn("verify_operator_session",{names:["form"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(form){let flags;if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["otk"],__rt.kw([])),()=>[OPERATOR_TOKEN]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["os"],__rt.kw([])),()=>[SESSION_TOKEN]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["gi"],__rt.kw([])),()=>["74"]]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(form,"get"),["btt"],__rt.kw([])),()=>["1"]])))){return __rt.tuple([400,__rt.dict([["dt",null],["err",__rt.dict([["cd","LOCAL_SESSION_INVALID"],["msg","Only the synthetic local session is supported."]])]])]);}
flags=__rt.call(__rt.attr(__rt.b["dict"],"fromkeys"),[__rt.call(__rt.attr("as bf bu cl et hd il ir mr np rp sp vc we gec gsc hnp igv pwr rcf std swf tsn grtp phtr smpo bfbli bfbsi swfbli swfbsi","split"),[],__rt.kw([])),0],__rt.kw([]));
__rt.call(__rt.attr(flags,"update"),[__rt.call(__rt.attr(__rt.b["dict"],"fromkeys"),[__rt.call(__rt.attr("bb gc hn ts asc hwl ign ivs sbb","split"),[],__rt.kw([])),1],__rt.kw([]))],__rt.kw([]));
__rt.setitem(flags,"cbu",0);
return __rt.tuple([200,__rt.dict([["dt",__rt.dict([["cc","AUD"],["cs",""],["ec",[]],["gm",[__rt.dict([["st",1],["gid",74],["mxe",5000],["rtp",__rt.dict([["df",__rt.dict([["max",__rt.float(96.22)],["min",__rt.float(96.22)]])]])],["amsg",""],["medt",1736316176514],["msdt",1736316176514],["mxehr",1000000000]])]],["oj",__rt.dict([["jid",1]])],["st",1],["tk",SESSION_TOKEN],["bau","web-api/game-proxy/"],["geu","game-api/74/"],["lau","game-api/lobby/"],["nkn","Local demo"],["pcd","100001"],["pid","100001"],["ioph","local-demo"],["occ",__rt.dict([["tcm",""],["tlb",""],["trb",""],["tsc",0],["ttp",0],["rurl",""]])],["uiogc",flags],["bl",2000],["sdn","api"]])],["err",null]])]);return null;});
