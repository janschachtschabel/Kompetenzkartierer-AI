import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type Job, type Run } from "@/api";
import { isolate } from "@/bidi";
import { t } from "@/i18n/de";
import { jobFailureText } from "@/jobMessages";
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
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  vi.useRealTimers();
  document.body.innerHTML = "";
});

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

describe("a document's extraction followed on its page", () => {
  it("is read by an editor from the document while it runs, the job not theirs to follow", async () => {
    vi.useFakeTimers();
    const running = document_({ own: false, extraction: { job_id: null, status: "running" } });
    const get = vi
      .spyOn(api, "getDocument")
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running)
      .mockResolvedValue(document_({ own: false, extraction: { job_id: null, status: "done" } }));
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
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { job_id: "j1", status: "running" } }));
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
      .mockResolvedValueOnce(document_({ extraction: { job_id: "j1", status: "running" } }))
      .mockResolvedValue(document_({ extraction: { job_id: "j1", status: "failed" } }));
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
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { job_id: "j1", status: "cancelled" } }));
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
    const ended = document_({ extraction: { job_id: "j2", status: "done" } });
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { job_id: "j1", status: "cancelled" } }))
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
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { job_id: "j1", status: "cancelled" } }));
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
      Promise.resolve(document_({ id, title: id, extraction: { job_id: `job-of-${id}`, status: "cancelled" } })),
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
      .mockResolvedValueOnce(document_({ own: false, extraction: { job_id: null, status: "running" } }))
      .mockResolvedValue(document_({ own: false, extraction: { job_id: null, status: "done" } }));
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
      .mockResolvedValueOnce(document_({ extraction: { job_id: "j1", status: "cancelled" } }))
      .mockResolvedValue(document_({ extraction: { job_id: "j2", status: "running" } }));
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
    const running = document_({ own: false, extraction: { job_id: null, status: "running" } });
    const queued = document_({ own: false, extraction: { job_id: null, status: "queued" } });
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
    const running = document_({ own: false, extraction: { job_id: null, status: "running" } });
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
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { job_id: "j1", status: "cancelled" } }));
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
      .mockResolvedValueOnce(document_({ extraction: { job_id: "j1", status: "running" } }))
      .mockResolvedValue(document_({ extraction: { job_id: "j1", status: "done" } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);
    vi.spyOn(api, "getJob").mockResolvedValue(job("done", "j1"));
    const wrapper = await open();
    (wrapper.get(".job__line").element as HTMLElement).focus();
    const elsewhere = wrapper.get("[data-test=document-source]").element as HTMLElement;
    vi.mocked(api.getDocument).mockImplementation(() => {
      elsewhere.focus(); // the reader goes on while the page reads the document again
      return Promise.resolve(document_({ extraction: { job_id: "j1", status: "done" } }));
    });

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(document.activeElement).toBe(elsewhere);
  });

  it("shows the job it started as ended until the page has read the document again", async () => {
    vi.useFakeTimers();
    let reread: (value: CurriculumDocument) => void = () => undefined;
    vi.spyOn(api, "getDocument")
      .mockResolvedValueOnce(document_({ extraction: { job_id: "j1", status: "cancelled" } }))
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
    reread(document_({ extraction: { job_id: "j2", status: "done" } }));
    await flushPromises();
    expect(wrapper.find("[data-test=extraction-resume]").exists()).toBe(true);
  });

  it("says, where a start led to an extraction that ran already, that it is that one", async () => {
    window.history.replaceState({ ...window.history.state, ledToRunning: true }, "");
    vi.spyOn(api, "getDocument").mockResolvedValue(document_({ extraction: { job_id: "j1", status: "running" } }));
    vi.spyOn(api, "getRuns").mockResolvedValue(RUNS);

    const wrapper = await open();

    expect(extraction(wrapper).text()).toContain(t("documents.page.ledToRunning"));
    window.history.replaceState({ ...window.history.state, ledToRunning: undefined }, "");
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
