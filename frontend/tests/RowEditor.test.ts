import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type TreeStatement } from "@/api";
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

  it("says when the row is gone", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 404, "no_statement"));
    const wrapper = editor();
    await write(wrapper, "Neu.");

    await save(wrapper);

    expect(wrapper.emitted("gone")).toHaveLength(1);
  });
});
