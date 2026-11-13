// Migrated from py/games/dr_zappo/engine.py. Runtime is Node.js only.
import * as __rt from "../../../../other/shared/compat/runtime.js";
const __file__=__rt.sourcePath("py/games/dr_zappo/engine.py");
export let DrZappo:any,Outcome:any,Path:any,ServiceError:any,action:any,copy:any,decode_grid:any,encode_grid:any,hashlib:any,json:any,laser_path:any,mask:any,random:any;

copy=__rt.modules["copy"];
hashlib=__rt.modules["hashlib"];
json=__rt.modules["json"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
random=__rt.modules["random"];
Outcome=__rt.attr(__rt.modules["py.core.contracts"],"Outcome");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
encode_grid=__rt.fn("encode_grid",{names:["grid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(grid){if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[grid],__rt.kw([])),()=>20]))){throw __rt.call(__rt.b["ValueError"],["Expected 5 by 4 grid"],__rt.kw([]));}
return __rt.bin("Add","-,",__rt.call(__rt.attr("","join"),[(function*(){let v;for(const __t1 of __rt.iter(grid)){v=__t1;yield __rt.call(__rt.b["chr"],[__rt.bin("Add",v,40)],__rt.kw([]));}})()],__rt.kw([])));return null;});
decode_grid=__rt.fn("decode_grid",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[value,__rt.b["str"]],__rt.kw([]))),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[value],__rt.kw([])),()=>22]),()=>__rt.unary("Not",__rt.call(__rt.attr(value,"startswith"),["-,"],__rt.kw([])))))){throw __rt.call(__rt.b["ValueError"],["Expected 5 by 4 grid"],__rt.kw([]));}
return (()=>{let v;const __out:any[]=[];for(const __t2 of __rt.iter(__rt.item(value,__rt.slice(2,null,null)))){v=__t2;__out.push(__rt.bin("Sub",__rt.call(__rt.b["ord"],[v],__rt.kw([])),40));}return __out;})();return null;});
mask=__rt.fn("mask",{names:["positions"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(positions){return __rt.call(__rt.attr("","join"),[(function*(){let p;for(const __t3 of __rt.iter(__rt.call(__rt.b["range"],[20],__rt.kw([])))){p=__t3;yield (__rt.truth(__rt.compare(["In"],[()=>p,()=>positions]))?"1":"0");}})()],__rt.kw([]));return null;});
action=__rt.fn("action",{names:["name"],kwonly:[],defaults:{},vararg:null,kwarg:"data"},function(name,data){return __rt.call(__rt.b["dict"],[],__rt.kw([["at",name],["data",data]]));return null;});
laser_path=__rt.fn("laser_path",{names:["origin", "direction"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(origin,direction){let dx,dy,path,x,y;
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotIn"],[()=>origin,()=>__rt.call(__rt.b["range"],[15,20],__rt.kw([]))]),()=>__rt.compare(["NotIn"],[()=>direction,()=>__rt.tuple(["UpLeft","Up","UpRight"])])))){throw __rt.call(__rt.b["ValueError"],["Invalid eye position or direction"],__rt.kw([]));}
{const __t4=Array.from(__rt.iter(__rt.tuple([__rt.item(__rt.dict([["UpLeft",__rt.unary("USub",1)],["Up",0],["UpRight",1]]),direction),__rt.unary("USub",1)])));dx=__t4[0];dy=__t4[1];}
{const __t5=Array.from(__rt.iter(__rt.tuple([__rt.bin("Mod",origin,5),3,[]])));x=__t5[0];y=__t5[1];path=__t5[2];}
while(__rt.truth(true)){if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>y,()=>0]),()=>__rt.compare(["In"],[()=>x,()=>__rt.tuple([0,4])])))){return path;}
if(__rt.truth(__rt.unary("Not",__rt.compare(["LtE", "Lt"],[()=>0,()=>__rt.bin("Add",x,dx),()=>5])))){dx=__rt.unary("USub",dx);}
if(__rt.truth(__rt.compare(["Lt"],[()=>__rt.bin("Add",y,dy),()=>0]))){dy=__rt.unary("USub",dy);
if(__rt.truth(__rt.compare(["Eq"],[()=>dx,()=>0]))){__rt.call(__rt.attr(path,"append"),[x],__rt.kw([]));}}
{const __t6=Array.from(__rt.iter(__rt.tuple([__rt.bin("Add",x,dx),__rt.bin("Add",y,dy)])));x=__t6[0];y=__t6[1];}
if(__rt.truth(__rt.compare(["Gt"],[()=>y,()=>3]))){return path;}
__rt.call(__rt.attr(path,"append"),[__rt.bin("Add",__rt.bin("Mult",y,5),x)],__rt.kw([]));}return null;});
DrZappo=__rt.cls("DrZappo",[],{"game_id":"dr-zappo","title":"Dr Zappo","version":"1.0.0","minor_unit":100,"__init__":__rt.fn("__init__",{names:["self", "config"],kwonly:[],defaults:{"config":null},vararg:null,kwarg:null},function(self,config){__rt.setattr(self,"config",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(Path,[__rt.or_(()=>config,()=>__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["config.json"],__rt.kw([])))],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(self,"ruleset_id",__rt.item(__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[__rt.call(__rt.attr(__rt.call(__rt.attr(json,"dumps"),[__rt.call(__rt.b["dict"],[],__rt.kw([["engine",__rt.attr(self,"version")],["config",__rt.attr(self,"config")]]))],__rt.kw([["sort_keys",true]])),"encode"),[],__rt.kw([]))],__rt.kw([])),"hexdigest"),[],__rt.kw([])),__rt.slice(null,20,null)));return null;}),"initial_state":__rt.fn("initial_state",{names:["self", "seed"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,seed){return __rt.call(__rt.b["dict"],[],__rt.kw([["sid","0"],["phase","ready"],["pending",null],["last_round",null],["last_bet_minor",__rt.item(__rt.attr(self,"config"),"default_bet_minor")]]));return null;}),"public_state":__rt.fn("public_state",{names:["self", "state"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state){return __rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));return null;}),"normalize_bet":__rt.fn("normalize_bet",{names:["self", "payload"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,payload){let amount,mode;if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(ServiceError,["BET_INVALID","Expected an object."],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(payload,"get"),["action"],__rt.kw([])),()=>"confirm"]))){if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["set"],[payload],__rt.kw([])),()=>__rt.set(["action","round_id"])]),()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[__rt.item(payload,"round_id"),__rt.b["str"]],__rt.kw([])))))){throw __rt.call(ServiceError,["BET_INVALID","Invalid round confirmation."],__rt.kw([]));}
return __rt.call(__rt.b["dict"],[],__rt.kw([["action","confirm"],["round_id",__rt.item(payload,"round_id")]]));}
if(__rt.truth(__rt.bin("Sub",__rt.call(__rt.b["set"],[payload],__rt.kw([])),__rt.set(["bet_minor","mode"])))){throw __rt.call(ServiceError,["BET_INVALID","Unknown bet field."],__rt.kw([]));}
{const __t7=Array.from(__rt.iter(__rt.tuple([__rt.call(__rt.attr(payload,"get"),["bet_minor"],__rt.kw([])),__rt.call(__rt.attr(payload,"get"),["mode","base"],__rt.kw([]))])));amount=__t7[0];mode=__t7[1];}
if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[amount],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["NotIn"],[()=>amount,()=>__rt.item(__rt.attr(self,"config"),"bets_minor")]),()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[mode,__rt.b["str"]],__rt.kw([]))),()=>__rt.compare(["NotIn"],[()=>mode,()=>__rt.item(__rt.attr(self,"config"),"costs")])))){throw __rt.call(ServiceError,["BET_INVALID","Invalid bet amount or feature."],__rt.kw([]));}
return __rt.call(__rt.b["dict"],[],__rt.kw([["bet_minor",amount],["mode",mode]]));return null;}),"evaluate":__rt.fn("evaluate",{names:["self", "grid", "multipliers", "amount"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,grid,multipliers,amount){let best,candidate,cells,count,factors,line,mult,natural,p,payout,positions,symbol,tier,win,wins;
wins=[];
for(const __t8 of __rt.iter(__rt.item(__rt.attr(self,"config"),"lines"))){line=__t8;positions=(()=>{let col,row;const __out:any[]=[];for(const __t9 of __rt.iter(__rt.call(__rt.b["enumerate"],[line],__rt.kw([])))){{const __t10=Array.from(__rt.iter(__t9));col=__t10[0];row=__t10[1];}__out.push(__rt.bin("Add",__rt.bin("Mult",row,5),col));}return __out;})();
best=null;
natural=__rt.call(__rt.b["next"],[(function*(){let p;for(const __t11 of __rt.iter(positions)){p=__t11;if(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.item(grid,p),()=>0]))){yield __rt.item(grid,p);}}})(),0],__rt.kw([]));
for(const __t12 of __rt.iter(__rt.call(__rt.attr(__rt.b["dict"],"fromkeys"),[__rt.tuple([0,natural])],__rt.kw([])))){symbol=__t12;count=0;
for(const __t13 of __rt.iter(positions)){p=__t13;if(__rt.truth(__rt.and_(()=>__rt.compare(["NotEq"],[()=>__rt.item(grid,p),()=>symbol]),()=>__rt.compare(["NotEq"],[()=>__rt.item(grid,p),()=>0])))){break;}
count=__rt.bin("Add",count,1);}
tier=(__rt.truth(__rt.compare(["Eq"],[()=>count,()=>5]))?"_5_inf":__rt.bin("Add","_",__rt.call(__rt.b["str"],[count],__rt.kw([]))));
payout=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.item(__rt.attr(self,"config"),"payouts"),"get"),[__rt.call(__rt.b["str"],[symbol],__rt.kw([])),__rt.dict([])],__rt.kw([])),"get"),[tier,0],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.unary("Not",payout))){continue;}
cells=__rt.item(positions,__rt.slice(null,count,null));
mult=__rt.or_(()=>__rt.call(__rt.b["sum"],[(function*(){let p;for(const __t14 of __rt.iter(cells)){p=__t14;if(__rt.truth(__rt.compare(["Gt"],[()=>__rt.item(multipliers,p),()=>1]))){yield __rt.item(multipliers,p);}}})()],__rt.kw([])),()=>1);
win=__rt.bin("FloorDiv",__rt.bin("Mult",__rt.bin("Mult",amount,payout),mult),__rt.item(__rt.attr(self,"config"),"base_bet_level"));
candidate=__rt.call(action,["gridwin"],__rt.kw([["winAmount",__rt.call(__rt.b["str"],[win],__rt.kw([]))],["symbol",__rt.call(__rt.b["str"],[symbol],__rt.kw([]))],["mask",__rt.call(mask,[cells],__rt.kw([]))],["count",__rt.call(__rt.b["str"],[count],__rt.kw([]))]]));
factors=(()=>{let p;const __out:any[]=[];for(const __t15 of __rt.iter(cells)){p=__t15;if(__rt.truth(__rt.compare(["Gt"],[()=>__rt.item(multipliers,p),()=>1]))){__out.push(__rt.item(multipliers,p));}}return __out;})();
if(__rt.truth(factors)){__rt.call(__rt.attr(__rt.item(candidate,"data"),"update"),[],__rt.kw([["baseWinAmount",__rt.call(__rt.b["str"],[__rt.bin("FloorDiv",__rt.bin("Mult",amount,payout),__rt.item(__rt.attr(self,"config"),"base_bet_level"))],__rt.kw([]))],["winMultipliers",__rt.call(__rt.b["list"],[__rt.call(__rt.b["map"],[__rt.b["str"],factors],__rt.kw([]))],__rt.kw([]))]]));}
if(__rt.truth(__rt.or_(()=>__rt.compare(["Is"],[()=>best,()=>null]),()=>__rt.compare(["Gt"],[()=>win,()=>__rt.call(__rt.b["int"],[__rt.item(__rt.item(best,"data"),"winAmount")],__rt.kw([]))])))){best=candidate;}}
if(__rt.truth(best)){__rt.call(__rt.attr(wins,"append"),[best],__rt.kw([]));}}
return wins;return null;}),"lasers":__rt.fn("lasers",{names:["self", "grid", "rng", "game_mode"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,grid,rng,game_mode){let actions,available,direction,directions,eyes,increment,origin,p,path,results,transformed,values;transformed=__rt.call(__rt.b["list"],[grid],__rt.kw([]));
values=(()=>{let v;const __out:any[]=[];for(const __t16 of __rt.iter(grid)){v=__t16;__out.push((__rt.truth(__rt.compare(["In"],[()=>v,()=>__rt.tuple([0,13])]))?1:0));}return __out;})();
actions=[];
eyes=(()=>{let p;const __out:any[]=[];for(const __t17 of __rt.iter(__rt.call(__rt.b["range"],[15,20],__rt.kw([])))){p=__t17;if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.item(grid,p),()=>13]))){__out.push(p);}}return __out;})();
for(const __t18 of __rt.iter(eyes)){origin=__t18;available=(__rt.truth(__rt.compare(["Eq"],[()=>origin,()=>15]))?["Up","UpRight"]:(__rt.truth(__rt.compare(["Eq"],[()=>origin,()=>19]))?["UpLeft","Up"]:["UpLeft","Up","UpRight"]));
directions=__rt.call(__rt.attr(rng,"sample"),[available,(__rt.truth(__rt.compare(["In"],[()=>game_mode,()=>__rt.tuple(["fs_2","epic"])]))?2:1)],__rt.kw([]));
__rt.setitem(values,origin,__rt.call(__rt.b["max"],[1,__rt.item(values,origin)],__rt.kw([])));
for(const __t19 of __rt.iter(directions)){direction=__t19;{const __t20=Array.from(__rt.iter(__rt.tuple([__rt.call(laser_path,[origin,direction],__rt.kw([])),[]])));path=__t20[0];results=__t20[1];}
for(const __t21 of __rt.iter(path)){p=__t21;if(__rt.truth(__rt.item(values,p))){increment=(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"multiplier_probability")]))?__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.item(__rt.attr(self,"config"),"multiplier_values"),__rt.item(__rt.attr(self,"config"),"multiplier_weights")],__rt.kw([])),0):1);
__rt.setitem(values,p,__rt.bin("Add",__rt.item(values,p),increment));}else{__rt.setitem(values,p,(__rt.truth(__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"multiplier_probability")]))?__rt.item(__rt.call(__rt.attr(rng,"choices"),[__rt.item(__rt.attr(self,"config"),"multiplier_values"),__rt.item(__rt.attr(self,"config"),"multiplier_weights")],__rt.kw([])),0):1));}
__rt.setitem(transformed,p,0);
__rt.call(__rt.attr(results,"append"),[__rt.call(__rt.b["str"],[__rt.item(values,p)],__rt.kw([]))],__rt.kw([]));}
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["laser"],__rt.kw([["p",__rt.call(__rt.b["list"],[__rt.call(__rt.b["map"],[__rt.b["str"],path],__rt.kw([]))],__rt.kw([]))],["m",results],["d",direction],["origin",__rt.call(__rt.b["str"],[origin],__rt.kw([]))]]))],__rt.kw([]));}
__rt.setitem(transformed,origin,0);}
if(__rt.truth(eyes)){__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["totalMulti"],__rt.kw([["m",__rt.call(__rt.b["list"],[__rt.call(__rt.b["map"],[__rt.b["str"],values],__rt.kw([]))],__rt.kw([]))]]))],__rt.kw([]));}
return __rt.tuple([actions,transformed,values]);return null;}),"generate":__rt.fn("generate",{names:["self", "rng", "amount", "mode"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,rng,amount,mode){let _,cap,emit,events,extra,free_count,free_mode,granted_total,play,played,remaining,total;{const __t22=Array.from(__rt.iter(__rt.tuple([[],0,0,null])));events=__t22[0];total=__t22[1];granted_total=__t22[2];free_mode=__t22[3];}
cap=__rt.bin("Mult",amount,__rt.item(__rt.attr(self,"config"),"maximum_win_multiplier"));
emit=__rt.fn("emit",{names:["kind", "data", "win"],kwonly:[],defaults:{"win":0},vararg:null,kwarg:null},function(kind,data,win){
win=__rt.call(__rt.b["min"],[win,__rt.bin("Sub",cap,total)],__rt.kw([]));
total=__rt.bin("Add",total,win);
__rt.call(__rt.attr(events,"append"),[__rt.call(__rt.b["dict"],[],__rt.kw([["et",2],["etn",kind],["en","0"],["ba","0"],["bc","0"],["wa",__rt.call(__rt.b["str"],[win],__rt.kw([]))],["wc","0"],["awa",__rt.call(__rt.b["str"],[total],__rt.kw([]))],["awc","0"],["c",data]]))],__rt.kw([]));return null;});
play=__rt.fn("play",{names:["game_mode", "forced"],kwonly:[],defaults:{"forced":null},vararg:null,kwarg:null},function(game_mode,forced){let actions,col,count,data,feature,final,free,grid,item,multipliers,paid,reels,remaining,scatter_count,wins;reels=__rt.item(__rt.attr(self,"config"),(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"base"]))?"reels":"free_reels"));
grid=(()=>{let p;const __out:any[]=[];for(const __t23 of __rt.iter(__rt.call(__rt.b["range"],[20],__rt.kw([])))){p=__t23;__out.push(__rt.call(__rt.attr(rng,"choice"),[__rt.item(reels,__rt.bin("Mod",p,5))],__rt.kw([])));}return __out;})();
scatter_count=0;
if(__rt.truth(__rt.compare(["In"],[()=>forced,()=>__rt.tuple(["fs","fs_2"])]))){scatter_count=(__rt.truth(__rt.compare(["Eq"],[()=>forced,()=>"fs"]))?3:4);}else{if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>game_mode,()=>"base"]),()=>__rt.compare(["NotEq"],[()=>mode,()=>"mod_laser"]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.bin("Mult",__rt.item(__rt.attr(self,"config"),"free_trigger_probability"),(__rt.truth(__rt.compare(["Eq"],[()=>mode,()=>"mod_bonus"]))?5:1))])))){scatter_count=__rt.item(__rt.call(__rt.attr(rng,"choices"),[[3,4,5],__rt.item(__rt.attr(self,"config"),"free_scatter_weights")],__rt.kw([])),0);}else{if(__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>game_mode,()=>__rt.tuple(["fs","fs_2"])]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"retrigger_probability")])))){scatter_count=__rt.item(__rt.call(__rt.attr(rng,"choices"),[[2,3],[9,1]],__rt.kw([])),0);}}}
if(__rt.truth(scatter_count)){for(const __t24 of __rt.iter(__rt.call(__rt.attr(rng,"sample"),[__rt.call(__rt.b["range"],[5],__rt.kw([])),scatter_count],__rt.kw([])))){col=__t24;__rt.setitem(grid,__rt.bin("Add",__rt.bin("Mult",__rt.call(__rt.attr(rng,"randrange"),[4],__rt.kw([])),5),col),12);}}else{if(__rt.truth(__rt.or_(()=>__rt.compare(["Eq"],[()=>forced,()=>"mod_laser"]),()=>__rt.compare(["Eq"],[()=>game_mode,()=>"epic"]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"base"]))?"eye_probability":"free_eye_probability"))])))){count=(__rt.truth(__rt.compare(["Eq"],[()=>forced,()=>"mod_laser"]))?2:1);
while(__rt.truth(__rt.and_(()=>__rt.compare(["Lt"],[()=>count,()=>5]),()=>__rt.compare(["Lt"],[()=>__rt.call(__rt.attr(rng,"random"),[],__rt.kw([])),()=>__rt.item(__rt.attr(self,"config"),"additional_eye_probability")])))){count=__rt.bin("Add",count,1);}
for(const __t25 of __rt.iter(__rt.call(__rt.attr(rng,"sample"),[__rt.call(__rt.b["range"],[5],__rt.kw([])),count],__rt.kw([])))){col=__t25;__rt.setitem(grid,__rt.bin("Add",15,col),13);}}}
{const __t26=Array.from(__rt.iter(__rt.call(__rt.attr(self,"lasers"),[grid,rng,game_mode],__rt.kw([]))));actions=__t26[0];final=__t26[1];multipliers=__t26[2];}
wins=__rt.call(__rt.attr(self,"evaluate"),[final,multipliers,amount],__rt.kw([]));
remaining=__rt.bin("Sub",cap,total);
for(const __t27 of __rt.iter(wins)){item=__t27;paid=__rt.call(__rt.b["min"],[__rt.call(__rt.b["int"],[__rt.item(__rt.item(item,"data"),"winAmount")],__rt.kw([])),remaining],__rt.kw([]));
__rt.setitem(__rt.item(item,"data"),"winAmount",__rt.call(__rt.b["str"],[paid],__rt.kw([])));
remaining=__rt.bin("Sub",remaining,paid);}
__rt.call(__rt.attr(actions,"extend"),[wins],__rt.kw([]));
free=0;
feature=null;
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>game_mode,()=>"base"]),()=>__rt.compare(["GtE"],[()=>scatter_count,()=>3])))){{const __t28=Array.from(__rt.iter(__rt.tuple([10,__rt.item(__rt.dict([[3,"fs"],[4,"fs_2"],[5,"epic"]]),scatter_count)])));free=__t28[0];feature=__t28[1];}
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["gridwin"],__rt.kw([["winAmount","0"],["symbol","12"],["mask",__rt.call(mask,[(()=>{let p,v;const __out:any[]=[];for(const __t29 of __rt.iter(__rt.call(__rt.b["enumerate"],[grid],__rt.kw([])))){{const __t30=Array.from(__rt.iter(__t29));p=__t30[0];v=__t30[1];}if(__rt.truth(__rt.compare(["Eq"],[()=>v,()=>12]))){__out.push(p);}}return __rt.set(__out);})()],__rt.kw([]))],["count",__rt.call(__rt.b["str"],[scatter_count],__rt.kw([]))]]))],__rt.kw([]));
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["bonusfeaturewon"],__rt.kw([["bfw",feature],["bfc","10"]]))],__rt.kw([]));}else{if(__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>game_mode,()=>__rt.tuple(["fs","fs_2"])]),()=>__rt.compare(["GtE"],[()=>scatter_count,()=>2])))){free=(__rt.truth(__rt.compare(["Eq"],[()=>scatter_count,()=>2]))?2:4);
__rt.call(__rt.attr(actions,"append"),[__rt.call(action,["retrigger"],__rt.kw([["s",__rt.call(__rt.b["str"],[free],__rt.kw([]))],["h",__rt.call(mask,[(()=>{let p,v;const __out:any[]=[];for(const __t31 of __rt.iter(__rt.call(__rt.b["enumerate"],[grid],__rt.kw([])))){{const __t32=Array.from(__rt.iter(__t31));p=__t32[0];v=__t32[1];}if(__rt.truth(__rt.compare(["Eq"],[()=>v,()=>12]))){__out.push(p);}}return __rt.set(__out);})()],__rt.kw([]))]]))],__rt.kw([]));}}
data=__rt.call(__rt.b["dict"],[],__rt.kw([["reelSet","default"],["grid",__rt.call(encode_grid,[grid],__rt.kw([]))]]));
if(__rt.truth(actions)){__rt.setitem(data,"actions",actions);}
__rt.call(emit,[__rt.bin("Add",(__rt.truth(__rt.compare(["Eq"],[()=>game_mode,()=>"base"]))?"":__rt.bin("Add",game_mode,"_")),"reveal"),data,__rt.call(__rt.b["sum"],[(function*(){let w;for(const __t33 of __rt.iter(wins)){w=__t33;yield __rt.call(__rt.b["int"],[__rt.item(__rt.item(w,"data"),"winAmount")],__rt.kw([]));}})()],__rt.kw([]))],__rt.kw([]));
return __rt.tuple([free,feature]);return null;});
{const __t34=Array.from(__rt.iter(__rt.call(play,["base",mode],__rt.kw([]))));free_count=__t34[0];free_mode=__t34[1];}
granted_total=free_count;
if(__rt.truth(__rt.and_(()=>free_count,()=>__rt.compare(["Lt"],[()=>total,()=>cap])))){__rt.call(emit,["feature_enter",__rt.call(__rt.b["dict"],[],__rt.kw([["bonusFeatureWon",free_mode],["bonusFeatureCount",__rt.call(__rt.b["str"],[free_count],__rt.kw([]))]]))],__rt.kw([]));
{const __t35=Array.from(__rt.iter(__rt.tuple([free_count,0])));remaining=__t35[0];played=__t35[1];}
while(__rt.truth(__rt.and_(()=>remaining,()=>__rt.compare(["Lt"],[()=>total,()=>cap])))){remaining=__rt.bin("Sub",remaining,1);
{const __t36=Array.from(__rt.iter(__rt.call(play,[free_mode],__rt.kw([]))));extra=__t36[0];_=__t36[1];}
remaining=__rt.bin("Add",remaining,extra);
granted_total=__rt.bin("Add",granted_total,extra);
played=__rt.bin("Add",played,1);
if(__rt.truth(__rt.compare(["Gt"],[()=>played,()=>1000]))){throw __rt.call(__rt.b["RuntimeError"],["Generated bonus exceeds sanity limit"],__rt.kw([]));}}
if(__rt.truth(__rt.compare(["Lt"],[()=>total,()=>cap]))){__rt.call(emit,["feature_exit",__rt.dict([])],__rt.kw([]));}}
if(__rt.truth(__rt.compare(["GtE"],[()=>total,()=>cap]))){__rt.call(emit,["max_win_reached",__rt.dict([])],__rt.kw([]));}
return __rt.tuple([events,total,granted_total,free_mode]);return null;}),"step":__rt.fn("step",{names:["self", "state", "bet", "seed", "sid"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,state,bet,seed,sid){let amount,event,events,free_count,free_mode,mode,pending,round_data,total;state=__rt.call(__rt.attr(copy,"deepcopy"),[state],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(bet,"get"),["action"],__rt.kw([])),()=>"confirm"]))){pending=__rt.item(state,"pending");
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",pending),()=>__rt.compare(["NotEq"],[()=>__rt.item(pending,"round_id"),()=>__rt.item(bet,"round_id")])))){throw __rt.call(ServiceError,["ROUND_INVALID","No matching pending round.",409],__rt.kw([]));}
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["sid",sid],["phase","ready"],["pending",null]]));
return __rt.call(Outcome,[state,__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",__rt.item(pending,"round_id")],["next_phase","ready"],["confirm",true],["round",__rt.call(__rt.b["dict"],[],__rt.kw([["roundId",__rt.item(pending,"round_id")],["status","completed"],["possibleActions",[]],["events",[]]]))]])),0,__rt.item(pending,"win_minor")],__rt.kw([]));}
if(__rt.truth(__rt.item(state,"pending"))){throw __rt.call(ServiceError,["ROUND_PENDING","Complete the previous round presentation first.",409],__rt.kw([]));}
{const __t37=Array.from(__rt.iter(__rt.tuple([__rt.item(bet,"bet_minor"),__rt.item(bet,"mode")])));amount=__t37[0];mode=__t37[1];}
{const __t38=Array.from(__rt.iter(__rt.call(__rt.attr(self,"generate"),[__rt.call(__rt.attr(random,"Random"),[__rt.call(__rt.b["str"],[seed],__rt.kw([]))],__rt.kw([])),amount,mode],__rt.kw([]))));events=__t38[0];total=__t38[1];free_count=__t38[2];free_mode=__t38[3];}
round_data=__rt.call(__rt.b["dict"],[],__rt.kw([["roundId",sid],["status",(__rt.truth(total)?"wfwpc":"completed")],["possibleActions",[]],["events",events]]));
__rt.call(__rt.attr(state,"update"),[],__rt.kw([["sid",sid],["last_bet_minor",amount],["last_round",round_data],["phase",(__rt.truth(total)?"pending":"ready")],["pending",(__rt.truth(total)?__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",sid],["win_minor",total],["bet_minor",amount],["mode",mode]])):null)]]));
event=__rt.call(__rt.b["dict"],[],__rt.kw([["round_id",sid],["next_phase",__rt.item(state,"phase")],["round",round_data],["bet_minor",amount],["mode",mode],["total_minor",total],["free_spins",free_count],["free_mode",free_mode]]));
return __rt.call(Outcome,[state,event,__rt.bin("Mult",amount,__rt.item(__rt.item(__rt.attr(self,"config"),"costs"),mode)),0],__rt.kw([]));return null;})});
