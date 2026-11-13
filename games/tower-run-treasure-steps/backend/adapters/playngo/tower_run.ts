// Migrated from py/adapters/playngo/tower_run.py. Runtime is Node.js only.
import * as __rt from "../../../../../other/shared/compat/runtime.js";
const __file__=__rt.sourcePath("py/adapters/playngo/tower_run.py");
export let Adapter:any,CLIENT:any,Path:any,ServiceError:any,datetime:any,json:any,timezone:any;

datetime=__rt.attr(__rt.modules["datetime"],"datetime");
timezone=__rt.attr(__rt.modules["datetime"],"timezone");
json=__rt.modules["json"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
CLIENT=__rt.bin("Div",__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),3),"clients/tower-run-treasure-steps");
Adapter=__rt.cls("Adapter",[],{"__init__":__rt.fn("__init__",{names:["self", "service"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,service){__rt.setattr(self,"service",service);return null;}),"current":__rt.fn("current",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){return __rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"state"),[token,"tower-run-treasure-steps"],__rt.kw([])),"state");return null;}),"wallet_line":__rt.fn("wallet_line",{names:["self", "token", "balance"],kwonly:[],defaults:{"balance":null},vararg:null,kwarg:null},function(self,token,balance){let amount;amount=(__rt.truth(__rt.compare(["Is"],[()=>balance,()=>null]))?__rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([])),"balance_minor"):balance);
return ("52 "+__rt.format(amount,"",-1)+" 0 0");return null;}),"transaction":__rt.fn("transaction",{names:["self", "token", "key", "payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,key,payload){let cached,db,player,previous;previous=__rt.item(__rt.call(__rt.attr(self,"current"),[token],__rt.kw([])),"sid");
{const __t1=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"service"),"connection"),[],__rt.kw([])));let __t3=false;db=__t1.value;try{player=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"service"),"sessions"),"_player"),[db,token],__rt.kw([]));
cached=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?",__rt.tuple([__rt.item(player,"id"),"tower-run-treasure-steps",key])],__rt.kw([])),"fetchone"),[],__rt.kw([]));
if(__rt.truth(cached)){previous=__rt.item(__rt.call(__rt.attr(json,"loads"),[__rt.item(cached,"request_json")],__rt.kw([])),"previous_sid");}}catch(__t2){__t3=true;if(!__t1.exit(__t2))throw __t2;}finally{if(!__t3)__t1.exit(null);}}
return __rt.call(__rt.attr(__rt.attr(self,"service"),"spin"),[token,"tower-run-treasure-steps",key,previous,payload],__rt.kw([]));return null;}),"call":__rt.fn("call",{names:["self", "token", "sequence", "command"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,sequence,command){let balance,key,kind,lines,outcome,payload,progress,replay,result,state,values,words;words=__rt.call(__rt.attr(command,"split"),[],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",words))){throw __rt.call(ServiceError,["REQUEST_INVALID","Missing command."],__rt.kw([]));}
kind=__rt.item(words,0);
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"103"]))){return [("103 \""+__rt.format(token,"",-1)+"\"")];}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"101"]))){return [("103 \""+__rt.format(token,"",-1)+"!1\""),"101 1 \"DEMO\" \"\" \"ZZ\" \"Player\" \"\"",__rt.bin("Add",__rt.bin("Add","127 \"",__rt.call(__rt.attr(__rt.call(__rt.attr(datetime,"now"),[__rt.attr(timezone,"utc")],__rt.kw([])),"strftime"),["%Y-%m-%dT%H:%M:%SZ"],__rt.kw([]))),"\"")];}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"104"]))){if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.item(words,1),()=>"1098"]))){throw __rt.call(ServiceError,["BET_INVALID","Unknown game."],__rt.kw([]));}
state=__rt.call(__rt.attr(self,"current"),[token],__rt.kw([]));
balance=__rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([])),"balance_minor");
if(__rt.truth(__rt.item(state,"pending"))){balance=__rt.bin("Add",balance,__rt.bin("Mult",(__rt.truth(__rt.item(state,"ultra"))?15:10),__rt.item(state,"last_denom")));}
values=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"service"),"registry"),"get"),["tower-run-treasure-steps"],__rt.kw([])),"config"),"denominations");
lines=["104 1",__rt.bin("Add",__rt.bin("Add",__rt.bin("Add",__rt.bin("Add","54 ",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[values],__rt.kw([]))],__rt.kw([])))," "),__rt.call(__rt.attr(" ","join"),[__rt.call(__rt.b["map"],[__rt.b["str"],values],__rt.kw([]))],__rt.kw([])))," 1"),"57 \"<custom><RTP Value=\\\"96\\\" /><DisableBetBooster Value=\\\"0\\\" /></custom>\"","60 96 0 0 0",__rt.call(__rt.attr(self,"wallet_line"),[token,balance],__rt.kw([])),"83 0"];
progress=__rt.call(__rt.b["sorted"],[(function*(){let k,v;for(const __t4 of __rt.iter(__rt.call(__rt.attr(__rt.item(state,"progress"),"items"),[],__rt.kw([])))){{const __t5=Array.from(__rt.iter(__t4));k=__t5[0];v=__t5[1];}yield __rt.tuple([__rt.call(__rt.b["int"],[k],__rt.kw([])),v]);}})()],__rt.kw([]));
__rt.call(__rt.attr(lines,"append"),[__rt.bin("Add",__rt.bin("Add",__rt.bin("Add",__rt.bin("Add","56 ",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[progress],__rt.kw([]))],__rt.kw([])))," "),__rt.call(__rt.attr(" ","join"),[(function*(){let pair,v;for(const __t6 of __rt.iter(progress)){pair=__t6;for(const __t7 of __rt.iter(pair)){v=__t7;yield __rt.call(__rt.b["str"],[v],__rt.kw([]));}}})()],__rt.kw([])))," 18")],__rt.kw([]));
if(__rt.truth(__rt.item(state,"pending"))){replay=__rt.call(__rt.attr(self,"transaction"),[token,__rt.bin("Add",__rt.bin("Add","playngo:",__rt.call(__rt.b["str"],[sequence],__rt.kw([]))),":replay"),__rt.dict([["action","replay"]])],__rt.kw([]));
__rt.call(__rt.attr(lines,"extend"),[__rt.item(__rt.item(replay,"outcome"),"lines")],__rt.kw([]));}
__rt.call(__rt.attr(lines,"append"),["109"],__rt.kw([]));
return lines;}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"0"]))){return ["0"];}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>kind,()=>"7"]),()=>__rt.compare(["Eq"],[()=>__rt.call(__rt.b["len"],[words],__rt.kw([])),()=>2])))){return [__rt.bin("Add","83 ",__rt.item(words,1))];}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>kind,()=>"2"]),()=>__rt.compare(["Eq"],[()=>__rt.call(__rt.b["len"],[words],__rt.kw([])),()=>3]),()=>__rt.compare(["Eq"],[()=>__rt.item(words,1),()=>"4"])))){return [command];}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>kind,()=>"1"]),()=>__rt.compare(["Eq"],[()=>__rt.call(__rt.b["len"],[words],__rt.kw([])),()=>5])))){if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.item(words,1),()=>"1"]),()=>__rt.compare(["NotEq"],[()=>__rt.item(words,4),()=>"1"]),()=>__rt.compare(["NotIn"],[()=>__rt.item(words,2),()=>__rt.tuple(["10","15"])])))){throw __rt.call(ServiceError,["BET_INVALID","Invalid fixed bet."],__rt.kw([]));}
payload=__rt.call(__rt.b["dict"],[],__rt.kw([["denom",__rt.call(__rt.b["int"],[__rt.item(words,3)],__rt.kw([]))],["ultra",__rt.compare(["Eq"],[()=>__rt.item(words,2),()=>"15"])]]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>command,()=>"2 6"]))){payload=__rt.call(__rt.b["dict"],[],__rt.kw([["action","continue"]]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>command,()=>"4 0"]))){payload=__rt.call(__rt.b["dict"],[],__rt.kw([["action","collect"]]));}else{throw __rt.call(ServiceError,["REQUEST_INVALID","Unknown game command."],__rt.kw([]));}}}
key=__rt.bin("Add","playngo:",__rt.call(__rt.b["str"],[sequence],__rt.kw([])));
result=__rt.call(__rt.attr(self,"transaction"),[token,key,payload],__rt.kw([]));
outcome=__rt.item(result,"outcome");
lines=__rt.bin("Add",(__rt.truth(__rt.or_(()=>__rt.compare(["Eq"],[()=>kind,()=>"1"]),()=>__rt.compare(["Eq"],[()=>kind,()=>"4"])))?[]:[command]),__rt.item(outcome,"lines"));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(outcome,"next_phase"),()=>"ready"]))){__rt.call(__rt.attr(lines,"append"),[__rt.call(__rt.attr(self,"wallet_line"),[token,__rt.item(__rt.item(result,"wallet"),"after_minor")],__rt.kw([]))],__rt.kw([]));}
return lines;return null;})});
