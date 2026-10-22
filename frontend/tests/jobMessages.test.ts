import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { t } from "@/i18n/de";
import { JOB_FAILURE_CODES, jobFailureText } from "@/jobMessages";

import { sourceFiles } from "./sources";

/**
 * The codes a job ends with (backend app/): a PermanentError's, the outcome's
 * own (app/jobs/outcome.py) and the queue's for a lost lease (app/jobs/queue.py).
 */
function backendJobCodes(): Set<string> {
  const code = sourceFiles(join(process.cwd(), "..", "backend", "app"), /\.py$/)
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");
  return new Set(
    [
      ...code.matchAll(/PermanentError\(\s*"([a-z_]+)"/g),
      ...code.matchAll(/fail\(\s*connection,\s*job,\s*"([a-z_]+)"/g),
      ...code.matchAll(/'code',\s*'([a-z_]+)'/g),
    ].map(([, found]) => found),
  );
}

describe("why a job failed, in the page's words", () => {
  it("reads the backend's codes", () => {
    const codes = backendJobCodes();
    expect(codes).toContain("download_refused");
    expect(codes).toContain("handler_error");
    expect(codes).toContain("lease_lost");
  });

  it.each(JOB_FAILURE_CODES)("%s is a code a job ends with", (code) => {
    expect(backendJobCodes()).toContain(code);
  });

  it("has words for every code a job ends with", () => {
    // the other way round: a new code of the backend would otherwise reach the page as the general words
    const worded = new Set<string>(JOB_FAILURE_CODES);
    expect([...backendJobCodes()].filter((code) => !worded.has(code))).toEqual([]);
  });

  it.each(JOB_FAILURE_CODES)("%s has German words of its own", (code) => {
    const text = jobFailureText(code);

    expect(text).not.toContain("jobs.");
    expect(text).not.toBe(t("jobs.failedUnknown"));
  });

  it("are the general ones for a code the page does not know, or for none", () => {
    expect(jobFailureText("something_new")).toBe(t("jobs.failedUnknown"));
    expect(jobFailureText(null)).toBe(t("jobs.failedUnknown"));
  });
});
