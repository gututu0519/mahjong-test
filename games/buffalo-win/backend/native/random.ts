import { createHash } from "node:crypto";
// CPython random.Random(str), version=2: SHA512 string seed + MT19937 init_by_array.
export class PythonRandom {
  private mt = new Uint32Array(624);
  private index = 624;
  constructor(seed: string | number) {
    const bytes = Buffer.from(typeof seed === 'string' ? seed : ''),
      all = Buffer.concat([bytes, createHash("sha512").update(bytes).digest()]);
    const words: number[] = [];
    let n = typeof seed === 'number' ? BigInt(Math.abs(seed)) : BigInt("0x" + all.toString("hex"));
    while (n) {
      words.push(Number(n & 0xffffffffn));
      n >>= 32n;
    }
    if (!words.length) words.push(0);
    this.mt[0] = 19650218;
    for (let i = 1; i < 624; i++)
      this.mt[i] =
        (Math.imul(1812433253, this.mt[i - 1] ^ (this.mt[i - 1] >>> 30)) +
          i) >>>
        0;
    let i = 1,
      j = 0;
    for (let k = Math.max(624, words.length); k; k--) {
      this.mt[i] =
        ((this.mt[i] ^
          Math.imul(this.mt[i - 1] ^ (this.mt[i - 1] >>> 30), 1664525)) +
          words[j] +
          j) >>>
        0;
      if (++i >= 624) {
        this.mt[0] = this.mt[623];
        i = 1;
      }
      if (++j >= words.length) j = 0;
    }
    for (let k = 623; k; k--) {
      this.mt[i] =
        ((this.mt[i] ^
          Math.imul(this.mt[i - 1] ^ (this.mt[i - 1] >>> 30), 1566083941)) -
          i) >>>
        0;
      if (++i >= 624) {
        this.mt[0] = this.mt[623];
        i = 1;
      }
    }
    this.mt[0] = 0x80000000;
  }
  private uint() {
    if (this.index >= 624) {
      for (let i = 0; i < 624; i++) {
        const y =
          (this.mt[i] & 0x80000000) | (this.mt[(i + 1) % 624] & 0x7fffffff);
        this.mt[i] =
          this.mt[(i + 397) % 624] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
      }
      this.index = 0;
    }
    let y = this.mt[this.index++];
    y ^= y >>> 11;
    y ^= (y << 7) & 0x9d2c5680;
    y ^= (y << 15) & 0xefc60000;
    y ^= y >>> 18;
    return y >>> 0;
  }
  random() {
    return (
      ((this.uint() >>> 5) * 67108864 + (this.uint() >>> 6)) / 9007199254740992
    );
  }
  range(n: number) {
    const k = Math.floor(Math.log2(n)) + 1;
    let v;
    do {
      v = this.uint() >>> (32 - k);
    } while (v >= n);
    return v;
  }
  int(a: number, b: number) {
    return a + this.range(b - a + 1);
  }
  choice(values: number[], weights: number[]) {
    const x = this.random() * weights.reduce((a, b) => a + b, 0);
    let total = 0;
    for (let i = 0; i < values.length; i++) {
      total += weights[i];
      if (x < total) return values[i];
    }
    return values.at(-1)!;
  }
}
