import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, type EffectScope } from "vue";

import * as api from "@/api";
import { ApiError, type NodeRow } from "@/api";
import { t } from "@/i18n/de";
import { useRowCreate, type CreateTarget } from "@/rowCreate";

import { CV, form_, node_, statement_ } from "./treeFixtures";

let scope: EffectScope;

function creator(target: CreateTarget) {
  const creating = scope.run(() => useRowCreate(target, form_()));
  if (!creating) throw new Error("no scope");
  return creating;
}

const AT_TOP: CreateTarget = { kind: "node", document: "d1", parent: null };
const UNDER_A: CreateTarget = { kind: "statement", node: "a" };
const REQUIRED = t("documents.tree.problems.required");

// as an added node answers: a tree's node is one
function made(id: string): NodeRow {
  return node_(id);
}

beforeEach(() => {
  vi.restoreAllMocks();
  scope = effectScope();
});

afterEach(() => {
  scope.stop();
});

describe("adding a row", () => {
  it("begins empty, a draft open once something is entered", () => {
    const creating = creator(AT_TOP);

    expect(creating.draft.value).toEqual({ original_title: "", function: "", node_type: "", code: "" });
    expect(creating.dirty.value).toBe(false);
    creating.draft.value = { ...creating.draft.value, code: "1.2" };
    expect(creating.dirty.value).toBe(true);
  });

  it("adds a node at the top or under its parent with the fields filled in, and gives its key", async () => {
    const sent = vi.spyOn(api, "addNode").mockResolvedValueOnce(made("n9")).mockResolvedValueOnce(made("n10"));
    const top = creator(AT_TOP);
    top.draft.value = { ...top.draft.value, original_title: "Optik", function: CV + "fn_area" };
    const under = creator({ kind: "node", document: "d1", parent: "a" });
    under.draft.value = { ...under.draft.value, original_title: "Linsen", function: CV + "fn_unit", code: "1.1" };

    expect(await top.save()).toEqual({ outcome: "created", key: "node:n9" });
    expect(await under.save()).toEqual({ outcome: "created", key: "node:n10" });

    expect(sent).toHaveBeenNthCalledWith(1, "d1", null, { original_title: "Optik", function: CV + "fn_area" });
    expect(sent).toHaveBeenNthCalledWith(2, "d1", "a", { original_title: "Linsen", function: CV + "fn_unit", code: "1.1" });
  });

  it("says each required field left empty at it, asking nothing", async () => {
    const sent = vi.spyOn(api, "addNode");
    const creating = creator(AT_TOP);
    creating.draft.value = { ...creating.draft.value, original_title: "  " };

    expect(await creating.save()).toEqual({ outcome: "invalid" });

    expect(creating.errors.value).toEqual({ original_title: REQUIRED, function: REQUIRED });
    expect(sent).not.toHaveBeenCalled();
  });

  it("adds a statement only with an anchor: without, it says so at the list and asks nothing", async () => {
    const sent = vi.spyOn(api, "addStatement").mockResolvedValue(statement_("s9"));
    const creating = creator(UNDER_A);
    creating.draft.value = {
      ...creating.draft.value,
      verbatim: "Sie messen.",
      statement_kind: CV + "kind_learningOutcome",
      addressees: [CV + "addr_learner"],
    };

    expect(await creating.save()).toEqual({ outcome: "invalid" });
    expect(creating.errors.value).toEqual({ anchors: t("refusals.anchor_missing") });
    expect(sent).not.toHaveBeenCalled();

    expect(creating.addAnchor("blocks:p5-b3,p5-b2")).toBe(true);
    expect(creating.addAnchor("blocks:p5-b2,p5-b3")).toBe(false); // held already
    creating.addAnchor("page:7");
    creating.removeAnchor("page:7");
    expect(await creating.save()).toEqual({ outcome: "created", key: "statement:s9" });
    expect(sent).toHaveBeenCalledWith(
      "a",
      { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome", addressees: [CV + "addr_learner"] },
      [{ blocks: ["p5-b2", "p5-b3"] }],
    );
    expect(creating.errors.value).toEqual({});
  });

  it("states a refusal: a field's problem at it, the tree closed, the parent gone, another failure above", async () => {
    vi.spyOn(api, "addNode")
      .mockRejectedValueOnce(new ApiError("server", 422, "invalid_field", "Long.", { field: "code", problem: "too_long" }))
      .mockRejectedValueOnce(new ApiError("server", 409, "job_open"))
      .mockRejectedValueOnce(new ApiError("server", 404, "no_node"))
      .mockRejectedValueOnce(new ApiError("network", 0));
    const creating = creator({ kind: "node", document: "d1", parent: "a" });
    creating.draft.value = { ...creating.draft.value, original_title: "Optik", function: CV + "fn_area", code: "x" };

    expect(await creating.save()).toEqual({ outcome: "invalid" });
    expect(creating.errors.value).toEqual({ code: t("documents.tree.problems.too_long") });
    expect(await creating.save()).toEqual({ outcome: "closed" });
    expect(creating.closed.value).toBe("job_open");
    expect(await creating.save()).toEqual({ outcome: "gone" });
    expect(creating.closed.value).toBeNull(); // tried again, the closing goes with it
    expect(await creating.save()).toEqual({ outcome: "failed" });
    expect(creating.problem.value?.text).toBe(t("documents.tree.create.failed"));
    // the draft kept to try again; tried again, the failure goes with it
    expect(creating.draft.value.original_title).toBe("Optik");
    creating.draft.value = { ...creating.draft.value, function: "" };
    expect(await creating.save()).toEqual({ outcome: "invalid" });
    expect(creating.problem.value).toBeNull();
  });

  it("says it saves while it does", async () => {
    let answer: (row: NodeRow) => void = () => undefined;
    vi.spyOn(api, "addNode").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const creating = creator(AT_TOP);
    creating.draft.value = { ...creating.draft.value, original_title: "Optik", function: CV + "fn_area" };

    const saved = creating.save();
    expect(creating.saving.value).toBe(true);
    answer(made("n9"));
    await saved;
    // added: busy until it goes, so that it is not added twice
    expect(creating.saving.value).toBe(true);
  });

  it("is no longer busy once a try failed", async () => {
    vi.spyOn(api, "addNode").mockRejectedValue(new ApiError("network", 0));
    const creating = creator(AT_TOP);
    creating.draft.value = { ...creating.draft.value, original_title: "Optik", function: CV + "fn_area" };

    await creating.save();

    expect(creating.saving.value).toBe(false);
  });
});
