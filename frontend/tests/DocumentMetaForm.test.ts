import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument } from "@/api";
import DocumentMetaForm from "@/components/DocumentMetaForm.vue";
import { t } from "@/i18n/de";
import { refusalText } from "@/refusals";

import { violations } from "./axe";
import { documentOf } from "./documentFixtures";

let shown: VueWrapper | null = null;

const DOCUMENT = documentOf({ title: "Kernlehrplan Physik", issuer: "MSB NRW", edition: null });

function form(document: CurriculumDocument = DOCUMENT): VueWrapper {
  shown = mount(DocumentMetaForm, { props: { document }, attachTo: document_body() });
  return shown;
}

// the page's body, named apart from the prop `document`
function document_body(): HTMLElement {
  return globalThis.document.body;
}

const field = (wrapper: VueWrapper, label: string) => {
  const found = wrapper.findAll("label").find((one) => one.text() === label);
  if (!found) throw new Error(label);
  return wrapper.get<HTMLInputElement>(`#${found.attributes("for")}`);
};
const issuer = (wrapper: VueWrapper) => field(wrapper, t("documents.page.edition.issuer"));
const edition = (wrapper: VueWrapper) => field(wrapper, t("documents.page.edition.edition"));
const title = (wrapper: VueWrapper) => field(wrapper, t("documents.page.edition.title"));
const save = (wrapper: VueWrapper) => wrapper.get("form").trigger("submit");
const status = (wrapper: VueWrapper) => wrapper.get("[role=status]").text();

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  globalThis.document.body.innerHTML = "";
});

describe("the form of a document's title, issuer and edition", () => {
  it("holds the document's values, each field named and described", async () => {
    const wrapper = form();

    expect([title(wrapper).element.value, issuer(wrapper).element.value, edition(wrapper).element.value]).toEqual([
      "Kernlehrplan Physik",
      "MSB NRW",
      "",
    ]);
    expect(issuer(wrapper).attributes("aria-describedby")).toBeTruthy();
    expect(wrapper.get("button[type=submit]").text()).toBe(t("documents.page.edition.save"));
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("sends only what changed, says it is saved and has the document read again", async () => {
    const sent = vi.spyOn(api, "editDocument").mockResolvedValue({ ...DOCUMENT, edition: "2019" });
    const wrapper = form();

    await edition(wrapper).setValue(" 2019 ");
    await save(wrapper);
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("d1", { edition: "2019" });
    expect(status(wrapper)).toBe(t("documents.page.edition.saved"));
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("asks nothing where nothing changed, and says so", async () => {
    const sent = vi.spyOn(api, "editDocument");
    const wrapper = form();

    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(status(wrapper)).toBe(t("documents.page.edition.unchanged"));
  });

  it("says a field's problem at the field and above the button", async () => {
    vi.spyOn(api, "editDocument").mockRejectedValue(
      new ApiError("server", 422, "invalid_field", "Bad.", { field: "issuer", problem: "too_long" }),
    );
    const wrapper = form();

    await issuer(wrapper).setValue("Ministerium");
    await save(wrapper);
    await flushPromises();

    const alert = wrapper.get("[role=alert]");
    expect(alert.text()).toContain(t("documents.tree.problems.too_long"));
    expect(issuer(wrapper).attributes("aria-invalid")).toBe("true");
    expect(issuer(wrapper).attributes("aria-describedby")).toContain(alert.attributes("id"));
    expect(title(wrapper).attributes("aria-invalid")).toBeUndefined();
    expect(issuer(wrapper).element.value).toBe("Ministerium"); // the entry kept
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("says a document closed to the change meanwhile and has it read again", async () => {
    vi.spyOn(api, "editDocument").mockRejectedValue(new ApiError("server", 409, "frozen"));
    const wrapper = form();

    await issuer(wrapper).setValue("Ministerium");
    await save(wrapper);
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("frozen"));
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("says another refusal by its code, reading nothing again", async () => {
    vi.spyOn(api, "editDocument").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const wrapper = form();

    await issuer(wrapper).setValue("Ministerium");
    await save(wrapper);
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("job_open"));
    expect(wrapper.emitted("changed")).toBeUndefined();
  });

  it("sends nothing more while it saves", async () => {
    const sent = vi.spyOn(api, "editDocument").mockReturnValue(new Promise(() => {}));
    const wrapper = form();

    await issuer(wrapper).setValue("Ministerium");
    await save(wrapper);
    await save(wrapper);

    expect(sent).toHaveBeenCalledTimes(1);
    expect(wrapper.get("button[type=submit]").attributes("aria-disabled")).toBe("true");
  });

  it("holds the issuer and the edition as they are once the document has its IRI", () => {
    const named = documentOf({ ...DOCUMENT, iri: "https://example.org/kk/doc/de-nw/msb-nrw/klp/2019", edition: "2019" });
    const wrapper = form(named);

    expect([issuer(wrapper).attributes("readonly"), edition(wrapper).attributes("readonly")]).toEqual(["", ""]);
    expect(title(wrapper).attributes("readonly")).toBeUndefined();
    expect(wrapper.text()).toContain(t("documents.page.edition.named"));
  });

  it("takes values read meanwhile into the fields left as they were, and holds nothing stale after a save", async () => {
    const bare = documentOf({ title: "Alt", issuer: null, edition: null });
    const sent = vi.spyOn(api, "editDocument").mockResolvedValue({ ...bare, title: "Neu", issuer: "MSB", edition: "2019" });
    const wrapper = form(bare);

    await title(wrapper).setValue("Neu");
    await wrapper.setProps({ document: { ...bare, issuer: "MSB", edition: "2019" } }); // the extraction filled them
    expect([title(wrapper).element.value, issuer(wrapper).element.value, edition(wrapper).element.value]).toEqual([
      "Neu",
      "MSB",
      "2019",
    ]);
    await save(wrapper);
    await flushPromises();
    await save(wrapper);

    expect(sent).toHaveBeenCalledTimes(1);
    expect(sent).toHaveBeenCalledWith("d1", { title: "Neu" });
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.page.edition.unchanged"));
  });

  it("keeps an entry not yet saved where the document is read again, and takes the saved values after a save", async () => {
    vi.spyOn(api, "editDocument").mockResolvedValue({ ...DOCUMENT, issuer: "Ministerium" });
    const wrapper = form();

    await edition(wrapper).setValue("2019");
    await wrapper.setProps({ document: { ...DOCUMENT } }); // read again, unchanged
    expect(edition(wrapper).element.value).toBe("2019");

    await edition(wrapper).setValue("");
    await issuer(wrapper).setValue("Ministerium");
    await save(wrapper);
    await flushPromises();
    await wrapper.setProps({ document: { ...DOCUMENT, issuer: "Ministerium", edition: "2020" } });

    expect([issuer(wrapper).element.value, edition(wrapper).element.value]).toEqual(["Ministerium", "2020"]);
  });
});
