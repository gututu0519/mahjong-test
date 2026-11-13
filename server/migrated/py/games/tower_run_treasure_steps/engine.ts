// Migrated from py/games/tower_run_treasure_steps/engine.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
const __file__=__rt.sourcePath("py/games/tower_run_treasure_steps/engine.py");
export let Outcome:any,Path:any,ServiceError:any,TowerRunTreasureSteps:any,copy:any,hashlib:any,json:any,random:any,wire:any;

copy=__rt.modules["copy"];
hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
random=__rt.modules["random"];
Outcome=__rt.attr(__rt.modules["py.core.contracts"],"Outcome");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
wire=__rt.fn("wire",{names:[],kwonly:[],defaults:{},vararg:"parts",kwarg:null},function(parts){return __rt.call(__rt.attr(" ","join"),[(function*(){let p;for(const __t1 of __rt.iter(parts)){p=__t1;yield __rt.call(__rt.b["str"],[p],__rt.kw([]));}})()],__rt.kw([]));return null;});
TowerRunTreasureSteps=__rt.cls("TowerRunTreasureSteps",[],{"game_id":"tower-run-treasure-steps","title":"Tower Run Treasure Steps","version":"1.1.0","minor_unit":100,"__init__":__rt.fn("__init__",{names:["self", "config"],kwonly:[],defaults:{"config":null},vararg:null,kwarg:null},function(self,config){__rt.setattr(self,"config",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(Path,[__rt.or_(()=>config,()=>__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["config.json"],__rt.kw([])))],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(self,"ruleset_id",__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[__rt.call(__rt.b["dict"],[],__rt.kw([["version",__rt.attr(self,"version")],["config",__rt.attr(self,"config")]]))],__rt.kw([["sort_keys",true]])),"encode"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,20,null)));return null;}),"initial_state":__rt.fn("initial_state",{names:["self", "seed"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,seed){return __rt.call(__rt.b["dict"],[],__rt.kw([["sid","0"],["phase","ready"],["pending",null],["progress",__rt.dict([])],["last_denom",10],["ultra",false],["last_grid",(()=>{let i;const __out:any[]=[];for(const __t2 of __rt.iter(__rt.call(__rt.b["range"],[25],__rt.kw([])))){i=__t2;__out.push(__rt.bin("Mod",i,10));}return __out;})()]]));return null;}),"public_state":__rt.fn("public_state",{names:["self", "state"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state){return __rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));return null;}),"normalize_bet":__rt.fn("normalize_bet",{names:["self", "payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,payload){let action;if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(ServiceError,["BET_INVALID","Expected an object."],__rt.kw([]));}
action=__rt.call(__rt.attr(payload,"get"),["action"],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>action,()=>__rt.tuple(["continue","collect","replay"])]),()=>__rt.compare(["Eq"],[()=>__rt.call(__rt.b["set"],[payload],__rt.kw([])),()=>__rt.set(["action"])])))){return __rt.call(__rt.b["dict"],[],__rt.kw([["action",action]]));}
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["set"],[payload],__rt.kw([])),()=>__rt.set(["denom","ultra"])]),()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[__rt.item(payload,"denom")],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["NotIn"],[()=>__rt.item(payload,"denom"),()=>__rt.item(__rt.attr(self,"config"),"denominations")]),()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[__rt.item(payload,"ultra")],__rt.kw([])),()=>__rt.b["bool"]])))){throw __rt.call(ServiceError,["BET_INVALID","Invalid denomination or booster."],__rt.kw([]));}
return __rt.call(__rt.attr(payload,"copy"),[],__rt.kw([]));return null;}),"evaluate":__rt.fn("evaluate",{names:["self", "grid", "multiplier"],kwonly:[],defaults:{"multiplier":1},vararg:null,kwarg:null},function(self,grid,multiplier){let cells,index,result,symbol,table;result=[];
for(const __t3 of __rt.iter(__rt.call(__rt.b["enumerate"],[__rt.item(__rt.attr(self,"config"),"payouts")],__rt.kw([])))){{const __t4=Array.from(__rt.iter(__t3));symbol=__t4[0];table=__t4[1];}cells=(()=>{let p,value;const __out:any[]=[];for(const __t5 of __rt.iter(__rt.call(__rt.b["enumerate"],[grid],__rt.kw([])))){{const __t6=Array.from(__rt.iter(__t5));p=__t6[0];value=__t6[1];}if(__rt.truth(__rt.compare(["In"],[()=>value,()=>__rt.tuple([symbol,10])]))){__out.push(p);}}return __out;})();
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotIn"],[()=>symbol,()=>grid]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.b["len"],[cells],__rt.kw([])),()=>(__rt.truth(__rt.compare(["Lt"],[()=>symbol,()=>5]))?7:6)])))){continue;}
index=__rt.bin("Sub",11,__rt.call(__rt.b["min"],[11,__rt.call(__rt.b["len"],[cells],__rt.kw([]))],__rt.kw([])));
__rt.call(__rt.attr(result,"append"),[__rt.call(__rt.b["dict"],[],__rt.kw([["symbol",symbol],["cells",cells],["coins",__rt.bin("Mult",__rt.item(table,index),multiplier)],["multiplier",multiplier]]))],__rt.kw([]));}
return result;return null;}),"generate":__rt.fn("generate",{names:["self", "rng", "denom", "ultra", "progress"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng,denom,ultra,progress){let args,available,awarded,base_coins,bonus,bonus_coins,cap,cascade,cells,charge,coins,col,encounter,end,grid,initial,lines,multiplier,next_multiplier,p,paid,prize,queue,rebuilt,refill,remain,removed,stage,steps,total,value,wilds,win,wins;{const __t7=Array.from(__rt.iter(__rt.tuple([(__rt.truth(ultra)?15:10),0,__rt.bin("Mult",10,__rt.item(__rt.attr(self,"config"),"maximum_win_multiplier"))])));coins=__t7[0];total=__t7[1];cap=__t7[2];}
grid=__rt.call(__rt.attr(rng,"choices"),[__rt.call(__rt.b["range"],[11],__rt.kw([])),__rt.item(__rt.attr(self,"config"),"symbol_weights")],__rt.kw([["k",25]]));
initial=__rt.call(__rt.attr(grid,"copy"),[],__rt.kw([]));
lines=[__rt.call(wire,[1,1,coins,denom,...__rt.iter(grid),1,0],__rt.kw([])),"2 0 0 0 0 0"];
steps=__rt.call(__rt.attr(rng,"randint"),[1,6],__rt.kw([]));
end=__rt.bin("Add",progress,steps);
encounter=__rt.compare(["GtE"],[()=>end,()=>18]);
end=__rt.bin("Mod",end,18);
__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,21,progress,steps,end,18,__rt.call(__rt.b["int"],[encounter],__rt.kw([])),denom],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(encounter)){prize=__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.item(__rt.attr(self,"config"),"instant_coins"),__rt.item(__rt.attr(self,"config"),"instant_weights")],__rt.kw([])),0);
total=__rt.bin("Add",total,prize);
__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,0,prize],__rt.kw([]))],__rt.kw([]));}
{const __t8=Array.from(__rt.iter(__rt.tuple([0,0,1,(__rt.truth(ultra)?2:1),false])));charge=__t8[0];stage=__t8[1];cascade=__t8[2];multiplier=__t8[3];bonus=__t8[4];}
while(__rt.truth(__rt.compare(["Lt"],[()=>total,()=>cap]))){wins=__rt.call(__rt.attr(self,"evaluate"),[grid,multiplier],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",wins))){break;}
{const __t9=Array.from(__rt.iter(__rt.tuple([[],__rt.call(__rt.b["set"],[],__rt.kw([]))])));args=__t9[0];removed=__t9[1];}
awarded=0;
for(const __t10 of __rt.iter(wins)){win=__t10;if(__rt.truth(__rt.compare(["Eq"],[()=>total,()=>cap]))){break;}
paid=__rt.call(__rt.b["min"],[__rt.item(win,"coins"),__rt.bin("Sub",cap,total)],__rt.kw([]));
total=__rt.bin("Add",total,paid);
awarded=__rt.bin("Add",awarded,1);
__rt.call(__rt.attr(args,"extend"),[[__rt.item(win,"symbol"),__rt.call(__rt.b["len"],[__rt.item(win,"cells")],__rt.kw([])),...__rt.iter(__rt.item(win,"cells")),paid,__rt.item(win,"multiplier")]],__rt.kw([]));
__rt.call(__rt.attr(removed,"update"),[__rt.item(win,"cells")],__rt.kw([]));}
__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,8,cascade,awarded,...__rt.iter(args)],__rt.kw([]))],__rt.kw([]));
charge=__rt.bin("Add",charge,awarded);
if(__rt.truth(__rt.compare(["Lt"],[()=>stage,()=>3]))){__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,22,cascade,__rt.call(__rt.b["min"],[charge,9],__rt.kw([])),9],__rt.kw([]))],__rt.kw([]));}
__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,9,cascade,__rt.call(__rt.b["len"],[removed],__rt.kw([])),...__rt.iter(__rt.call(__rt.b["sorted"],[removed],__rt.kw([])))],__rt.kw([]))],__rt.kw([]));
{const __t11=Array.from(__rt.iter(__rt.tuple([(__rt.truth(ultra)?2:1),[]])));next_multiplier=__t11[0];wilds=__t11[1];}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Lt"],[()=>total,()=>cap]),()=>__rt.compare(["Lt"],[()=>stage,()=>2]),()=>__rt.compare(["GtE"],[()=>charge,()=>6])))){wilds=__rt.call(__rt.attr(rng,"sample"),[__rt.call(__rt.b["sorted"],[removed],__rt.kw([])),__rt.call(__rt.b["min"],[__rt.call(__rt.b["len"],[removed],__rt.kw([])),(__rt.truth(__rt.compare(["Eq"],[()=>stage,()=>0]))?__rt.call(__rt.attr(rng,"randint"),[2,8],__rt.kw([])):__rt.call(__rt.attr(rng,"randint"),[1,4],__rt.kw([])))],__rt.kw([]))],__rt.kw([]));
next_multiplier=(__rt.truth(ultra)?5:__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.item(__rt.attr(self,"config"),"global_multipliers"),__rt.item(__rt.attr(self,"config"),"global_weights")],__rt.kw([])),0));
stage=2;}else{if(__rt.truth(__rt.and_(()=>__rt.compare(["Lt"],[()=>total,()=>cap]),()=>__rt.compare(["Lt"],[()=>stage,()=>1]),()=>__rt.compare(["GtE"],[()=>charge,()=>3])))){wilds=__rt.call(__rt.attr(rng,"sample"),[__rt.call(__rt.b["sorted"],[removed],__rt.kw([])),__rt.call(__rt.b["min"],[__rt.call(__rt.b["len"],[removed],__rt.kw([])),__rt.call(__rt.attr(rng,"randint"),[1,4],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));
stage=1;}}
if(__rt.truth(wilds)){__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,23,cascade,__rt.call(__rt.b["len"],[wilds],__rt.kw([])),...__rt.iter(wilds)],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["NotEq"],[()=>next_multiplier,()=>(__rt.truth(ultra)?2:1)]))){__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,24,cascade,next_multiplier],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Lt"],[()=>total,()=>cap]),()=>__rt.compare(["GtE"],[()=>charge,()=>9])))){{const __t12=Array.from(__rt.iter(__rt.tuple([3,true])));stage=__t12[0];bonus=__t12[1];}}
for(const __t13 of __rt.iter(__rt.call(__rt.b["range"],[5],__rt.kw([])))){col=__t13;cells=__rt.call(__rt.b["list"],[__rt.call(__rt.b["range"],[__rt.bin("Mult",col,5),__rt.bin("Add",__rt.bin("Mult",col,5),5)],__rt.kw([]))],__rt.kw([]));
remain=(()=>{let p;const __out:any[]=[];for(const __t14 of __rt.iter(cells)){p=__t14;if(__rt.truth(__rt.compare(["NotIn"],[()=>p,()=>removed]))){__out.push(__rt.item(grid,p));}}return __out;})();
refill=__rt.call(__rt.attr(rng,"choices"),[__rt.call(__rt.b["range"],[11],__rt.kw([])),__rt.item(__rt.attr(self,"config"),"symbol_weights")],__rt.kw([["k",__rt.bin("Sub",5,__rt.call(__rt.b["len"],[remain],__rt.kw([])))]]));
available=(()=>{let p;const __out:any[]=[];for(const __t15 of __rt.iter(cells)){p=__t15;if(__rt.truth(__rt.compare(["NotIn"],[()=>p,()=>wilds]))){__out.push(p);}}return __out;})();
rebuilt=__rt.bin("Add",__rt.item(refill,__rt.slice(null,__rt.bin("Sub",__rt.call(__rt.b["len"],[available],__rt.kw([])),__rt.call(__rt.b["len"],[remain],__rt.kw([]))),null)),remain);
for(const __t16 of __rt.iter(__rt.call(__rt.b["zip"],[available,rebuilt],__rt.kw([])))){{const __t17=Array.from(__rt.iter(__t16));p=__t17[0];value=__t17[1];}__rt.setitem(grid,p,value);}}
for(const __t18 of __rt.iter(wilds)){p=__t18;__rt.setitem(grid,p,10);}
cascade=__rt.bin("Add",cascade,1);
__rt.call(__rt.attr(lines,"append"),[__rt.call(wire,[2,2,10,cascade,25,...__rt.iter(grid)],__rt.kw([]))],__rt.kw([]));
multiplier=next_multiplier;
if(__rt.truth(__rt.compare(["Gt"],[()=>cascade,()=>500]))){throw __rt.call(__rt.b["RuntimeError"],["Cascade sanity limit exceeded"],__rt.kw([]));}}
__rt.call(__rt.attr(lines,"append"),["2 5 1"],__rt.kw([]));
bonus=__rt.and_(()=>bonus,()=>__rt.compare(["Lt"],[()=>total,()=>cap]));
{const __t19=Array.from(__rt.iter((__rt.truth(bonus)?__rt.call(__rt.attr(self,"generate_treasure"),[rng,denom,ultra,total,cap],__rt.kw([])):__rt.tuple([[],0]))));queue=__t19[0];bonus_coins=__t19[1];}
base_coins=total;
total=__rt.bin("Add",total,bonus_coins);
return __rt.call(__rt.b["dict"],[],__rt.kw([["lines",lines],["queue",queue],["total_coins",total],["total_minor",__rt.bin("Mult",total,denom)],["base_coins",base_coins],["treasure_coins",bonus_coins],["progress",end],["initial_grid",initial],["bonus",bonus],["cascades",__rt.bin("Sub",cascade,1)]]));return null;}),"generate_treasure":__rt.fn("generate_treasure",{names:["self", "rng", "denom", "ultra", "base_coins", "cap"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng,denom,ultra,base_coins,cap){let activated,batch,batch_spins,closed,coins,credit,display,ended,final_award,flag,group,groups,has_opening,i,item,keys,lives,locked,maximum_lives,opened,p,paid,previous_lives,queue,reset,spins,symbol,target,value,values,was_open;
maximum_lives=(__rt.truth(ultra)?4:3);
{const __t20=Array.from(__rt.iter(__rt.tuple([(__rt.truth(ultra)?15:10),maximum_lives,0])));coins=__t20[0];lives=__t20[1];paid=__t20[2];}
queue=[["2 0 3 11 0 0",__rt.call(wire,[2,2,1,lives],__rt.kw([])),"2 5 1"]];
{const __t21=Array.from(__rt.iter(__rt.tuple([__rt.dict([]),[],0,0])));locked=__t21[0];batch=__t21[1];batch_spins=__t21[2];spins=__t21[3];}
credit=__rt.fn("credit",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){
value=__rt.call(__rt.b["min"],[value,__rt.bin("Sub",__rt.bin("Sub",cap,base_coins),paid)],__rt.kw([]));
paid=__rt.bin("Add",paid,value);
return value;return null;});
final_award=__rt.fn("final_award",{names:[],kwonly:[],defaults:{},vararg:null,kwarg:null},function(){return ["2 0 3 14 0 0",__rt.call(wire,[2,2,0,paid],__rt.kw([])),"2 5 1"];return null;});
while(__rt.truth(__rt.and_(()=>__rt.compare(["Gt"],[()=>lives,()=>0]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.b["len"],[locked],__rt.kw([])),()=>25]),()=>__rt.compare(["Lt"],[()=>__rt.bin("Add",base_coins,paid),()=>cap])))){previous_lives=lives;
lives=__rt.bin("Sub",lives,1);
spins=__rt.bin("Add",spins,1);
was_open=(()=>{let item,p;const __out:any[]=[];for(const __t22 of __rt.iter(__rt.call(__rt.attr(locked,"items"),[],__rt.kw([])))){{const __t23=Array.from(__rt.iter(__t22));p=__t23[0];item=__t23[1];}if(__rt.truth(__rt.item(item,"open"))){__out.push(p);}}return __rt.set(__out);})();
{const __t24=Array.from(__rt.iter(__rt.tuple([[],[],__rt.call(__rt.b["set"],[],__rt.kw([])),false])));opened=__t24[0];activated=__t24[1];keys=__t24[2];reset=__t24[3];}
for(const __t25 of __rt.iter(__rt.call(__rt.b["sorted"],[__rt.call(__rt.attr(locked,"items"),[],__rt.kw([]))],__rt.kw([])))){{const __t26=Array.from(__rt.iter(__t25));p=__t26[0];item=__t26[1];}if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.item(item,"symbol"),()=>13]),()=>__rt.unary("Not",__rt.item(item,"open"))))){__rt.setitem(item,"timer",__rt.bin("Sub",__rt.item(item,"timer"),1));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(item,"timer"),()=>0]))){__rt.setitem(item,"open",true);
__rt.setitem(item,"value",__rt.call(credit,[__rt.item(item,"value")],__rt.kw([])));
__rt.call(__rt.attr(opened,"append"),[__rt.tuple([p,__rt.item(item,"value")])],__rt.kw([]));
reset=true;
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.bin("Add",base_coins,paid),()=>cap]))){break;}}}}
for(const __t27 of __rt.iter(__rt.call(__rt.b["range"],[25],__rt.kw([])))){p=__t27;if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.bin("Add",base_coins,paid),()=>cap]))){break;}
if(__rt.truth(__rt.or_(()=>__rt.compare(["In"],[()=>p,()=>locked]),()=>__rt.compare(["GtE"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"treasure_land_probability")])))){continue;}
symbol=__rt.item(__rt.call(__rt.attr(rng,"choices"),[[11,12,13],__rt.item(__rt.attr(self,"config"),"treasure_symbol_weights")],__rt.kw([])),0);
reset=true;
if(__rt.truth(__rt.compare(["Eq"],[()=>symbol,()=>11]))){value=__rt.call(credit,[__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.item(__rt.attr(self,"config"),"coin_coins"),__rt.item(__rt.attr(self,"config"),"coin_weights")],__rt.kw([])),0)],__rt.kw([]));
__rt.setitem(locked,p,__rt.call(__rt.b["dict"],[],__rt.kw([["symbol",11],["value",value],["open",true],["timer",0]])));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>symbol,()=>13]))){__rt.setitem(locked,p,__rt.call(__rt.b["dict"],[],__rt.kw([["symbol",13],["open",false],["timer",__rt.call(__rt.attr(rng,"choice"),[__rt.item(__rt.attr(self,"config"),"chest_timers")],__rt.kw([]))],["value",__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.item(__rt.attr(self,"config"),"chest_coins"),__rt.item(__rt.attr(self,"config"),"chest_weights")],__rt.kw([])),0)]])));}else{__rt.call(__rt.attr(keys,"add"),[p],__rt.kw([]));}}}
for(const __t28 of __rt.iter(__rt.call(__rt.b["sorted"],[keys],__rt.kw([])))){p=__t28;if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.bin("Add",base_coins,paid),()=>cap]))){break;}
closed=(()=>{let q;const __out:any[]=[];for(const __t29 of __rt.iter(locked)){q=__t29;if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.item(__rt.item(locked,q),"symbol"),()=>13]),()=>__rt.unary("Not",__rt.item(__rt.item(locked,q),"open"))))){__out.push(q);}}return __out;})();
if(__rt.truth(closed)){target=__rt.call(__rt.attr(rng,"choice"),[closed],__rt.kw([]));
item=__rt.item(locked,target);
__rt.setitem(item,"open",true);
__rt.setitem(item,"value",__rt.call(credit,[__rt.item(item,"value")],__rt.kw([])));
__rt.call(__rt.attr(activated,"append"),[__rt.tuple([p,target,__rt.item(item,"value")])],__rt.kw([]));}}
if(__rt.truth(reset)){lives=maximum_lives;}
display=(()=>{let p;const __out:any[]=[];for(const __t30 of __rt.iter(__rt.call(__rt.b["range"],[25],__rt.kw([])))){p=__t30;__out.push((__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>p,()=>was_open]),()=>__rt.compare(["Eq"],[()=>__rt.item(__rt.item(locked,p),"symbol"),()=>13])))?14:(__rt.truth(__rt.compare(["In"],[()=>p,()=>locked]))?__rt.item(__rt.item(locked,p),"symbol"):(__rt.truth(__rt.compare(["In"],[()=>p,()=>keys]))?12:__rt.unary("USub",1)))));}return __out;})();
values=[];
for(const __t31 of __rt.iter(__rt.call(__rt.b["sorted"],[__rt.call(__rt.attr(locked,"items"),[],__rt.kw([]))],__rt.kw([])))){{const __t32=Array.from(__rt.iter(__t31));p=__t32[0];item=__t32[1];}symbol=__rt.item(display,p);
value=(__rt.truth(__rt.compare(["In"],[()=>symbol,()=>__rt.tuple([11,14])]))?__rt.item(item,"value"):__rt.item(item,"timer"));
__rt.call(__rt.attr(values,"extend"),[[p,symbol,value]],__rt.kw([]));}
ended=__rt.or_(()=>__rt.compare(["Eq"],[()=>lives,()=>0]),()=>__rt.compare(["Eq"],[()=>__rt.call(__rt.b["len"],[locked],__rt.kw([])),()=>25]),()=>__rt.compare(["Eq"],[()=>__rt.bin("Add",base_coins,paid),()=>cap]));
has_opening=__rt.call(__rt.b["bool"],[__rt.or_(()=>opened,()=>activated)],__rt.kw([]));
flag=(__rt.truth(has_opening)?3:(__rt.truth(__rt.or_(()=>reset,()=>ended))?2:1));
__rt.call(__rt.attr(batch,"extend"),[[__rt.call(wire,[3,0,base_coins,__rt.bin("Mult",base_coins,denom),previous_lives,1],__rt.kw([])),__rt.call(wire,[1,1,coins,denom,...__rt.iter(display),flag,0],__rt.kw([])),"2 0 3 13 0 0",__rt.call(wire,[2,2,25,__rt.call(__rt.b["len"],[locked],__rt.kw([])),...__rt.iter(values)],__rt.kw([])),"2 5 0"]],__rt.kw([]));
batch_spins=__rt.bin("Add",batch_spins,1);
if(__rt.truth(has_opening)){groups=[];
if(__rt.truth(opened)){__rt.call(__rt.attr(groups,"append"),[["2 0 0 13 1 0",...__rt.iter((()=>{let p,value;const __out:any[]=[];for(const __t33 of __rt.iter(opened)){{const __t34=Array.from(__rt.iter(__t33));p=__t34[0];value=__t34[1];}__out.push(__rt.call(wire,[2,2,27,p,value],__rt.kw([])));}return __out;})())]],__rt.kw([]));}
if(__rt.truth(activated)){__rt.call(__rt.attr(groups,"append"),[["2 0 0 12 1 0",...__rt.iter((()=>{let p,target,value;const __out:any[]=[];for(const __t35 of __rt.iter(activated)){{const __t36=Array.from(__rt.iter(__t35));p=__t36[0];target=__t36[1];value=__t36[2];}__out.push(__rt.call(wire,[2,2,26,p,target,value],__rt.kw([])));}return __out;})())]],__rt.kw([]));}
for(const __t37 of __rt.iter(__rt.call(__rt.b["enumerate"],[groups],__rt.kw([])))){{const __t38=Array.from(__rt.iter(__t37));i=__t38[0];group=__t38[1];}__rt.call(__rt.attr(batch,"extend"),[__rt.bin("Add",group,[__rt.call(wire,[2,5,__rt.call(__rt.b["int"],[__rt.compare(["Eq"],[()=>i,()=>__rt.bin("Sub",__rt.call(__rt.b["len"],[groups],__rt.kw([])),1)])],__rt.kw([]))],__rt.kw([]))])],__rt.kw([]));}
__rt.call(__rt.attr(queue,"append"),[batch],__rt.kw([]));
__rt.call(__rt.attr(queue,"append"),[(__rt.truth(ended)?__rt.call(final_award,[],__rt.kw([])):["2 0 3 11 0 0",__rt.call(wire,[2,2,1,batch_spins],__rt.kw([])),"2 5 1"])],__rt.kw([]));}else{if(__rt.truth(ended)){__rt.call(__rt.attr(queue,"append"),[__rt.bin("Add",batch,__rt.call(final_award,[],__rt.kw([])))],__rt.kw([]));}else{if(__rt.truth(reset)){__rt.call(__rt.attr(queue,"append"),[__rt.bin("Add",batch,["2 0 3 11 0 0",__rt.call(wire,[2,2,1,batch_spins],__rt.kw([])),"2 5 1"])],__rt.kw([]));}}}
if(__rt.truth(__rt.or_(()=>reset,()=>ended))){{const __t39=Array.from(__rt.iter(__rt.tuple([[],0])));batch=__t39[0];batch_spins=__t39[1];}}
if(__rt.truth(__rt.compare(["Gt"],[()=>spins,()=>1000]))){throw __rt.call(__rt.b["RuntimeError"],["Treasure sanity limit exceeded"],__rt.kw([]));}}
return __rt.tuple([queue,paid]);return null;}),"step":__rt.fn("step",{names:["self", "state", "bet", "seed", "sid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state,bet,seed,sid){let action,amount,data,denom,end,i,last,line,lines,old,packet,pending,result,ultra;state=__rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));
action=__rt.call(__rt.attr(bet,"get"),["action"],__rt.kw([]));
pending=__rt.item(state,"pending");
if(__rt.truth(action)){if(__rt.truth(__rt.unary("Not",pending))){throw __rt.call(ServiceError,["ROUND_INVALID","No pending round.",409],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>action,()=>"replay"]))){if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(pending,"get"),["presentation_version",1],__rt.kw([])),()=>1]),()=>__rt.item(pending,"all_queue")))){old=__rt.item(pending,"all_queue");
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>__rt.item(__rt.item(old,__rt.unary("USub",1)),0),()=>"2 0 3 14 0 0"]),()=>__rt.compare(["Gt"],[()=>__rt.call(__rt.b["len"],[old],__rt.kw([])),()=>1])))){end=__rt.call(__rt.attr(old,"pop"),[],__rt.kw([]));
last=__rt.item(old,__rt.unary("USub",1));
if(__rt.truth(__rt.compare(["In"],[()=>"2 0 3 11 0 0",()=>last]))){__rt.delitem(last,__rt.slice(__rt.call(__rt.attr(last,"index"),["2 0 3 11 0 0"],__rt.kw([])),null,null));}
__rt.call(__rt.attr(last,"extend"),[end],__rt.kw([]));}
for(const __t40 of __rt.iter(old)){packet=__t40;for(const __t41 of __rt.iter(__rt.call(__rt.b["enumerate"],[packet],__rt.kw([])))){{const __t42=Array.from(__rt.iter(__t41));i=__t42[0];line=__t42[1];}if(__rt.truth(__rt.call(__rt.attr(line,"startswith"),["3 0 "],__rt.kw([])))){data=__rt.call(__rt.attr(line,"split"),[],__rt.kw([]));
__rt.setitem(packet,i,__rt.call(wire,[3,0,__rt.item(pending,"total_coins"),__rt.item(pending,"total_minor"),...__rt.iter(__rt.item(data,__rt.slice(4,null,null)))],__rt.kw([])));}}}
__rt.setitem(pending,"presentation_version",2);}
__rt.setitem(pending,"queue",__rt.call(__rt.attr(copy,"deepcopy"),[__rt.item(pending,"all_queue")],__rt.kw([])));
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["sid",sid],["phase","pending"]]));
return __rt.call(Outcome,[state,__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",__rt.item(pending,"round_id")],["lines",__rt.item(pending,"initial_lines")],["next_phase","pending"],["replay",true]])),0,0],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>action,()=>"collect"]))){if(__rt.truth(__rt.or_(()=>__rt.item(pending,"queue"),()=>__rt.compare(["NotEq"],[()=>__rt.item(state,"phase"),()=>"collect"])))){throw __rt.call(ServiceError,["ROUND_PENDING","Finish the presentation first.",409],__rt.kw([]));}
amount=__rt.item(pending,"total_minor");
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["sid",sid],["phase","ready"],["pending",null]]));
return __rt.call(Outcome,[state,__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",__rt.item(pending,"round_id")],["lines",[__rt.call(wire,[5,__rt.item(pending,"total_coins")],__rt.kw([])),__rt.call(wire,[6,amount],__rt.kw([]))]],["next_phase","ready"],["confirm",true]])),0,amount],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(state,"phase"),()=>"collect"]))){__rt.setitem(state,"sid",sid);
return __rt.call(Outcome,[state,__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",__rt.item(pending,"round_id")],["lines",[__rt.call(wire,[3,0,__rt.item(pending,"total_coins"),__rt.item(pending,"total_minor"),0,1],__rt.kw([]))]],["next_phase","collect"]])),0,0],__rt.kw([]));}
if(__rt.truth(__rt.item(pending,"queue"))){lines=__rt.call(__rt.attr(__rt.item(pending,"queue"),"pop"),[0],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.unary("Not",__rt.item(pending,"queue")),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(pending,"get"),["presentation_version",2],__rt.kw([])),()=>3])))){__rt.setitem(state,"phase","collect");}}else{lines=[__rt.call(wire,[3,0,__rt.item(pending,"total_coins"),__rt.item(pending,"total_minor"),0,1],__rt.kw([]))];
__rt.setitem(state,"phase",(__rt.truth(__rt.item(pending,"total_minor"))?"collect":"ready"));
if(__rt.truth(__rt.unary("Not",__rt.item(pending,"total_minor")))){__rt.call(__rt.attr(lines,"append"),["6 0"],__rt.kw([]));
__rt.setitem(state,"pending",null);}}
__rt.setitem(state,"sid",sid);
return __rt.call(Outcome,[state,__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",__rt.item(pending,"round_id")],["lines",lines],["next_phase",__rt.item(state,"phase")]])),0,0],__rt.kw([]));}
if(__rt.truth(pending)){throw __rt.call(ServiceError,["ROUND_PENDING","Finish the previous round.",409],__rt.kw([]));}
{const __t43=Array.from(__rt.iter(__rt.tuple([__rt.item(bet,"denom"),__rt.item(bet,"ultra")])));denom=__t43[0];ultra=__t43[1];}
result=__rt.call(__rt.attr(self,"generate"),[__rt.call(__rt.attr(random,"Random"),[__rt.call(__rt.b["str"],[seed],__rt.kw([]))],__rt.kw([])),denom,ultra,__rt.call(__rt.attr(__rt.item(state,"progress"),"get"),[__rt.call(__rt.b["str"],[denom],__rt.kw([])),0],__rt.kw([]))],__rt.kw([]));
__rt.setitem(__rt.item(state,"progress"),__rt.call(__rt.b["str"],[denom],__rt.kw([])),__rt.item(result,"progress"));
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["sid",sid],["phase","pending"],["last_denom",denom],["ultra",ultra],["last_grid",__rt.item(result,"initial_grid")],["pending",__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",sid],["queue",__rt.item(result,"queue")],["all_queue",__rt.call(__rt.attr(copy,"deepcopy"),[__rt.item(result,"queue")],__rt.kw([]))],["total_coins",__rt.item(result,"total_coins")],["total_minor",__rt.item(result,"total_minor")],["initial_lines",__rt.item(result,"lines")],["presentation_version",3]]))]]));
return __rt.call(Outcome,[state,__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",sid],["lines",__rt.item(result,"lines")],["next_phase","pending"],["total_minor",__rt.item(result,"total_minor")],["bonus",__rt.item(result,"bonus")],["ultra",ultra],["denom",denom]])),__rt.bin("Mult",(__rt.truth(ultra)?15:10),denom),0],__rt.kw([]));return null;})});
