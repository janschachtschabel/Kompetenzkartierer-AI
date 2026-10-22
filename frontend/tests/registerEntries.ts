// Register entries, pages of them and jobs as the server answers, for the tests of the register's pages.
import type { Job, SourceDetail, SourceEntry, SourcePage } from "@/api";

export function entry(id: string, title: string, overrides: Partial<SourceEntry> = {}): SourceEntry {
  return {
    id,
    title,
    provenance: "upload",
    rights_status: "unklar",
    source_type: null,
    register_status: "acquired",
    country: null,
    sector: null,
    url: null,
    file: { name: `${title}.pdf`, mime: "application/pdf", size: 8, sha256: "ab" },
    mine: true,
    created_at: "2026-10-22T10:00:00Z",
    updated_at: "2026-10-22T10:00:00Z",
    ...overrides,
  };
}

export function page(entries: SourceEntry[], total = entries.length, offset = 0): SourcePage {
  return { entries, total, limit: 50, offset };
}

/** A promise the test settles when it chooses: the order two answers arrive in. */
export function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve: (value: T) => void = () => {};
  let reject: (error: unknown) => void = () => {};
  const promise = new Promise<T>((settle, fail) => {
    resolve = settle;
    reject = fail;
  });
  return { promise, resolve, reject };
}

export function job(status: Job["status"]): Job {
  return {
    id: "j1",
    kind: "source.fetch",
    status,
    progress: null,
    error_code: null,
    cancel_requested: false,
    attempts: 1,
    max_attempts: 3,
    created_at: "2026-10-22T10:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

/** A seed candidate as its page reads it: what the dataset said, what the check found, how to reach it. */
export function detail(overrides: Partial<SourceDetail> = {}): SourceDetail {
  return {
    ...entry("s1", "Rheinland-Pfalz · Physik · Gymnasium", {
      provenance: "vergleichsdatensatz-v62.493",
      register_status: "reachable",
      source_type: "amtlich",
      country: "DE-RP",
      url: "https://lehrplaene.bildung-rp.de/physik.pdf",
      file: null,
      mine: false,
    }),
    license: null,
    rights_evidence: null,
    acquisitions: [],
    seed: {
      dataset: "vergleichsdatensatz-v62.493",
      school_form: "Gymnasium",
      stage: "Sekundarstufe I",
      subject_key: "physik",
      subject: "Physik",
      grade_from: 7,
      grade_to: 10,
      binding: "verbindlich",
      archive_url: "https://web.archive.org/web/2024/https://lehrplaene.bildung-rp.de/physik.pdf",
      archived_at: "20240101120000",
      evidence: null,
    },
    access_notes: [
      {
        categories: ["Sperre 403", "Archiv"],
        field: "URL",
        text: "Das Landesportal sperrt automatische Abrufe; eine Archivkopie liegt vor.",
        url: "https://web.archive.org/web/2024/https://lehrplaene.bildung-rp.de/",
        // the dataset's own bookkeeping, no words for a reader
        origin: "laender_meta",
      },
    ],
    check: {
      outcome: "reachable",
      status_code: 200,
      detected_type: "pdf",
      size: 3_355_443,
      checked_at: "2026-10-22T10:30:00Z",
    },
    ...overrides,
  };
}
