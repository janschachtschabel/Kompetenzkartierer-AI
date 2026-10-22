import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type Job, type SourceEntry, type SourcePage } from "@/api";
import { t } from "@/i18n/de";
import SourcesView from "@/views/SourcesView.vue";

function entry(id: string, title: string, overrides: Partial<SourceEntry> = {}): SourceEntry {
  return {
    id,
    title,
    provenance: "upload",
    rights_status: "unklar",
    source_type: null,
    register_status: "acquired",
    country: null,
    sector: null,
    url: null,
    file: { name: `${title}.pdf`, mime: "application/pdf", size: 8, sha256: "ab" },
    mine: true,
    created_at: "2026-10-22T10:00:00Z",
    updated_at: "2026-10-22T10:00:00Z",
    ...overrides,
  };
}

function page(entries: SourceEntry[], total = entries.length, offset = 0): SourcePage {
  return { entries, total, limit: 50, offset };
}

function job(status: Job["status"]): Job {
  return {
    id: "j1",
    kind: "source.fetch",
    status,
    progress: null,
    error_code: null,
    cancel_requested: false,
    attempts: 1,
    max_attempts: 3,
    created_at: "2026-10-22T10:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getInfo").mockResolvedValue({
    name: "Kompetenzkartierer-AI",
    version: "0.1.0",
    public_access: "off",
    max_upload_mb: 50,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the register page", () => {
  it("says it loads, then shows the entries with what they are", async () => {
    vi.spyOn(api, "listSources").mockResolvedValue(
      page([entry("a", "Lehrplan Physik"), entry("b", "Lehrplan Chemie", { provenance: "url", register_status: "unchecked", file: null })]),
    );
    const wrapper = mount(SourcesView);
    expect(wrapper.text()).toContain(t("states.loading"));

    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain("Lehrplan Physik");
    expect(rows[0].text()).toContain(t("sources.provenance.upload"));
    expect(rows[0].text()).toContain(t("sources.status.acquired"));
    expect(rows[0].text()).toContain(t("sources.rights.unklar"));
    expect(rows[0].text()).toContain("22.10.2026");
    expect(rows[1].text()).toContain(t("sources.status.unchecked"));
    expect(rows[1].text()).toContain(t("sources.register.noFile"));
  });

  it("names an entry whose file has not come yet by its address", async () => {
    // an import's title is the file's name, once the fetch has the file
    const address = "https://example.org/lehrplan.pdf";
    vi.spyOn(api, "listSources").mockResolvedValue(page([entry("a", "", { provenance: "url", url: address, file: null })]));
    const wrapper = mount(SourcesView);

    await flushPromises();

    expect(wrapper.get("tbody tr .register__title").text()).toBe(address);
  });

  it("says the register is empty, and how to fill it", async () => {
    vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    const wrapper = mount(SourcesView);

    await flushPromises();

    expect(wrapper.text()).toContain(t("sources.register.emptyTitle"));
    expect(wrapper.find("table").exists()).toBe(false);
  });

  it("says when the register did not load, and loads it again on request", async () => {
    const listed = vi
      .spyOn(api, "listSources")
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue(page([entry("a", "Lehrplan Physik")]));
    const wrapper = mount(SourcesView);
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(t("sources.register.loadFailed"));
    expect(wrapper.get("[role=alert]").text()).toContain(t("refusals.service_unavailable"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(listed).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  });

  it("counts what it shows of all there are, and loads the next page on request", async () => {
    const first = Array.from({ length: 50 }, (_, index) => entry(`a${index}`, `Plan ${index}`));
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(page(first, 51))
      .mockResolvedValue(page([entry("z", "Der letzte")], 51, 50));
    const wrapper = mount(SourcesView);
    await flushPromises();
    expect(wrapper.text()).toContain(t("sources.register.shown", { shown: 50, total: 51 }));

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    expect(listed).toHaveBeenLastCalledWith({}, { offset: 50 });
    expect(wrapper.findAll("tbody tr")).toHaveLength(51);
    expect(wrapper.find("[data-test=more]").exists()).toBe(false);
  });

  it("keeps the entries it has when the next page does not load, and offers to try again", async () => {
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Plan")], 2))
      .mockRejectedValueOnce(new ApiError("network", 0));
    const wrapper = mount(SourcesView);
    await flushPromises();

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    expect(wrapper.get(".page-notice").text()).toContain(t("sources.register.moreFailed"));
  });

  it("reads the register again after an upload", async () => {
    const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    vi.spyOn(api, "uploadSource").mockResolvedValue({
      id: "a",
      title: "Lehrplan",
      provenance: "upload",
      rights_status: "unklar",
      register_status: "acquired",
      file: null,
    });
    const wrapper = mount(SourcesView);
    await flushPromises();
    const input = wrapper.get("#upload-file");
    Object.defineProperty(input.element, "files", { value: [new File(["%PDF"], "a.pdf")], configurable: true });
    await input.trigger("change");

    await wrapper.get("#upload-file").trigger("submit");
    await flushPromises();

    expect(listed).toHaveBeenCalledTimes(2);
  });

  it("follows an import's job and reads the register again once it ended", async () => {
    vi.useFakeTimers();
    const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    vi.spyOn(api, "importSource").mockResolvedValue({
      source: {
        id: "s",
        title: "",
        provenance: "url",
        rights_status: "unklar",
        register_status: "unchecked",
        file: null,
      },
      job_id: "j1",
    });
    vi.spyOn(api, "getJob").mockResolvedValue(job("done"));
    const wrapper = mount(SourcesView);
    await vi.advanceTimersByTimeAsync(0);
    await wrapper.get("#import-url").setValue("https://example.org/lehrplan.pdf");

    await wrapper.get("#import-url").trigger("submit");
    await vi.advanceTimersByTimeAsync(0);
    expect(wrapper.text()).toContain(t("sources.jobs.heading"));
    // its title waits for the file: the job is named by its address
    expect(wrapper.get(".job__label").text()).toBe("https://example.org/lehrplan.pdf");
    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.text()).toContain(t("jobs.status.done"));
    expect(listed).toHaveBeenCalledTimes(3); // on arrival, after the import, after the job
  });

  it("lets an upload through without the limit where the service's facts did not load", async () => {
    vi.spyOn(api, "getInfo").mockRejectedValue(new ApiError("network", 0));
    vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    const wrapper = mount(SourcesView);

    await flushPromises();

    expect(wrapper.get("#upload-file-hint").text()).not.toContain("MB");
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
  });
});
