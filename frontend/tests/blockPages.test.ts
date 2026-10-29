import { describe, expect, it } from "vitest";

import { pageOf } from "@/blockPages";

describe("the page an address names", () => {
  it("is a whole number from 1 as the address writes it, and none for anything else", () => {
    expect(["1", "7", "100000"].map(pageOf)).toEqual([1, 7, 100000]);
    expect(["0", "0x10", "1e3", " 2 ", "2.5", "-3", "", "1234567"].map(pageOf)).toEqual(Array(8).fill(null));
    expect([undefined, null, ["2"], 2].map(pageOf)).toEqual([null, null, null, null]);
  });
});
