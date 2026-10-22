import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Me } from "@/api";

vi.mock("@/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api")>()),
  getMe: vi.fn(),
  getToken: vi.fn(),
}));

const api = await import("@/api");
const { clearSession, ensureSession, hasRole, session, setSession } = await import("@/session");

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

  it("stays empty when the account cannot be loaded, so nothing shows that may not", async () => {
    vi.mocked(api.getMe).mockRejectedValue(new api.ApiError("network", 0));

    await ensureSession();

    expect(session.value).toBeNull();
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
