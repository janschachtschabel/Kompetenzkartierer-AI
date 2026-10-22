// The source register (backend app/api/sources.py and source_register.py):
// what an account uploads or has fetched, and the entries it reads.
import { apiFetch } from "./http";

// The register's lists (backend app/sources/register.py)
export type Provenance =
  | "upload"
  | "url"
  | "vergleichsdatensatz-v62.493"
  | "laenderrecherche"
  | "ttl"
  | "recherche"
  | "redaktion";
export type RightsStatus = "amtlich" | "offen_lizenziert" | "geschuetzt" | "unklar";
export type SourceType = "amtlich" | "archiv" | "spiegel" | "sekundaer";
/** How far the register has come with the entry: `acquired` means its file is stored. */
export type RegisterStatus = "unchecked" | "reachable" | "unreachable" | "acquired";

export interface SourceFile {
  name: string;
  mime: string;
  size: number;
}

/** What an upload or an import answers with. */
export interface SourceOut {
  id: string;
  title: string;
  provenance: Provenance;
  rights_status: RightsStatus;
  register_status: RegisterStatus;
  file: SourceFile | null;
}

/** An import: its entry, and the job that fetches the file. */
export interface ImportStarted {
  source: SourceOut;
  job_id: string;
}

export interface SourceEntry extends Omit<SourceOut, "file"> {
  source_type: SourceType | null;
  country: string | null;
  /** A concept of the education sectors, by its IRI. */
  sector: string | null;
  url: string | null;
  file: (SourceFile & { sha256: string }) | null;
  /** The caller's own entry. */
  mine: boolean;
  created_at: string;
  updated_at: string;
}

export interface SourcePage {
  entries: SourceEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface SourceFilters {
  status?: RegisterStatus;
  provenance?: Provenance;
  country?: string;
  /** In the title or the address. */
  q?: string;
}

/** The register's page size, the server's own default. */
export const PAGE_SIZE = 50;
/** The longest title the backend keeps (MAX_TITLE_SIGNS), and the longest address it fetches. */
export const MAX_TITLE_SIGNS = 500;
export const MAX_URL_SIGNS = 2000;
export const MIB = 2 ** 20;

/** Uploads `file`; a blank `title` is left out, and the entry takes the file's name. */
export function uploadSource(file: File, title: string): Promise<SourceOut> {
  const form = new FormData();
  form.append("file", file);
  if (title.trim()) form.append("title", title.trim());
  return apiFetch<SourceOut>("/api/v1/sources", { method: "POST", body: form });
}

/** Enters `url` into the register and starts the job that fetches it. */
export function importSource(url: string, title: string): Promise<ImportStarted> {
  const body = title.trim() ? { url, title: title.trim() } : { url };
  return apiFetch<ImportStarted>("/api/v1/sources/import", { method: "POST", body: JSON.stringify(body) });
}

/** A page of the entries the caller sees, newest first; only the filters given are sent. */
export function listSources(
  filters: SourceFilters = {},
  { limit = PAGE_SIZE, offset = 0 }: { limit?: number; offset?: number } = {},
): Promise<SourcePage> {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) if (value) query.set(name, value);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return apiFetch<SourcePage>(`/api/v1/sources?${query}`);
}

export function getSource(id: string): Promise<SourceEntry> {
  return apiFetch<SourceEntry>(`/api/v1/sources/${encodeURIComponent(id)}`);
}
