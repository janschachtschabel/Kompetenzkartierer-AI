import { describe, expect, it } from "vitest";

import type { TreeAnchor } from "@/api";
import {
  anchorCodeText,
  anchorRequest,
  anchorsOf,
  decodeAnchor,
  encodeAnchor,
  pageOfBlock,
  withAnchor,
  withoutAnchor,
} from "@/anchorDraft";

import { CV } from "./treeFixtures";

function anchor(changes: Partial<TreeAnchor> = {}): TreeAnchor {
  return {
    id: "a1",
    page_start: 5,
    page_end: null,
    printed_page: "12",
    quote: "Sie messen.",
    match_kind: CV + "match_exact",
    match_score: 1,
    blocks: ["p5-b2", "p5-b3"],
    ...changes,
  };
}

describe("an anchor in a draft", () => {
  it("is written as its blocks or its page, and read back as it was", () => {
    expect(encodeAnchor({ blocks: ["p5-b2", "p5-b3"] })).toBe("blocks:p5-b2,p5-b3");
    expect(encodeAnchor({ page: 5 })).toBe("page:5");
    // one place, one code: its blocks once each, by page and number, however they were chosen
    expect(encodeAnchor({ blocks: ["p5-b3", "p5-b2", "p4-b10", "p4-b9", "p5-b3"] })).toBe("blocks:p4-b9,p4-b10,p5-b2,p5-b3");

    expect(decodeAnchor("blocks:p5-b2,p5-b3")).toEqual({ blocks: ["p5-b2", "p5-b3"] });
    expect(decodeAnchor("blocks:p5-b2")).toEqual({ blocks: ["p5-b2"] });
    expect(decodeAnchor("page:5")).toEqual({ page: 5 });
    expect(decodeAnchor("page:99999")).toEqual({ page: 99999 });
  });

  it.each([
    "",
    "blocks:",
    "blocks:p5-b2,",
    "blocks:p5-b2;p5-b3",
    "blocks:x",
    "blocks:p0-b1",
    "blocks:p5-b",
    " blocks:p5-b2",
    "page:",
    "page:0",
    "page:007",
    "page:1e3",
    "page:100000",
    "page:5 ",
    "pages:5",
    "bloxks:p5-b2",
  ])("reads %j as none", (code) => {
    expect(decodeAnchor(code)).toBeNull();
  });

  it("is read off a stored anchor by its blocks, else its page; one with neither cannot be named", () => {
    const codes = anchorsOf([
      anchor({ id: "a1", blocks: ["p6-b1", "p5-b3"] }),
      anchor({ id: "a2", blocks: [], page_start: 7 }),
      anchor({ id: "a3", blocks: [], page_start: null }),
      // the same place twice: once
      anchor({ id: "a4", blocks: ["p5-b3", "p6-b1"] }),
    ]);

    expect(codes).toEqual(["blocks:p5-b3,p6-b1", "page:7"]);
  });

  it("goes to the server as the anchors it names, in their order", () => {
    expect(anchorRequest(["page:7", "blocks:p5-b2,p5-b3"])).toEqual([{ page: 7 }, { blocks: ["p5-b2", "p5-b3"] }]);
    expect(anchorRequest([])).toEqual([]);
    // none the server could not read
    expect(anchorRequest(["page:0", "page:7"])).toEqual([{ page: 7 }]);
  });

  it("says its pages and how many blocks, or the page it was not found on", () => {
    expect(anchorCodeText("blocks:p5-b2,p5-b3")).toBe("Seite 5: 2 Blöcke");
    expect(anchorCodeText("blocks:p5-b2")).toBe("Seite 5: 1 Block");
    expect(anchorCodeText("blocks:p6-b1,p5-b9,p7-b2")).toBe("Seiten 5–7: 3 Blöcke");
    expect(anchorCodeText("page:5")).toBe("Auf Seite 5 nicht gefunden");
    // one it cannot read stands as written, not as nothing
    expect(anchorCodeText("blocks:x")).toBe("blocks:x");
  });

  it("reads a block's page off its id", () => {
    expect(pageOfBlock("p5-b2")).toBe(5);
    expect(pageOfBlock("p12345-b123456")).toBe(12345);
    expect(pageOfBlock("p0-b1")).toBeNull();
    expect(pageOfBlock("p5-b")).toBeNull();
    expect(pageOfBlock("x")).toBeNull();
  });

  it("is taken into a draft's anchors once, as its place's code, and out again", () => {
    const draft = { verbatim: "Sie messen.", anchors: ["page:7"] };

    const taken = withAnchor(draft, "blocks:p5-b3,p5-b2");
    expect(taken).toEqual({ verbatim: "Sie messen.", anchors: ["page:7", "blocks:p5-b2,p5-b3"] });
    expect(withAnchor(taken, "blocks:p5-b2,p5-b3")).toBe(taken);
    expect(withAnchor(draft, "blocks:x")).toBe(draft); // none it cannot read
    expect(withoutAnchor(taken, "page:7")).toEqual({ verbatim: "Sie messen.", anchors: ["blocks:p5-b2,p5-b3"] });
    expect(draft.anchors).toEqual(["page:7"]); // a new draft each time
  });

  it("leaves a draft that holds no anchors - a node's - as it is", () => {
    const node = { original_title: "Optik" };

    expect(withAnchor(node, "page:3")).toBe(node);
    expect(withoutAnchor(node, "page:3")).toBe(node);
  });
});

