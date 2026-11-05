// Migrated from server/adapters/pg/protocol.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
const __file__=__rt.sourcePath("server/adapters/pg/protocol.py");
export let GAME_SALT:any,decode_request:any,double_field:any,field:any,fields:any,pack:any,patch:any,read_varint:any,struct:any,swaps:any,text_field:any,unpack:any,varint:any;

struct=__rt.modules["struct"];
GAME_SALT=11;
swaps=__rt.fn("swaps",{names:["length", "seed", "salt"],kwonly:[],defaults:{"salt":GAME_SALT},vararg:null,kwarg:null},function*(length,seed,salt){let a,b,i,x,y;{const __t1=Array.from(__rt.iter(__rt.tuple([__rt.bin("Add",seed,salt),__rt.bin("Add",__rt.bin("Add",seed,salt),1)])));a=__t1[0];b=__t1[1];}
for(const __t2 of __rt.iter(__rt.call(__rt.b["range"],[__rt.bin("Sub",length,1),0,__rt.unary("USub",1)],__rt.kw([])))){i=__t2;{const __t3=Array.from(__rt.iter(__rt.tuple([a,b])));x=__t3[0];y=__t3[1];}
a=y;
x=__rt.bin("BitXor",x,__rt.bin("LShift",x,23));
x=__rt.bin("BitXor",x,__rt.bin("RShift",x,17));
x=__rt.bin("BitXor",x,y);
x=__rt.bin("BitXor",x,__rt.bin("RShift",y,26));
b=x;
(yield __rt.tuple([i,__rt.bin("Mod",__rt.bin("Add",x,y),__rt.bin("Add",i,1))]));}return null;});
unpack=__rt.fn("unpack",{names:["data", "seed", "salt"],kwonly:[],defaults:{"seed":null,"salt":GAME_SALT},vararg:null,kwarg:null},function(data,seed,salt){let i,j,pos,raw;if(__rt.truth(__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>2,()=>__rt.call(__rt.b["len"],[data],__rt.kw([])),()=>16384])))){throw __rt.call(__rt.b["ValueError"],["Invalid binary message length"],__rt.kw([]));}
pos=__rt.bin("Mod",salt,__rt.bin("Sub",__rt.call(__rt.b["len"],[data],__rt.kw([])),1));
if(__rt.truth(__rt.compare(["Is"],[()=>seed,()=>null]))){seed=__rt.item(data,pos);}
raw=__rt.call(__rt.b["bytearray"],[__rt.bin("Add",__rt.item(data,__rt.slice(null,pos,null)),__rt.item(data,__rt.slice(__rt.bin("Add",pos,1),null,null)))],__rt.kw([]));
for(const __t4 of __rt.iter(__rt.call(__rt.b["reversed"],[__rt.call(__rt.b["list"],[__rt.call(swaps,[__rt.call(__rt.b["len"],[raw],__rt.kw([])),seed,salt],__rt.kw([]))],__rt.kw([]))],__rt.kw([])))){{const __t5=Array.from(__rt.iter(__t4));i=__t5[0];j=__t5[1];}{const __t6=Array.from(__rt.iter(__rt.tuple([__rt.item(raw,j),__rt.item(raw,i)])));__rt.setitem(raw,i,__t6[0]);__rt.setitem(raw,j,__t6[1]);}}
return __rt.tuple([__rt.call(__rt.b["bytes"],[raw],__rt.kw([])),seed]);return null;});
pack=__rt.fn("pack",{names:["raw", "seed", "salt"],kwonly:[],defaults:{"salt":GAME_SALT},vararg:null,kwarg:null},function(raw,seed,salt){let data,i,j;if(__rt.truth(__rt.or_(()=>__rt.unary("Not",raw),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>seed,()=>255]))))){throw __rt.call(__rt.b["ValueError"],["Invalid binary message"],__rt.kw([]));}
data=__rt.call(__rt.b["bytearray"],[raw],__rt.kw([]));
for(const __t7 of __rt.iter(__rt.call(swaps,[__rt.call(__rt.b["len"],[data],__rt.kw([])),seed,salt],__rt.kw([])))){{const __t8=Array.from(__rt.iter(__t7));i=__t8[0];j=__t8[1];}{const __t9=Array.from(__rt.iter(__rt.tuple([__rt.item(data,j),__rt.item(data,i)])));__rt.setitem(data,i,__t9[0]);__rt.setitem(data,j,__t9[1]);}}
__rt.call(__rt.attr(data,"insert"),[__rt.bin("Mod",salt,__rt.call(__rt.b["len"],[data],__rt.kw([]))),seed],__rt.kw([]));
return __rt.call(__rt.b["bytes"],[data],__rt.kw([]));return null;});
varint=__rt.fn("varint",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){let out;value=__rt.bin("BitAnd",value,__rt.bin("Sub",__rt.bin("LShift",1,64),1));
out=__rt.call(__rt.b["bytearray"],[],__rt.kw([]));
while(__rt.truth(__rt.compare(["Gt"],[()=>value,()=>127]))){__rt.call(__rt.attr(out,"append"),[__rt.bin("BitOr",__rt.bin("BitAnd",value,127),128)],__rt.kw([]));
value=__rt.bin("RShift",value,7);}
__rt.call(__rt.attr(out,"append"),[value],__rt.kw([]));
return __rt.call(__rt.b["bytes"],[out],__rt.kw([]));return null;});
read_varint=__rt.fn("read_varint",{names:["raw", "pos"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(raw,pos){let byte,shift,value;value=0;
for(const __t10 of __rt.iter(__rt.call(__rt.b["range"],[0,70,7],__rt.kw([])))){shift=__t10;if(__rt.truth(__rt.compare(["GtE"],[()=>pos,()=>__rt.call(__rt.b["len"],[raw],__rt.kw([]))]))){throw __rt.call(__rt.b["ValueError"],["Truncated varint"],__rt.kw([]));}
byte=__rt.item(raw,pos);
pos=__rt.bin("Add",pos,1);
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>shift,()=>63]),()=>__rt.compare(["Gt"],[()=>byte,()=>1])))){throw __rt.call(__rt.b["ValueError"],["Oversized varint"],__rt.kw([]));}
value=__rt.bin("BitOr",value,__rt.bin("LShift",__rt.bin("BitAnd",byte,127),shift));
if(__rt.truth(__rt.compare(["Lt"],[()=>byte,()=>128]))){return __rt.tuple([value,pos]);}}
throw __rt.call(__rt.b["ValueError"],["Oversized varint"],__rt.kw([]));return null;});
fields=__rt.fn("fields",{names:["raw"],kwonly:[],defaults:{},vararg:null,kwarg:null},function*(raw){let number,pos,size,tag,value,wire;
pos=0;
while(__rt.truth(__rt.compare(["Lt"],[()=>pos,()=>__rt.call(__rt.b["len"],[raw],__rt.kw([]))]))){{const __t11=Array.from(__rt.iter(__rt.call(read_varint,[raw,pos],__rt.kw([]))));tag=__t11[0];pos=__t11[1];}
{const __t12=Array.from(__rt.iter(__rt.tuple([__rt.bin("RShift",tag,3),__rt.bin("BitAnd",tag,7)])));number=__t12[0];wire=__t12[1];}
if(__rt.truth(__rt.unary("Not",number))){throw __rt.call(__rt.b["ValueError"],["Invalid field number"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>0]))){{const __t13=Array.from(__rt.iter(__rt.call(read_varint,[raw,pos],__rt.kw([]))));value=__t13[0];pos=__t13[1];}}else{if(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>2]))){{const __t14=Array.from(__rt.iter(__rt.call(read_varint,[raw,pos],__rt.kw([]))));size=__t14[0];pos=__t14[1];}}else{if(__rt.truth(__rt.compare(["In"],[()=>wire,()=>__rt.tuple([1,5])]))){size=(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>1]))?8:4);}else{throw __rt.call(__rt.b["ValueError"],["Unsupported wire type"],__rt.kw([]));}}
if(__rt.truth(__rt.compare(["Gt"],[()=>__rt.bin("Add",pos,size),()=>__rt.call(__rt.b["len"],[raw],__rt.kw([]))]))){throw __rt.call(__rt.b["ValueError"],["Truncated field"],__rt.kw([]));}
{const __t15=Array.from(__rt.iter(__rt.tuple([__rt.item(raw,__rt.slice(pos,__rt.bin("Add",pos,size),null)),__rt.bin("Add",pos,size)])));value=__t15[0];pos=__t15[1];}}
(yield __rt.tuple([number,wire,value]));}return null;});
field=__rt.fn("field",{names:["number", "wire", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(number,wire,value){let tag;tag=__rt.call(varint,[__rt.bin("BitOr",__rt.bin("LShift",number,3),wire)],__rt.kw([]));
if(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>0]))){return __rt.bin("Add",tag,__rt.call(varint,[value],__rt.kw([])));}
return __rt.bin("Add",__rt.bin("Add",tag,(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>2]))?__rt.call(varint,[__rt.call(__rt.b["len"],[value],__rt.kw([]))],__rt.kw([])):Buffer.from([]))),value);return null;});
patch=__rt.fn("patch",{names:["raw", "replacements"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(raw,replacements){let out;
out=__rt.call(__rt.attr(Buffer.from([]),"join"),[(function*(){let n,v,w;for(const __t16 of __rt.iter(__rt.call(fields,[raw],__rt.kw([])))){{const __t17=Array.from(__rt.iter(__t16));n=__t17[0];w=__t17[1];v=__t17[2];}if(__rt.truth(__rt.compare(["NotIn"],[()=>n,()=>replacements]))){yield __rt.call(field,[n,w,v],__rt.kw([]));}}})()],__rt.kw([]));
return __rt.bin("Add",out,__rt.call(__rt.attr(Buffer.from([]),"join"),[__rt.call(__rt.attr(replacements,"values"),[],__rt.kw([]))],__rt.kw([])));return null;});
text_field=__rt.fn("text_field",{names:["number", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(number,value){return __rt.call(field,[number,2,__rt.call(__rt.attr(value,"encode"),[],__rt.kw([]))],__rt.kw([]));return null;});
double_field=__rt.fn("double_field",{names:["number", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(number,value){return __rt.call(field,[number,1,__rt.call(__rt.attr(struct,"pack"),["<d",__rt.call(__rt.b["float"],[value],__rt.kw([]))],__rt.kw([]))],__rt.kw([]));return null;});
decode_request=__rt.fn("decode_request",{names:["raw"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(raw){let expected,name,number,result,types,value,wire;types=__rt.dict([[1,__rt.tuple(["atk",2])],[2,__rt.tuple(["btt",0])],[3,__rt.tuple(["pf",0])],[5,__rt.tuple(["id",2])],[12,__rt.tuple(["wk",2])],[21,__rt.tuple(["cs",1])],[22,__rt.tuple(["ml",0])],[24,__rt.tuple(["fb",0])],[31,__rt.tuple(["ab",0])]]);
result=__rt.dict([]);
for(const __t18 of __rt.iter(__rt.call(fields,[raw],__rt.kw([])))){{const __t19=Array.from(__rt.iter(__t18));number=__t19[0];wire=__t19[1];value=__t19[2];}if(__rt.truth(__rt.compare(["NotIn"],[()=>number,()=>types]))){throw __rt.call(__rt.b["ValueError"],["Unsupported Spin parameter"],__rt.kw([]));}
{const __t20=Array.from(__rt.iter(__rt.item(types,number)));name=__t20[0];expected=__t20[1];}
if(__rt.truth(__rt.or_(()=>__rt.compare(["NotEq"],[()=>wire,()=>expected]),()=>__rt.compare(["In"],[()=>name,()=>result])))){throw __rt.call(__rt.b["ValueError"],["Invalid Spin parameter"],__rt.kw([]));}
__rt.setitem(result,name,(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>2]))?__rt.call(__rt.attr(value,"decode"),["utf-8"],__rt.kw([])):(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>1]))?__rt.item(__rt.call(__rt.attr(struct,"unpack"),["<d",value],__rt.kw([])),0):value)));}
return result;return null;});
