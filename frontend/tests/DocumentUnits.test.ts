import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type Unit } from "@/api";
import DocumentUnits from "@/components/DocumentUnits.vue";
import { t } from "@/i18n/de";

import { violations } from "./axe";

let shown: VueWrapper | null = null;

const UNITS: Unit[] = [
  { key: "E0", path: [], pages: [1, 1], state: "frame", statements: null },
  { key: "E1", path: ["Kompetenzen"], pages: [2, 3], state: "done", statements: 3 },
  { key: "E2", path: ["Kompetenzen", "Optik"], pages: [4, 4], state: "open", statements: null },
  { key: "E3", path: ["Anhang"], pages: [5, 9], state: "none", statements: null },
];

function open(refresh = 0): VueWrapper {
  shown = mount(DocumentUnits, { props: { documentId: "d1", refresh }, attachTo: document.body });
  return shown;
}

function rows(wrapper: VueWrapper): string[][] {
  return wrapper.findAll("tbody tr").map((row) => row.findAll("td").map((cell) => cell.text()));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("a document's work packages", () => {
  it("lists each with its section, its pages and how far the extraction has come with it", async () => {
    const asked = vi.spyOn(api, "getUnits").mockResolvedValue(UNITS);

    const wrapper = open();
    await flushPromises();

    expect(asked).toHaveBeenCalledWith("d1");
    expect(rows(wrapper)).toEqual([
      ["E0", t("documents.units.titlePages"), t("documents.units.page", { first: 1 }), t("documents.units.states.frame")],
      ["E1", "Kompetenzen", t("documents.units.pages", { first: 2, last: 3 }), t("documents.units.states.done", { statements: 3 })],
      ["E2", "Kompetenzen / Optik", t("documents.units.page", { first: 4 }), t("documents.units.states.open")],
      ["E3", "Anhang", t("documents.units.pages", { first: 5, last: 9 }), t("documents.units.states.none")],
    ]);
    expect(wrapper.get("[data-test=units-summary]").text()).toBe(t("documents.units.summary", { done: 1, total: 2 }));
  });

  it("names the one package of a document without headings as the whole document", async () => {
    vi.spyOn(api, "getUnits").mockResolvedValue([{ key: "E1", path: [], pages: [1, 3], state: "open", statements: null }]);

    const wrapper = open();
    await flushPromises();

    expect(rows(wrapper)[0][1]).toBe(t("documents.units.wholeDocument"));
  });

  it("says that the packages are not set before the document is parted", async () => {
    vi.spyOn(api, "getUnits").mockResolvedValue([]);

    const wrapper = open();
    await flushPromises();

    expect(wrapper.find("table").exists()).toBe(false);
    expect(wrapper.text()).toContain(t("documents.units.noneTitle"));
    expect(wrapper.find("[data-test=units-summary]").exists()).toBe(false);
  });

  it("says that they did not load, and loads them again when asked", async () => {
    const asked = vi
      .spyOn(api, "getUnits")
      .mockRejectedValueOnce(new ApiError("server", 503, "db_unavailable"))
      .mockResolvedValue(UNITS);

    const wrapper = open();
    await flushPromises();
    expect(wrapper.text()).toContain(t("documents.units.loadFailed"));
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(asked).toHaveBeenCalledTimes(2);
    expect(rows(wrapper)).toHaveLength(4);
  });

  it("reads them again when the extraction moves on, keeping the ones shown meanwhile", async () => {
    let answer: (units: Unit[]) => void = () => undefined;
    const later = new Promise<Unit[]>((resolve) => (answer = resolve));
    vi.spyOn(api, "getUnits").mockResolvedValueOnce(UNITS).mockReturnValueOnce(later);
    const wrapper = open();
    await flushPromises();

    await wrapper.setProps({ refresh: 1 });
    expect(rows(wrapper)).toHaveLength(4); // the list stays while the next one is on its way
    answer(UNITS.map((unit) => (unit.key === "E2" ? { ...unit, state: "done" as const, statements: 5 } : unit)));
    await flushPromises();

    expect(rows(wrapper)[2][3]).toBe(t("documents.units.states.done", { statements: 5 }));
    expect(wrapper.get("[data-test=units-summary]").text()).toBe(t("documents.units.summary", { done: 2, total: 2 }));
  });

  it("keeps the list it shows where a later reading fails, and says so beside it", async () => {
    vi.spyOn(api, "getUnits").mockResolvedValueOnce(UNITS).mockRejectedValue(new TypeError("Failed to fetch"));
    const wrapper = open();
    await flushPromises();

    await wrapper.setProps({ refresh: 1 });
    await flushPromises();

    expect(rows(wrapper)).toHaveLength(4);
    expect(wrapper.text()).toContain(t("documents.units.loadFailed"));
  });

  it("shows the waiting again for a retry of the first reading, and its failure once more", async () => {
    let fail: (error: Error) => void = () => undefined;
    vi.spyOn(api, "getUnits")
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockReturnValueOnce(new Promise<Unit[]>((_, reject) => (fail = reject)));
    const wrapper = open();
    await flushPromises();

    await wrapper.get("button").trigger("click");
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
    expect(wrapper.text()).toContain(t("documents.units.loading"));
    fail(new TypeError("Failed to fetch"));
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.units.loadFailed"));
  });

  it("says a later reading's failure anew when a retry fails again", async () => {
    vi.spyOn(api, "getUnits").mockResolvedValueOnce(UNITS).mockRejectedValue(new TypeError("Failed to fetch"));
    const wrapper = open();
    await flushPromises();
    await wrapper.setProps({ refresh: 1 });
    await flushPromises();
    const notice = () => wrapper.get(".page-notice__text").element.textContent;
    const first = notice();

    await wrapper.get(".page-notice button").trigger("click");
    await flushPromises();

    expect(notice()).not.toBe(first); // the same words, changed for the eye's unseen: read out again
    expect(notice()?.trim()).toBe(first?.trim());
    await wrapper.setProps({ refresh: 2 }); // readings as the extraction moves on: the retry was answered
    await flushPromises();
    const later = notice();
    await wrapper.setProps({ refresh: 3 });
    await flushPromises();

    expect(notice()).toBe(later); // not said again
  });

  it("takes the keyboard to the section's heading once a retry brought the list", async () => {
    vi.spyOn(api, "getUnits").mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValue(UNITS);
    const wrapper = open();
    await flushPromises();
    const retry = wrapper.get("button").element as HTMLElement;
    retry.focus();

    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(document.activeElement).toBe(wrapper.get("#document-units").element);
  });

  it("leaves a retry a later reading overtook to that reading: no failure said, the keyboard to the heading", async () => {
    let failRetry: (error: Error) => void = () => undefined;
    let answerLater: (units: Unit[]) => void = () => undefined;
    vi.spyOn(api, "getUnits")
      .mockResolvedValueOnce(UNITS)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockReturnValueOnce(new Promise<Unit[]>((_, reject) => (failRetry = reject)))
      .mockReturnValueOnce(new Promise<Unit[]>((resolve) => (answerLater = resolve)));
    const wrapper = open();
    await flushPromises();
    await wrapper.setProps({ refresh: 1 });
    await flushPromises();
    const notice = () => wrapper.get(".page-notice__text").element.textContent;
    const first = notice();
    const retry = wrapper.get(".page-notice button");
    (retry.element as HTMLElement).focus();

    await retry.trigger("click");
    await wrapper.setProps({ refresh: 2 }); // the extraction moved on while the retry asked
    failRetry(new TypeError("Failed to fetch"));
    await flushPromises();

    expect(notice()).toBe(first); // the retry's answer was dropped: nothing is said again
    answerLater([...UNITS]); // a reading's own list, as every answer brings
    await flushPromises();

    expect(wrapper.text()).not.toContain(t("documents.units.loadFailed"));
    expect(document.activeElement).toBe(wrapper.get("#document-units").element);
  });

  it("says a failure anew for a retry a later reading answered first, and leaves the keyboard be", async () => {
    let failRetry: (error: Error) => void = () => undefined;
    vi.spyOn(api, "getUnits")
      .mockResolvedValueOnce(UNITS)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockReturnValueOnce(new Promise<Unit[]>((_, reject) => (failRetry = reject)))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce([...UNITS]);
    const wrapper = open();
    await flushPromises();
    await wrapper.setProps({ refresh: 1 });
    await flushPromises();
    const notice = () => wrapper.get(".page-notice__text").element.textContent;
    const first = notice();
    const retry = wrapper.get(".page-notice button");
    (retry.element as HTMLElement).focus();

    await retry.trigger("click");
    await wrapper.setProps({ refresh: 2 }); // the extraction moved on: its reading fails as the retry's would
    await flushPromises();

    expect(notice()).not.toBe(first); // the same words, said again for the retry
    expect(notice()?.trim()).toBe(first?.trim());
    failRetry(new TypeError("Failed to fetch"));
    await wrapper.setProps({ refresh: 3 }); // a later reading brings the list: the retry was answered before
    await flushPromises();

    expect(wrapper.text()).not.toContain(t("documents.units.loadFailed"));
    expect(document.activeElement).not.toBe(wrapper.get("#document-units").element);
  });

  it("drops an answer that came after a later one", async () => {
    let first: (units: Unit[]) => void = () => undefined;
    vi.spyOn(api, "getUnits")
      .mockReturnValueOnce(new Promise<Unit[]>((resolve) => (first = resolve)))
      .mockResolvedValue(UNITS);
    const wrapper = open();

    await wrapper.setProps({ refresh: 1 });
    await flushPromises();
    first([]);
    await flushPromises();

    expect(rows(wrapper)).toHaveLength(4);
  });

  it("has nothing axe finds", async () => {
    vi.spyOn(api, "getUnits").mockResolvedValue(UNITS);

    const wrapper = open();
    await flushPromises();

    expect(await violations(wrapper.html())).toEqual([]);
  });
});

describe("a document's units whose entry is no longer the reader's", () => {
  it("says so, with no retry that could change it", async () => {
    vi.spyOn(api, "getUnits").mockRejectedValue(new ApiError("forbidden", 403, "file_hidden"));

    const wrapper = open();
    await flushPromises();

    expect(wrapper.text()).toContain(t("refusals.file_hidden"));
    expect(wrapper.findAll("button").some((button) => button.text() === t("states.retry"))).toBe(false);
  });
});
