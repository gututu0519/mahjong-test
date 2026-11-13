import { check, encode, ServiceError } from "../shared/core.js";
import { fetchBounded } from "../shared/http.js";
export class GameClient {
  constructor(
    public origin: string,
    private secret: string,
    public configuration: any,
  ) {
    const u = new URL(origin);
    check(
      u.protocol === "http:" &&
        ["127.0.0.1", "localhost", "[::1]"].includes(u.hostname) &&
        u.pathname === "/" &&
        !u.search &&
        !u.hash,
      "GAME_ORIGIN_INVALID",
    );
  }
  async call(action: string, p: any = {}, configuration = this.configuration) {
    try {
      const r = await fetchBounded(
        this.origin + "/v1/" + action,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            authorization: "Bearer " + this.secret,
          },
          body: encode({ ...p, configuration }),
          timeout: action === "plan" ? 120000 : 10000,
        },
        16 * 1024 * 1024,
      );
      const v = JSON.parse(r.body);
      if (v.error)
        throw new ServiceError(v.error.code, v.error.message, r.status);
      check(r.status === 200 && v.data != null, "GAME_UNAVAILABLE");
      return v.data;
    } catch (e) {
      if (e instanceof ServiceError) throw e;
      throw new ServiceError(
        "GAME_UNAVAILABLE",
        "Game calculation unavailable; retry the same operation",
        503,
      );
    }
  }
}
