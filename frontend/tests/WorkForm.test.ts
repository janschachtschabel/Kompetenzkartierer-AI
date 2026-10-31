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

// a field's error, inside its field and named by it, the keyboard on the field
function errorAt(wrapper: VueWrapper, input: { attributes: (name: string) => string | undefined; element: Element }) {
  const error = wrapper.get(`#${input.attributes("id")}-error`);
  expect(input.attributes("aria-invalid")).toBe("true");
  expect(input.attributes("aria-describedby")).toContain(error.attributes("id"));
  expect(globalThis.document.activeElement).toBe(input.element);
  expect(wrapper.find("[role=alert]").exists()).toBe(false);
  return error.text();
}

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
    expect(wrapper.emitted("saved")).toHaveLength(1); // said where the form goes with it (DocumentEdition)
  });

  it("asks for a work to choose before it sends", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(errorAt(wrapper, control(wrapper, t("documents.page.edition.workChosen")))).toContain(
      t("documents.page.edition.workChoose"),
    );
  });

  it("makes a new work of its title, its land and its short title", async () => {
    const sent = vi.spyOn(api, "setWork").mockResolvedValue(documentOf({ work: KLP }));
    const wrapper = await form();

    await fillNew(wrapper);
    await save(wrapper);
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("d1", { title: "Kernlehrplan Physik", region: "DE-NW", short_title: "klp-physik" });
    expect(wrapper.emitted("saved")).toHaveLength(1);
  });

  it("says a short title the IRI cannot take at its field, sending nothing", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await fillNew(wrapper, "KLP Physik");
    await save(wrapper);

    const short = control(wrapper, t("documents.page.edition.workShortTitle"));
    expect(sent).not.toHaveBeenCalled();
    expect(errorAt(wrapper, short)).toContain(t("documents.page.edition.workShortTitleBad"));
    expect(short.attributes("aria-describedby")).toContain(`${short.attributes("id")}-hint`);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("says a short title's problem where the keyboard rests on that field, Enter pressed there", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await fillNew(wrapper, "KLP Physik");
    const short = control(wrapper, t("documents.page.edition.workShortTitle"));
    (short.element as HTMLElement).focus();
    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(globalThis.document.activeElement).toBe(short.element);
    expect(short.attributes("aria-invalid")).toBe("true");
    expect(wrapper.get("[role=status]").text()).toBe(
      t("documents.page.edition.fieldProblem", {
        field: t("documents.page.edition.workShortTitle"),
        problem: t("documents.page.edition.workShortTitleBad"),
      }),
    );
  });

  it("sets nothing more once the work is set: the form goes with it", async () => {
    const sent = vi.spyOn(api, "setWork").mockResolvedValue(documentOf({ work: KLP }));
    const wrapper = await form();

    await control<HTMLSelectElement>(wrapper, t("documents.page.edition.workChosen")).setValue("w1");
    await save(wrapper);
    await flushPromises();
    await save(wrapper);
    await flushPromises();

    expect(sent).toHaveBeenCalledTimes(1);
    expect(wrapper.get("button[type=submit]").attributes("aria-disabled")).toBe("true");
  });

  it("asks for the new work's title before it sends", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await fillNew(wrapper);
    await control(wrapper, t("documents.page.edition.workTitle")).setValue("  ");
    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(errorAt(wrapper, control(wrapper, t("documents.page.edition.workTitle")))).toContain(
      t("documents.tree.problems.required"),
    );
  });

  it("asks for the new work's land before it sends", async () => {
    const sent = vi.spyOn(api, "setWork");
    const wrapper = await form();

    await fillNew(wrapper);
    await control<HTMLSelectElement>(wrapper, t("documents.page.edition.workRegion")).setValue("");
    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(errorAt(wrapper, control(wrapper, t("documents.page.edition.workRegion")))).toContain(
      t("documents.page.edition.workRegionChoose"),
    );
  });

  it("says the server's problem with a field at the field", async () => {
    vi.spyOn(api, "setWork").mockRejectedValue(
      new ApiError("server", 422, "invalid_field", "Bad.", { field: "region", problem: "not_offered" }),
    );
    const wrapper = await form();

    await fillNew(wrapper);
    await save(wrapper);
    await flushPromises();

    expect(errorAt(wrapper, control(wrapper, t("documents.page.edition.workRegion")))).toContain(
      t("documents.tree.problems.not_offered"),
    );
  });

  it("says a problem of a field the form does not hold above the button", async () => {
    vi.spyOn(api, "setWork").mockRejectedValue(
      new ApiError("server", 422, "invalid_field", "Bad.", { field: "colour", problem: "not_offered" }),
    );
    const wrapper = await form();

    await fillNew(wrapper);
    await save(wrapper);
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.tree.problems.not_offered"));
    expect(wrapper.find("[aria-invalid]").exists()).toBe(false);
  });

  it("says a refusal and another failure above the button, reading nothing again", async () => {
    vi.spyOn(api, "setWork")
      .mockRejectedValueOnce(new ApiError("forbidden", 403, "not_editor"))
      .mockRejectedValueOnce(new ApiError("network", 0));
    const wrapper = await form();

    await control<HTMLSelectElement>(wrapper, t("documents.page.edition.workChosen")).setValue("w1");
    await save(wrapper);
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("not_editor"));
    await save(wrapper);
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.page.edition.workFailed"));
    expect(wrapper.emitted("changed")).toBeUndefined();
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

  it("shows only that the works are read until they are: no field to type in goes from under the user", async () => {
    let read: (documents: ReturnType<typeof documentOf>[]) => void = () => undefined;
    vi.mocked(api.listDocuments).mockReturnValueOnce(new Promise((resolve) => (read = resolve)));
    shown = mount(WorkForm, { props: { document: documentOf() }, attachTo: document.body });
    await flushPromises();

    expect(shown.text()).toContain(t("documents.page.edition.worksLoading"));
    expect(shown.findAll("input, select, button")).toHaveLength(0);
    read(OTHERS);
    await flushPromises();

    expect(control<HTMLSelectElement>(shown, t("documents.page.edition.workChosen")).element.tagName).toBe("SELECT");
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
