// Migrated from py/games/mahjong_ways2/engine.py. Runtime is Node.js only.
import * as __rt from "../../../../other/shared/compat/runtime.js";
const __file__=__rt.sourcePath("py/games/mahjong_ways2/engine.py");
export let Decimal:any,InvalidOperation:any,MahjongWays2:any,Outcome:any,PAYTABLE:any,Path:any,ServiceError:any,VISIBLE:any,copy:any,evaluate:any,hashlib:any,json:any,math:any,random:any;

copy=__rt.modules["copy"];
hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
math=__rt.modules["math"];
random=__rt.modules["random"];
Decimal=__rt.attr(__rt.modules["decimal"],"Decimal");
InvalidOperation=__rt.attr(__rt.modules["decimal"],"InvalidOperation");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
Outcome=__rt.attr(__rt.modules["py.core.contracts"],"Outcome");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
PAYTABLE=__rt.dict([[2,__rt.dict([[3,10],[4,25],[5,50]])],[3,__rt.dict([[3,8],[4,20],[5,40]])],[4,__rt.dict([[3,6],[4,15],[5,30]])],[5,__rt.dict([[3,5],[4,10],[5,15]])],[6,__rt.dict([[3,3],[4,5],[5,12]])],[7,__rt.dict([[3,3],[4,5],[5,12]])],[8,__rt.dict([[3,2],[4,4],[5,10]])],[9,__rt.dict([[3,1],[4,3],[5,6]])],[10,__rt.dict([[3,1],[4,3],[5,6]])]]);
VISIBLE=[__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[1,5],__rt.kw([]))],__rt.kw([])),__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[8,13],__rt.kw([]))],__rt.kw([])),__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[15,20],__rt.kw([]))],__rt.kw([])),__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[22,27],__rt.kw([]))],__rt.kw([])),__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[29,33],__rt.kw([]))],__rt.kw([]))];
evaluate=__rt.fn("evaluate",{names:["board", "coin_minor", "level", "multiplier"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(board,coin_minor,level,multiplier){let awards,column,hits,key,matches,positions,rates,symbol,table,ways;if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[board],__rt.kw([])),()=>35]),()=>__rt.call(__rt.b["any"],[(function*(){let x;for(const __t1 of __rt.iter(board)){x=__t1;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[x],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>x,()=>10])));}})()],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],["Expected 35 symbol IDs in 0..10"],__rt.kw([]));}
{const __t2=Array.from(__rt.iter(__rt.tuple([__rt.dict([]),__rt.dict([]),__rt.dict([]),__rt.dict([])])));positions=__t2[0];ways=__t2[1];rates=__t2[2];awards=__t2[3];}
for(const __t3 of __rt.iter(__rt.call(__rt.attr(PAYTABLE,"items"),[],__rt.kw([])))){{const __t4=Array.from(__rt.iter(__t3));symbol=__t4[0];table=__t4[1];}hits=[];
for(const __t5 of __rt.iter(VISIBLE)){column=__t5;matches=(()=>{let p;const __out:any[]=[];for(const __t6 of __rt.iter(column)){p=__t6;if(__rt.truth(__rt.compare(["In"],[()=>__rt.item(board,p),()=>__rt.tuple([0,symbol])]))){__out.push(p);}}return __out;})();
if(__rt.truth(__rt.unary("Not",matches))){break;}
__rt.call(__rt.attr(hits,"append"),[matches],__rt.kw([]));}
if(__rt.truth(__rt.compare(["GtE"],[()=>__rt.call(__rt.b["len"],[hits],__rt.kw([])),()=>3]))){key=__rt.call(__rt.b["str"],[symbol],__rt.kw([]));
__rt.setitem(positions,key,(()=>{let group,p;const __out:any[]=[];for(const __t7 of __rt.iter(hits)){group=__t7;for(const __t8 of __rt.iter(group)){p=__t8;__out.push(p);}}return __out;})());
__rt.setitem(ways,key,__rt.call(__rt.attr(math,"prod"),[__rt.call(__rt.b["map"],[__rt.b["len"],hits],__rt.kw([]))],__rt.kw([])));
__rt.setitem(rates,key,__rt.item(table,__rt.call(__rt.b["len"],[hits],__rt.kw([]))));
__rt.setitem(awards,key,__rt.bin("Mult",__rt.bin("Mult",__rt.bin("Mult",coin_minor,level),__rt.item(ways,key)),__rt.item(rates,key)));}}
return __rt.dict([["winning_positions",positions],["ways",ways],["rates",rates],["base_awards_minor",awards],["win_minor",__rt.bin("Mult",__rt.call(__rt.b["sum"],[__rt.call(__rt.attr(awards,"values"),[],__rt.kw([]))],__rt.kw([])),multiplier)]]);return null;});
MahjongWays2=__rt.cls("MahjongWays2",[],{"game_id":"mahjong-ways2","title":"\u9ebb\u5c06\u80e1\u4e862","version":"1.0.0","__init__":__rt.fn("__init__",{names:["self", "config_path"],kwonly:[],defaults:{"config_path":null},vararg:null,kwarg:null},function(self,config_path){let c,digest,path;path=__rt.or_(()=>config_path,()=>__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["config.json"],__rt.kw([])));
__rt.setattr(self,"config",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(Path,[path],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
c=__rt.attr(self,"config");
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["set"],[__rt.item(c,"symbol_weights")],__rt.kw([])),()=>__rt.call(__rt.b["set"],[__rt.call(__rt.b["map"],[__rt.b["str"],__rt.call(__rt.b["range"],[1,11],__rt.kw([]))],__rt.kw([]))],__rt.kw([]))]),()=>__rt.call(__rt.b["any"],[(function*(){let v;for(const __t9 of __rt.iter(__rt.call(__rt.attr(__rt.item(c,"symbol_weights"),"values"),[],__rt.kw([])))){v=__t9;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[v],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["LtE"],[()=>v,()=>0]));}})()],__rt.kw([])),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>__rt.item(c,"gold_probability"),()=>1]))))){throw __rt.call(__rt.b["ValueError"],["Invalid generation weights"],__rt.kw([]));}
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"coin_sizes_minor"),()=>[1,6,30]]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"bet_levels"),()=>__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[1,11],__rt.kw([]))],__rt.kw([]))]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"base_bet_factor"),()=>20]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"normal_multipliers"),()=>[1,2,3,5]]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_multipliers"),()=>[2,4,6,10]]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_trigger"),()=>3]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_base_spins"),()=>10]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_extra_per_scatter"),()=>2]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"win_thresholds"),()=>__rt.dict([["mw",3],["bw",5],["mgw",15],["smgw",35]])])))){throw __rt.call(__rt.b["ValueError"],["This engine version only supports the documented rule constants"],__rt.kw([]));}
digest=__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[c],__rt.kw([["sort_keys",true]])),"encode"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,16,null));
__rt.setattr(self,"ruleset_id",(__rt.format(__rt.attr(self,"version"),"",-1)+":"+__rt.format(digest,"",-1)));return null;}),"normalize_bet":__rt.fn("normalize_bet",{names:["self", "payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,payload){let coin,level,value;if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(ServiceError,["BET_INVALID","Bet must be an object."],__rt.kw([]));}
if(__rt.truth(__rt.bin("Sub",__rt.call(__rt.b["set"],[payload],__rt.kw([])),__rt.set(["coin_minor","level","cs","ml"])))){throw __rt.call(ServiceError,["BET_INVALID","Unsupported bet fields."],__rt.kw([]));}
try{coin=__rt.call(__rt.attr(payload,"get"),["coin_minor"],__rt.kw([]));
if(__rt.truth(__rt.compare(["Is"],[()=>coin,()=>null]))){value=__rt.bin("Mult",__rt.call(Decimal,[__rt.call(__rt.b["str"],[__rt.call(__rt.attr(payload,"get"),["cs","0.01"],__rt.kw([]))],__rt.kw([]))],__rt.kw([])),100);
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.attr(value,"is_finite"),[],__rt.kw([]))),()=>__rt.compare(["NotEq"],[()=>value,()=>__rt.call(__rt.attr(value,"to_integral_value"),[],__rt.kw([]))])))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}
coin=__rt.call(__rt.b["int"],[value],__rt.kw([]));}
level=__rt.call(__rt.attr(payload,"get"),["level",__rt.call(__rt.attr(payload,"get"),["ml",5],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[coin],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[level],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["NotIn"],[()=>coin,()=>__rt.item(__rt.attr(self,"config"),"coin_sizes_minor")]),()=>__rt.compare(["NotIn"],[()=>level,()=>__rt.item(__rt.attr(self,"config"),"bet_levels")])))){throw __rt.call(__rt.b["ValueError"],[],__rt.kw([]));}}catch(__t10){if(__rt.matches(__t10,__rt.tuple([__rt.b["ValueError"],__rt.b["TypeError"],InvalidOperation,__rt.b["OverflowError"]]))){throw __rt.call(ServiceError,["BET_INVALID","Unsupported coin size or bet level."],__rt.kw([]));}else{throw __t10;}}
return __rt.dict([["coin_minor",coin],["level",level]]);return null;}),"_draw_column":__rt.fn("_draw_column",{names:["self", "rng", "count", "has_scatter"],kwonly:[],defaults:{"has_scatter":false},vararg:null,kwarg:null},function(self,rng,count,has_scatter){let _,result,symbol,symbols,weights;symbols=__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[1,11],__rt.kw([]))],__rt.kw([]));
result=[];
for(const __t11 of __rt.iter(__rt.call(__rt.b["range"],[count],__rt.kw([])))){_=__t11;weights=(()=>{let s;const __out:any[]=[];for(const __t12 of __rt.iter(symbols)){s=__t12;__out.push((__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>s,()=>1]),()=>has_scatter))?0:__rt.item(__rt.item(__rt.attr(self,"config"),"symbol_weights"),__rt.call(__rt.b["str"],[s],__rt.kw([])))));}return __out;})();
symbol=__rt.item(__rt.call(__rt.attr(rng,"choices"),[symbols],__rt.kw([["weights",weights],["k",1]])),0);
has_scatter=__rt.bin("BitOr",has_scatter,__rt.compare(["Eq"],[()=>symbol,()=>1]));
__rt.call(__rt.attr(result,"append"),[symbol],__rt.kw([]));}
return result;return null;}),"_gold":__rt.fn("_gold",{names:["self", "rng", "board", "candidates", "gold", "serial"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng,board,candidates,gold,serial){let added,col,pos;added=(()=>{let _;const __out:any[]=[];for(const __t13 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){_=__t13;__out.push([]);}return __out;})();
for(const __t14 of __rt.iter(candidates)){pos=__t14;col=__rt.bin("FloorDiv",pos,7);
if(__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>col,()=>__rt.tuple([1,2,3])]),()=>__rt.compare(["GtE"],[()=>__rt.item(board,pos),()=>2]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"gold_probability")])))){serial=__rt.bin("Add",serial,1);
__rt.setitem(gold,__rt.call(__rt.b["str"],[serial],__rt.kw([])),pos);
__rt.call(__rt.attr(__rt.item(added,col),"append"),[__rt.bin("Mod",pos,7)],__rt.kw([]));}}
return __rt.tuple([gold,serial,added]);return null;}),"_new_board":__rt.fn("_new_board",{names:["self", "rng"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng){return (()=>{let _,s;const __out:any[]=[];for(const __t15 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){_=__t15;for(const __t16 of __rt.iter(__rt.call(__rt.attr(self,"_draw_column"),[rng,7],__rt.kw([])))){s=__t16;__out.push(s);}}return __out;})();return null;}),"initial_state":__rt.fn("initial_state",{names:["self", "seed"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,seed){let board,rng;rng=__rt.call(__rt.attr(random,"Random"),[seed],__rt.kw([]));
board=__rt.call(__rt.attr(self,"_new_board"),[rng],__rt.kw([]));
return __rt.dict([["phase","ready"],["sid","0"],["round_id","0"],["step",0],["ruleset_id",__rt.attr(self,"ruleset_id")],["board",board],["gold",__rt.dict([])],["removed",[]],["gold_serial",0],["bet",__rt.dict([["coin_minor",1],["level",5]])],["free",null],["multiplier_index",0],["combo",0],["round_award_minor",0],["spin_award_minor",0],["counts",__rt.dict([])],["last_event",null]]);return null;}),"public_state":__rt.fn("public_state",{names:["self", "state"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state){return (()=>{let k,v;const __out:any[]=[];for(const __t17 of __rt.iter(__rt.call(__rt.attr(state,"items"),[],__rt.kw([])))){{const __t18=Array.from(__rt.iter(__t17));k=__t18[0];v=__t18[1];}if(__rt.truth(__rt.compare(["NotIn"],[()=>k,()=>__rt.tuple(["seed","gold_serial"])]))){__out.push([k,__rt.call(__rt.attr(copy,"deepcopy"),[v],__rt.kw([]))]);}}return __rt.dict(__out);})();return null;}),"step":__rt.fn("step",{names:["self", "state", "bet", "seed", "sid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state,bet,seed,sid){let _,added,after,board,candidates,cascade,col,combo,converted,counts,debit,event,free,free_mode,gold,gold_moves,incoming,index,key,multiplier,__py_new,new_gold,next_phase,old,phase,refills,remaining_gold,removed,result,rng,round_award,scatter,serial,spin_award,start,survivors,total_bet,win,won_positions;state=__rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));
phase=__rt.item(state,"phase");
start=__rt.compare(["Eq"],[()=>phase,()=>"ready"]);
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",start),()=>__rt.compare(["NotEq"],[()=>__rt.item(state,"ruleset_id"),()=>__rt.attr(self,"ruleset_id")])))){throw __rt.call(ServiceError,["RULESET_CHANGED","Finish this round with its original ruleset.",409],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",start),()=>__rt.compare(["NotEq"],[()=>bet,()=>__rt.item(state,"bet")])))){throw __rt.call(ServiceError,["BET_LOCKED","Finish the round before changing the bet.",409],__rt.kw([]));}
if(__rt.truth(start)){__rt.call(__rt.attr(state,"update"),[],__rt.kw([["seed",seed],["step",0],["ruleset_id",__rt.attr(self,"ruleset_id")],["round_id",sid],["bet",bet],["round_award_minor",0],["spin_award_minor",0],["free",null],["counts",__rt.dict([])],["gold_serial",0]]));}
rng=__rt.call(__rt.attr(random,"Random"),[(__rt.format(__rt.item(state,"seed"),"",-1)+":"+__rt.format(__rt.item(state,"step"),"",-1)+":"+__rt.format(__rt.attr(self,"ruleset_id"),"",-1))],__rt.kw([]));
cascade=__rt.compare(["In"],[()=>phase,()=>__rt.tuple(["paid_cascade","free_cascade"])]);
free_mode=__rt.compare(["In"],[()=>phase,()=>__rt.tuple(["free_start","free_cascade"])]);
{const __t19=Array.from(__rt.iter(__rt.tuple([__rt.dict([]),null,null])));gold_moves=__t19[0];refills=__t19[1];new_gold=__t19[2];}
if(__rt.truth(cascade)){{const __t20=Array.from(__rt.iter(__rt.tuple([[],__rt.dict([]),[],[]])));board=__t20[0];gold=__t20[1];candidates=__t20[2];refills=__t20[3];}
removed=__rt.call(__rt.b["set"],[__rt.item(state,"removed")],__rt.kw([]));
for(const __t21 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){col=__t21;survivors=(()=>{let p,v;const __out:any[]=[];for(const __t22 of __rt.iter(__rt.call(__rt.b["enumerate"],[__rt.item(state,"board")],__rt.kw([])))){{const __t23=Array.from(__rt.iter(__t22));p=__t23[0];v=__t23[1];}if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.bin("FloorDiv",p,7),()=>col]),()=>__rt.compare(["NotIn"],[()=>p,()=>removed])))){__out.push(v);}}return __out;})();
incoming=__rt.call(__rt.attr(self,"_draw_column"),[rng,__rt.bin("Sub",7,__rt.call(__rt.b["len"],[survivors],__rt.kw([]))),__rt.compare(["In"],[()=>1,()=>survivors])],__rt.kw([]));
__rt.call(__rt.attr(refills,"append"),[incoming],__rt.kw([]));
__rt.call(__rt.attr(candidates,"extend"),[__rt.call(__rt.b["range"],[__rt.bin("Mult",col,7),__rt.bin("Add",__rt.bin("Mult",col,7),__rt.call(__rt.b["len"],[incoming],__rt.kw([])))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(board,"extend"),[__rt.bin("Add",incoming,survivors)],__rt.kw([]));}
for(const __t24 of __rt.iter(__rt.call(__rt.attr(__rt.item(state,"gold"),"items"),[],__rt.kw([])))){{const __t25=Array.from(__rt.iter(__t24));key=__t25[0];old=__t25[1];}__py_new=__rt.bin("Add",old,__rt.call(__rt.b["sum"],[(function*(){let p;for(const __t26 of __rt.iter(removed)){p=__t26;yield __rt.and_(()=>__rt.compare(["Gt"],[()=>p,()=>old]),()=>__rt.compare(["Eq"],[()=>__rt.bin("FloorDiv",p,7),()=>__rt.bin("FloorDiv",old,7)]));}})()],__rt.kw([])));
__rt.setitem(gold,key,__py_new);
if(__rt.truth(__rt.compare(["NotEq"],[()=>old,()=>__py_new]))){__rt.setitem(gold_moves,key,[old,__py_new]);}}
{const __t27=Array.from(__rt.iter(__rt.call(__rt.attr(self,"_gold"),[rng,board,candidates,gold,__rt.item(state,"gold_serial")],__rt.kw([]))));gold=__t27[0];serial=__t27[1];new_gold=__t27[2];}}else{board=__rt.call(__rt.attr(self,"_new_board"),[rng],__rt.kw([]));
{const __t28=Array.from(__rt.iter(__rt.call(__rt.attr(self,"_gold"),[rng,board,__rt.call(__rt.b["range"],[35],__rt.kw([])),__rt.dict([]),__rt.item(state,"gold_serial")],__rt.kw([]))));gold=__t28[0];serial=__t28[1];_=__t28[2];}}
index=(__rt.truth(cascade)?__rt.call(__rt.b["min"],[__rt.bin("Add",__rt.item(state,"multiplier_index"),1),3],__rt.kw([])):0);
multiplier=__rt.item(__rt.item(__rt.attr(self,"config"),(__rt.truth(free_mode)?"free_multipliers":"normal_multipliers")),index);
result=__rt.call(evaluate,[board,__rt.item(bet,"coin_minor"),__rt.item(bet,"level"),multiplier],__rt.kw([]));
win=__rt.item(result,"win_minor");
won_positions=(()=>{let group,p;const __out:any[]=[];for(const __t29 of __rt.iter(__rt.call(__rt.attr(__rt.item(result,"winning_positions"),"values"),[],__rt.kw([])))){group=__t29;for(const __t30 of __rt.iter(group)){p=__t30;__out.push(p);}}return __rt.set(__out);})();
converted=__rt.bin("BitAnd",won_positions,__rt.call(__rt.b["set"],[__rt.call(__rt.attr(gold,"values"),[],__rt.kw([]))],__rt.kw([])));
removed=__rt.call(__rt.b["sorted"],[__rt.bin("Sub",won_positions,converted)],__rt.kw([]));
after=(()=>{let p,s;const __out:any[]=[];for(const __t31 of __rt.iter(__rt.call(__rt.b["enumerate"],[board],__rt.kw([])))){{const __t32=Array.from(__rt.iter(__t31));p=__t32[0];s=__t32[1];}__out.push((__rt.truth(__rt.compare(["In"],[()=>p,()=>converted]))?0:s));}return __out;})();
remaining_gold=(()=>{let k,p;const __out:any[]=[];for(const __t33 of __rt.iter(__rt.call(__rt.attr(gold,"items"),[],__rt.kw([])))){{const __t34=Array.from(__rt.iter(__t33));k=__t34[0];p=__t34[1];}if(__rt.truth(__rt.compare(["NotIn"],[()=>p,()=>converted]))){__out.push([k,p]);}}return __rt.dict(__out);})();
scatter=__rt.call(__rt.b["sum"],[(function*(){let column,p;for(const __t35 of __rt.iter(VISIBLE)){column=__t35;for(const __t36 of __rt.iter(column)){p=__t36;yield __rt.compare(["Eq"],[()=>__rt.item(board,p),()=>1]);}}})()],__rt.kw([]));
free=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.item(state,"free")],__rt.kw([]));
if(__rt.truth(free_mode)){__rt.setitem(free,"remaining",__rt.bin("Sub",__rt.item(free,"remaining"),__rt.call(__rt.b["int"],[__rt.compare(["Eq"],[()=>phase,()=>"free_start"])],__rt.kw([]))));
__rt.setitem(free,"award_minor",__rt.bin("Add",__rt.item(free,"award_minor"),win));
__rt.setitem(free,"added",0);}
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",win),()=>__rt.compare(["GtE"],[()=>scatter,()=>__rt.item(__rt.attr(self,"config"),"free_trigger")])))){added=__rt.bin("Add",__rt.item(__rt.attr(self,"config"),"free_base_spins"),__rt.bin("Mult",__rt.bin("Sub",scatter,3),__rt.item(__rt.attr(self,"config"),"free_extra_per_scatter")));
if(__rt.truth(__rt.compare(["Is"],[()=>free,()=>null]))){free=__rt.dict([["remaining",0],["total",0],["award_minor",0],["added",0]]);}
__rt.setitem(free,"remaining",__rt.bin("Add",__rt.item(free,"remaining"),added));
__rt.setitem(free,"total",__rt.bin("Add",__rt.item(free,"total"),added));
__rt.setitem(free,"added",added);}
next_phase=(__rt.truth(win)?(__rt.truth(free_mode)?"free_cascade":"paid_cascade"):(__rt.truth(__rt.and_(()=>free,()=>__rt.item(free,"remaining")))?"free_start":"ready"));
total_bet=__rt.bin("Mult",__rt.bin("Mult",__rt.item(bet,"coin_minor"),__rt.item(bet,"level")),__rt.item(__rt.attr(self,"config"),"base_bet_factor"));
debit=(__rt.truth(start)?total_bet:0);
round_award=__rt.bin("Add",__rt.item(state,"round_award_minor"),win);
spin_award=__rt.bin("Add",(__rt.truth(cascade)?__rt.item(state,"spin_award_minor"):0),win);
combo=(__rt.truth(win)?__rt.bin("Add",(__rt.truth(cascade)?__rt.item(state,"combo"):0),1):0);
counts=__rt.item(state,"counts");
if(__rt.truth(__rt.unary("Not",start))){__rt.setitem(counts,phase,__rt.bin("Add",__rt.call(__rt.attr(counts,"get"),[phase,0],__rt.kw([])),1));}
event=__rt.call(__rt.b["dict"],[result],__rt.kw([["sid",sid],["round_id",__rt.item(state,"round_id")],["phase",phase],["next_phase",next_phase],["bet",bet],["base_bet_minor",total_bet],["debit_minor",debit],["board_before",board],["board_after",after],["gold_before",gold],["gold_after",remaining_gold],["removed",removed],["refills",refills],["new_gold",new_gold],["gold_moves",gold_moves],["scatter_count",scatter],["multiplier",multiplier],["multiplier_index",index],["free",free],["round_award_minor",round_award],["spin_award_minor",spin_award],["combo",combo],["counts",__rt.call(__rt.attr(copy,"deepcopy"),[counts],__rt.kw([]))],["ruleset_id",__rt.attr(self,"ruleset_id")]]));
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["phase",next_phase],["sid",sid],["step",__rt.bin("Add",__rt.item(state,"step"),1)],["board",after],["gold",remaining_gold],["gold_serial",serial],["removed",removed],["multiplier_index",index],["combo",combo],["free",free],["round_award_minor",round_award],["spin_award_minor",spin_award],["last_event",event]]));
return __rt.call(Outcome,[state,event,debit,win],__rt.kw([]));return null;})});
