// Migrated from py/adapters/jili/super_ace.py. Runtime is Node.js only.
import * as __rt from "../../../../../other/shared/compat/runtime.js";
import * as __m0 from "../../../../../other/shared/migrated/py/adapters/jili/wire.js";
const __file__=__rt.sourcePath("py/adapters/jili/super_ace.py");
export let Adapter:any,CLIENT:any,Decimal:any,Path:any,ROOT:any,SCHEMAS:any,ServiceError:any,copy:any,decode:any,encode:any,json:any,pack:any,time:any,unpack:any;

copy=__rt.modules["copy"];
json=__rt.modules["json"];
time=__rt.modules["time"];
Decimal=__rt.attr(__rt.modules["decimal"],"Decimal");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
encode=__rt.attr(__m0,"encode");
decode=__rt.attr(__m0,"decode");
SCHEMAS=__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"with_name"),["super_ace_schema.json"],__rt.kw([])),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([]));
ROOT=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),3);
CLIENT=__rt.bin("Div",ROOT,"clients/super-ace");
pack=__rt.fn("pack",{names:["name", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(name,value){return __rt.call(__rt.b["list"],[__rt.call(encode,[__rt.item(SCHEMAS,name),value,SCHEMAS],__rt.kw([]))],__rt.kw([]));return null;});
unpack=__rt.fn("unpack",{names:["name", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(name,value){return __rt.call(decode,[__rt.item(SCHEMAS,name),value,SCHEMAS],__rt.kw([]));return null;});
Adapter=__rt.cls("Adapter",[],{"__init__":__rt.fn("__init__",{names:["self", "service"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,service){__rt.setattr(self,"service",service);
__rt.setattr(self,"login_template",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/login.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));
__rt.setattr(self,"info_template",__rt.call(__rt.attr(json,"loads"),[__rt.call(__rt.attr(__rt.bin("Div",CLIENT,"fixtures/info.json"),"read_text"),[],__rt.kw([["encoding","utf-8"]]))],__rt.kw([])));return null;}),"login":__rt.fn("login",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){let data,wallet;wallet=__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([]));
data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(self,"login_template")],__rt.kw([]));
__rt.setitem(data,"token",token);
__rt.setitem(__rt.item(data,"profile"),"coin",__rt.bin("Div",__rt.item(wallet,"balance_minor"),10000));
__rt.setitem(__rt.item(data,"response"),"time",__rt.call(__rt.b["int"],[__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))],__rt.kw([])));
return data;return null;}),"info":__rt.fn("info",{names:["self", "token"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token){let data,state;state=__rt.call(__rt.attr(__rt.attr(self,"service"),"state"),[token,"super-ace"],__rt.kw([]));
data=__rt.call(__rt.attr(copy,"deepcopy"),[__rt.attr(self,"info_template")],__rt.kw([]));
__rt.setitem(__rt.item(__rt.item(data,"WalletInfo"),0),"coin",__rt.bin("Div",__rt.item(state,"balance_minor"),10000));
__rt.setitem(data,"lastBet",__rt.bin("Div",__rt.item(__rt.item(state,"state"),"last_bet_minor"),10000));
return __rt.call(pack,["GameInfoAck",data],__rt.kw([]));return null;}),"handle":__rt.fn("handle",{names:["self", "token", "ack", "payload", "key"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,token,ack,payload,key){let amount,buy,cached,data,db,event,mall,money,notice,player,previous_sid,req,result,sid,state,struct,varint;if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[ack],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[payload,__rt.b["list"]],__rt.kw([]))),()=>__rt.compare(["Gt"],[()=>__rt.call(__rt.b["len"],[payload],__rt.kw([])),()=>16384]),()=>__rt.call(__rt.b["any"],[(function*(){let v;for(const __t1 of __rt.iter(payload)){v=__t1;yield __rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[v],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>v,()=>255])));}})()],__rt.kw([]))))){throw __rt.call(ServiceError,["INVALID_REQUEST","Invalid JILI request."],__rt.kw([]));}
data=[];
if(__rt.truth(__rt.compare(["Eq"],[()=>ack,()=>1]))){data=__rt.call(__rt.attr(self,"info"),[token],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>ack,()=>2]))){varint=__rt.attr(__m0,"varint");
struct=__rt.modules["struct"];
money=__rt.bin("Div",__rt.item(__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([])),"balance_minor"),10000);
notice=__rt.bin("Add",__rt.bin("Add",Buffer.from([8, 4, 17]),__rt.call(__rt.attr(struct,"pack"),["<d",money],__rt.kw([]))),Buffer.from([40, 3]));
data=__rt.call(__rt.b["list"],[__rt.bin("Add",__rt.bin("Add",Buffer.from([10]),__rt.call(varint,[__rt.call(__rt.b["len"],[notice],__rt.kw([]))],__rt.kw([]))),notice)],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["In"],[()=>ack,()=>__rt.tuple([0,4,36])]))){state=__rt.call(__rt.attr(__rt.attr(self,"service"),"state"),[token,"super-ace"],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>ack,()=>0]))){req=__rt.call(unpack,["SpinReq",payload],__rt.kw([]));
amount=__rt.bin("Mult",__rt.call(Decimal,[__rt.call(__rt.b["str"],[__rt.call(__rt.attr(req,"get"),["bet",0],__rt.kw([]))],__rt.kw([]))],__rt.kw([])),10000);
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.attr(amount,"is_finite"),[],__rt.kw([]))),()=>__rt.compare(["NotEq"],[()=>amount,()=>__rt.call(__rt.attr(amount,"to_integral_value"),[],__rt.kw([]))])))){throw __rt.call(ServiceError,["BET_INVALID","Invalid bet precision."],__rt.kw([]));}
buy=__rt.compare(["In"],[()=>"mall",()=>req]);
if(__rt.truth(buy)){mall=__rt.item(req,"mall");
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(mall,"get"),["Type",0],__rt.kw([])),()=>0]),()=>__rt.compare(["NotEq"],[()=>__rt.call(__rt.attr(mall,"get"),["Index",0],__rt.kw([])),()=>0]),()=>__rt.compare(["NotEq"],[()=>__rt.bin("Mult",__rt.call(Decimal,[__rt.call(__rt.b["str"],[__rt.call(__rt.attr(mall,"get"),["Bet",0],__rt.kw([]))],__rt.kw([]))],__rt.kw([])),10000),()=>__rt.bin("Mult",amount,__rt.call(Decimal,["40.5"],__rt.kw([])))])))){throw __rt.call(ServiceError,["BET_INVALID","Purchase price does not match the bet."],__rt.kw([]));}}
if(__rt.truth(__rt.or_(()=>__rt.call(__rt.attr(req,"get"),["extraSpin"],__rt.kw([])),()=>__rt.call(__rt.attr(req,"get"),["freeSpin"],__rt.kw([]))))){throw __rt.call(ServiceError,["BET_INVALID","Free games are included in the original round response."],__rt.kw([]));}
previous_sid=__rt.item(__rt.item(state,"state"),"sid");
{const __t2=__rt.context(__rt.call(__rt.attr(__rt.attr(self,"service"),"connection"),[],__rt.kw([])));let __t4=false;db=__t2.value;try{player=__rt.call(__rt.attr(__rt.attr(__rt.attr(self,"service"),"sessions"),"_player"),[db,token],__rt.kw([]));
cached=__rt.call(__rt.attr(__rt.call(__rt.attr(db,"execute"),["SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?",__rt.tuple([__rt.item(player,"id"),"super-ace",key])],__rt.kw([])),"fetchone"),[],__rt.kw([]));
if(__rt.truth(cached)){previous_sid=__rt.item(__rt.call(__rt.attr(json,"loads"),[__rt.item(cached,"request_json")],__rt.kw([])),"previous_sid");}}catch(__t3){__t4=true;if(!__t2.exit(__t3))throw __t3;}finally{if(!__t4)__t2.exit(null);}}
result=__rt.call(__rt.attr(__rt.attr(self,"service"),"spin"),[token,"super-ace",key,previous_sid,__rt.call(__rt.b["dict"],[],__rt.kw([["bet_minor",__rt.call(__rt.b["int"],[amount],__rt.kw([]))],["buy_bonus",buy]]))],__rt.kw([]));
{const __t5=Array.from(__rt.iter(__rt.tuple([__rt.item(result,"outcome"),__rt.item(__rt.item(result,"wallet"),"after_minor"),__rt.item(result,"sid")])));event=__t5[0];money=__t5[1];sid=__t5[2];}}else{__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([]));
{const __t6=Array.from(__rt.iter(__rt.tuple([__rt.item(__rt.item(state,"state"),"last_event"),__rt.item(state,"balance_minor"),__rt.item(__rt.item(state,"state"),"sid")])));event=__t6[0];money=__t6[1];sid=__t6[2];}
if(__rt.truth(__rt.unary("Not",event))){return __rt.call(__rt.b["dict"],[],__rt.kw([["type",ack],["ret",0],["error_msg",""],["data",[]]]));}
req=__rt.dict([["bet",__rt.bin("Div",__rt.item(event,"bet_minor"),10000)]]);}
data=__rt.call(pack,["SpinResponse",__rt.call(__rt.b["dict"],[],__rt.kw([["data",__rt.call(pack,["AllPlate",__rt.dict([["plate",__rt.item(event,"plates")]])],__rt.kw([]))],["service",__rt.dict([])],["totalWin",__rt.bin("Div",__rt.item(event,"total_minor"),10000)],["postMoney",__rt.bin("Div",money,10000)],["roundIndexV2",__rt.call(__rt.b["int"],[sid],__rt.kw([]))],["spinReq",req]]))],__rt.kw([]));}else{__rt.call(__rt.attr(__rt.attr(self,"service"),"wallet"),[token],__rt.kw([]));
throw __rt.call(ServiceError,["ACK_UNSUPPORTED",__rt.bin("Add","Unrecognized JILI command: ",__rt.call(__rt.b["str"],[ack],__rt.kw([])))],__rt.kw([]));}}}
return __rt.call(__rt.b["dict"],[],__rt.kw([["type",ack],["ret",0],["error_msg",""],["data",data]]));return null;})});
