import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type Job } from "@/api";
import JobProgress from "@/components/JobProgress.vue";
import { isolate } from "@/bidi";
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

  it("quiet, says no change of the job's state, but that the server does not answer", async () => {
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(job("running"))
      .mockRejectedValue(new ApiError("server", 503, "service_unavailable"));
    const wrapper = mount(JobProgress, { props: { jobId: "j1", label: "Lehrplan Physik", quiet: true } });
    const region = () => wrapper.get("[role=status]").text();

    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.get(".status-badge").text()).toBe(t("jobs.status.running"));
    expect(region()).toBe("");

    await vi.advanceTimersByTimeAsync(2000);
    // the page around it says how the job ends; that its progress stalls only this can say
    expect(region()).toBe(t("jobs.announce", { label: isolate("Lehrplan Physik"), status: t("jobs.trouble") }));
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

    expect(wrapper.text()).toContain(t("jobs.goneReasons.not_found"));
    expect(wrapper.emitted("gone")).toHaveLength(1);
  });

  it("says a job this account may not follow is not its to follow, not that it is gone", async () => {
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("forbidden", 403, "forbidden"));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.text()).toContain(t("jobs.goneReasons.forbidden"));
    expect(wrapper.text()).not.toContain(t("jobs.goneReasons.not_found"));
  });

  it("announces that the server does not answer, and that it answers again", async () => {
    vi.spyOn(api, "getJob")
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(job("running"));
    const wrapper = shown();
    const region = wrapper.get("[role=status]");

    await vi.advanceTimersByTimeAsync(1000);
    expect(region.text()).toContain(t("jobs.trouble"));
    await vi.advanceTimersByTimeAsync(2000);

    expect(region.text()).not.toContain(t("jobs.trouble"));
    expect(region.text()).toContain(t("jobs.status.running"));
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
    expect(region.text()).toContain(isolate("Lehrplan Physik"));
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

  it("shows how far a check has come, without reading out every address", async () => {
    const checking = (done: number): Job => ({
      ...job("running"),
      kind: "source.check",
      progress: { code: "checking", params: { done, total: 1871 } },
    });
    vi.spyOn(api, "getJob").mockResolvedValueOnce(checking(12)).mockResolvedValue(checking(13));
    const wrapper = shown("Prüfung der Saat");

    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.get(".job__progress").text()).toBe(t("jobs.progress.checking", { done: 12, total: 1871 }));
    const heard = wrapper.get("[role=status]").text();
    await vi.advanceTimersByTimeAsync(2000);

    expect(wrapper.get(".job__progress").text()).toBe(t("jobs.progress.checking", { done: 13, total: 1871 }));
    // the region says the state; the count only shows, or every address would be read out
    expect(wrapper.get("[role=status]").text()).toBe(heard);
    expect(heard).not.toContain("12");
  });

  it("tells the page of each progress that is new, not of the same one again", async () => {
    const at = (code: string, done: number): Job => ({
      ...job("running"),
      kind: "extract.run",
      progress: { code, params: { done, total: 3 } },
    });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(at("extract_statements", 0))
      .mockResolvedValueOnce(at("extract_statements", 0))
      .mockResolvedValue(at("extract_statements", 1));
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(2000);
    await vi.advanceTimersByTimeAsync(4000);

    expect(wrapper.emitted("progress")).toEqual([
      [{ code: "extract_statements", params: { done: 0, total: 3 } }],
      [{ code: "extract_statements", params: { done: 1, total: 3 } }],
    ]);
  });

  it("shows that a conversion is under way, a progress that needs no numbers", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue({
      ...job("running"),
      kind: "source.convert",
      progress: { code: "converting", params: {} },
    });
    const wrapper = shown("Umwandlung in Blöcke");

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.get(".job__progress").text()).toBe(t("jobs.progress.converting"));
  });

  it("shows how far an extraction has come, with no heading left to the model too", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue({
      ...job("running"),
      kind: "extract.run",
      progress: { code: "extract_outline", params: { headings: 0 } },
    });
    const wrapper = shown("Kernlehrplan Physik");

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.get(".job__progress").text()).toBe(
      "Die Gliederung wird gebaut. Überschriften, die das Sprachmodell einordnet: 0.",
    );
  });

  it("shows no progress for a code named as what every object has", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue({
      ...job("running"),
      progress: { code: "constructor", params: {} },
    });
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.find(".job__progress").exists()).toBe(false);
    expect(wrapper.get(".status-badge").text()).toBe(t("jobs.status.running"));
  });

  it("shows no progress it has no words for, nor one whose numbers are missing", async () => {
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce({ ...job("running"), progress: { code: "sorting", params: { page: 3 } } })
      .mockResolvedValue({ ...job("running"), progress: { code: "checking", params: { done: "viele" } } });
    const wrapper = shown();

    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.find(".job__progress").exists()).toBe(false);
    await vi.advanceTimersByTimeAsync(2000);

    expect(wrapper.find(".job__progress").exists()).toBe(false);
  });
});
