import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import { t } from "@/i18n/de";
import { router } from "@/router";
import ConversionView from "@/views/ConversionView.vue";

import { block, blockPage, conversion, table } from "./conversions";
import { deferred, detail } from "./registerEntries";

const PDF = { name: "physik.pdf", mime: "application/pdf", size: 8, sha256: "ab" };
let shown: VueWrapper | null = null;

/** The entry's blocks at `query`, as the app opens them: the navigation first, then the page. */
async function open(query: Record<string, string> = {}): Promise<VueWrapper> {
  shown?.unmount();
  await router.push({ name: "conversion", params: { id: "s1" }, query });
  shown = mount(ConversionView, { props: { id: "s1" }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

const heading = (wrapper: VueWrapper) => wrapper.get("h2#conversion-page-heading");
const status = (wrapper: VueWrapper) => wrapper.get("[data-test=page-status]");

beforeEach(() => {
  vi.restoreAllMocks();
  api.setToken("kka_token");
  vi.spyOn(api, "getSource").mockResolvedValue(detail({ file: PDF, mine: true }));
  vi.spyOn(api, "getConversion").mockResolvedValue(conversion());
  vi.spyOn(api, "getBlocks").mockImplementation((_id, page) =>
    Promise.resolve(blockPage(page, [block(`p${page}-b1`, `Text der Seite ${page}`)])),
  );
});

afterEach(async () => {
  shown?.unmount();
  shown = null;
  api.clearToken();
  await router.push("/");
});

describe("an entry's blocks", () => {
  it("say they load, then name the entry, the page and its blocks, each with its id", async () => {
    vi.mocked(api.getBlocks).mockResolvedValue(
      blockPage(1, [
        block("p1-b1", "Lehrplan Physik", { bold: true }),
        block("p1-b2", "Die Schülerinnen und Schüler\nexperimentieren.", { italic: true }),
      ]),
    );
    await router.push({ name: "conversion", params: { id: "s1" } });
    shown = mount(ConversionView, { props: { id: "s1" }, global: { plugins: [router] }, attachTo: document.body });
    expect(shown.text()).toContain(t("states.loading"));
    await flushPromises();
    const wrapper = shown;

    expect(wrapper.get("h1").text()).toBe("Rheinland-Pfalz · Physik · Gymnasium");
    expect(heading(wrapper).text()).toBe(t("conversionPage.pageHeading", { page: 1, pages: 3 }));
    const items = wrapper.findAll(".block");
    expect(items.map((item) => item.get(".block__id").text())).toEqual(["p1-b1", "p1-b2"]);
    expect(items[0].text()).toContain(t("conversionPage.bold"));
    expect(items[1].text()).toContain(t("conversionPage.italic"));
    // the conversion's line breaks stay, as text: nothing of the file is read as markup
    expect(items[1].get(".block__text").element.textContent).toBe("Die Schülerinnen und Schüler\nexperimentieren.");
    expect(api.getBlocks).toHaveBeenCalledWith("s1", 1);
  });

  it("say what a block is where it is more than text: a running head or foot", async () => {
    vi.mocked(api.getBlocks).mockResolvedValue(
      blockPage(1, [
        block("p1-b1", "Kerncurriculum Physik", { kind: "page_header" }),
        block("p1-b2", "Inhalt"),
        block("p1-b3", "Seite 1", { kind: "page_footer" }),
      ]),
    );
    const wrapper = await open();

    const items = wrapper.findAll(".block");
    expect(items[0].text()).toContain(t("conversionPage.kind.page_header"));
    expect(items[1].find(".block__kind").exists()).toBe(false);
    expect(items[2].text()).toContain(t("conversionPage.kind.page_footer"));
  });

  it.each([
    [{ seite: "2" }, 2],
    [{}, 1],
    [{ seite: "abc" }, 1],
    [{ seite: "0" }, 1],
    [{ seite: "-1" }, 1],
    [{ seite: "2.5" }, 1],
  ])("read the page from the address %j: page %i", async (query, page) => {
    const wrapper = await open(query);

    expect(api.getBlocks).toHaveBeenCalledWith("s1", page);
    expect(heading(wrapper).text()).toBe(t("conversionPage.pageHeading", { page, pages: 3 }));
  });

  it("show the number printed on the page where the conversion found one", async () => {
    const wrapper = await open({ seite: "3" });
    expect(wrapper.text()).toContain(t("conversionPage.printed", { printed: "2" }));

    const first = await open();
    expect(first.find("[data-test=printed]").exists()).toBe(false);
  });

  it("go to the next page and back by keyboard, the heading taking the focus and the move said", async () => {
    const wrapper = await open();
    const next = wrapper.get<HTMLButtonElement>("[data-test=next]");
    next.element.focus();

    await next.trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query.seite).toBe("2");
    expect(api.getBlocks).toHaveBeenLastCalledWith("s1", 2);
    expect(heading(wrapper).text()).toBe(t("conversionPage.pageHeading", { page: 2, pages: 3 }));
    expect(document.activeElement).toBe(heading(wrapper).element);
    expect(status(wrapper).text()).toBe(t("conversionPage.announce", { page: 2, pages: 3, count: 1 }));

    const previous = wrapper.get<HTMLButtonElement>("[data-test=previous]");
    previous.element.focus();
    await previous.trigger("click");
    await flushPromises();

    // the first page is the address without its number
    expect(router.currentRoute.value.query.seite).toBeUndefined();
    expect(wrapper.get(".block__id").text()).toBe("p1-b1");
    expect(document.activeElement).toBe(heading(wrapper).element);
  });

  it("keep a step that leads nowhere in reach, said to be unavailable, and take it nowhere", async () => {
    const first = await open();
    const previous = first.get("[data-test=previous]");
    expect(previous.attributes("aria-disabled")).toBe("true");
    expect(previous.attributes("disabled")).toBeUndefined();
    expect(first.get("[data-test=next]").attributes("aria-disabled")).toBeUndefined();

    await previous.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.seite).toBeUndefined();

    const last = await open({ seite: "3" });
    expect(last.get("[data-test=next]").attributes("aria-disabled")).toBe("true");
    expect(last.get("[data-test=previous]").attributes("aria-disabled")).toBeUndefined();
  });

  it("go to the page typed into the field, and refuse one the file does not have beside it", async () => {
    const wrapper = await open();
    const field = wrapper.get<HTMLInputElement>("#pager-page");
    expect(field.element.value).toBe("1");

    await field.setValue("3");
    await wrapper.get("form.pager__jump").trigger("submit");
    await flushPromises();
    expect(router.currentRoute.value.query.seite).toBe("3");
    expect(document.activeElement).toBe(heading(wrapper).element);

    await field.setValue("9");
    await wrapper.get("form.pager__jump").trigger("submit");
    await flushPromises();

    expect(router.currentRoute.value.query.seite).toBe("3");
    expect(wrapper.get("#pager-error").text()).toBe(t("conversionPage.pager.invalid", { pages: 3 }));
    expect(wrapper.get("#pager-error").attributes("role")).toBe("alert");
    expect(field.attributes("aria-invalid")).toBe("true");
    expect(field.attributes("aria-describedby")).toContain("pager-error");
  });

  it("say a page without blocks is empty", async () => {
    vi.mocked(api.getBlocks).mockResolvedValue(blockPage(1, []));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("conversionPage.emptyTitle"));
    expect(wrapper.find(".block").exists()).toBe(false);
  });

  it("show a table as a table: its header cells head their columns, each cell says its id", async () => {
    vi.mocked(api.getBlocks).mockResolvedValue(blockPage(2, [block("p2-b1", "Kompetenzen"), table()]));
    const wrapper = await open({ seite: "2" });

    const grid = wrapper.get("table");
    expect(grid.get("caption").text()).toBe(t("conversionPage.table.caption", { table: "1" }));
    const headers = grid.findAll("th");
    expect(headers.map((header) => header.attributes("scope"))).toEqual(["col", "col"]);
    expect(headers[0].text()).toContain("Kompetenz");
    const rows = grid.findAll("tr");
    expect(rows).toHaveLength(3);
    expect(rows[1].findAll("td").map((data) => data.get(".cell__id").text())).toEqual(["T1:r2c1", "T1:r2c2"]);
    // the cell the file left empty keeps its column
    expect(rows[2].findAll("td")).toHaveLength(2);
    // a cell carried over from the next page says where it stands
    expect(rows[2].text()).toContain(t("conversionPage.table.onPage", { page: 3 }));
    expect(rows[1].text()).not.toContain(t("conversionPage.table.onPage", { page: 2 }));
    // the table is not shown a second time as its text
    expect(wrapper.text()).not.toContain("| Kompetenz | Stufe |");
  });

  it("say the file is not converted yet, with the way to the entry where it is started", async () => {
    vi.mocked(api.getConversion).mockRejectedValue(new ApiError("server", 404, "no_conversion"));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("conversionPage.notConvertedTitle"));
    expect(wrapper.text()).toContain(t("refusals.no_conversion"));
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
    expect(wrapper.get("[data-test=to-entry]").attributes("href")).toBe("/quellen/s1");
    expect(api.getBlocks).not.toHaveBeenCalled();
  });

  it.each([
    ["pending", "refusals.not_converted"],
    ["failed", "conversionPage.failedBody"],
  ] as const)("say a conversion %s is no blocks yet", async (state, words) => {
    vi.mocked(api.getConversion).mockResolvedValue(conversion({ status: state, pages: null, printed_pages: null }));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t(words));
    expect(api.getBlocks).not.toHaveBeenCalled();
  });

  it("say the blocks are the editors' where the file is", async () => {
    vi.mocked(api.getConversion).mockRejectedValue(new ApiError("forbidden", 403, "file_hidden"));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("conversionPage.hiddenTitle"));
    expect(wrapper.text()).toContain(t("refusals.file_hidden"));
  });

  it("say an entry it cannot see is not there, and lead back to the register", async () => {
    vi.mocked(api.getSource).mockRejectedValue(new ApiError("server", 404, "not_found"));
    vi.mocked(api.getConversion).mockRejectedValue(new ApiError("server", 404, "not_found"));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("entryPage.notFoundTitle"));
    expect(wrapper.get("[data-test=to-register]").attributes("href")).toBe("/quellen");
  });

  it("say a page past the file's end is not there, with the way to its first", async () => {
    const wrapper = await open({ seite: "9" });

    expect(wrapper.text()).toContain(t("conversionPage.noPageTitle"));
    expect(api.getBlocks).not.toHaveBeenCalled();

    await wrapper.get("[data-test=first-page]").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.seite).toBeUndefined();
    expect(api.getBlocks).toHaveBeenCalledWith("s1", 1);
  });

  it("say a page the server does not have is not there, should it know better than the conversion", async () => {
    vi.mocked(api.getBlocks).mockRejectedValue(new ApiError("server", 404, "no_such_page"));
    const wrapper = await open({ seite: "2" });

    expect(wrapper.text()).toContain(t("conversionPage.noPageTitle"));
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
  });

  it("say when a page did not load, and load it again on request", async () => {
    vi.mocked(api.getBlocks)
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue(blockPage(1, [block("p1-b1", "Wieder da")]));
    const wrapper = await open();
    expect(wrapper.get("[role=alert]").text()).toContain(t("conversionPage.pageFailed"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(wrapper.get(".block__text").text()).toBe("Wieder da");
    // the retry button went with the alert: the keyboard is at the page's heading
    expect(document.activeElement).toBe(heading(wrapper).element);
  });

  it("say when the entry's conversion did not load, and load it again on request", async () => {
    vi.mocked(api.getConversion)
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(conversion());
    const wrapper = await open();
    expect(wrapper.get("[role=alert]").text()).toContain(t("conversionPage.loadFailed"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(wrapper.find(".block").exists()).toBe(true);
  });

  it("show the page it was moved on to, whichever answer comes last", async () => {
    const wrapper = await open();
    const second = deferred<api.BlockPage>();
    const third = deferred<api.BlockPage>();
    vi.mocked(api.getBlocks).mockImplementation((_id, page) => (page === 2 ? second.promise : third.promise));

    await wrapper.get("[data-test=next]").trigger("click");
    await flushPromises();
    await wrapper.get("[data-test=next]").trigger("click");
    await flushPromises();
    third.resolve(blockPage(3, [block("p3-b1", "Dritte")]));
    await flushPromises();
    second.resolve(blockPage(2, [block("p2-b1", "Zweite")]));
    await flushPromises();

    expect(heading(wrapper).text()).toBe(t("conversionPage.pageHeading", { page: 3, pages: 3 }));
    expect(wrapper.get(".block__text").text()).toBe("Dritte");
  });

  it("name the entry and the page in the browser's title (WCAG 2.4.2)", async () => {
    await open({ seite: "2" });
    expect(document.title).toBe(
      `${t("conversionPage.tabTitle", { title: "Rheinland-Pfalz · Physik · Gymnasium", page: 2 })} · ${t("app.title")}`,
    );

    await router.replace({ query: { seite: "3" } });
    await flushPromises();
    expect(document.title).toContain(t("conversionPage.tabTitle", { title: "Rheinland-Pfalz · Physik · Gymnasium", page: 3 }));
  });

  it("read no page of the address they are left for, nor name its tab", async () => {
    // a leaving transition keeps the page mounted under the next page's address
    await open({ seite: "2" });
    vi.mocked(api.getBlocks).mockClear();

    await router.push({ name: "sources" });
    await flushPromises();

    expect(api.getBlocks).not.toHaveBeenCalled();
    expect(document.title).toBe(`${t("app.titles.sources")} · ${t("app.title")}`);
  });

  it("lead back to the entry's page", async () => {
    const wrapper = await open();

    expect(wrapper.get(".conversion-page__back a").attributes("href")).toBe("/quellen/s1");
  });
});
