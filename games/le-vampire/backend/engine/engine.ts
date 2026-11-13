// Migrated from py/games/le_vampire/engine.py. Runtime is Node.js only.
import * as __rt from "../../../../other/shared/compat/runtime.js";
import * as __m0 from "../../../wicked-grin/backend/engine/engine.js";
const __file__=__rt.sourcePath("py/games/le_vampire/engine.py");
export let COINS:any,LeVampire:any,PAYING:any,Path:any,WickedGrin:any,action:any,adjacent:any,decode_grid:any,encode_grid:any,hashlib:any,json:any,mask:any,order:any,random:any;

hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
random=__rt.modules["random"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
WickedGrin=__rt.attr(__m0,"WickedGrin");
action=__rt.attr(__m0,"action");
COINS=[2,4,10,20,30,40,50,60,70,80,90,100,200,300,400,500,1000,1500,2500,5000];
PAYING=__rt.bin("Add",__rt.call(__rt.b["tuple"],[__rt.call(__rt.b["range"],[1,9],__rt.kw([]))],__rt.kw([])),__rt.call(__rt.b["tuple"],[__rt.call(__rt.b["range"],[15,19],__rt.kw([]))],__rt.kw([])));
encode_grid=__rt.fn("encode_grid",{names:["grid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(grid){return __rt.bin("Add",".-",__rt.call(__rt.attr("","join"),[(function*(){let v;for(const __t1 of __rt.iter(grid)){v=__t1;yield __rt.call(__rt.b["chr"],[__rt.bin("Add",__rt.call(__rt.b["int"],[v],__rt.kw([])),40)],__rt.kw([]));}})()],__rt.kw([])));return null;});
decode_grid=__rt.fn("decode_grid",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[value,__rt.b["str"]],__rt.kw([]))),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[value],__rt.kw([])),()=>32]),()=>__rt.compare(["NotEq"],[()=>__rt.item(value,__rt.slice(null,2,null)),()=>".-"])))){throw __rt.call(__rt.b["ValueError"],["Expected a six by five grid"],__rt.kw([]));}
return (()=>{let c;const __out:any[]=[];for(const __t2 of __rt.iter(__rt.item(value,__rt.slice(2,null,null)))){c=__t2;__out.push(__rt.bin("Sub",__rt.call(__rt.b["ord"],[c],__rt.kw([])),40));}return __out;})();return null;});
mask=__rt.fn("mask",{names:["positions"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(positions){positions=__rt.call(__rt.b["set"],[positions],__rt.kw([]));
return __rt.call(__rt.attr("","join"),[(function*(){let p;for(const __t3 of __rt.iter(__rt.call(__rt.b["range"],[30],__rt.kw([])))){p=__t3;yield (__rt.truth(__rt.compare(["In"],[()=>p,()=>positions]))?"1":"0");}})()],__rt.kw([]));return null;});
order=__rt.fn("order",{names:["p"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(p){return __rt.tuple([__rt.bin("Mod",p,6),__rt.bin("FloorDiv",p,6)]);return null;});
adjacent=__rt.fn("adjacent",{names:["p", "q"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(p,q){return __rt.and_(()=>__rt.compare(["LtE"],[()=>__rt.call(__rt.b["max"],[__rt.call(__rt.b["abs"],[__rt.bin("Sub",__rt.bin("Mod",p,6),__rt.bin("Mod",q,6))],__rt.kw([])),__rt.call(__rt.b["abs"],[__rt.bin("Sub",__rt.bin("FloorDiv",p,6),__rt.bin("FloorDiv",q,6))],__rt.kw([]))],__rt.kw([])),()=>1]),()=>__rt.compare(["NotEq"],[()=>p,()=>q]));return null;});
LeVampire=__rt.cls("LeVampire",[WickedGrin],{"game_id":"le-vampire","title":"Le Vampire","version":"1.0.0","__init__":__rt.fn("__init__",{names:["self", "config"],kwonly:[],defaults:{"config":null},vararg:null,kwarg:null},function(self,config){__rt.setattr(self,"config",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(Path,[__rt.or_(()=>config,()=>__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["config.json"],__rt.kw([])))],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(self,"ruleset_id",__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[__rt.dict([["engine",__rt.attr(self,"version")],["config",__rt.attr(self,"config")]])],__rt.kw([["sort_keys",true]])),"encode"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,20,null)));return null;}),"clusters":__rt.fn("clusters",{names:["self", "grid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,grid){let cells,found,more,near,p,symbol,todo,unseen;
found=[];
for(const __t4 of __rt.iter(PAYING)){symbol=__t4;unseen=(()=>{let i,v;const __out:any[]=[];for(const __t5 of __rt.iter(__rt.call(__rt.b["enumerate"],[grid],__rt.kw([])))){{const __t6=Array.from(__rt.iter(__t5));i=__t6[0];v=__t6[1];}if(__rt.truth(__rt.compare(["In"],[()=>v,()=>__rt.tuple([0,symbol])]))){__out.push(i);}}return __rt.set(__out);})();
while(__rt.truth(unseen)){todo=[__rt.call(__rt.b["min"],[unseen],__rt.kw([["key",order]]))];
cells=__rt.call(__rt.b["set"],[todo],__rt.kw([]));
__rt.call(__rt.attr(unseen,"difference_update"),[cells],__rt.kw([]));
while(__rt.truth(todo)){p=__rt.call(__rt.attr(todo,"pop"),[],__rt.kw([]));
near=(()=>{let q;const __out:any[]=[];for(const __t7 of __rt.iter(__rt.tuple([__rt.bin("Sub",p,6),__rt.bin("Add",p,6),__rt.bin("Sub",p,1),__rt.bin("Add",p,1)]))){q=__t7;if(__rt.truth(__rt.and_(()=>__rt.compare(["LtE", "Lt"],[()=>0,()=>q,()=>30]),()=>__rt.compare(["Eq"],[()=>__rt.bin("Add",__rt.call(__rt.b["abs"],[__rt.bin("Sub",__rt.bin("Mod",q,6),__rt.bin("Mod",p,6))],__rt.kw([])),__rt.call(__rt.b["abs"],[__rt.bin("Sub",__rt.bin("FloorDiv",q,6),__rt.bin("FloorDiv",p,6))],__rt.kw([]))),()=>1])))){__out.push(q);}}return __rt.set(__out);})();
more=__rt.bin("BitAnd",near,unseen);
__rt.call(__rt.attr(unseen,"difference_update"),[more],__rt.kw([]));
__rt.call(__rt.attr(cells,"update"),[more],__rt.kw([]));
__rt.call(__rt.attr(todo,"extend"),[more],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.compare(["GtE"],[()=>__rt.call(__rt.b["len"],[cells],__rt.kw([])),()=>5]),()=>__rt.call(__rt.b["any"],[(function*(){let p;for(const __t8 of __rt.iter(cells)){p=__t8;yield __rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>symbol]);}})()],__rt.kw([]))))){__rt.call(__rt.attr(found,"append"),[__rt.tuple([symbol,cells])],__rt.kw([]));}}}
return __rt.call(__rt.b["sorted"],[found],__rt.kw([["key",__rt.fn("<lambda>",{names:["item"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(item){return __rt.tuple([__rt.call(__rt.b["min"],[__rt.call(__rt.b["map"],[order,__rt.item(item,1)],__rt.kw([]))],__rt.kw([])),__rt.item(item,0)]);return null;})]]));return null;}),"payout":__rt.fn("payout",{names:["self", "symbol", "count", "bet"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,symbol,count,bet){let tier;tier=(__rt.truth(__rt.compare(["Eq"],[()=>count,()=>5]))?0:(__rt.truth(__rt.compare(["Lt"],[()=>count,()=>8]))?1:(__rt.truth(__rt.compare(["Lt"],[()=>count,()=>10]))?2:(__rt.truth(__rt.compare(["Lt"],[()=>count,()=>12]))?3:(__rt.truth(__rt.compare(["Lt"],[()=>count,()=>14]))?4:5)))));
return __rt.bin("FloorDiv",__rt.bin("Mult",bet,__rt.item(__rt.item(__rt.item(__rt.attr(self,"config"),"payouts"),__rt.call(__rt.b["str"],[symbol],__rt.kw([]))),tier)),5);return null;}),"evaluate":__rt.fn("evaluate",{names:["self", "grid", "bet"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,grid,bet){return (()=>{let cells,s;const __out:any[]=[];for(const __t9 of __rt.iter(__rt.call(__rt.attr(self,"clusters"),[grid],__rt.kw([])))){{const __t10=Array.from(__rt.iter(__t9));s=__t10[0];cells=__t10[1];}__out.push(__rt.call(action,["gridwin"],__rt.kw([["symbol",__rt.call(__rt.b["str"],[s],__rt.kw([]))],["count",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[cells],__rt.kw([]))],__rt.kw([]))],["mask",__rt.call(mask,[cells],__rt.kw([]))],["winAmount",__rt.call(__rt.b["str"],[__rt.call(__rt.attr(self,"payout"),[s,__rt.call(__rt.b["len"],[cells],__rt.kw([])),bet],__rt.kw([]))],__rt.kw([]))]])));}return __out;})();return null;}),"resolve_special":__rt.fn("resolve_special",{names:["self", "grid", "gold", "blood", "rng", "bet", "minimum", "limit"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,grid,gold,blood,rng,bet,minimum,limit){let actions,area,bags,candidate,candidates,cfg,clovers,collected,cycle,hits,local,mult,p,pots,q,refill,reveal,used,values,win;
grid=__rt.call(__rt.b["list"],[grid],__rt.kw([]));
area=__rt.bin("BitOr",__rt.call(__rt.b["set"],[gold],__rt.kw([])),__rt.call(__rt.b["set"],[blood],__rt.kw([])));
values=__rt.dict([]);
used=__rt.call(__rt.b["set"],[],__rt.kw([]));
actions=[];
cfg=__rt.attr(self,"config");
reveal=__rt.fn("reveal",{names:["cells", "local"],kwonly:[],defaults:{"local":false},vararg:null,kwarg:null},function(cells,local){let floor,i,indices,p,pick,weights;for(const __t11 of __rt.iter(__rt.call(__rt.b["sorted"],[cells],__rt.kw([["key",order]])))){p=__t11;__rt.call(__rt.attr(values,"pop"),[p,null],__rt.kw([]));
__rt.call(__rt.attr(used,"discard"),[p],__rt.kw([]));
pick=__rt.call(__rt.attr(rng,"random"),[],__rt.kw([]));
weights=__rt.item(cfg,"special_probabilities");
if(__rt.truth(__rt.compare(["Lt"],[()=>pick,()=>__rt.item(weights,0)]))){__rt.setitem(grid,p,41);}else{if(__rt.truth(__rt.compare(["Lt"],[()=>pick,()=>__rt.call(__rt.b["sum"],[__rt.item(weights,__rt.slice(null,2,null))],__rt.kw([]))]))){__rt.setitem(grid,p,42);}else{if(__rt.truth(__rt.compare(["Lt"],[()=>pick,()=>__rt.call(__rt.b["sum"],[__rt.item(weights,__rt.slice(null,3,null))],__rt.kw([]))]))){__rt.setitem(grid,p,44);}else{if(__rt.truth(__rt.compare(["Lt"],[()=>pick,()=>__rt.call(__rt.b["sum"],[weights],__rt.kw([]))]))){__rt.setitem(grid,p,43);}else{floor=__rt.call(__rt.b["max"],[minimum,(__rt.truth(__rt.compare(["In"],[()=>p,()=>blood]))?50:0)],__rt.kw([]));
indices=(()=>{let i,v;const __out:any[]=[];for(const __t12 of __rt.iter(__rt.call(__rt.b["enumerate"],[COINS],__rt.kw([])))){{const __t13=Array.from(__rt.iter(__t12));i=__t13[0];v=__t13[1];}if(__rt.truth(__rt.compare(["GtE"],[()=>v,()=>floor]))){__out.push(i);}}return __out;})();
i=__rt.item(__rt.call(__rt.attr(rng,"choices"),[indices],__rt.kw([["weights",(()=>{let i;const __out:any[]=[];for(const __t14 of __rt.iter(indices)){i=__t14;__out.push(__rt.item(__rt.item(cfg,"coin_weights"),i));}return __out;})()]])),0);
__rt.setitem(grid,p,__rt.bin("Add",19,i));
__rt.setitem(values,p,__rt.item(COINS,i));}}}}}
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,[(__rt.truth(local)?"localReplace":"replace")],__rt.kw([["g",__rt.call(encode_grid,[grid],__rt.kw([]))],["goldMask",__rt.call(mask,[__rt.bin("Sub",__rt.call(__rt.b["set"],[cells],__rt.kw([])),__rt.call(__rt.b["set"],[blood],__rt.kw([])))],__rt.kw([]))],["bloodMask",__rt.call(mask,[__rt.bin("BitAnd",__rt.call(__rt.b["set"],[cells],__rt.kw([])),__rt.call(__rt.b["set"],[blood],__rt.kw([])))],__rt.kw([]))]]))],__rt.kw([]));return null;});
if(__rt.truth(__rt.unary("Not",area))){return __rt.tuple([[],0]);}
__rt.call(reveal,[area],__rt.kw([]));
let __t15=true;for(const __t16 of __rt.iter(__rt.call(__rt.b["range"],[1000],__rt.kw([])))){cycle=__t16;clovers=__rt.call(__rt.b["sorted"],[(function*(){let p;for(const __t17 of __rt.iter(area)){p=__t17;if(__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>__rt.item(grid,p),()=>__rt.tuple([41,42])]),()=>__rt.compare(["NotIn"],[()=>p,()=>used])))){yield p;}}})()],__rt.kw([["key",order]]));
for(const __t18 of __rt.iter(clovers)){p=__t18;hits=__rt.call(__rt.b["sorted"],[(function*(){let q;for(const __t19 of __rt.iter(values)){q=__t19;if(__rt.truth(__rt.and_(()=>__rt.compare(["NotEq"],[()=>q,()=>p]),()=>__rt.or_(()=>__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>42]),()=>__rt.call(adjacent,[p,q],__rt.kw([])))))){yield q;}}})()],__rt.kw([["key",order]]));
if(__rt.truth(__rt.unary("Not",hits))){continue;}
mult=__rt.item(__rt.call(__rt.attr(rng,"choices"),[[2,3,4,5,10,20]],__rt.kw([["weights",__rt.item(cfg,"multiplier_weights")]])),0);
for(const __t20 of __rt.iter(hits)){q=__t20;__rt.setitem(values,q,__rt.bin("Mult",__rt.item(values,q),mult));}
__rt.call(__rt.attr(used,"add"),[p],__rt.kw([]));
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,[(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>42]))?"globalMult":"mult")],__rt.kw([["p",__rt.call(__rt.b["str"],[p],__rt.kw([]))],["m",__rt.call(__rt.b["str"],[mult],__rt.kw([]))],["hits",__rt.call(__rt.b["list"],[__rt.call(__rt.b["map"],[__rt.b["str"],hits],__rt.kw([]))],__rt.kw([]))],["results",(()=>{let q;const __out:any[]=[];for(const __t21 of __rt.iter(hits)){q=__t21;__out.push(__rt.call(__rt.b["str"],[__rt.item(values,q)],__rt.kw([])));}return __out;})()]]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["GtE"],[()=>__rt.bin("FloorDiv",__rt.bin("Mult",bet,__rt.call(__rt.b["sum"],[__rt.call(__rt.attr(values,"values"),[],__rt.kw([]))],__rt.kw([]))),10),()=>limit]))){__t15=false;break;}
bags=__rt.call(__rt.b["sorted"],[(function*(){let p;for(const __t22 of __rt.iter(area)){p=__t22;if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>44]))){yield p;}}})()],__rt.kw([["key",order]]));
pots=__rt.call(__rt.b["sorted"],[(function*(){let p;for(const __t23 of __rt.iter(area)){p=__t23;if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>43]))){yield p;}}})()],__rt.kw([["key",order]]));
candidates=__rt.or_(()=>bags,()=>pots);
candidate=null;
for(const __t24 of __rt.iter(candidates)){p=__t24;hits=(()=>{let q;const __out:any[]=[];for(const __t25 of __rt.iter(values)){q=__t25;if(__rt.truth(__rt.and_(()=>__rt.compare(["NotEq"],[()=>q,()=>p]),()=>__rt.or_(()=>__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>43]),()=>__rt.call(adjacent,[p,q],__rt.kw([])))))){__out.push(q);}}return __rt.set(__out);})();
if(__rt.truth(hits)){candidate=__rt.tuple([p,hits]);
break;}}
if(__rt.truth(__rt.compare(["Is"],[()=>candidate,()=>null]))){for(const __t26 of __rt.iter(pots)){p=__t26;hits=__rt.bin("Sub",__rt.call(__rt.b["set"],[values],__rt.kw([])),__rt.set([p]));
if(__rt.truth(hits)){candidate=__rt.tuple([p,hits]);
break;}}}
if(__rt.truth(__rt.compare(["Is"],[()=>candidate,()=>null]))){__t15=false;break;}
{const __t27=Array.from(__rt.iter(candidate));p=__t27[0];hits=__t27[1];}
local=__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>44]);
collected=__rt.call(__rt.b["sum"],[(function*(){let q;for(const __t28 of __rt.iter(hits)){q=__t28;yield __rt.item(values,q);}})()],__rt.kw([]));
refill=(()=>{let q;const __out:any[]=[];for(const __t29 of __rt.iter(hits)){q=__t29;if(__rt.truth(__rt.compare(["NotIn"],[()=>__rt.item(grid,q),()=>__rt.tuple([45,46])]))){__out.push(q);}}return __rt.set(__out);})();
__rt.call(__rt.attr(refill,"update"),[(function*(){let q;for(const __t30 of __rt.iter(used)){q=__t30;if(__rt.truth(__rt.and_(()=>__rt.compare(["NotEq"],[()=>q,()=>p]),()=>__rt.or_(()=>__rt.unary("Not",local),()=>__rt.call(adjacent,[p,q],__rt.kw([])))))){yield q;}}})()],__rt.kw([]));
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,[(__rt.truth(local)?"localCollect":"collect")],__rt.kw([["p",__rt.call(__rt.b["str"],[p],__rt.kw([]))],["w",__rt.call(__rt.b["str"],[collected],__rt.kw([]))],["h",__rt.call(mask,[hits],__rt.kw([]))],["replaceMask",__rt.call(mask,[refill],__rt.kw([]))]]))],__rt.kw([]));
__rt.setitem(grid,p,(__rt.truth(local)?46:45));
__rt.setitem(values,p,collected);
if(__rt.truth(refill)){__rt.call(reveal,[refill,local],__rt.kw([]));}}if(__t15){throw __rt.call(__rt.b["RuntimeError"],["Special-symbol chain exceeded sanity limit"],__rt.kw([]));}
win=__rt.call(__rt.b["min"],[__rt.bin("FloorDiv",__rt.bin("Mult",bet,__rt.call(__rt.b["sum"],[__rt.call(__rt.attr(values,"values"),[],__rt.kw([]))],__rt.kw([]))),10),limit],__rt.kw([]));
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["cashWin"],__rt.kw([["w",__rt.call(__rt.b["str"],[win],__rt.kw([]))],["h",__rt.call(mask,[values],__rt.kw([]))]]))],__rt.kw([]));
return __rt.tuple([actions,win]);return null;}),"generate":__rt.fn("generate",{names:["self", "rng", "amount", "mode"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng,amount,mode){let _,add_cash,awarded,blood,cap,count,emit,events,extra,feature,gold,guarantee,pending_reset,play,remaining,total,upgraded;events=[];
total=0;
cap=__rt.bin("Mult",amount,__rt.item(__rt.attr(self,"config"),"maximum_win_multiplier"));
gold=__rt.call(__rt.b["set"],[],__rt.kw([]));
blood=__rt.call(__rt.b["set"],[],__rt.kw([]));
upgraded=__rt.call(__rt.b["set"],[],__rt.kw([]));
pending_reset=null;
guarantee=null;
awarded=0;
emit=__rt.fn("emit",{names:["kind", "data", "win"],kwonly:[],defaults:{"win":0},vararg:null,kwarg:null},function(kind,data,win){
win=__rt.call(__rt.b["min"],[win,__rt.bin("Sub",cap,total)],__rt.kw([]));
total=__rt.bin("Add",total,win);
__rt.call(__rt.attr(events,"append"),[__rt.call(__rt.b["dict"],[],__rt.kw([["et",2],["etn",kind],["en","0"],["ba","0"],["bc","0"],["wa",__rt.call(__rt.b["str"],[win],__rt.kw([]))],["wc","0"],["awa",__rt.call(__rt.b["str"],[total],__rt.kw([]))],["awc","0"],["c",data]]))],__rt.kw([]));return null;});
play=__rt.fn("play",{names:["game_mode", "forced"],kwonly:[],defaults:{"forced":null},vararg:null,kwarg:null},function(game_mode,forced){let actions,active_blood,active_gold,c,cascade,cash,cells,clusters,data,effective,extras,fs,grid,is_epic,kept,minimum,__py_new,original_blood,original_gold,p,paid,positions,prefix,r,raining,reels,reelset,removed,scatters,special,special_actions,stops,symbol,total_before,v,win;
prefix=(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"base"]))?"":__rt.bin("Add",game_mode,"_"));
reelset=(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"base"]))?(__rt.truth(__rt.compare(["In"],[()=>forced,()=>__rt.tuple(["mod_rainbow","mod_epic"])]))?forced:"default"):(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"fs_2"]))?"fs2_high":(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"epic"]))?"epic":"fs_high")));
reels=__rt.item(__rt.item(__rt.attr(self,"config"),"reels"),reelset);
stops=(()=>{let reel;const __out:any[]=[];for(const __t31 of __rt.iter(reels)){reel=__t31;__out.push(__rt.call(__rt.attr(rng,"randrange"),[__rt.call(__rt.b["len"],[reel],__rt.kw([]))],__rt.kw([])));}return __out;})();
grid=(()=>{let c,r;const __out:any[]=[];for(const __t32 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){r=__t32;for(const __t33 of __rt.iter(__rt.call(__rt.b["range"],[6],__rt.kw([])))){c=__t33;__out.push(__rt.call(__rt.b["int"],[__rt.item(__rt.item(reels,c),__rt.bin("Mod",__rt.bin("Add",__rt.item(stops,c),r),__rt.call(__rt.b["len"],[__rt.item(reels,c)],__rt.kw([]))))],__rt.kw([])));}}return __out;})();
grid=(()=>{let v;const __out:any[]=[];for(const __t34 of __rt.iter(grid)){v=__t34;__out.push((__rt.truth(__rt.compare(["In"],[()=>v,()=>upgraded]))?__rt.bin("Add",v,10):v));}return __out;})();
special=null;
scatters=0;
if(__rt.truth(__rt.compare(["In"],[()=>forced,()=>__rt.tuple(["fs","fs_2"])]))){scatters=(__rt.truth(__rt.compare(["Eq"],[()=>forced,()=>"fs"]))?3:4);}else{if(__rt.truth(__rt.compare(["Eq"],[()=>forced,()=>"mod_epic"]))){special=14;}else{if(__rt.truth(__rt.compare(["Eq"],[()=>forced,()=>"mod_rainbow"]))){special=(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"epic_probability")]))?14:13);}else{if(__rt.truth(__rt.compare(["IsNot"],[()=>guarantee,()=>null]))){special=guarantee;
guarantee=null;}else{if(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"epic"]))){special=(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"epic_probability")]))?14:13);}else{if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>game_mode,()=>"base"]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.bin("Mult",__rt.item(__rt.attr(self,"config"),"bonus_probability"),(__rt.truth(__rt.compare(["Eq"],[()=>mode,()=>"mod_bonus"]))?5:1))])))){scatters=__rt.item(__rt.call(__rt.attr(rng,"choices"),[[3,4,5]],__rt.kw([["weights",__rt.item(__rt.attr(self,"config"),"bonus_weights")]])),0);}else{if(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"rainbow_probability")]))){special=(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"epic_probability")]))?14:13);}}}}}}}
if(__rt.truth(scatters)){for(const __t35 of __rt.iter(__rt.call(__rt.attr(rng,"sample"),[__rt.call(__rt.b["range"],[30],__rt.kw([])),scatters],__rt.kw([])))){p=__t35;__rt.setitem(grid,p,12);}}else{if(__rt.truth(special)){__rt.setitem(grid,__rt.call(__rt.attr(rng,"randrange"),[30],__rt.kw([])),special);}}
extras=0;
let __t36=true;for(const __t37 of __rt.iter(__rt.call(__rt.b["range"],[1000],__rt.kw([])))){cascade=__t37;data=__rt.dict([["reelSet",reelset],["grid",__rt.call(encode_grid,[grid],__rt.kw([]))]]);
if(__rt.truth(__rt.compare(["Eq"],[()=>cascade,()=>0]))){__rt.setitem(data,"stops",__rt.call(__rt.b["list"],[__rt.call(__rt.b["map"],[__rt.b["str"],stops],__rt.kw([]))],__rt.kw([])));}
actions=[];
win=0;
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>cascade,()=>0]),()=>pending_reset))){__rt.call(__rt.attr(actions,"append"),[__rt.call(action,[pending_reset],__rt.kw([]))],__rt.kw([]));
pending_reset=null;}
clusters=__rt.call(__rt.attr(self,"clusters"),[grid],__rt.kw([]));
removed=__rt.call(__rt.b["set"],[],__rt.kw([]));
for(const __t38 of __rt.iter(clusters)){{const __t39=Array.from(__rt.iter(__t38));symbol=__t39[0];cells=__t39[1];}effective=(__rt.truth(__rt.compare(["In"],[()=>symbol,()=>upgraded]))?__rt.bin("Add",symbol,10):symbol);
paid=__rt.call(__rt.b["min"],[__rt.call(__rt.attr(self,"payout"),[effective,__rt.call(__rt.b["len"],[cells],__rt.kw([])),amount],__rt.kw([])),__rt.bin("Sub",__rt.bin("Sub",cap,total),win)],__rt.kw([]));
win=__rt.bin("Add",win,paid);
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["gridwin"],__rt.kw([["symbol",__rt.call(__rt.b["str"],[effective],__rt.kw([]))],["count",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[cells],__rt.kw([]))],__rt.kw([]))],["mask",__rt.call(mask,[cells],__rt.kw([]))],["winAmount",__rt.call(__rt.b["str"],[paid],__rt.kw([]))]]))],__rt.kw([]));
if(__rt.truth(__rt.compare(["GtE"],[()=>effective,()=>15]))){__rt.call(__rt.attr(blood,"update"),[cells],__rt.kw([]));
__rt.call(__rt.attr(gold,"difference_update"),[cells],__rt.kw([]));}else{__rt.call(__rt.attr(gold,"update"),[__rt.bin("Sub",cells,__rt.call(__rt.b["set"],[blood],__rt.kw([])))],__rt.kw([]));}
__rt.call(__rt.attr(removed,"update"),[(function*(){let i,v;for(const __t40 of __rt.iter(__rt.call(__rt.b["enumerate"],[grid],__rt.kw([])))){{const __t41=Array.from(__rt.iter(__t40));i=__t41[0];v=__t41[1];}if(__rt.truth(__rt.compare(["Eq"],[()=>v,()=>symbol]))){yield i;}}})()],__rt.kw([]));
__rt.call(__rt.attr(removed,"update"),[(function*(){let p;for(const __t42 of __rt.iter(cells)){p=__t42;if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>0]))){yield p;}}})()],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.compare(["NotEq"],[()=>game_mode,()=>"base"]),()=>__rt.compare(["LtE", "LtE"],[()=>5,()=>symbol,()=>8]),()=>__rt.compare(["NotIn"],[()=>symbol,()=>upgraded])))){__rt.call(__rt.attr(upgraded,"add"),[symbol],__rt.kw([]));
extras=__rt.bin("Add",extras,2);
awarded=__rt.bin("Add",awarded,2);
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["highUpgrade"],__rt.kw([["i",__rt.call(__rt.b["str"],[symbol],__rt.kw([]))],["s","2"]]))],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.b["len"],[upgraded],__rt.kw([])),()=>4]))){guarantee=(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"epic"]))?14:(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"epic_probability")]))?14:13));
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["allHighsUpgraded"],__rt.kw([]))],__rt.kw([]));}}}
if(__rt.truth(removed)){__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["remove"],__rt.kw([["mask",__rt.call(mask,[removed],__rt.kw([]))]]))],__rt.kw([]));}
if(__rt.truth(actions)){__rt.setitem(data,"actions",actions);}
__rt.call(emit,[__rt.bin("Add",prefix,(__rt.truth(__rt.compare(["Eq"],[()=>cascade,()=>0]))?"reveal":"collapse")),data,win],__rt.kw([]));
if(__rt.truth(__rt.compare(["GtE"],[()=>total,()=>cap]))){return __rt.tuple([0,null,extras]);}
if(__rt.truth(__rt.unary("Not",clusters))){__t36=false;break;}
for(const __t43 of __rt.iter(__rt.call(__rt.b["range"],[6],__rt.kw([])))){c=__t43;kept=(()=>{let r;const __out:any[]=[];for(const __t44 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){r=__t44;if(__rt.truth(__rt.compare(["NotIn"],[()=>__rt.bin("Add",__rt.bin("Mult",r,6),c),()=>removed]))){__out.push(__rt.item(grid,__rt.bin("Add",__rt.bin("Mult",r,6),c)));}}return __out;})();
__py_new=__rt.bin("Add",(()=>{let _;const __out:any[]=[];for(const __t45 of __rt.iter(__rt.call(__rt.b["range"],[__rt.bin("Sub",5,__rt.call(__rt.b["len"],[kept],__rt.kw([])))],__rt.kw([])))){_=__t45;__out.push(__rt.call(__rt.b["int"],[__rt.call(__rt.attr(rng,"choice"),[__rt.item(reels,c)],__rt.kw([]))],__rt.kw([])));}return __out;})(),kept);
for(const __t46 of __rt.iter(__rt.call(__rt.b["enumerate"],[__py_new],__rt.kw([])))){{const __t47=Array.from(__rt.iter(__t46));r=__t47[0];v=__t47[1];}__rt.setitem(grid,__rt.bin("Add",__rt.bin("Mult",r,6),c),(__rt.truth(__rt.compare(["In"],[()=>v,()=>upgraded]))?__rt.bin("Add",v,10):v));}}}if(__t36){throw __rt.call(__rt.b["RuntimeError"],["Cascade exceeded sanity limit"],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>game_mode,()=>"base"]),()=>scatters))){fs=(__rt.truth(__rt.compare(["Eq"],[()=>scatters,()=>3]))?"fs":(__rt.truth(__rt.compare(["Eq"],[()=>scatters,()=>4]))?"fs_2":"epic"));
positions=(()=>{let p,v;const __out:any[]=[];for(const __t48 of __rt.iter(__rt.call(__rt.b["enumerate"],[grid],__rt.kw([])))){{const __t49=Array.from(__rt.iter(__t48));p=__t49[0];v=__t49[1];}if(__rt.truth(__rt.compare(["Eq"],[()=>v,()=>12]))){__out.push(p);}}return __out;})();
__rt.call(__rt.attr(__rt.call(__rt.attr(data,"setdefault"),["actions",[]],__rt.kw([])),"extend"),[[__rt.call(action,["gridwin"],__rt.kw([["symbol","12"],["count",__rt.call(__rt.b["str"],[__rt.call(__rt.b["len"],[positions],__rt.kw([]))],__rt.kw([]))],["mask",__rt.call(mask,[positions],__rt.kw([]))],["winAmount","0"]])),__rt.call(action,["bonusfeaturewon"],__rt.kw([["bfw",fs],["bfc","10"]]))]],__rt.kw([]));
return __rt.tuple([10,fs,extras]);}
p=__rt.call(__rt.b["next"],[(function*(){let p,v;for(const __t50 of __rt.iter(__rt.call(__rt.b["enumerate"],[grid],__rt.kw([])))){{const __t51=Array.from(__rt.iter(__t50));p=__t51[0];v=__t51[1];}if(__rt.truth(__rt.compare(["In"],[()=>v,()=>__rt.tuple([13,14])]))){yield p;}}})(),null],__rt.kw([]));
if(__rt.truth(__rt.compare(["IsNot"],[()=>p,()=>null]))){is_epic=__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>14]);
raining=__rt.and_(()=>is_epic,()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"blood_rain_probability")]));
{const __t52=Array.from(__rt.iter(__rt.tuple([__rt.call(__rt.b["set"],[gold],__rt.kw([])),__rt.call(__rt.b["set"],[blood],__rt.kw([]))])));original_gold=__t52[0];original_blood=__t52[1];}
active_blood=(__rt.truth(raining)?__rt.call(__rt.b["set"],[__rt.call(__rt.b["range"],[30],__rt.kw([]))],__rt.kw([])):__rt.call(__rt.b["set"],[blood],__rt.kw([])));
active_gold=(__rt.truth(is_epic)?__rt.bin("Sub",__rt.call(__rt.b["set"],[__rt.call(__rt.b["range"],[30],__rt.kw([]))],__rt.kw([])),active_blood):__rt.call(__rt.b["set"],[gold],__rt.kw([])));
__rt.call(__rt.attr(__rt.call(__rt.attr(data,"setdefault"),["actions",[]],__rt.kw([])),"append"),[__rt.call(action,["activator"],__rt.kw([["p",__rt.call(__rt.b["str"],[p],__rt.kw([]))],[null,(__rt.truth(raining)?__rt.dict([["blood",true]]):__rt.dict([]))]]))],__rt.kw([]));
minimum=(__rt.truth(__rt.or_(()=>__rt.compare(["Eq"],[()=>game_mode,()=>"epic"]),()=>__rt.compare(["In"],[()=>mode,()=>__rt.tuple(["mod_rainbow","mod_epic"])])))?10:0);
{const __t53=Array.from(__rt.iter(__rt.call(__rt.attr(self,"resolve_special"),[grid,active_gold,active_blood,rng,amount,minimum,__rt.bin("Sub",cap,total)],__rt.kw([]))));special_actions=__t53[0];cash=__t53[1];}
__rt.call(__rt.attr(__rt.item(data,"actions"),"extend"),[special_actions],__rt.kw([]));
total_before=total;
__rt.setitem(__rt.item(events,__rt.unary("USub",1)),"wa",__rt.call(__rt.b["str"],[__rt.bin("Add",__rt.call(__rt.b["int"],[__rt.item(__rt.item(events,__rt.unary("USub",1)),"wa")],__rt.kw([])),cash)],__rt.kw([])));
__rt.call(add_cash,[cash],__rt.kw([]));
__rt.setitem(__rt.item(events,__rt.unary("USub",1)),"awa",__rt.call(__rt.b["str"],[__rt.bin("Add",total_before,cash)],__rt.kw([])));
if(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"fs"]))){__rt.call(__rt.attr(gold,"clear"),[],__rt.kw([]));
__rt.call(__rt.attr(blood,"clear"),[],__rt.kw([]));
pending_reset="clearHighlights";}else{if(__rt.truth(__rt.compare(["In"],[()=>game_mode,()=>__rt.tuple(["fs_2","epic"])]))){__rt.call(__rt.attr(gold,"clear"),[],__rt.kw([]));
__rt.call(__rt.attr(gold,"update"),[original_gold],__rt.kw([]));
__rt.call(__rt.attr(blood,"clear"),[],__rt.kw([]));
__rt.call(__rt.attr(blood,"update"),[original_blood],__rt.kw([]));
if(__rt.truth(is_epic)){pending_reset="highlightReset";}}else{__rt.call(__rt.attr(gold,"clear"),[],__rt.kw([]));
__rt.call(__rt.attr(blood,"clear"),[],__rt.kw([]));}}}
return __rt.tuple([0,null,extras]);return null;});
add_cash=__rt.fn("add_cash",{names:["win"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(win){
total=__rt.bin("Add",total,win);return null;});
{const __t54=Array.from(__rt.iter(__rt.call(play,["base",(__rt.truth(__rt.compare(["In"],[()=>mode,()=>__rt.tuple(["fs","fs_2","mod_rainbow","mod_epic"])]))?mode:null)],__rt.kw([]))));count=__t54[0];feature=__t54[1];_=__t54[2];}
awarded=__rt.bin("Add",awarded,count);
if(__rt.truth(__rt.and_(()=>count,()=>__rt.compare(["Lt"],[()=>total,()=>cap])))){__rt.call(__rt.attr(gold,"clear"),[],__rt.kw([]));
__rt.call(__rt.attr(blood,"clear"),[],__rt.kw([]));
__rt.call(__rt.attr(upgraded,"clear"),[],__rt.kw([]));
pending_reset=null;
__rt.call(emit,["feature_enter",__rt.dict([["bonusFeatureWon",feature],["bonusFeatureCount",__rt.call(__rt.b["str"],[count],__rt.kw([]))]])],__rt.kw([]));
remaining=count;
while(__rt.truth(__rt.and_(()=>remaining,()=>__rt.compare(["Lt"],[()=>total,()=>cap])))){remaining=__rt.bin("Sub",remaining,1);
{const __t55=Array.from(__rt.iter(__rt.call(play,[feature],__rt.kw([]))));_=__t55[0];_=__t55[1];extra=__t55[2];}
remaining=__rt.bin("Add",remaining,extra);}
if(__rt.truth(__rt.compare(["Lt"],[()=>total,()=>cap]))){__rt.call(emit,["feature_exit",__rt.dict([])],__rt.kw([]));}}
if(__rt.truth(__rt.compare(["GtE"],[()=>total,()=>cap]))){__rt.call(emit,["max_win_reached",__rt.dict([])],__rt.kw([]));}
return __rt.tuple([events,total,awarded,feature]);return null;})});
