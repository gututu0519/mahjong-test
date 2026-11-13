// Migrated from py/games/captains_bounty/engine.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
import * as __m0 from "../mahjong_ways2/engine.js";
const __file__=__rt.sourcePath("py/games/captains_bounty/engine.py");
export let CaptainsBounty:any,LINES:any,MahjongWays2:any,Outcome:any,PAYTABLE:any,Path:any,ServiceError:any,copy:any,evaluate:any,hashlib:any,json:any,random:any;

copy=__rt.modules["copy"];
hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
random=__rt.modules["random"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
Outcome=__rt.attr(__rt.modules["py.core.contracts"],"Outcome");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
MahjongWays2=__rt.attr(__m0,"MahjongWays2");
PAYTABLE=__rt.dict([[2,__rt.dict([[3,50],[4,250],[5,2500]])],[3,__rt.dict([[3,20],[4,100],[5,1000]])],[4,__rt.dict([[3,15],[4,50],[5,500]])],[5,__rt.dict([[3,10],[4,25],[5,200]])],[6,__rt.dict([[3,5],[4,20],[5,100]])],[7,__rt.dict([[3,4],[4,15],[5,75]])],[8,__rt.dict([[3,3],[4,10],[5,50]])]]);
LINES=[__rt.tuple([1,4,7,10,13]),__rt.tuple([0,3,6,9,12]),__rt.tuple([2,5,8,11,14]),__rt.tuple([0,4,8,10,12]),__rt.tuple([2,4,6,10,14]),__rt.tuple([0,3,7,9,12]),__rt.tuple([2,5,7,11,14]),__rt.tuple([1,5,8,11,13]),__rt.tuple([1,3,6,9,13]),__rt.tuple([0,4,7,10,12]),__rt.tuple([2,4,7,10,14]),__rt.tuple([1,4,6,10,13]),__rt.tuple([1,4,8,10,13]),__rt.tuple([1,3,7,9,13]),__rt.tuple([1,5,7,11,13]),__rt.tuple([0,4,6,10,12]),__rt.tuple([2,4,8,10,14]),__rt.tuple([0,3,7,11,14]),__rt.tuple([2,5,7,9,12]),__rt.tuple([0,5,6,11,12])];
evaluate=__rt.fn("evaluate",{names:["board", "coin_minor", "level", "multiplier"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(board,coin_minor,level,multiplier){let awards,candidates,cells,key,line,number,p,positions,rate,rates,symbol,table;if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[board],__rt.kw([])),()=>15]),()=>__rt.call(__rt.b["any"],[(function*(){let s;for(const __t1 of __rt.iter(board)){s=__t1;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[s],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>s,()=>8])));}})()],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],["Expected 15 Captain's Bounty symbols"],__rt.kw([]));}
{const __t2=Array.from(__rt.iter(__rt.tuple([__rt.dict([]),__rt.dict([]),__rt.dict([])])));positions=__t2[0];rates=__t2[1];awards=__t2[2];}
for(const __t3 of __rt.iter(__rt.call(__rt.b["enumerate"],[LINES,1],__rt.kw([])))){{const __t4=Array.from(__rt.iter(__t3));number=__t4[0];line=__t4[1];}candidates=[];
for(const __t5 of __rt.iter(__rt.call(__rt.attr(PAYTABLE,"items"),[],__rt.kw([])))){{const __t6=Array.from(__rt.iter(__t5));symbol=__t6[0];table=__t6[1];}cells=[];
for(const __t7 of __rt.iter(line)){p=__t7;if(__rt.truth(__rt.compare(["NotIn"],[()=>__rt.item(board,p),()=>__rt.tuple([0,symbol])]))){break;}
__rt.call(__rt.attr(cells,"append"),[p],__rt.kw([]));}
if(__rt.truth(__rt.compare(["GtE"],[()=>__rt.call(__rt.b["len"],[cells],__rt.kw([])),()=>3]))){__rt.call(__rt.attr(candidates,"append"),[__rt.tuple([__rt.item(table,__rt.call(__rt.b["len"],[cells],__rt.kw([]))),cells])],__rt.kw([]));}}
if(__rt.truth(candidates)){{const __t8=Array.from(__rt.iter(__rt.call(__rt.b["max"],[candidates],__rt.kw([["key",__rt.fn("<lambda>",{names:["item"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(item){return __rt.item(item,0);return null;})]]))));rate=__t8[0];cells=__t8[1];}
key=__rt.call(__rt.b["str"],[number],__rt.kw([]));
{const __t9=Array.from(__rt.iter(__rt.tuple([cells,rate])));__rt.setitem(positions,key,__t9[0]);__rt.setitem(rates,key,__t9[1]);}
__rt.setitem(awards,key,__rt.bin("Mult",__rt.bin("Mult",coin_minor,level),rate));}}
return __rt.call(__rt.b["dict"],[],__rt.kw([["winning_positions",positions],["rates",rates],["base_awards_minor",awards],["base_win_minor",__rt.call(__rt.b["sum"],[__rt.call(__rt.attr(awards,"values"),[],__rt.kw([]))],__rt.kw([]))],["win_minor",__rt.bin("Mult",__rt.call(__rt.b["sum"],[__rt.call(__rt.attr(awards,"values"),[],__rt.kw([]))],__rt.kw([])),multiplier)]]));return null;});
CaptainsBounty=__rt.cls("CaptainsBounty",[MahjongWays2],{"game_id":"captains-bounty","title":"Captain's Bounty","version":"1.0.0","__init__":__rt.fn("__init__",{names:["self", "config_path"],kwonly:[],defaults:{"config_path":null},vararg:null,kwarg:null},function(self,config_path){let c;__rt.setattr(self,"config",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(Path,[__rt.or_(()=>config_path,()=>__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["config.json"],__rt.kw([])))],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
c=__rt.attr(self,"config");
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"coin_sizes_minor"),()=>[3,10,30,90]]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"bet_levels"),()=>__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[1,11],__rt.kw([]))],__rt.kw([]))]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"base_bet_factor"),()=>20]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"normal_multipliers"),()=>[1,2,3,5]]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_multipliers"),()=>[3,6,9,15]]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_trigger"),()=>3]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_base_spins"),()=>10]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_extra_per_scatter"),()=>5]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"max_win_multiplier"),()=>30000]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["set"],[__rt.item(c,"symbol_weights")],__rt.kw([])),()=>__rt.call(__rt.b["set"],[__rt.call(__rt.b["map"],[__rt.b["str"],__rt.call(__rt.b["range"],[9],__rt.kw([]))],__rt.kw([]))],__rt.kw([]))]),()=>__rt.call(__rt.b["any"],[(function*(){let w;for(const __t10 of __rt.iter(__rt.call(__rt.attr(__rt.item(c,"symbol_weights"),"values"),[],__rt.kw([])))){w=__t10;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[w],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["LtE"],[()=>w,()=>0]));}})()],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],["Invalid Captain's Bounty rules"],__rt.kw([]));}
__rt.setattr(self,"ruleset_id",__rt.bin("Add",__rt.bin("Add",__rt.attr(self,"version"),":"),__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[c],__rt.kw([["sort_keys",true]])),"encode"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,16,null))));return null;}),"normalize_bet":__rt.fn("normalize_bet",{names:["self", "payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,payload){if(__rt.truth(__rt.and_(()=>__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([])),()=>__rt.unary("Not",__rt.bin("BitAnd",__rt.set(["coin_minor","cs"]),__rt.call(__rt.attr(payload,"keys"),[],__rt.kw([]))))))){payload=__rt.dict([[null,payload],["coin_minor",30]]);}
if(__rt.truth(__rt.and_(()=>__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([])),()=>__rt.unary("Not",__rt.bin("BitAnd",__rt.set(["level","ml"]),__rt.call(__rt.attr(payload,"keys"),[],__rt.kw([]))))))){payload=__rt.dict([[null,payload],["level",2]]);}
return __rt.call(__rt.attr(__rt.super_(CaptainsBounty,self),"normalize_bet"),[payload],__rt.kw([]));return null;}),"_draw_column":__rt.fn("_draw_column",{names:["self", "rng", "count", "column", "has_scatter"],kwonly:[],defaults:{"has_scatter":false},vararg:null,kwarg:null},function(self,rng,count,column,has_scatter){let _,result,symbol,weights;result=[];
for(const __t11 of __rt.iter(__rt.call(__rt.b["range"],[count],__rt.kw([])))){_=__t11;weights=(()=>{let s;const __out:any[]=[];for(const __t12 of __rt.iter(__rt.call(__rt.b["range"],[9],__rt.kw([])))){s=__t12;__out.push((__rt.truth(__rt.or_(()=>__rt.and_(()=>__rt.compare(["Eq"],[()=>s,()=>0]),()=>__rt.compare(["In"],[()=>column,()=>__rt.tuple([0,4])])),()=>__rt.and_(()=>__rt.compare(["Eq"],[()=>s,()=>1]),()=>has_scatter)))?0:__rt.item(__rt.item(__rt.attr(self,"config"),"symbol_weights"),__rt.call(__rt.b["str"],[s],__rt.kw([])))));}return __out;})();
symbol=__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.call(__rt.b["range"],[9],__rt.kw([]))],__rt.kw([["weights",weights],["k",1]])),0);
__rt.call(__rt.attr(result,"append"),[symbol],__rt.kw([]));
has_scatter=__rt.bin("BitOr",has_scatter,__rt.compare(["Eq"],[()=>symbol,()=>1]));}
return result;return null;}),"_new_board":__rt.fn("_new_board",{names:["self", "rng"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng){return (()=>{let column,s;const __out:any[]=[];for(const __t13 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){column=__t13;for(const __t14 of __rt.iter(__rt.call(__rt.attr(self,"_draw_column"),[rng,3,column],__rt.kw([])))){s=__t14;__out.push(s);}}return __out;})();return null;}),"initial_state":__rt.fn("initial_state",{names:["self", "seed"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,seed){return __rt.call(__rt.b["dict"],[],__rt.kw([["phase","ready"],["sid","0"],["round_id","0"],["ruleset_id",__rt.attr(self,"ruleset_id")],["step",0],["board",__rt.call(__rt.attr(self,"_new_board"),[__rt.call(__rt.attr(random,"Random"),[seed],__rt.kw([]))],__rt.kw([]))],["removed",[]],["bet",__rt.call(__rt.b["dict"],[],__rt.kw([["coin_minor",30],["level",2]]))],["free",null],["multiplier_index",0],["round_award_minor",0],["spin_award_minor",0],["last_event",null]]));return null;}),"step":__rt.fn("step",{names:["self", "state", "bet", "seed", "sid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state,bet,seed,sid){let added,available,board,cascade,column,event,free,free_mode,incoming,index,max_win,multiplier,next_phase,phase,refill,removed,result,retrigger,rng,round_award,scatters,spin_award,start,survivors,total_bet,win;state=__rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));
phase=__rt.item(state,"phase");
start=__rt.compare(["Eq"],[()=>phase,()=>"ready"]);
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",start),()=>__rt.compare(["NotEq"],[()=>__rt.item(state,"ruleset_id"),()=>__rt.attr(self,"ruleset_id")])))){throw __rt.call(ServiceError,["RULESET_CHANGED","Finish the current round first.",409],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",start),()=>__rt.compare(["NotEq"],[()=>__rt.item(state,"bet"),()=>bet])))){throw __rt.call(ServiceError,["BET_LOCKED","Finish the current round before changing bet.",409],__rt.kw([]));}
if(__rt.truth(start)){__rt.call(__rt.attr(state,"update"),[],__rt.kw([["seed",seed],["step",0],["round_id",sid],["bet",bet],["free",null],["round_award_minor",0],["spin_award_minor",0],["ruleset_id",__rt.attr(self,"ruleset_id")]]));}
rng=__rt.call(__rt.attr(random,"Random"),[(__rt.format(__rt.item(state,"seed"),"",-1)+":"+__rt.format(__rt.item(state,"step"),"",-1)+":"+__rt.format(__rt.attr(self,"ruleset_id"),"",-1))],__rt.kw([]));
cascade=__rt.compare(["In"],[()=>phase,()=>__rt.tuple(["paid_cascade","free_cascade"])]);
free_mode=__rt.compare(["In"],[()=>phase,()=>__rt.tuple(["free_start","free_cascade"])]);
incoming=null;
if(__rt.truth(cascade)){{const __t15=Array.from(__rt.iter(__rt.tuple([[],[]])));board=__t15[0];incoming=__t15[1];}
for(const __t16 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){column=__t16;survivors=(()=>{let p;const __out:any[]=[];for(const __t17 of __rt.iter(__rt.call(__rt.b["range"],[__rt.bin("Mult",column,3),__rt.bin("Add",__rt.bin("Mult",column,3),3)],__rt.kw([])))){p=__t17;if(__rt.truth(__rt.compare(["NotIn"],[()=>p,()=>__rt.item(state,"removed")]))){__out.push(__rt.item(__rt.item(state,"board"),p));}}return __out;})();
refill=__rt.call(__rt.attr(self,"_draw_column"),[rng,__rt.bin("Sub",3,__rt.call(__rt.b["len"],[survivors],__rt.kw([]))),column,__rt.compare(["In"],[()=>1,()=>survivors])],__rt.kw([]));
__rt.call(__rt.attr(incoming,"append"),[refill],__rt.kw([]));
__rt.call(__rt.attr(board,"extend"),[__rt.bin("Add",refill,survivors)],__rt.kw([]));}}else{board=__rt.call(__rt.attr(self,"_new_board"),[rng],__rt.kw([]));}
index=(__rt.truth(cascade)?__rt.call(__rt.b["min"],[__rt.bin("Add",__rt.item(state,"multiplier_index"),1),3],__rt.kw([])):0);
multiplier=__rt.item(__rt.item(__rt.attr(self,"config"),(__rt.truth(free_mode)?"free_multipliers":"normal_multipliers")),index);
result=__rt.call(evaluate,[board,__rt.item(bet,"coin_minor"),__rt.item(bet,"level"),multiplier],__rt.kw([]));
total_bet=__rt.bin("Mult",__rt.bin("Mult",__rt.item(bet,"coin_minor"),__rt.item(bet,"level")),20);
available=__rt.bin("Sub",__rt.bin("Mult",total_bet,__rt.item(__rt.attr(self,"config"),"max_win_multiplier")),__rt.item(state,"round_award_minor"));
win=__rt.call(__rt.b["min"],[__rt.item(result,"win_minor"),__rt.call(__rt.b["max"],[0,available],__rt.kw([]))],__rt.kw([]));
max_win=__rt.compare(["GtE"],[()=>win,()=>available]);
free=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.item(state,"free")],__rt.kw([]));
if(__rt.truth(free_mode)){__rt.setitem(free,"remaining",__rt.bin("Sub",__rt.item(free,"remaining"),__rt.call(__rt.b["int"],[__rt.compare(["Eq"],[()=>phase,()=>"free_start"])],__rt.kw([]))));
__rt.setitem(free,"award_minor",__rt.bin("Add",__rt.item(free,"award_minor"),win));
__rt.setitem(free,"added",0);}
scatters=__rt.call(__rt.attr(board,"count"),[1],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",win),()=>__rt.compare(["GtE"],[()=>scatters,()=>3])))){added=__rt.bin("Add",10,__rt.bin("Mult",__rt.bin("Sub",scatters,3),5));
retrigger=__rt.compare(["IsNot"],[()=>free,()=>null]);
if(__rt.truth(__rt.compare(["Is"],[()=>free,()=>null]))){free=__rt.call(__rt.b["dict"],[],__rt.kw([["remaining",0],["total",0],["added",0],["award_minor",0]]));}
__rt.setitem(free,"remaining",__rt.bin("Add",__rt.item(free,"remaining"),added));
__rt.setitem(free,"total",__rt.bin("Add",__rt.item(free,"total"),added));
__rt.setitem(free,"added",(__rt.truth(retrigger)?added:0));}
if(__rt.truth(__rt.and_(()=>max_win,()=>free))){__rt.setitem(free,"remaining",0);}
next_phase=(__rt.truth(max_win)?"ready":(__rt.truth(win)?(__rt.truth(free_mode)?"free_cascade":"paid_cascade"):(__rt.truth(__rt.and_(()=>free,()=>__rt.item(free,"remaining")))?"free_start":"ready")));
removed=__rt.call(__rt.b["sorted"],[(()=>{let cells,p;const __out:any[]=[];for(const __t18 of __rt.iter(__rt.call(__rt.attr(__rt.item(result,"winning_positions"),"values"),[],__rt.kw([])))){cells=__t18;for(const __t19 of __rt.iter(cells)){p=__t19;__out.push(p);}}return __rt.set(__out);})()],__rt.kw([]));
spin_award=__rt.bin("Add",(__rt.truth(cascade)?__rt.item(state,"spin_award_minor"):0),win);
round_award=__rt.bin("Add",__rt.item(state,"round_award_minor"),win);
event=__rt.call(__rt.b["dict"],[result],__rt.kw([["sid",sid],["round_id",__rt.item(state,"round_id")],["phase",phase],["next_phase",next_phase],["bet",bet],["board",board],["removed",removed],["refills",incoming],["multiplier",multiplier],["base_bet_minor",total_bet],["debit_minor",(__rt.truth(start)?total_bet:0)],["win_minor",win],["spin_award_minor",spin_award],["round_award_minor",round_award],["free",free],["free_mode",free_mode],["scatter_count",scatters],["max_win",max_win],["ruleset_id",__rt.attr(self,"ruleset_id")]]));
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["sid",sid],["phase",next_phase],["board",board],["removed",removed],["free",free],["multiplier_index",index],["step",__rt.bin("Add",__rt.item(state,"step"),1)],["round_award_minor",round_award],["spin_award_minor",spin_award],["last_event",event]]));
return __rt.call(Outcome,[state,event,__rt.item(event,"debit_minor"),win],__rt.kw([]));return null;})});
