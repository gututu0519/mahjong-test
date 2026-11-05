// Migrated from server/core/service.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
import * as __m0 from "./storage.js";
import * as __m1 from "./sessions.js";
import * as __m2 from "./queries.js";
import * as __m3 from "./settlement.js";
const __file__=__rt.sourcePath("server/core/service.py");
export let GameService:any,Queries:any,Sessions:any,Settlement:any,Storage:any;

Storage=__rt.attr(__m0,"Storage");
Sessions=__rt.attr(__m1,"Sessions");
Queries=__rt.attr(__m2,"Queries");
Settlement=__rt.attr(__m3,"Settlement");
GameService=__rt.cls("GameService",[],{"__init__":__rt.fn("__init__",{names:["self", "database", "registry"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,database,registry){let minor_unit,units;units=(()=>{let game;const __out:any[]=[];for(const __t1 of __rt.iter(__rt.call(__rt.attr(registry,"games"),[],__rt.kw([])))){game=__t1;__out.push(__rt.call(__rt.b["getattr"],[game,"minor_unit",100],__rt.kw([])));}return __rt.set(__out);})();
if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[units],__rt.kw([])),()=>1]))){throw __rt.call(__rt.b["ValueError"],["Games with different monetary precision require separate services"],__rt.kw([]));}
minor_unit=__rt.call(__rt.attr(units,"pop"),[],__rt.kw([]));
__rt.setattr(self,"store",__rt.call(Storage,[database,registry],__rt.kw([])));
__rt.setattr(self,"sessions",__rt.call(Sessions,[__rt.attr(self,"store"),minor_unit],__rt.kw([])));
__rt.setattr(self,"queries",__rt.call(Queries,[__rt.attr(self,"store"),__rt.attr(self,"sessions")],__rt.kw([])));
__rt.setattr(self,"settlement",__rt.call(Settlement,[__rt.attr(self,"store"),__rt.attr(self,"sessions"),__rt.attr(self,"queries")],__rt.kw([])));
{const __t2=Array.from(__rt.iter(__rt.tuple([__rt.attr(__rt.attr(self,"store"),"database"),registry])));__rt.setattr(self,"database",__t2[0]);__rt.setattr(self,"registry",__t2[1]);}return null;}),"connection":__rt.fn("connection",{names:["self", "transaction"],kwonly:[],defaults:{"transaction":false},vararg:null,kwarg:null},function(self,transaction){return __rt.call(__rt.attr(__rt.attr(self,"store"),"connection"),[transaction],__rt.kw([]));return null;}),"create_session":__rt.fn("create_session",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){return __rt.call(__rt.attr(__rt.attr(self,"sessions"),"create_session"),[],__rt.kw([]));return null;}),"ensure_local_demo":__rt.fn("ensure_local_demo",{names:["self"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self){return __rt.call(__rt.attr(__rt.attr(self,"sessions"),"ensure_local_demo"),[],__rt.kw([]));return null;}),"wallet":__rt.fn("wallet",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){return __rt.call(__rt.attr(__rt.attr(self,"queries"),"wallet"),[token],__rt.kw([]));return null;}),"state":__rt.fn("state",{names:["self", "token", "game_id"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,game_id){return __rt.call(__rt.attr(__rt.attr(self,"queries"),"state"),[token,game_id],__rt.kw([]));return null;}),"history":__rt.fn("history",{names:["self", "token", "limit"],kwonly:[],defaults:{"limit":20},vararg:null,kwarg:null},function(self,token,limit){return __rt.call(__rt.attr(__rt.attr(self,"queries"),"history"),[token,limit],__rt.kw([]));return null;}),"spin":__rt.fn("spin",{names:["self", "token", "game_id", "request_key", "previous_sid", "bet_payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,game_id,request_key,previous_sid,bet_payload){return __rt.call(__rt.attr(__rt.attr(self,"settlement"),"spin"),[token,game_id,request_key,previous_sid,bet_payload],__rt.kw([]));return null;})});
