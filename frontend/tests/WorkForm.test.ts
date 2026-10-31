import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type DocumentWork } from "@/api";
import WorkForm from "@/components/WorkForm.vue";
import { t } from "@/i18n/de";
import { refusalText } from "@/refusals";

import { violations } from "./axe";
import { documentOf } from "./documentFixtures";

let shown: VueWrapper | null = null;

const KLP: DocumentWork = { id: "w1", title: "Kernlehrplan Physik", region: "DE-NW", short_title: "klp-physik", iri: null };
const OTHERS = [documentOf({ id: "d7", work: KLP }), documentOf({ id: "d8", work: null })];

async function form(): Promise<VueWrapper> {
  shown = mount(WorkForm, { props: { document: documentOf() }, attachTo: document.body });
  await flushPromises();
  return shown;
}

const control = <T extends HTMLElement = HTMLInputElement>(wrapper: VueWrapper, label: string) => {
  const found = wrapper.findAll("label").find((one) => one.text() === label);
  if (!found) throw new Error(label);
  return found.attributes("for") ? wrapper.get<T>(`#${found.attributes("for")}`) : found.get<T>("input");
};
const save = (wrapper: VueWrapper) => wrapper.get("form").trigger("submit");

async function fillNew(wrapper: VueWrapper, shortTitle = "klp-physik"): Promise<void> {
  await control(wrapper, t("documents.page.edition.workNew")).setValue(true);
  await control(wrapper, t("documents.page.edition.workTitle")).setValue("Kernlehrplan Physik");
  await control<HTMLSelectElement>(wrapper, t("documents.page.edition.workRegion")).setValue("DE-NW");
  await control(wrapper, t("documents.page.edition.workShortTitle")).setValue(shortTitle);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listDocuments").mockResolvedValue(OTHERS);
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("the form of a document's work", () => {
  it("offers the works of the documents the caller sees, and a new one", async () => {
    const wrapper = await form();

    const chosen = control<HTMLSelectElement>(wrapper, t("documents.page.edition.workChosen"));
    expect(chosen.findAll("option").map((one) => one.element.value)).toEqual(["", "w1"]);
    expect(chosen.findAll("option")[1].text()).toContain("Kernlehrplan Physik");
    expect(control(wrapper, t("documents.page.edition.workNew")).attributes("type")).toBe("radio");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("sets a work there is", async () => {
    const sent = vi.spyOn(api, "setWork").mockResolvedValue(documentOf({ work: KLP }));
    const wrapper = await form();

    await control<HTMLSelectElement>(wrapper, t("documents.page.edition.workChosen")).setValue("w1");
    await save(wrapper);
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("d1", { work_id: "w1" });
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.page.edition.workSaved"));
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("asks for a work to choose before it sends", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.page.edition.workChoose"));
    expect(control(wrapper, t("documents.page.edition.workChosen")).attributes("aria-invalid")).toBe("true");
  });

  it("makes a new work of its title, its land and its short title", async () => {
    const sent = vi.spyOn(api, "setWork").mockResolvedValue(documentOf({ work: KLP }));
    const wrapper = await form();

    await fillNew(wrapper);
    await save(wrapper);
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("d1", { title: "Kernlehrplan Physik", region: "DE-NW", short_title: "klp-physik" });
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("says a short title the IRI cannot take at its field, sending nothing", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await fillNew(wrapper, "KLP Physik");
    await save(wrapper);

    const short = control(wrapper, t("documents.page.edition.workShortTitle"));
    expect(sent).not.toHaveBeenCalled();
    expect(short.attributes("aria-invalid")).toBe("true");
    expect(short.attributes("aria-describedby")).toContain(wrapper.get("[role=alert]").attributes("id"));
    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.page.edition.workShortTitleBad"));
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("asks for the new work's title before it sends", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await fillNew(wrapper);
    await control(wrapper, t("documents.page.edition.workTitle")).setValue("  ");
    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(control(wrapper, t("documents.page.edition.workTitle")).attributes("aria-invalid")).toBe("true");
  });

  it("asks for the new work's land before it sends", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await fillNew(wrapper);
    await control<HTMLSelectElement>(wrapper, t("documents.page.edition.workRegion")).setValue("");
    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(control(wrapper, t("documents.page.edition.workRegion")).attributes("aria-invalid")).toBe("true");
    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.page.edition.workRegionChoose"));
  });

  it("says the server's problem with a field at the field", async () => {
    vi.spyOn(api, "setWork").mockRejectedValue(
      new ApiError("server", 422, "invalid_field", "Bad.", { field: "region", problem: "not_offered" }),
    );
    const wrapper = await form();

    await fillNew(wrapper);
    await save(wrapper);
    await flushPromises();

    expect(control(wrapper, t("documents.page.edition.workRegion")).attributes("aria-invalid")).toBe("true");
    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.tree.problems.not_offered"));
  });

  it("says a document named meanwhile and has it read again", async () => {
    vi.spyOn(api, "setWork").mockRejectedValue(new ApiError("server", 409, "named"));
    const wrapper = await form();

    await control<HTMLSelectElement>(wrapper, t("documents.page.edition.workChosen")).setValue("w1");
    await save(wrapper);
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("named"));
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("offers only a new work where none is known, and where the works were not read, saying so", async () => {
    vi.mocked(api.listDocuments).mockResolvedValueOnce([documentOf({ id: "d8" })]);
    const none = await form();
    expect(none.findAll("select").length).toBe(1); // the land alone
    expect(none.text()).toContain(t("documents.page.edition.workNone"));
    none.unmount();

    vi.mocked(api.listDocuments).mockRejectedValueOnce(new ApiError("network", 0));
    const failed = await form();
    expect(failed.findAll("select").length).toBe(1);
    expect(failed.text()).toContain(t("documents.page.edition.worksFailed"));
  });
});
