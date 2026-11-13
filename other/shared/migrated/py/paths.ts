// Migrated from py/paths.py. Runtime is Node.js only.
import * as __rt from "../../compat/runtime.js";
const __file__=__rt.sourcePath("py/paths.py");
export let BUFFALO_CLIENT:any,CLIENTS:any,MAHJONG_CLIENT:any,MAHJONG_DIAGNOSTICS:any,Path:any,ROOT:any;

Path=__rt.attr(__rt.modules["pathlib"],"Path");
ROOT=__rt.item(__rt.attr(__rt.call(__rt.attr(__rt.call(Path,[__file__],__rt.kw([])),"resolve"),[],__rt.kw([])),"parents"),1);
CLIENTS=__rt.bin("Div",ROOT,"clients");
MAHJONG_CLIENT=__rt.bin("Div",CLIENTS,"mahjong-ways2");
BUFFALO_CLIENT=__rt.bin("Div",CLIENTS,"buffalo-win");
MAHJONG_DIAGNOSTICS=__rt.bin("Div",ROOT,"diagnostics/mahjong-ways2");
