import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import App from "@/App.vue";
import { t } from "@/i18n/de";
import { router } from "@/router";
import { clearSession, session, setSession } from "@/session";

async function render(path = "/") {
  await router.push(path);
  const wrapper = mount(App, { global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.restoreAllMocks();
  api.clearToken();
  clearSession();
  vi.spyOn(api, "getInfo").mockResolvedValue({ name: "Kompetenzkartierer-AI", version: "0.1.0", public_access: "off" });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("the shell for a visitor", () => {
  it("has one main region, a skip link to it, and the way to sign in", async () => {
    const wrapper = await render();

    expect(wrapper.findAll("main")).toHaveLength(1);
    expect(wrapper.get("a.skip-link").attributes("href")).toBe("#main");
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(wrapper.get("header a[href='/anmelden']").text()).toBe(t("app.signIn"));
  });

  it("offers no second way to sign in on the sign-in page itself", async () => {
    const wrapper = await render("/anmelden");

    expect(wrapper.find("header a[href='/anmelden']").exists()).toBe(false);
  });
});

describe("the shell for an account", () => {
  beforeEach(() => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Erste Admin", roles: ["admin", "redaktion"] });
  });

  it("names its navigation and leads to what the roles open", async () => {
    const wrapper = await render();

    const nav = wrapper.get("nav");
    expect(nav.attributes("aria-label")).toBe(t("app.nav.label"));
    expect(nav.get("a[href='/']").text()).toBe(t("app.nav.start"));
  });

  it("says who is signed in, in which roles", async () => {
    const wrapper = await render();

    const account = wrapper.get(".shell__account").text();
    expect(account).toContain("Erste Admin");
    expect(account).toContain(t("app.roles.admin"));
    expect(account).toContain(t("app.roles.redaktion"));
  });

  it("signs out: forgets the token and the account, and goes to the sign-in", async () => {
    const wrapper = await render();
    const push = vi.spyOn(router, "push");

    await wrapper.get("button.shell__sign-out").trigger("click");

    expect(api.getToken()).toBeNull();
    expect(session.value).toBeNull();
    expect(push).toHaveBeenCalledWith({ name: "login" });
  });
});


describe("the shell while an account is held but not loaded", () => {
  it("offers no sign-in, as if nobody were signed in", async () => {
    api.setToken("kka_token");
    vi.spyOn(api, "getMe").mockReturnValue(new Promise(() => undefined));

    const wrapper = await render();

    expect(wrapper.find("header a[href='/anmelden']").exists()).toBe(false);
  });

  it("offers the way out once the account cannot be loaded: a stale token is no dead end", async () => {
    api.setToken("kka_token");
    vi.spyOn(api, "getMe").mockRejectedValue(new api.ApiError("server", 429, undefined, undefined, {}, 900));
    const wrapper = await render();
    const push = vi.spyOn(router, "push");

    await wrapper.get("header button.shell__sign-out").trigger("click");

    expect(api.getToken()).toBeNull();
    expect(push).toHaveBeenCalledWith({ name: "login" });
  });
});
