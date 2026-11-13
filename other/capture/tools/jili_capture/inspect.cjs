const fs=require('fs'),vm=require('vm');
const root='response-capture/captures/d15806bcacc3496aade5a3f080feb2c6/bodies/';
for(const name of ['000738.bin','000740.bin','000746.bin','000752.bin','000759.bin']) {
 const mods=[];const ctx={System:{register(...a){mods.push({name:a[0],deps:a[1],factory:a.at(-1).toString()});}},console:{log(){},warn(){},error(){}},setTimeout(){},clearTimeout(){},setInterval(){},clearInterval(){},TextDecoder,TextEncoder,Uint8Array,ArrayBuffer,atob,btoa};ctx.navigator={userAgent:'Mozilla/5.0'};
 try{vm.createContext(ctx);vm.runInContext('var window=globalThis,self=globalThis;',ctx);vm.runInContext(fs.readFileSync(root+name,'utf8'),ctx,{timeout:15000});}catch(e){console.log(name,e.stack.slice(-1800));}
 if(name==='000759.bin') {let src=fs.readFileSync(root+name,'utf8');src=src.replace(/_0x[0-9a-f]+\((0x[0-9a-f]+)\)/g,(s,n)=>{try{const v=ctx._0x48f8(Number(n));return typeof v==='string'?JSON.stringify(v):s;}catch{return s;}});fs.writeFileSync('clients/super-ace/diagnostics/game.decoded.js',src);}
 fs.writeFileSync('clients/super-ace/diagnostics/'+name+'.modules.json',JSON.stringify(mods,null,2));console.log(name,mods.length,mods.map(x=>x.name).filter(x=>/net|proto|http|crypto|data|game|request/i.test(x)).join('\n'));
}
