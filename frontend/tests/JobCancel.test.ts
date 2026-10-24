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
    expect(wrapper.get("[role=status]").text()).toContain(t("jobs.cancel.requested"));
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
