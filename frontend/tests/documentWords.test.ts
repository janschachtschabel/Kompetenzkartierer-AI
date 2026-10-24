import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import type * as api from "@/api";
import { messages } from "@/i18n/de";

/** true where `A` and `B` name the same values; vue-tsc fails the list below where they do not. */
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;

const typesFollow: [
  Same<api.Sector, keyof typeof messages.documents.sectors>,
  Same<api.RunState, keyof typeof messages.documents.runStates>,
] = [true, true];

/** The notations of cv:EducationSectors in the core's vocabulary, as the backend loads them. */
function sectorNotations(): string[] {
  const path = join(process.cwd(), "..", "ontology", "ontologie", "cur-vokabular.ttl");
  const source = readFileSync(path, "utf8");
  const concepts = [...source.matchAll(/skos:inScheme cv:EducationSectors[^.]*?skos:notation "([a-z]+)"/gs)];
  return concepts.map(([, notation]) => notation).sort();
}

/** The values of RunState in backend app/db/runs.py. */
function runStates(): string[] {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "db", "runs.py"), "utf8");
  const literal = /^RunState = Literal\[([^\]]*)\]/m.exec(source)?.[1] ?? "";
  return [...literal.matchAll(/"([^"]+)"/g)].map(([, value]) => value).sort();
}

describe("the words of a document", () => {
  it("read the vocabulary's sectors and the backend's run states", () => {
    expect(sectorNotations()).toContain("school");
    expect(runStates()).toContain("abandoned");
    expect(typesFollow.every(Boolean)).toBe(true);
  });

  it("name every sector of the vocabulary, and no other", () => {
    // a sector without words would be a choice the form does not offer
    expect(Object.keys(messages.documents.sectors).sort()).toEqual(sectorNotations());
  });

  it("name every state a run is read in, and no other", () => {
    expect(Object.keys(messages.documents.runStates).sort()).toEqual(runStates());
  });
});
