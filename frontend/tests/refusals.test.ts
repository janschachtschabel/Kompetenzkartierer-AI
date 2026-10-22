import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { REFUSAL_CODES, refusalText } from "@/refusals";

const API = join(process.cwd(), "..", "backend", "app", "api");

/**
 * The codes the backend answers with: the table of app/api/errors.py and its own
 * one, and every route's own - a Refusal's, and a rate limit's (sources.py).
 */
function backendCodes(): Set<string> {
  const source = readFileSync(join(API, "errors.py"), "utf8");
  const table = /CODES = \{([\s\S]*?)\}/.exec(source)?.[1] ?? "";
  const own = [...source.matchAll(/^[A-Z_]+ = "([a-z_]+)"$/gm)].map(([, code]) => code);
  const routes = readdirSync(API)
    .filter((name) => name.endsWith(".py"))
    .map((name) => readFileSync(join(API, name), "utf8"))
    .join("\n");
  const refused = [...routes.matchAll(/Refusal\(\s*\d{3},\s*"([a-z_]+)"/g)].map(([, code]) => code);
  const limited = [...routes.matchAll(/_within_limit\([^)]*?"([a-z_]+)"\s*\)/g)].map(([, code]) => code);
  const tabled = [...table.matchAll(/:\s*"([a-z_]+)"/g)].map(([, code]) => code);
  return new Set([...tabled, ...own, ...refused, ...limited]);
}

describe("the refusals the page says in its own words", () => {
  it("read the backend's codes", () => {
    const codes = backendCodes();
    expect(codes).toContain("service_unavailable");
    expect(codes).toContain("validation_failed");
    // a route's own, and a rate limit's
    expect(codes).toContain("file_too_large");
    expect(codes).toContain("too_many_imports");
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
