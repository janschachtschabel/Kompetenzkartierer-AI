import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import RegisterFilter from "@/components/RegisterFilter.vue";
import { t } from "@/i18n/de";
import { router } from "@/router";
import SourcesView from "@/views/SourcesView.vue";

import { entry, page } from "./registerEntries";

beforeEach(() => {
  vi.restoreAllMocks();
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

  it("keeps the shown entries busy-marked while the filter's reading is under way", async () => {
    let answer: (value: api.SourcePage) => void = () => undefined;
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Lehrplan Physik")]))
      .mockImplementation(() => new Promise((resolve) => (answer = resolve)));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("input[type=checkbox]").setValue(true);
    await flushPromises();
    const register = wrapper.get("[aria-labelledby=sources-register]");
    expect(register.attributes("aria-busy")).toBe("true");
    answer(page([entry("b", "Kandidat")]));
    await flushPromises();

    expect(register.attributes("aria-busy")).toBeUndefined();
    expect(wrapper.get("tbody").text()).toContain("Kandidat");
  });
});
