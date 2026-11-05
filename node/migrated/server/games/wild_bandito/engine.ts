// Migrated from server/games/wild_bandito/engine.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
import * as __m0 from "../mahjong_ways2/engine.js";
const __file__=__rt.sourcePath("server/games/wild_bandito/engine.py");
export let MahjongWays2:any,Outcome:any,PAYTABLE:any,Path:any,ServiceError:any,VISIBLE:any,WildBandito:any,copy:any,evaluate:any,hashlib:any,json:any,math:any,random:any;

copy=__rt.modules["copy"];
hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
math=__rt.modules["math"];
random=__rt.modules["random"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
Outcome=__rt.attr(__rt.modules["server.core.contracts"],"Outcome");
ServiceError=__rt.attr(__rt.modules["server.core.contracts"],"ServiceError");
MahjongWays2=__rt.attr(__m0,"MahjongWays2");
PAYTABLE=__rt.dict([[2,__rt.dict([[3,10],[4,25],[5,50]])],[3,__rt.dict([[3,8],[4,20],[5,40]])],[4,__rt.dict([[3,6],[4,15],[5,30]])],[5,__rt.dict([[3,5],[4,10],[5,15]])],[6,__rt.dict([[3,3],[4,5],[5,12]])],[7,__rt.dict([[3,3],[4,5],[5,12]])],[8,__rt.dict([[3,2],[4,4],[5,10]])],[9,__rt.dict([[3,1],[4,3],[5,6]])],[10,__rt.dict([[3,1],[4,3],[5,6]])]]);
VISIBLE=(()=>{let c;const __out:any[]=[];for(const __t1 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){c=__t1;__out.push(__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[__rt.bin("Add",__rt.bin("Mult",c,5),1),__rt.bin("Add",__rt.bin("Mult",c,5),5)],__rt.kw([]))],__rt.kw([])));}return __out;})();
evaluate=__rt.fn("evaluate",{names:["board", "coin_minor", "level", "multiplier"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(board,coin_minor,level,multiplier){let awards,column,hits,key,matches,positions,rates,symbol,table,ways;if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[board],__rt.kw([])),()=>25]),()=>__rt.call(__rt.b["any"],[(function*(){let v;for(const __t2 of __rt.iter(board)){v=__t2;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[v],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>v,()=>10])));}})()],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],["Expected 25 symbols"],__rt.kw([]));}
{const __t3=Array.from(__rt.iter(__rt.tuple([__rt.dict([]),__rt.dict([]),__rt.dict([]),__rt.dict([])])));positions=__t3[0];ways=__t3[1];rates=__t3[2];awards=__t3[3];}
for(const __t4 of __rt.iter(__rt.call(__rt.attr(PAYTABLE,"items"),[],__rt.kw([])))){{const __t5=Array.from(__rt.iter(__t4));symbol=__t5[0];table=__t5[1];}hits=[];
for(const __t6 of __rt.iter(VISIBLE)){column=__t6;matches=(()=>{let p;const __out:any[]=[];for(const __t7 of __rt.iter(column)){p=__t7;if(__rt.truth(__rt.compare(["In"],[()=>__rt.item(board,p),()=>__rt.tuple([0,symbol])]))){__out.push(p);}}return __out;})();
if(__rt.truth(__rt.unary("Not",matches))){break;}
__rt.call(__rt.attr(hits,"append"),[matches],__rt.kw([]));}
if(__rt.truth(__rt.compare(["GtE"],[()=>__rt.call(__rt.b["len"],[hits],__rt.kw([])),()=>3]))){key=__rt.call(__rt.b["str"],[symbol],__rt.kw([]));
__rt.setitem(positions,key,(()=>{let cells,p;const __out:any[]=[];for(const __t8 of __rt.iter(hits)){cells=__t8;for(const __t9 of __rt.iter(cells)){p=__t9;__out.push(p);}}return __out;})());
__rt.setitem(ways,key,__rt.call(__rt.attr(math,"prod"),[__rt.call(__rt.b["map"],[__rt.b["len"],hits],__rt.kw([]))],__rt.kw([])));
__rt.setitem(rates,key,__rt.item(table,__rt.call(__rt.b["len"],[hits],__rt.kw([]))));
__rt.setitem(awards,key,__rt.bin("Mult",__rt.bin("Mult",__rt.bin("Mult",coin_minor,level),__rt.item(ways,key)),__rt.item(rates,key)));}}
return __rt.call(__rt.b["dict"],[],__rt.kw([["winning_positions",positions],["ways",ways],["rates",rates],["base_awards_minor",awards],["win_minor",__rt.bin("Mult",__rt.call(__rt.b["sum"],[__rt.call(__rt.attr(awards,"values"),[],__rt.kw([]))],__rt.kw([])),multiplier)]]));return null;});
WildBandito=__rt.cls("WildBandito",[MahjongWays2],{"game_id":"wild-bandito","title":"Wild Bandito","version":"1.0.0","__init__":__rt.fn("__init__",{names:["self", "config_path"],kwonly:[],defaults:{"config_path":null},vararg:null,kwarg:null},function(self,config_path){let c;__rt.setattr(self,"config",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(Path,[__rt.or_(()=>config_path,()=>__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["config.json"],__rt.kw([])))],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
c=__rt.attr(self,"config");
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"coin_sizes_minor"),()=>[3,10,30,90]]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"bet_levels"),()=>__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[1,11],__rt.kw([]))],__rt.kw([]))]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"base_bet_factor"),()=>20]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_trigger"),()=>3]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_base_spins"),()=>12]),()=>__rt.compare(["NotEq"],[()=>__rt.item(c,"free_extra_per_scatter"),()=>2]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>__rt.item(c,"gold_probability"),()=>1])),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["set"],[__rt.item(c,"symbol_weights")],__rt.kw([])),()=>__rt.call(__rt.b["set"],[__rt.call(__rt.b["map"],[__rt.b["str"],__rt.call(__rt.b["range"],[1,11],__rt.kw([]))],__rt.kw([]))],__rt.kw([]))]),()=>__rt.call(__rt.b["any"],[(function*(){let w;for(const __t10 of __rt.iter(__rt.call(__rt.attr(__rt.item(c,"symbol_weights"),"values"),[],__rt.kw([])))){w=__t10;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[w],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["LtE"],[()=>w,()=>0]));}})()],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],["Invalid Wild Bandito rules"],__rt.kw([]));}
__rt.setattr(self,"ruleset_id",__rt.bin("Add",__rt.bin("Add",__rt.attr(self,"version"),":"),__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[c],__rt.kw([["sort_keys",true]])),"encode"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,16,null))));return null;}),"normalize_bet":__rt.fn("normalize_bet",{names:["self", "payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,payload){payload=(__rt.truth(__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([])))?__rt.call(__rt.b["dict"],[payload],__rt.kw([])):payload);
if(__rt.truth(__rt.and_(()=>__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([])),()=>__rt.unary("Not",__rt.bin("BitAnd",__rt.set(["cs","coin_minor"]),__rt.call(__rt.attr(payload,"keys"),[],__rt.kw([]))))))){__rt.setitem(payload,"coin_minor",10);}
return __rt.call(__rt.attr(__rt.super_(WildBandito,self),"normalize_bet"),[payload],__rt.kw([]));return null;}),"_new_board":__rt.fn("_new_board",{names:["self", "rng"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng){return (()=>{let _,s;const __out:any[]=[];for(const __t11 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){_=__t11;for(const __t12 of __rt.iter(__rt.call(__rt.attr(self,"_draw_column"),[rng,5],__rt.kw([])))){s=__t12;__out.push(s);}}return __out;})();return null;}),"_gold":__rt.fn("_gold",{names:["self", "rng", "board", "candidates", "gold", "serial", "free_mode"],kwonly:[],defaults:{"free_mode":false},vararg:null,kwarg:null},function(self,rng,board,candidates,gold,serial,free_mode){let added,col,pos;added=(()=>{let _;const __out:any[]=[];for(const __t13 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){_=__t13;__out.push([]);}return __out;})();
for(const __t14 of __rt.iter(candidates)){pos=__t14;col=__rt.bin("FloorDiv",pos,5);
if(__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>col,()=>__rt.tuple([1,2,3])]),()=>__rt.compare(["GtE"],[()=>__rt.item(board,pos),()=>2]),()=>__rt.or_(()=>__rt.and_(()=>free_mode,()=>__rt.compare(["Eq"],[()=>col,()=>2])),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"gold_probability")]))))){serial=__rt.bin("Add",serial,1);
__rt.setitem(gold,__rt.call(__rt.b["str"],[serial],__rt.kw([])),pos);
__rt.call(__rt.attr(__rt.item(added,col),"append"),[__rt.bin("Mod",pos,5)],__rt.kw([]));}}
return __rt.tuple([gold,serial,added]);return null;}),"initial_state":__rt.fn("initial_state",{names:["self", "seed"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,seed){return __rt.call(__rt.b["dict"],[],__rt.kw([["phase","ready"],["sid","0"],["round_id","0"],["step",0],["ruleset_id",__rt.attr(self,"ruleset_id")],["board",__rt.call(__rt.attr(self,"_new_board"),[__rt.call(__rt.attr(random,"Random"),[seed],__rt.kw([]))],__rt.kw([]))],["gold",__rt.dict([])],["removed",[]],["converted",[]],["gold_serial",0],["bet",__rt.dict([["coin_minor",10],["level",2]])],["free",null],["multiplier",1],["combo",0],["round_award_minor",0],["spin_award_minor",0],["counts",__rt.dict([])],["last_event",null]]));return null;}),"step":__rt.fn("step",{names:["self", "state", "bet", "seed", "sid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state,bet,seed,sid){let _,added,after,board,broken,candidates,cascade,col,combo,converted,counts,debit,event,free,free_mode,gold,incoming,key,multiplier,new_gold,next_phase,old,phase,refills,remaining_gold,removed,result,rng,round_award,scatter,serial,spin_award,start,survivors,total_bet,transformed,win,won;state=__rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));
phase=__rt.item(state,"phase");
start=__rt.compare(["Eq"],[()=>phase,()=>"ready"]);
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",start),()=>__rt.compare(["NotEq"],[()=>__rt.item(state,"ruleset_id"),()=>__rt.attr(self,"ruleset_id")])))){throw __rt.call(ServiceError,["RULESET_CHANGED","Finish the current round first.",409],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",start),()=>__rt.compare(["NotEq"],[()=>bet,()=>__rt.item(state,"bet")])))){throw __rt.call(ServiceError,["BET_LOCKED","Finish the current round before changing bet.",409],__rt.kw([]));}
if(__rt.truth(start)){__rt.call(__rt.attr(state,"update"),[],__rt.kw([["seed",seed],["step",0],["ruleset_id",__rt.attr(self,"ruleset_id")],["round_id",sid],["bet",bet],["round_award_minor",0],["spin_award_minor",0],["free",null],["counts",__rt.dict([])]]));}
rng=__rt.call(__rt.attr(random,"Random"),[(__rt.format(__rt.item(state,"seed"),"",-1)+":"+__rt.format(__rt.item(state,"step"),"",-1)+":"+__rt.format(__rt.attr(self,"ruleset_id"),"",-1))],__rt.kw([]));
cascade=__rt.compare(["In"],[()=>phase,()=>__rt.tuple(["paid_cascade","free_cascade"])]);
free_mode=__rt.compare(["In"],[()=>phase,()=>__rt.tuple(["free_start","free_cascade"])]);
{const __t15=Array.from(__rt.iter(__rt.tuple([null,null,[]])));refills=__t15[0];new_gold=__t15[1];broken=__t15[2];}
if(__rt.truth(cascade)){{const __t16=Array.from(__rt.iter(__rt.tuple([[],__rt.dict([]),[],[]])));board=__t16[0];gold=__t16[1];candidates=__t16[2];refills=__t16[3];}
removed=__rt.call(__rt.b["set"],[__rt.item(state,"removed")],__rt.kw([]));
for(const __t17 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){col=__t17;survivors=(()=>{let p,v;const __out:any[]=[];for(const __t18 of __rt.iter(__rt.call(__rt.b["enumerate"],[__rt.item(state,"board")],__rt.kw([])))){{const __t19=Array.from(__rt.iter(__t18));p=__t19[0];v=__t19[1];}if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.bin("FloorDiv",p,5),()=>col]),()=>__rt.compare(["NotIn"],[()=>p,()=>removed])))){__out.push(v);}}return __out;})();
incoming=__rt.call(__rt.attr(self,"_draw_column"),[rng,__rt.bin("Sub",5,__rt.call(__rt.b["len"],[survivors],__rt.kw([]))),__rt.compare(["In"],[()=>1,()=>survivors])],__rt.kw([]));
__rt.call(__rt.attr(refills,"append"),[incoming],__rt.kw([]));
__rt.call(__rt.attr(candidates,"extend"),[__rt.call(__rt.b["range"],[__rt.bin("Mult",col,5),__rt.bin("Add",__rt.bin("Mult",col,5),__rt.call(__rt.b["len"],[incoming],__rt.kw([])))],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(board,"extend"),[__rt.bin("Add",incoming,survivors)],__rt.kw([]));}
for(const __t20 of __rt.iter(__rt.call(__rt.attr(__rt.item(state,"gold"),"items"),[],__rt.kw([])))){{const __t21=Array.from(__rt.iter(__t20));key=__t21[0];old=__t21[1];}__rt.setitem(gold,key,__rt.bin("Add",old,__rt.call(__rt.b["sum"],[(function*(){let p;for(const __t22 of __rt.iter(removed)){p=__t22;yield __rt.and_(()=>__rt.compare(["Gt"],[()=>p,()=>old]),()=>__rt.compare(["Eq"],[()=>__rt.bin("FloorDiv",p,5),()=>__rt.bin("FloorDiv",old,5)]));}})()],__rt.kw([]))));}
broken=__rt.item(state,"converted");
{const __t23=Array.from(__rt.iter(__rt.call(__rt.attr(self,"_gold"),[rng,board,candidates,gold,__rt.item(state,"gold_serial"),free_mode],__rt.kw([]))));gold=__t23[0];serial=__t23[1];new_gold=__t23[2];}}else{board=__rt.call(__rt.attr(self,"_new_board"),[rng],__rt.kw([]));
{const __t24=Array.from(__rt.iter(__rt.call(__rt.attr(self,"_gold"),[rng,board,__rt.call(__rt.b["range"],[25],__rt.kw([])),__rt.dict([]),0,free_mode],__rt.kw([]))));gold=__t24[0];serial=__t24[1];_=__t24[2];}}
multiplier=(__rt.truth(cascade)?__rt.bin("Add",__rt.item(state,"multiplier"),1):(__rt.truth(free_mode)?__rt.item(__rt.item(state,"free"),"multiplier"):1));
result=__rt.call(evaluate,[board,__rt.item(bet,"coin_minor"),__rt.item(bet,"level"),multiplier],__rt.kw([]));
win=__rt.item(result,"win_minor");
won=(()=>{let group,p;const __out:any[]=[];for(const __t25 of __rt.iter(__rt.call(__rt.attr(__rt.item(result,"winning_positions"),"values"),[],__rt.kw([])))){group=__t25;for(const __t26 of __rt.iter(group)){p=__t26;__out.push(p);}}return __rt.set(__out);})();
converted=(()=>{let k,p;const __out:any[]=[];for(const __t27 of __rt.iter(__rt.call(__rt.attr(gold,"items"),[],__rt.kw([])))){{const __t28=Array.from(__rt.iter(__t27));k=__t28[0];p=__t28[1];}if(__rt.truth(__rt.compare(["In"],[()=>p,()=>won]))){__out.push(__rt.call(__rt.b["int"],[k],__rt.kw([])));}}return __out;})();
transformed=(()=>{let k;const __out:any[]=[];for(const __t29 of __rt.iter(converted)){k=__t29;__out.push(__rt.item(gold,__rt.call(__rt.b["str"],[k],__rt.kw([]))));}return __rt.set(__out);})();
removed=__rt.call(__rt.b["sorted"],[__rt.bin("Sub",won,transformed)],__rt.kw([]));
after=(()=>{let p,symbol;const __out:any[]=[];for(const __t30 of __rt.iter(__rt.call(__rt.b["enumerate"],[board],__rt.kw([])))){{const __t31=Array.from(__rt.iter(__t30));p=__t31[0];symbol=__t31[1];}__out.push((__rt.truth(__rt.compare(["In"],[()=>p,()=>transformed]))?0:symbol));}return __out;})();
remaining_gold=(()=>{let k,p;const __out:any[]=[];for(const __t32 of __rt.iter(__rt.call(__rt.attr(gold,"items"),[],__rt.kw([])))){{const __t33=Array.from(__rt.iter(__t32));k=__t33[0];p=__t33[1];}if(__rt.truth(__rt.compare(["NotIn"],[()=>p,()=>transformed]))){__out.push([k,p]);}}return __rt.dict(__out);})();
scatter=__rt.call(__rt.b["sum"],[(function*(){let column,p;for(const __t34 of __rt.iter(VISIBLE)){column=__t34;for(const __t35 of __rt.iter(column)){p=__t35;yield __rt.compare(["Eq"],[()=>__rt.item(board,p),()=>1]);}}})()],__rt.kw([]));
free=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.item(state,"free")],__rt.kw([]));
if(__rt.truth(free_mode)){__rt.setitem(free,"remaining",__rt.bin("Sub",__rt.item(free,"remaining"),__rt.call(__rt.b["int"],[__rt.compare(["Eq"],[()=>phase,()=>"free_start"])],__rt.kw([]))));
__rt.setitem(free,"award_minor",__rt.bin("Add",__rt.item(free,"award_minor"),win));
__rt.setitem(free,"added",0);
__rt.setitem(free,"multiplier",__rt.bin("Add",multiplier,__rt.call(__rt.b["int"],[__rt.compare(["Gt"],[()=>win,()=>0])],__rt.kw([]))));}
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",win),()=>__rt.compare(["GtE"],[()=>scatter,()=>3])))){added=__rt.bin("Add",12,__rt.bin("Mult",__rt.bin("Sub",scatter,3),2));
if(__rt.truth(__rt.compare(["Is"],[()=>free,()=>null]))){free=__rt.call(__rt.b["dict"],[],__rt.kw([["remaining",0],["total",0],["award_minor",0],["added",0],["multiplier",1]]));}
__rt.setitem(free,"remaining",__rt.bin("Add",__rt.item(free,"remaining"),added));
__rt.setitem(free,"total",__rt.bin("Add",__rt.item(free,"total"),added));
__rt.setitem(free,"added",added);}
next_phase=(__rt.truth(win)?(__rt.truth(free_mode)?"free_cascade":"paid_cascade"):(__rt.truth(__rt.and_(()=>free,()=>__rt.item(free,"remaining")))?"free_start":"ready"));
total_bet=__rt.bin("Mult",__rt.bin("Mult",__rt.item(bet,"coin_minor"),__rt.item(bet,"level")),20);
debit=(__rt.truth(start)?total_bet:0);
round_award=__rt.bin("Add",__rt.item(state,"round_award_minor"),win);
spin_award=__rt.bin("Add",(__rt.truth(cascade)?__rt.item(state,"spin_award_minor"):0),win);
combo=(__rt.truth(win)?__rt.bin("Add",(__rt.truth(cascade)?__rt.item(state,"combo"):0),1):0);
counts=__rt.item(state,"counts");
if(__rt.truth(__rt.unary("Not",start))){__rt.setitem(counts,phase,__rt.bin("Add",__rt.call(__rt.attr(counts,"get"),[phase,0],__rt.kw([])),1));}
event=__rt.call(__rt.b["dict"],[result],__rt.kw([["sid",sid],["round_id",__rt.item(state,"round_id")],["phase",phase],["next_phase",next_phase],["bet",bet],["base_bet_minor",total_bet],["debit_minor",debit],["board_before",board],["board_after",after],["gold_before",gold],["gold_after",remaining_gold],["removed",removed],["refills",refills],["new_gold",new_gold],["broken_gold",broken],["scatter_count",scatter],["multiplier",multiplier],["free",free],["round_award_minor",round_award],["spin_award_minor",spin_award],["combo",combo],["counts",__rt.call(__rt.attr(copy,"deepcopy"),[counts],__rt.kw([]))],["ruleset_id",__rt.attr(self,"ruleset_id")]]));
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["phase",next_phase],["sid",sid],["step",__rt.bin("Add",__rt.item(state,"step"),1)],["board",after],["gold",remaining_gold],["gold_serial",serial],["removed",removed],["converted",converted],["multiplier",multiplier],["combo",combo],["free",free],["round_award_minor",round_award],["spin_award_minor",spin_award],["last_event",event]]));
return __rt.call(Outcome,[state,event,debit,win],__rt.kw([]));return null;})});
