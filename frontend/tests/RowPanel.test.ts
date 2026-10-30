import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import RowPanel from "@/components/RowPanel.vue";
import { rowsOf, type Row } from "@/documentTree";
import { t } from "@/i18n/de";

import { form_, node_, tree_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

const NODES = [node_("a", { fields: { original_title: "Optik", code: "LF 1" } })];
const ROW = rowsOf(NODES).get("node:a") as Row;

describe("the panel of a row being added", () => {
  it("gives the form why the tree, read anew, closed under it", async () => {
    shown = mount(RowPanel, {
      props: { row: ROW, tree: tree_(NODES), form: form_(), creating: { kind: "node", document: "d1", parent: "a" } },
      attachTo: document.body,
    });
    await shown.get(".row-creator input").setValue("Neu");

    await shown.setProps({ tree: tree_(NODES, { editable: false, closed: "frozen" }) });

    expect(shown.get(".row-creator__closed [role=alert]").text()).toBe(t("refusals.frozen"));
    expect(shown.find(".row-creator form").exists()).toBe(false);
  });
});
