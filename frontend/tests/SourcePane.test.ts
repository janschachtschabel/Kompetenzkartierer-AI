import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type DocumentPage } from "@/api";
import type { AnchorTaking } from "@/anchorDraft";
import SourcePane from "@/components/SourcePane.vue";
import { t } from "@/i18n/de";
import { router } from "@/router";

import { violations } from "./axe";
import { block } from "./conversions";

let shown: VueWrapper | null = null;

beforeEach(() => {
  vi.restoreAllMocks();
  api.setToken("kka_token");
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

function page(number: number, changes: Partial<DocumentPage> = {}): DocumentPage {
  return {
    page: number,
    pages: 9,
    printed_page: null,
    blocks: [block(`p${number}-b1`, `Erster auf ${number}`), block(`p${number}-b2`, `Zweiter auf ${number}`)],
    continued: [],
    ...changes,
  };
}

async function pane(number: number, cited: string[] = []): Promise<VueWrapper> {
  await router.push({ name: "conversion", params: { id: "s1" } });
  shown = mount(SourcePane, {
    props: { documentId: "d1", page: number, cited },
    global: { plugins: [router] },
    attachTo: document.body,
  });
  await flushPromises();
  return shown;
}

describe("the source under a row", () => {
  it("shows a page of the document's own conversion, the blocks its anchors name marked", async () => {
    const read = vi.spyOn(api, "getDocumentBlocks").mockImplementation((_id, number) => Promise.resolve(page(number)));

    const wrapper = await pane(3, ["p3-b2"]);

    expect(read).toHaveBeenCalledWith("d1", 3);
    expect(wrapper.get("h2").text()).toBe("Quelle");
    expect(wrapper.text()).toContain("Seite 3 von 9");
    expect(wrapper.findAll(".block").map((item) => item.classes("block--cited"))).toEqual([false, true]);
    expect(wrapper.text()).toContain("Mit „Beleg“ markiert: die Blöcke, die die gewählte Zeile nennt.");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("asks for another page by its pager, and reads the page it is given", async () => {
    const read = vi.spyOn(api, "getDocumentBlocks").mockImplementation((_id, number) => Promise.resolve(page(number)));
    const wrapper = await pane(3);

    await wrapper.get("[data-test=next]").trigger("click");
    expect(wrapper.emitted("go")).toEqual([[4]]);
    await wrapper.setProps({ page: 4 });
    await flushPromises();

    expect(read).toHaveBeenLastCalledWith("d1", 4);
    expect(wrapper.text()).toContain("Erster auf 4");
  });

  it("drops a page a later one overtook", async () => {
    let early: (found: DocumentPage) => void = () => undefined;
    vi.spyOn(api, "getDocumentBlocks")
      .mockReturnValueOnce(new Promise((resolve) => (early = resolve)))
      .mockResolvedValueOnce(page(5));
    const wrapper = await pane(4);

    await wrapper.setProps({ page: 5 });
    await flushPromises();
    early(page(4));
    await flushPromises();

    expect(wrapper.text()).toContain("Erster auf 5");
    expect(wrapper.text()).not.toContain("Erster auf 4");
  });

  it("says a reading failed, and reads the page again on request", async () => {
    const read = vi
      .spyOn(api, "getDocumentBlocks")
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValueOnce(page(2));
    const wrapper = await pane(2);

    expect(wrapper.find(".block").exists()).toBe(false);
    expect(wrapper.text()).toContain("Die Quelle wurde nicht geladen.");
    expect(await violations(wrapper.html())).toEqual([]);
    await wrapper.findAll("button").find((button) => button.text() === t("states.retry"))?.trigger("click");
    await flushPromises();

    expect(read).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll(".block")).toHaveLength(2);
  });

  it("says a page without blocks is empty", async () => {
    vi.spyOn(api, "getDocumentBlocks").mockResolvedValue(page(7, { blocks: [] }));

    const wrapper = await pane(7);

    expect(wrapper.text()).toContain("Auf dieser Seite steht kein Text"); // as on the conversion's page
  });

  it("says while another page loads that it does, the pager showing the page asked for", async () => {
    let later: (found: DocumentPage) => void = () => undefined;
    vi.spyOn(api, "getDocumentBlocks")
      .mockResolvedValueOnce(page(3))
      .mockReturnValueOnce(new Promise((resolve) => (later = resolve)));
    const wrapper = await pane(3);

    await wrapper.setProps({ page: 4 });

    expect(wrapper.text()).not.toContain("Erster auf 3");
    expect(wrapper.find(".loading").exists()).toBe(true);
    expect(wrapper.findAll("[role=status]")).toHaveLength(1); // the loading says nothing: the move is said once shown
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("4");
    later(page(4));
    await flushPromises();
    expect(wrapper.find(".loading").exists()).toBe(false);
  });

  it("says the page it moved to once it shows, and takes the focus to its heading from where the move began", async () => {
    vi.spyOn(api, "getDocumentBlocks").mockImplementation((_id, number) => Promise.resolve(page(number)));
    const wrapper = await pane(3);
    const status = wrapper.get("[role=status]");
    expect(status.text()).toBe(""); // the first page is no move
    const next = wrapper.get("[data-test=next]").element as HTMLButtonElement;
    next.focus();

    await wrapper.setProps({ page: 4 });
    await flushPromises();

    expect(status.text()).toBe("Seite 4 von 9: 2 Blöcke.");
    expect(document.activeElement).toBe(wrapper.get("h2").element);
  });

  it("leaves the focus where a move begun outside it was asked for", async () => {
    vi.spyOn(api, "getDocumentBlocks").mockImplementation((_id, number) => Promise.resolve(page(number)));
    const outside = document.createElement("button"); // a row of the tree, say
    document.body.append(outside);
    const wrapper = await pane(3);
    outside.focus();

    await wrapper.setProps({ page: 4 });
    await flushPromises();

    expect(wrapper.get("[role=status]").text()).toBe("Seite 4 von 9: 2 Blöcke."); // said all the same
    expect(document.activeElement).toBe(outside);
  });

  it("takes the focus to its heading when asked to, as for an anchor's page", async () => {
    vi.spyOn(api, "getDocumentBlocks").mockImplementation((_id, number) => Promise.resolve(page(number)));
    const wrapper = await pane(3);

    (wrapper.vm as unknown as { focus: () => void }).focus();

    expect(document.activeElement).toBe(wrapper.get("h2").element);
  });

  it("leaves the focus where the reader went on to while the page loaded", async () => {
    let later: (found: DocumentPage) => void = () => undefined;
    vi.spyOn(api, "getDocumentBlocks")
      .mockResolvedValueOnce(page(3))
      .mockReturnValueOnce(new Promise((resolve) => (later = resolve)));
    const elsewhere = document.createElement("button");
    document.body.append(elsewhere);
    const wrapper = await pane(3);

    await wrapper.setProps({ page: 4 });
    elsewhere.focus();
    later(page(4));
    await flushPromises();

    expect(document.activeElement).toBe(elsewhere);
  });

  it("says a page past the end is none, keeps its pager and offers the first page", async () => {
    vi.spyOn(api, "getDocumentBlocks")
      .mockResolvedValueOnce(page(3))
      .mockRejectedValueOnce(new ApiError("server", 404, "no_such_page"));
    const wrapper = await pane(3);

    await wrapper.setProps({ page: 12 });
    await flushPromises();

    expect(wrapper.text()).toContain("Die Datei hat 9 Seiten.");
    expect(wrapper.get("[role=status]").text()).toBe("Diese Seite gibt es nicht"); // not the page before
    expect(wrapper.find("[data-test=next]").exists()).toBe(true);
    const first = wrapper.findAll("button").find((button) => button.text() === "Zur ersten Seite");
    (first?.element as HTMLElement).focus();
    await first?.trigger("click");
    expect(wrapper.emitted("go")).toEqual([[1]]);
  });

  it("takes the focus to its heading where the control the move began at is gone", async () => {
    vi.spyOn(api, "getDocumentBlocks")
      .mockRejectedValueOnce(new ApiError("server", 404, "no_such_page"))
      .mockResolvedValueOnce(page(1));
    const wrapper = await pane(12);
    const first = wrapper.findAll("button").find((button) => button.text() === "Zur ersten Seite");
    (first?.element as HTMLElement).focus();

    await wrapper.setProps({ page: 1 }); // the way to the first page goes with the page past the end
    await flushPromises();

    expect(document.activeElement).toBe(wrapper.get("h2").element);
  });

  it("says, moved to, that the content is no longer the reader's, and offers no other page", async () => {
    vi.spyOn(api, "getDocumentBlocks")
      .mockResolvedValueOnce(page(3))
      .mockRejectedValueOnce(new ApiError("forbidden", 403, "file_hidden"));
    const wrapper = await pane(3);

    await wrapper.setProps({ page: 4 });
    await flushPromises();

    expect(wrapper.get("[role=status]").text()).toBe(t("conversionPage.hiddenTitle"));
    expect(wrapper.find("[data-test=next]").exists()).toBe(false);
  });

  it("offers no pager while another page loads after a refusal of the content, and again once one shows", async () => {
    let later: (found: DocumentPage) => void = () => undefined;
    vi.spyOn(api, "getDocumentBlocks")
      .mockResolvedValueOnce(page(3))
      .mockRejectedValueOnce(new ApiError("forbidden", 403, "file_hidden"))
      .mockReturnValueOnce(new Promise((resolve) => (later = resolve)));
    const wrapper = await pane(3);
    await wrapper.setProps({ page: 4 });
    await flushPromises();

    await wrapper.setProps({ page: 5 });
    expect(wrapper.find(".loading").exists()).toBe(true);
    expect(wrapper.find("[data-test=next]").exists()).toBe(false);
    later(page(5));
    await flushPromises();

    expect(wrapper.text()).toContain("Erster auf 5");
    expect(wrapper.find("[data-test=next]").exists()).toBe(true);
  });

  it("says the entry's content is no longer the reader's, with no retry that could change it", async () => {
    vi.spyOn(api, "getDocumentBlocks").mockRejectedValue(new ApiError("forbidden", 403, "file_hidden"));

    const wrapper = await pane(2);

    expect(wrapper.text()).toContain(t("refusals.file_hidden"));
    expect(wrapper.findAll("button").some((button) => button.text() === t("states.retry"))).toBe(false);
    expect(await violations(wrapper.html())).toEqual([]);
  });
});

describe("the source a statement's anchor is chosen in", () => {
  let taking = vi.fn<(code: string) => AnchorTaking>(() => "taken");

  async function choosing(number: number, picking: string | null = "statement:s1"): Promise<VueWrapper> {
    taking = vi.fn<(code: string) => AnchorTaking>(() => "taken");
    vi.spyOn(api, "getDocumentBlocks").mockImplementation((_id, at) => Promise.resolve(page(at)));
    await router.push({ name: "conversion", params: { id: "s1" } });
    shown = mount(SourcePane, {
      props: { documentId: "d1", page: number, cited: [], picking, takeAnchor: taking },
      global: { plugins: [router] },
      attachTo: document.body,
    });
    await flushPromises();
    return shown;
  }

  const take = (wrapper: VueWrapper) => wrapper.get("[data-test=take]");
  const toggle = (wrapper: VueWrapper, index: number) => wrapper.findAll(".block button")[index];
  const pressed = (wrapper: VueWrapper) => wrapper.findAll(".block button").map((one) => one.attributes("aria-pressed"));
  const said = (wrapper: VueWrapper) => wrapper.get("[role=status]").text();
  const shownSaid = (wrapper: VueWrapper) => wrapper.get(".anchor-pick__said").text();

  it("takes the blocks chosen as one anchor, in their order, and lets the choice go", async () => {
    const wrapper = await choosing(3);
    expect(wrapper.text()).toContain(t("documents.tree.source.pickNote"));
    expect([take(wrapper).text(), take(wrapper).attributes("aria-disabled")]).toEqual([
      "Gewählte Blöcke als Fundstelle übernehmen (0)",
      "true",
    ]);
    await take(wrapper).trigger("click");
    expect(taking).not.toHaveBeenCalled(); // none chosen, none taken

    await toggle(wrapper, 1)?.trigger("click");
    expect(take(wrapper).text()).toBe("Gewählten Block als Fundstelle übernehmen (1)");
    await toggle(wrapper, 0)?.trigger("click");
    expect(pressed(wrapper)).toEqual(["true", "true"]);
    expect([take(wrapper).text(), take(wrapper).attributes("aria-disabled")]).toEqual([
      "Gewählte Blöcke als Fundstelle übernehmen (2)",
      undefined,
    ]);
    expect(await violations(wrapper.html())).toEqual([]);

    (take(wrapper).element as HTMLElement).focus();
    await take(wrapper).trigger("click");
    expect(taking).toHaveBeenCalledWith("blocks:p3-b1,p3-b2");
    expect(pressed(wrapper)).toEqual(["false", "false"]);
    expect(said(wrapper)).toBe("Fundstelle übernommen – Seite 3: 2 Blöcke (p3-b1, p3-b2).");
    // said where it was taken too, the keyboard kept there
    expect(shownSaid(wrapper)).toBe("Fundstelle übernommen – Seite 3: 2 Blöcke (p3-b1, p3-b2).");
    expect(document.activeElement).toBe(take(wrapper).element);
  });

  it("offers to take them after the blocks, the way to choose before them", async () => {
    const wrapper = await choosing(3);

    const note = wrapper.findAll("p").find((one) => one.text() === t("documents.tree.source.pickNote"));
    if (!note) throw new Error("no way to choose said");
    const blocks = wrapper.get(".blocks").element;
    expect(note.element.compareDocumentPosition(blocks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(blocks.compareDocumentPosition(take(wrapper).element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("says an anchor the draft holds already, or one it takes no more", async () => {
    const wrapper = await choosing(3);

    taking.mockReturnValueOnce("held");
    await wrapper.get("[data-test=not-found]").trigger("click");
    expect(said(wrapper)).toBe("Diese Fundstelle steht schon im Entwurf – Auf Seite 3 nicht gefunden.");

    taking.mockReturnValueOnce("refused");
    await wrapper.get("[data-test=not-found]").trigger("click");
    expect(said(wrapper)).toBe(t("documents.tree.source.refused"));
    expect(shownSaid(wrapper)).toBe(t("documents.tree.source.refused"));
  });

  it("lets a block chosen go again", async () => {
    const wrapper = await choosing(3);

    await toggle(wrapper, 0)?.trigger("click");
    await toggle(wrapper, 0)?.trigger("click");

    expect(pressed(wrapper)).toEqual(["false", "false"]);
    expect(take(wrapper).text()).toContain("(0)");
  });

  it("takes the page shown as one the passage was not found on", async () => {
    const wrapper = await choosing(3);

    await wrapper.get("[data-test=not-found]").trigger("click");

    expect(wrapper.get("[data-test=not-found]").text()).toBe("Seite 3 als „nicht gefunden“ übernehmen");
    expect(taking).toHaveBeenCalledWith("page:3");
    expect(said(wrapper)).toBe("Fundstelle übernommen – Auf Seite 3 nicht gefunden.");
  });

  it("lets the choice and what it said go with another page, another statement or document", async () => {
    const wrapper = await choosing(3);
    await toggle(wrapper, 0)?.trigger("click");
    await wrapper.get("[data-test=not-found]").trigger("click");

    await wrapper.setProps({ page: 4 });
    await flushPromises();
    expect(pressed(wrapper)).toEqual(["false", "false"]);
    expect(take(wrapper).text()).toContain("(0)");
    expect(wrapper.find(".anchor-pick__said").exists()).toBe(false);

    await toggle(wrapper, 0)?.trigger("click");
    await wrapper.setProps({ picking: "statement:s2" });
    await flushPromises();
    expect(take(wrapper).text()).toContain("(0)");

    await toggle(wrapper, 0)?.trigger("click");
    await wrapper.setProps({ documentId: "d2" });
    await flushPromises();
    expect(take(wrapper).text()).toContain("(0)");
  });

  it("offers nothing to choose while no statement's anchor is, nor where no page shows", async () => {
    const reading = await choosing(3, null);
    expect(reading.find("[data-test=take]").exists()).toBe(false);
    expect(reading.findAll(".block button")).toHaveLength(0);
    reading.unmount();

    vi.spyOn(api, "getDocumentBlocks").mockRejectedValue(new ApiError("forbidden", 403, "file_hidden"));
    shown = mount(SourcePane, {
      props: { documentId: "d1", page: 3, cited: [], picking: "statement:s1" },
      global: { plugins: [router] },
      attachTo: document.body,
    });
    await flushPromises();
    expect(shown.find("[data-test=take]").exists()).toBe(false);
  });
});
