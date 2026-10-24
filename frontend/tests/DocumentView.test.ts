import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type Job, type Run } from "@/api";
import { t } from "@/i18n/de";
import { router } from "@/router";
import DocumentView from "@/views/DocumentView.vue";

import { violations } from "./axe";

let shown: VueWrapper | null = null;

function document_(changes: Partial<CurriculumDocument> = {}): CurriculumDocument {
  return {
    id: "d1",
    source_id: "s1",
    conversion_id: "c1",
    own: true,
    title: "Kernlehrplan Physik",
    document_type_iri: null,
    sector: "school",
    regions: ["DE-NW"],
    created_at: "2026-10-24T10:00:00Z",
    extraction: { job_id: "j1", status: "done" },
    ...changes,
  };
}

function job(status: Job["status"]): Job {
  return {
    id: "j2",
    kind: "extract.run",
    status,
    progress: null,
    error_code: null,
    cancel_requested: false,
    attempts: 0,
    max_attempts: 3,
    created_at: "2026-10-24T12:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

const RUNS: Run[] = [
  { stage: "X1", attempt: 1, state: "done", started_at: "2026-10-24T10:01:00Z", finished_at: "2026-10-24T10:03:00Z", failure: null },
  { stage: "X2", attempt: 1, state: "abandoned", started_at: "2026-10-24T10:03:00Z", finished_at: null, failure: null },
];

async function open(id = "d1"): Promise<VueWrapper> {
  shown = mount(DocumentView, { props: { id }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getJob").mockResolvedValue(job("queued"));
});

afterEach(() => {
  shown?.unmount();
  shown = null;
});

describe("a document's page", () => {
  it("names the document, what it is for, and how its stages ran", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(wrapper.get("h1").text()).toBe("Kernlehrplan Physik");
    expect(wrapper.text()).toContain(t("documents.sectors.school"));
    expect(wrapper.text()).toContain("Nordrhein-Westfalen");
    expect(wrapper.get("a[data-test=document-source]").attributes("href")).toBe("/quellen/s1");
    const rows = wrapper.findAll("tbody tr").map((row) => row.findAll("td").map((cell) => cell.text()));
    expect(rows.map((cells) => [cells[0], cells[1], cells[2]])).toEqual([
      [t("documents.stages.X1"), "1", t("documents.runStates.done")],
      [t("documents.stages.X2"), "1", t("documents.runStates.abandoned")],
    ]);
  });

  it("names a document without a title as such", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ title: null, extraction: null }));
    vi.spyOn(api, "getRuns").mockResolvedValue([]);

    const wrapper = await open();

    expect(wrapper.get("h1").text()).toBe(t("documents.untitled"));
    expect(wrapper.text()).toContain(t("documents.page.noRuns"));
  });

  it("follows the extraction waiting or running, and offers no new start beside it", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { job_id: "j1", status: "running" } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(wrapper.findComponent({ name: "JobProgress" }).props("jobId")).toBe("j1");
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(false);
  });

  it("starts the extraction again where it ended, and follows the new one", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { job_id: "j1", status: "cancelled" } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const start = vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    const wrapper = await open();
    expect(wrapper.text()).toContain(t("documents.page.lastStatus", { status: t("jobs.status.cancelled") }));

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();

    expect(start).toHaveBeenCalledWith("d1");
    expect(wrapper.findComponent({ name: "JobProgress" }).props("jobId")).toBe("j2");
  });

  it("says a start refused in its own words", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "startExtraction").mockRejectedValue(new ApiError("server", 429, "too_many_starts"));
    const wrapper = await open();

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(t("refusals.too_many_starts"));
  });

  it("offers another's document no start", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ own: false }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(false);
    expect(wrapper.text()).toContain(t("documents.page.notOwn"));
  });

  it("says a document it does not find, and one that did not load with a retry", async () => {
    vi.spyOn(api, "getRuns").mockResolvedValue([]);
    const get = vi.spyOn(api, "getDocument").mockRejectedValueOnce(new ApiError("server", 404, "no_document"));
    const missing = await open();
    // the state of no document, not a failure: nothing to try again
    expect(missing.get("h2").text()).toBe(t("documents.page.notFoundTitle"));
    expect(missing.find("[role=alert]").exists()).toBe(false);
    shown?.unmount();

    get.mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable")).mockResolvedValue(document_());
    const wrapper = await open();
    expect(wrapper.text()).toContain(t("documents.page.loadFailed"));
    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();
    expect(wrapper.get("h1").text()).toBe("Kernlehrplan Physik");
  });

  it("has nothing axe finds", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(await violations(wrapper.html())).toEqual([]);
  });
});
