import type { CurriculumDocument } from "@/api";

/** A document as the server gives it: the caller's own draft, never frozen, no work or IRI yet. */
export function documentOf(changes: Partial<CurriculumDocument> = {}): CurriculumDocument {
  return {
    id: "d1",
    source_id: "s1",
    conversion_id: "c1",
    own: true,
    title: "Lehrplan Physik",
    document_type_iri: null,
    sector: "school",
    regions: ["DE-NW"],
    issuer: null,
    edition: null,
    work: null,
    iri: null,
    revision: 1,
    frozen_at: null,
    copy_of: null,
    created_at: "2026-10-29T10:00:00Z",
    extraction: null,
    ...changes,
  };
}
