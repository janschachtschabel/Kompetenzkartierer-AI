/**
 * axe over the pages as they are shown: the shell with its routed page, mounted
 * in the document as the app is, for a visitor and for an account, and the
 * sign-in with a refusal on screen. The whole document is checked, so the rules
 * about the page itself fire too (tests/axe.ts, pageViolations).
 */
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import App from "@/App.vue";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";

import { describeViolations, pageViolations } from "./axe";

let shown: VueWrapper | null = null;

async function show(path: string): Promise<VueWrapper> {
  document.body.innerHTML = '<div id="app"></div>';
  await router.push(path);
  shown = mount(App, { global: { plugins: [router] }, attachTo: "#app" });
  await flushPromises();
  return shown;
}

beforeEach(() => {
  vi.restoreAllMocks();
  api.clearToken();
  clearSession();
  // as index.html says it
  document.documentElement.lang = "de";
  vi.spyOn(api, "getInfo").mockResolvedValue({ name: "Kompetenzkartierer-AI", version: "0.1.0", public_access: "lookup" });
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("the page harness", () => {
  it("reports a page whose content is in no landmark", async () => {
    // the guard on the checks below: inside a div these rules never fire
    document.body.innerHTML = '<div id="app"><p>Nur ein Absatz.</p></div>';

    const found = describeViolations(await pageViolations());

    expect(found).toMatch(/landmark-one-main|region/);
  });
});

describe("accessibility of the pages", () => {
  it("the start page for a visitor has none", async () => {
    const wrapper = await show("/");
    expect(wrapper.html().length).toBeGreaterThan(300);

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the start page for an account has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Erste Admin", roles: ["admin"] });
    await show("/");

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the start page for an account whose load failed has none", async () => {
    api.setToken("kka_token");
    vi.spyOn(api, "getMe").mockRejectedValue(new api.ApiError("server", 503, "service_unavailable"));
    const wrapper = await show("/");
    expect(wrapper.find("[role=alert]").exists()).toBe(true);

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the sign-in with a refused token on screen has none", async () => {
    vi.spyOn(api, "checkToken").mockResolvedValue(null);
    const wrapper = await show("/anmelden");
    await wrapper.get("form input").setValue("kka_" + "t".repeat(43));
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find("#login-error").exists()).toBe(true);

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });
});
