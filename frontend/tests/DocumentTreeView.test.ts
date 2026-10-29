import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type DocumentPage, type TreeAnchor } from "@/api";
import { t } from "@/i18n/de";
import { router } from "@/router";
import DocumentTreeView from "@/views/DocumentTreeView.vue";

import { violations } from "./axe";
import { block } from "./conversions";
import { CV, form_, node_, statement_, tree_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

function document_(changes: Partial<CurriculumDocument> = {}): CurriculumDocument {
  return {
    id: "d1",
    source_id: "s1",
    conversion_id: "c1",
    own: true,
    title: "Lehrplan Physik",
    document_type_iri: null,
    sector: "school",
    regions: ["DE-NW"],
    created_at: "2026-10-29T10:00:00Z",
    extraction: null,
    ...changes,
  };
}

function anchor(id: string, page: number, blocks: string[]): TreeAnchor {
  return {
    id,
    page_start: page,
    page_end: page,
    printed_page: null,
    quote: null,
    match_kind: CV + "match_exact",
    match_score: 1,
    blocks,
  };
}

const TREE = tree_([
  node_("a", {
    fields: { original_title: "Optik", code: "LF 1", function: CV + "fn_area" },
    anchors: [anchor("t1", 4, ["p4-b1"])],
    statements: [
      statement_("s1", {
        fields: { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome", addressees: [CV + "addr_learner"] },
        anchors: [anchor("q1", 5, ["p5-b2"]), anchor("q2", 6, ["p6-b1"])],
      }),
      statement_("s2", { position: 2, fields: { verbatim: "Ohne Fundstelle." } }),
    ],
  }),
]);

function page(number: number): DocumentPage {
  return {
    page: number,
    pages: 9,
    printed_page: null,
    blocks: [block(`p${number}-b1`, `Erster auf ${number}`), block(`p${number}-b2`, `Zweiter auf ${number}`)],
    continued: [],
  };
}

async function open(query: Record<string, string> = {}): Promise<VueWrapper> {
  await router.push({ name: "documentTree", params: { id: "d1" }, query });
  shown = mount(DocumentTreeView, { props: { id: "d1" }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

function query(): Record<string, unknown> {
  return { ...router.currentRoute.value.query };
}

beforeEach(() => {
  vi.restoreAllMocks();
  api.setToken("kka_token");
  vi.spyOn(api, "getDocument").mockResolvedValue(document_());
  vi.spyOn(api, "getTree").mockResolvedValue(TREE);
  vi.spyOn(api, "getForm").mockResolvedValue(form_());
  vi.spyOn(api, "getDocumentBlocks").mockImplementation((_id, number) => Promise.resolve(page(number)));
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("a document's tree page", () => {
  it("names the document, shows its tree and the source's first page while no row is chosen", async () => {
    const wrapper = await open();

    expect(wrapper.get("h1").text()).toBe("Baum: Lehrplan Physik");
    expect(wrapper.findAll("[role=treeitem]").map((item) => item.attributes("data-key"))).toEqual([
      "node:a",
      "statement:s1",
      "statement:s2",
    ]);
    expect(wrapper.text()).toContain(t("documents.tree.detail.none"));
    expect(api.getDocumentBlocks).toHaveBeenCalledWith("d1", 1);
    expect(wrapper.get("a[href='/dokumente/d1']").text()).toBe("Zum Dokument");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("shows a row chosen in the tree with the page of its first anchor, its blocks marked, both in the address", async () => {
    const wrapper = await open();

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();

    expect(query()).toEqual({ zeile: "statement:s1", seite: "5" });
    expect(wrapper.get(".row-detail").text()).toContain("Sie messen.");
    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 5);
    expect(wrapper.findAll(".block").map((item) => item.classes("block--cited"))).toEqual([false, true]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("keeps the document's name in the tab while the row and the page change", async () => {
    const wrapper = await open();
    expect(document.title).toBe(`Baum: Lehrplan Physik · ${t("app.title")}`);

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();

    expect(document.title).toBe(`Baum: Lehrplan Physik · ${t("app.title")}`);
  });

  it("opens with the row and the page its address names", async () => {
    const wrapper = await open({ zeile: "node:a", seite: "7" });

    expect(wrapper.get(".row-detail").text()).toContain("Optik");
    expect(wrapper.get("[data-key='node:a']").attributes("aria-selected")).toBe("true");
    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 7);
  });

  it("reads a page the address writes otherwise than as a whole number as none: the first anchor's", async () => {
    await open({ zeile: "statement:s1", seite: "0x10" });

    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 5);
  });

  it("shows the first page for a row chosen without anchors, whatever page was shown before", async () => {
    const wrapper = await open({ zeile: "statement:s1", seite: "6" });

    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();

    expect(query()).toEqual({ zeile: "statement:s2" });
    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 1);
  });

  it("leaves a row the address names but the tree does not hold unchosen", async () => {
    const wrapper = await open({ zeile: "node:gone" });

    expect(wrapper.text()).toContain(t("documents.tree.detail.none"));
    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 1);
  });

  it("goes to the page an anchor names, and to the page its pager asks for", async () => {
    const wrapper = await open({ zeile: "statement:s1" });
    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 5); // no page asked: its first anchor's

    await wrapper.findAll(".row-detail__anchors button")[1]?.trigger("click");
    await flushPromises();
    expect(query()).toEqual({ zeile: "statement:s1", seite: "6" });
    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 6);

    await wrapper.get("[data-test=next]").trigger("click");
    await flushPromises();
    expect(query()).toEqual({ zeile: "statement:s1", seite: "7" });
  });

  it("says a document it may not read is not there", async () => {
    vi.spyOn(api, "getDocument").mockRejectedValue(new ApiError("server", 404, "no_document"));
    vi.spyOn(api, "getTree").mockRejectedValue(new ApiError("server", 404, "no_document"));

    const wrapper = await open();

    expect(wrapper.text()).toContain(t("documents.page.notFoundTitle"));
    expect(wrapper.find("[role=tree]").exists()).toBe(false);
  });

  it("says a reading failed, and reads again on request", async () => {
    vi.spyOn(api, "getTree").mockRejectedValueOnce(new ApiError("network", 0)).mockResolvedValue(TREE);
    const wrapper = await open();
    expect(wrapper.text()).toContain(t("documents.tree.loadFailed"));

    await wrapper.findAll("button").find((button) => button.text() === t("states.retry"))?.trigger("click");
    await flushPromises();

    expect(wrapper.findAll("[role=treeitem]")).toHaveLength(3);
  });
});
