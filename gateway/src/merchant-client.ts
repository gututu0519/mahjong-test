import { check } from "../../other/shared/core.js";

export const PG_GAMES = new Set(["buffalo-win", "captains-bounty", "fortune-rabbit", "wild-bandito", "mahjong-ways2"]);
const JILI_GAMES = new Set(["super-ace", "fortune-gems2", "jokers-fortune-winx", "3-billion-vaults", "money-pot-deluxe", "roma-x-10000"]);
const HACKSAW_GAMES = new Set(["wicked-grin", "le-vampire", "dr-zappo", "great-game-serengeti"]);
const PP_GAMES = new Set(["big-bass-bonanza", "sweet-bonanza-pop", "gates-of-olympus"]);
export type MerchantClient = { code: string; token: string; operator: string; player_id: string; currency: string };

export function merchantLaunchQuery(code: string, token: string, language: string, operator: string) {
  return new URLSearchParams({ops:token,l:language,lang:language,
    ...(PG_GAMES.has(code) ? {btt:"1",ot:operator} : {})});
}

export function merchantClientURL(href: string, origin: string, client: MerchantClient) {
  const url = new URL(href, origin);
  check(url.origin === origin, "GAME_ENTRY_INVALID", "Game entry must stay on its configured origin");
  for (const key of ["mock", "preview"]) url.searchParams.delete(key);
  url.searchParams.set("ops", client.token);
  if (PG_GAMES.has(client.code)) {
    url.searchParams.set("btt", "1");
    url.searchParams.set("ot", client.operator);
  }
  if (JILI_GAMES.has(client.code)) {
    url.searchParams.set("demo", "false");
    if (url.searchParams.has("currency")) url.searchParams.set("currency", client.currency);
    url.searchParams.delete("loginFrom");
    if (url.searchParams.has("ssoKey")) url.searchParams.set("ssoKey", client.token);
  }
  if (HACKSAW_GAMES.has(client.code)) {
    // All four captured casino bundles explicitly map 1=live and 2=demo.
    url.searchParams.set("mode", "1");
    url.searchParams.set("partner", client.operator);
    url.searchParams.set("currency", client.currency);
    url.searchParams.delete("disableddemotext");
  }
  return url.pathname + url.search + url.hash;
}

function merchantTransport() {
  const client = (window as any).__GTT_MERCHANT__;
  const local = (input: string) => new URL(input, location.href).origin === location.origin;
  const nativeFetch = window.fetch;
  window.fetch = function(input, init) {
    const source = input instanceof Request ? input.url : String(input);
    if (!local(source)) return nativeFetch.call(this, input, init);
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    headers.set("Authorization", "Bearer " + client.token);
    return nativeFetch.call(this, input, {...init, headers});
  };
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method: string, url: string | URL, ...args: any[]) {
    (this as any).__gttLocal = local(String(url));
    return (open as any).call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if ((this as any).__gttLocal) this.setRequestHeader("Authorization", "Bearer " + client.token);
    return send.call(this, body);
  };
  const NativeWebSocket = window.WebSocket;
  window.WebSocket = class extends NativeWebSocket {
    constructor(input: string | URL, protocols?: string | string[]) {
      const url = new URL(input, location.href);
      if (url.host === location.host && ["ws:", "wss:"].includes(url.protocol))
        url.searchParams.set("ops", client.token);
      if (protocols === undefined) super(url); else super(url, protocols);
    }
  };
}

export function merchantClientHTML(html: string, href: string, origin: string, client: MerchantClient) {
  if (PP_GAMES.has(client.code)) {
    // The original worker builds these URLs from its loopback listener address.
    // Keep both assets and wallet requests on the authenticated game host.
    html = html.replace(/("(?:datapath|gameService)"\s*:\s*")https?:\/\/[^"/]+(\/[^"\n]*)"/g,
      (_match, prefix, path) => prefix + origin + path + '"');
  }
  const json = (v: unknown) => JSON.stringify(v).replaceAll("<", "\\u003c");
  const current = merchantClientURL(href, origin, client);
  const script = `<script>window.__GTT_MERCHANT__=Object.freeze(${json(client)});history.replaceState(history.state,'',${json(current)});(${merchantTransport.toString()})();</script>`;
  html = html.replace(/<head\b[^>]*>/i, match => match + script);
  if (client.code === "mahjong-ways2" && !html.includes('src="/local-auth-bootstrap.js'))
    html = html.replace(/<\/head>/i, '<script src="/local-frame-clock.js"></script><script src="/local-auth-bootstrap.js"></script></head>');
  if (client.code === "tower-run-treasure-steps" && /\bpractice\s*:/.test(html)) {
    html = html.replace(/\bpractice\s*:\s*1\b/, "practice: 0");
    html = html.replace(/\bticket\s*:\s*""/, "ticket: " + json(client.token));
  }
  return html;
}

export function merchantClientJSON(value: any, client: MerchantClient): any {
  if (Array.isArray(value)) return value.map(v => merchantClientJSON(v, client));
  if (!value || typeof value !== "object") return value;
  const copy = Object.fromEntries(Object.entries(value).map(([key,v]) =>
    [key, (key === "cc" || key === "currencyCode") && typeof v === "string" ? client.currency : merchantClientJSON(v, client)]));
  if (HACKSAW_GAMES.has(client.code) && copy.accountBalance) {
    const balance: any = copy.accountBalance;
    balance.realBalance = balance.balance;
    balance.bonusBalance = "0";
    if (copy.sessionUuid && copy.playerId) {
      copy.partnerId = client.operator;
      copy.name = client.player_id;
    }
  }
  return copy;
}

export function merchantClientText(text: string, client: MerchantClient) {
  if (client.code !== "tower-run-treasure-steps") return text;
  return text.replace(/(^d=|\r?\n)101 1 "DEMO" "" "ZZ" "Player" ""/g,
    (_, prefix) => prefix + '101 1 ' + JSON.stringify(client.currency) + ' "" "ZZ" ' + JSON.stringify(client.player_id) + ' ""');
}

export function merchantPGAuth(template: any, client: MerchantClient, wallet: any) {
  const flags = Object.fromEntries("as bf bu cl et hd il ir mr np rp sp vc we gec gsc hnp igv pwr rcf std swf tsn grtp phtr smpo bfbli bfbsi swfbli swfbsi".split(" ").map(k => [k,0]));
  Object.assign(flags,Object.fromEntries("bb gc hn ts asc hwl ign ivs sbb".split(" ").map(k => [k,1])),{cbu:0});
  const metadata = template ?? {st:1,geu:"game-api/74/",bau:"web-api/game-proxy/",lau:"game-api/lobby/",
    gm:[{st:1,gid:74,mxe:5000}],oj:{jid:1},uiogc:flags,ec:[],occ:{tcm:"",tlb:"",trb:"",tsc:0,ttp:0,rurl:""},sdn:"api"};
  return {dt:{...metadata,oj:metadata.oj ?? {jid:1},uiogc:{...metadata.uiogc,...(client.code === "buffalo-win" ? {bf:1} : {})},tk:client.token,pid:wallet.player_id,pcd:wallet.player_id,
    nkn:client.player_id,ioph:client.operator,cc:client.currency,cs:"",bl:wallet.balance_minor/100},err:null};
}
