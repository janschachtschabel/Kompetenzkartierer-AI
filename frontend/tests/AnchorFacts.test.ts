import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import type { TreeAnchor } from "@/api";
import { matchWord, pagesText } from "@/anchorWords";
import AnchorFacts from "@/components/AnchorFacts.vue";

import { violations } from "./axe";
import { CV } from "./treeFixtures";

let shown: VueWrapper | null = null;

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

function anchor(changes: Partial<TreeAnchor> = {}): TreeAnchor {
  return {
    id: "a1",
    page_start: 3,
    page_end: 3,
    printed_page: null,
    quote: "Die Lernenden messen Spannungen.",
    match_kind: CV + "match_exact",
    match_score: 1,
    blocks: ["p3-b2", "p3-b3"],
    ...changes,
  };
}

function facts(given: TreeAnchor): VueWrapper {
  shown = mount(AnchorFacts, { props: { anchor: given }, attachTo: document.body });
  return shown;
}

function described(wrapper: VueWrapper): string[][] {
  // a percentage's space is a no-break one (Intl, de-DE)
  const said = (text: string) => text.replace(/\u00a0/g, " ");
  return wrapper.findAll("dt").map((term, index) => [term.text(), said(wrapper.findAll("dd")[index]?.text() ?? "")]);
}

describe("an anchor in words", () => {
  it("says how its passage was found, and that X5 has not looked yet", () => {
    expect(
      ["exact", "whitespace", "elided", "normalized", "fuzzy", "notFound"].map((kind) => matchWord(`${CV}match_${kind}`)),
    ).toEqual([
      "wörtlich gefunden",
      "bis auf Leerraum gefunden",
      "mit Auslassung gefunden",
      "gefunden bis auf Trennstriche und Anführungszeichen",
      "nur unscharf gefunden, kein Wortlautbeleg",
      "nicht gefunden",
    ]);
    expect(matchWord(null)).toBe("noch nicht geprüft");
    expect(matchWord(CV + "match_other")).toBe(CV + "match_other");
  });

  it("names its pages, the one the document prints beside", () => {
    expect(pagesText(anchor())).toBe("Seite 3");
    expect(pagesText(anchor({ page_end: 4 }))).toBe("Seiten 3–4");
    expect(pagesText(anchor({ printed_page: "12" }))).toBe("Seite 3 (gedruckt 12)");
    expect(pagesText(anchor({ page_start: null, page_end: null }))).toBe("ohne Seite");
  });
});

describe("an anchor's facts", () => {
  it("show its page, how it was found, the passage and its blocks", async () => {
    const wrapper = facts(anchor({ match_kind: CV + "match_fuzzy", match_score: 0.87 }));

    expect(described(wrapper)).toEqual([
      ["Seite", "Seite 3"],
      ["Fundart", "nur unscharf gefunden, kein Wortlautbeleg (Übereinstimmung 87 %)"],
      ["Zitat", "Die Lernenden messen Spannungen."],
      ["Blöcke", "p3-b2, p3-b3"],
    ]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("offer to show their page in the source, and say so where it names none", async () => {
    const wrapper = facts(anchor());

    expect(described(wrapper)[1]).toEqual(["Fundart", "wörtlich gefunden"]); // a score for a fuzzy one alone
    await wrapper.get("button").trigger("click");
    expect(wrapper.get("button").text()).toBe("Seite 3 in der Quelle zeigen");
    expect(wrapper.emitted("show")).toEqual([[3]]);

    const nowhere = mount(AnchorFacts, {
      props: { anchor: anchor({ page_start: null, page_end: null, quote: null, blocks: [], match_kind: null }) },
    });
    expect(nowhere.find("button").exists()).toBe(false);
    expect(described(nowhere)).toEqual([
      ["Seite", "ohne Seite"],
      ["Fundart", "noch nicht geprüft"],
    ]);
    nowhere.unmount();
  });
});
