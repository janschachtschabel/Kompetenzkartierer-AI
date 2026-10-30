import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import RowActions from "@/components/RowActions.vue";
import { rowsOf, type Row } from "@/documentTree";
import { t } from "@/i18n/de";

import { violations } from "./axe";
import { node_, statement_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

const ROWS = rowsOf([
  node_("a", { revision: 4, statements: [statement_("s1", { revision: 7 })], children: [node_("b", { statements: [statement_("s2")] })] }),
]);
const row = (key: "node:a" | "statement:s1") => ROWS.get(key) as Row;

// how taking a row away went, as the panel hears it: by a function the actions are given
let dropped = vi.fn();

function actions(key: "node:a" | "statement:s1"): VueWrapper {
  dropped = vi.fn();
  shown = mount(RowActions, { props: { row: row(key), onDropped: dropped }, attachTo: document.body });
  return shown;
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

describe("the ways on from a row chosen", () => {
  it("add a node under a node chosen, or a statement to it", async () => {
    const wrapper = actions("node:a");

    await button(wrapper, t("documents.tree.create.child")).trigger("click");
    await button(wrapper, t("documents.tree.create.statement")).trigger("click");

    expect(wrapper.emitted("create")).toEqual([["node"], ["statement"]]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("take a node away once asked, saying what goes with it", async () => {
    const sent = vi.spyOn(api, "dropNode").mockResolvedValue({ nodes: 2, statements: 2 });
    const wrapper = actions("node:a");

    await button(wrapper, t("documents.tree.drop.node")).trigger("click");
    const dialog = wrapper.get("[role=dialog]");
    expect(dialog.text()).toContain(t("documents.tree.drop.titleNode"));
    expect(dialog.text()).toContain("Der Knoten wird gelöscht – mit 1 Unterknoten und 2 Aussagen und ihren Befunden.");
    expect(await violations(wrapper.html())).toEqual([]);
    await button(wrapper, t("dialog.cancel")).trigger("click");
    expect(sent).not.toHaveBeenCalled();

    await button(wrapper, t("documents.tree.drop.node")).trigger("click");
    await wrapper.findAll("[role=dialog] button").find((one) => one.text() === t("documents.tree.drop.node"))?.trigger("click");
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("a", 4);
    expect(dropped).toHaveBeenCalledWith({ outcome: "dropped", nodes: 2, statements: 2 }, "node:a");
  });

  it("offer a statement only to be rejected or deleted, as the server decides", async () => {
    vi.spyOn(api, "dropStatement").mockResolvedValue({ outcome: "rejected", revision: 8 });
    const wrapper = actions("statement:s1");
    expect(wrapper.findAll("button").map((one) => one.text())).toEqual([t("documents.tree.drop.statement")]);

    await button(wrapper, t("documents.tree.drop.statement")).trigger("click");
    expect(wrapper.get("[role=dialog]").text()).toContain(t("documents.tree.drop.messageStatement"));
    await wrapper
      .findAll("[role=dialog] button")
      .find((one) => one.text() === t("documents.tree.drop.statement"))
      ?.trigger("click");
    await flushPromises();

    expect(dropped).toHaveBeenCalledWith({ outcome: "rejected" }, "statement:s1");
  });

  it("say a failure where it was asked, and tell nothing", async () => {
    vi.spyOn(api, "dropStatement").mockRejectedValue(new ApiError("network", 0));
    const wrapper = actions("statement:s1");

    await button(wrapper, t("documents.tree.drop.statement")).trigger("click");
    await wrapper
      .findAll("[role=dialog] button")
      .find((one) => one.text() === t("documents.tree.drop.statement"))
      ?.trigger("click");
    await flushPromises();

    const alert = wrapper.get(".row-actions__problem");
    expect([alert.attributes("role"), alert.text()]).toEqual(["alert", expect.stringContaining(t("documents.tree.drop.failed"))]);
    expect(dropped).not.toHaveBeenCalled();
  });

  it("asks nothing more while it takes the row away, and tells how it went once another row is chosen", async () => {
    let answer: (done: { outcome: "deleted" | "rejected"; revision: number | null }) => void = () => undefined;
    vi.spyOn(api, "dropStatement").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const wrapper = actions("statement:s1");
    await button(wrapper, t("documents.tree.drop.statement")).trigger("click");
    await wrapper
      .findAll("[role=dialog] button")
      .find((one) => one.text() === t("documents.tree.drop.statement"))
      ?.trigger("click");

    const again = button(wrapper, t("documents.tree.drop.statement"));
    expect(again.attributes("aria-disabled")).toBe("true");
    await again.trigger("click");
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);

    wrapper.unmount();
    answer({ outcome: "deleted", revision: null });
    await flushPromises();
    expect(dropped).toHaveBeenCalledWith({ outcome: "deleted" }, "statement:s1");
  });
});
