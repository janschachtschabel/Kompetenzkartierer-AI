import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { REFUSAL_CODES, refusalText } from "@/refusals";

/** The codes the backend answers with (app/api/errors.py): its table and its own one. */
function backendCodes(): Set<string> {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "api", "errors.py"), "utf8");
  const table = /CODES = \{([\s\S]*?)\}/.exec(source)?.[1] ?? "";
  const own = [...source.matchAll(/^[A-Z_]+ = "([a-z_]+)"$/gm)].map(([, code]) => code);
  return new Set([...[...table.matchAll(/:\s*"([a-z_]+)"/g)].map(([, code]) => code), ...own]);
}

describe("the refusals the page says in its own words", () => {
  it("read the backend's codes", () => {
    const codes = backendCodes();
    expect(codes).toContain("service_unavailable");
    expect(codes).toContain("validation_failed");
  });

  it.each(REFUSAL_CODES)("%s is a code the backend sends", (code) => {
    // A text for a code nobody sends is wording nobody reads.
    expect(backendCodes()).toContain(code);
  });

  it.each(REFUSAL_CODES)("%s has German words", (code) => {
    const text = refusalText(code);

    expect(text).not.toBeNull();
    expect(text).not.toContain("refusals.");
  });

  it("are none for a code the page does not know, or for no code", () => {
    expect(refusalText("internal_server_error")).toBeNull();
    expect(refusalText(undefined)).toBeNull();
    expect(refusalText(42)).toBeNull();
  });
});
