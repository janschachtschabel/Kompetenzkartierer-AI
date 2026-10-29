// A row of a document's tree in words (TreeView, TreeRow; plan M1 9.7, Paket 9c J7): what it is, then a node's
// code, title and type - its function where it has none - or a statement's wording and kind, its review status
// and a node's findings. TreeRow shows the parts; the row's name says them as one sentence, apart by commas,
// so that a screen reader does not run them into one another.
import type { FieldValue, Form } from "@/api";
import type { Row } from "@/documentTree";
import { valueLabel } from "@/formWords";
import { t } from "@/i18n/de";
import { REVIEW_TONES, statusOf, statusWord } from "@/reviewStatus";

export interface RowParts {
  kind: Row["kind"];
  code: string | null;
  /** A node's title ("ohne Titel" where it has none), a statement's wording. */
  text: string;
  /** A node's type or function, a statement's kind, by the label of the sector's form. */
  type: string | null;
  status: string;
  tone: (typeof REVIEW_TONES)[keyof typeof REVIEW_TONES];
  /** A node's findings; none for a statement. */
  findings: number | null;
}

function text(value: FieldValue | undefined): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function rowParts(row: Row, form: Form): RowParts {
  const item = row.kind === "node" ? row.node : row.statement;
  const known = statusOf(item.review_status);
  const status = { status: statusWord(item.review_status), tone: known ? REVIEW_TONES[known] : "neutral" } as const;
  if (row.kind === "node") {
    const { fields, findings } = row.node;
    const type = text(fields.node_type);
    const named = type ?? text(fields.function);
    return {
      kind: "node",
      code: text(fields.code),
      text: text(fields.original_title) ?? t("documents.tree.untitled"),
      type: named ? valueLabel(form.node, type ? "node_type" : "function", named) : null,
      findings: findings.violation + findings.warning + findings.info,
      ...status,
    };
  }
  const kind = text(row.statement.fields.statement_kind);
  return {
    kind: "statement",
    code: null,
    text: text(row.statement.fields.verbatim) ?? "",
    type: kind ? valueLabel(form.statement, "statement_kind", kind) : null,
    findings: null,
    ...status,
  };
}

/** The row's name: its parts as one sentence. */
export function rowLabel(parts: RowParts): string {
  const findings = parts.findings ? t("documents.tree.findings", { count: parts.findings }) : null;
  return [t(`documents.tree.kinds.${parts.kind}`), parts.code, parts.text, parts.type, parts.status, findings]
    .filter((part): part is string => Boolean(part))
    .join(", ");
}
