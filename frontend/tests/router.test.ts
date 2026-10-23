import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import * as api from "@/api";
import { clearToken, send, setToken } from "@/api";
import { t } from "@/i18n/de";
import { RETURN_PARAM } from "@/returnTarget";
import { router } from "@/router";
import { clearSession, sessionState, setSession } from "@/session";

const BLANK = { template: "<div></div>" };

beforeEach(async () => {
  clearToken();
  clearSession();
  document.body.innerHTML = '<main id="main" tabindex="-1"></main>';
  await router.push("/");
  await router.isReady();
});

afterEach(() => {
  for (const name of ["geschuetzt", "nur-admin"]) if (router.hasRoute(name)) router.removeRoute(name);
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("every page", () => {
  it("has a name of its own in the catalogue", () => {
    const pages = router.getRoutes().filter((route) => !route.redirect);
    expect(pages.length).toBeGreaterThan(1);

    for (const route of pages) {
      const title = route.meta.title;
      expect(typeof title, `${String(route.name)} has a title`).toBe("string");
      expect(t(title as string)).not.toBe(title);
    }
  });

  it("names itself in the browser's title after a navigation (WCAG 2.4.2)", async () => {
    await router.push({ name: "login" });

    expect(document.title).toBe(`${t("app.titles.login")} · ${t("app.title")}`);
  });

  it("hands the focus to its content, so the next Tab does not walk the navigation again", async () => {
    await router.push({ name: "login" });
    await nextTick();

    expect(document.activeElement?.id).toBe("main");
  });

  it("an address the app does not know leads to the start", async () => {
    await router.push("/gibt-es-nicht");

    expect(router.currentRoute.value.name).toBe("start");
  });
});

describe("the guards", () => {
  it("send a visitor to the sign-in, with the way back", async () => {
    router.addRoute({ path: "/geschuetzt", name: "geschuetzt", component: BLANK, meta: { requiresAuth: true } });

    await router.push("/geschuetzt?x=1");

    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query[RETURN_PARAM]).toBe("/geschuetzt?x=1");
  });

  it("keep the register for accounts: a visitor goes to the sign-in, with the way back", async () => {
    await router.push("/quellen");

    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query[RETURN_PARAM]).toBe("/quellen");
  });

  it("keep an entry's page for accounts too, and hand it the entry's id", async () => {
    await router.push("/quellen/0190-s1");
    expect(router.currentRoute.value.query[RETURN_PARAM]).toBe("/quellen/0190-s1");

    const entry = router.resolve("/quellen/0190-s1");
    expect(entry.name).toBe("source");
    expect(entry.params).toEqual({ id: "0190-s1" });
    expect(entry.matched[0].props).toEqual({ default: true });
  });

  it("keep an entry's blocks for accounts too, and hand them the entry's id", async () => {
    await router.push("/quellen/0190-s1/bloecke?seite=2");
    expect(router.currentRoute.value.query[RETURN_PARAM]).toBe("/quellen/0190-s1/bloecke?seite=2");

    const blocks = router.resolve("/quellen/0190-s1/bloecke");
    expect(blocks.name).toBe("conversion");
    expect(blocks.params).toEqual({ id: "0190-s1" });
    expect(blocks.matched[0].props).toEqual({ default: true });
    // the navigation marks the register as where the reader is
    expect(blocks.meta.section).toBe("sources");
  });

  it("keep an account without the role off a page, to the start", async () => {
    // hiding an entry is convenience; the server refuses the route's requests anyway
    router.addRoute({ path: "/nur-admin", name: "nur-admin", component: BLANK, meta: { requiresRole: "admin" } });
    setToken("kka_token");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });

    await router.push("/nur-admin");

    expect(router.currentRoute.value.name).toBe("start");
  });
});

describe("a token the server stops accepting", () => {
  it("leads to the sign-in, with the page as the way back", async () => {
    setToken("kka_token");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await send("/api/v1/me").catch(() => undefined);
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query[RETURN_PARAM]).toBe("/");
  });

  it("changes nothing once the sign-in is on screen", async () => {
    await router.push({ name: "login" });
    setToken("kka_token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await send("/api/v1/me").catch(() => undefined);
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query[RETURN_PARAM]).toBeUndefined();
  });
});


describe("a page for a role, opened straight from a bookmark", () => {
  beforeEach(() => {
    router.addRoute({ path: "/nur-admin", name: "nur-admin", component: BLANK, meta: { requiresRole: "admin" } });
    setToken("kka_token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the account first, and lets the role in", async () => {
    vi.spyOn(api, "getMe").mockResolvedValue({ id: "0190-a", name: "Erste Admin", roles: ["admin"] });

    await router.push("/nur-admin");

    expect(router.currentRoute.value.name).toBe("nur-admin");
  });

  it("keeps another role out", async () => {
    vi.spyOn(api, "getMe").mockResolvedValue({ id: "0190-b", name: "Lehrkraft", roles: ["nutzer"] });

    await router.push("/nur-admin");

    expect(router.currentRoute.value.name).toBe("start");
  });

  it("leads to the sign-in, with the way back, when the token turns out stale", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await router.push("/nur-admin");
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query[RETURN_PARAM]).toBe("/nur-admin");
  });

  it("goes to the start, where the failure is said, when the account cannot be loaded", async () => {
    vi.spyOn(api, "getMe").mockRejectedValue(new api.ApiError("server", 503, "service_unavailable"));

    await router.push("/nur-admin");

    expect(router.currentRoute.value.name).toBe("start");
    expect(sessionState.value).toBe("failed");
  });
});

describe("scrolling", () => {
  it("opens a new page at its top, and a page met again where it was left", () => {
    const behave = router.options.scrollBehavior;
    expect(behave).toBeDefined();
    const route = router.currentRoute.value;

    const other = { ...route, path: "/anmelden", fullPath: "/anmelden" };

    expect(behave?.(other, route, null)).toEqual({ top: 0 });
    expect(behave?.(route, other, { left: 0, top: 480 })).toEqual({ left: 0, top: 480 });
  });

  it("goes to the top on a link to the page already open: the brand, the active destination", () => {
    // vue-router asks with the same route twice for that click
    const behave = router.options.scrollBehavior;
    const route = router.currentRoute.value;

    expect(behave?.(route, route, null)).toEqual({ top: 0 });
  });

  it("stays put where only the query or the fragment changes: the same page, as for the focus", () => {
    const behave = router.options.scrollBehavior;
    const route = router.currentRoute.value;

    const paged = { ...route, query: { seite: "2" }, fullPath: "/?seite=2" };
    const anchored = { ...route, hash: "#main", fullPath: "/#main" };

    expect(behave?.(paged, route, null)).toBe(false);
    expect(behave?.(anchored, route, null)).toBe(false);
  });
});
