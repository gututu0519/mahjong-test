// Migrated from server/core/settlement.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "./encoding.js";
const __file__=__rt.sourcePath("server/core/settlement.py");
export let ServiceError:any,Settlement:any,encode:any,json:any,secrets:any,time:any;

json=__rt.modules["json"];
secrets=__rt.modules["secrets"];
time=__rt.modules["time"];
ServiceError=__rt.attr(__rt.modules["server.core.contracts"],"ServiceError");
encode=__rt.attr(__m0,"encode");
Settlement=__rt.cls("Settlement",[],{"__init__":__rt.fn("__init__",{names:["self", "store", "sessions", "queries"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,store,sessions,queries){{const __t1=Array.from(__rt.iter(__rt.tuple([store,sessions,queries])));__rt.setattr(self,"store",__t1[0]);__rt.setattr(self,"sessions",__t1[1]);__rt.setattr(self,"queries",__t1[2]);}return null;}),"spin":__rt.fn("spin",{names:["self", "token", "game_id", "request_key", "previous_sid", "bet_payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,game_id,request_key,previous_sid,bet_payload){let after,before,bet,cached,credit,db,debit,game,now,outcome,player,request_json,response,sid,state;if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[request_key,__rt.b["str"]],__rt.kw([]))),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>1,()=>__rt.call(__rt.b["len"],[request_key],__rt.kw([])),()=>128]))))){throw __rt.call(ServiceError,["REQUEST_KEY_INVALID","Use a 1..128 character idempotency key."],__rt.kw([]));}
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[previous_sid,__rt.b["str"]],__rt.kw([]))),()=>__rt.compare(["Gt"],[()=>__rt.call(__rt.b["len"],[previous_sid],__rt.kw([])),()=>64])))){throw __rt.call(ServiceError,["PREVIOUS_SID_INVALID","previous_sid must be a string from the last state."],__rt.kw([]));}
game=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"store"),"registry"),"get"),[game_id],__rt.kw([]));
bet=__rt.call(__rt.attr(game,"normalize_bet"),[bet_payload],__rt.kw([]));
request_json=__rt.call(encode,[__rt.dict([["previous_sid",previous_sid],["bet",bet]])],__rt.kw([]));
{const __t2=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"store"),"connection"),[true],__rt.kw([])));let __t4=false;db=__t2.value;try{player=__rt.call(__rt.attr(__rt.attr(self,"sessions"),"_player"),[db,token],__rt.kw([]));
cached=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT request_json,response_json FROM spins\n                                   WHERE player_id=? AND game_id=? AND request_key=?",__rt.tuple([__rt.item(player,"id"),game_id,request_key])],__rt.kw([])),"fetchone"),[],__rt.kw([]));
if(__rt.truth(cached)){if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.item(cached,"request_json"),()=>request_json]))){throw __rt.call(ServiceError,["IDEMPOTENCY_CONFLICT","This key was used for a different request.",409],__rt.kw([]));}
return __rt.call(__rt.attr(json,"loads"),[__rt.item(cached,"response_json")],__rt.kw([]));}
state=__rt.call(__rt.attr(__rt.attr(self,"queries"),"_state"),[db,__rt.item(player,"id"),game],__rt.kw([]));
if(__rt.truth(__rt.compare(["NotEq"],[()=>previous_sid,()=>__rt.item(state,"sid")]))){throw __rt.call(ServiceError,["STALE_STATE","Refresh game state before continuing.",409],__rt.kw([]));}
sid=__rt.call(__rt.b["str"],[__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT COALESCE(MAX(id),0)+1 FROM spins"],__rt.kw([])),"fetchone"),[],__rt.kw([])),0)],__rt.kw([]));
outcome=__rt.call(__rt.attr(game,"step"),[state,bet,__rt.call(__rt.attr(secrets,"token_hex"),[32],__rt.kw([])),sid],__rt.kw([]));
{const __t5=Array.from(__rt.iter(__rt.tuple([__rt.attr(outcome,"debit_minor"),__rt.attr(outcome,"credit_minor")])));debit=__t5[0];credit=__t5[1];}
if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[debit],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[credit],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.b["min"],[debit,credit],__rt.kw([])),()=>0])))){throw __rt.call(__rt.b["RuntimeError"],["Game returned invalid settlement amounts"],__rt.kw([]));}
before=__rt.item(player,"balance_minor");
if(__rt.truth(__rt.compare(["Lt"],[()=>before,()=>debit]))){throw __rt.call(ServiceError,["INSUFFICIENT_BALANCE","Insufficient virtual credits.",409],__rt.kw([]));}
after=__rt.bin("Add",__rt.bin("Sub",before,debit),credit);
if(__rt.truth(__rt.compare(["Gt"],[()=>after,()=>9000000000000000]))){throw __rt.call(ServiceError,["BALANCE_LIMIT","Local account balance limit reached.",409],__rt.kw([]));}
response=__rt.dict([["game_id",game_id],["sid",sid],["round_id",__rt.item(__rt.attr(outcome,"event"),"round_id")],["engine_version",__rt.attr(game,"version")],["ruleset_id",__rt.attr(game,"ruleset_id")],["wallet",__rt.dict([["before_minor",before],["debit_minor",debit],["credit_minor",credit],["after_minor",after]])],["outcome",__rt.attr(outcome,"event")]]);
now=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(db,"execute"),["INSERT INTO spins(id,player_id,game_id,round_id,request_key,request_json,\n                          response_json,state_json,ruleset_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",__rt.tuple([__rt.call(__rt.b["int"],[sid],__rt.kw([])),__rt.item(player,"id"),game_id,__rt.item(response,"round_id"),request_key,request_json,__rt.call(encode,[response],__rt.kw([])),__rt.call(encode,[__rt.attr(outcome,"state")],__rt.kw([])),__rt.attr(game,"ruleset_id"),now])],__rt.kw([]));
__rt.call(__rt.attr(db,"execute"),["INSERT INTO ledger(player_id,spin_id,kind,debit_minor,credit_minor,\n                          balance_before,balance_after,created_at) VALUES (?,?,'spin',?,?,?,?,?)",__rt.tuple([__rt.item(player,"id"),__rt.call(__rt.b["int"],[sid],__rt.kw([])),debit,credit,before,after,now])],__rt.kw([]));
__rt.call(__rt.attr(db,"execute"),["UPDATE players SET balance_minor=? WHERE id=?",__rt.tuple([after,__rt.item(player,"id")])],__rt.kw([]));
__rt.call(__rt.attr(db,"execute"),["UPDATE game_states SET state_json=? WHERE player_id=? AND game_id=?",__rt.tuple([__rt.call(encode,[__rt.attr(outcome,"state")],__rt.kw([])),__rt.item(player,"id"),game_id])],__rt.kw([]));
return response;}catch(__t3){__t4=true;if(!__t2.exit(__t3))throw __t3;}finally{if(!__t4)__t2.exit(null);}}return null;})});
