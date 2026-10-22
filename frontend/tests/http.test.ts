import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, clearToken, getMe, getToken, onUnauthorized, send, setToken, verifyToken } from "@/api";

const TOKEN = "kka_" + "t".repeat(43);

function answer(status: number, body?: unknown, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers });
}

function sentHeaders(): Headers {
  return new Headers((vi.mocked(fetch).mock.calls[0][1] as RequestInit).headers);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  onUnauthorized(null);
  clearToken();
  vi.unstubAllGlobals();
});

describe("a request", () => {
  it("carries the token as a bearer token", async () => {
    setToken(TOKEN);
    vi.mocked(fetch).mockResolvedValue(answer(200, {}));

    await send("/api/v1/me");

    expect(sentHeaders().get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("carries none without a token, and none where the route is open", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(200, {}));
    await send("/api/v1/info");
    expect(sentHeaders().get("Authorization")).toBeNull();

    setToken(TOKEN);
    vi.mocked(fetch).mockClear();
    await send("/api/v1/info", {}, { withToken: false });
    expect(sentHeaders().get("Authorization")).toBeNull();
  });

  it("declares a JSON body as JSON", async () => {
    // Without it fetch sends text/plain, and FastAPI answers 422.
    vi.mocked(fetch).mockResolvedValue(answer(200, {}));

    await send("/api/v1/accounts", { method: "POST", body: JSON.stringify({ name: "x" }) });

    expect(sentHeaders().get("Content-Type")).toBe("application/json");
  });

  it("leaves an upload alone so the browser can set its boundary", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(200, {}));
    const form = new FormData();
    form.append("file", "x");

    await send("/api/v1/uploads", { method: "POST", body: form });

    expect(sentHeaders().get("Content-Type")).toBeNull();
  });

  it("does not overrule a content type the caller chose", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(200, {}));

    await send("/api/v1/x", { method: "POST", body: "a,b\n1,2", headers: { "Content-Type": "text/csv" } });

    expect(sentHeaders().get("Content-Type")).toBe("text/csv");
  });

  it("reads a JSON answer, and an empty one as null", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(answer(200, { id: "a" }));
    await expect(apiFetch("/api/v1/x")).resolves.toEqual({ id: "a" });

    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(apiFetch("/api/v1/x")).resolves.toBeNull();
  });
});

describe("a failed request", () => {
  it("hands on the code, the server's sentence and its details", async () => {
    // The server's error shape: a code for programs, an English sentence for
    // people reading the raw answer, details by field and kind.
    vi.mocked(fetch).mockResolvedValue(
      answer(422, {
        code: "validation_failed",
        message: "The request is not valid.",
        details: { errors: [{ loc: ["body", "name"], type: "string_too_short" }] },
      }),
    );

    const refused = await send("/api/v1/accounts").catch((error: unknown) => error);

    expect(refused).toBeInstanceOf(ApiError);
    expect(refused).toMatchObject({
      kind: "server",
      status: 422,
      code: "validation_failed",
      sentence: "The request is not valid.",
      details: { errors: [{ loc: ["body", "name"], type: "string_too_short" }] },
    });
  });

  it("tells a missing token from a missing role", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(answer(401, { code: "unauthorized", message: "A token is needed." }));
    await expect(send("/api/v1/me")).rejects.toMatchObject({ kind: "unauthorized", status: 401 });

    vi.mocked(fetch).mockResolvedValueOnce(answer(403, { code: "forbidden", message: "This needs another role." }));
    await expect(send("/api/v1/accounts")).rejects.toMatchObject({ kind: "forbidden", status: 403 });
  });

  it("keeps the status of an answer that is no JSON, and nothing it cannot read", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502 }));

    const refused = await send("/api/v1/x").catch((error: unknown) => error);

    expect(refused).toMatchObject({ kind: "server", status: 502, code: undefined, sentence: undefined });
  });

  it("does not take a sentence that is no string", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(400, { code: "bad_request", message: { text: "x" } }));

    await expect(send("/api/v1/x")).rejects.toMatchObject({ code: "bad_request", sentence: undefined });
  });

  it.each([429, 503])("hands on how long a %i asks the client to wait", async (status) => {
    vi.mocked(fetch).mockResolvedValue(answer(status, { code: "x", message: "wait" }, { "Retry-After": "42" }));

    await expect(send("/api/v1/x")).rejects.toMatchObject({ status, retryAfter: 42 });
  });

  it("leaves the wait unknown where it is no number of seconds", async () => {
    vi.mocked(fetch).mockResolvedValue(
      answer(429, { code: "too_many_requests", message: "wait" }, { "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT" }),
    );

    const refused = await send("/api/v1/x").catch((error: unknown) => error);

    expect((refused as ApiError).retryAfter).toBeUndefined();
  });

  it("says that the network failed", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("offline"));

    await expect(send("/api/v1/x")).rejects.toMatchObject({ kind: "network", status: 0 });
  });
});

describe("a token the server no longer accepts", () => {
  beforeEach(() => {
    setToken(TOKEN);
  });

  it("is dropped on a 401, and the app is told once", async () => {
    // The one place every request passes: it drops the token and hands over to
    // whoever registered - the router, which knows where the sign-in is.
    const handler = vi.fn();
    onUnauthorized(handler);
    vi.mocked(fetch).mockResolvedValue(answer(401, { code: "unauthorized", message: "The token is not valid." }));

    await expect(getMe()).rejects.toMatchObject({ status: 401 });

    expect(getToken()).toBeNull();
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("stays on a 403: the token is good, the route is not for this account", async () => {
    const handler = vi.fn();
    onUnauthorized(handler);
    vi.mocked(fetch).mockResolvedValue(answer(403, { code: "forbidden", message: "This needs another role." }));

    await expect(send("/api/v1/accounts")).rejects.toMatchObject({ status: 403 });

    expect(getToken()).toBe(TOKEN);
    expect(handler).not.toHaveBeenCalled();
  });

  it("stays on a 401 of an open route, which never looked at it", async () => {
    const handler = vi.fn();
    onUnauthorized(handler);
    vi.mocked(fetch).mockResolvedValue(answer(401, { code: "unauthorized", message: "A token is needed." }));

    await expect(send("/api/v1/open", {}, { withToken: false })).rejects.toMatchObject({ status: 401 });

    expect(getToken()).toBe(TOKEN);
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("checking a token before it is kept", () => {
  it("answers with the account a good token belongs to", async () => {
    const me = { id: "0190-a", name: "Erste Admin", roles: ["admin"] };
    vi.mocked(fetch).mockResolvedValue(answer(200, me));

    await expect(verifyToken(TOKEN)).resolves.toEqual(me);

    expect(sentHeaders().get("Authorization")).toBe(`Bearer ${TOKEN}`);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/v1/me");
    expect(getToken()).toBeNull();
  });

  it("answers null for a token the server refuses, without telling the app", async () => {
    // A wrong token typed at the sign-in is that page's business, not a session ending.
    const handler = vi.fn();
    onUnauthorized(handler);
    vi.mocked(fetch).mockResolvedValue(answer(401, { code: "unauthorized", message: "The token is not valid." }));

    await expect(verifyToken(TOKEN)).resolves.toBeNull();

    expect(handler).not.toHaveBeenCalled();
  });

  it("says how long the address has to wait after too many failures", async () => {
    vi.mocked(fetch).mockResolvedValue(
      answer(429, { code: "too_many_requests", message: "Too many failed sign-ins" }, { "Retry-After": "900" }),
    );

    await expect(verifyToken(TOKEN)).rejects.toMatchObject({ status: 429, retryAfter: 900 });
  });

  it("says that the network failed", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("offline"));

    await expect(verifyToken(TOKEN)).rejects.toMatchObject({ kind: "network" });
  });
});
