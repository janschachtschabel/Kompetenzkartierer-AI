import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type Me } from "@/api";
import DocumentFreeze from "@/components/DocumentFreeze.vue";
import { t } from "@/i18n/de";
import { refusalText } from "@/refusals";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";

import { violations } from "./axe";
import { documentOf } from "./documentFixtures";

let shown: VueWrapper | null = null;

const EDITOR: Me = { id: "a2", name: "Redakteurin", roles: ["redaktion"] };
const DOCUMENT = documentOf({ title: "Kernlehrplan Physik", revision: 2 });
const FROZEN = { ...DOCUMENT, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" };

function section(document: CurriculumDocument = DOCUMENT, me: Me = EDITOR): VueWrapper {
  setSession(me);
  shown = mount(DocumentFreeze, { props: { document }, global: { plugins: [router] }, attachTo: globalThis.document.body });
  return shown;
}

const freezeButton = (wrapper: VueWrapper) => wrapper.get("[data-test=freeze]");
const dialog = (wrapper: VueWrapper) => wrapper.get("[role=dialog]");

async function confirmFreeze(wrapper: VueWrapper): Promise<void> {
  await freezeButton(wrapper).trigger("click");
  await flushPromises();
  await wrapper.get("[data-test=confirm]").trigger("click");
  await flushPromises();
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  globalThis.document.body.innerHTML = "";
  clearSession();
});

describe("freezing a document", () => {
  it("is offered to an editor while the document is open, with what it does", async () => {
    const wrapper = section();

    expect(wrapper.get("h2").text()).toBe(t("documents.page.freeze.heading"));
    expect(wrapper.text()).toContain(t("documents.page.freeze.intro"));
    expect(freezeButton(wrapper).text()).toBe(t("documents.page.freeze.button"));
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("is offered to no one else, and not once frozen", () => {
    expect(section(DOCUMENT, { ...EDITOR, roles: ["nutzer"] }).html()).toBe("<!--v-if-->");
    shown?.unmount();
    expect(section(FROZEN).html()).toBe("<!--v-if-->");
  });

  it("asks first, naming the document and what follows, the keyboard on Cancel", async () => {
    const sent = vi.spyOn(api, "freezeDocument");
    const wrapper = section();

    await freezeButton(wrapper).trigger("click");
    await flushPromises();

    expect(dialog(wrapper).text()).toContain(t("documents.page.freeze.title"));
    expect(dialog(wrapper).text()).toContain(t("documents.page.freeze.message", { title: "Kernlehrplan Physik", revision: 2 }));
    const list = dialog(wrapper).get("ul");
    expect(list.findAll("li")).toHaveLength(4);
    expect(dialog(wrapper).attributes("aria-describedby")).toContain(list.attributes("id"));
    expect(globalThis.document.activeElement).toBe(wrapper.get("[data-test=cancel]").element);
    expect(await violations(wrapper.html())).toEqual([]);

    await wrapper.get("[data-test=cancel]").trigger("click");
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
    expect(sent).not.toHaveBeenCalled();
  });

  it("freezes on yes and hands the frozen document to the page", async () => {
    const sent = vi.spyOn(api, "freezeDocument").mockResolvedValue(FROZEN);
    const wrapper = section();

    await confirmFreeze(wrapper);

    expect(sent).toHaveBeenCalledWith("d1", false);
    expect(wrapper.emitted("frozen")).toEqual([[FROZEN]]);
  });

  it("asks again where the findings name violations, by their count, and takes them on yes", async () => {
    const sent = vi
      .spyOn(api, "freezeDocument")
      .mockRejectedValueOnce(new ApiError("server", 409, "has_violations", "Violations.", { violations: 3 }))
      .mockResolvedValue(FROZEN);
    const wrapper = section();

    await confirmFreeze(wrapper);
    expect(dialog(wrapper).text()).toContain(t("documents.page.freeze.violationsTitle"));
    expect(dialog(wrapper).text()).toContain(t("documents.page.freeze.violationsMessage", { count: 3 }));
    await wrapper.get("[data-test=confirm]").trigger("click");
    await flushPromises();

    expect(sent).toHaveBeenLastCalledWith("d1", true);
    expect(wrapper.emitted("frozen")).toEqual([[FROZEN]]);
  });

  it("takes no violations where the second question is answered no", async () => {
    const sent = vi
      .spyOn(api, "freezeDocument")
      .mockRejectedValue(new ApiError("server", 409, "has_violations", "Violations.", { violations: 1 }));
    const wrapper = section();

    await confirmFreeze(wrapper);
    await wrapper.get("[data-test=cancel]").trigger("click");
    await flushPromises();

    expect(sent).toHaveBeenCalledTimes(1);
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
  });

  it("names what is missing for the IRI, item by item", async () => {
    vi.spyOn(api, "freezeDocument").mockRejectedValue(
      new ApiError("server", 409, "incomplete", "Incomplete.", { missing: ["work", "issuer"] }),
    );
    const wrapper = section();

    await confirmFreeze(wrapper);

    const missing = [t("documents.page.freeze.missing.work"), t("documents.page.freeze.missing.issuer")].join(", ");
    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.page.freeze.incomplete", { missing }));
  });

  it("says a check owed, with the way to the tree where it is checked", async () => {
    vi.spyOn(api, "freezeDocument").mockRejectedValue(new ApiError("server", 409, "check_owed", "Owed.", { unchecked: 0 }));
    const wrapper = section();

    await confirmFreeze(wrapper);

    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("check_owed"));
    expect(wrapper.get("[data-test=freeze-tree]").attributes("href")).toBe("/dokumente/d1/baum");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("says a document closed meanwhile and has it read again; another refusal it only says", async () => {
    vi.spyOn(api, "freezeDocument")
      .mockRejectedValueOnce(new ApiError("server", 409, "job_open"))
      .mockRejectedValueOnce(new ApiError("server", 409, "no_iri_base"));
    const wrapper = section();

    await confirmFreeze(wrapper);
    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("job_open"));
    expect(wrapper.emitted("changed")).toHaveLength(1);
    await confirmFreeze(wrapper);

    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("no_iri_base"));
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("asks nothing more while it freezes", async () => {
    const sent = vi.spyOn(api, "freezeDocument").mockReturnValue(new Promise(() => {}));
    const wrapper = section();

    await confirmFreeze(wrapper);
    await freezeButton(wrapper).trigger("click");
    await flushPromises();

    expect(freezeButton(wrapper).attributes("aria-disabled")).toBe("true");
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
    expect(sent).toHaveBeenCalledTimes(1);
  });
});
