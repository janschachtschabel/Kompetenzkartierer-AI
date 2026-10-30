import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref, type EffectScope } from "vue";

import * as api from "@/api";
import { ApiError, type TreeStatement } from "@/api";
import { rowsOf, type Row, type RowKey } from "@/documentTree";
import { useRowSave } from "@/rowSave";

import { CV, form_, node_, statement_ } from "./treeFixtures";

const SAID = statement_("s1", {
  revision: 3,
  fields: { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome", addressees: [CV + "addr_learner"] },
});
const NODE = node_("a", { revision: 2, fields: { original_title: "Optik", function: CV + "fn_area" }, statements: [SAID] });
const ROWS = rowsOf([NODE]);

function row(key: RowKey): Row {
  const found = ROWS.get(key);
  if (!found) throw new Error(key);
  return found;
}

let scope: EffectScope;

function editor(key: RowKey = "statement:s1") {
  const shown = ref(row(key));
  const editing = scope.run(() => useRowSave(shown, ref(form_())));
  if (!editing) throw new Error("no scope");
  return { shown, editing };
}

function stored(fields: Record<string, unknown>, revision: number): TreeStatement {
  return { ...SAID, revision, fields: { ...SAID.fields, ...fields } as TreeStatement["fields"] };
}

beforeEach(() => {
  vi.restoreAllMocks();
  scope = effectScope();
});

afterEach(() => {
  scope.stop();
});

describe("saving a row's change", () => {
  it("sends only the fields changed with the revision read, and takes the answer as the row stored", async () => {
    const sent = vi.spyOn(api, "editStatement").mockResolvedValue(stored({ verbatim: "Sie messen genau." }, 4));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Sie messen genau." };
    expect(editing.dirty.value).toBe(true);

    expect(await editing.save()).toBe("saved");

    expect(sent).toHaveBeenCalledWith("s1", 3, { verbatim: "Sie messen genau." });
    expect([editing.revision.value, editing.dirty.value]).toEqual([4, false]);
  });

  it("changes a node by its own request", async () => {
    const sent = vi.spyOn(api, "editNode").mockResolvedValue({ ...NODE, revision: 3 });
    const { editing } = editor("node:a");
    editing.draft.value = { ...editing.draft.value, code: "1" };

    await editing.save();

    expect(sent).toHaveBeenCalledWith("a", 2, { code: "1" });
  });

  it("asks nothing where nothing changed", async () => {
    const sent = vi.spyOn(api, "editStatement");
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Sie messen.", levelText: "  " };

    expect(await editing.save()).toBe("unchanged");
    expect(sent).not.toHaveBeenCalled();
  });

  it("keeps what the user typed while a change was saved, laid on the row as stored", async () => {
    let answer: (row: TreeStatement) => void = () => undefined;
    vi.spyOn(api, "editStatement").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };

    const saved = editing.save();
    editing.draft.value = { ...editing.draft.value, levelText: "Stufe 3" }; // typed on meanwhile
    answer(stored({ verbatim: "Neu.", statement_kind: CV + "kind_other" }, 4)); // stored otherwise meanwhile

    expect(await saved).toBe("saved");
    expect([editing.draft.value.verbatim, editing.draft.value.levelText, editing.dirty.value]).toEqual([
      "Neu.",
      "Stufe 3",
      true,
    ]);
    expect(editing.draft.value.statement_kind).toBe(CV + "kind_other");
    expect(editing.revision.value).toBe(4);
  });

  it("says a required field emptied at the field, asking nothing", async () => {
    const sent = vi.spyOn(api, "editStatement");
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: " ", addressees: [] };

    expect(await editing.save()).toBe("invalid");

    expect(sent).not.toHaveBeenCalled();
    expect(editing.errors.value).toEqual({
      verbatim: "Dieses Feld braucht einen Wert.",
      addressees: "Dieses Feld braucht einen Wert.",
    });
  });

  it("leaves a required field already empty to the server, the change naming it not", async () => {
    const sent = vi.spyOn(api, "editStatement").mockResolvedValue(stored({ levelText: "Stufe 2" }, 4));
    const shown = ref({ ...row("statement:s1"), statement: stored({ statement_kind: null }, 3) } as Row);
    const editing = scope.run(() => useRowSave(shown, ref(form_())));
    if (!editing) throw new Error("no scope");
    editing.draft.value = { ...editing.draft.value, levelText: "Stufe 2" };

    expect(await editing.save()).toBe("saved");
    expect(sent).toHaveBeenCalledWith("s1", 3, { levelText: "Stufe 2" });

    editing.draft.value = { ...editing.draft.value, levelText: "" }; // an optional field cleared
    await editing.save();
    expect(sent).toHaveBeenLastCalledWith("s1", 4, { levelText: null });
  });

  it("says it saves while it does", async () => {
    let answer: (row: TreeStatement) => void = () => undefined;
    vi.spyOn(api, "editStatement").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };

    const saved = editing.save();
    expect(editing.saving.value).toBe(true);
    answer(stored({ verbatim: "Neu." }, 4));
    await saved;

    expect(editing.saving.value).toBe(false);
  });
});

describe("a change that met another stored meanwhile", () => {
  function stale(current: unknown): ApiError {
    return new ApiError("server", 409, "stale_revision", "Changed meanwhile.", { current });
  }

  it("takes in what only the other changed, puts what both changed before the user, and saves on the stored", async () => {
    const sent = vi
      .spyOn(api, "editStatement")
      .mockRejectedValueOnce(stale(stored({ verbatim: "Ihr Satz.", levelText: "Stufe 2" }, 5)))
      .mockResolvedValueOnce(stored({ verbatim: "Mein Satz.", levelText: "Stufe 2" }, 6));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Mein Satz." };

    expect(await editing.save()).toBe("conflict");
    expect(editing.conflict.value?.clashes).toEqual([{ key: "verbatim", yours: "Mein Satz.", stored: "Ihr Satz." }]);
    expect(editing.conflict.value?.taken).toEqual(["levelText"]);
    expect(editing.draft.value.levelText).toBe("Stufe 2");
    expect(editing.revision.value).toBe(5);

    editing.keep("verbatim");
    expect(editing.conflict.value?.clashes).toEqual([]);
    await editing.save();

    expect(sent).toHaveBeenLastCalledWith("s1", 5, { verbatim: "Mein Satz." });
    expect(editing.conflict.value).toBeNull();
  });

  it("takes a change met by the same change stored meanwhile as saved", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValueOnce(stale(stored({ verbatim: "Gleich." }, 5)));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Gleich." };

    expect(await editing.save()).toBe("saved");

    expect([editing.conflict.value, editing.revision.value, editing.dirty.value]).toEqual([null, 5, false]);
  });

  it("saves nothing while a field both changed is undecided", async () => {
    const sent = vi
      .spyOn(api, "editStatement")
      .mockRejectedValueOnce(stale(stored({ verbatim: "Ihr Satz." }, 5)));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Mein Satz." };
    await editing.save();

    expect(await editing.save()).toBe("undecided");
    expect(sent).toHaveBeenCalledTimes(1);
  });

  it("takes the stored value of a field when the user chooses it", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValueOnce(stale(stored({ verbatim: "Ihr Satz." }, 5)));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Mein Satz." };
    await editing.save();

    editing.take("verbatim");

    expect(editing.draft.value.verbatim).toBe("Ihr Satz.");
    expect([editing.conflict.value?.clashes, editing.dirty.value]).toEqual([[], false]);
  });

  it("says the row is gone where the stored one is none, or the row is no more", async () => {
    vi.spyOn(api, "editStatement")
      .mockRejectedValueOnce(stale(null))
      .mockRejectedValueOnce(new ApiError("server", 404, "no_statement"));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };

    expect(await editing.save()).toBe("gone");
    expect(await editing.save()).toBe("gone");
  });
});

describe("a change refused", () => {
  it.each(["job_open", "frozen", "not_extracted", "no_form", "file_hidden"])(
    "is refused for the tree closing meanwhile (%s): the reason kept, the draft too",
    async (code) => {
      vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 409, code));
      const { editing } = editor();
      editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };

      expect(await editing.save()).toBe("closed");

      expect([editing.closed.value, editing.draft.value.verbatim]).toEqual([code, "Neu."]);
    },
  );

  it("finds a node gone as a statement", async () => {
    vi.spyOn(api, "editNode").mockRejectedValue(new ApiError("server", 404, "no_node"));
    const { editing } = editor("node:a");
    editing.draft.value = { ...editing.draft.value, code: "9" };

    expect(await editing.save()).toBe("gone");
  });

  it("states a field's problem at the field, one the form does not hold above it", async () => {
    vi.spyOn(api, "editStatement")
      .mockRejectedValueOnce(
        new ApiError("server", 422, "invalid_field", "Required.", { field: "verbatim", problem: "required" }),
      )
      .mockRejectedValueOnce(new ApiError("server", 422, "invalid_field", "Odd.", { field: "levelText", problem: "new" }))
      .mockRejectedValueOnce(new ApiError("server", 422, "invalid_field", "Unknown.", { field: "lead_in", problem: "x" }));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };

    expect(await editing.save()).toBe("invalid"); // the server's word for it, at the field
    expect(editing.errors.value).toEqual({ verbatim: "Dieses Feld braucht einen Wert." });
    expect(await editing.save()).toBe("invalid"); // a problem this app does not know yet, at a field it shows
    expect(editing.errors.value).toEqual({ levelText: "Dieser Wert lässt sich so nicht speichern." });
    expect(await editing.save()).toBe("invalid");
    expect([editing.errors.value, editing.problem.value?.explanation]).toEqual([
      {},
      "Ein Feld, das dieses Formular nicht zeigt, lässt sich so nicht setzen.",
    ]);
  });

  it("says a failure above the form and keeps the draft to try again", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("network", 0));
    const { editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };

    expect(await editing.save()).toBe("failed");

    expect(editing.problem.value?.text).toBe("Die Änderung wurde nicht gespeichert.");
    expect(editing.draft.value.verbatim).toBe("Neu.");
  });
});

describe("the row edited", () => {
  it("begins anew with another row: its values, no conflict, no problems", async () => {
    vi.spyOn(api, "editStatement").mockRejectedValue(new ApiError("server", 409, "job_open"));
    const { shown, editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };
    await editing.save();

    shown.value = row("node:a");
    await nextTick();

    expect(editing.draft.value.original_title).toBe("Optik");
    expect([editing.closed.value, editing.revision.value, editing.dirty.value]).toEqual([null, 2, false]);
  });

  it("leaves another row chosen while a change was saved as it is", async () => {
    let answer: (row: TreeStatement) => void = () => undefined;
    vi.spyOn(api, "editStatement").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const { shown, editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };
    const saved = editing.save();

    shown.value = row("node:a");
    await nextTick();
    answer(stored({ verbatim: "Neu." }, 4));
    await saved;

    expect([editing.draft.value.original_title, editing.revision.value]).toEqual(["Optik", 2]);
  });

  it("leaves another row chosen while a change failed as it is", async () => {
    let refuse: (error: unknown) => void = () => undefined;
    vi.spyOn(api, "editStatement").mockReturnValue(new Promise((_resolve, reject) => (refuse = reject)));
    const { shown, editing } = editor();
    editing.draft.value = { ...editing.draft.value, verbatim: "Neu." };
    const saved = editing.save();

    shown.value = row("node:a");
    await nextTick();
    refuse(new ApiError("server", 409, "job_open"));

    expect(await saved).toBe("failed");
    expect([editing.closed.value, editing.problem.value, editing.draft.value.original_title]).toEqual([null, null, "Optik"]);
  });

  it("takes the row read anew where the user changed nothing, and keeps the draft where they did", async () => {
    const { shown, editing } = editor();
    const said = row("statement:s1");
    if (said.kind !== "statement") throw new Error("a statement");
    const again = (verbatim: string, revision: number): Row => ({ ...said, statement: stored({ verbatim }, revision) });

    shown.value = again("Anders gelesen.", 4);
    await flushPromises();
    expect([editing.draft.value.verbatim, editing.revision.value]).toEqual(["Anders gelesen.", 4]);

    editing.draft.value = { ...editing.draft.value, verbatim: "Mein Entwurf." };
    shown.value = again("Wieder anders.", 5);
    await flushPromises();
    expect([editing.draft.value.verbatim, editing.revision.value]).toEqual(["Mein Entwurf.", 4]);
  });
});
