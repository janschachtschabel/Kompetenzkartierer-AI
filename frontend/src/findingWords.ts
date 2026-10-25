// A document's findings in words (DocumentFindings.vue): what a rule found, in German where the page
// knows the rule - X5's checks and the reading of the model's answers, named alike at every stage that
// reads one (tests/findingWords.test.ts) -, SHACL's message as it is (German already), any other as
// the server's English, to be quoted; and the row it is about.
import type { DocumentFinding, FindingSeverity } from "@/api";
import { isolate } from "@/bidi";
import { messages, t } from "@/i18n/de";
import { word } from "@/registerWords";

/** A finding's pill by what its severity means (style.css, .status-badge). */
export const SEVERITY_TONES: Readonly<Record<FindingSeverity, string>> = {
  violation: "error",
  warning: "warning",
  info: "neutral",
};

/** In the gravest-first order the server lists them. */
export const SEVERITIES: readonly FindingSeverity[] = ["violation", "warning", "info"];

const RULES: Readonly<Record<string, string>> = messages.documents.findings.rules;

/** What the finding says, and `lang` "en" where it is the server's English. */
export function findingText(finding: DocumentFinding): { text: string; lang?: "en" } {
  const [stage, name] = finding.rule.split(".", 2);
  if (/^x\d$/.test(stage) && name && Object.hasOwn(RULES, name)) {
    return { text: t(`documents.findings.rules.${name}`) };
  }
  if (stage === "shacl") return { text: finding.message };
  return { text: finding.message, lang: "en" };
}

/** The row a finding is about: its kind, its wording or title set apart, the work package it names. */
export function focusText(finding: DocumentFinding): string {
  const { kind, label } = finding.focus;
  const named = word(messages.documents.findings.kinds, kind);
  const what = label ? t("documents.findings.about", { kind: named, label: isolate(label) }) : named;
  return finding.unit ? t("documents.findings.inUnit", { what, unit: finding.unit }) : what;
}
