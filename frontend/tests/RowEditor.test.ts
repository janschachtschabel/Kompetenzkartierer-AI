import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import * as api from "@/api";
import { ApiError, type TreeAnchor, type TreeStatement } from "@/api";
import RowEditor from "@/components/RowEditor.vue";
import { rowsOf, type Row } from "@/documentTree";
import { t } from "@/i18n/de";

import { violations } from "./axe";
import { CV, form_, node_, statement_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

const SAID = statement_("s1", {
  revision: 3,
  fields: { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome", addressees: [CV + "addr_learner"] },
});
const ROW = rowsOf([node_("a", { statements: [SAID] })]).get("statement:s1") as Row;

function stored(fields: Record<string, unknown>, revision: number): TreeStatement {
  return { ...SAID, revision, fields: { ...SAID.fields, ...fields } as TreeStatement["fields"] };
}

// a change saved, as the panel hears it: by a function the editor is given
let saved = vi.fn();

function editor(): VueWrapper {
  saved = vi.fn();
  shown = mount(RowEditor, { props: { row: ROW, form: form_(), onSaved: saved }, attachTo: document.body });
  return shown;
}

async function write(wrapper: VueWrapper, text: string): Promise<void> {
  await wrapper.get("textarea, input").setValue(text);
}

async function save(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("form").trigger("submit");
  await flushPromises();
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("a row's editor", () => {
  it("saves a change and says so, and says when a draft is open", async () => {
    const sent = vi.spyOn(api, "editStatement").mockResolvedValue(stored({ verbatim: "Sie messen genau." }, 4));
    const wrapper = editor();
    expect(wrapper.emitted("dirty")).toEqual([[false]]);

    await write(wrapper, "Sie messen genau.");
    expect(wrapper.emitted("dirty")?.at(-1)).toEqual([true]);
    await save(wrapper);

    expect(sent).toHaveBeenCalledWith("s1", 3, { verbatim: "Sie messen genau." });
    expect(wrapper.get("[role=status]").text()).toBe("Gespeichert.");
    expect(saved).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted("dirty")?.at(-1)).toEqual([false]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("says that nothing changed, asking nothing", async () => {
    const sent = vi.spyOn(api, "editStatement");
    const wrapper = editor();

    await save(wrapper);

    expect(sent).not.toHaveBeenCalled();
    expect(wrapper.get("[role=status]").text()).toBe("Nichts geändert, nichts zu speichern.");
  });

  it("lays a change that met another beside it, takes the keyboard there, and saves the choice", async () => {
    const sent = vi
      .spyOn(api, "editStatement")
      .mockRejectedValueOnce(
        new ApiError("server", 409, "stale_revision", "Changed.", { current: stored({ verbatim: "Ihr Satz." }, 5) }),
      )
      .mockResolvedValueOnce(stored({ verbatim: "Mein Satz." }, 6));
    const wrapper = editor();
    await write(wrapper, "Mein Satz.");
    await save(wrapper);

    expect(document.activeElement).toBe(wrapper.get(".conflict-panel").element);
    expect(await violations(wrapper.html())).toEqual([]);
    (wrapper.get("textarea").element as HTMLElement).focus(); // saving again from the form
    await save(wrapper); // undecided: not saved, said, the keyboard back to the choice
    expect(sent).toHaveBeenCalledTimes(1);
    expect(wrapper.get("[role=status]").text()).toBe("Entscheide zuerst bei jedem Feld oben, welcher Wert gilt.");
    expect(document.activeElement).toBe(wrapper.get(".conflict-panel").element);
    await wrapper.findAll(".conflict-panel button")[0]?.trigger("click"); // keep mine
    await save(wrapper);

    expect(sent).toHaveBeenLastCalledWith("s1", 5, { verbatim: "Mein Satz." });
    expect(wrapper.find(".conflict-panel").exists()).toBe(false);
  });

  it("says each time a click finds nothing to save", async () => {
    const wrapper = editor();

    await save(wrapper);
    const first = wrapper.get("[role=status]").text();
    await save(wrapper);

    expect(first).toBe("Nichts geändert, nichts zu speichern.");
    expect(wrapper.get("[role=status]").element.textContent).not.toBe(first); // told anew, to be read anew
  });

  it("states a field's problem at the field and takes the keyboard there", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(
      new ApiError("server", 422, "invalid_field", "Required.", { field: "verbatim", problem: "required" }),
    );
    const wrapper = editor();
    await write(wrapper, "");

    await save(wrapper);

    expect(wrapper.get(".field__error").text()).toBe("Dieses Feld braucht einen Wert.");
    expect(document.activeElement).toBe(wrapper.get("textarea, input").element);
  });

  it("says a failure above the form, which stays to try again", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("network", 0));
    const wrapper = editor();
    await write(wrapper, "Neu.");

    await save(wrapper);

    expect(wrapper.get(".row-editor__problem[role=alert]").text()).toContain("Die Änderung wurde nicht gespeichert.");
    expect((wrapper.get("textarea, input").element as HTMLInputElement).value).toBe("Neu.");
  });

  it("says why the tree closed meanwhile and keeps the draft to copy, without a form to save it", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const wrapper = editor();
    await write(wrapper, "Mein Satz.");
    await wrapper.get("input[type=text]").setValue("Stufe 3");

    await save(wrapper);

    expect(wrapper.emitted("closed")).toEqual([["job_open"]]);
    const notice = wrapper.get(".row-editor__closed");
    expect(notice.get("[role=alert]").text()).toBe(t("refusals.job_open"));
    expect(document.activeElement).toBe(notice.element);
    expect(notice.text()).toMatch(/Dein Entwurf.*Wortlaut.*Mein Satz\./s);
    // a term and its value side by side, as the facts' grid lays them out
    expect(notice.findAll("dl > *").map((item) => item.element.tagName)).toEqual(["DT", "DD", "DT", "DD"]);
    expect(notice.findAll("dd").map((item) => item.text())).toEqual(["Mein Satz.", "Stufe 3"]);
    expect(wrapper.find("form").exists()).toBe(false);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("keeps in the draft shown what the user changed, not what another changed meanwhile", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const wrapper = editor();
    await write(wrapper, "Mein Satz.");
    await save(wrapper);

    // the tree read anew: another set the kind meanwhile
    await wrapper.setProps({ row: { ...ROW, statement: stored({ statement_kind: CV + "kind_other" }, 4) } as Row });

    expect(wrapper.get(".row-editor__closed").findAll("dd").map((item) => item.text())).toEqual(["Mein Satz."]);
  });

  it("says when the row is gone", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 404, "no_statement"));
    const wrapper = editor();
    await write(wrapper, "Neu.");

    await save(wrapper);

    expect(wrapper.emitted("gone")).toHaveLength(1);
  });
});

describe("a statement's anchors in its editor", () => {
  function placed(id: string, page: number, blocks: string[]): TreeAnchor {
    return { id, page_start: page, page_end: null, printed_page: null, quote: null, match_kind: null, match_score: null, blocks };
  }

  const PLACED = statement_("s1", { ...SAID, anchors: [placed("q1", 5, ["p5-b2"])] });
  const PLACED_ROW = rowsOf([node_("a", { statements: [PLACED] })]).get("statement:s1") as Row;

  function placedEditor(): VueWrapper {
    shown = mount(RowEditor, { props: { row: PLACED_ROW, form: form_(), onSaved: vi.fn() }, attachTo: document.body });
    return shown;
  }

  async function addAnchor(wrapper: VueWrapper, code: string): Promise<string> {
    const taking = (wrapper.vm as unknown as { addAnchor: (code: string) => string }).addAnchor(code);
    await nextTick();
    return taking;
  }

  const entries = (wrapper: VueWrapper) => wrapper.findAll(".anchor-draft li span").map((one) => one.text());

  it("lists the draft's anchors in its form, before the button that saves them; a node's editor none", async () => {
    const wrapper = placedEditor();

    const list = wrapper.get(".row-form .anchor-draft").element;
    const button = wrapper.get(".row-form__save").element;
    expect(list.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(entries(wrapper)).toEqual(["Seite 5: 1 Block (p5-b2)"]);
    expect(await violations(wrapper.html())).toEqual([]);
    wrapper.unmount();

    const node = rowsOf([node_("a", { statements: [PLACED] })]).get("node:a") as Row;
    shown = mount(RowEditor, { props: { row: node, form: form_() }, attachTo: document.body });
    expect(shown.find(".anchor-draft").exists()).toBe(false);
  });

  it("takes an anchor chosen in the source and lets one go, the draft open; saving sends them all", async () => {
    const sent = vi.spyOn(api, "editStatement").mockResolvedValue({ ...PLACED, revision: 4, anchors: [placed("q2", 6, ["p6-b1"])] });
    const wrapper = placedEditor();

    expect(await addAnchor(wrapper, "blocks:p6-b1")).toBe("taken");
    expect(await addAnchor(wrapper, "blocks:p6-b1")).toBe("held");
    expect(entries(wrapper)).toEqual(["Seite 5: 1 Block (p5-b2)", "Seite 6: 1 Block (p6-b1)"]);
    expect(wrapper.emitted("dirty")?.at(-1)).toEqual([true]);
    await wrapper.findAll(".anchor-draft li button")[0]?.trigger("click");
    expect(entries(wrapper)).toEqual(["Seite 6: 1 Block (p6-b1)"]);
    await save(wrapper);

    expect(sent).toHaveBeenCalledWith("s1", 3, {}, [{ blocks: ["p6-b1"] }]);
    expect(wrapper.emitted("dirty")?.at(-1)).toEqual([false]);
  });

  it("takes the keyboard to the anchors where their problem is said", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(
      new ApiError("server", 422, "invalid_field", "No block.", { field: "anchors", problem: "unknown_block" }),
    );
    const wrapper = placedEditor();
    await addAnchor(wrapper, "blocks:p6-b1");

    await save(wrapper);

    expect(document.activeElement).toBe(wrapper.get(".anchor-draft").element);
    expect(wrapper.get(".anchor-draft .field__error").text()).toBe(t("documents.tree.problems.unknown_block"));
  });

  it("keeps the anchors changed in the draft it shows once the tree closed, and takes no more", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const wrapper = placedEditor();
    await addAnchor(wrapper, "blocks:p6-b1");
    await save(wrapper);

    const kept = () => wrapper.findAll(".row-editor__closed dd").map((one) => one.text());
    expect(wrapper.findAll(".row-editor__closed dt").map((one) => one.text())).toEqual(["Fundstellen"]);
    expect(kept()).toEqual(["Seite 5: 1 Block (p5-b2); Seite 6: 1 Block (p6-b1)"]);

    expect(await addAnchor(wrapper, "page:9")).toBe("refused");
    expect(kept()).toEqual(["Seite 5: 1 Block (p5-b2); Seite 6: 1 Block (p6-b1)"]);
  });
});
