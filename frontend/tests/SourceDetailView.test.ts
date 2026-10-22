import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import { messages, t } from "@/i18n/de";
import { router } from "@/router";
import SourceDetailView from "@/views/SourceDetailView.vue";

import { detail } from "./registerEntries";

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
    expect(described(wrapper, "source-facts", t("entryPage.facts.country"))).toBe("DE-RP");
    expect(described(wrapper, "source-facts", t("entryPage.facts.file"))).toBe(t("sources.register.noFile"));
    const address = wrapper.get<HTMLAnchorElement>("[aria-labelledby=source-facts] a");
    expect(address.attributes("href")).toBe("https://lehrplaene.bildung-rp.de/physik.pdf");
    // the app's own address goes to no foreign server
    expect(address.attributes("rel")).toBe("noreferrer");
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
    expect(notes[0].text()).not.toContain("laender_meta");
  });

  it("shows a note that is its address alone once, as the link", async () => {
    const address = "https://web.archive.org/web/2024/https://lehrplaene.bildung-rp.de/physik.pdf";
    const note = { categories: ["Wayback-Archiv"], field: null, text: address, url: address, origin: null };
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
