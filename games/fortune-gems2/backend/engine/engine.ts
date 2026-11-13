// Migrated from py/games/fortune_gems2/engine.py. Runtime is Node.js only.
import * as __rt from "../../../../other/shared/compat/runtime.js";
const __file__=__rt.sourcePath("py/games/fortune_gems2/engine.py");
export let FortuneGems2:any,LINES:any,MULTIPLIERS:any,Outcome:any,Path:any,ServiceError:any,copy:any,evaluate:any,hashlib:any,json:any,random:any;

copy=__rt.modules["copy"];
hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
random=__rt.modules["random"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
Outcome=__rt.attr(__rt.modules["py.core.contracts"],"Outcome");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
LINES=__rt.tuple([__rt.tuple([1,1,1]),__rt.tuple([0,0,0]),__rt.tuple([2,2,2]),__rt.tuple([0,1,2]),__rt.tuple([2,1,0])]);
MULTIPLIERS=__rt.tuple([1,2,3,5,10,15]);
evaluate=__rt.fn("evaluate",{names:["columns", "bet", "multiplier", "paytable"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(columns,bet,multiplier,paytable){let amount,awards,line,regular,rows,symbol,symbols;awards=[];
for(const __t1 of __rt.iter(__rt.call(__rt.b["enumerate"],[LINES],__rt.kw([])))){{const __t2=Array.from(__rt.iter(__t1));line=__t2[0];rows=__t2[1];}symbols=(()=>{let c,r;const __out:any[]=[];for(const __t3 of __rt.iter(__rt.call(__rt.b["enumerate"],[rows],__rt.kw([])))){{const __t4=Array.from(__rt.iter(__t3));c=__t4[0];r=__t4[1];}__out.push(__rt.item(__rt.item(columns,c),r));}return __out;})();
regular=__rt.bin("Sub",__rt.call(__rt.b["set"],[symbols],__rt.kw([])),__rt.set([7]));
if(__rt.truth(__rt.compare(["Gt"],[()=>__rt.call(__rt.b["len"],[regular],__rt.kw([])),()=>1]))){continue;}
symbol=__rt.call(__rt.b["next"],[__rt.call(__rt.b["iter"],[regular],__rt.kw([])),7],__rt.kw([]));
amount=__rt.bin("FloorDiv",__rt.bin("Mult",__rt.bin("Mult",bet,__rt.item(paytable,symbol)),multiplier),5);
__rt.call(__rt.attr(awards,"append"),[__rt.call(__rt.b["dict"],[],__rt.kw([["Symbol",symbol],["Line",line],["Win",__rt.bin("Div",amount,10000)]]))],__rt.kw([]));}
return awards;return null;});
FortuneGems2=__rt.cls("FortuneGems2",[],{"game_id":__rt.item(__rt.tuple(["fortune-gems2","Fortune Gems 2","1.0.1",10000]),0),"title":__rt.item(__rt.tuple(["fortune-gems2","Fortune Gems 2","1.0.1",10000]),1),"version":__rt.item(__rt.tuple(["fortune-gems2","Fortune Gems 2","1.0.1",10000]),2),"minor_unit":__rt.item(__rt.tuple(["fortune-gems2","Fortune Gems 2","1.0.1",10000]),3),"__init__":__rt.fn("__init__",{names:["self", "config_path"],kwonly:[],defaults:{"config_path":null},vararg:null,kwarg:null},function(self,config_path){let c,key,size;__rt.setattr(self,"config",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(Path,[__rt.or_(()=>config_path,()=>__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["config.json"],__rt.kw([])))],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
c=__rt.attr(self,"config");
for(const __t5 of __rt.iter([__rt.tuple(["symbol_weights",8]),__rt.tuple(["paytable_fifths",8]),__rt.tuple(["multiplier_weights",6]),__rt.tuple(["wheel_multiplier_weights",6]),__rt.tuple(["wheel_weights",12])])){{const __t6=Array.from(__rt.iter(__t5));key=__t6[0];size=__t6[1];}if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[__rt.item(c,key)],__rt.kw([])),()=>size]),()=>__rt.call(__rt.b["any"],[(function*(){let x;for(const __t7 of __rt.iter(__rt.item(c,key))){x=__t7;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[x],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["LtE"],[()=>x,()=>0]));}})()],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],[__rt.bin("Add","Invalid Fortune Gems 2 configuration: ",key)],__rt.kw([]));}}
if(__rt.truth(__rt.call(__rt.b["any"],[(function*(){let k;for(const __t8 of __rt.iter(["stack_chance","wheel_chance","extra_wheel_chance"])){k=__t8;yield __rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>__rt.item(c,k),()=>1]));}})()],__rt.kw([])))){throw __rt.call(__rt.b["ValueError"],["Invalid Fortune Gems 2 probabilities"],__rt.kw([]));}
__rt.setattr(self,"ruleset_id",__rt.bin("Add",__rt.bin("Add",__rt.attr(self,"version"),":"),__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[c],__rt.kw([["sort_keys",true]])),"encode"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,16,null))));return null;}),"initial_state":__rt.fn("initial_state",{names:["self", "seed"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,seed){return __rt.call(__rt.b["dict"],[],__rt.kw([["sid","0"],["round_id","0"],["phase","ready"],["ruleset_id",__rt.attr(self,"ruleset_id")],["last_event",null],["last_bet_minor",2000],["extra",false]]));return null;}),"public_state":__rt.fn("public_state",{names:["self", "state"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state){return __rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));return null;}),"normalize_bet":__rt.fn("normalize_bet",{names:["self", "payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,payload){let amount,extra;if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([]))),()=>__rt.bin("Sub",__rt.call(__rt.b["set"],[payload],__rt.kw([])),__rt.set(["bet_minor","extra"]))))){throw __rt.call(ServiceError,["BET_INVALID","Unsupported Fortune Gems 2 bet fields."],__rt.kw([]));}
{const __t9=Array.from(__rt.iter(__rt.tuple([__rt.call(__rt.attr(payload,"get"),["bet_minor",2000],__rt.kw([])),__rt.call(__rt.attr(payload,"get"),["extra",false],__rt.kw([]))])));amount=__t9[0];extra=__t9[1];}
if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[amount],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["NotIn"],[()=>amount,()=>__rt.item(__rt.attr(self,"config"),"bets_minor")]),()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[extra],__rt.kw([])),()=>__rt.b["bool"]])))){throw __rt.call(ServiceError,["BET_INVALID","Invalid Fortune Gems 2 bet."],__rt.kw([]));}
return __rt.call(__rt.b["dict"],[],__rt.kw([["bet_minor",amount],["extra",extra]]));return null;}),"step":__rt.fn("step",{names:["self", "state", "bet", "seed", "sid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state,bet,seed,sid){let _,amount,awards,c,col,columns,event,extra,index,line_minor,mult_show,multiplier,new_state,rng,special,spin,total,wheel,wheel_minor,wheel_mult,wheel_odd;{const __t10=Array.from(__rt.iter(__rt.tuple([__rt.call(__rt.attr(random,"Random"),[seed],__rt.kw([])),__rt.attr(self,"config")])));rng=__t10[0];c=__t10[1];}
{const __t11=Array.from(__rt.iter(__rt.tuple([__rt.item(bet,"bet_minor"),__rt.item(bet,"extra")])));amount=__t11[0];extra=__t11[1];}
columns=[];
for(const __t12 of __rt.iter(__rt.call(__rt.b["range"],[3],__rt.kw([])))){_=__t12;col=__rt.call(__rt.attr(rng,"choices"),[__rt.call(__rt.b["range"],[8],__rt.kw([])),__rt.item(c,"symbol_weights")],__rt.kw([["k",3]]));
if(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(c,"stack_chance")]))){col=__rt.bin("Mult",[__rt.item(col,0)],3);}
__rt.call(__rt.attr(columns,"append"),[col],__rt.kw([]));}
wheel=__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(c,(__rt.truth(extra)?"extra_wheel_chance":"wheel_chance"))]);
index=__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.call(__rt.b["range"],[(__rt.truth(extra)?1:0),6],__rt.kw([])),__rt.item(__rt.item(c,"multiplier_weights"),__rt.slice((__rt.truth(extra)?1:0),null,null))],__rt.kw([])),0);
multiplier=(__rt.truth(wheel)?1:__rt.item(MULTIPLIERS,index));
special=(__rt.truth(__rt.and_(()=>extra,()=>wheel))?15:(__rt.truth(wheel)?14:__rt.bin("Add",8,index)));
__rt.call(__rt.attr(columns,"append"),[[__rt.call(__rt.attr(rng,"randrange"),[(__rt.truth(extra)?9:8),14],__rt.kw([])),special,__rt.call(__rt.attr(rng,"randrange"),[(__rt.truth(extra)?9:8),14],__rt.kw([]))]],__rt.kw([]));
awards=__rt.call(evaluate,[columns,amount,multiplier,__rt.item(c,"paytable_fifths")],__rt.kw([]));
line_minor=__rt.call(__rt.b["sum"],[(function*(){let a;for(const __t13 of __rt.iter(awards)){a=__t13;yield __rt.call(__rt.b["round"],[__rt.bin("Mult",__rt.item(a,"Win"),10000)],__rt.kw([]));}})()],__rt.kw([]));
wheel_odd=(__rt.truth(wheel)?__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.item(c,"wheel_odds"),__rt.item(c,"wheel_weights")],__rt.kw([])),0):0);
mult_show=(__rt.truth(__rt.and_(()=>wheel,()=>extra))?__rt.call(__rt.attr(rng,"choices"),[MULTIPLIERS,__rt.item(c,"wheel_multiplier_weights")],__rt.kw([["k",12]])):__rt.bin("Mult",[1],12));
wheel_mult=(__rt.truth(wheel)?__rt.item(mult_show,__rt.call(__rt.attr(__rt.item(c,"wheel_odds"),"index"),[wheel_odd],__rt.kw([]))):1);
wheel_minor=__rt.bin("Mult",__rt.bin("Mult",amount,wheel_odd),wheel_mult);
total=__rt.bin("Add",line_minor,wheel_minor);
if(__rt.truth(__rt.compare(["Gt"],[()=>total,()=>__rt.bin("Mult",amount,__rt.item(c,"max_win_multiple"))]))){throw __rt.call(ServiceError,["GENERATION_LIMIT","Configured maximum win exceeded.",503],__rt.kw([]));}
spin=__rt.call(__rt.b["dict"],[],__rt.kw([["PlateSymbol",(()=>{let col;const __out:any[]=[];for(const __t14 of __rt.iter(columns)){col=__t14;__out.push(__rt.dict([["Col",col]]));}return __out;})()],["AwardDataVec",awards],["AwardTypeFlag",__rt.bin("BitOr",(__rt.truth(awards)?1:0),(__rt.truth(wheel)?2:0))],["LineMult",multiplier],["LineWin",__rt.bin("Div",line_minor,10000)],["WheelOdd",wheel_odd],["WheelMult",wheel_mult],["WheelWin",__rt.bin("Div",wheel_minor,10000)],["TotalWin",__rt.bin("Div",total,10000)],["Bet",__rt.bin("Div",amount,10000)],["Extra",extra],["IsBonus",wheel],["MultShowArray",mult_show],["LightOnPos",[]]]));
event=__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",sid],["bet_minor",amount],["extra",extra],["spin",spin],["total_minor",total]]));
new_state=__rt.call(__rt.b["dict"],[],__rt.kw([["sid",sid],["round_id",sid],["phase","ready"],["ruleset_id",__rt.attr(self,"ruleset_id")],["last_event",event],["last_bet_minor",amount],["extra",extra]]));
return __rt.call(Outcome,[new_state,event,(__rt.truth(extra)?__rt.bin("FloorDiv",__rt.bin("Mult",amount,3),2):amount),total],__rt.kw([]));return null;})});
