import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Me } from "@/api";

vi.mock("@/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api")>()),
  getMe: vi.fn(),
  getToken: vi.fn(),
}));

const api = await import("@/api");
const { clearSession, ensureSession, hasRole, session, sessionFailure, sessionState, setSession } =
  await import("@/session");

const ME: Me = { id: "0190-a", name: "Erste Admin", roles: ["admin"] };

beforeEach(() => {
  clearSession();
  vi.mocked(api.getMe).mockReset();
  vi.mocked(api.getToken).mockReturnValue("kka_token");
});

describe("the session", () => {
  it("loads the account once for everyone who asks at the same time", async () => {
    let answer: (me: Me) => void = () => undefined;
    vi.mocked(api.getMe).mockReturnValue(new Promise((resolve) => (answer = resolve)));

    const asked = [ensureSession(), ensureSession(), ensureSession()];
    answer(ME);
    await Promise.all(asked);

    expect(api.getMe).toHaveBeenCalledTimes(1);
    expect(session.value).toEqual(ME);
  });

  it("asks for nothing without a token, or with an account already loaded", async () => {
    vi.mocked(api.getToken).mockReturnValue(null);
    await ensureSession();

    vi.mocked(api.getToken).mockReturnValue("kka_token");
    setSession(ME);
    await ensureSession();

    expect(api.getMe).not.toHaveBeenCalled();
  });

  it("stays empty when the account cannot be loaded, and says that it failed and why", async () => {
    // the page must tell an account whose load failed from a visitor
    const failure = new api.ApiError("server", 503, "service_unavailable");
    vi.mocked(api.getMe).mockRejectedValue(failure);

    await ensureSession();

    expect(session.value).toBeNull();
    expect(sessionState.value).toBe("failed");
    expect(sessionFailure.value).toBe(failure);
  });

  it("is loading while the account is asked for, and ready after", async () => {
    let answer: (me: Me) => void = () => undefined;
    vi.mocked(api.getMe).mockReturnValue(new Promise((resolve) => (answer = resolve)));

    const asked = ensureSession();
    expect(sessionState.value).toBe("loading");
    answer(ME);
    await asked;

    expect(sessionState.value).toBe("ready");
  });

  it("tells the roles of the account", () => {
    setSession({ ...ME, roles: ["redaktion"] });

    expect(hasRole("redaktion")).toBe(true);
    expect(hasRole("admin")).toBe(false);
  });

  it("is empty once cleared, and so has no role", () => {
    setSession(ME);
    clearSession();

    expect(session.value).toBeNull();
    expect(hasRole("admin")).toBe(false);
  });
});


describe("a late answer", () => {
  it("does not overwrite the account signed in meanwhile", async () => {
    let answer: (me: Me) => void = () => undefined;
    vi.mocked(api.getMe).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const asked = ensureSession();

    const other: Me = { id: "0190-b", name: "Zweites Konto", roles: ["nutzer"] };
    setSession(other);
    answer(ME);
    await asked;

    expect(session.value).toEqual(other);
  });

  it("does not bring back an account signed out meanwhile", async () => {
    let answer: (me: Me) => void = () => undefined;
    vi.mocked(api.getMe).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const asked = ensureSession();

    clearSession();
    answer(ME);
    await asked;

    expect(session.value).toBeNull();
    expect(sessionState.value).toBe("none");
  });

  it("for another token than the one held now is dropped", async () => {
    let answer: (me: Me) => void = () => undefined;
    vi.mocked(api.getMe).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const asked = ensureSession();

    vi.mocked(api.getToken).mockReturnValue("kka_other");
    answer(ME);
    await asked;

    expect(session.value).toBeNull();
    expect(sessionState.value).toBe("none");
    // the token held now gets its own question, not the settled answer of the old one
    vi.mocked(api.getMe).mockResolvedValue(ME);
    await ensureSession();
    expect(api.getMe).toHaveBeenCalledTimes(2);
    expect(session.value).toEqual(ME);
  });
});
