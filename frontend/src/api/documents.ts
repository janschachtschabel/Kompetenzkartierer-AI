// Documents and their extraction (backend app/api/documents.py): made of an entry's finished
// conversion with their extraction started at once; one extraction or repair of a document waits or
// runs at a time - a start while one does gives that one back. Their findings
// (app/api/document_findings.py).
import { apiFetch } from "./http";
import type { Job, JobStatus } from "./jobs";

/** A notation of cv:EducationSectors (backend ontology/ontologie/cur-vokabular.ttl). */
export type Sector = "elementary" | "school" | "vocational" | "higher" | "adult";

export interface CurriculumDocument {
  id: string;
  source_id: string;
  conversion_id: string;
  /** The caller's own: who may start its extraction. */
  own: boolean;
  title: string | null;
  document_type_iri: string | null;
  sector: string;
  /** ISO 3166-2 codes, "DE" for all Länder. */
  regions: string[];
  created_at: string;
  /** The latest extraction job, whatever became of it; its id only for who may follow it - the
   * owner, an admin - null for an editor, who reads the status; why it failed, for every reader. */
  extraction: { job_id: string | null; kind: string; status: JobStatus; error_code: string | null } | null;
}

/** The job kind of a document's repair: X6, then X5 again (backend app/pipeline/x6_repair.py). */
export const REPAIR_KIND = "extract.repair";

/** The job kind of a document checked again: X5, with no model (backend app/api/document_check.py). */
export const CHECK_KIND = "extract.check";

/** How grave a finding is (backend app/domain/l1.py, Severity). */
export type FindingSeverity = "violation" | "warning" | "info";

export interface DocumentFinding {
  /** "x5.wording_not_found", "shacl.StatementShape" … */
  rule: string;
  severity: FindingSeverity;
  /** The stage whose run found it, "X5". */
  stage: string | null;
  /** The row it is about: its kind ("statement", "node", "document" …), and its wording or title. */
  focus: { kind: string; id: string; label: string | null };
  /** The property, or the place in the model's answer, where it names one. */
  path: string | null;
  /** The server's: English but where `message_lang` says otherwise. */
  message: string;
  /** The message's language where the stage knew it - SHACL's German, "de" -; else English. */
  message_lang: string | null;
  /** The work package it names, "E2". */
  unit: string | null;
}

export interface FindingsPage {
  /** Of all the document's findings. */
  counts: Record<FindingSeverity, number>;
  /** Gravest first, at most 500. */
  findings: DocumentFinding[];
  /** More were found than are listed. */
  truncated: boolean;
  /** The work packages a repair would ask again: to the owner, once X5 has checked the document. */
  repairable: string[];
}

/** How far X4 has come with a unit: done, open; read typed by X3 (frame), or not at all (none). */
export type UnitState = "done" | "open" | "frame" | "none";

/** One of X2's work packages of a document (backend app/pipeline/x2_segments.py). */
export interface Unit {
  /** "E0", "E1" … in the document's order; E0 the title pages. */
  key: string;
  /** The titles from the top down to its section; none for the title pages, or a document of no headings. */
  path: string[];
  /** Its first and last page. */
  pages: [number, number];
  state: UnitState;
  /** The statements X4 wrote of it, once it is done. */
  statements: number | null;
}

export interface DocumentStarted {
  document: CurriculumDocument;
  job: Job;
  /** False where the account's document of the entry being extracted came back instead (200). */
  made: boolean;
}

/** How a run of a stage stands: its outcome, else running, or left with its attempt. */
export type RunState = "done" | "failed" | "budget_exhausted" | "running" | "abandoned";

export interface Run {
  /** The stage's notation, "X1". */
  stage: string;
  attempt: number | null;
  state: RunState;
  started_at: string;
  finished_at: string | null;
  /** What broke a failed run, by its type ("LeaseLost"). */
  failure: string | null;
}

export interface DocumentRequest {
  source_id: string;
  conversion_id: string;
  sector: Sector;
  regions: string[];
}

/** Makes a document of the conversion and starts its extraction. */
export function makeDocument(asked: DocumentRequest): Promise<DocumentStarted> {
  return apiFetch<DocumentStarted>("/api/v1/documents", { method: "POST", body: JSON.stringify(asked) });
}

/** Starts the document's extraction again; the one waiting or running where there is one. */
export function startExtraction(documentId: string): Promise<Job> {
  return apiFetch<Job>(`${documentPath(documentId)}/extraction`, { method: "POST" });
}

/** Starts the document's repair; the extraction or repair waiting or running where there is one. */
export function startRepair(documentId: string): Promise<Job> {
  return apiFetch<Job>(`${documentPath(documentId)}/repair`, { method: "POST" });
}

/**
 * Checks the document again (X5, no model asked): the job made, or the one of the document waiting or running
 * where the caller may follow it. It goes in the owner's lane: who is not the owner follows it no further than
 * this answer. 409 `not_checked`, `frozen`, `job_open`; 403 `file_hidden`.
 */
export function startDocumentCheck(documentId: string): Promise<Job> {
  return apiFetch<Job>(`${documentPath(documentId)}/check`, { method: "POST" });
}

/** The documents the caller may read, of one entry where `sourceId` names it; the newest first. */
export function listDocuments(sourceId?: string): Promise<CurriculumDocument[]> {
  const query = sourceId ? `?${new URLSearchParams({ source_id: sourceId })}` : "";
  return apiFetch<CurriculumDocument[]>(`/api/v1/documents${query}`);
}

export function getDocument(id: string): Promise<CurriculumDocument> {
  return apiFetch<CurriculumDocument>(documentPath(id));
}

/** The runs of the document's stages, in the order they began. */
export function getRuns(id: string): Promise<Run[]> {
  return apiFetch<Run[]>(`${documentPath(id)}/runs`);
}

/** The document's units, in its order; none before X2 has parted it. */
export function getUnits(id: string): Promise<Unit[]> {
  return apiFetch<Unit[]>(`${documentPath(id)}/units`);
}

/** What the stages found on the document, gravest first. */
export function getFindings(id: string): Promise<FindingsPage> {
  return apiFetch<FindingsPage>(`${documentPath(id)}/findings`);
}

function documentPath(id: string): string {
  return `/api/v1/documents/${encodeURIComponent(id)}`;
}
