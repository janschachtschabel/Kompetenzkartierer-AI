import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import type { TreeAnchor } from "@/api";
import RowDetail from "@/components/RowDetail.vue";
import { rowsOf, type Row, type RowKey } from "@/documentTree";

import { violations } from "./axe";
import { CV, SCHOOL, form_, node_, statement_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

function anchor(id: string, page: number): TreeAnchor {
  return {
    id,
    page_start: page,
    page_end: page,
    printed_page: null,
    quote: `Zitat ${id}`,
    match_kind: CV + "match_exact",
    match_score: 1,
    blocks: [`p${page}-b1`],
  };
}

const ROWS = rowsOf([
  node_("a", {
    fields: { original_title: "Optik", function: CV + "fn_area", node_type: SCHOOL + "Inhaltsbereich", code: "1" },
    code_assigned: true,
    iri: "https://example.org/kk/doc/de-nw/msb/klp/2019/1",
    anchors: [anchor("t1", 4)],
    statements: [
      statement_("s1", {
        fields: {
          verbatim: "Sie messen Spannungen.",
          statement_kind: CV + "kind_learningOutcome",
          addressees: [CV + "addr_learner", CV + "addr_educator"],
          levelText: "Stufe 2",
        },
        origin: CV + "orig_human",
        review_status: CV + "rev_confirmed",
        revision: 3,
        anchors: [anchor("q1", 5), anchor("q2", 6)],
      }),
      statement_("s2", {
        fields: { verbatim: null, statement_kind: CV + "kind_gone", addressees: [] },
        origin: CV + "orig_gone",
      }),
    ],
  }),
]);

function detail(key: RowKey): VueWrapper {
  shown = mount(RowDetail, { props: { row: ROWS.get(key) as Row, form: form_() }, attachTo: document.body });
  return shown;
}

function facts(wrapper: VueWrapper): string[][] {
  const list = wrapper.get(".row-detail__fields");
  return list.findAll("dt").map((term, index) => [term.text(), list.findAll("dd")[index]?.text() ?? ""]);
}

describe("a row's detail", () => {
  it("lists a node's fields in the form's order by their labels, and where it comes from", async () => {
    const wrapper = detail("node:a");

    expect(facts(wrapper)).toEqual([
      ["Titel", "Optik"],
      ["Funktion", "Bereich"],
      ["Knotentyp", "Inhaltsbereich"],
      ["Code", "1 (aus der Position vergeben)"],
      ["Herkunft", "vom Modell"],
      ["Prüfstand", "Vorgeschlagen"],
      ["Revision", "1"],
      ["IRI", "https://example.org/kk/doc/de-nw/msb/klp/2019/1"],
    ]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("lists a statement's fields: the required ones always, the others where they hold a value", () => {
    const wrapper = detail("statement:s1");

    expect(facts(wrapper)).toEqual([
      ["Wortlaut", "Sie messen Spannungen."],
      ["Art der Aussage", "Lernergebnis"],
      ["Adressaten", "Lernende, Lehrkräfte"],
      ["Niveau im Wortlaut", "Stufe 2"],
      ["Herkunft", "redaktionell"],
      ["Prüfstand", "Bestätigt"],
      ["Revision", "3"],
    ]);
  });

  it("says what is not given, and names a value the form or the vocabulary no longer holds by its IRI", () => {
    const wrapper = detail("statement:s2");

    expect(facts(wrapper)).toEqual([
      ["Wortlaut", "nicht angegeben"],
      ["Art der Aussage", CV + "kind_gone"],
      ["Adressaten", "nicht angegeben"],
      ["Herkunft", CV + "orig_gone"],
      ["Prüfstand", "Vorgeschlagen"],
      ["Revision", "1"],
    ]);
  });

  it("lists its anchors, each with a way to show its page, and says where it has none", async () => {
    const wrapper = detail("statement:s1");

    expect(wrapper.get("h3").text()).toBe("Fundstellen");
    expect(wrapper.findAll(".row-detail__anchors > li")).toHaveLength(2);
    await wrapper.findAll(".row-detail__anchors button")[1]?.trigger("click");
    expect(wrapper.emitted("show")).toEqual([[6]]);
    expect(await violations(wrapper.html())).toEqual([]);

    const bare = detail("statement:s2");
    expect(bare.text()).toContain("Keine Fundstelle.");
  });
});
