// The rows of a document's tree and its form, as the backend answers them (app/api/document_tree.py,
// app/api/profiles.py), for the tests of the tree's view.
import type { Form, FormField, FormValue, Tree, TreeNode, TreeStatement } from "@/api";

export const CV = "https://w3id.org/wlo/curriculum/vocab#";
export const SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#";

export function statement_(id: string, changes: Partial<TreeStatement> = {}): TreeStatement {
  return {
    id,
    position: 1,
    fields: { verbatim: `Aussage ${id}` },
    origin: CV + "orig_model",
    review_status: CV + "rev_proposed",
    revision: 1,
    iri: null,
    text_hash: "h",
    anchors: [],
    ...changes,
  };
}

export function node_(id: string, changes: Partial<TreeNode> = {}): TreeNode {
  return {
    id,
    position: 1,
    fields: { original_title: `Knoten ${id}`, code: null },
    code_assigned: false,
    origin: CV + "orig_model",
    review_status: CV + "rev_proposed",
    revision: 1,
    iri: null,
    findings: { violation: 0, warning: 0, info: 0 },
    anchors: [],
    statements: [],
    children: [],
    ...changes,
  };
}

export function tree_(nodes: TreeNode[], changes: Partial<Tree> = {}): Tree {
  return { editable: true, reviewable: true, closed: null, counts: { nodes: {}, statements: {} }, nodes, ...changes };
}

export function value_(iri: string, label: string, changes: Partial<FormValue> = {}): FormValue {
  return {
    iri,
    notation: null,
    label,
    alt_labels: [],
    definition: null,
    note: null,
    delimitation: null,
    examples: [],
    broader: [],
    ...changes,
  };
}

function field(key: string, kind: FormField["kind"], values: FormValue[] | null = null, required = false): FormField {
  return { key, kind, required, many: kind === "concepts", most: kind === "text" ? 2000 : null, values };
}

/** The school's form, as far as the tests of the tree ask it. */
export function form_(sector = "school"): Form {
  return {
    sector,
    profile: "schule",
    node: [
      field("original_title", "text", null, true),
      field("function", "concept", [value_(CV + "fn_area", "Bereich"), value_(CV + "fn_unit", "Einheit")], true),
      field("node_type", "concept", [value_(SCHOOL + "Inhaltsbereich", "Inhaltsbereich", { broader: [CV + "fn_area"] })]),
      field("code", "text"),
    ],
    statement: [
      field("verbatim", "longtext", null, true),
      field("statement_kind", "concept", [value_(CV + "kind_learningOutcome", "Lernergebnis")], true),
      field("addressees", "concepts", [value_(CV + "addr_learner", "Lernende"), value_(CV + "addr_educator", "Lehrkräfte")], true),
      field("levelText", "text"),
    ],
  };
}
