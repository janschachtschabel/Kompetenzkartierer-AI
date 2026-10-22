import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type SourceEntry, type SourcePage } from "@/api";
import { t } from "@/i18n/de";
import { router } from "@/router";
import UploadForm from "@/components/UploadForm.vue";
import SourcesView from "@/views/SourcesView.vue";

import { deferred, entry, job, page } from "./registerEntries";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getInfo").mockResolvedValue({
    name: "Kompetenzkartierer-AI",
    version: "0.1.0",
    public_access: "off",
    max_upload_mb: 50,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the register page", () => {
  it("says it loads, then shows the entries with what they are", async () => {
    vi.spyOn(api, "listSources").mockResolvedValue(
      page([entry("a", "Lehrplan Physik"), entry("b", "Lehrplan Chemie", { provenance: "url", register_status: "unchecked", file: null })]),
    );
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    expect(wrapper.text()).toContain(t("states.loading"));

    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain("Lehrplan Physik");
    expect(rows[0].text()).toContain(t("sources.provenance.upload"));
    expect(rows[0].text()).toContain(t("sources.status.acquired"));
    expect(rows[0].text()).toContain(t("sources.rights.unklar"));
    expect(rows[0].text()).toContain("22.10.2026");
    expect(rows[1].text()).toContain(t("sources.status.unchecked"));
    expect(rows[1].text()).toContain(t("sources.register.noFile"));
  });

  it("leads from each entry to its page", async () => {
    vi.spyOn(api, "listSources").mockResolvedValue(page([entry("0190-a", "Lehrplan Physik")]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });

    await flushPromises();

    const link = wrapper.get("tbody tr a");
    expect(link.attributes("href")).toBe("/quellen/0190-a");
    expect(link.text()).toBe("Lehrplan Physik");
  });

  it("names an entry whose file has not come yet by its address", async () => {
    // an import's title is the file's name, once the fetch has the file
    const address = "https://example.org/lehrplan.pdf";
    vi.spyOn(api, "listSources").mockResolvedValue(page([entry("a", "", { provenance: "url", url: address, file: null })]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });

    await flushPromises();

    expect(wrapper.get("tbody tr .register__title").text()).toBe(address);
    // said once: the title is the address already
    expect(wrapper.find("tbody tr [data-test=address]").exists()).toBe(false);
  });

  it("tells candidates of one title apart by their address, as text and not as a second link", async () => {
    const title = "Bayern · Biologie · Erster Schulabschluss (ESA)";
    const candidate = (id: string, grade: number) =>
      entry(id, title, {
        provenance: "vergleichsdatensatz-v62.493",
        register_status: "unchecked",
        file: null,
        mine: false,
        url: `https://www.lehrplanplus.bayern.de/fachlehrplan/realschule/${grade}/biologie`,
      });
    vi.spyOn(api, "listSources").mockResolvedValue(page([candidate("a", 5), candidate("b", 6)]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });

    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    expect(rows.map((row) => row.get("[data-test=address] bdi").text())).toEqual([
      "www.lehrplanplus.bayern.de/fachlehrplan/realschule/5/biologie",
      "www.lehrplanplus.bayern.de/fachlehrplan/realschule/6/biologie",
    ]);
    expect(rows[0].text()).toContain(t("sources.register.noFile"));
    expect(rows[0].findAll("a")).toHaveLength(1);
  });

  it("says the register is empty, and how to fill it", async () => {
    vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });

    await flushPromises();

    expect(wrapper.text()).toContain(t("sources.register.emptyTitle"));
    expect(wrapper.find("table").exists()).toBe(false);
  });

  it("says when the register did not load, and loads it again on request", async () => {
    const listed = vi
      .spyOn(api, "listSources")
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue(page([entry("a", "Lehrplan Physik")]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(t("sources.register.loadFailed"));
    expect(wrapper.get("[role=alert]").text()).toContain(t("refusals.service_unavailable"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(listed).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  });

  it("counts what it shows of all there are, and loads the next page on request", async () => {
    const first = Array.from({ length: 50 }, (_, index) => entry(`a${index}`, `Plan ${index}`));
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(page(first, 51))
      .mockResolvedValue(page([entry("z", "Der letzte")], 51, 50));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    expect(wrapper.text()).toContain(t("sources.register.shown", { shown: 50, total: 51 }));

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    expect(listed).toHaveBeenLastCalledWith({}, { offset: 50 });
    expect(wrapper.findAll("tbody tr")).toHaveLength(51);
    expect(wrapper.find("[data-test=more]").exists()).toBe(false);
  });

  it("keeps the entries it has when the next page does not load, and offers to try again", async () => {
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Plan")], 2))
      .mockRejectedValueOnce(new ApiError("network", 0));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    expect(wrapper.get(".page-notice").text()).toContain(t("sources.register.moreFailed"));
  });

  it("reads the register again after an upload", async () => {
    const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    vi.spyOn(api, "uploadSource").mockResolvedValue({
      id: "a",
      title: "Lehrplan",
      provenance: "upload",
      rights_status: "unklar",
      register_status: "acquired",
      file: null,
    });
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    const input = wrapper.get("#upload-file");
    Object.defineProperty(input.element, "files", { value: [new File(["%PDF"], "a.pdf")], configurable: true });
    await input.trigger("change");

    await wrapper.get("#upload-file").trigger("submit");
    await flushPromises();

    expect(listed).toHaveBeenCalledTimes(2);
  });

  it("follows an import's job and reads the register again once it ended", async () => {
    vi.useFakeTimers();
    const listed = vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    vi.spyOn(api, "importSource").mockResolvedValue({
      source: {
        id: "s",
        title: "",
        provenance: "url",
        rights_status: "unklar",
        register_status: "unchecked",
        file: null,
      },
      job_id: "j1",
    });
    vi.spyOn(api, "getJob").mockResolvedValue(job("done"));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await vi.advanceTimersByTimeAsync(0);
    await wrapper.get("#import-url").setValue("https://example.org/lehrplan.pdf");

    await wrapper.get("#import-url").trigger("submit");
    await vi.advanceTimersByTimeAsync(0);
    expect(wrapper.text()).toContain(t("sources.jobs.heading"));
    // its title waits for the file: the job is named by its address
    expect(wrapper.get(".job__label").text()).toBe("https://example.org/lehrplan.pdf");
    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.text()).toContain(t("jobs.status.done"));
    expect(listed).toHaveBeenCalledTimes(3); // on arrival, after the import, after the job
  });

  it("lets an upload through without the limit where the service's facts did not load", async () => {
    vi.spyOn(api, "getInfo").mockRejectedValue(new ApiError("network", 0));
    vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });

    await flushPromises();

    expect(wrapper.get("#upload-file-hint").text()).not.toContain("MB");
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
  });

  it("shows a value the page has no word for as it is, rather than an empty cell", async () => {
    const unknown = entry("a", "Plan", { provenance: "neu-v1" as SourceEntry["provenance"] });
    vi.spyOn(api, "listSources").mockResolvedValue(page([unknown]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });

    await flushPromises();

    expect(wrapper.get("tbody tr").text()).toContain("neu-v1");
  });
});

const FIFTY = Array.from({ length: 50 }, (_, index) => entry(`a${index}`, `Plan ${index}`));

function uploaded(): void {
  vi.spyOn(api, "uploadSource").mockResolvedValue({
    id: "new",
    title: "Neu",
    provenance: "upload",
    rights_status: "unklar",
    register_status: "acquired",
    file: null,
  });
}

async function upload(wrapper: ReturnType<typeof mount>): Promise<void> {
  const input = wrapper.get("#upload-file");
  Object.defineProperty(input.element, "files", { value: [new File(["%PDF"], "a.pdf")], configurable: true });
  await input.trigger("change");
  await input.trigger("submit");
  await flushPromises();
}

describe("paging through the register", () => {
  it("keeps what a reload brought, however a further page asked for meanwhile comes back", async () => {
    // an upload reads the register again; "Weitere laden" pressed before that answer is in
    uploaded();
    const reload = deferred<SourcePage>();
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockImplementationOnce(() => reload.promise)
      .mockResolvedValue(page([entry("a49", "Plan 49"), entry("a50", "Plan 50")], 52, 50));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await upload(wrapper);
    await wrapper.get("[data-test=more]").trigger("click");
    reload.resolve(page([entry("new", "Neu"), ...FIFTY.slice(0, 49)], 52));
    await flushPromises();

    const titles = wrapper.findAll("tbody tr .register__title").map((cell) => cell.text());
    expect(titles[0]).toBe("Neu");
    expect(titles).toHaveLength(50);
    expect(listed).toHaveBeenCalledTimes(2); // no further page asked for while the register was read again
  });

  it("says how many it shows in a region a screen reader follows", async () => {
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockResolvedValue(page([entry("z", "Der letzte")], 51, 50));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    const count = wrapper.get(".register__count");
    expect(count.attributes("role")).toBe("status");

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    expect(wrapper.get(".register__count").text()).toBe(t("sources.register.shown", { shown: 51, total: 51 }));
  });

  it("hands the focus to the first entry it added, as the button may go", async () => {
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockResolvedValue(page([entry("z", "Der letzte")], 51, 50));
    const wrapper = mount(SourcesView, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    // the row itself: the page's body holds the words too
    expect(document.activeElement?.tagName).toBe("TR");
    expect(document.activeElement?.textContent).toContain("Der letzte");
    wrapper.unmount();
  });

  it("reads the register from the start when entries moved between its pages", async () => {
    // someone added one meanwhile: the next page begins with one already shown
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockResolvedValueOnce(page([entry("a49", "Plan 49"), entry("a50", "Plan 50")], 52, 50))
      .mockResolvedValue(page([entry("x", "Dazwischen"), ...FIFTY.slice(0, 49)], 52));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    // one page more than was shown: the button still adds what it says
    expect(listed).toHaveBeenLastCalledWith({}, { limit: 100 });
    expect(wrapper.findAll("tbody tr .register__title")[0].text()).toBe("Dazwischen");
  });

  it("keeps the entries when a reload fails, says so, and reads again on request", async () => {
    uploaded();
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Plan")]))
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(page([entry("new", "Neu"), entry("a", "Plan")]));
    const wrapper = mount(SourcesView, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();

    await upload(wrapper);
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    expect(wrapper.get(".sources__partial").text()).toContain(t("sources.register.reloadFailed"));
    await wrapper.get(".sources__partial button").trigger("click");
    await flushPromises();

    expect(listed).toHaveBeenCalledTimes(3);
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
    expect(wrapper.get(".sources__partial").text()).toBe("");
    // the retry button went with the notice: the focus goes to the register, not the page's top
    expect(document.activeElement?.id).toBe("sources-register");
    wrapper.unmount();
  });

  it("says a failure in a region that is there before it, and keeps the way to try again while it tries", async () => {
    const retry = deferred<SourcePage>();
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Plan")], 2))
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockImplementationOnce(() => retry.promise);
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    const region = wrapper.get(".sources__partial");
    expect(region.attributes("role")).toBe("status");
    expect(region.text()).toBe("");

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();
    expect(wrapper.get(".sources__partial").text()).toContain(t("sources.register.moreFailed"));
    await wrapper.get(".sources__partial button").trigger("click");

    expect(wrapper.find(".sources__partial button").exists()).toBe(true);
    retry.resolve(page([entry("b", "Zweiter")], 2, 1));
    await flushPromises();
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
  });

  it("leaves the focus where the person went meanwhile", async () => {
    const next = deferred<SourcePage>();
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockImplementationOnce(() => next.promise);
    const wrapper = mount(SourcesView, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();
    const button = wrapper.get("[data-test=more]");
    (button.element as HTMLElement).focus();
    await button.trigger("click");

    // while the page is on its way, the person goes on to type an address
    (wrapper.get("#import-url").element as HTMLElement).focus();
    next.resolve(page([entry("z", "Der letzte")], 51, 50));
    await flushPromises();

    expect(document.activeElement?.id).toBe("import-url");
    wrapper.unmount();
  });

  it("reads again as many entries as it shows, so a later page and its focus stay", async () => {
    const listed = vi
      .spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 60))
      .mockResolvedValueOnce(page(Array.from({ length: 10 }, (_, index) => entry(`b${index}`, `Mehr ${index}`)), 60, 50))
      .mockResolvedValue(page([...FIFTY, ...Array.from({ length: 10 }, (_, index) => entry(`b${index}`, `Mehr ${index}`))], 60));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    wrapper.findComponent(UploadForm).vm.$emit("uploaded", { id: "x" });
    await flushPromises();

    expect(listed).toHaveBeenLastCalledWith({}, { limit: 60 });
    expect(wrapper.findAll("tbody tr")).toHaveLength(60);
  });

  it("keeps the newer of two readings, whichever answer comes last", async () => {
    const older = deferred<SourcePage>();
    const newer = deferred<SourcePage>();
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Plan")]))
      .mockImplementationOnce(() => older.promise)
      .mockImplementationOnce(() => newer.promise);
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    const form = wrapper.findComponent(UploadForm);

    form.vm.$emit("uploaded", { id: "x" });
    form.vm.$emit("uploaded", { id: "y" });
    newer.resolve(page([entry("y", "Neuer"), entry("a", "Plan")]));
    await flushPromises();
    older.resolve(page([entry("x", "Älter"), entry("a", "Plan")]));
    await flushPromises();

    expect(wrapper.findAll("tbody tr .register__title")[0].text()).toBe("Neuer");
  });

  it("says the way to more is busy while the register is read again", async () => {
    const reload = deferred<SourcePage>();
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockImplementationOnce(() => reload.promise);
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    wrapper.findComponent(UploadForm).vm.$emit("uploaded", { id: "x" });
    await flushPromises();

    expect(wrapper.get("[data-test=more]").attributes("aria-disabled")).toBe("true");
  });

  it("says a failure again when trying again fails again", async () => {
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page([entry("a", "Plan")], 2))
      .mockRejectedValue(new ApiError("network", 0));
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();
    const first = wrapper.get(".sources__partial").element.textContent;

    await wrapper.get(".sources__partial button").trigger("click");
    await flushPromises();

    expect(wrapper.get(".sources__partial").element.textContent).not.toBe(first);
  });

  it("keeps the focus where the person went when entries moved between the pages", async () => {
    // the person goes on to type while the next page is on its way; it overlaps, and the
    // register is read again - the focus is judged against where the press began
    const next = deferred<SourcePage>();
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockImplementationOnce(() => next.promise)
      .mockResolvedValue(page([entry("x", "Dazwischen"), ...FIFTY, entry("a50", "Plan 50")], 52));
    const wrapper = mount(SourcesView, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();
    const button = wrapper.get("[data-test=more]");
    (button.element as HTMLElement).focus();
    await button.trigger("click");

    (wrapper.get("#import-url").element as HTMLElement).focus();
    next.resolve(page([entry("a49", "Plan 49"), entry("a50", "Plan 50")], 52, 50));
    await flushPromises();

    expect(document.activeElement?.id).toBe("import-url");
    wrapper.unmount();
  });

  it("hands the focus to the entry after the last one shown when entries moved between the pages", async () => {
    vi.spyOn(api, "listSources")
      .mockResolvedValueOnce(page(FIFTY, 51))
      .mockResolvedValueOnce(page([entry("a49", "Plan 49"), entry("a50", "Plan 50")], 52, 50))
      .mockResolvedValue(page([entry("x", "Dazwischen"), ...FIFTY, entry("a50", "Plan 50")], 52));
    const wrapper = mount(SourcesView, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();

    await wrapper.get("[data-test=more]").trigger("click");
    await flushPromises();

    // the first one not read before - not the one at the old count, which the new entry pushed down
    expect(document.activeElement?.tagName).toBe("TR");
    expect(document.activeElement?.textContent).toContain("Plan 50");
    wrapper.unmount();
  });
});

