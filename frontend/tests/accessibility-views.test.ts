/**
 * axe over the pages as they are shown: the shell with its routed page, for a
 * visitor and for an account, and the sign-in with a refusal on screen.
 */
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import App from "@/App.vue";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";

import { describeViolations, violations } from "./axe";

async function page(path: string): Promise<string> {
  await router.push(path);
  const wrapper = mount(App, { global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  const html = wrapper.html();
  wrapper.unmount();
  return html;
}

beforeEach(() => {
  vi.restoreAllMocks();
  api.clearToken();
  clearSession();
  vi.spyOn(api, "getInfo").mockResolvedValue({ name: "Kompetenzkartierer-AI", version: "0.1.0", public_access: "lookup" });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("accessibility of the pages", () => {
  it("the start page for a visitor has none", async () => {
    const html = await page("/");
    expect(html.length).toBeGreaterThan(300);

    const found = await violations(html);

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the start page for an account has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Erste Admin", roles: ["admin"] });

    const found = await violations(await page("/"));

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the sign-in with a refused token on screen has none", async () => {
    vi.spyOn(api, "checkToken").mockResolvedValue(null);
    await router.push("/anmelden");
    const wrapper = mount(App, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();
    await wrapper.get("form input").setValue("kka_" + "t".repeat(43));
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find("#login-error").exists()).toBe(true);
    // unmounted first: axe checks a copy in the same document, and two shells would be two of each landmark
    const html = wrapper.html();
    wrapper.unmount();

    const found = await violations(html);

    expect(found, describeViolations(found)).toEqual([]);
  });
});
