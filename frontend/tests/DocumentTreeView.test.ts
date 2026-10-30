import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RouterView } from "vue-router";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type DocumentPage, type Tree, type TreeAnchor, type TreeStatement } from "@/api";
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

const NODES = [
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
];
const TREE = tree_(NODES, { editable: false, reviewable: false, closed: "frozen" });
// statement s1 as a change of its wording answers
const SAID_SAVED = statement_("s1", {
  fields: { verbatim: "Sie messen genau.", statement_kind: CV + "kind_learningOutcome", addressees: [CV + "addr_learner"] },
});
const OPEN = tree_(NODES);

function page(number: number): DocumentPage {
  return {
    page: number,
    pages: 9,
    printed_page: null,
    blocks: [block(`p${number}-b1`, `Erster auf ${number}`), block(`p${number}-b2`, `Zweiter auf ${number}`)],
    continued: [],
  };
}

// as a leaving transition keeps the page: mounted on its own, it stays when the address leaves it
async function openOutside(query: Record<string, string> = {}): Promise<VueWrapper> {
  await router.push({ name: "documentTree", params: { id: "d1" }, query });
  shown = mount(DocumentTreeView, { props: { id: "d1" }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

// as the app shows it, in a RouterView: the guards of a route's view need one
async function open(query: Record<string, string> = {}): Promise<VueWrapper> {
  await router.push({ name: "documentTree", params: { id: "d1" }, query });
  shown = mount(RouterView, { global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

// a held answer to a change, given when the test says
let answerSave: (row: TreeStatement) => void = () => undefined;

async function answer(wrapper: VueWrapper, label: string): Promise<void> {
  await wrapper
    .findAll("[role=dialog] button")
    .find((button) => button.text() === label)
    ?.trigger("click");
  await flushPromises();
}

async function press(wrapper: VueWrapper, label: string): Promise<void> {
  const found = wrapper.findAll("button").find((one) => one.text() === label);
  if (!found) throw new Error(label);
  await found.trigger("click");
  await flushPromises();
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

  it("goes to the page of the first anchor that names one", async () => {
    const unplaced = { ...anchor("q0", 1, []), page_start: null, page_end: null };
    vi.mocked(api.getTree).mockResolvedValue(
      tree_([node_("a", { statements: [statement_("s1", { anchors: [unplaced, anchor("q1", 6, ["p6-b1"])] })] })]),
    );
    const wrapper = await open();

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();

    expect(query()).toEqual({ zeile: "statement:s1", seite: "6" });
  });

  it("changes the row and the page in place: back leaves the tree page, not the row before", async () => {
    const wrapper = await open();
    const steps = window.history.length;

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();
    await wrapper.get("[data-test=next]").trigger("click");
    await flushPromises();

    expect(query()).toEqual({ zeile: "statement:s1", seite: "6" });
    expect(window.history.length).toBe(steps);
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

  it("keeps the keys in the tree while a row chosen there moves the source to its page", async () => {
    const wrapper = await open();
    const row = wrapper.get("[data-key='statement:s1']").element as HTMLElement;
    row.focus();

    await wrapper.get("[data-key='statement:s1']").trigger("keydown", { key: "Enter" });
    await flushPromises();

    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 5);
    expect(document.activeElement).toBe(row);
  });

  it("takes the keys along to the source when an anchor shows its page", async () => {
    const wrapper = await open({ zeile: "statement:s1" });
    const show = wrapper.findAll(".row-detail__anchors button")[1];
    (show?.element as HTMLElement).focus();

    await show?.trigger("click");
    await flushPromises();

    expect(document.activeElement?.textContent).toBe("Quelle");
    expect(document.activeElement?.tagName).toBe("H2");
  });

  it("reads no row or page of the address it is left for, nor names its tab", async () => {
    // a leaving transition keeps the page mounted under the next page's address
    await openOutside({ zeile: "statement:s1", seite: "6" });
    vi.mocked(api.getDocumentBlocks).mockClear();

    await router.push({ name: "document", params: { id: "d1" } });
    await flushPromises();

    expect(api.getDocumentBlocks).not.toHaveBeenCalled();
    expect(document.title).toBe(`${t("app.titles.document")} · ${t("app.title")}`);
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

  it("says why the tree only reads: the document's state, or the caller's role", async () => {
    const wrapper = await open({ zeile: "statement:s1" });

    expect(wrapper.get(".row-panel__closed").text()).toBe(
      "Das Dokument ist festgeschrieben; Änderungen gehen nur in einer Entwurfskopie.",
    );
    expect(wrapper.find(".row-form").exists()).toBe(false);
    expect(wrapper.get(".row-detail").text()).toContain("Sie messen.");
    shown?.unmount();

    vi.spyOn(api, "getTree").mockResolvedValue(tree_(NODES, { editable: false, reviewable: false }));
    const other = await open({ zeile: "statement:s1" });
    expect(other.get(".row-panel__closed").text()).toBe("Bearbeiten dürfen der Eigentümer und die Redaktion.");
  });

  it("shows the row chosen in its form where the tree is open, its origin and anchors beside", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);

    const wrapper = await open({ zeile: "statement:s1" });

    expect((wrapper.get(".row-form textarea").element as HTMLTextAreaElement).value).toBe("Sie messen.");
    expect(wrapper.find(".row-panel__closed").exists()).toBe(false);
    expect(wrapper.get(".row-detail").text()).not.toContain("Sie messen.");
    expect(wrapper.get(".row-detail").text()).toContain("Fundstellen");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("reads the tree again once a change is saved, the row staying chosen", async () => {
    const read = vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    vi.spyOn(api, "editStatement").mockImplementation((id, revision, fields) =>
      Promise.resolve({ ...statement_(id), revision: revision + 1, fields: { verbatim: String(fields.verbatim) } }),
    );
    const wrapper = await open({ zeile: "statement:s1" });

    await wrapper.get(".row-form textarea").setValue("Sie messen genau.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(2);
    expect(query()).toEqual({ zeile: "statement:s1" });
    expect(wrapper.get(".row-editor__status").text()).toBe("Gespeichert.");
  });

  it("takes a statement's anchor chosen in the source into its draft, and saves it with the others", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const sent = vi.spyOn(api, "editStatement").mockImplementation((id, revision) =>
      Promise.resolve({ ...statement_(id), revision: revision + 1 }),
    );
    const wrapper = await open({ zeile: "statement:s1" });
    expect(api.getDocumentBlocks).toHaveBeenLastCalledWith("d1", 5);

    await wrapper.findAll(".block button")[0]?.trigger("click");
    await wrapper.get("[data-test=take]").trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".anchor-draft li span").map((one) => one.text())).toEqual([
      "Seite 5: 1 Block (p5-b2)",
      "Seite 6: 1 Block (p6-b1)",
      "Seite 5: 1 Block (p5-b1)",
    ]);
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("s1", 1, {}, [{ blocks: ["p5-b2"] }, { blocks: ["p6-b1"] }, { blocks: ["p5-b1"] }]);
  });

  it("offers no anchor to choose for a node, nor where the tree only reads", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const node = await open({ zeile: "node:a" });
    expect(node.find("[data-test=take]").exists()).toBe(false);
    expect(node.findAll(".block button")).toHaveLength(0);
    node.unmount();

    vi.mocked(api.getTree).mockResolvedValue(TREE);
    const reading = await open({ zeile: "statement:s1" });
    expect(reading.find("[data-test=take]").exists()).toBe(false);
    expect(reading.findAll(".block button")).toHaveLength(0);
  });

  it("adds a node at the tree's top, and shows it chosen once it is", async () => {
    const added = tree_([...NODES, node_("n9", { position: 2, fields: { original_title: "Neu", code: null } })]);
    let reread: (tree: Tree) => void = () => undefined;
    vi.spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockReturnValueOnce(new Promise((resolve) => (reread = resolve)));
    const sent = vi.spyOn(api, "addNode").mockResolvedValue(node_("n9"));
    const wrapper = await open();

    await press(wrapper, t("documents.tree.create.node"));
    expect(wrapper.get(".row-panel h2").text()).toBe(t("documents.tree.create.headingTop"));
    expect(document.activeElement).toBe(wrapper.get(".row-panel h2").element);
    expect(wrapper.findAll(".block button")).toHaveLength(0); // a node has no anchor to choose
    await wrapper.get(".row-creator input").setValue("Neu");
    await wrapper.get(".row-creator select").setValue(CV + "fn_area");
    await wrapper.get(".row-creator form").trigger("submit");
    await flushPromises();
    // while the tree is read again: the form, busy - not the row chosen before; the keyboard on its button
    expect(wrapper.get(".row-panel h2").text()).toBe(t("documents.tree.create.headingTop"));
    (wrapper.get(".row-creator .row-form__save").element as HTMLElement).focus();
    expect(wrapper.get(".row-creator .row-form__save").attributes("aria-disabled")).toBe("true");
    reread(added);
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("d1", null, { original_title: "Neu", function: CV + "fn_area" });
    expect(query()).toEqual({ zeile: "node:n9" });
    expect(wrapper.find(".row-creator").exists()).toBe(false);
    expect(wrapper.get(".row-panel__status").text()).toBe(t("documents.tree.create.created"));
    expect(wrapper.get(".row-panel h2").text()).toBe("Knoten Neu");
    expect(document.activeElement).toBe(wrapper.get(".row-panel h2").element);
  });

  it("adds a statement to a node chosen, its anchor chosen in the source", async () => {
    const s9 = statement_("s9", { position: 3, anchors: [anchor("q9", 4, ["p4-b1"])] });
    const added = tree_([{ ...NODES[0], statements: [...NODES[0].statements, s9] }]);
    vi.spyOn(api, "getTree").mockResolvedValueOnce(OPEN).mockResolvedValue(added);
    const sent = vi.spyOn(api, "addStatement").mockResolvedValue(s9);
    const wrapper = await open({ zeile: "node:a" });

    await press(wrapper, t("documents.tree.create.statement"));
    expect(wrapper.get(".row-panel h2").text()).toBe(t("documents.tree.create.headingStatement", { name: "LF 1 Optik" }));
    expect(await violations(wrapper.html())).toEqual([]);
    await wrapper.findAll(".block button")[0]?.trigger("click");
    await wrapper.get("[data-test=take]").trigger("click");
    await wrapper.get(".row-creator textarea").setValue("Sie messen.");
    await wrapper.get(".row-creator select").setValue(CV + "kind_learningOutcome");
    await wrapper.get(".row-creator input[type=checkbox]").setValue(true);
    await wrapper.get(".row-creator form").trigger("submit");
    await flushPromises();

    expect(sent).toHaveBeenCalledWith(
      "a",
      { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome", addressees: [CV + "addr_learner"] },
      [{ blocks: ["p4-b1"] }],
    );
    expect(query()).toEqual({ zeile: "statement:s9", seite: "4" });
  });

  it("adds a node under the node chosen", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const sent = vi.spyOn(api, "addNode").mockResolvedValue(node_("n9"));
    const wrapper = await open({ zeile: "node:a" });

    await press(wrapper, t("documents.tree.create.child"));
    expect(wrapper.get(".row-panel h2").text()).toBe(t("documents.tree.create.headingChild", { name: "LF 1 Optik" }));
    await wrapper.get(".row-creator input").setValue("Linsen");
    await wrapper.get(".row-creator select").setValue(CV + "fn_unit");
    await wrapper.get(".row-creator form").trigger("submit");
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("d1", "a", { original_title: "Linsen", function: CV + "fn_unit" });
  });

  it("lets a new row go when cancelled, the keyboard at the panel, or when another row is chosen", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "node:a" });

    await press(wrapper, t("documents.tree.create.child"));
    const cancelling = wrapper.findAll(".row-creator button").find((one) => one.text() === t("documents.tree.create.cancel"));
    (cancelling?.element as HTMLElement).focus();
    await press(wrapper, t("documents.tree.create.cancel"));
    expect(wrapper.find(".row-creator").exists()).toBe(false);
    expect(wrapper.get(".row-panel h2").text()).toBe("Knoten LF 1 Optik");
    expect(document.activeElement).toBe(wrapper.get(".row-panel h2").element);

    await press(wrapper, t("documents.tree.create.child"));
    const row = wrapper.get("[data-key='statement:s1']");
    (row.element as HTMLElement).focus();
    await row.trigger("click");
    await flushPromises();
    expect(wrapper.find(".row-creator").exists()).toBe(false);
    expect(document.activeElement).toBe(row.element);
  });

  it("asks before a new row's entries go with another row chosen", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "node:a" });
    await press(wrapper, t("documents.tree.create.child"));
    await wrapper.get(".row-creator input").setValue("Neu");

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();
    await answer(wrapper, t("documents.tree.leave.cancel"));

    expect(query()).toEqual({ zeile: "node:a" });
    expect((wrapper.get(".row-creator input").element as HTMLInputElement).value).toBe("Neu");
  });

  it("takes a node away once asked: it leaves the address, the panel says what went", async () => {
    const read = vi.spyOn(api, "getTree").mockResolvedValueOnce(OPEN).mockResolvedValue(tree_([]));
    const sent = vi.spyOn(api, "dropNode").mockResolvedValue({ nodes: 1, statements: 2 });
    const wrapper = await open({ zeile: "node:a", seite: "4" });

    await press(wrapper, t("documents.tree.drop.node"));
    const confirm = wrapper.findAll("[role=dialog] button").find((one) => one.text() === t("documents.tree.drop.node"));
    await confirm?.trigger("click");
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("a", 1);
    expect(read).toHaveBeenCalledTimes(2);
    expect(query()).toEqual({ seite: "4" });
    expect(wrapper.get(".row-panel__status").text()).toBe("Gelöscht: der Knoten mit 0 Unterknoten und 2 Aussagen.");
    expect(document.activeElement).toBe(wrapper.get(".row-panel h2").element);
  });

  it("rejects a statement a run found, which stays chosen, the tree read again", async () => {
    const read = vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    vi.spyOn(api, "dropStatement").mockResolvedValue({ outcome: "rejected", revision: 2 });
    const wrapper = await open({ zeile: "statement:s1" });

    await press(wrapper, t("documents.tree.drop.reject"));
    const confirm = wrapper.findAll("[role=dialog] button").find((one) => one.text() === t("documents.tree.drop.reject"));
    await confirm?.trigger("click");
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(2);
    expect(query()).toEqual({ zeile: "statement:s1" });
    expect(wrapper.get(".row-panel__status").text()).toBe(t("documents.tree.drop.rejected"));
  });

  it("asks before adding a row takes a draft's place, the draft kept where the user stays", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "node:a" });
    await wrapper.get(".row-form input").setValue("Optik neu");

    await press(wrapper, t("documents.tree.create.child"));
    expect(wrapper.get("[role=dialog]").text()).toContain(t("documents.tree.leave.title"));
    await answer(wrapper, t("documents.tree.leave.cancel"));
    expect(wrapper.find(".row-creator").exists()).toBe(false);
    expect((wrapper.get(".row-form input").element as HTMLInputElement).value).toBe("Optik neu");

    await press(wrapper, t("documents.tree.create.child"));
    await answer(wrapper, t("documents.tree.leave.confirm"));
    expect(wrapper.find(".row-creator").exists()).toBe(true);

    // a row being added with entries: asked in its own words
    await wrapper.get(".row-creator input").setValue("Neu");
    await press(wrapper, t("documents.tree.create.node"));
    expect(wrapper.get("[role=dialog]").text()).toContain(t("documents.tree.create.discard.title"));
    await answer(wrapper, t("documents.tree.create.discard.cancel"));
    expect((wrapper.get(".row-creator input").element as HTMLInputElement).value).toBe("Neu");
    expect(wrapper.get(".row-panel h2").text()).toBe(t("documents.tree.create.headingChild", { name: "LF 1 Optik" }));
  });

  it("lets a row to add asked about go with the row it was to go under", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "node:a" });
    await wrapper.get(".row-form input").setValue("Optik neu");
    await press(wrapper, t("documents.tree.create.child"));

    void router.push({ name: "documentTree", params: { id: "d1" }, query: { zeile: "statement:s1" } });
    await flushPromises();
    await answer(wrapper, t("documents.tree.leave.confirm"));

    expect(query()).toEqual({ zeile: "statement:s1" });
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
    expect(wrapper.find(".row-creator").exists()).toBe(false);
  });

  it("asks nothing and keeps the entries where the same row to add is asked for again", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open();
    await press(wrapper, t("documents.tree.create.node"));
    await wrapper.get(".row-creator input").setValue("Neu");

    await press(wrapper, t("documents.tree.create.node"));

    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
    expect((wrapper.get(".row-creator input").element as HTMLInputElement).value).toBe("Neu");
  });

  it("asks in a new row's own words before another row takes its place", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "node:a" });
    await press(wrapper, t("documents.tree.create.child"));
    await wrapper.get(".row-creator input").setValue("Neu");

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[role=dialog]").text()).toContain(t("documents.tree.create.discard.message"));
  });

  it("reads a row as it reads once a row being added under it met a closed tree and was let go", async () => {
    vi.spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockResolvedValue(tree_(NODES, { editable: false, closed: "job_open" }));
    vi.spyOn(api, "addNode").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const wrapper = await open({ zeile: "node:a" });
    await press(wrapper, t("documents.tree.create.child"));
    await wrapper.get(".row-creator input").setValue("Neu");
    await wrapper.get(".row-creator select").setValue(CV + "fn_area");
    await wrapper.get(".row-creator form").trigger("submit");
    await flushPromises();
    expect(wrapper.get(".row-creator__closed").text()).toContain("Neu");

    await press(wrapper, t("documents.tree.create.cancel"));
    await answer(wrapper, t("documents.tree.create.discard.confirm"));

    expect(wrapper.find(".row-editor__closed").exists()).toBe(false);
    expect(wrapper.get(".row-panel__closed").text()).toBe(t("documents.tree.closed.job_open"));
    expect(wrapper.get(".row-detail").text()).toContain("Optik");
  });

  it("reads the tree again for a row added after another row was chosen, the choice kept", async () => {
    const withNew = tree_([{ ...NODES[0], children: [node_("n9", { fields: { original_title: "Neu", code: null } })] }]);
    const read = vi.spyOn(api, "getTree").mockResolvedValueOnce(OPEN).mockResolvedValue(withNew);
    let added: (row: ReturnType<typeof node_>) => void = () => undefined;
    vi.spyOn(api, "addNode").mockReturnValue(new Promise((resolve) => (added = resolve)));
    const wrapper = await open({ zeile: "node:a" });
    await press(wrapper, t("documents.tree.create.child"));
    await wrapper.get(".row-creator input").setValue("Neu");
    await wrapper.get(".row-creator select").setValue(CV + "fn_area");
    await wrapper.get(".row-creator form").trigger("submit");
    await flushPromises();

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();
    await answer(wrapper, t("documents.tree.create.discard.confirm"));
    added(node_("n9"));
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(2);
    expect(query()).toEqual({ zeile: "statement:s1", seite: "5" });

    // the new row chosen later in the tree, as any row: the keyboard stays there
    const newRow = wrapper.get("[data-key='node:n9']");
    (newRow.element as HTMLElement).focus();
    await newRow.trigger("click");
    await flushPromises();
    expect(document.activeElement).toBe(newRow.element);
  });

  it("leaves the address of a page gone to alone when a row added there is answered late", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    let added: (row: ReturnType<typeof node_>) => void = () => undefined;
    vi.spyOn(api, "addNode").mockReturnValue(new Promise((resolve) => (added = resolve)));
    // as a leaving transition keeps the page mounted under the next page's address
    const wrapper = await openOutside();
    await press(wrapper, t("documents.tree.create.node"));
    await wrapper.get(".row-creator input").setValue("Neu");
    await wrapper.get(".row-creator select").setValue(CV + "fn_area");
    await wrapper.get(".row-creator form").trigger("submit");
    await flushPromises();

    await router.push({ name: "document", params: { id: "d1" } });
    added(node_("n9"));
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("document");
    expect(query()).toEqual({});
  });

  it("says the row it was to go under is gone", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    vi.spyOn(api, "addStatement").mockRejectedValue(new ApiError("server", 404, "no_node"));
    const wrapper = await open({ zeile: "node:a" });
    await press(wrapper, t("documents.tree.create.statement"));
    await wrapper.get(".row-creator textarea").setValue("Sie messen.");
    await wrapper.get(".row-creator select").setValue(CV + "kind_learningOutcome");
    await wrapper.get(".row-creator input[type=checkbox]").setValue(true);
    await wrapper.get("[data-test=not-found]").trigger("click");
    await wrapper.get(".row-creator form").trigger("submit");
    await flushPromises();

    expect(wrapper.get(".row-panel__status").text()).toBe(t("documents.tree.create.parentGone"));
    expect(query()).toEqual({});
  });

  it("reads the tree again for a row taken away after another row was chosen, the choice kept", async () => {
    const read = vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    let dropped: (done: { nodes: number; statements: number }) => void = () => undefined;
    vi.spyOn(api, "dropNode").mockReturnValue(new Promise((resolve) => (dropped = resolve)));
    const wrapper = await open({ zeile: "node:a" });
    await press(wrapper, t("documents.tree.drop.node"));
    const confirm = wrapper.findAll("[role=dialog] button").find((one) => one.text() === t("documents.tree.drop.node"));
    await confirm?.trigger("click");

    await wrapper.get("[data-key='statement:s1']").trigger("click");
    await flushPromises();
    dropped({ nodes: 1, statements: 2 });
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(2);
    expect(query()).toEqual({ zeile: "statement:s1", seite: "5" });
  });

  it("lets what the panel said go as a row to add begins", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    vi.spyOn(api, "dropStatement").mockResolvedValue({ outcome: "rejected", revision: 2 });
    const wrapper = await open({ zeile: "statement:s1" });
    await press(wrapper, t("documents.tree.drop.reject"));
    const confirm = wrapper.findAll("[role=dialog] button").find((one) => one.text() === t("documents.tree.drop.reject"));
    await confirm?.trigger("click");
    await flushPromises();
    expect(wrapper.get(".row-panel__status").text()).toBe(t("documents.tree.drop.rejected"));

    await press(wrapper, t("documents.tree.create.node"));

    expect(wrapper.get(".row-panel__status").text()).toBe("");
  });

  it("offers no row to add where the tree only reads", async () => {
    const wrapper = await open({ zeile: "node:a" });

    const labels = wrapper.findAll("button").map((one) => one.text());
    expect(labels).not.toContain(t("documents.tree.create.node"));
    expect(labels).not.toContain(t("documents.tree.create.child"));
    expect(labels).not.toContain(t("documents.tree.drop.node"));
  });

  it("keeps the draft of a change the closing tree refused, until another row is chosen", async () => {
    vi.spyOn(api, "getTree").mockResolvedValueOnce(OPEN).mockResolvedValue(
      tree_(NODES, { editable: false, reviewable: false, closed: "job_open" }),
    );
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const wrapper = await open({ zeile: "statement:s1" });

    await wrapper.get(".row-form textarea").setValue("Mein Satz.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();

    expect(api.getTree).toHaveBeenCalledTimes(2);
    expect(wrapper.get(".row-editor__closed").text()).toContain("Mein Satz.");
    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();
    await answer(wrapper, "Verwerfen"); // the draft, though refused, is asked about before it goes
    expect(wrapper.find(".row-editor__closed").exists()).toBe(false);
    expect(wrapper.get(".row-panel__closed").text()).toContain("läuft gerade ein Auftrag");
    await wrapper.get("[data-key='statement:s1']").trigger("click"); // back: the draft is given up, no form
    await flushPromises();
    expect(wrapper.find(".row-form").exists()).toBe(false);
  });

  it("lets a row found gone go, says so and reads the tree again", async () => {
    const read = vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 404, "no_statement"));
    const wrapper = await open({ zeile: "statement:s1", seite: "5" }); // its draft goes unasked

    await wrapper.get(".row-form textarea").setValue("Neu.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(2);
    expect(query()).toEqual({ seite: "5" });
    expect(wrapper.get(".row-panel__status").text()).toBe("Diese Zeile gibt es nicht mehr; der Baum wird neu geladen.");
    expect(document.activeElement).toBe(wrapper.get(".row-panel h2").element); // not lost with the editor
  });

  it("reads the tree again for a change saved after another row was chosen", async () => {
    const read = vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    vi.spyOn(api, "editStatement").mockReturnValue(new Promise((resolve) => (answerSave = resolve)));
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Neu.");
    await wrapper.get(".row-form").trigger("submit");

    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();
    await answer(wrapper, "Verwerfen");
    answerSave(statement_("s1", { revision: 2, fields: { verbatim: "Neu." } }));
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(2);
  });

  it("keeps a draft the tree, read anew, closed on - its reason said - and asks nothing of a draft gone", async () => {
    vi.spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(tree_(NODES, { editable: false, reviewable: false, closed: "job_open" }));
    vi.spyOn(api, "editStatement").mockResolvedValue({ ...statement_("s1"), revision: 2, fields: { verbatim: "Erst." } });
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Erst.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises(); // saved; reading the tree again fails
    await wrapper.get(".row-form textarea").setValue("Mein Entwurf.");

    await wrapper.get(".document-tree__partial button").trigger("click");
    await flushPromises();

    const kept = wrapper.get(".row-editor__closed");
    expect(kept.text()).toContain(t("refusals.job_open"));
    expect(kept.text()).toContain("Mein Entwurf.");
  });

  it("reads a row saved and then closed as it reads, with no draft to keep", async () => {
    vi.spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockResolvedValue(tree_(NODES, { editable: false, reviewable: false, closed: "job_open" }));
    vi.spyOn(api, "editStatement").mockResolvedValue({ ...SAID_SAVED, revision: 2 });
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Sie messen genau.");

    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();

    expect(wrapper.find(".row-editor").exists()).toBe(false);
    expect(wrapper.get(".row-panel__closed").text()).toContain("läuft gerade ein Auftrag");
  });

  it("reads a tree read anew that the caller may no longer change as it reads, with the reason", async () => {
    vi.spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(tree_(NODES, { editable: false, reviewable: false })); // the role gone, not the tree closed
    vi.spyOn(api, "editStatement").mockResolvedValue({ ...SAID_SAVED, revision: 2 });
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Sie messen genau.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();
    await wrapper.get(".row-form textarea").setValue("Mein Entwurf.");

    await wrapper.get(".document-tree__partial button").trigger("click");
    await flushPromises();

    expect(wrapper.find(".row-form").exists()).toBe(false);
    expect(wrapper.get(".row-panel__closed").text()).toBe("Bearbeiten dürfen der Eigentümer und die Redaktion.");
  });

  it("leaves the keyboard where it is when the tree asked again fails once more", async () => {
    vi.spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockRejectedValue(new ApiError("network", 0)); // every reading again fails
    vi.spyOn(api, "editStatement").mockResolvedValue({ ...SAID_SAVED, revision: 2 });
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Sie messen genau.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();

    const retry = wrapper.get(".document-tree__partial button");
    (retry.element as HTMLElement).focus();
    await retry.trigger("click");
    await flushPromises();

    expect(wrapper.get(".document-tree__partial").text()).toContain(t("documents.tree.loadFailed"));
    expect(document.activeElement).not.toBe(wrapper.get("#document-tree-rows").element);
  });

  it("lets a refused draft go where the tree read anew is closed to the caller's role, not to all", async () => {
    vi.spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(tree_(NODES, { editable: false, reviewable: false })); // the role gone
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Mein Satz.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises(); // refused, the draft kept; reading the tree again fails

    await wrapper.get(".document-tree__partial button").trigger("click");
    await flushPromises();

    expect(wrapper.find(".row-editor").exists()).toBe(false);
    expect(wrapper.get(".row-panel__closed").text()).toBe("Bearbeiten dürfen der Eigentümer und die Redaktion.");
  });

  it("asks nothing of a draft that went with another document", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Mein Entwurf.");

    void router.push({ name: "documentTree", params: { id: "d2" } });
    await flushPromises();
    await answer(wrapper, "Verwerfen");

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect([router.currentRoute.value.params.id, event.defaultPrevented]).toEqual(["d2", false]);
    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
  });

  it("says a tree whose entry's content is no longer the caller's is theirs no more, with no retry", async () => {
    vi.spyOn(api, "getTree").mockRejectedValue(new ApiError("forbidden", 403, "file_hidden"));

    const wrapper = await open();

    expect(wrapper.text()).toContain(t("refusals.file_hidden"));
    expect(wrapper.findAll("button").some((button) => button.text() === t("states.retry"))).toBe(false);
  });

  it("keeps the tree where reading it again fails, says so and reads again on request", async () => {
    const read = vi
      .spyOn(api, "getTree")
      .mockResolvedValueOnce(OPEN)
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(OPEN);
    vi.spyOn(api, "editStatement").mockResolvedValue({ ...statement_("s1"), revision: 2 });
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Neu.");
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();

    expect(wrapper.findAll("[role=treeitem]")).toHaveLength(3);
    expect(wrapper.get(".document-tree__partial").text()).toContain(t("documents.tree.loadFailed"));
    const retry = wrapper.get(".document-tree__partial button");
    (retry.element as HTMLElement).focus();
    await retry.trigger("click");
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(3);
    expect(wrapper.get(".document-tree__partial").text()).toBe("");
    // the button gone with the notice: the keyboard to the tree's heading, not lost
    expect(document.activeElement).toBe(wrapper.get("#document-tree-rows").element);
  });

  it("asks before a draft goes with another row: staying keeps row and draft, discarding moves on", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Mein Entwurf.");

    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();
    expect(wrapper.get("[role=dialog]").text()).toContain("Änderungen verwerfen?");
    await answer(wrapper, "Weiter bearbeiten");

    expect(query()).toEqual({ zeile: "statement:s1" });
    expect((wrapper.get(".row-form textarea").element as HTMLTextAreaElement).value).toBe("Mein Entwurf.");
    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();
    await answer(wrapper, "Verwerfen");
    expect(query()).toEqual({ zeile: "statement:s2" });
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
  });

  it("refuses a second move while it asks, and makes the move asked about once it is to go", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Mein Entwurf.");
    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();

    const second = await router.push({ name: "document", params: { id: "d1" } }); // a second press, say
    await answer(wrapper, "Verwerfen");

    expect(second).toBeTruthy(); // refused: a navigation failure, not a move
    expect(router.currentRoute.value.name).toBe("documentTree");
    expect(query()).toEqual({ zeile: "statement:s2" });
  });

  it("lets the source's page change and a saved row go unasked", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    vi.spyOn(api, "editStatement").mockImplementation((id, revision, fields) =>
      Promise.resolve({ ...statement_(id), revision: revision + 1, fields: { verbatim: String(fields.verbatim) } }),
    );
    const wrapper = await open({ zeile: "statement:s1" });
    await wrapper.get(".row-form textarea").setValue("Mein Entwurf.");

    await wrapper.get("[data-test=next]").trigger("click");
    await flushPromises();
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
    await wrapper.get(".row-form").trigger("submit");
    await flushPromises();
    await wrapper.get("[data-key='statement:s2']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
    expect(query()).toMatchObject({ zeile: "statement:s2" });
  });

  it("asks before a draft goes with the page, and the browser before the tab closes", async () => {
    vi.spyOn(api, "getTree").mockResolvedValue(OPEN);
    const wrapper = await open({ zeile: "statement:s1" });
    const unload = (): boolean => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(unload()).toBe(false);
    await wrapper.get(".row-form textarea").setValue("Mein Entwurf.");
    expect(unload()).toBe(true);

    void router.push({ name: "document", params: { id: "d1" } });
    await flushPromises();
    expect(wrapper.get("[role=dialog]").text()).toContain("Änderungen verwerfen?");
    await answer(wrapper, "Verwerfen");

    expect(router.currentRoute.value.name).toBe("document");
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
