import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import { messages, t } from "@/i18n/de";
import { router } from "@/router";
import SourceDetailView from "@/views/SourceDetailView.vue";

import { conversion } from "./conversions";
import { deferred, detail } from "./registerEntries";

let shown: VueWrapper | null = null;

async function open(id = "s1"): Promise<VueWrapper> {
  shown = mount(SourceDetailView, { props: { id }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

/** The value a description list gives for `term`. */
function described(wrapper: VueWrapper, section: string, term: string): string {
  const terms = wrapper.get(`[aria-labelledby=${section}]`).findAll("dt");
  const found = terms.find((dt) => dt.text() === term);
  expect(found, `no ${term} in ${section}`).toBeDefined();
  return (found?.element.nextElementSibling?.textContent ?? "").trim();
}

beforeEach(() => {
  vi.restoreAllMocks();
  // an entry with a file asks for its conversion: none, unless a test says otherwise
  vi.spyOn(api, "getConversion").mockRejectedValue(new ApiError("server", 404, "no_conversion"));
  vi.spyOn(api, "listDocuments").mockResolvedValue([]);
});

afterEach(() => {
  shown?.unmount();
  shown = null;
});

describe("a register entry's page", () => {
  it("says it loads, then names the entry and what the register knows of it", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail());
    shown = mount(SourceDetailView, { props: { id: "s1" }, global: { plugins: [router] } });
    expect(shown.text()).toContain(t("states.loading"));
    await flushPromises();
    const wrapper = shown;

    expect(wrapper.get("h1").text()).toBe("Rheinland-Pfalz · Physik · Gymnasium");
    expect(described(wrapper, "source-facts", t("entryPage.facts.provenance"))).toBe(messages.sources.provenance["vergleichsdatensatz-v62.493"]);
    expect(described(wrapper, "source-facts", t("entryPage.facts.status"))).toBe(t("sources.status.reachable"));
    expect(described(wrapper, "source-facts", t("entryPage.facts.rights"))).toBe(t("sources.rights.unklar"));
    expect(described(wrapper, "source-facts", t("entryPage.facts.country"))).toBe("Rheinland-Pfalz");
    expect(described(wrapper, "source-facts", t("entryPage.facts.file"))).toBe(t("sources.register.noFile"));
    const address = wrapper.get<HTMLAnchorElement>("[aria-labelledby=source-facts] a");
    expect(address.attributes("href")).toBe("https://lehrplaene.bildung-rp.de/physik.pdf");
    // the app's own address goes to no foreign server
    expect(address.attributes("rel")).toBe("noreferrer");
  });

  it.each([
    ["DE", "Bund"],
    ["DE-TH", "Thüringen"],
    // a code the catalogue has no name for yet, as it came
    ["AT-9", "AT-9"],
  ])("names the land %s by its name", async (country, name) => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail({ country }));
    const wrapper = await open();

    expect(described(wrapper, "source-facts", t("entryPage.facts.country"))).toBe(name);
  });

  it("shows on what terms it may be used, and the evidence for it, where the register has them", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(
      detail({ rights_status: "offen_lizenziert", license: "CC BY 4.0", rights_evidence: "Lizenzhinweis auf der Portalseite" }),
    );
    const wrapper = await open();

    expect(described(wrapper, "source-facts", t("entryPage.facts.license"))).toBe("CC BY 4.0");
    expect(described(wrapper, "source-facts", t("entryPage.facts.rightsEvidence"))).toBe("Lizenzhinweis auf der Portalseite");
  });

  it("leaves out a licence and evidence the register does not have", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail());
    const wrapper = await open();

    const terms = wrapper.get("[aria-labelledby=source-facts]").findAll("dt").map((dt) => dt.text());
    expect(terms).not.toContain(t("entryPage.facts.license"));
    expect(terms).not.toContain(t("entryPage.facts.rightsEvidence"));
    expect(wrapper.find("#source-acquisitions").exists()).toBe(false);
  });

  it("shows how its file came: fetched, when, under which name, by which addresses in turn", async () => {
    const chain = ["https://lehrplaene.bildung-rp.de/physik", "https://lehrplaene.bildung-rp.de/dateien/physik.pdf"];
    vi.spyOn(api, "getSource").mockResolvedValue(
      detail({
        register_status: "acquired",
        file: { name: "physik.pdf", mime: "application/pdf", size: 8, sha256: "ab" },
        acquisitions: [{ method: "url", acquired_at: "2026-10-22T11:00:00Z", chain, received_name: "physik.pdf" }],
      }),
    );
    const wrapper = await open();

    const acquired = wrapper.get("[aria-labelledby=source-acquisitions]");
    expect(acquired.get("h2").text()).toBe(t("entryPage.acquisitions.heading"));
    expect(described(wrapper, "source-acquisitions", t("entryPage.acquisitions.method"))).toBe(t("entryPage.acquisitionMethod.url"));
    expect(described(wrapper, "source-acquisitions", t("entryPage.acquisitions.acquiredAt"))).toContain("22.10.2026");
    expect(described(wrapper, "source-acquisitions", t("entryPage.acquisitions.receivedName"))).toBe("physik.pdf");
    const addresses = acquired.findAll("ol li a");
    expect(addresses.map((link) => link.attributes("href"))).toEqual(chain);
    expect(addresses.every((link) => link.attributes("rel") === "noreferrer")).toBe(true);
  });

  it("shows the conversion of its file, and none where it has no file yet", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(
      detail({ file: { name: "physik.pdf", mime: "application/pdf", size: 8, sha256: "ab" } }),
    );
    const wrapper = await open();

    expect(wrapper.get("#source-conversion").text()).toBe(t("conversions.heading"));
    expect(wrapper.get("[aria-labelledby=source-conversion]").text()).toContain(t("conversions.start"));
    expect(api.getConversion).toHaveBeenCalledWith("s1");

    vi.mocked(api.getConversion).mockClear();
    vi.mocked(api.getSource).mockResolvedValue(detail({ id: "s2" }));
    await wrapper.setProps({ id: "s2" });
    await flushPromises();
    expect(wrapper.find("#source-conversion").exists()).toBe(false);
    expect(api.getConversion).not.toHaveBeenCalled();
  });

  it("lists the documents of a PDF's conversion, and offers its extraction for the entry's Land", async () => {
    const pdf = { name: "physik.pdf", mime: "application/pdf", size: 8, sha256: "ab" };
    vi.spyOn(api, "getSource").mockResolvedValue(detail({ country: "DE-BY", file: pdf }));
    vi.mocked(api.getConversion).mockResolvedValue(conversion());
    const wrapper = await open();

    expect(wrapper.find("#source-documents").exists()).toBe(true);
    expect(api.listDocuments).toHaveBeenCalledWith("s1");
    expect(wrapper.find<HTMLInputElement>("input[value=DE-BY]").element.checked).toBe(true);
  });

  it("has no documents' section for a file that is no PDF: nothing is made of it", async () => {
    const docx = { name: "physik.docx", mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", size: 8, sha256: "ab" };
    vi.spyOn(api, "getSource").mockResolvedValue(detail({ file: docx }));

    const wrapper = await open();

    expect(wrapper.find("#source-documents").exists()).toBe(false);
    expect(api.listDocuments).not.toHaveBeenCalled();
  });

  it("says an upload came as one, with no addresses to show", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(
      detail({
        provenance: "upload",
        seed: null,
        url: null,
        acquisitions: [{ method: "upload", acquired_at: "2026-10-22T11:00:00Z", chain: [], received_name: "plan.pdf" }],
      }),
    );
    const wrapper = await open();

    expect(described(wrapper, "source-acquisitions", t("entryPage.acquisitions.method"))).toBe(t("entryPage.acquisitionMethod.upload"));
    expect(wrapper.find("[aria-labelledby=source-acquisitions] ol").exists()).toBe(false);
  });

  it("names the entry in the browser's title once it is known (WCAG 2.4.2)", async () => {
    api.setToken("kka_token");
    try {
      // as in the app: the navigation is done before the page asks for its entry
      await router.push({ name: "source", params: { id: "s1" } });
      expect(document.title).toBe(`${t("app.titles.source")} · ${t("app.title")}`);
      vi.spyOn(api, "getSource").mockResolvedValue(detail());

      await open();

      expect(document.title).toBe(`Rheinland-Pfalz · Physik · Gymnasium · ${t("app.title")}`);
    } finally {
      api.clearToken();
      await router.push("/");
    }
  });

  it("leaves the title to the page the reader went on to, when its answer comes after", async () => {
    const late = deferred<api.SourceDetail>();
    vi.spyOn(api, "getSource").mockImplementation(() => late.promise);
    const wrapper = await open();
    wrapper.unmount();
    shown = null;
    document.title = "Nächste Seite";

    late.resolve(detail());
    await flushPromises();

    expect(document.title).toBe("Nächste Seite");
  });

  it("shows what the seed said of the curriculum", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail());
    const wrapper = await open();

    expect(wrapper.get("#source-seed").text()).toBe(t("entryPage.seed.heading"));
    expect(described(wrapper, "source-seed", t("entryPage.seed.dataset"))).toBe(messages.sources.provenance["vergleichsdatensatz-v62.493"]);
    expect(described(wrapper, "source-seed", t("entryPage.seed.schoolForm"))).toBe("Gymnasium");
    expect(described(wrapper, "source-seed", t("entryPage.seed.stage"))).toBe("Sekundarstufe I");
    expect(described(wrapper, "source-seed", t("entryPage.seed.subject"))).toBe("Physik");
    expect(described(wrapper, "source-seed", t("entryPage.seed.grades"))).toBe(t("entryPage.seed.gradeRange", { from: 7, to: 10 }));
    expect(described(wrapper, "source-seed", t("entryPage.seed.binding"))).toBe("verbindlich");
    expect(wrapper.get("[aria-labelledby=source-seed] a").attributes("href")).toContain("web.archive.org");
  });

  it("says where the land's research found its row, and a single grade as one", async () => {
    const research = detail().seed;
    vi.spyOn(api, "getSource").mockResolvedValue(
      detail({ seed: research && { ...research, dataset: "laenderrecherche", evidence: "S", grade_to: 7 } }),
    );
    const wrapper = await open();

    expect(described(wrapper, "source-seed", t("entryPage.seed.evidence"))).toBe(t("entryPage.evidence.S"));
    expect(described(wrapper, "source-seed", t("entryPage.seed.grades"))).toBe("7");
  });

  it("shows what the check found at the address", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail());
    const wrapper = await open();

    expect(described(wrapper, "source-check", t("entryPage.check.outcome"))).toBe(t("entryPage.outcome.reachable"));
    expect(described(wrapper, "source-check", t("entryPage.check.statusCode"))).toBe("200");
    expect(described(wrapper, "source-check", t("entryPage.check.kind"))).toBe(t("entryPage.kind.pdf"));
    expect(described(wrapper, "source-check", t("entryPage.check.size"))).toBe("3,2 MB");
    expect(described(wrapper, "source-check", t("entryPage.check.checkedAt"))).toContain("22.10.2026");
  });

  it("says when the address was not checked yet", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail({ check: null }));
    const wrapper = await open();

    expect(wrapper.get("[aria-labelledby=source-check]").text()).toContain(t("entryPage.check.none"));
    expect(wrapper.find("[aria-labelledby=source-check] dl").exists()).toBe(false);
  });

  it("shows the access notes of its land, school form and subject", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail());
    const wrapper = await open();

    const notes = wrapper.findAll("[aria-labelledby=source-notes] li.note");
    expect(notes).toHaveLength(1);
    expect(notes[0].text()).toContain("Das Landesportal sperrt automatische Abrufe");
    expect(notes[0].text()).toContain("Sperre 403");
    expect(notes[0].get("a").attributes("rel")).toBe("noreferrer");
  });

  it("shows a note that is its address alone once, as the link", async () => {
    const address = "https://web.archive.org/web/2024/https://lehrplaene.bildung-rp.de/physik.pdf";
    const note: api.AccessNote = { categories: ["Wayback-Archiv"], text: address, url: address };
    vi.spyOn(api, "getSource").mockResolvedValue(detail({ access_notes: [note] }));
    const wrapper = await open();

    const shown = wrapper.get("[aria-labelledby=source-notes] li.note");
    expect(shown.text().split(address)).toHaveLength(2);
    expect(shown.get("a").attributes("href")).toBe(address);
  });

  it("says when no access note concerns it", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail({ access_notes: [] }));
    const wrapper = await open();

    expect(wrapper.get("[aria-labelledby=source-notes]").text()).toContain(t("entryPage.notes.none"));
  });

  it("leaves out what only a seed has for an entry of an account", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(
      detail({ provenance: "upload", seed: null, access_notes: [], check: null, url: null, mine: true }),
    );
    const wrapper = await open();

    expect(wrapper.find("#source-seed").exists()).toBe(false);
    expect(wrapper.find("#source-notes").exists()).toBe(false);
    expect(wrapper.find("#source-check").exists()).toBe(false);
  });

  it("shows an address that is no web address as text, not as a link", async () => {
    vi.spyOn(api, "getSource").mockResolvedValue(detail({ url: "javascript:alert(1)" }));
    const wrapper = await open();

    expect(wrapper.find("[aria-labelledby=source-facts] a").exists()).toBe(false);
    expect(described(wrapper, "source-facts", t("entryPage.facts.address"))).toBe("javascript:alert(1)");
  });

  it("says an entry it cannot see is not there, and leads back to the register", async () => {
    vi.spyOn(api, "getSource").mockRejectedValue(new ApiError("server", 404, "not_found"));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("entryPage.notFoundTitle"));
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
    expect(wrapper.get("a[href='/quellen']").text()).toBe(t("entryPage.back"));
  });

  it("leads back to the register as it was filtered, where the reader came from it", async () => {
    api.setToken("kka_token");
    try {
      await router.push({ name: "sources", query: { kandidaten: "1", stand: "unreachable" } });
      await router.push({ name: "source", params: { id: "s1" } });
      vi.spyOn(api, "getSource").mockResolvedValue(detail());
      const wrapper = await open();

      expect(wrapper.get(".source__back a").attributes("href")).toBe("/quellen?kandidaten=1&stand=unreachable");
      // arrived from elsewhere - a bookmark, another page: the register itself
      shown?.unmount();
      await router.push("/");
      await router.push({ name: "source", params: { id: "s1" } });
      expect((await open()).get(".source__back a").attributes("href")).toBe("/quellen");
    } finally {
      api.clearToken();
      await router.push("/");
    }
  });

  it("says an id that is no entry's at all is not there, without a retry that could not help", async () => {
    // the server checks the id's form first: no UUID is 422, not 404
    vi.spyOn(api, "getSource").mockRejectedValue(new ApiError("server", 422, "validation_failed"));
    const wrapper = await open("kein-eintrag");

    expect(wrapper.text()).toContain(t("entryPage.notFoundTitle"));
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
    expect(wrapper.find("button").exists()).toBe(false);
  });

  it("shows the entry it was moved on to, whichever answer comes last", async () => {
    const older = deferred<api.SourceDetail>();
    const newer = deferred<api.SourceDetail>();
    vi.spyOn(api, "getSource").mockImplementation((id) => (id === "s1" ? older.promise : newer.promise));
    const wrapper = await open("s1");

    await wrapper.setProps({ id: "s2" });
    newer.resolve(detail({ id: "s2", title: "Zweiter Eintrag" }));
    await flushPromises();
    older.resolve(detail({ id: "s1", title: "Erster Eintrag" }));
    await flushPromises();

    expect(wrapper.get("h1").text()).toBe("Zweiter Eintrag");
  });

  it("shows no longer the entry it was moved on from while the next one loads", async () => {
    const next = deferred<api.SourceDetail>();
    vi.spyOn(api, "getSource").mockResolvedValueOnce(detail({ title: "Erster Eintrag" })).mockImplementation(() => next.promise);
    const wrapper = await open("s1");

    await wrapper.setProps({ id: "s2" });

    expect(wrapper.get("h1").text()).toBe(t("entryPage.heading"));
    expect(wrapper.text()).toContain(t("states.loading"));
    expect(wrapper.text()).not.toContain("Erster Eintrag");
  });

  it("says when the entry did not load, and loads it again on request", async () => {
    const asked = vi
      .spyOn(api, "getSource")
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue(detail());
    const wrapper = await open();
    expect(wrapper.get("[role=alert]").text()).toContain(t("entryPage.loadFailed"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(asked).toHaveBeenCalledTimes(2);
    expect(wrapper.get("h1").text()).toBe("Rheinland-Pfalz · Physik · Gymnasium");
  });
});
