import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type Job } from "@/api";
import JobProgress from "@/components/JobProgress.vue";
import { t } from "@/i18n/de";

import { violations } from "./axe";

const NOW = new Date("2026-10-24T12:00:00Z");

function job(status: Job["status"], changes: Partial<Job> = {}): Job {
  return {
    id: "j1",
    kind: "extract.run",
    status,
    progress: null,
    error_code: null,
    cancel_requested: false,
    attempts: 1,
    max_attempts: 3,
    created_at: "2026-10-24T11:50:00Z",
    started_at: status === "queued" ? null : "2026-10-24T11:55:00Z",
    finished_at: null,
    ...changes,
  };
}

function shown(label = "Lehrplan Physik") {
  return mount(JobProgress, { props: { jobId: "j1", label }, attachTo: document.body });
}

const cancelButton = (wrapper: ReturnType<typeof shown>) => wrapper.find("[data-test=job-cancel]");
const dialog = () => document.querySelector("[role=dialog]");

/** Presses the job's cancel, its button focused as a click leaves it, and says yes. */
async function confirmCancel(wrapper: ReturnType<typeof shown>): Promise<void> {
  (cancelButton(wrapper).element as HTMLButtonElement).focus();
  await cancelButton(wrapper).trigger("click");
  (document.querySelector("[data-test=confirm]") as HTMLButtonElement).click();
  await flushPromises();
}

/** As confirmCancel, the reader going on to another control while the cancel is on its way. */
async function confirmCancelGoingOn(wrapper: ReturnType<typeof shown>, answer: Job): Promise<HTMLButtonElement> {
  let reply: (value: Job) => void = () => undefined;
  vi.mocked(api.cancelJob).mockReturnValue(new Promise<Job>((resolve) => (reply = resolve)));
  const elsewhere = document.body.appendChild(document.createElement("button"));
  (cancelButton(wrapper).element as HTMLButtonElement).focus();
  await cancelButton(wrapper).trigger("click");
  (document.querySelector("[data-test=confirm]") as HTMLButtonElement).click();
  await flushPromises();
  elsewhere.focus();
  reply(answer);
  await flushPromises();
  return elsewhere;
}

const line = (wrapper: ReturnType<typeof shown>) => wrapper.get(".job__line").element;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("a job cancelled from the page", () => {
  it.each(["queued", "running"] as const)("offers its cancel while it is %s", async (status) => {
    vi.spyOn(api, "getJob").mockResolvedValue(job(status));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    const button = cancelButton(wrapper);
    expect(button.exists()).toBe(true);
    expect(button.text()).toBe(t("jobs.cancel.button"));
    // its name says which job, the visible word inside it
    expect(button.attributes("aria-label")).toBe(t("jobs.cancel.name", { label: "Lehrplan Physik" }));
  });

  it.each(["done", "failed", "cancelled"] as const)("offers none once it is %s", async (status) => {
    vi.spyOn(api, "getJob").mockResolvedValue(job(status));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    expect(cancelButton(wrapper).exists()).toBe(false);
  });

  it("asks first, and a no leaves the job running", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("running"));
    const cancel = vi.spyOn(api, "cancelJob");
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);

    await cancelButton(wrapper).trigger("click");

    expect(dialog()?.textContent).toContain(t("jobs.cancel.title"));
    // the keyboard starts on keeping it: Enter on a dialog that came unasked stops nothing
    expect(document.activeElement?.textContent?.trim()).toBe(t("jobs.cancel.keep"));
    (document.querySelector("[data-test=cancel]") as HTMLButtonElement).click();
    await flushPromises();
    expect(dialog()).toBeNull();
    expect(cancel).not.toHaveBeenCalled();
  });

  it("cancels on a yes and says the stop is asked for until the job has ended", async () => {
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(asked);
    const cancel = vi.spyOn(api, "cancelJob").mockResolvedValue(asked);
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);

    await cancelButton(wrapper).trigger("click");
    (document.querySelector("[data-test=confirm]") as HTMLButtonElement).click();
    await flushPromises();

    expect(cancel).toHaveBeenCalledWith("j1");
    expect(cancelButton(wrapper).exists()).toBe(false);
    expect(wrapper.get("[data-test=job-cancel-asked]").text()).toBe(t("jobs.cancel.requested"));
    // said once: the keyboard lands on the note, which reads it; the region does not say it again
    expect(document.activeElement).toBe(wrapper.get("[data-test=job-cancel-asked]").element);
    expect(wrapper.get("[role=status]").text()).not.toContain(t("jobs.cancel.requested"));
  });

  it.each([
    [409, "jobs.cancel.ended"],
    [404, "jobs.cancel.gone"],
    [503, "jobs.cancel.failed"],
  ])("says why a cancel answered %i was not taken", async (status, key) => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("running"));
    vi.spyOn(api, "cancelJob").mockRejectedValue(new ApiError("server", status));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);

    await cancelButton(wrapper).trigger("click");
    (document.querySelector("[data-test=confirm]") as HTMLButtonElement).click();
    await flushPromises();

    expect(wrapper.get("[data-test=job-cancel-failed]").text()).toContain(t(key));
  });

  it("says how long a running job has run", async () => {
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running", { started_at: "2026-10-24T11:55:00Z" }))
      .mockResolvedValue(job("running", { started_at: "2026-10-24T11:59:40Z" }));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.runningFor", { minutes: 5 }));

    await vi.advanceTimersByTimeAsync(2000);
    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.runningJustNow"));
  });

  it("has nothing axe finds, the question open too", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("running"));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    vi.useRealTimers(); // axe waits on timers of its own

    expect(await violations(wrapper.html())).toEqual([]);
    await cancelButton(wrapper).trigger("click");
    expect(await violations(document.body.innerHTML)).toEqual([]);
  });
});

describe("a cancel as the page around it sees it", () => {
  it("is announced where the keyboard went elsewhere, though the page says the job's states itself", async () => {
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(asked);
    vi.spyOn(api, "cancelJob");
    const wrapper = mount(JobProgress, {
      props: { jobId: "j1", label: "Umwandlung", quiet: true },
      attachTo: document.body,
    });
    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.get("[role=status]").text()).toBe("");

    const elsewhere = await confirmCancelGoingOn(wrapper, asked);

    expect(wrapper.get("[role=status]").text()).toContain(t("jobs.cancel.requested"));
    expect(document.activeElement).toBe(elsewhere); // where the reader went, not taken back
  });

  it("says the stop as a sentence of its own after the job's state", async () => {
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(asked);
    vi.spyOn(api, "cancelJob");
    const wrapper = shown("Physik");
    await vi.advanceTimersByTimeAsync(1000);

    await confirmCancelGoingOn(wrapper, asked);

    const said = t("jobs.announce", { label: "\u2068Physik\u2069", status: t("jobs.status.running") });
    expect(wrapper.get("[role=status]").text()).toBe(`${said}. ${t("jobs.cancel.requested")}`);
  });

  it("says a failure as a sentence of its own after the job's state", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("failed", { error_code: "handler_error" }));
    const wrapper = shown("Physik");

    await vi.advanceTimersByTimeAsync(1000);

    const said = t("jobs.announce", { label: "\u2068Physik\u2069", status: t("jobs.status.failed") });
    expect(wrapper.get("[role=status]").text()).toBe(`${said}. ${t("jobs.failures.handler_error")}`);
  });

  it("keeps the keyboard at the job once the cancel's button has gone", async () => {
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(asked);
    vi.spyOn(api, "cancelJob").mockResolvedValue(asked);
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);

    await confirmCancel(wrapper);

    expect(document.activeElement).toBe(wrapper.get("[data-test=job-cancel-asked]").element);
  });

  it("tells the page at once that the cancel ended a waiting job, and once", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("queued"));
    vi.spyOn(api, "cancelJob").mockResolvedValue(job("cancelled", { cancel_requested: true }));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);

    await confirmCancel(wrapper);

    expect(wrapper.emitted("ended")).toHaveLength(1);
    expect(document.activeElement).toBe(line(wrapper));
    expect(wrapper.get("[role=status]").text()).toBe(""); // the line read where the keyboard landed says it
    await vi.advanceTimersByTimeAsync(30_000); // no question asked after: a waiting answer would undo it
    expect(wrapper.emitted("ended")).toHaveLength(1);
    expect(wrapper.find(".status-badge").text()).toBe(t("jobs.status.cancelled"));
  });

  it("is not undone by an answer to a question asked before it", async () => {
    let late: (value: Job) => void = () => undefined;
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running"))
      .mockImplementationOnce(() => new Promise<Job>((resolve) => (late = resolve)))
      .mockResolvedValue(asked);
    vi.spyOn(api, "cancelJob").mockResolvedValue(asked);
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(3000); // the second question is on its way

    await confirmCancel(wrapper);
    late(job("running"));
    await flushPromises();

    expect(cancelButton(wrapper).exists()).toBe(false);
    expect(wrapper.find("[data-test=job-cancel-asked]").exists()).toBe(true);
    // the region says the state the later answer gave, and not that the stop is off
    expect(wrapper.get("[role=status]").text()).toBe(
      t("jobs.announce", { label: "\u2068Lehrplan Physik\u2069", status: t("jobs.status.running") }),
    );
  });

  it("closes its question when the job ends meanwhile", async () => {
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(job("done"));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    await cancelButton(wrapper).trigger("click");
    expect(dialog()).not.toBeNull();

    await vi.advanceTimersByTimeAsync(2000);

    expect(dialog()).toBeNull();
  });
});

describe("the keyboard and the page as the job ends", () => {
  it("tells the page once when a question asked before the cancel brought the end first", async () => {
    let early: (value: Job) => void = () => undefined;
    let reply: (value: Job) => void = () => undefined;
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running"))
      .mockImplementationOnce(() => new Promise<Job>((resolve) => (early = resolve)));
    vi.spyOn(api, "cancelJob").mockReturnValue(new Promise<Job>((resolve) => (reply = resolve)));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(3000); // the second question is on its way
    await cancelButton(wrapper).trigger("click");
    (document.querySelector("[data-test=confirm]") as HTMLButtonElement).click();
    await flushPromises();

    early(job("cancelled", { cancel_requested: true }));
    await flushPromises();
    reply(job("cancelled", { cancel_requested: true }));
    await flushPromises();

    expect(wrapper.emitted("ended")).toHaveLength(1);
  });

  it("keeps the keyboard at the job when the note it rested on goes with the job's end", async () => {
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running"))
      .mockResolvedValueOnce(asked)
      .mockResolvedValue(job("cancelled", { cancel_requested: true }));
    vi.spyOn(api, "cancelJob").mockResolvedValue(asked);
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    await confirmCancel(wrapper);
    expect(document.activeElement).toBe(wrapper.get("[data-test=job-cancel-asked]").element);

    await vi.advanceTimersByTimeAsync(8000);
    await flushPromises();

    expect(wrapper.find("[data-test=job-cancel-asked]").exists()).toBe(false);
    expect(document.activeElement).toBe(line(wrapper));
    expect(wrapper.get("[role=status]").text()).toBe(""); // said once: by the line the keyboard reads
  });

  it("leaves the keyboard to the page that says the job's states, when its note goes with the end", async () => {
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running"))
      .mockResolvedValueOnce(asked)
      .mockResolvedValue(job("cancelled", { cancel_requested: true }));
    vi.spyOn(api, "cancelJob").mockResolvedValue(asked);
    const wrapper = mount(JobProgress, { props: { jobId: "j1", label: "Umwandlung", quiet: true }, attachTo: document.body });
    await vi.advanceTimersByTimeAsync(1000);
    await confirmCancel(wrapper);

    await vi.advanceTimersByTimeAsync(8000);
    await flushPromises();

    // the page around reads the job again and takes the keyboard to its own heading
    expect(document.activeElement).not.toBe(line(wrapper));
  });

  it("says the stop in the region where the keyboard did not reach its note", async () => {
    const asked = job("running", { cancel_requested: true });
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(asked);
    vi.spyOn(api, "cancelJob").mockResolvedValue(asked);
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    (cancelButton(wrapper).element as HTMLButtonElement).focus();
    await cancelButton(wrapper).trigger("click");
    const focus = vi.spyOn(HTMLElement.prototype, "focus").mockImplementation(() => undefined);
    (document.querySelector("[data-test=confirm]") as HTMLButtonElement).click();
    await flushPromises();
    focus.mockRestore();

    expect(wrapper.get("[role=status]").text()).toContain(t("jobs.cancel.requested"));
  });

  it("is not set running again by a cancel's answer that comes after the job's end", async () => {
    let reply: (value: Job) => void = () => undefined;
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running"))
      .mockResolvedValue(job("cancelled", { cancel_requested: true }));
    vi.spyOn(api, "cancelJob").mockReturnValue(new Promise<Job>((resolve) => (reply = resolve)));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    await cancelButton(wrapper).trigger("click");
    (document.querySelector("[data-test=confirm]") as HTMLButtonElement).click();
    await vi.advanceTimersByTimeAsync(2000); // the end comes first
    await flushPromises();

    reply(job("running", { cancel_requested: true }));
    await flushPromises();

    expect(wrapper.find(".status-badge").text()).toBe(t("jobs.status.cancelled"));
    expect(wrapper.find("[data-test=job-cancel-asked]").exists()).toBe(false);
  });

  it("keeps the keyboard at the job when its open question closes with the job's end", async () => {
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(job("done"));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    (cancelButton(wrapper).element as HTMLButtonElement).focus();
    await cancelButton(wrapper).trigger("click");

    await vi.advanceTimersByTimeAsync(2000);

    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(line(wrapper));
  });

  it("takes the keyboard nowhere when the job ends where it rested on nothing of the job", async () => {
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(job("done"));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    expect(document.activeElement).toBe(document.body);

    await vi.advanceTimersByTimeAsync(2000);

    expect(wrapper.find(".status-badge").text()).toBe(t("jobs.status.done"));
    expect(document.activeElement).toBe(document.body); // no jump to the job the reader was not at
  });

  it("leaves the keyboard where the reader took it when the job ends", async () => {
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(job("done"));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    const elsewhere = document.body.appendChild(document.createElement("button"));
    elsewhere.focus();

    await vi.advanceTimersByTimeAsync(2000);

    expect(wrapper.find(".status-badge").text()).toBe(t("jobs.status.done"));
    expect(document.activeElement).toBe(elsewhere);
  });
});

describe("how long a job has waited or run", () => {
  it("says a job handed back waits for its next try, not since it was made", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("queued", { attempts: 1, created_at: "2026-10-24T09:00:00Z" }));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.waitingAgain"));
  });

  it("counts hours and minutes past an hour", async () => {
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running", { started_at: "2026-10-24T09:48:00Z" }))
      .mockResolvedValue(job("running", { started_at: "2026-10-24T10:00:00Z" }));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.runningForHours", { hours: 2, minutes: 12 }));
    await vi.advanceTimersByTimeAsync(2000);
    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.runningForHoursOnly", { hours: 2 }));
  });

  it("goes on with the clock between two answers", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("running", { started_at: "2026-10-24T11:59:30Z" }));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.runningJustNow"));

    await vi.advanceTimersByTimeAsync(61_000);

    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.runningFor", { minutes: 1 }));
  });

  it("says how long a waiting job has waited: one that hangs there shows it", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("queued", { attempts: 0, created_at: "2026-10-24T11:48:00Z" }));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.get("[data-test=job-runtime]").text()).toBe(t("jobs.waitingFor", { minutes: 12 }));
  });
});
