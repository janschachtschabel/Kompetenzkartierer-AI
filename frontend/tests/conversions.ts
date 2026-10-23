// Conversions and their blocks as the server answers, for the tests of the conversion's pages.
import type { Block, BlockCell, BlockPage, Conversion } from "@/api";

export function conversion(overrides: Partial<Conversion> = {}): Conversion {
  return {
    id: "c1",
    engine: "pdfplumber",
    engine_version: "0.11.10",
    status: "done",
    error_code: null,
    job_id: "j1",
    pages: 3,
    printed_pages: [null, "1", "2"],
    findings: [],
    created_at: "2026-10-23T08:00:00Z",
    finished_at: "2026-10-23T08:01:00Z",
    ...overrides,
  };
}

export function block(id: string, text: string, overrides: Partial<Block> = {}): Block {
  return {
    id,
    page: Number(/^p(\d+)-/.exec(id)?.[1] ?? 1),
    kind: "text",
    text,
    bbox: [72, 100, 520, 130],
    font_size: 11,
    bold: false,
    italic: false,
    cells: [],
    ...overrides,
  };
}

export function cell(id: string, text: string, overrides: Partial<BlockCell> = {}): BlockCell {
  const [, row, column] = /r(\d+)c(\d+)$/.exec(id) ?? ["", "1", "1"];
  return { id, page: 2, row: Number(row), column: Number(column), text, header: false, ...overrides };
}

/** A table on page 2 that runs on to page 3: a bold header row, and a cell left empty by the file. */
export function table(): Block {
  return block("p2-b2", "| Kompetenz | Stufe |", {
    kind: "table",
    cells: [
      cell("T1:r1c1", "Kompetenz", { header: true }),
      cell("T1:r1c2", "Stufe", { header: true }),
      cell("T1:r2c1", "Experimentieren"),
      cell("T1:r2c2", "1"),
      cell("T1:r3c1", "Modellieren", { page: 3 }),
    ],
  });
}

export function blockPage(page: number, blocks: Block[], printed: string | null = null): BlockPage {
  return { page, printed_page: printed, blocks };
}
