import { describe, expect, it } from "vitest";

import { filtersFromQuery, queryOf, sameFilters } from "@/registerFilters";

describe("the register's filter in the address", () => {
  it("is read from it", () => {
    expect(filtersFromQuery({ kandidaten: "1", stand: "unreachable" })).toEqual({ candidates: true, status: "unreachable" });
    expect(filtersFromQuery({})).toEqual({ candidates: false, status: "" });
  });

  it.each([
    ["a status the register does not know", { stand: "kaputt" }],
    ["a status twice", { stand: ["acquired", "reachable"] }],
    ["candidates by another word", { kandidaten: "ja" }],
    ["a parameter without its value", { kandidaten: null, stand: null }],
  ])("leaves out %s", (_what, query) => {
    expect(filtersFromQuery(query)).toEqual({ candidates: false, status: "" });
  });

  it("is written as it is read, and only with what is set", () => {
    expect(queryOf({ candidates: true, status: "acquired" })).toEqual({ kandidaten: "1", stand: "acquired" });
    expect(queryOf({ candidates: false, status: "reachable" })).toEqual({ stand: "reachable" });
    expect(queryOf({ candidates: false, status: "" })).toEqual({});
  });

  it("tells one filter from another", () => {
    expect(sameFilters({ candidates: true, status: "" }, { candidates: true, status: "" })).toBe(true);
    expect(sameFilters({ candidates: true, status: "" }, { candidates: true, status: "acquired" })).toBe(false);
  });
});
