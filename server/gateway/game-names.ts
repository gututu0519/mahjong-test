import { GAME_CODES } from "./catalog.js";

// Platform display names; translation provenance is documented in docs/game-integration-readiness.md.
// Bind names to stable game codes so catalog order cannot change an integration ID.
const names: Record<string, [string, string]> = {
  "buffalo-win": [
    "美洲野牛",
    "Buffalo Win"
  ],
  "captains-bounty": [
    "赏金船长",
    "Captain’s Bounty"
  ],
  "fortune-rabbit": [
    "福兔",
    "Fortune Rabbit"
  ],
  "wild-bandito": [
    "狂野大盗",
    "Wild Bandito"
  ],
  "tower-run-treasure-steps": [
    "高塔寻宝阶梯",
    "Tower Run Treasure Steps"
  ],
  "great-game-serengeti": [
    "塞伦盖蒂大猎场",
    "Great Game Serengeti"
  ],
  "dr-zappo": [
    "扎波博士",
    "Dr Zappo"
  ],
  "le-vampire": [
    "吸血鬼",
    "Le Vampire"
  ],
  "wicked-grin": [
    "邪恶笑容",
    "Wicked Grin"
  ],
  "roma-x-10000": [
    "罗马 X 10000",
    "Roma X 10000"
  ],
  "money-pot-deluxe": [
    "豪华聚宝盆",
    "Money Pot DELUXE"
  ],
  "3-billion-vaults": [
    "三十亿保险库",
    "3 Billion Vaults"
  ],
  "jokers-fortune-winx": [
    "小丑财富 WinX",
    "Joker’s Fortune WinX"
  ],
  "fortune-gems2": [
    "财富宝石 2",
    "Fortune Gems 2"
  ],
  "super-ace": [
    "超级王牌",
    "Super Ace"
  ],
  "big-bass-bonanza": [
    "大鲈鱼",
    "Big Bass Bonanza"
  ],
  "sweet-bonanza-pop": [
    "甜蜜财富 POP",
    "Sweet Bonanza POP"
  ],
  "gates-of-olympus": [
    "奥林匹斯之门",
    "Gates of Olympus"
  ],
  "mahjong-ways2": [
    "麻将胡了 2",
    "Mahjong Ways 2"
  ]
};

export function gameNames(id: number) {
  const entry = names[GAME_CODES[id - 1]];
  return entry ? {title_zh:entry[0], title_en:entry[1]} : {title_zh:"",title_en:""};
}
