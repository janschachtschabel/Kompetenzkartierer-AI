import { readFileSync } from "node:fs";
import { join } from "node:path";

import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import App from "@/App.vue";
import RegisterFilter from "@/components/RegisterFilter.vue";
import UploadForm from "@/components/UploadForm.vue";
import { t } from "@/i18n/de";
import { router } from "@/router";
import SourcesView from "@/views/SourcesView.vue";

import { deferred, detail, entry, page } from "./registerEntries";
import { SRC, cssRules, stylesOf } from "./sources";

// a page left mounted would follow the next test's address with its own filter, and read
enableAutoUnmount(afterEach);

beforeEach(async () => {
  vi.restoreAllMocks();
  // the filter lives in the address: each test starts unfiltered
  await router.replace({ query: {} });
  vi.spyOn(api, "getInfo").mockResolvedValue({
    name: "Kompetenzkartierer-AI",
    version: "0.1.0",
    public_access: "off",
    max_upload_mb: 50,
  });
});

describe("the register's filter", () => {
  it("names its controls and says what a candidate is", () => {
    const wrapper = mount(RegisterFilter, { props: { modelValue: { candidates: false, status: "" } } });

    const box = wrapper.get<HTMLInputElement>("input[type=checkbox]");
    const hint = wrapper.get(`#${box.attributes("aria-describedby")}`);
    expect(wrapper.get(`label[for=${box.attributes("id")}]`).text()).toBe(t("sources.filter.candidates"));
    expect(hint.text()).toBe(t("sources.filter.candidatesHint"));
    const select = wrapper.get<HTMLSelectElement>("select");
    expect(wrapper.get(`label[for=${select.attributes("id")}]`).text()).toBe(t("sources.filter.status"));
    expect([...select.element.options].map((option) => option.text)).toEqual([
      t("sources.filter.anyStatus"),
      t("sources.status.unchecked"),
      t("sources.status.reachable"),
      t("sources.status.unreachable"),
      t("sources.status.acquired"),
    ]);
  });

  it("hands on each change as a new value", async () => {
    const wrapper = mount(RegisterFilter, { props: { modelValue: { candidates: false, status: "" } } });

    await wrapper.get("input[type=checkbox]").setValue(true);
    await wrapper.setProps({ modelValue: { candidates: true, status: "" } });
    await wrapper.get("select").setValue("unreachable");

    expect(wrapper.emitted("update:modelValue")).toEqual([
      [{ candidates: true, status: "" }],
      [{ candidates: true, status: "unreachable" }],
    ]);
  });
});

describe("the register page's filter", () => {
  it("reads the register again from its first page with what the filter lets through", async () => {
    const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([entry("a", "Lehrplan Physik")], 120));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();
    await wrapper.get("select").setValue("unreachable");
    await flushPromises();
    await wrapper.get("select").setValue("");
    await flushPromises();

    expect(listed.mock.calls).toEqual([
      [{}, { limit: 50 }],
      [{ candidates: true }, { limit: 50 }],
      [{ candidates: true, status: "unreachable" }, { limit: 50 }],
      [{ candidates: true }, { limit: 50 }],
    ]);
  });

  it("asks the next page with the filter, and a new filter from the first page again", async () => {
    const first = page(Array.from({ length: 50 }, (_, index) => entry(`e${index}`, `Plan ${index}`)), 80);
    const second = page(Array.from({ length: 30 }, (_, index) => entry(`f${index}`, `Plan ${50 + index}`)), 80, 50);
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second)
      .mockResolvedValue(first);
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();
    expect(wrapper.findAll("tbody tr")).toHaveLength(80);
    await wrapper.get("input[type=checkbox]").setValue(false);
    await flushPromises();

    expect(listed).toHaveBeenNthCalledWith(3, { candidates: true }, { offset: 50 });
    // not as many as it showed: those were another filter's
    expect(listed).toHaveBeenLastCalledWith({}, { limit: 50 });
  });

  it("says when no entry matches the filter, apart from an empty register, and says it aloud", async () => {
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Lehrplan Physik")]))
      .mockResolvedValue(page([]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();

    expect(wrapper.text()).toContain(t("sources.filter.emptyTitle"));
    expect(wrapper.text()).not.toContain(t("sources.register.emptyTitle"));
    expect(wrapper.get("[data-test=filter-status]").text()).toBe(t("sources.filter.none"));
    // the filter stays, so it can be taken back
    expect(wrapper.get<HTMLInputElement>("input[type=checkbox]").element.checked).toBe(true);
  });

  it.each([
    ["the candidates alone", true, "", t("sources.filter.emptyBody.candidates", { label: t("sources.filter.candidates") })],
    ["a status alone", false, "acquired", t("sources.filter.emptyBody.status", { any: t("sources.filter.anyStatus") })],
    ["both", true, "acquired", t("sources.filter.emptyBody.both", { label: t("sources.filter.candidates") })],
  ])("advises taking back what is set when %s let nothing through", async (_what, candidates, status, advice) => {
    vi.spyOn(api, "listSources").mockResolvedValueOnce(page([entry("a", "Lehrplan Physik")])).mockResolvedValue(page([]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    if (candidates) await wrapper.get("input[type=checkbox]").setValue(true);
    if (status) await wrapper.get("select").setValue(status);
    await flushPromises();

    expect(wrapper.get(".empty__body").text()).toBe(advice);
    // the control's own label, not a copy of it
    if (candidates) expect(advice).toContain(`„${t("sources.filter.candidates")}“`);
  });

  it("says how many it shows once a filter that let nothing through is taken back", async () => {
    const both = page([entry("a", "Lehrplan Physik"), entry("b", "Lehrplan Chemie")], 2);
    vi.spyOn(api, "listSources").mockResolvedValueOnce(both).mockResolvedValueOnce(page([])).mockResolvedValue(both);
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    // on arrival the page says nothing of its own: the count is in the table
    expect(wrapper.get("[data-test=filter-status]").text()).toBe("");
    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();
    expect(wrapper.get("[data-test=filter-status]").text()).toBe(t("sources.filter.none"));

    await wrapper.get("input[type=checkbox]").setValue(false);
    await flushPromises();

    // the table and its count region come back together, and a region inserted with its words is often not read
    expect(wrapper.get("[data-test=filter-status]").text()).toBe(t("sources.register.shown", { shown: 2, total: 2 }));
  });

  it("drops another filter's page when the filter's reading fails, and reads the filter again on request", async () => {
    const uploads = Array.from({ length: 50 }, (_, index) => entry(`u${index}`, `Upload ${index}`));
    const candidates = Array.from({ length: 10 }, (_, index) => entry(`c${index}`, `Kandidat ${index}`));
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(page(uploads, 100))
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(page(candidates, 10));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();
    // no rows of the unfiltered register under the filter's controls, and no further page of them
    expect(wrapper.find("tbody tr").exists()).toBe(false);
    expect(wrapper.find("[data-test=more]").exists()).toBe(false);
    expect(wrapper.get("[role=alert]").text()).toContain(t("sources.register.loadFailed"));
    expect(wrapper.get(".sources__partial").text()).toBe("");

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(listed).toHaveBeenLastCalledWith({ candidates: true }, { limit: 50 });
    expect(wrapper.findAll("tbody tr .register__title").map((title) => title.text())).toEqual(
      candidates.map((candidate) => candidate.title),
    );
  });

  it("says the register is empty, not that nothing matches, until the filter's answer is in", async () => {
    const answer = deferred<api.SourcePage>();
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([]))
      .mockImplementationOnce(() => answer.promise);
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();
    expect(wrapper.text()).toContain(t("sources.register.emptyTitle"));
    expect(wrapper.text()).not.toContain(t("sources.filter.emptyTitle"));
    answer.resolve(page([]));
    await flushPromises();

    expect(wrapper.text()).toContain(t("sources.filter.emptyTitle"));
  });

  it("reads one page when a reload overtakes the filter's reading: what it showed was another filter's", async () => {
    const first = page(Array.from({ length: 50 }, (_, index) => entry(`e${index}`, `Plan ${index}`)), 100);
    const second = page(Array.from({ length: 50 }, (_, index) => entry(`f${index}`, `Plan ${50 + index}`)), 100, 50);
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second)
      .mockImplementationOnce(() => new Promise(() => undefined))
      .mockResolvedValue(page([entry("c", "Kandidat")]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();
    expect(wrapper.findAll("tbody tr")).toHaveLength(100);

    await wrapper.get("input[type=checkbox]").setValue(true);
    wrapper.findComponent(UploadForm).vm.$emit("uploaded", { id: "x" });
    await flushPromises();

    expect(listed).toHaveBeenLastCalledWith({ candidates: true }, { limit: 50 });
    expect(wrapper.get("tbody").text()).toContain("Kandidat");
  });

  it("keeps the shown entries busy-marked while the filter's reading is under way, and only them", async () => {
    let answer: (value: api.SourcePage) => void = () => undefined;
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Lehrplan Physik")]))
      .mockImplementation(() => new Promise((resolve) => (answer = resolve)));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();
    const results = wrapper.get(".sources__results");
    expect(results.attributes("aria-busy")).toBe("true");
    expect(results.find("table").exists()).toBe(true);
    // the controls and the regions that speak stay outside: a busy region's changes wait to be read
    for (const outside of ["fieldset", "[data-test=filter-status]", ".sources__partial"]) {
      expect(wrapper.get(outside).element.closest("[aria-busy]"), outside).toBeNull();
    }
    answer(page([entry("b", "Kandidat")]));
    await flushPromises();

    expect(results.attributes("aria-busy")).toBeUndefined();
    expect(wrapper.get("tbody").text()).toContain("Kandidat");
  });

  it("shows the reading too: the busy results fade by the token the contrast check holds", () => {
    const source = readFileSync(join(SRC, "views", "SourcesView.vue"), "utf8");

    const busy = cssRules(stylesOf(source)).filter(({ selectors }) =>
      selectors.includes('.sources__results[aria-busy="true"]'),
    );

    expect(busy.map(({ body }) => body).join("")).toMatch(/opacity:\s*var\(--busy-opacity\)/);
  });
});

describe("the register page's filter in the address", () => {
  it("is read on arrival, so the way back finds the register as it was filtered", async () => {
    await router.replace({ query: { kandidaten: "1", stand: "unreachable" } });
    const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([entry("c", "Kandidat")]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    expect(listed.mock.calls).toEqual([[{ candidates: true, status: "unreachable" }, { limit: 50 }]]);
    expect(wrapper.get<HTMLInputElement>("input[type=checkbox]").element.checked).toBe(true);
    expect(wrapper.get<HTMLSelectElement>("select").element.value).toBe("unreachable");
  });

  it("is kept in the address as it changes, without a step for the way back each time", async () => {
    vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    const pushed = vi.spyOn(router, "push");
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("input[type=checkbox]").setValue(true);
    await wrapper.get("select").setValue("acquired");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({ kandidaten: "1", stand: "acquired" });
    await wrapper.get("input[type=checkbox]").setValue(false);
    await wrapper.get("select").setValue("");
    await flushPromises();

    expect(router.currentRoute.value.query).toEqual({});
    expect(pushed).not.toHaveBeenCalled();
  });

  it("leaves the address to the entry's page the reader goes on to", async () => {
    api.setToken("kka_token");
    try {
      await router.push({ name: "sources", query: { kandidaten: "1" } });
      vi.spyOn(api, "getMe").mockResolvedValue({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });
      const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([entry("a", "Lehrplan Physik")]));
      vi.spyOn(api, "getSource").mockResolvedValue(detail());
      mount(App, { global: { plugins: [router] }, attachTo: document.body });
      await flushPromises();

      await router.push({ name: "source", params: { id: "a" } });
      await flushPromises();

      expect(router.currentRoute.value.fullPath).toBe("/quellen/a");
      expect(listed).toHaveBeenCalledTimes(1);
    } finally {
      api.clearToken();
      await router.push("/");
      document.body.innerHTML = "";
    }
  });

  it("follows the address when it changes from elsewhere: the navigation's link to the register", async () => {
    await router.replace({ query: { kandidaten: "1" } });
    const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([entry("a", "Lehrplan Physik")]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await router.push({ query: {} });
    await flushPromises();

    expect(wrapper.get<HTMLInputElement>("input[type=checkbox]").element.checked).toBe(false);
    expect(listed).toHaveBeenLastCalledWith({}, { limit: 50 });
  });
});
