import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import ConflictPanel from "@/components/ConflictPanel.vue";
import type { Clash } from "@/rowConflict";
import { draftOf } from "@/rowDraft";

import { violations } from "./axe";
import { CV, form_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

const FIELDS = form_().statement;
const STORED = draftOf(FIELDS, {
  verbatim: "Ihr Satz.",
  statement_kind: CV + "kind_learningOutcome",
  addressees: [CV + "addr_learner", CV + "addr_educator"],
  levelText: "Stufe 2",
});
const CLASHES: Clash[] = [
  { key: "verbatim", yours: "Mein Satz.", stored: "Ihr Satz." },
  { key: "addressees", yours: [], stored: [CV + "addr_learner", CV + "addr_educator"] },
];

function panel(clashes: Clash[] = CLASHES, taken: string[] = ["levelText"]): VueWrapper {
  shown = mount(ConflictPanel, { props: { fields: FIELDS, clashes, taken, stored: STORED }, attachTo: document.body });
  return shown;
}

describe("a change laid beside the row as another stored it", () => {
  it("puts each field both changed before the user: both values in words, an empty one as such", async () => {
    const wrapper = panel();

    expect(wrapper.get("h3").text()).toBe("Inzwischen gespeichert");
    expect(wrapper.get(".conflict-panel__intro").text()).toContain("Entscheide bei jedem Feld unten, welcher Wert gilt");
    expect(wrapper.findAll(".conflict-panel__clash").map((clash) => clash.text())).toEqual([
      expect.stringMatching(/^Wortlaut\s*Dein Wert\s*Mein Satz\.\s*Gespeichert\s*Ihr Satz\./),
      expect.stringMatching(/^Adressaten\s*Dein Wert\s*leer\s*Gespeichert\s*Lernende, Lehrkräfte/),
    ]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("asks per field to keep the user's value or take the stored one, each button tied to its field", async () => {
    const wrapper = panel();
    const [keep, take] = wrapper.findAll(".conflict-panel__clash")[1]?.findAll("button") ?? [];

    expect([keep?.text(), take?.text()]).toEqual(["Meins behalten", "Gespeichertes nehmen"]);
    expect(document.getElementById(keep?.attributes("aria-describedby") ?? "")?.textContent).toBe("Adressaten");
    await keep?.trigger("click");
    await take?.trigger("click");

    expect(wrapper.emitted("keep")).toEqual([["addressees"]]);
    expect(wrapper.emitted("take")).toEqual([["addressees"]]);
  });

  it("takes the focus on to the next field to decide once one is decided, and to itself once none is left", async () => {
    const wrapper = panel();
    await wrapper.findAll("button")[0]?.trigger("click"); // keep mine: verbatim

    await wrapper.setProps({ clashes: CLASHES.slice(1) });
    await nextTick();
    expect(document.activeElement?.textContent?.trim()).toBe("Meins behalten");
    expect(document.activeElement?.getAttribute("aria-describedby")).toBe(
      wrapper.get(".conflict-panel__clash p").attributes("id"),
    );

    await wrapper.findAll("button")[1]?.trigger("click");
    await wrapper.setProps({ clashes: [] });
    await nextTick();
    expect(document.activeElement).toBe(wrapper.get("section").element);
  });

  it("names the fields taken in from the stored row, with their values", () => {
    const wrapper = panel();

    expect(wrapper.get(".conflict-panel__taken").text()).toMatch(/Übernommen.*Niveau im Wortlaut: Stufe 2/s);
  });

  it("says, with nothing to decide, that saving again lays the user's change onto the stored row", () => {
    const wrapper = panel([], ["levelText"]);

    expect(wrapper.get(".conflict-panel__intro").text()).toBe(
      "Jemand hat diese Zeile geändert, während du sie bearbeitet hast. Diese Änderungen sind übernommen; speichere erneut, um deine dazuzulegen.",
    );
    expect(wrapper.find(".conflict-panel__clash").exists()).toBe(false);
  });

  it("says, with nothing to decide and nothing taken in, that the change waits to be saved again", () => {
    const wrapper = panel([], []);

    expect(wrapper.get(".conflict-panel__intro").text()).toBe(
      "Jemand hat diese Zeile inzwischen gespeichert. Deine Änderungen sind noch nicht gespeichert; speichere erneut.",
    );
    expect(wrapper.find(".conflict-panel__taken").exists()).toBe(false);
  });

  it("takes the focus when asked, so that a screen reader reads where the change stands", () => {
    const wrapper = panel();

    (wrapper.vm as unknown as { focus: () => void }).focus();

    expect(document.activeElement).toBe(wrapper.get("section").element);
    expect(wrapper.get("section").attributes("aria-labelledby")).toBe(wrapper.get("h3").attributes("id"));
    // focused, it is read with what to do, not its name alone
    const intro = wrapper.get(".conflict-panel__intro").attributes("id");
    expect([Boolean(intro), wrapper.get("section").attributes("aria-describedby")]).toEqual([true, intro]);
  });
});
