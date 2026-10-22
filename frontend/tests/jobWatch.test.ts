import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type Job } from "@/api";
import { watchJob } from "@/jobWatch";

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
  vi.useFakeTimers();
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("following a job", () => {
  it("asks again after one, two, four and then every eight seconds while it runs", async () => {
    const asked = vi.spyOn(api, "getJob").mockResolvedValue(job("running"));
    watchJob("j1", { onState: () => {}, onGone: () => {} });

    const counts = [];
    for (const step of [1000, 2000, 4000, 8000, 8000]) {
      await vi.advanceTimersByTimeAsync(step - 1);
      counts.push(asked.mock.calls.length);
      await vi.advanceTimersByTimeAsync(1);
    }

    // just before each step the count is the one before it
    expect(counts).toEqual([0, 1, 2, 3, 4]);
    expect(asked).toHaveBeenCalledTimes(5);
  });

  it.each(["done", "failed", "cancelled"] as const)("stops once the job is %s, and says how it ended", async (status) => {
    const asked = vi.spyOn(api, "getJob").mockResolvedValue(job(status));
    const states: string[] = [];
    watchJob("j1", { onState: (state) => states.push(state.status), onGone: () => {} });

    await vi.advanceTimersByTimeAsync(60_000);

    expect(asked).toHaveBeenCalledTimes(1);
    expect(states).toEqual([status]);
  });

  it.each([
    ["unauthorized", new ApiError("unauthorized", 401)],
    ["forbidden", new ApiError("forbidden", 403, "forbidden")],
    ["not_found", new ApiError("server", 404, "not_found")],
  ] as const)("stops for good when the job is %s to this session", async (reason, error) => {
    const asked = vi.spyOn(api, "getJob").mockRejectedValue(error);
    const gone: string[] = [];
    watchJob("j1", { onState: () => {}, onGone: (why) => gone.push(why) });

    await vi.advanceTimersByTimeAsync(60_000);

    expect(asked).toHaveBeenCalledTimes(1);
    expect(gone).toEqual([reason]);
  });

  it("keeps asking through a lost connection, and says so", async () => {
    const asked = vi
      .spyOn(api, "getJob")
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(job("done"));
    const troubles: unknown[] = [];
    const states: string[] = [];
    watchJob("j1", { onState: (state) => states.push(state.status), onGone: () => {}, onTrouble: (error) => troubles.push(error) });

    await vi.advanceTimersByTimeAsync(3000);

    expect(asked).toHaveBeenCalledTimes(2);
    expect(troubles).toHaveLength(1);
    expect(states).toEqual(["done"]);
  });

  it("stops when the page lets go of it", async () => {
    const asked = vi.spyOn(api, "getJob").mockResolvedValue(job("running"));
    const watch = watchJob("j1", { onState: () => {}, onGone: () => {} });

    await vi.advanceTimersByTimeAsync(1000);
    watch.stop();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(asked).toHaveBeenCalledTimes(1);
  });

  it("asks no more once a handler lets go of it", async () => {
    const asked = vi.spyOn(api, "getJob").mockResolvedValue(job("running"));
    const watch = watchJob("j1", { onState: () => watch.stop(), onGone: () => {} });

    await vi.advanceTimersByTimeAsync(60_000);

    expect(asked).toHaveBeenCalledTimes(1);
  });

  it("says nothing of an answer that arrives after the page let go", async () => {
    let answer: (job: Job) => void = () => {};
    const asked = vi.spyOn(api, "getJob").mockImplementation(() => new Promise((resolve) => (answer = resolve)));
    const states: string[] = [];
    const watch = watchJob("j1", { onState: (state) => states.push(state.status), onGone: () => {} });

    await vi.advanceTimersByTimeAsync(1000);
    watch.stop();
    answer(job("running"));
    await vi.advanceTimersByTimeAsync(60_000);

    expect(states).toEqual([]);
    expect(asked).toHaveBeenCalledTimes(1);
  });
});
