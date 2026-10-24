import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { t } from "@/i18n/de";
import { JOB_PROGRESS } from "@/jobProgress";

import { sourceFiles } from "./sources";

function backendCode(): string {
  return sourceFiles(join(process.cwd(), "..", "backend", "app"), /\.py$/)
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");
}

/**
 * The progress codes the backend's jobs report, each with the numbers it sends: a
 * `report_progress(connection, job, "code", {"name": …})` (app/jobs/queue.py) and an
 * extraction's `report(connection, job, "code", name=…)` (app/pipeline/progress.py).
 */
function backendProgress(code: string): Record<string, string[]> {
  const found: Record<string, string[]> = {};
  for (const [, name, params] of code.matchAll(/report_progress\(\s*connection,\s*job,\s*"([a-z_]+)",\s*\{([^}]*)\}/g)) {
    found[name] = [...params.matchAll(/"([a-z_]+)":/g)].map(([, param]) => param);
  }
  for (const [, name, params] of code.matchAll(/\breport\(\s*connection,\s*job,\s*"([a-z_]+)"([^\n]*)/g)) {
    found[name] = [...params.matchAll(/([a-z_]+)=/g)].map(([, param]) => param);
  }
  return found;
}

function sorted(progress: Readonly<Record<string, readonly string[]>>): Record<string, string[]> {
  return Object.fromEntries(
    Object.entries(progress)
      .map(([code, params]) => [code, [...params].sort()] as const)
      .sort(([one], [other]) => one.localeCompare(other)),
  );
}

describe("how far a job has come, in the page's words", () => {
  it("reads the backend's codes with their numbers", () => {
    const found = backendProgress(backendCode());
    expect(found.checking).toEqual(["done", "total"]);
    expect(found.converting).toEqual([]);
    expect(found.extract_outline).toEqual(["headings"]);
  });

  it("has words for every code a job reports, with the numbers it sends, and for no other", () => {
    expect(sorted(JOB_PROGRESS)).toEqual(sorted(backendProgress(backendCode())));
  });

  it("knows every code an extraction may report (ProgressCode)", () => {
    const literal = /^ProgressCode = Literal\[([^\]]*)\]/m.exec(backendCode())?.[1] ?? "";
    const codes = [...literal.matchAll(/"([a-z_]+)"/g)].map(([, code]) => code);
    expect(codes).toContain("extract_profile");
    for (const code of codes) expect(Object.keys(JOB_PROGRESS)).toContain(code);
  });

  it("words each code with its numbers in it", () => {
    for (const [code, params] of Object.entries(JOB_PROGRESS)) {
      const text = t(`jobs.progress.${code}`, Object.fromEntries(params.map((param) => [param, 2])));
      expect(text, code).not.toBe(`jobs.progress.${code}`);
      expect(text, code).not.toContain("{");
    }
  });
});
