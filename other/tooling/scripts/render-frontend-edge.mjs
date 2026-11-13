import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { GAME_CODES } from "../dist/gateway/catalog.js";

// The generated code is a viewer-request CloudFront Function (runtime 2.0).
// Deployment must attach it to a dedicated version-host distribution with an
// all-viewer origin request policy, MinTTL=0, private S3 OAC, and wildcard TLS.
export function renderFrontendEdge(config) {
  for (const key of [
    "host_suffix",
    "assets_origin_id",
    "assets_domain",
    "dynamic_origin_id",
    "dynamic_tls_name",
  ])
    if (typeof config[key] !== "string" || !config[key])
      throw Error("Missing " + key);
  if (
    !/^\.[a-z0-9.-]+$/.test(config.host_suffix) ||
    !/^[a-z0-9.-]+$/.test(config.assets_domain) ||
    !/^[a-z0-9.-]+$/.test(config.dynamic_tls_name)
  )
    throw Error("Invalid version-domain configuration");
  return `import cf from 'cloudfront';
var config=${JSON.stringify(config)},games=${JSON.stringify(GAME_CODES)};
function handler(event) {
  var request=event.request,host=(request.headers.host||{}).value||'';
  if(host.slice(-config.host_suffix.length)!==config.host_suffix)return request;
  var label=host.slice(0,-config.host_suffix.length),match=/^(fe-\\d{17}-[a-f0-9]{8}-[a-f0-9]{6})-g([1-9]|1[0-9])$/.exec(label);
  if(!match)return {statusCode:404,headers:{'cache-control':{value:'no-store'}}};
  var uri=request.uri,decoded;
  try{decoded=decodeURIComponent(uri);}catch(e){return {statusCode:404,headers:{'cache-control':{value:'no-store'}}};}
  var parts=decoded.split('/');
  if(/[\\\\\\x00-\\x1f]/.test(decoded)||parts.some(function(p){return p==='.'||p==='..';}))return {statusCode:404,headers:{'cache-control':{value:'no-store'}}};
  var reserved=parts.some(function(p){return ['fixtures','diagnostics','data','logs','config','api-documents','api','web-api','game-api','gtt'].indexOf(p)>=0;});
  var asset=(request.method==='GET'||request.method==='HEAD')&&!reserved&&/\\.(js|css|json|png|jpe?g|webp|avif|gif|svg|ico|mp3|ogg|wav|m4a|mp4|webm|woff2?|ttf|otf|wasm|bin|atlas|skel)$/i.test(uri);
  if(asset) {
    cf.selectRequestOriginById(config.assets_origin_id);
    cf.updateRequestOrigin({customHeaders:{}});
    request.uri='/releases/'+games[Number(match[2])-1]+'/'+match[1]+uri;
    request.headers.host={value:config.assets_domain};request.querystring={};request.cookies={};
    Object.keys(request.headers).forEach(function(key){if(['host','accept','accept-encoding','accept-language','origin','range','if-range','if-modified-since','if-none-match','cache-control'].indexOf(key)<0)delete request.headers[key];});
  } else {
    cf.selectRequestOriginById(config.dynamic_origin_id,{hostHeader:host,sni:config.dynamic_tls_name,allowedCertificateNames:[config.dynamic_tls_name]});
  }
  return request;
}
`;
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  const [configPath, output] = process.argv.slice(2);
  if (!configPath || !output)
    throw Error("Supply config.json and an unused output.js path");
  writeFileSync(
    resolve(output),
    renderFrontendEdge(JSON.parse(readFileSync(configPath, "utf8"))),
    { flag: "wx" },
  );
  console.log(resolve(output));
}
