// Migrated from server/adapters/jili/wire.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
const __file__=__rt.sourcePath("server/adapters/jili/wire.py");
export let decode:any,encode:any,fields:any,read_varint:any,scalar:any,struct:any,varint:any;

struct=__rt.modules["struct"];
varint=__rt.fn("varint",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){let result;value=__rt.bin("BitAnd",__rt.call(__rt.b["int"],[value],__rt.kw([])),__rt.bin("Sub",__rt.bin("LShift",1,64),1));
result=__rt.call(__rt.b["bytearray"],[],__rt.kw([]));
while(__rt.truth(__rt.compare(["Gt"],[()=>value,()=>127]))){__rt.call(__rt.attr(result,"append"),[__rt.bin("BitOr",__rt.bin("BitAnd",value,127),128)],__rt.kw([]));
value=__rt.bin("RShift",value,7);}
__rt.call(__rt.attr(result,"append"),[value],__rt.kw([]));
return __rt.call(__rt.b["bytes"],[result],__rt.kw([]));return null;});
read_varint=__rt.fn("read_varint",{names:["data", "offset"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(data,offset){let byte,result,shift;result=0;
for(const __t1 of __rt.iter(__rt.call(__rt.b["range"],[0,70,7],__rt.kw([])))){shift=__t1;if(__rt.truth(__rt.compare(["GtE"],[()=>offset,()=>__rt.call(__rt.b["len"],[data],__rt.kw([]))]))){throw __rt.call(__rt.b["ValueError"],["Truncated varint"],__rt.kw([]));}
byte=__rt.item(data,offset);
offset=__rt.bin("Add",offset,1);
result=__rt.bin("BitOr",result,__rt.bin("LShift",__rt.bin("BitAnd",byte,127),shift));
if(__rt.truth(__rt.compare(["Lt"],[()=>byte,()=>128]))){return __rt.tuple([result,offset]);}}
throw __rt.call(__rt.b["ValueError"],["Oversized varint"],__rt.kw([]));return null;});
fields=__rt.fn("fields",{names:["data"],kwonly:[],defaults:{},vararg:null,kwarg:null},function*(data){let end,length,number,offset,tag,value,wire;offset=0;
while(__rt.truth(__rt.compare(["Lt"],[()=>offset,()=>__rt.call(__rt.b["len"],[data],__rt.kw([]))]))){{const __t2=Array.from(__rt.iter(__rt.call(read_varint,[data,offset],__rt.kw([]))));tag=__t2[0];offset=__t2[1];}
{const __t3=Array.from(__rt.iter(__rt.tuple([__rt.bin("RShift",tag,3),__rt.bin("BitAnd",tag,7)])));number=__t3[0];wire=__t3[1];}
if(__rt.truth(__rt.unary("Not",number))){throw __rt.call(__rt.b["ValueError"],["Invalid protobuf field"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>0]))){{const __t4=Array.from(__rt.iter(__rt.call(read_varint,[data,offset],__rt.kw([]))));value=__t4[0];offset=__t4[1];}}else{if(__rt.truth(__rt.compare(["In"],[()=>wire,()=>__rt.tuple([1,2,5])]))){if(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>2]))){{const __t5=Array.from(__rt.iter(__rt.call(read_varint,[data,offset],__rt.kw([]))));length=__t5[0];offset=__t5[1];}}else{length=(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>1]))?8:4);}
end=__rt.bin("Add",offset,length);
if(__rt.truth(__rt.compare(["Gt"],[()=>end,()=>__rt.call(__rt.b["len"],[data],__rt.kw([]))]))){throw __rt.call(__rt.b["ValueError"],["Truncated protobuf value"],__rt.kw([]));}
{const __t6=Array.from(__rt.iter(__rt.tuple([__rt.item(data,__rt.slice(offset,end,null)),end])));value=__t6[0];offset=__t6[1];}}else{throw __rt.call(__rt.b["ValueError"],["Unsupported protobuf wire type"],__rt.kw([]));}}
(yield __rt.tuple([number,wire,value]));}return null;});
encode=__rt.fn("encode",{names:["schema", "value", "schemas"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(schema,value,schemas){let item,key,kind,number,payload,repeated,result,values,wire;result=__rt.call(__rt.b["bytearray"],[],__rt.kw([]));
for(const __t7 of __rt.iter(__rt.call(__rt.attr(schema,"items"),[],__rt.kw([])))){{const __t8=Array.from(__rt.iter(__t7));key=__t8[0];{const __t9=Array.from(__rt.iter(__t8[1]));number=__t9[0];kind=__t9[1];repeated=__t9[2];}}if(__rt.truth(__rt.or_(()=>__rt.compare(["NotIn"],[()=>key,()=>value]),()=>__rt.compare(["Is"],[()=>__rt.item(value,key),()=>null])))){continue;}
values=(__rt.truth(repeated)?__rt.item(value,key):[__rt.item(value,key)]);
for(const __t10 of __rt.iter(values)){item=__t10;if(__rt.truth(__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["int32","uint32","int64","bool"])]))){{const __t11=Array.from(__rt.iter(__rt.tuple([0,__rt.call(varint,[item],__rt.kw([]))])));wire=__t11[0];payload=__t11[1];}}else{if(__rt.truth(__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["double","float"])]))){wire=(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"double"]))?1:5);
payload=__rt.call(__rt.attr(struct,"pack"),[(__rt.truth(__rt.compare(["Eq"],[()=>wire,()=>1]))?"<d":"<f"),item],__rt.kw([]));}else{wire=2;
payload=(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"string"]))?__rt.call(__rt.attr(item,"encode"),["utf-8"],__rt.kw([])):(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"bytes"]))?__rt.call(__rt.b["bytes"],[item],__rt.kw([])):__rt.call(encode,[__rt.item(schemas,kind),item,schemas],__rt.kw([]))));
payload=__rt.bin("Add",__rt.call(varint,[__rt.call(__rt.b["len"],[payload],__rt.kw([]))],__rt.kw([])),payload);}}
result=__rt.bin("Add",result,__rt.bin("Add",__rt.call(varint,[__rt.bin("Add",__rt.bin("Mult",number,8),wire)],__rt.kw([])),payload));}}
return __rt.call(__rt.b["bytes"],[result],__rt.kw([]));return null;});
scalar=__rt.fn("scalar",{names:["kind", "value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(kind,value){let bits;if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"bool"]))){return __rt.call(__rt.b["bool"],[value],__rt.kw([]));}
bits=__rt.call(__rt.attr(__rt.dict([["int32",32],["int64",64]]),"get"),[kind],__rt.kw([]));
if(__rt.truth(bits)){value=__rt.bin("BitAnd",value,__rt.bin("Sub",__rt.bin("LShift",1,bits),1));
return (__rt.truth(__rt.compare(["GtE"],[()=>value,()=>__rt.bin("LShift",1,__rt.bin("Sub",bits,1))]))?__rt.bin("Sub",value,__rt.bin("LShift",1,bits)):value);}
return value;return null;});
decode=__rt.fn("decode",{names:["schema", "data", "schemas"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(schema,data,schemas){let item,key,kind,number,offset,packed,repeated,result,reverse,size,value,wire;reverse=(()=>{let k,v;const __out:any[]=[];for(const __t12 of __rt.iter(__rt.call(__rt.attr(schema,"items"),[],__rt.kw([])))){{const __t13=Array.from(__rt.iter(__t12));k=__t13[0];v=__t13[1];}__out.push([__rt.item(v,0),__rt.tuple([k,__rt.item(v,1),__rt.item(v,2)])]);}return __rt.dict(__out);})();
result=(()=>{let _,k,repeated;const __out:any[]=[];for(const __t14 of __rt.iter(__rt.call(__rt.attr(schema,"items"),[],__rt.kw([])))){{const __t15=Array.from(__rt.iter(__t14));k=__t15[0];{const __t16=Array.from(__rt.iter(__t15[1]));_=__t16[0];_=__t16[1];repeated=__t16[2];}}if(__rt.truth(repeated)){__out.push([k,[]]);}}return __rt.dict(__out);})();
for(const __t17 of __rt.iter(__rt.call(fields,[__rt.call(__rt.b["bytes"],[data],__rt.kw([]))],__rt.kw([])))){{const __t18=Array.from(__rt.iter(__t17));number=__t18[0];wire=__t18[1];value=__t18[2];}if(__rt.truth(__rt.compare(["NotIn"],[()=>number,()=>reverse]))){continue;}
{const __t19=Array.from(__rt.iter(__rt.item(reverse,number)));key=__t19[0];kind=__t19[1];repeated=__t19[2];}
if(__rt.truth(__rt.and_(()=>repeated,()=>__rt.compare(["Eq"],[()=>wire,()=>2]),()=>__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["int32","uint32","int64","bool","double","float"])])))){{const __t20=Array.from(__rt.iter(__rt.tuple([[],0])));packed=__t20[0];offset=__t20[1];}
while(__rt.truth(__rt.compare(["Lt"],[()=>offset,()=>__rt.call(__rt.b["len"],[value],__rt.kw([]))]))){if(__rt.truth(__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["double","float"])]))){size=(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"double"]))?8:4);
__rt.call(__rt.attr(packed,"append"),[__rt.item(__rt.call(__rt.attr(struct,"unpack"),[(__rt.truth(__rt.compare(["Eq"],[()=>size,()=>8]))?"<d":"<f"),__rt.item(value,__rt.slice(offset,__rt.bin("Add",offset,size),null))],__rt.kw([])),0)],__rt.kw([]));
offset=__rt.bin("Add",offset,size);}else{{const __t21=Array.from(__rt.iter(__rt.call(read_varint,[value,offset],__rt.kw([]))));item=__t21[0];offset=__t21[1];}
__rt.call(__rt.attr(packed,"append"),[__rt.call(scalar,[kind,item],__rt.kw([]))],__rt.kw([]));}}
__rt.call(__rt.attr(__rt.item(result,key),"extend"),[packed],__rt.kw([]));
continue;}
if(__rt.truth(__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["int32","uint32","int64","bool"])]))){if(__rt.truth(__rt.compare(["NotEq"],[()=>wire,()=>0]))){throw __rt.call(__rt.b["ValueError"],["Incorrect scalar wire type"],__rt.kw([]));}
item=__rt.call(scalar,[kind,value],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["double","float"])]))){if(__rt.truth(__rt.compare(["NotEq"],[()=>wire,()=>(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"double"]))?1:5)]))){throw __rt.call(__rt.b["ValueError"],["Incorrect floating point wire type"],__rt.kw([]));}
item=__rt.item(__rt.call(__rt.attr(struct,"unpack"),[(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"double"]))?"<d":"<f"),value],__rt.kw([])),0);}else{if(__rt.truth(__rt.compare(["NotEq"],[()=>wire,()=>2]))){throw __rt.call(__rt.b["ValueError"],["Incorrect message wire type"],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"string"]))){item=__rt.call(__rt.attr(value,"decode"),["utf-8"],__rt.kw([]));}else{if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"bytes"]))){item=__rt.call(__rt.b["list"],[value],__rt.kw([]));}else{item=__rt.call(decode,[__rt.item(schemas,kind),value,schemas],__rt.kw([]));}}}}}
if(__rt.truth(repeated)){__rt.call(__rt.attr(__rt.item(result,key),"append"),[item],__rt.kw([]));}else{__rt.setitem(result,key,item);}}
return result;return null;});
