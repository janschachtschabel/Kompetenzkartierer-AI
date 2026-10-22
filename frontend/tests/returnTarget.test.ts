import { describe, expect, it } from "vitest";

import { RETURN_PARAM, returnTarget } from "@/returnTarget";

describe("the way back after signing in", () => {
  it("travels in the address parameter ziel", () => {
    expect(RETURN_PARAM).toBe("ziel");
  });

  it.each(["/", "/konto", "/lehrplaene/1?ansicht=baum", "/a#b"])("is a path of this app: %s", (path) => {
    expect(returnTarget(path)).toBe(path);
  });

  it.each([
    [42],
    [undefined],
    [["/a"]],
    ["https://evil.example/"],
    ["//evil.example/"],
    ["/\\evil.example/"],
    ["anmelden"],
    ["/anmelden"],
    ["/anmelden?ziel=/konto"],
    ["/anmelden#x"],
  ])("is nothing else, and never the sign-in: %s", (value) => {
    // the value comes from the address, which anybody can write: forwarding to
    // another site would be an open redirect
    expect(returnTarget(value)).toBeNull();
  });
});
