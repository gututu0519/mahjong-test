// Migrated from py/adapters/jili/jokers_fortune_winx.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
import * as __m0 from "./wire.js";
const __file__=__rt.sourcePath("py/adapters/jili/jokers_fortune_winx.py");
export let Adapter:any,CLIENT:any,Decimal:any,Path:any,SCHEMAS:any,ServiceError:any,copy:any,decode:any,encode:any,json:any,pack:any,time:any,unpack:any,varint:any;

copy=__rt.modules["copy"];
json=__rt.modules["json"];
time=__rt.modules["time"];
Decimal=__rt.attr(__rt.modules["decimal"],"Decimal");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
encode=__rt.attr(__m0,"encode");
decode=__rt.attr(__m0,"decode");
varint=__rt.attr(__m0,"varint");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
SCHEMAS=__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",__rt.item(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"parents"),1),"tada/fortune_gems2_schema.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]));
__rt.call(__rt.attr(SCHEMAS,"update"),[__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["jokers_fortune_winx_schema.json"],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]))],__rt.kw([]));
CLIENT=__rt.bin("Div",__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),3),"clients/jokers-fortune-winx");
pack=__rt.fn("pack",{names:["name", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(name,value){return __rt.call(__rt.b["list"],[__rt.call(encode,[__rt.item(SCHEMAS,name),value,SCHEMAS],__rt.kw([]))],__rt.kw([]));return null;});
unpack=__rt.fn("unpack",{names:["name", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(name,value){return __rt.call(decode,[__rt.item(SCHEMAS,name),value,SCHEMAS],__rt.kw([]));return null;});
Adapter=__rt.cls("Adapter",[],{"__init__":__rt.fn("__init__",{names:["self", "service"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,service){__rt.setattr(self,"service",service);
__rt.setattr(self,"login_template",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/login.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(self,"info_template",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/info.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));return null;}),"login":__rt.fn("login",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){let data,wallet;wallet=__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([]));
data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(self,"login_template")],__rt.kw([]));
__rt.setitem(data,"token",token);
__rt.setitem(__rt.item(data,"profile"),"coin",__rt.bin("Div",__rt.item(wallet,"balance_minor"),10000));
__rt.setitem(__rt.item(data,"response"),"time",__rt.call(__rt.b["int"],[__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))],__rt.kw([])));
return data;return null;}),"info":__rt.fn("info",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){let data,state;state=__rt.call(__rt.attr(__rt.attr(self,"service"),"state"),[token,"jokers-fortune-winx"],__rt.kw([]));
data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(self,"info_template")],__rt.kw([]));
__rt.setitem(__rt.item(__rt.item(data,"WalletInfo"),0),"coin",__rt.bin("Div",__rt.item(state,"balance_minor"),10000));
// Keep the captured wire wallet identifier; its display currency belongs to the signed merchant.
if (self.service.merchant_currency) {
  const wallet = __rt.item(__rt.item(data,"WalletInfo"),0);
  __rt.setitem(wallet,"currencyName",self.service.merchant_currency);
  __rt.setitem(wallet,"currencySymbol",self.service.merchant_currency);
}
__rt.setitem(__rt.item(__rt.item(data,"WalletInfo"),0),"bet",(()=>{let b;const __out:any[]=[];for(const __t1 of __rt.iter(__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"service"),"registry"),"get"),["jokers-fortune-winx"],__rt.kw([])),"config"),"bets_minor"))){b=__t1;__out.push(__rt.bin("Div",b,10000));}return __out;})());
__rt.setitem(data,"lastBet",__rt.bin("Div",__rt.item(__rt.item(state,"state"),"last_bet_minor"),10000));
return __rt.call(pack,["GameInfoAck",data],__rt.kw([]));return null;}),"handle":__rt.fn("handle",{names:["self", "token", "ack", "payload", "key"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,ack,payload,key){let amount,cached,data,db,event,money,notice,player,previous_sid,replies,req,result,sid,state,struct;if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[ack],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["list"]],__rt.kw([]))),()=>__rt.compare(["Gt"],[()=>__rt.call(__rt.b["len"],[payload],__rt.kw([])),()=>16384]),()=>__rt.call(__rt.b["any"],[(function*(){let v;for(const __t2 of __rt.iter(payload)){v=__t2;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[v],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>v,()=>255])));}})()],__rt.kw([]))))){throw __rt.call(ServiceError,["INVALID_REQUEST","Invalid TaDa request."],__rt.kw([]));}
if(__rt.truth(__rt.compare(["In"],[()=>ack,()=>__rt.tuple([19,21,25,27,33,51,60])]))){__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>ack,()=>19]),()=>__rt.compare(["NotEq"],[()=>payload,()=>[8,80]])))){throw __rt.call(ServiceError,["CURRENCY_INVALID","Only the captured SC wallet is available."],__rt.kw([]));}
replies=__rt.dict([[19,[24,1]],[21,[]],[25,[]],[27,[]],[33,[10,2,8,1,10,2,8,2,10,2,8,3]],[51,[]],[60,[]]]);
return __rt.call(__rt.b["dict"],[],__rt.kw([["type",ack],["ret",(__rt.truth(__rt.compare(["Eq"],[()=>ack,()=>60]))?801:0)],["error_msg",""],["data",__rt.item(replies,ack)]]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>ack,()=>1]))){data=__rt.call(__rt.attr(self,"info"),[token],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>ack,()=>2]))){struct=__rt.modules["struct"];
money=__rt.bin("Div",__rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([])),"balance_minor"),10000);
notice=__rt.bin("Add",__rt.bin("Add",Buffer.from([8, 4, 17]),__rt.call(__rt.attr(struct,"pack"),["<d",money],__rt.kw([]))),Buffer.from([40, 80]));
data=__rt.call(__rt.b["list"],[__rt.bin("Add",__rt.bin("Add",Buffer.from([10]),__rt.call(varint,[__rt.call(__rt.b["len"],[notice],__rt.kw([]))],__rt.kw([]))),notice)],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["In"],[()=>ack,()=>__rt.tuple([0,4,36])]))){state=__rt.call(__rt.attr(__rt.attr(self,"service"),"state"),[token,"jokers-fortune-winx"],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>ack,()=>0]))){req=__rt.call(unpack,["SpinReq",payload],__rt.kw([]));
if(__rt.truth(__rt.bin("Sub",__rt.call(__rt.b["set"],[req],__rt.kw([])),__rt.set(["bet","special","extraSpin","clientRecord"])))){throw __rt.call(ServiceError,["BET_INVALID","Unsupported Joker's Fortune WinX spin request."],__rt.kw([]));}
if(__rt.truth(__rt.call(__rt.b["any"],[__rt.call(__rt.attr(__rt.call(__rt.attr(req,"get"),["special",__rt.dict([])],__rt.kw([])),"values"),[],__rt.kw([]))],__rt.kw([])))){if(__rt.truth(__rt.bin("Sub",__rt.call(__rt.b["set"],[(function*(){let k,v;for(const __t3 of __rt.iter(__rt.call(__rt.attr(__rt.item(req,"special"),"items"),[],__rt.kw([])))){{const __t4=Array.from(__rt.iter(__t3));k=__t4[0];v=__t4[1];}if(__rt.truth(v)){yield k;}}})()],__rt.kw([])),__rt.set(["turbo"])))){throw __rt.call(ServiceError,["BET_INVALID","Unsupported spin option."],__rt.kw([]));}}
if(__rt.truth(__rt.and_(()=>__rt.compare(["In"],[()=>"extraSpin",()=>req]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(__rt.item(req,"extraSpin"),"get"),["Index",0],__rt.kw([])),()=>0])))){throw __rt.call(ServiceError,["BET_INVALID","Invalid Extra Bet selection."],__rt.kw([]));}
amount=__rt.bin("Mult",__rt.call(Decimal,[__rt.call(__rt.b["str"],[__rt.call(__rt.attr(req,"get"),["bet",0],__rt.kw([]))],__rt.kw([]))],__rt.kw([])),10000);
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.attr(amount,"is_finite"),[],__rt.kw([]))),()=>__rt.compare(["NotEq"],[()=>amount,()=>__rt.call(__rt.attr(amount,"to_integral_value"),[],__rt.kw([]))])))){throw __rt.call(ServiceError,["BET_INVALID","Invalid bet precision."],__rt.kw([]));}
previous_sid=__rt.item(__rt.item(state,"state"),"sid");
{const __t5=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"service"),"connection"),[],__rt.kw([])));let __t7=false;db=__t5.value;try{player=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"service"),"sessions"),"_player"),[db,token],__rt.kw([]));
cached=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?",__rt.tuple([__rt.item(player,"id"),"jokers-fortune-winx",key])],__rt.kw([])),"fetchone"),[],__rt.kw([]));
if(__rt.truth(cached)){previous_sid=__rt.item(__rt.call(__rt.attr(json,"loads"),[__rt.item(cached,"request_json")],__rt.kw([])),"previous_sid");}}catch(__t6){__t7=true;if(!__t5.exit(__t6))throw __t6;}finally{if(!__t7)__t5.exit(null);}}
result=__rt.call(__rt.attr(__rt.attr(self,"service"),"spin"),[token,"jokers-fortune-winx",key,previous_sid,__rt.call(__rt.b["dict"],[],__rt.kw([["bet_minor",__rt.call(__rt.b["int"],[amount],__rt.kw([]))],["extra",__rt.compare(["In"],[()=>"extraSpin",()=>req])]]))],__rt.kw([]));
{const __t8=Array.from(__rt.iter(__rt.tuple([__rt.item(result,"outcome"),__rt.item(__rt.item(result,"wallet"),"after_minor"),__rt.item(result,"sid")])));event=__t8[0];money=__t8[1];sid=__t8[2];}}else{{const __t9=Array.from(__rt.iter(__rt.tuple([__rt.item(__rt.item(state,"state"),"last_event"),__rt.item(state,"balance_minor"),__rt.item(__rt.item(state,"state"),"sid")])));event=__t9[0];money=__t9[1];sid=__t9[2];}
if(__rt.truth(__rt.unary("Not",event))){return __rt.call(__rt.b["dict"],[],__rt.kw([["type",ack],["ret",0],["error_msg",""],["data",[]]]));}
req=__rt.dict([["bet",__rt.bin("Div",__rt.item(event,"bet_minor"),10000)]]);
if(__rt.truth(__rt.item(event,"extra"))){__rt.setitem(req,"extraSpin",__rt.dict([]));}}
data=__rt.call(pack,["SpinResponse",__rt.call(__rt.b["dict"],[],__rt.kw([["data",__rt.call(pack,["SpinAck",__rt.item(event,"spin")],__rt.kw([]))],["service",__rt.dict([])],["totalWin",__rt.bin("Div",__rt.item(event,"total_minor"),10000)],["postMoney",__rt.bin("Div",money,10000)],["roundIndexV2",__rt.call(__rt.b["int"],[sid],__rt.kw([]))],["spinReq",req]]))],__rt.kw([]));}else{__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([]));
throw __rt.call(ServiceError,["ACK_UNSUPPORTED",__rt.bin("Add","Unrecognized TaDa command: ",__rt.call(__rt.b["str"],[ack],__rt.kw([])))],__rt.kw([]));}}}
return __rt.call(__rt.b["dict"],[],__rt.kw([["type",ack],["ret",0],["error_msg",""],["data",data]]));return null;})});
