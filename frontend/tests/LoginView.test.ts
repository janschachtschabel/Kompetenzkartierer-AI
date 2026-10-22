import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { t } from "@/i18n/de";
import { router } from "@/router";
import { clearSession, session } from "@/session";
import LoginView from "@/views/LoginView.vue";

const TOKEN = "kka_" + "t".repeat(43);
const ME: api.Me = { id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] };

async function signIn(typed: string, query: Record<string, string> = {}) {
  await router.push({ name: "login", query });
  const wrapper = mount(LoginView, { global: { plugins: [router] }, attachTo: document.body });
  await wrapper.get("input").setValue(typed);
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  return wrapper;
}

beforeEach(async () => {
  vi.restoreAllMocks();
  api.clearToken();
  clearSession();
  await router.push("/");
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("signing in", () => {
  it("asks for a token before it asks the server", async () => {
    const check = vi.spyOn(api, "checkToken");

    const wrapper = await signIn("   ");

    expect(wrapper.get("[role=alert]").text()).toContain(t("login.errors.empty"));
    expect(check).not.toHaveBeenCalled();
  });

  it("says a refused token is not valid, beside the field, and keeps nothing", async () => {
    vi.spyOn(api, "checkToken").mockResolvedValue(null);

    const wrapper = await signIn(TOKEN);

    const field = wrapper.get("input");
    expect(wrapper.get("#login-error").text()).toContain(t("login.errors.invalid"));
    expect(field.attributes("aria-invalid")).toBe("true");
    expect(field.attributes("aria-describedby")).toBe("login-error");
    expect(api.getToken()).toBeNull();
  });

  it("keeps a good token and its account, and goes to the start", async () => {
    const check = vi.spyOn(api, "checkToken").mockResolvedValue(ME);
    const push = vi.spyOn(router, "push");

    await signIn(`  ${TOKEN} `);

    expect(check).toHaveBeenCalledWith(TOKEN);
    expect(api.getToken()).toBe(TOKEN);
    expect(session.value).toEqual(ME);
    expect(push).toHaveBeenLastCalledWith({ name: "start" });
  });

  it("goes back where the visitor was going, if that is a page of this app", async () => {
    vi.spyOn(api, "checkToken").mockResolvedValue(ME);
    const push = vi.spyOn(router, "push");

    await signIn(TOKEN, { ziel: "/konto?x=1" });
    expect(push).toHaveBeenLastCalledWith("/konto?x=1");

    await signIn(TOKEN, { ziel: "//evil.example/" });
    expect(push).toHaveBeenLastCalledWith({ name: "start" });
  });

  it("says how long to wait after too many failures, in minutes", async () => {
    vi.spyOn(api, "checkToken").mockRejectedValue(new api.ApiError("server", 429, "too_many_requests", "x", {}, 900));

    const wrapper = await signIn(TOKEN);

    expect(wrapper.get("[role=alert]").text()).toContain(t("login.errors.locked", { count: 15 }));
  });

  it("says to try later where the wait is not named", async () => {
    vi.spyOn(api, "checkToken").mockRejectedValue(new api.ApiError("server", 429, "too_many_requests"));

    const wrapper = await signIn(TOKEN);

    expect(wrapper.get("[role=alert]").text()).toContain(t("login.errors.lockedLater"));
  });

  it("tells a lost connection from a server that failed", async () => {
    vi.spyOn(api, "checkToken").mockRejectedValueOnce(new api.ApiError("network", 0));
    const offline = await signIn(TOKEN);
    expect(offline.get("[role=alert]").text()).toContain(t("login.errors.network"));

    vi.spyOn(api, "checkToken").mockRejectedValueOnce(new api.ApiError("server", 500, "internal_server_error"));
    const failed = await signIn(TOKEN);
    expect(failed.get("[role=alert]").text()).toContain(t("login.errors.server"));
  });

  it("shows that it is checking, and takes no second press meanwhile", async () => {
    let answer: (me: api.Me | null) => void = () => undefined;
    vi.spyOn(api, "checkToken").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    await router.push({ name: "login" });
    const wrapper = mount(LoginView, { global: { plugins: [router] } });
    await wrapper.get("input").setValue(TOKEN);

    await wrapper.get("form").trigger("submit");

    const button = wrapper.get("button[type=submit]");
    expect(button.text()).toBe(t("login.checking"));
    expect(button.attributes("disabled")).toBeDefined();
    answer(null);
    await flushPromises();
    expect(button.text()).toBe(t("login.submit"));
  });
});
