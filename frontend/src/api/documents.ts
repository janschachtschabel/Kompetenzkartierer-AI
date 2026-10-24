// Documents and their extraction (backend app/api/documents.py): made of an entry's finished
// conversion with their extraction started at once; one extraction of a document waits or runs at
// a time - a start while one does gives that one back.
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
   * owner, an admin - null for an editor, who reads the status. */
  extraction: { job_id: string | null; status: JobStatus } | null;
}

export interface DocumentStarted {
  document: CurriculumDocument;
  job: Job;
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

function documentPath(id: string): string {
  return `/api/v1/documents/${encodeURIComponent(id)}`;
}
