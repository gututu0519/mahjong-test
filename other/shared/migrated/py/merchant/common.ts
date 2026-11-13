// Migrated from py/merchant/common.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
const __file__=__rt.sourcePath("py/merchant/common.py");
export let Database:any,Path:any,ServiceError:any,amount:any,contextmanager:any,encode:any,hashlib:any,hmac:any,identifier:any,json:any,limit:any,re:any,read_object:any,secrets:any,signature:any,signed_headers:any,sqlite3:any,time:any;
hashlib=__rt.modules["hashlib"];
hmac=__rt.modules["hmac"];
json=__rt.modules["json"];
re=__rt.modules["re"];
secrets=__rt.modules["secrets"];
sqlite3=__rt.modules["sqlite3"];
time=__rt.modules["time"];
contextmanager=__rt.attr(__rt.modules["contextlib"],"contextmanager");
Path=__rt.attr(__rt.modules["pathlib"],"Path");
ServiceError=__rt.attr(__rt.modules["py.core.contracts"],"ServiceError");
encode=__rt.fn("encode",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){return __rt.call(__rt.attr(json,"dumps"),[value],__rt.kw([["ensure_ascii",false],["sort_keys",true],["separators",__rt.tuple([",",":"])],["allow_nan",false]]));return null;});
identifier=__rt.fn("identifier",{names:["value", "name"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value,name){if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.b["isinstance"],[value,__rt.b["str"]],__rt.kw([]))),()=>__rt.unary("Not",__rt.call(__rt.attr(re,"fullmatch"),["[A-Za-z0-9_.:-]{1,128}",value],__rt.kw([])))))){throw __rt.call(ServiceError,["INVALID_ARGUMENT",__rt.bin("Add",name," must use 1..128 ASCII letters, digits, or _ . : -")],__rt.kw([]));}
return value;return null;});
amount=__rt.fn("amount",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[value],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>0,()=>value,()=>9000000000000000]))))){throw __rt.call(ServiceError,["INVALID_ARGUMENT","amount_minor must be a nonnegative integer within the balance limit."],__rt.kw([]));}
return value;return null;});
limit=__rt.fn("limit",{names:["value"],kwonly:[],defaults:{"value":20},vararg:null,kwarg:null},function(value){if(__rt.truth(__rt.or_(()=>__rt.compare(["IsNot"],[()=>__rt.call(__rt.b["type"],[value],__rt.kw([])),()=>__rt.b["int"]]),()=>__rt.unary("Not",__rt.compare(["LtE", "LtE"],[()=>1,()=>value,()=>100]))))){throw __rt.call(ServiceError,["INVALID_ARGUMENT","limit must be an integer from 1 to 100."],__rt.kw([]));}
return value;return null;});
signature=__rt.fn("signature",{names:["secret", "method", "path", "timestamp", "nonce", "body"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(secret,method,path,timestamp,nonce,body){let message;message=__rt.call(__rt.attr("\n","join"),[__rt.tuple([__rt.call(__rt.attr(method,"upper"),[],__rt.kw([])),path,__rt.call(__rt.b["str"],[timestamp],__rt.kw([])),nonce,__rt.call(__rt.attr(__rt.call(__rt.attr(hashlib,"sha256"),[body],__rt.kw([])),"hexdigest"),[],__rt.kw([]))])],__rt.kw([]));
return __rt.call(__rt.attr(__rt.call(__rt.attr(hmac,"new"),[__rt.call(__rt.attr(secret,"encode"),[],__rt.kw([])),__rt.call(__rt.attr(message,"encode"),[],__rt.kw([])),__rt.attr(hashlib,"sha256")],__rt.kw([])),"hexdigest"),[],__rt.kw([]));return null;});
signed_headers=__rt.fn("signed_headers",{names:["merchant_id", "secret", "path", "body", "timestamp", "nonce"],kwonly:[],defaults:{"timestamp":null,"nonce":null},vararg:null,kwarg:null},function(merchant_id,secret,path,body,timestamp,nonce){timestamp=__rt.call(__rt.b["str"],[(__rt.truth(__rt.compare(["Is"],[()=>timestamp,()=>null]))?__rt.call(__rt.b["int"],[__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))],__rt.kw([])):timestamp)],__rt.kw([]));
nonce=(__rt.truth(__rt.compare(["Is"],[()=>nonce,()=>null]))?__rt.call(__rt.attr(secrets,"token_hex"),[16],__rt.kw([])):nonce);
return __rt.dict([["Content-Type","application/json"],["X-GTT-Merchant",merchant_id],["X-GTT-Timestamp",timestamp],["X-GTT-Nonce",nonce],["X-GTT-Signature",__rt.call(signature,[secret,"POST",path,timestamp,nonce,body],__rt.kw([]))]]);return null;});
Database=__rt.cls("Database",[],{"__init__":__rt.fn("__init__",{names:["self", "path"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(self,path){let db;__rt.setattr(self,"path",__rt.call(__rt.b["str"],[__rt.call(__rt.attr(__rt.call(Path,[path],__rt.kw([])),"resolve"),[],__rt.kw([]))],__rt.kw([])));
__rt.call(__rt.attr(__rt.attr(__rt.call(Path,[__rt.attr(self,"path")],__rt.kw([])),"parent"),"mkdir"),[],__rt.kw([["parents",true],["exist_ok",true]]));
{const __t1=__rt.context(__rt.call(__rt.attr(self,"connection"),[],__rt.kw([])));let __t3=false;db=__t1.value;try{__rt.call(__rt.attr(db,"execute"),["PRAGMA journal_mode=WAL"],__rt.kw([]));
__rt.call(__rt.attr(db,"execute"),["CREATE TABLE IF NOT EXISTS request_nonces (\n                merchant_id TEXT NOT NULL, nonce TEXT NOT NULL, expires_at INTEGER NOT NULL,\n                PRIMARY KEY(merchant_id,nonce))"],__rt.kw([]));}catch(__t2){__t3=true;if(!__t1.exit(__t2))throw __t2;}finally{if(!__t3)__t1.exit(null);}}return null;}),"connection":__rt.call(contextmanager,[__rt.fn("connection",{names:["self", "write"],kwonly:[],defaults:{"write":false},vararg:null,kwarg:null},function*(self,write){let db;db=__rt.call(__rt.attr(sqlite3,"connect"),[__rt.attr(self,"path")],__rt.kw([["isolation_level",null],["timeout",15]]));
__rt.setattr(db,"row_factory",__rt.attr(sqlite3,"Row"));
__rt.call(__rt.attr(db,"execute"),["PRAGMA foreign_keys=ON"],__rt.kw([]));
__rt.call(__rt.attr(db,"execute"),["PRAGMA synchronous=FULL"],__rt.kw([]));
try{if(__rt.truth(write)){__rt.call(__rt.attr(db,"execute"),["BEGIN IMMEDIATE"],__rt.kw([]));}
(yield db);
if(__rt.truth(write)){__rt.call(__rt.attr(db,"commit"),[],__rt.kw([]));}}catch(__t4){if(__rt.matches(__t4,__rt.b["BaseException"])){if(__rt.truth(write)){__rt.call(__rt.attr(db,"rollback"),[],__rt.kw([]));}
throw __t4;}else{throw __t4;}}finally{__rt.call(__rt.attr(db,"close"),[],__rt.kw([]));}return null;})]),"authenticate":__rt.fn("authenticate",{names:["self", "headers", "path", "body", "merchants", "allow_disabled"],kwonly:[],defaults:{"allow_disabled":false},vararg:null,kwarg:null},function(self,headers,path,body,merchants,allow_disabled){let db,matches,merchant,merchant_id,nonce,now,secret,supplied,timestamp;merchant_id=__rt.call(__rt.attr(headers,"get"),["X-GTT-Merchant",""],__rt.kw([]));
merchant=__rt.call(__rt.attr(merchants,"get"),[merchant_id],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",merchant),()=>__rt.and_(()=>__rt.unary("Not",__rt.call(__rt.attr(merchant,"get"),["enabled"],__rt.kw([]))),()=>__rt.unary("Not",allow_disabled))))){throw __rt.call(ServiceError,["AUTH_INVALID","Unknown or disabled merchant.",401],__rt.kw([]));}
{const __t5=Array.from(__rt.iter(__rt.tuple([__rt.call(__rt.attr(headers,"get"),["X-GTT-Timestamp",""],__rt.kw([])),__rt.call(__rt.attr(headers,"get"),["X-GTT-Nonce",""],__rt.kw([]))])));timestamp=__t5[0];nonce=__t5[1];}
now=__rt.call(__rt.b["int"],[__rt.call(__rt.attr(time,"time"),[],__rt.kw([]))],__rt.kw([]));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.attr(re,"fullmatch"),["[0-9]{10}",timestamp],__rt.kw([]))),()=>__rt.compare(["Gt"],[()=>__rt.call(__rt.b["abs"],[__rt.bin("Sub",now,__rt.call(__rt.b["int"],[timestamp],__rt.kw([])))],__rt.kw([])),()=>300]),()=>__rt.unary("Not",__rt.call(__rt.attr(re,"fullmatch"),["[A-Za-z0-9_-]{16,64}",nonce],__rt.kw([])))))){throw __rt.call(ServiceError,["AUTH_INVALID","Invalid timestamp or nonce.",401],__rt.kw([]));}
supplied=__rt.call(__rt.attr(headers,"get"),["X-GTT-Signature",""],__rt.kw([]));
secret=__rt.call(__rt.attr(merchant,"get"),["merchant_secret"],__rt.kw([]));
matches=__rt.and_(()=>__rt.call(__rt.b["isinstance"],[secret,__rt.b["str"]],__rt.kw([])),()=>__rt.call(__rt.b["bool"],[secret],__rt.kw([])),()=>__rt.call(__rt.attr(hmac,"compare_digest"),[__rt.call(signature,[secret,"POST",path,timestamp,nonce,body],__rt.kw([])),supplied],__rt.kw([])));
if(__rt.truth(__rt.or_(()=>__rt.unary("Not",__rt.call(__rt.attr(re,"fullmatch"),["[0-9a-f]{64}",supplied],__rt.kw([]))),()=>__rt.unary("Not",matches)))){throw __rt.call(ServiceError,["AUTH_INVALID","Invalid signature.",401],__rt.kw([]));}
{const __t6=__rt.context(__rt.call(__rt.attr(self,"connection"),[true],__rt.kw([])));let __t8=false;db=__t6.value;try{__rt.call(__rt.attr(db,"execute"),["DELETE FROM request_nonces WHERE expires_at<?",__rt.tuple([now])],__rt.kw([]));
try{__rt.call(__rt.attr(db,"execute"),["INSERT INTO request_nonces VALUES (?,?,?)",__rt.tuple([merchant_id,nonce,__rt.bin("Add",now,601)])],__rt.kw([]));}catch(__t9){if(__rt.matches(__t9,__rt.attr(sqlite3,"IntegrityError"))){throw __rt.call(ServiceError,["AUTH_REPLAY","Nonce has already been used.",409],__rt.kw([]));}else{throw __t9;}}}catch(__t7){__t8=true;if(!__t6.exit(__t7))throw __t7;}finally{if(!__t8)__t6.exit(null);}}
return __rt.tuple([merchant_id,merchant]);return null;})});
read_object=__rt.fn("read_object",{names:["body"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(body){let pairs,result;pairs=__rt.fn("pairs",{names:["items"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(items){let key,result,value;result=__rt.dict([]);
for(const __t10 of __rt.iter(items)){{const __t11=Array.from(__rt.iter(__t10));key=__t11[0];value=__t11[1];}if(__rt.truth(__rt.compare(["In"],[()=>key,()=>result]))){throw __rt.call(__rt.b["ValueError"],["Duplicate JSON key"],__rt.kw([]));}
__rt.setitem(result,key,value);}
return result;return null;});
result=__rt.call(__rt.attr(json,"loads"),[body],__rt.kw([["object_pairs_hook",pairs],["parse_constant",__rt.fn("<lambda>",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){return __rt.call(__rt.attr((function*(){let _;for(const __t12 of __rt.iter(__rt.tuple([]))){_=__t12;yield _;}})(),"throw"),[__rt.call(__rt.b["ValueError"],["Non-finite JSON number"],__rt.kw([]))],__rt.kw([]));return null;})]]));
if(__rt.truth(__rt.unary("Not",__rt.call(__rt.b["isinstance"],[result,__rt.b["dict"]],__rt.kw([]))))){throw __rt.call(__rt.b["ValueError"],["Expected a JSON object"],__rt.kw([]));}
return result;return null;});
