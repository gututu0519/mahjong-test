// Migrated from py/core/queries.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "./encoding.js";
const __file__=__rt.sourcePath("py/core/queries.py");
export let Queries:any,ServiceError:any,encode:any,json:any,secrets:any;

json=__rt.modules["json"];
secrets=__rt.modules["secrets"];
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
encode=__rt.attr(__m0,"encode");
Queries=__rt.cls("Queries",[],{"__init__":__rt.fn("__init__",{names:["self", "store", "sessions"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,store,sessions){{const __t1=Array.from(__rt.iter(__rt.tuple([store,sessions])));__rt.setattr(self,"store",__t1[0]);__rt.setattr(self,"sessions",__t1[1]);}return null;}),"wallet":__rt.fn("wallet",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){let db,p;{const __t2=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"store"),"connection"),[],__rt.kw([])));let __t4=false;db=__t2.value;try{p=__rt.call(__rt.attr(__rt.attr(self,"sessions"),"_player"),[db,token],__rt.kw([]));
return __rt.dict([["player_id",__rt.item(p,"id")],["balance_minor",__rt.item(p,"balance_minor")],["currency","DEMO"],["minor_unit",__rt.attr(__rt.attr(self,"sessions"),"minor_unit")]]);}catch(__t3){__t4=true;if(!__t2.exit(__t3))throw __t3;}finally{if(!__t4)__t2.exit(null);}}return null;}),"_state":__rt.fn("_state",{names:["self", "db", "player_id", "game"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,db,player_id,game){let row,state;row=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT state_json FROM game_states WHERE player_id=? AND game_id=?",__rt.tuple([player_id,__rt.attr(game,"game_id")])],__rt.kw([])),"fetchone"),[],__rt.kw([]));
if(__rt.truth(row)){return __rt.call(__rt.attr(json,"loads"),[__rt.item(row,0)],__rt.kw([]));}
state=__rt.call(__rt.attr(game,"initial_state"),[__rt.call(__rt.attr(secrets,"token_hex"),[32],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(db,"execute"),["INSERT INTO game_states VALUES (?,?,?)",__rt.tuple([player_id,__rt.attr(game,"game_id"),__rt.call(encode,[state],__rt.kw([]))])],__rt.kw([]));
return state;return null;}),"state":__rt.fn("state",{names:["self", "token", "game_id"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,game_id){let db,game,p,state;game=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"store"),"registry"),"get"),[game_id],__rt.kw([]));
{const __t5=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"store"),"connection"),[true],__rt.kw([])));let __t7=false;db=__t5.value;try{p=__rt.call(__rt.attr(__rt.attr(self,"sessions"),"_player"),[db,token],__rt.kw([]));
state=__rt.call(__rt.attr(self,"_state"),[db,__rt.item(p,"id"),game],__rt.kw([]));
return __rt.dict([["game_id",game_id],["balance_minor",__rt.item(p,"balance_minor")],["engine_version",__rt.attr(game,"version")],["ruleset_id",__rt.attr(game,"ruleset_id")],["state",__rt.call(__rt.attr(game,"public_state"),[state],__rt.kw([]))]]);}catch(__t6){__t7=true;if(!__t5.exit(__t6))throw __t6;}finally{if(!__t7)__t5.exit(null);}}return null;}),"history":__rt.fn("history",{names:["self", "token", "limit"],kwonly:[],defaults:{"limit":20},vararg:null,kwarg:null},function(self,token,limit){let db,player,rows;if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[limit],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>1,()=>limit,()=>100]))))){throw __rt.call(ServiceError,["LIMIT_INVALID","limit must be between 1 and 100."],__rt.kw([]));}
{const __t8=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"store"),"connection"),[],__rt.kw([])));let __t10=false;db=__t8.value;try{player=__rt.call(__rt.attr(__rt.attr(self,"sessions"),"_player"),[db,token],__rt.kw([]));
rows=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT response_json FROM spins WHERE player_id=? ORDER BY id DESC LIMIT ?",__rt.tuple([__rt.item(player,"id"),limit])],__rt.kw([])),"fetchall"),[],__rt.kw([]));
return (()=>{let row;const __out:any[]=[];for(const __t11 of __rt.iter(rows)){row=__t11;__out.push(__rt.call(__rt.attr(json,"loads"),[__rt.item(row,0)],__rt.kw([])));}return __out;})();}catch(__t9){__t10=true;if(!__t8.exit(__t9))throw __t9;}finally{if(!__t10)__t8.exit(null);}}return null;})});
