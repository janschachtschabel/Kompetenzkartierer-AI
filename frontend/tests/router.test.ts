import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { clearToken, send, setToken } from "@/api";
import { t } from "@/i18n/de";
import { RETURN_PARAM } from "@/returnTarget";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";

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
