// A register entry's conversion into blocks (backend app/api/conversions.py): asked for,
// followed while its job runs, and read page by page. It is reached through the entry, and
// whoever may read the entry's file may read its conversion (app/api/source_content.py).
import { apiFetch } from "./http";

/** A failed conversion may be asked for again; a waiting or a done one comes back as it is. */
export type ConversionStatus = "pending" | "done" | "failed";
/** What a block is (backend app/conversion/base.py, BlockKind). */
export type BlockKind = "text" | "table" | "page_header" | "page_footer";
/** What the conversion noticed in the text (backend FindingCode). */
export type FindingCode = "unmapped_symbol" | "encoding_suspect" | "text_dropped";
/** Why the conversion dropped words, a `text_dropped` finding's `reason` (backend DropReason). */
export type DropReason = "vertical" | "off_page" | "tiny" | "unplaced";

export interface ConversionFinding {
  code: string;
  params: Record<string, unknown>;
}

/** How far the conversion of the entry's file is (backend ConversionOut). */
export interface Conversion {
  id: string;
  engine: string;
  engine_version: string | null;
  status: ConversionStatus;
  /** Why it failed: the conversion's own code, or the code of the job that ended without it. */
  error_code: string | null;
  job_id: string | null;
  pages: number | null;
  /** The number printed on each page, where the conversion found one. */
  printed_pages: (string | null)[] | null;
  findings: ConversionFinding[];
  created_at: string;
  finished_at: string | null;
}

/** A table's cell; `id` is `T<table>:r<row>c<column>`, all counted from 1. */
export interface BlockCell {
  id: string;
  /** The page the cell stands on: a table may run on from the page before. */
  page: number;
  row: number;
  column: number;
  text: string;
  header: boolean;
}

/** A block of the file, in reading order; `id` is `p<page>-b<n>`, what a quote cites. */
export interface Block {
  id: string;
  page: number;
  kind: BlockKind;
  text: string;
  /** x0, top, x1, bottom in PDF points. */
  bbox: [number, number, number, number];
  font_size: number | null;
  bold: boolean;
  italic: boolean;
  /** A table's cells; none for any other kind. */
  cells: BlockCell[];
}

/**
 * A table begun on an earlier page that runs on to this one (backend ContinuedOut): a table joined
 * over pages is one block, on its first; here are its cells on this page.
 */
export interface ContinuedTable {
  /** The table's block, `p<page>-b<n>` of the page it begins on. */
  id: string;
  page: number;
  cells: BlockCell[];
}

/** One page's blocks (backend PageOut). */
export interface BlockPage {
  page: number;
  printed_page: string | null;
  blocks: Block[];
  /** The tables of earlier pages that run on here, before the page's own blocks. */
  continued: ContinuedTable[];
}

function conversionPath(sourceId: string): string {
  return `/api/v1/sources/${encodeURIComponent(sourceId)}/conversion`;
}

/**
 * Asks for the conversion of the entry's file: a new one, or a failed one again, with its job
 * (202); the one there - waiting, running or done - as it is (200). Refusals: 403 `file_hidden`,
 * 404 `no_file`, 422 `not_pdf`.
 */
export function askConversion(sourceId: string): Promise<Conversion> {
  return apiFetch<Conversion>(`/api/v1/sources/${encodeURIComponent(sourceId)}/conversions`, { method: "POST" });
}

/** The conversion of the entry's file; 404 `no_conversion` before any was asked for. */
export function getConversion(sourceId: string): Promise<Conversion> {
  return apiFetch<Conversion>(conversionPath(sourceId));
}

/** The blocks of page `page` (from 1); 409 `not_converted` before it is done, 404 `no_such_page` past its end. */
export function getBlocks(sourceId: string, page: number): Promise<BlockPage> {
  return apiFetch<BlockPage>(`${conversionPath(sourceId)}/blocks?page=${page}`);
}
