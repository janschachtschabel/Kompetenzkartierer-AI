import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import type { CurriculumDocument, DocumentWork, Me } from "@/api";
import DocumentEdition from "@/components/DocumentEdition.vue";
import DocumentMetaForm from "@/components/DocumentMetaForm.vue";
import WorkForm from "@/components/WorkForm.vue";
import { t } from "@/i18n/de";
import { clearSession, setSession } from "@/session";

import { violations } from "./axe";
import { documentOf } from "./documentFixtures";

let shown: VueWrapper | null = null;

const KLP: DocumentWork = {
  id: "w1",
  title: "Kernlehrplan Physik",
  region: "DE-NW",
  short_title: "klp-physik",
  iri: "https://example.org/kk/work/de-nw/klp-physik",
};
const OWNER: Me = { id: "a1", name: "Eigentümerin", roles: ["nutzer"] };
const EDITOR: Me = { id: "a2", name: "Redakteurin", roles: ["redaktion"] };

async function edition(document: CurriculumDocument, me: Me = OWNER): Promise<VueWrapper> {
  setSession(me);
  shown = mount(DocumentEdition, { props: { document }, attachTo: globalThis.document.body });
  await flushPromises();
  return shown;
}

const facts = (wrapper: VueWrapper) =>
  Object.fromEntries(
    wrapper.findAll("dt").map((term) => [term.text(), (term.element.nextElementSibling as HTMLElement).textContent?.trim()]),
  );

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listDocuments").mockResolvedValue([]);
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  globalThis.document.body.innerHTML = "";
  clearSession();
});

describe("a document's work and edition", () => {
  it("say its issuer, edition, work, IRI and revision, what is not there said as such", async () => {
    const named = await edition(
      documentOf({ issuer: "MSB NRW", edition: "2019", work: KLP, iri: "https://example.org/kk/doc/x", revision: 2 }),
    );

    expect(named.get("h2").text()).toBe(t("documents.page.edition.heading"));
    expect(facts(named)).toEqual({
      [t("documents.page.edition.issuer")]: "MSB NRW",
      [t("documents.page.edition.edition")]: "2019",
      [t("documents.page.edition.workHeading")]: "Kernlehrplan Physik (Nordrhein-Westfalen, klp-physik)",
      [t("documents.page.edition.iri")]: "https://example.org/kk/doc/x",
      [t("documents.page.edition.revision")]: "2",
    });
    expect(await violations(named.html())).toEqual([]);
    named.unmount();

    const bare = await edition(documentOf());
    const none = t("documents.page.edition.none");
    expect(facts(bare)).toMatchObject({
      [t("documents.page.edition.issuer")]: none,
      [t("documents.page.edition.edition")]: none,
      [t("documents.page.edition.workHeading")]: none,
      [t("documents.page.edition.iri")]: t("documents.page.edition.noIri"),
    });
  });

  it("offer the owner its title, issuer and edition to change, the work being the editors'", async () => {
    const wrapper = await edition(documentOf({ own: true }));

    expect(wrapper.findComponent(DocumentMetaForm).exists()).toBe(true);
    expect(wrapper.findComponent(WorkForm).exists()).toBe(false);
  });

  it("offer an editor the work too, while the document has none and no IRI", async () => {
    const editing = await edition(documentOf({ own: false }), EDITOR);
    expect([editing.findComponent(DocumentMetaForm).exists(), editing.findComponent(WorkForm).exists()]).toEqual([
      true,
      true,
    ]);
    shown?.unmount();
    expect((await edition(documentOf({ own: false, work: KLP }), EDITOR)).findComponent(WorkForm).exists()).toBe(false);
    shown?.unmount();
    const copied = documentOf({ own: false, iri: "https://example.org/kk/doc/x", copy_of: "d0" });
    expect((await edition(copied, EDITOR)).findComponent(WorkForm).exists()).toBe(false);
  });

  it("offer nothing to change once the document is frozen", async () => {
    const wrapper = await edition(documentOf({ frozen_at: "2026-10-31T10:00:00Z", iri: "x", work: KLP }), EDITOR);

    expect(wrapper.find("form").exists()).toBe(false);
  });

  it("have the page read the document again for a change saved below", async () => {
    const wrapper = await edition(documentOf(), EDITOR);

    wrapper.findComponent(DocumentMetaForm).vm.$emit("changed");
    wrapper.findComponent(WorkForm).vm.$emit("changed");

    expect(wrapper.emitted("changed")).toHaveLength(2);
  });
});
