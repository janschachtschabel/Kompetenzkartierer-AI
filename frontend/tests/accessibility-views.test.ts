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
import { t } from "@/i18n/de";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";

import { describeViolations, pageViolations } from "./axe";
import { detail } from "./registerEntries";

let shown: VueWrapper | null = null;

const ENTRY: api.SourceEntry = {
  id: "s1",
  title: "Lehrplan Physik",
  provenance: "url",
  rights_status: "unklar",
  source_type: null,
  register_status: "acquired",
  country: "DE-BY",
  sector: null,
  url: "https://example.org/lehrplan.pdf",
  file: { name: "lehrplan.pdf", mime: "application/pdf", size: 8, sha256: "ab" },
  mine: true,
  created_at: "2026-10-22T10:00:00Z",
  updated_at: "2026-10-22T10:00:00Z",
};

const FAILED_JOB: api.Job = {
  id: "j1",
  kind: "source.fetch",
  status: "failed",
  progress: null,
  error_code: "download_refused",
  cancel_requested: false,
  attempts: 1,
  max_attempts: 3,
  created_at: "2026-10-22T10:00:00Z",
  started_at: null,
  finished_at: null,
};

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
  vi.spyOn(api, "getInfo").mockResolvedValue({ name: "Kompetenzkartierer-AI", version: "0.1.0", public_access: "lookup", max_upload_mb: 50 });
});

afterEach(() => {
  // a test that faked the clock and failed early must not leave it to the next one's axe
  vi.useRealTimers();
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

  it("the register with its entries, a failed fetch and a page that did not load has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce({ entries: [ENTRY], total: 2, limit: 50, offset: 0 })
      .mockResolvedValueOnce({ entries: [ENTRY], total: 2, limit: 50, offset: 0 })
      .mockRejectedValue(new api.ApiError("network", 0));
    vi.spyOn(api, "importSource").mockResolvedValue({ source: { ...ENTRY, file: null }, job_id: "j1" });
    vi.spyOn(api, "getJob").mockResolvedValue(FAILED_JOB);
    // the job's first question is a second away; flushPromises runs on setImmediate, left real
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const wrapper = await show("/quellen");
    await wrapper.get("#import-url").setValue("https://example.org/lehrplan.pdf");
    await wrapper.get("#import-url").trigger("submit");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(1000);
    vi.useRealTimers(); // axe keeps its own time
    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();
    expect(wrapper.find("tbody tr").exists()).toBe(true);
    expect(wrapper.text()).toContain(t("jobs.failures.download_refused"));
    expect(wrapper.get(".sources__partial").text()).toContain(t("sources.register.moreFailed"));

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the register with refusals in both forms and no entries has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });
    vi.spyOn(api, "listSources").mockResolvedValue({ entries: [], total: 0, limit: 50, offset: 0 });
    const wrapper = await show("/quellen");
    await wrapper.get("#upload-file").trigger("submit");
    await wrapper.get("#import-url").trigger("submit");
    await flushPromises();
    expect(wrapper.find("#upload-error").exists()).toBe(true);
    expect(wrapper.find("#import-error").exists()).toBe(true);

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the register that did not load has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });
    vi.spyOn(api, "listSources").mockRejectedValue(new api.ApiError("server", 503, "service_unavailable"));
    const wrapper = await show("/quellen");
    expect(wrapper.find("[role=alert]").exists()).toBe(true);

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("the register of an admin, filtered to nothing, with the check's question open, has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Erste Admin", roles: ["admin"] });
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce({ entries: [ENTRY], total: 1, limit: 50, offset: 0 })
      .mockResolvedValue({ entries: [], total: 0, limit: 50, offset: 0 });
    const wrapper = await show("/quellen");
    await wrapper.get("#register-candidates").setValue(true);
    await flushPromises();
    await wrapper.get("[data-test=check-start]").trigger("click");
    expect(wrapper.text()).toContain(t("sources.filter.emptyTitle"));
    expect(wrapper.find("[role=dialog]").exists()).toBe(true);

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("an entry's page with its rights, its file's fetch, what the seed said, the check found and the notes tell has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });
    const chain = ["https://lehrplaene.bildung-rp.de/physik", "https://lehrplaene.bildung-rp.de/dateien/physik.pdf"];
    vi.spyOn(api, "getSource").mockResolvedValue(
      detail({
        license: "CC BY 4.0",
        rights_evidence: "Lizenzhinweis auf der Portalseite",
        acquisitions: [{ method: "url", acquired_at: "2026-10-22T11:00:00Z", chain, received_name: "physik.pdf" }],
      }),
    );
    const wrapper = await show("/quellen/s1");
    expect(wrapper.find("#source-notes").exists()).toBe(true);
    expect(wrapper.find("#source-acquisitions").exists()).toBe(true);

    const found = await pageViolations();

    expect(found, describeViolations(found)).toEqual([]);
  });

  it("an entry's page for an entry that is not there has none", async () => {
    api.setToken("kka_token");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });
    vi.spyOn(api, "getSource").mockRejectedValue(new api.ApiError("server", 404, "not_found"));
    const wrapper = await show("/quellen/s1");
    expect(wrapper.text()).toContain(t("entryPage.notFoundTitle"));

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
