import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type FindingsPage, type Job, type Run } from "@/api";
import { isolate } from "@/bidi";
import { t } from "@/i18n/de";
import { jobFailureText } from "@/jobMessages";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";
import DocumentView from "@/views/DocumentView.vue";

import { violations } from "./axe";
import { documentOf } from "./documentFixtures";

let shown: VueWrapper | null = null;

function document_(changes: Partial<CurriculumDocument> = {}): CurriculumDocument {
  return documentOf({
    title: "Kernlehrplan Physik",
    created_at: "2026-10-24T10:00:00Z",
    extraction: { kind: "extract.run", job_id: "j1", status: "done", error_code: null },
    ...changes,
  });
}

const NO_FINDINGS: FindingsPage = { counts: { violation: 0, warning: 0, info: 0 }, findings: [], truncated: false, repairable: [] };
const REPAIRABLE: FindingsPage = {
  counts: { violation: 1, warning: 0, info: 0 },
  findings: [
    {
      rule: "x5.wording_not_found",
      severity: "violation",
      stage: "X5",
      focus: { kind: "statement", id: "s1", label: "Die Lernenden messen." },
      path: null,
      message: "the wording is not in the blocks its anchor names",
      message_lang: null,
      unit: null,
    },
  ],
  truncated: false,
  repairable: ["E1"],
};

function job(status: Job["status"], id = "j2"): Job {
  return {
    id,
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
  vi.spyOn(api, "getUnits").mockResolvedValue([]);
  vi.spyOn(api, "getFindings").mockResolvedValue(NO_FINDINGS);
});

/** The extraction's job running at a step it reports. */
function at(code: string, params: Record<string, number> = {}): Job {
  return { ...job("running", "j1"), progress: { code, params } };
}

afterEach(() => {
  shown?.unmount();
  shown = null;
  vi.useRealTimers();
  document.body.innerHTML = "";
  window.history.replaceState({ ...window.history.state, ledToRunning: undefined, copied: undefined }, "");
  clearSession();
});

function ledHere(): void {
  window.history.replaceState({ ...window.history.state, ledToRunning: true }, "");
}

const extraction = (wrapper: VueWrapper) => wrapper.get("section[aria-labelledby=document-extraction]");
const extractionStatus = (wrapper: VueWrapper) => extraction(wrapper).get("[data-test=extraction-status]").text();

describe("a document's page", () => {
  it("names the document, what it is for, and how its stages ran", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(wrapper.get("h1").text()).toBe("Kernlehrplan Physik");
    expect(wrapper.text()).toContain(t("documents.sectors.school"));
    expect(wrapper.text()).toContain("Nordrhein-Westfalen");
    expect(wrapper.get("a[data-test=document-source]").attributes("href")).toBe("/quellen/s1");
    // its nodes and statements on a page of their own
    expect(wrapper.get("a[data-test=document-tree]").attributes("href")).toBe("/dokumente/d1/baum");
    expect(wrapper.get("a[data-test=document-tree]").text()).toBe(t("documents.page.treeLink"));
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
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(wrapper.findComponent({ name: "JobProgress" }).props("jobId")).toBe("j1");
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(false);
  });

  it("starts the extraction again where it ended, and follows the new one", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const start = vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    const wrapper = await open();
    expect(wrapper.text()).toContain(t("documents.page.lastStatus", { status: t("jobs.status.cancelled") }));

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();

    expect(start).toHaveBeenCalledWith("d1");
    expect(wrapper.findComponent({ name: "JobProgress" }).props("jobId")).toBe("j2");
  });

  it("names a repair a start gave back as one, and says that it runs already", async () => {
    // a repair started meanwhile (in another tab): the start follows it, by its own kind
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const repairing = { ...job("running", "j9"), kind: "extract.repair" };
    vi.spyOn(api, "startExtraction").mockResolvedValue(repairing);
    vi.mocked(api.getJob).mockResolvedValue(repairing);
    const wrapper = await open();

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();

    expect(extraction(wrapper).get(".job__label").text()).toBe(t("documents.page.repairLabel"));
    expect(extractionStatus(wrapper)).toBe(t("documents.page.repairRunning"));
  });

  it("says a check the start met as one, by its own kind", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const checking = { ...job("running", "j9"), kind: "extract.check" };
    vi.spyOn(api, "startExtraction").mockResolvedValue(checking);
    vi.mocked(api.getJob).mockResolvedValue(checking);
    const wrapper = await open();

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();

    expect(extraction(wrapper).get(".job__label").text()).toBe(t("documents.page.checkLabel"));
    expect(extractionStatus(wrapper)).toBe(t("documents.page.checkRunning"));
  });

  it("offers no extraction to start for a frozen document or a draft copy, saying why", async () => {
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" }));
    const frozen = await open();
    expect(frozen.find("[data-test=extraction-resume]").exists()).toBe(false);
    expect(extraction(frozen).text()).toContain(t("documents.page.frozenNoExtraction"));
    frozen.unmount();

    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ copy_of: "d0", revision: 2, extraction: null }));
    const copy = await open();
    expect(copy.find("[data-test=extraction-resume]").exists()).toBe(false);
    expect(extraction(copy).text()).toContain(t("documents.page.copyNoExtraction"));
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

  it("shows the document's work packages and its findings between its extraction and its runs", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getUnits).mockResolvedValue([
      { key: "E1", path: ["Kompetenzen"], pages: [2, 3], state: "done", statements: 3 },
    ]);

    const wrapper = await open();

    const headings = wrapper.findAll("h2").map((heading) => heading.attributes("id"));
    expect(headings).toEqual([
      "document-facts",
      "document-edition",
      "document-extraction",
      "document-units",
      "document-findings",
      "document-runs",
    ]);
    expect(wrapper.get("section[aria-labelledby=document-units]").text()).toContain("Kompetenzen");
  });

  it("reads the work packages and the findings again as the extraction moves on", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getJob)
      .mockResolvedValueOnce(at("extract_statements", { done: 0, total: 2 }))
      .mockResolvedValue(at("extract_statements", { done: 1, total: 2 }));
    await open();
    expect(api.getUnits).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(2000);
    await flushPromises();

    expect(api.getUnits).toHaveBeenCalledTimes(3); // once a step reported: the first, then the next
    expect(api.getFindings).toHaveBeenCalledTimes(3);
  });

  it("says each step the extraction moves to, once, and not each package it counts", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getJob)
      .mockResolvedValueOnce(at("extract_frame"))
      .mockResolvedValueOnce(at("extract_statements", { done: 0, total: 2 }))
      .mockResolvedValue(at("extract_statements", { done: 1, total: 2 }));
    const wrapper = await open();

    await vi.advanceTimersByTimeAsync(1000);
    expect(extractionStatus(wrapper)).toBe(t("jobs.progress.extract_frame"));
    await vi.advanceTimersByTimeAsync(2000);
    const statements = t("jobs.progress.extract_statements", { done: 0, total: 2 });
    expect(extractionStatus(wrapper)).toBe(statements);
    await vi.advanceTimersByTimeAsync(4000);

    expect(extractionStatus(wrapper)).toBe(statements); // the count shows in the job, not said
  });

  it("says the first step of a job started again, though the one before ended on that step", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }))
      .mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "failed", error_code: "budget_exhausted" } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const statements = at("extract_statements", { done: 1, total: 2 });
    let asked = 0;
    vi.mocked(api.getJob).mockImplementation((id) =>
      Promise.resolve(
        id === "j2"
          ? { ...statements, id: "j2" }
          : asked++ === 0
            ? statements
            : { ...statements, status: "failed" as const, error_code: "budget_exhausted" },
      ),
    );
    vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    const wrapper = await open();
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(2000);
    await flushPromises();

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(1000);

    expect(extractionStatus(wrapper)).toBe(t("jobs.progress.extract_statements", { done: 1, total: 2 }));
  });

  it("says why the last extraction failed, to an editor too", async () => {
    const failed = { kind: "extract.run", job_id: null, status: "failed" as const, error_code: "budget_exhausted" };
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ own: false, extraction: failed }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    const note = extraction(wrapper).get("[data-test=extraction-last]").text();
    expect(note).toBe(
      `${t("documents.page.lastStatus", { status: t("jobs.status.failed") })}. ${jobFailureText("budget_exhausted")}`,
    );
  });

  it("says no reason for an extraction that did not fail", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(extraction(wrapper).get("[data-test=extraction-last]").text()).toBe(
      t("documents.page.lastStatus", { status: t("jobs.status.done") }),
    );
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

describe("a document's extraction followed on its page", () => {
  it("is read by an editor from the document while it runs, the job not theirs to follow", async () => {
    vi.useFakeTimers();
    const running = document_({ own: false, extraction: { kind: "extract.run", job_id: null, status: "running", error_code: null } });
    const get = vi
      .spyOn(api, "getDocument")
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running)
      .mockResolvedValue(document_({ own: false, extraction: { kind: "extract.run", job_id: null, status: "done", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const getJob = vi.spyOn(api, "getJob");

    const wrapper = await open();

    expect(wrapper.findComponent({ name: "JobProgress" }).exists()).toBe(false);
    expect(extraction(wrapper).text()).toContain(t("documents.page.lastStatus", { status: t("jobs.status.running") }));
    expect(extraction(wrapper).text()).toContain(t("documents.page.following"));
    await vi.advanceTimersByTimeAsync(1000); // still running
    await vi.advanceTimersByTimeAsync(2000); // done: the page is read again
    await flushPromises();
    expect(get.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(extraction(wrapper).text()).toContain(t("documents.page.lastStatus", { status: t("jobs.status.done") }));
    expect(getJob).not.toHaveBeenCalled();
    expect(extraction(wrapper).text()).not.toContain(t("jobs.goneReasons.not_found"));
  });

  it("goes on asking after the document when its job is gone from the reader", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));

    const wrapper = await open();
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(wrapper.findComponent({ name: "JobProgress" }).exists()).toBe(false);
    expect(extraction(wrapper).text()).toContain(t("documents.page.following"));
  });

  it("shows how the extraction ended, the new runs and the way to go on, and says so", async () => {
    vi.useFakeTimers();
    const get = vi
      .spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }))
      .mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "failed", error_code: null } }));
    const later: Run[] = [...RUNS, { ...RUNS[1], attempt: 2, state: "failed", failure: "LeaseLost" }];
    vi.spyOn(api, "getRuns").mockResolvedValueOnce(RUNS).mockResolvedValue(later);
    vi.spyOn(api, "getJob").mockResolvedValue({ ...job("failed", "j1"), error_code: "model_not_configured" });
    const wrapper = await open();
    (wrapper.get(".job__line").element as HTMLElement).focus(); // the keyboard rests in the job

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(get).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
    expect(extraction(wrapper).text()).toContain(t("documents.page.lastStatus", { status: t("jobs.status.failed") }));
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(true);
    const said = t("jobs.announce", { label: isolate(t("documents.page.jobLabel")), status: t("jobs.status.failed") });
    expect(extractionStatus(wrapper)).toBe(`${said}. ${jobFailureText("model_not_configured")}`);
    expect(document.activeElement).toBe(wrapper.get("#document-extraction").element);
  });

  it("takes the keyboard to the extraction's heading once the start's button has gone, and says it started", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    const wrapper = await open();
    const button = wrapper.get("[data-test=extraction-resume]");
    (button.element as HTMLButtonElement).focus();

    await button.trigger("click");
    await flushPromises();

    expect(document.activeElement).toBe(wrapper.get("#document-extraction").element);
    expect(extractionStatus(wrapper)).toBe(t("documents.page.started"));
  });

  it("offers the start again once the extraction it started has ended", async () => {
    vi.useFakeTimers();
    const ended = document_({ extraction: { kind: "extract.run", job_id: "j2", status: "done", error_code: null } });
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }))
      .mockResolvedValue(ended);
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    vi.spyOn(api, "getJob").mockResolvedValue(job("done"));
    const wrapper = await open();

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(wrapper.findComponent({ name: "JobProgress" }).exists()).toBe(false);
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(true);
  });

  it("starts once however often its button is pressed while the start is on its way", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const start = vi.spyOn(api, "startExtraction").mockReturnValue(new Promise<Job>(() => undefined));
    const wrapper = await open();

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await wrapper.get("[data-test=extraction-resume]").trigger("click");

    expect(start).toHaveBeenCalledTimes(1);
  });

  it("does not follow on another document the job a start of the one before gave back late", async () => {
    let late: (value: Job) => void = () => undefined;
    vi.spyOn(api, "getDocument").mockImplementation((id) =>
      Promise.resolve(document_({ id, title: id, extraction: { kind: "extract.run", job_id: `job-of-${id}`, status: "cancelled", error_code: null } })),
    );
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "startExtraction").mockReturnValue(new Promise<Job>((resolve) => (late = resolve)));
    const wrapper = await open("d1");
    await wrapper.get("[data-test=extraction-resume]").trigger("click");

    await wrapper.setProps({ id: "d2" });
    await flushPromises();
    late(job("queued", "new-of-d1"));
    await flushPromises();

    expect(wrapper.get("h1").text()).toBe("d2");
    expect(wrapper.findComponent({ name: "JobProgress" }).exists()).toBe(false);
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(true);
  });

  it("drops a document that came after the page moved on to another", async () => {
    let late: (value: CurriculumDocument) => void = () => undefined;
    vi.spyOn(api, "getDocument")
      .mockReturnValueOnce(new Promise<CurriculumDocument>((resolve) => (late = resolve)))
      .mockResolvedValue(document_({ id: "d2", title: "Zweites" }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const wrapper = await open("d1");

    await wrapper.setProps({ id: "d2" });
    await flushPromises();
    late(document_({ title: "Erstes" }));
    await flushPromises();

    expect(wrapper.get("h1").text()).toBe("Zweites");
  });

  it("takes an address that is no document's for one it does not find", async () => {
    vi.spyOn(api, "getDocument").mockRejectedValue(new ApiError("server", 422, "validation"));
    vi.spyOn(api, "getRuns").mockResolvedValue([]);

    const wrapper = await open("kein-dokument");

    expect(wrapper.get("h2").text()).toBe(t("documents.page.notFoundTitle"));
  });
});

describe("a document's extraction asked after on its page", () => {
  it("says to an editor that the extraction ended", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ own: false, extraction: { kind: "extract.run", job_id: null, status: "running", error_code: null } }))
      .mockResolvedValue(document_({ own: false, extraction: { kind: "extract.run", job_id: null, status: "done", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const wrapper = await open();

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    const said = t("jobs.announce", { label: isolate(t("documents.page.jobLabel")), status: t("jobs.status.done") });
    expect(extractionStatus(wrapper)).toBe(said);
  });

  it("asks after the document again when a job it started is gone from the reader", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }))
      .mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j2", status: "running", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));
    const wrapper = await open();

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(1000); // the job answers 404
    await flushPromises();

    expect(api.getDocument).toHaveBeenCalledTimes(2);
    expect(extraction(wrapper).text()).toContain(t("documents.page.following"));
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(false);
  });

  it("goes on asking after an editor's document whose state came back as it was", async () => {
    vi.useFakeTimers();
    const running = document_({ own: false, extraction: { kind: "extract.run", job_id: null, status: "running", error_code: null } });
    const queued = document_({ own: false, extraction: { kind: "extract.run", job_id: null, status: "queued", error_code: null } });
    const get = vi
      .spyOn(api, "getDocument")
      .mockResolvedValueOnce({ ...running }) // the page
      .mockResolvedValueOnce({ ...queued }) // the question: it moved, the page reads it again
      .mockResolvedValueOnce({ ...running }) // and gets it as it was, running again
      .mockImplementation(() => Promise.resolve({ ...running }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    await open();

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();
    const asked = get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10_000);

    expect(get.mock.calls.length).toBeGreaterThan(asked);
  });

  it("goes on asking when the server is away a moment, and stops once the page is left", async () => {
    vi.useFakeTimers();
    const running = document_({ own: false, extraction: { kind: "extract.run", job_id: null, status: "running", error_code: null } });
    const get = vi
      .spyOn(api, "getDocument")
      .mockResolvedValueOnce(running)
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue(running);
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const wrapper = await open();

    await vi.advanceTimersByTimeAsync(1000); // 503
    await vi.advanceTimersByTimeAsync(2000); // asked again
    expect(get).toHaveBeenCalledTimes(3);
    wrapper.unmount();
    shown = null;
    await vi.advanceTimersByTimeAsync(30_000);

    expect(get).toHaveBeenCalledTimes(3);
  });

  it("leaves the keyboard where the reader took it while the start was on its way", async () => {
    let reply: (value: Job) => void = () => undefined;
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "startExtraction").mockReturnValue(new Promise<Job>((resolve) => (reply = resolve)));
    const wrapper = await open();
    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    const elsewhere = wrapper.get("[data-test=document-source]").element as HTMLElement;
    elsewhere.focus();

    reply(job("queued"));
    await flushPromises();

    expect(document.activeElement).toBe(elsewhere);
  });

  it("leaves the keyboard where the reader took it once the extraction ended", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }))
      .mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "done", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "getJob").mockResolvedValue(job("done", "j1"));
    const wrapper = await open();
    (wrapper.get(".job__line").element as HTMLElement).focus();
    const elsewhere = wrapper.get("[data-test=document-source]").element as HTMLElement;
    vi.mocked(api.getDocument).mockImplementation(() => {
      elsewhere.focus(); // the reader goes on while the page reads the document again
      return Promise.resolve(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "done", error_code: null } }));
    });

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(document.activeElement).toBe(elsewhere);
  });

  it("shows the job it started as ended until the page has read the document again", async () => {
    vi.useFakeTimers();
    let reread: (value: CurriculumDocument) => void = () => undefined;
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }))
      .mockReturnValue(new Promise<CurriculumDocument>((resolve) => (reread = resolve)));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    vi.spyOn(api, "getJob").mockResolvedValue(job("done"));
    const wrapper = await open();
    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();

    await vi.advanceTimersByTimeAsync(1000); // ended; the document is on its way

    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(false);
    expect(wrapper.get(".status-badge").text()).toBe(t("jobs.status.done"));
    reread(document_({ extraction: { kind: "extract.run", job_id: "j2", status: "done", error_code: null } }));
    await flushPromises();
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(true);
  });

  it("says, where a start led to an extraction that ran already, that it is that one, and says it once", async () => {
    ledHere();
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(extraction(wrapper).text()).toContain(t("documents.page.ledToRunning"));
    expect(extractionStatus(wrapper)).toBe(t("documents.page.ledToRunning"));
    wrapper.unmount();
    shown = null;
    const again = await open(); // the page read again later, or come back to: no longer so
    expect(extraction(again).text()).not.toContain(t("documents.page.ledToRunning"));
  });

  it("reads anew for each document it moves to whether a start led there", async () => {
    vi.spyOn(api, "getDocument").mockImplementation((id) =>
      Promise.resolve(document_({ id, title: id, extraction: { kind: "extract.run", job_id: `job-of-${id}`, status: "running", error_code: null } })),
    );
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const wrapper = await open("d1");
    expect(extraction(wrapper).text()).not.toContain(t("documents.page.ledToRunning"));

    ledHere();
    await wrapper.setProps({ id: "d2" });
    await flushPromises();

    expect(extraction(wrapper).text()).toContain(t("documents.page.ledToRunning"));
  });
});

describe("a document's repair on its page", () => {
  const repairing = (status: Job["status"]): CurriculumDocument["extraction"] => ({
    kind: "extract.repair",
    job_id: "j9",
    status,
    error_code: status === "failed" ? "budget_exhausted" : null,
  });

  it("is named as such under the extraction, and how the last one ended", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: repairing("failed") }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(extraction(wrapper).get("[data-test=extraction-last]").text()).toBe(
      `${t("documents.page.lastRepairStatus", { status: t("jobs.status.failed") })}. ${jobFailureText("budget_exhausted")}`,
    );
  });

  it("is started from the findings and followed under the extraction, named as a repair", async () => {
    let reread: (value: CurriculumDocument) => void = () => undefined;
    const read = vi
      .spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_())
      .mockReturnValueOnce(new Promise<CurriculumDocument>((resolve) => (reread = resolve)));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getFindings).mockResolvedValue(REPAIRABLE);
    vi.mocked(api.getJob).mockResolvedValue({ ...job("queued", "j9"), kind: "extract.repair" });
    const start = vi.spyOn(api, "startRepair").mockResolvedValue({ ...job("queued", "j9"), kind: "extract.repair" });
    const wrapper = await open();

    await wrapper.get("[data-test=repair-start]").trigger("click");
    await flushPromises();
    // the document not read again yet: no second start is offered meanwhile
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
    reread(document_({ extraction: repairing("queued") }));
    await flushPromises();

    expect(start).toHaveBeenCalledWith("d1");
    expect(read).toHaveBeenCalledTimes(2); // the page reads the document again, and follows its job
    expect(extraction(wrapper).get(".job__label").text()).toBe(t("documents.page.repairLabel"));
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
  });

  it("is offered again once the document says the repair started has ended", async () => {
    // a package repaired once, its findings still asking: a second repair is the owner's to start
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_())
      .mockResolvedValue(document_({ extraction: repairing("done") }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getFindings).mockResolvedValue(REPAIRABLE);
    vi.spyOn(api, "startRepair").mockResolvedValue({ ...job("queued", "j9"), kind: "extract.repair" });
    const wrapper = await open();

    await wrapper.get("[data-test=repair-start]").trigger("click");
    await flushPromises();

    expect(extraction(wrapper).get("[data-test=extraction-last]").text()).toBe(
      t("documents.page.lastRepairStatus", { status: t("jobs.status.done") }),
    );
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(true);
  });

  it("is not offered while the extraction runs", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(
      document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }),
    );
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getFindings).mockResolvedValue(REPAIRABLE);

    const wrapper = await open();

    expect(wrapper.get("section[aria-labelledby=document-findings]").text()).toContain(
      t("documents.findings.rules.wording_not_found"),
    );
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
  });

  it("is not offered while the job runs though it is no longer the reader's to follow", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "getDocument").mockResolvedValue(
      document_({ extraction: { kind: "extract.run", job_id: "j1", status: "running", error_code: null } }),
    );
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getFindings).mockResolvedValue(REPAIRABLE);
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));

    const wrapper = await open();
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(extraction(wrapper).text()).toContain(t("documents.page.following")); // asked after, not followed
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
  });

  it("is not offered to another who reads the document", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ own: false }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getFindings).mockResolvedValue(REPAIRABLE);

    const wrapper = await open();

    expect(wrapper.get("section[aria-labelledby=document-findings]").text()).toContain(
      t("documents.findings.rules.wording_not_found"),
    );
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
  });

  it("is not offered while an extraction started here runs, the document not read again yet", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(
      document_({ extraction: { kind: "extract.run", job_id: "j1", status: "cancelled", error_code: null } }),
    );
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.mocked(api.getFindings).mockResolvedValue(REPAIRABLE);
    vi.spyOn(api, "startExtraction").mockResolvedValue(job("queued"));
    const wrapper = await open();
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(true);

    await wrapper.get("[data-test=extraction-resume]").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
  });
});

describe("a document's revision on its page", () => {
  const EDITOR = { id: "a2", name: "Redakteurin", roles: ["redaktion" as const] };
  const WORK = { id: "w1", title: "Kernlehrplan Physik", region: "DE-NW", short_title: "klp-physik", iri: null };

  it("says its work and edition to everyone, and offers freezing to an editor alone", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ work: WORK, issuer: "MSB", edition: "2019" }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    const owner = await open();
    expect(owner.find("section[aria-labelledby=document-edition]").exists()).toBe(true);
    expect(owner.find("[data-test=freeze]").exists()).toBe(false);
    owner.unmount();

    setSession(EDITOR);
    const editor = await open();
    expect(editor.find("[data-test=freeze]").exists()).toBe(true);
  });

  it("freezes the document, the keyboard taken to the notice that says so, its start no longer offered", async () => {
    setSession(EDITOR);
    const frozen = document_({ work: WORK, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" });
    vi.spyOn(api, "getDocument").mockResolvedValueOnce(document_({ work: WORK })).mockResolvedValue(frozen);
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "freezeDocument").mockResolvedValue(frozen);
    const wrapper = await open();

    await wrapper.get("[data-test=freeze]").trigger("click");
    await flushPromises();
    await wrapper.get("[data-test=confirm]").trigger("click");
    await flushPromises();

    const notice = wrapper.get(".revision-notice");
    expect(notice.text()).toContain(t("documents.page.revision.frozenText"));
    expect(document.activeElement).toBe(notice.element);
    expect(wrapper.find("[data-test=freeze]").exists()).toBe(false);
    expect(extraction(wrapper).text()).toContain(t("documents.page.frozenNoExtraction"));
  });

  it("says a document frozen where the keyboard went elsewhere meanwhile, leaving it there", async () => {
    setSession(EDITOR);
    const frozen = document_({ work: WORK, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" });
    vi.spyOn(api, "getDocument").mockResolvedValueOnce(document_({ work: WORK })).mockResolvedValue(frozen);
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    let answer: (document: typeof frozen) => void = () => undefined;
    vi.spyOn(api, "freezeDocument").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const wrapper = await open();
    await wrapper.get("[data-test=freeze]").trigger("click");
    await flushPromises();
    await wrapper.get("[data-test=confirm]").trigger("click");

    const elsewhere = wrapper.get("[data-test=document-tree]").element as HTMLElement;
    elsewhere.focus();
    answer(frozen);
    await flushPromises();

    expect(document.activeElement).toBe(elsewhere);
    expect(wrapper.get("[data-test=document-status]").text()).toBe(t("documents.page.revision.frozenSaid"));
  });

  it("takes the keyboard to the notice where a reading finds the document frozen under a form", async () => {
    setSession(EDITOR);
    const frozen = document_({ work: WORK, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" });
    vi.spyOn(api, "getDocument").mockResolvedValueOnce(document_({ work: WORK })).mockResolvedValue(frozen);
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "editDocument").mockRejectedValue(new ApiError("server", 409, "frozen"));
    const wrapper = await open();
    const issuer = wrapper.findAll("label").find((one) => one.text() === t("documents.page.edition.issuer"));
    await wrapper.get(`#${issuer?.attributes("for")}`).setValue("Ministerium");
    const save = wrapper.get(".meta-form button[type=submit]");
    (save.element as HTMLElement).focus();

    await wrapper.get(".meta-form").trigger("submit");
    await flushPromises();

    expect(wrapper.find(".meta-form").exists()).toBe(false);
    expect(document.activeElement).toBe(wrapper.get(".revision-notice").element);
  });

  it("leaves the keyboard where it is on a page opened frozen, and on a frozen document read again", async () => {
    setSession(EDITOR);
    const frozen = document_({ work: WORK, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" });
    // each reading a document of its own, as the server's answers are
    vi.spyOn(api, "getDocument").mockImplementation(() => Promise.resolve({ ...frozen }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "copyDocument").mockRejectedValue(new ApiError("server", 409, "not_frozen"));
    const wrapper = await open();
    expect(document.activeElement).not.toBe(wrapper.get(".revision-notice").element);

    const copy = wrapper.get("[data-test=copy]");
    (copy.element as HTMLElement).focus();
    await copy.trigger("click"); // refused: the page reads the document again, still frozen
    await flushPromises();

    expect(api.getDocument).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(wrapper.get("[data-test=copy]").element);
    expect(wrapper.get("[data-test=document-status]").text()).toBe("");
  });

  it("shows the document frozen as the freeze answers, before it is read again", async () => {
    setSession(EDITOR);
    const frozen = document_({ work: WORK, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" });
    vi.spyOn(api, "getDocument").mockResolvedValueOnce(document_({ work: WORK })).mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "freezeDocument").mockResolvedValue(frozen);
    const wrapper = await open();

    await wrapper.get("[data-test=freeze]").trigger("click");
    await flushPromises();
    await wrapper.get("[data-test=confirm]").trigger("click");
    await flushPromises();

    expect(wrapper.find(".revision-notice").exists()).toBe(true);
    expect(wrapper.find("[data-test=freeze]").exists()).toBe(false);
  });

  it("keeps the keyboard on the notice where a reading finds the document frozen and its work set at once", async () => {
    setSession(EDITOR);
    vi.spyOn(api, "listDocuments").mockResolvedValue([document_({ id: "d7", work: WORK })]);
    const frozen = document_({ work: WORK, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" });
    vi.spyOn(api, "getDocument").mockResolvedValueOnce(document_()).mockResolvedValue(frozen);
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "setWork").mockRejectedValue(new ApiError("server", 409, "frozen"));
    const wrapper = await open();
    const choose = wrapper.findAll(".work-form select")[0];
    await choose.setValue("w1");
    const button = wrapper.get(".work-form button[type=submit]");
    (button.element as HTMLElement).focus();

    await wrapper.get(".work-form").trigger("submit");
    await flushPromises();

    expect(wrapper.find(".work-form").exists()).toBe(false);
    expect(document.activeElement).toBe(wrapper.get(".revision-notice").element);
  });

  it("says a draft copy made where the page moves on to it from the frozen one", async () => {
    vi.spyOn(api, "getRuns").mockResolvedValue([]);
    vi.spyOn(api, "getDocument").mockImplementation((id) =>
      Promise.resolve(
        id === "d3"
          ? document_({ id: "d3", copy_of: "d1", revision: 2, extraction: null })
          : document_({ iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" }),
      ),
    );
    const wrapper = await open();

    window.history.replaceState({ ...window.history.state, copied: true }, "");
    await wrapper.setProps({ id: "d3" });
    await flushPromises();

    expect(wrapper.get(".revision-notice [role=status]").text()).toBe(t("documents.page.revision.copied"));
    expect(window.history.state.copied).toBeUndefined();
  });

  it("says a draft copy made, once, where its page was opened for that", async () => {
    window.history.replaceState({ ...window.history.state, copied: true }, "");
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ id: "d3", copy_of: "d1", revision: 2, extraction: null }));
    vi.spyOn(api, "getRuns").mockResolvedValue([]);

    const wrapper = await open("d3");

    expect(wrapper.get(".revision-notice [role=status]").text()).toBe(t("documents.page.revision.copied"));
    expect(window.history.state.copied).toBeUndefined();
  });
});

describe("why a run failed", () => {
  it("is said in the page's words where it knows them, else quoted as the server wrote it", async () => {
    const sentence = "X1 of the document was written by another run meanwhile";
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue([
      { ...RUNS[1], state: "failed", failure: "LeaseLost" },
      { ...RUNS[1], state: "failed", failure: "model_not_configured" },
      { ...RUNS[1], state: "failed", failure: sentence },
      { ...RUNS[1], state: "failed", failure: "x".repeat(400) },
    ]);

    const wrapper = await open();

    const reasons = wrapper.findAll("tbody tr").map((row) => row.findAll("td")[5]);
    expect(reasons[0].text()).toBe(t("documents.runFailures.LeaseLost"));
    expect(reasons[1].text()).toBe(jobFailureText("model_not_configured"));
    expect(reasons[2].get("q").attributes("lang")).toBe("en");
    expect(reasons[2].get("q").text()).toBe(sentence);
    expect(reasons[3].get("q").text().length).toBeLessThanOrEqual(201);
  });

  it("cuts a long sentence at a word and no sign in two, and quotes a name every object has", async () => {
    const words = `${"Wort ".repeat(39)}Wortende${"x".repeat(30)}`;
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getRuns").mockResolvedValue([
      { ...RUNS[1], state: "failed", failure: words },
      { ...RUNS[1], state: "failed", failure: `a${"\u{1F600}".repeat(150)}` },
      { ...RUNS[1], state: "failed", failure: "constructor" },
    ]);

    const wrapper = await open();

    const reasons = wrapper.findAll("tbody tr").map((row) => row.findAll("td")[5]);
    expect(reasons[0].get("q").text()).toBe(`${"Wort ".repeat(38)}Wort…`);
    expect([...reasons[1].get("q").text()].every((sign) => sign === "a" || sign === "\u{1F600}" || sign === "…")).toBe(true);
    expect(reasons[2].get("q").text()).toBe("constructor");
  });
});
