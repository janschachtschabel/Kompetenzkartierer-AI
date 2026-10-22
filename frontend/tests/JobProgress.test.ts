import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type Job } from "@/api";
import JobProgress from "@/components/JobProgress.vue";
import { t } from "@/i18n/de";

function job(status: Job["status"], error_code: string | null = null): Job {
  return {
    id: "j1",
    kind: "source.fetch",
    status,
    progress: null,
    error_code,
    cancel_requested: false,
    attempts: 1,
    max_attempts: 3,
    created_at: "2026-10-22T10:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

function shown(label = "Lehrplan Physik") {
  return mount(JobProgress, { props: { jobId: "j1", label } });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a job's progress", () => {
  it("shows the job waiting until the server says more, then what it says, and when it ended", async () => {
    vi.spyOn(api, "getJob").mockResolvedValueOnce(job("running")).mockResolvedValue(job("done"));
    const wrapper = shown();
    expect(wrapper.get(".status-badge").text()).toBe(t("jobs.status.queued"));
    expect(wrapper.text()).toContain("Lehrplan Physik");

    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.get(".status-badge").text()).toBe(t("jobs.status.running"));
    await vi.advanceTimersByTimeAsync(2000);

    expect(wrapper.get(".status-badge").text()).toBe(t("jobs.status.done"));
    expect(wrapper.emitted("ended")?.[0]).toEqual([job("done")]);
  });

  it("says why a job failed, in its own words", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("failed", "download_refused"));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.text()).toContain(t("jobs.failures.download_refused"));
    expect(wrapper.emitted("ended")).toHaveLength(1);
  });

  it("says that a job the server does not have is gone", async () => {
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "not_found"));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.text()).toContain(t("jobs.gone"));
    expect(wrapper.emitted("gone")).toHaveLength(1);
  });

  it("says when an answer did not come, until the next one does", async () => {
    vi.spyOn(api, "getJob")
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(job("running"));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.text()).toContain(t("jobs.trouble"));
    await vi.advanceTimersByTimeAsync(2000);

    expect(wrapper.text()).not.toContain(t("jobs.trouble"));
  });

  it("announces each change of state in a region that is there from the start", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue(job("failed", "url_not_allowed"));
    const wrapper = shown();
    const region = wrapper.get("[role=status]");
    expect(region.text()).toBe("");

    await vi.advanceTimersByTimeAsync(1000);

    expect(region.text()).toContain(t("jobs.status.failed"));
    expect(region.text()).toContain("Lehrplan Physik");
    expect(region.text()).toContain(t("jobs.failures.url_not_allowed"));
  });

  it("stops asking once the page drops it", async () => {
    const asked = vi.spyOn(api, "getJob").mockResolvedValue(job("running"));
    const wrapper = shown();
    await vi.advanceTimersByTimeAsync(1000);

    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(asked).toHaveBeenCalledTimes(1);
  });
});
