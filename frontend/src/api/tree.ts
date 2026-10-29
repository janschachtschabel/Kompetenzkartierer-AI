// A document's nodes and statements as the editor reads them (backend app/api/document_tree.py), the form
// their fields follow (app/api/profiles.py), and the pages of the conversion the document was read off -
// the blocks its anchors name (app/api/document_blocks.py).
import type { BlockPage } from "./conversions";
import type { FindingSeverity } from "./documents";
import { apiFetch } from "./http";

/** A field's value: a text, a value's IRI, the IRIs of a field of many; none where it is unset. */
export type FieldValue = string | string[] | null;

/** Where a node's title or a statement stands in the document (backend AnchorOut). */
export interface TreeAnchor {
  id: string;
  /** Physical pages, from 1. */
  page_start: number | null;
  page_end: number | null;
  /** As the document prints it. */
  printed_page: string | null;
  /** The passage found. */
  quote: string | null;
  /** How it was found (cv:MatchKinds); none before X5 looked. */
  match_kind: string | null;
  match_score: number | null;
  /** In the document's order. */
  blocks: string[];
}

export interface TreeStatement {
  id: string;
  position: number;
  /** By the keys of the form's statement fields, each of them. */
  fields: Record<string, FieldValue>;
  origin: string;
  review_status: string;
  /** The change of the statement an edit of it names. */
  revision: number;
  /** Given when its document was frozen; a draft copy's rows bring theirs. */
  iri: string | null;
  text_hash: string;
  anchors: TreeAnchor[];
}

export interface TreeNode {
  id: string;
  position: number;
  /** By the keys of the form's node fields, each of them. */
  fields: Record<string, FieldValue>;
  /** Its code is its position: the source names none. */
  code_assigned: boolean;
  origin: string;
  review_status: string;
  revision: number;
  iri: string | null;
  /** On the node and its anchors, its statements and theirs - not its children's. */
  findings: Record<FindingSeverity, number>;
  anchors: TreeAnchor[];
  statements: TreeStatement[];
  children: TreeNode[];
}

export interface Tree {
  /** The caller may edit the nodes and statements now. */
  editable: boolean;
  /** The caller may set their review status now. */
  reviewable: boolean;
  /** By review status (cv:ReviewStatuses), each of them. */
  counts: { nodes: Record<string, number>; statements: Record<string, number> };
  /** From the top, in their order. */
  nodes: TreeNode[];
}

/** A value of a list field: a concept of the core vocabulary or the sector's profile (backend ValueOut). */
export interface FormValue {
  iri: string;
  notation: string | null;
  label: string;
  alt_labels: string[];
  definition: string | null;
  /** skos:scopeNote. */
  note: string | null;
  /** What it is not for. */
  delimitation: string | null;
  examples: string[];
  /** The core values it refines: a node type's function, a subkind's kind. */
  broader: string[];
}

export type FieldKind = "text" | "longtext" | "concept" | "concepts";

export interface FormField {
  key: string;
  kind: FieldKind;
  required: boolean;
  many: boolean;
  /** Signs, for a text. */
  most: number | null;
  /** A list's, active ones in the order of their labels; none for a text. */
  values: FormValue[] | null;
}

export interface Form {
  sector: string;
  profile: string;
  node: FormField[];
  statement: FormField[];
}

/** A page of the document's own conversion, with the count of its pages (backend DocumentPageOut). */
export interface DocumentPage extends BlockPage {
  pages: number;
}

/** The document's nodes and statements; 404 `no_document` to one who may not read it. */
export function getTree(documentId: string): Promise<Tree> {
  return apiFetch<Tree>(`${documentPath(documentId)}/tree`);
}

/** The fields of a node and of a statement in the sector's profile; 404 `unknown_sector`. */
export function getForm(sector: string): Promise<Form> {
  return apiFetch<Form>(`/api/v1/profiles/${encodeURIComponent(sector)}/form`);
}

/** Page `page` (from 1) of the conversion the document was read off; 403 `file_hidden`, 404 `no_such_page`. */
export function getDocumentBlocks(documentId: string, page: number): Promise<DocumentPage> {
  return apiFetch<DocumentPage>(`${documentPath(documentId)}/blocks?page=${page}`);
}

function documentPath(id: string): string {
  return `/api/v1/documents/${encodeURIComponent(id)}`;
}
