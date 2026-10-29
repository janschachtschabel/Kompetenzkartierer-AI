import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type DocumentPage } from "@/api";
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

describe("the source beside a row", () => {
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

  it("says why it shows no blocks, and reads the page again on request", async () => {
    const read = vi
      .spyOn(api, "getDocumentBlocks")
      .mockRejectedValueOnce(new ApiError("forbidden", 403, "file_hidden"))
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
});
