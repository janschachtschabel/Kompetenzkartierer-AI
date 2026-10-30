import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import * as api from "@/api";
import { ApiError } from "@/api";
import RowActions from "@/components/RowActions.vue";
import RowCreator from "@/components/RowCreator.vue";
import { rowsOf, type Row } from "@/documentTree";
import { t } from "@/i18n/de";
import type { CreateTarget } from "@/rowCreate";

import { violations } from "./axe";
import { CV, form_, node_, statement_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

const AT_TOP: CreateTarget = { kind: "node", document: "d1", parent: null };
const UNDER_A: CreateTarget = { kind: "statement", node: "a" };

function creator(target: CreateTarget): VueWrapper {
  shown = mount(RowCreator, { props: { target, form: form_() }, attachTo: document.body });
  return shown;
}

async function submit(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("form").trigger("submit");
  await flushPromises();
}

async function fillNode(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("input").setValue("Optik");
  await wrapper.get("select").setValue(CV + "fn_area");
}

function button(wrapper: VueWrapper, label: string) {
  const found = wrapper.findAll("button").find((one) => one.text() === label);
  if (!found) throw new Error(label);
  return found;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("a new row's form", () => {
  it("adds a node with the fields filled in and gives its key, a draft open meanwhile", async () => {
    const sent = vi.spyOn(api, "addNode").mockResolvedValue(node_("n9"));
    const wrapper = creator(AT_TOP);
    expect(wrapper.emitted("dirty")).toEqual([[false]]);
    expect(wrapper.find(".anchor-draft").exists()).toBe(false);
    expect(wrapper.get(".row-form__save").text()).toBe(t("documents.tree.create.save"));
    expect(await violations(wrapper.html())).toEqual([]);

    await fillNode(wrapper);
    expect(wrapper.emitted("dirty")?.at(-1)).toEqual([true]);
    await submit(wrapper);

    expect(sent).toHaveBeenCalledWith("d1", null, { original_title: "Optik", function: CV + "fn_area" });
    expect(wrapper.emitted("created")).toEqual([["node:n9"]]);
  });

  it("takes the keyboard to a required field left empty", async () => {
    const wrapper = creator(AT_TOP);
    await wrapper.get("select").setValue(CV + "fn_area");

    await submit(wrapper);

    expect(document.activeElement).toBe(wrapper.get("input").element);
    expect(wrapper.text()).toContain(t("documents.tree.problems.required"));
  });

  it("adds a statement only with an anchor, the keyboard taken to their list without one", async () => {
    const sent = vi.spyOn(api, "addStatement").mockResolvedValue(statement_("s9"));
    const wrapper = creator(UNDER_A);
    await wrapper.get("textarea").setValue("Sie messen.");
    await wrapper.get("select").setValue(CV + "kind_learningOutcome");
    await wrapper.get("input[type=checkbox]").setValue(true);

    await submit(wrapper);
    expect(document.activeElement).toBe(wrapper.get(".anchor-draft").element);
    expect(sent).not.toHaveBeenCalled();

    (wrapper.vm as unknown as { addAnchor: (code: string) => void }).addAnchor("page:5");
    await nextTick();
    expect(wrapper.findAll(".anchor-draft li span").map((one) => one.text())).toEqual(["Auf Seite 5 nicht gefunden"]);
    await submit(wrapper);

    expect(sent).toHaveBeenCalledWith(
      "a",
      { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome", addressees: [CV + "addr_learner"] },
      [{ page: 5 }],
    );
    expect(wrapper.emitted("created")).toEqual([["statement:s9"]]);
  });

  it("lets an empty draft go at once, and asks before one with entries goes", async () => {
    const empty = creator(AT_TOP);
    await button(empty, t("documents.tree.create.cancel")).trigger("click");
    expect(empty.emitted("cancel")).toHaveLength(1);
    empty.unmount();

    const wrapper = creator(AT_TOP);
    await fillNode(wrapper);
    await button(wrapper, t("documents.tree.create.cancel")).trigger("click");
    expect(wrapper.get("[role=dialog]").text()).toContain(t("documents.tree.create.discard.message"));
    await button(wrapper, t("documents.tree.create.discard.cancel")).trigger("click");
    expect([wrapper.find("[role=dialog]").exists(), wrapper.emitted("cancel")]).toEqual([false, undefined]);
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("Optik");

    await button(wrapper, t("documents.tree.create.cancel")).trigger("click");
    await button(wrapper, t("documents.tree.create.discard.confirm")).trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });

  it("says why the tree closed, the draft kept, and that the parent is gone", async () => {
    vi.spyOn(api, "addNode")
      .mockRejectedValueOnce(new ApiError("server", 409, "job_open"))
      .mockRejectedValueOnce(new ApiError("server", 404, "no_node"));
    const wrapper = creator({ kind: "node", document: "d1", parent: "a" });
    await fillNode(wrapper);

    await submit(wrapper);
    const alert = wrapper.get(".row-creator__closed");
    expect([alert.attributes("role"), alert.text()]).toEqual(["alert", t("refusals.job_open")]);
    expect(document.activeElement).toBe(alert.element);
    expect(wrapper.emitted("closed")).toEqual([["job_open"]]);
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("Optik");

    await submit(wrapper);
    expect(wrapper.emitted("gone")).toHaveLength(1);
  });

  it("says another failure above the form, the draft kept to try again", async () => {
    vi.spyOn(api, "addNode").mockRejectedValue(new ApiError("network", 0));
    const wrapper = creator(AT_TOP);
    await fillNode(wrapper);

    await submit(wrapper);

    expect(wrapper.get(".row-creator__problem").text()).toContain(t("documents.tree.create.failed"));
    expect(wrapper.emitted("created")).toBeUndefined();
  });

  it("says no draft is open once it goes", async () => {
    const wrapper = creator(AT_TOP);
    await fillNode(wrapper);

    wrapper.unmount();

    expect(wrapper.emitted("dirty")?.at(-1)).toEqual([false]);
  });
});

describe("the ways on from a row chosen", () => {
  const ROWS = rowsOf([node_("a", { statements: [statement_("s1")] })]);
  const row = (key: "node:a" | "statement:s1") => ROWS.get(key) as Row;

  it("add a node under a node chosen, or a statement to it", async () => {
    shown = mount(RowActions, { props: { row: row("node:a") }, attachTo: document.body });

    await button(shown, t("documents.tree.create.child")).trigger("click");
    await button(shown, t("documents.tree.create.statement")).trigger("click");

    expect(shown.emitted("create")).toEqual([["node"], ["statement"]]);
    expect(await violations(shown.html())).toEqual([]);
  });

  it("add nothing under a statement", () => {
    shown = mount(RowActions, { props: { row: row("statement:s1") }, attachTo: document.body });

    expect(shown.findAll("button")).toHaveLength(0);
  });
});
