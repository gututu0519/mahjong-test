// Migrated from server/adapters/pg/wire.py. Runtime is Node.js only.
import * as __rt from "../../../../compat/runtime.js";
import * as __m0 from "./protocol.js";
const __file__=__rt.sourcePath("server/adapters/pg/wire.py");
export let decode:any,double_field:any,encode:any,field:any,fields:any,read_varint:any,scalar:any,struct:any,text_field:any;

struct=__rt.modules["struct"];
fields=__rt.attr(__m0,"fields");
field=__rt.attr(__m0,"field");
read_varint=__rt.attr(__m0,"read_varint");
double_field=__rt.attr(__m0,"double_field");
text_field=__rt.attr(__m0,"text_field");
scalar=__rt.fn("scalar",{names:["number", "kind", "value", "types"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(number,kind,value,types){if(__rt.truth(__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["int32","int64","uint32","uint64","bool"])]))){return __rt.call(field,[number,0,__rt.call(__rt.b["int"],[value],__rt.kw([]))],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"double"]))){return __rt.call(double_field,[number,value],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"string"]))){return __rt.call(text_field,[number,value],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"bytes"]))){return __rt.call(field,[number,2,value],__rt.kw([]));}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>kind,()=>"Int32List"]),()=>__rt.call(__rt.b["isinstance"],[value,__rt.b["list"]],__rt.kw([]))))){value=__rt.dict([["__value",value]]);}
return __rt.call(field,[number,2,__rt.call(encode,[value,types,kind],__rt.kw([]))],__rt.kw([]));return null;});
encode=__rt.fn("encode",{names:["data", "types", "name"],kwonly:[],defaults:{"name":"__root__"},vararg:null,kwarg:null},function(data,types,name){let entry,k,key,kind,n,out,spec,value;out=[];
for(const __t1 of __rt.iter(__rt.call(__rt.attr(__rt.item(__rt.item(types,name),"fields"),"items"),[],__rt.kw([])))){{const __t2=Array.from(__rt.iter(__t1));key=__t2[0];spec=__t2[1];}value=__rt.call(__rt.attr(data,"get"),[key],__rt.kw([]));
if(__rt.truth(__rt.compare(["Is"],[()=>value,()=>null]))){continue;}
{const __t3=Array.from(__rt.iter(__rt.tuple([__rt.item(spec,"id"),__rt.item(spec,"type")])));n=__t3[0];kind=__t3[1];}
if(__rt.truth(__rt.compare(["In"],[()=>"keyType",()=>spec]))){for(const __t4 of __rt.iter(__rt.call(__rt.b["sorted"],[value],__rt.kw([["key",__rt.b["int"]]])))){k=__t4;entry=__rt.bin("Add",__rt.call(scalar,[1,__rt.item(spec,"keyType"),__rt.call(__rt.b["int"],[k],__rt.kw([])),types],__rt.kw([])),__rt.call(scalar,[2,kind,__rt.item(value,k),types],__rt.kw([])));
__rt.call(__rt.attr(out,"append"),[__rt.call(field,[n,2,entry],__rt.kw([]))],__rt.kw([]));}}else{if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(spec,"get"),["rule"],__rt.kw([])),()=>"repeated"]))){__rt.call(__rt.attr(out,"extend"),[(function*(){let item;for(const __t5 of __rt.iter(value)){item=__t5;yield __rt.call(scalar,[n,kind,item,types],__rt.kw([]));}})()],__rt.kw([]));}else{__rt.call(__rt.attr(out,"append"),[__rt.call(scalar,[n,kind,value,types],__rt.kw([]))],__rt.kw([]));}}}
return __rt.call(__rt.attr(Buffer.from([]),"join"),[out],__rt.kw([]));return null;});
decode=__rt.fn("decode",{names:["raw", "types", "name"],kwonly:[],defaults:{"name":"__root__"},vararg:null,kwarg:null},function(raw,types,name){let data,entry,items,k,key,kind,n,pos,result,spec,specs,v,value,wire;specs=(()=>{let k,s;const __out:any[]=[];for(const __t6 of __rt.iter(__rt.call(__rt.attr(__rt.item(__rt.item(types,name),"fields"),"items"),[],__rt.kw([])))){{const __t7=Array.from(__rt.iter(__t6));k=__t7[0];s=__t7[1];}__out.push([__rt.item(s,"id"),__rt.tuple([k,s])]);}return __rt.dict(__out);})();
result=__rt.dict([]);
value=__rt.fn("value",{names:["kind", "wire", "data"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(kind,wire,data){let child;if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"double"]))){return __rt.item(__rt.call(__rt.attr(struct,"unpack"),["<d",data],__rt.kw([])),0);}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"string"]))){return __rt.call(__rt.attr(data,"decode"),["utf-8"],__rt.kw([]));}
if(__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"bytes"]))){return data;}
if(__rt.truth(__rt.compare(["In"],[()=>kind,()=>types]))){child=__rt.call(decode,[data,types,kind],__rt.kw([]));
return (__rt.truth(__rt.compare(["Eq"],[()=>kind,()=>"Int32List"]))?__rt.call(__rt.attr(child,"get"),["__value",[]],__rt.kw([])):child);}
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>kind,()=>"int32"]),()=>__rt.compare(["GtE"],[()=>data,()=>__rt.bin("LShift",1,31)])))){return __rt.bin("Sub",__rt.bin("BitAnd",data,4294967295),__rt.bin("LShift",1,32));}
return data;return null;});
for(const __t8 of __rt.iter(__rt.call(fields,[raw],__rt.kw([])))){{const __t9=Array.from(__rt.iter(__t8));n=__t9[0];wire=__t9[1];data=__t9[2];}if(__rt.truth(__rt.compare(["NotIn"],[()=>n,()=>specs]))){continue;}
{const __t10=Array.from(__rt.iter(__rt.item(specs,n)));key=__t10[0];spec=__t10[1];}
kind=__rt.item(spec,"type");
if(__rt.truth(__rt.compare(["In"],[()=>"keyType",()=>spec]))){entry=(()=>{let n,v,w;const __out:any[]=[];for(const __t11 of __rt.iter(__rt.call(fields,[data],__rt.kw([])))){{const __t12=Array.from(__rt.iter(__t11));n=__t12[0];w=__t12[1];v=__t12[2];}__out.push([n,__rt.tuple([w,v])]);}return __rt.dict(__out);})();
k=__rt.call(value,[__rt.item(spec,"keyType"),...__rt.iter(__rt.call(__rt.attr(entry,"get"),[1,__rt.tuple([0,0])],__rt.kw([])))],__rt.kw([]));
v=__rt.call(value,[kind,...__rt.iter(__rt.call(__rt.attr(entry,"get"),[2,__rt.tuple([0,0])],__rt.kw([])))],__rt.kw([]));
__rt.setitem(__rt.call(__rt.attr(result,"setdefault"),[key,__rt.dict([])],__rt.kw([])),__rt.call(__rt.b["str"],[k],__rt.kw([])),v);}else{if(__rt.truth(__rt.compare(["Eq"],[()=>__rt.call(__rt.attr(spec,"get"),["rule"],__rt.kw([])),()=>"repeated"]))){items=__rt.call(__rt.attr(result,"setdefault"),[key,[]],__rt.kw([]));
if(__rt.truth(__rt.and_(()=>__rt.compare(["Eq"],[()=>wire,()=>2]),()=>__rt.compare(["In"],[()=>kind,()=>__rt.tuple(["int32","uint32","int64","uint64","bool"])])))){pos=0;
while(__rt.truth(__rt.compare(["Lt"],[()=>pos,()=>__rt.call(__rt.b["len"],[data],__rt.kw([]))]))){{const __t13=Array.from(__rt.iter(__rt.call(read_varint,[data,pos],__rt.kw([]))));v=__t13[0];pos=__t13[1];}
__rt.call(__rt.attr(items,"append"),[__rt.call(value,[kind,0,v],__rt.kw([]))],__rt.kw([]));}}else{__rt.call(__rt.attr(items,"append"),[__rt.call(value,[kind,wire,data],__rt.kw([]))],__rt.kw([]));}}else{__rt.setitem(result,key,__rt.call(value,[kind,wire,data],__rt.kw([])));}}}
return result;return null;});
