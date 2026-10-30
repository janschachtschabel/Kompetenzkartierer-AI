import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RouterView } from "vue-router";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type DocumentPage, type TreeAnchor, type TreeStatement } from "@/api";
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
    await wrapper.get(".document-tree__partial button").trigger("click");
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(3);
    expect(wrapper.get(".document-tree__partial").text()).toBe("");
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
