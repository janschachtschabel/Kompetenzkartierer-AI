import { describe, expect, it } from "vitest";

import { CV, REVIEW_STATUSES, REVIEW_TONES, statusIri, statusOf, statusWord } from "@/reviewStatus";

describe("the review statuses", () => {
  it("are named by their IRIs and said in words, each with a tone", () => {
    expect(REVIEW_STATUSES.map(statusIri)).toEqual([CV + "rev_proposed", CV + "rev_confirmed", CV + "rev_rejected"]);
    expect(REVIEW_STATUSES.map((status) => statusWord(statusIri(status)))).toEqual([
      "Vorgeschlagen",
      "Bestätigt",
      "Verworfen",
    ]);
    expect(REVIEW_TONES).toEqual({ proposed: "neutral", confirmed: "success", rejected: "error" });
  });

  it("leave an IRI the vocabulary does not hold as it is", () => {
    expect(statusOf(CV + "rev_unknown")).toBeNull();
    expect(statusWord(CV + "rev_unknown")).toBe(CV + "rev_unknown");
  });
});
