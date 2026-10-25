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
  Same<api.UnitState, keyof typeof messages.documents.units.states>,
  Same<api.FindingSeverity, keyof typeof messages.documents.findings.severities>,
] = [true, true, true, true];

/** The notations of cv:EducationSectors in the core's vocabulary, as the backend loads them. */
function sectorNotations(): string[] {
  const path = join(process.cwd(), "..", "ontology", "ontologie", "cur-vokabular.ttl");
  const source = readFileSync(path, "utf8");
  const concepts = [...source.matchAll(/skos:inScheme cv:EducationSectors[^.]*?skos:notation "([a-z]+)"/gs)];
  return concepts.map(([, notation]) => notation).sort();
}

/** The notations of the regions in the core's vocabulary, which the backend checks a document's against. */
function regionNotations(): string[] {
  const source = readFileSync(join(process.cwd(), "..", "ontology", "vokabulare", "laender.ttl"), "utf8");
  const concepts = [...source.matchAll(/skos:inScheme land:Regions[^.]*?skos:notation "([A-Z-]+)"/gs)];
  return concepts.map(([, notation]) => notation).sort();
}

/** The values of RunState in backend app/db/runs.py. */
function runStates(): string[] {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "db", "runs.py"), "utf8");
  const literal = /^RunState = Literal\[([^\]]*)\]/m.exec(source)?.[1] ?? "";
  return [...literal.matchAll(/"([^"]+)"/g)].map(([, value]) => value).sort();
}

/** The values of UnitState in backend app/pipeline/units.py. */
function unitStates(): string[] {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "pipeline", "units.py"), "utf8");
  const literal = /^UnitState = Literal\[([^\]]*)\]/m.exec(source)?.[1] ?? "";
  return [...literal.matchAll(/"([^"]+)"/g)].map(([, value]) => value).sort();
}

/** The values of Severity in backend app/domain/l1.py, as a finding is graded. */
function severities(): string[] {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "domain", "l1.py"), "utf8");
  const literal = /^Severity = Literal\[([^\]]*)\]/m.exec(source)?.[1] ?? "";
  return [...literal.matchAll(/"([^"]+)"/g)].map(([, value]) => value).sort();
}

/** The stages the backend's extraction job runs (STAGES in app/pipeline/run.py). */
function extractionStages(): string[] {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "pipeline", "run.py"), "utf8");
  const tuple = /^STAGES = \(([^)]*)\)/m.exec(source)?.[1] ?? "";
  return [...tuple.matchAll(/"([^"]+)"/g)].map(([, value]) => value);
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

  it("offer every region of the vocabulary as a Land, and no other", () => {
    // a Land the form offers that the vocabulary lacks would be refused (422 unknown_region)
    expect(regionNotations()).toContain("DE-NW");
    expect(Object.keys(messages.sources.countries).sort()).toEqual(regionNotations());
  });

  it("name every state a run is read in, and no other", () => {
    expect(Object.keys(messages.documents.runStates).sort()).toEqual(runStates());
  });

  it("name every state of a work package, and no other", () => {
    expect(unitStates()).toContain("frame");
    expect(Object.keys(messages.documents.units.states).sort()).toEqual(unitStates());
  });

  it("name every stage the extraction runs", () => {
    expect(extractionStages()).toContain("X1");
    for (const stage of extractionStages()) expect(Object.keys(messages.documents.stages)).toContain(stage);
  });

  it("name the stage a repair runs", () => {
    const source = readFileSync(join(process.cwd(), "..", "backend", "app", "pipeline", "x6_repair.py"), "utf8");
    expect(source).toContain('"X6",');
    expect(Object.keys(messages.documents.stages)).toContain("X6");
  });

  it("name every severity of a finding, and no other", () => {
    expect(severities()).toContain("violation");
    expect(Object.keys(messages.documents.findings.severities).sort()).toEqual(severities());
  });
});
