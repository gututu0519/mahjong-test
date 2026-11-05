// Migrated from server/core/encoding.py. Runtime is Node.js only.
import * as __rt from "../../../compat/runtime.js";
const __file__=__rt.sourcePath("server/core/encoding.py");
export let encode:any,json:any;
json=__rt.modules["json"];
encode=__rt.fn("encode",{names:["value"],kwonly:[],defaults:{},vararg:null,kwarg:null},function(value){return __rt.call(__rt.attr(json,"dumps"),[value],__rt.kw([["ensure_ascii",false],["sort_keys",true],["separators",__rt.tuple([",",":"])],["allow_nan",false]]));return null;});
