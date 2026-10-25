import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import type { DocumentFinding } from "@/api";
import { isolate } from "@/bidi";
import { findingText, focusText } from "@/findingWords";
import { messages, t } from "@/i18n/de";

import { sourceFiles } from "./sources";

function backendCode(): string {
  return sourceFiles(join(process.cwd(), "..", "backend", "app"), /\.py$/)
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");
}

/**
 * The rules whose findings X3 to X6 write, by name without their stage: a `Finding("x5.…"` of X5's
 * checks, a stage's own (`f"{…stage}.pattern_timeout"`), and what the reading of an answer notes
 * (`reading.note("unknown_block", …)`, app/pipeline/statement_read.py, x3_read.py).
 */
function backendRules(code: string): string[] {
  const named = [...code.matchAll(/Finding\(\s*"x[3-6]\.([a-z_]+)"/g)];
  const staged = [...code.matchAll(/Finding\(\s*f"\{[a-z_.]+\}\.([a-z_]+)"/g)];
  const noted = [...code.matchAll(/\bnote\(\s*"([a-z_]+)"/g)];
  return [...new Set([...named, ...staged, ...noted].map(([, rule]) => rule))].sort();
}

function finding(changes: Partial<DocumentFinding> = {}): DocumentFinding {
  return {
    rule: "x5.wording_not_found",
    severity: "violation",
    stage: "X5",
    focus: { kind: "statement", id: "s1", label: "Die Lernenden messen." },
    path: null,
    message: "the wording is not in the blocks its anchor names",
    unit: null,
    ...changes,
  };
}

describe("a finding in words", () => {
  it("finds the rules the backend writes", () => {
    const rules = backendRules(backendCode());

    expect(rules).toEqual(expect.arrayContaining(["wording_not_found", "unknown_block", "unanswered", "pattern_timeout"]));
  });

  it("has words for every rule X3 to X6 write", () => {
    // the reading's rules are named alike at every stage that reads an answer (x3., x4., x6.)
    for (const rule of backendRules(backendCode())) expect(Object.keys(messages.documents.findings.rules)).toContain(rule);
  });

  it("says a rule it has words for in them, whichever stage wrote it", () => {
    expect(findingText(finding())).toEqual({ text: t("documents.findings.rules.wording_not_found") });
    expect(findingText(finding({ rule: "x6.unknown_block", message: "a block the conversion does not hold" }))).toEqual({
      text: t("documents.findings.rules.unknown_block"),
    });
    expect(findingText(finding({ rule: "x1.unknown_block" }))).toEqual({ text: t("documents.findings.rules.unknown_block") });
  });

  it("quotes SHACL's German message as it is, and another message as the server's English", () => {
    const shacl = finding({ rule: "shacl.StatementShape", message: "Eine Aussage braucht genau einen Wortlaut." });

    expect(findingText(shacl)).toEqual({ text: "Eine Aussage braucht genau einen Wortlaut." });
    expect(findingText(finding({ rule: "x1.regions_differ", message: "the Länder read differ" }))).toEqual({
      text: "the Länder read differ",
      lang: "en",
    });
  });

  it("names what a finding is about by its kind, its wording or title, and the work package", () => {
    // the wording set apart, so its direction does not turn the sentence around it
    expect(focusText(finding())).toBe(
      t("documents.findings.about", { kind: t("documents.findings.kinds.statement"), label: isolate("Die Lernenden messen.") }),
    );
    expect(focusText(finding({ focus: { kind: "document", id: "d1", label: null }, unit: "E2" }))).toBe(
      t("documents.findings.inUnit", { what: t("documents.findings.kinds.document"), unit: "E2" }),
    );
    expect(focusText(finding({ focus: { kind: "work", id: "w1", label: null } }))).toBe("work");
  });
});
