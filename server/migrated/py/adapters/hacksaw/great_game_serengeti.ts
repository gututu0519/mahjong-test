// Migrated from py/adapters/hacksaw/great_game_serengeti.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
const __file__=__rt.sourcePath("py/adapters/hacksaw/great_game_serengeti.py");
export let Adapter:any,CLIENT:any,Path:any,ServiceError:any,copy:any,datetime:any,json:any,timezone:any;

copy=__rt.modules["copy"];
datetime=__rt.attr(__rt.modules["datetime"],"datetime");
timezone=__rt.attr(__rt.modules["datetime"],"timezone");
json=__rt.modules["json"];
Path=__rt.attr(__rt.modules["pathlib"],"Path");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
CLIENT=__rt.bin("Div",__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),3),"clients/great-game-serengeti");
Adapter=__rt.cls("Adapter",[],{"__init__":__rt.fn("__init__",{names:["self", "service"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,service){__rt.setattr(self,"service",service);
__rt.setattr(self,"auth",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/authenticate.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(self,"partner",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/partner-settings.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(self,"info",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/game-info.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));return null;}),"response":__rt.fn("response",{names:["self", "token"],kwonly:[],defaults:{"token":null},vararg:null,kwarg:"fields"},function(self,token,fields){let balance;balance=(__rt.truth(__rt.compare(["Is"],[()=>token,()=>null]))?null:__rt.dict([["currencyCode","EUR"],["balance",__rt.call(__rt.b["str"],[__rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([])),"balance_minor")],__rt.kw([]))],["realBalance",null],["bonusBalance",null]]));
return __rt.call(__rt.b["dict"],[],__rt.kw([["statusCode",0],["statusMessage",""],["accountBalance",balance],["statusData",null],["dialog",null],["customData",null],["serverTime",__rt.call(__rt.attr(__rt.call(__rt.attr(datetime,"now"),[__rt.attr(timezone,"utc")],__rt.kw([])),"strftime"),["%Y-%m-%dT%H:%M:%SZ"],__rt.kw([]))],[null,fields]]));return null;}),"authenticate":__rt.fn("authenticate",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){let current,data,pending,state;current=__rt.call(__rt.attr(__rt.attr(self,"service"),"state"),[token,"great-game-serengeti"],__rt.kw([]));
state=__rt.item(current,"state");
data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(self,"auth")],__rt.kw([]));
__rt.call(__rt.attr(data,"update"),[__rt.call(__rt.attr(self,"response"),[token],__rt.kw([]))],__rt.kw([]));
__rt.call(__rt.attr(data,"update"),[],__rt.kw([["playerId",__rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([])),"player_id")],["name","Player"],["sessionUuid",token],["languageCode","en-us"],["roundId","0"],["roundStatus",null],["pendingWin","0"],["events",null],["defaultBetLevel",__rt.call(__rt.b["str"],[__rt.item(state,"last_bet_minor")],__rt.kw([]))],["gameState",null]]));
if(__rt.truth(__rt.item(state,"pending"))){pending=__rt.item(state,"pending");
__rt.call(__rt.attr(data,"update"),[],__rt.kw([["roundId",__rt.item(pending,"round_id")],["roundStatus","wfwpc"],["pendingWin",__rt.call(__rt.b["str"],[__rt.item(pending,"win_minor")],__rt.kw([]))],["events",__rt.item(__rt.item(state,"last_round"),"events")],["gameState",__rt.dict([["bet",__rt.dict([["betAmount",__rt.call(__rt.b["str"],[__rt.item(pending,"bet_minor")],__rt.kw([]))],[null,(__rt.truth(__rt.compare(["NotEq"],[()=>__rt.item(pending,"mode"),()=>"base"]))?__rt.dict([["buyBonus",__rt.item(pending,"mode")],["buyBonusBetMultiplier",__rt.call(__rt.b["str"],[__rt.item(__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"service"),"registry"),"get"),["great-game-serengeti"],__rt.kw([])),"config"),"costs"),__rt.item(pending,"mode"))],__rt.kw([]))]]):__rt.dict([]))]])],["possibleActions",[]]])]]));}
return data;return null;}),"bet":__rt.fn("bet",{names:["self", "request"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,request){let amount,bets,cached,continuation,current,data,db,item,key,payload,player,previous,result,token;token=__rt.call(__rt.attr(request,"get"),["sessionUuid"],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[token,__rt.b["str"]],__rt.kw([]))),()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[__rt.call(__rt.attr(request,"get"),["seq"],__rt.kw([]))],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.compare(["Lt"],[()=>__rt.item(request,"seq"),()=>1])))){throw __rt.call(ServiceError,["REQUEST_INVALID","A session and sequence are required."],__rt.kw([]));}
continuation=__rt.call(__rt.attr(request,"get"),["continueInstructions"],__rt.kw([]));
if(__rt.truth(__rt.compare(["IsNot"],[()=>continuation,()=>null]))){if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>continuation,()=>__rt.dict([["action","win_presentation_complete"]])]),()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[__rt.call(__rt.attr(request,"get"),["roundId"],__rt.kw([])),__rt.b["str"]],__rt.kw([])))))){throw __rt.call(ServiceError,["REQUEST_INVALID","Unknown continuation."],__rt.kw([]));}
payload=__rt.call(__rt.b["dict"],[],__rt.kw([["action","confirm"],["round_id",__rt.item(request,"roundId")]]));}else{bets=__rt.call(__rt.attr(request,"get"),["bets"],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[bets,__rt.b["list"]],__rt.kw([]))),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.b["len"],[bets],__rt.kw([])),()=>1]),()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[__rt.item(bets,0),__rt.b["dict"]],__rt.kw([])))))){throw __rt.call(ServiceError,["BET_INVALID","Expected one bet."],__rt.kw([]));}
item=__rt.item(bets,0);
if(__rt.truth(__rt.bin("Sub",__rt.call(__rt.b["set"],[item],__rt.kw([])),__rt.set(["betAmount","buyBonus"])))){throw __rt.call(ServiceError,["BET_INVALID","Unknown bet field."],__rt.kw([]));}
amount=__rt.call(__rt.attr(item,"get"),["betAmount"],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[amount,__rt.b["str"]],__rt.kw([]))),()=>__rt.unary("Not",__rt.call(__rt.attr(amount,"isdecimal"),[],__rt.kw([])))))){throw __rt.call(ServiceError,["BET_INVALID","Bet amount must be an integer string."],__rt.kw([]));}
if(__rt.truth(__rt.or_(()=>__rt.call(__rt.attr(request,"get"),["offerId"],__rt.kw([])),()=>__rt.call(__rt.attr(request,"get"),["promotionId"],__rt.kw([]))))){throw __rt.call(ServiceError,["BET_INVALID","No promotion is attached to this account."],__rt.kw([]));}
payload=__rt.call(__rt.b["dict"],[],__rt.kw([["bet_minor",__rt.call(__rt.b["int"],[amount],__rt.kw([]))],["mode",__rt.or_(()=>__rt.call(__rt.attr(item,"get"),["buyBonus"],__rt.kw([])),()=>"base")]]));}
key=__rt.bin("Add","hacksaw:",__rt.call(__rt.b["str"],[__rt.item(request,"seq")],__rt.kw([])));
current=__rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"state"),[token,"great-game-serengeti"],__rt.kw([])),"state");
previous=__rt.item(current,"sid");
{const __t1=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"service"),"connection"),[],__rt.kw([])));let __t3=false;db=__t1.value;try{player=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"service"),"sessions"),"_player"),[db,token],__rt.kw([]));
cached=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?",__rt.tuple([__rt.item(player,"id"),"great-game-serengeti",key])],__rt.kw([])),"fetchone"),[],__rt.kw([]));
if(__rt.truth(cached)){previous=__rt.item(__rt.call(__rt.attr(json,"loads"),[__rt.item(cached,"request_json")],__rt.kw([])),"previous_sid");}}catch(__t2){__t3=true;if(!__t1.exit(__t2))throw __t2;}finally{if(!__t3)__t1.exit(null);}}
result=__rt.call(__rt.attr(__rt.attr(self,"service"),"spin"),[token,"great-game-serengeti",key,previous,payload],__rt.kw([]));
data=__rt.call(__rt.attr(self,"response"),[token],__rt.kw([["round",__rt.item(__rt.item(result,"outcome"),"round")],["promotionNoLongerAvailable",false],["promotionWin",null],["offer",null],["freeRoundOffer",null]]));
__rt.setitem(__rt.item(data,"accountBalance"),"balance",__rt.call(__rt.b["str"],[__rt.item(__rt.item(result,"wallet"),"after_minor")],__rt.kw([])));
return data;return null;})});
