import { readFileSync } from "node:fs";
import { join } from "node:path";

import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import App from "@/App.vue";
import { t } from "@/i18n/de";
import { router } from "@/router";
import { clearSession, session, setSession } from "@/session";

import { detail, page } from "./registerEntries";
import { SRC, cssRules, stylesOf } from "./sources";

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
  vi.spyOn(api, "getInfo").mockResolvedValue({ name: "Kompetenzkartierer-AI", version: "0.1.0", public_access: "off", max_upload_mb: 50 });
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

  it("marks where the reader is: the page itself, or the section an entry's page lies in", async () => {
    vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    vi.spyOn(api, "getSource").mockResolvedValue(detail());
    const wrapper = await render("/quellen");
    const link = (href: string) => wrapper.get(`nav a[href='${href}']`);
    expect(link("/quellen").attributes("aria-current")).toBe("page");
    expect(link("/").attributes("aria-current")).toBeUndefined();

    await router.push("/quellen/s1");
    await flushPromises();
    expect(link("/quellen").attributes("aria-current")).toBe("true");
    expect(link("/").attributes("aria-current")).toBeUndefined();

    await router.push("/");
    await flushPromises();
    expect(link("/").attributes("aria-current")).toBe("page");
    expect(link("/quellen").attributes("aria-current")).toBeUndefined();
  });

  it("draws the mark by the state it says: what the eye sees, a screen reader hears", () => {
    const rules = cssRules(stylesOf(readFileSync(join(SRC, "App.vue"), "utf8")));

    const marked = rules.filter(({ selectors }) => selectors.includes(".shell__destination[aria-current]"));

    expect(marked.map(({ body }) => body).join("")).toMatch(/background:\s*var\(--accent-wash\)/);
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
    await flushPromises();

    expect(api.getToken()).toBeNull();
    expect(session.value).toBeNull();
    expect(push).toHaveBeenCalledWith({ name: "login" });
  });

  it("signs out once the sign-in is reached by the move made anew after a draft was asked about", async () => {
    const wrapper = await render();
    const stay = router.beforeEach(() => false); // asked about, a second move came: this one held
    await wrapper.get("button.shell__sign-out").trigger("click");
    await flushPromises();
    stay();
    expect(api.getToken()).not.toBeNull();

    await router.push({ name: "login" }); // the draft to go: the move made anew

    expect([api.getToken(), session.value]).toEqual([null, null]);
  });

  it("keeps the account where the user, asked, went on elsewhere", async () => {
    const wrapper = await render();
    const stay = router.beforeEach(() => false);
    await wrapper.get("button.shell__sign-out").trigger("click");
    await flushPromises();
    stay();

    await router.push({ name: "sources" });
    await router.push({ name: "login" }); // later, by another way: no sign-out pending any more

    expect(api.getToken()).not.toBeNull();
  });

  it("signs out on the sign-in page itself, where there is no page to leave", async () => {
    const wrapper = await render("/anmelden");

    await wrapper.get("button.shell__sign-out").trigger("click");
    await flushPromises();

    expect([api.getToken(), session.value]).toEqual([null, null]);
  });

  it("stays signed in where the page it would leave keeps the user, a draft asked about", async () => {
    const wrapper = await render();
    const stay = router.beforeEach(() => false); // the leave guard's answer: stay with the draft

    await wrapper.get("button.shell__sign-out").trigger("click");
    await flushPromises();
    stay();

    expect(api.getToken()).not.toBeNull();
    expect(session.value).not.toBeNull();
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
    vi.spyOn(api, "getMe").mockRejectedValue(new api.ApiError("server", 429, "too_many_requests", "Too many failed sign-ins; try again later.", {}, 900));
    const wrapper = await render();
    const push = vi.spyOn(router, "push");

    await wrapper.get("header button.shell__sign-out").trigger("click");
    await flushPromises();

    expect(api.getToken()).toBeNull();
    expect(push).toHaveBeenCalledWith({ name: "login" });
  });
});
