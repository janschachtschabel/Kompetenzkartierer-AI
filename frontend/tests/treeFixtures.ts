// The rows of a document's tree and its form, as the backend answers them (app/api/document_tree.py,
// app/api/profiles.py), for the tests of the tree's view.
import type { Form, Tree, TreeNode, TreeStatement } from "@/api";

export const CV = "https://w3id.org/wlo/curriculum/vocab#";

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
  return { editable: true, reviewable: true, counts: { nodes: {}, statements: {} }, nodes, ...changes };
}

export function form_(sector = "school"): Form {
  return { sector, profile: "schule", node: [], statement: [] };
}
