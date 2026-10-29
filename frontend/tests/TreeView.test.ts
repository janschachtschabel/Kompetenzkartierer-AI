import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import TreeView from "@/components/TreeView.vue";
import { rowsOf, type RowKey } from "@/documentTree";

import { violations } from "./axe";
import { CV, SCHOOL, form_, node_, statement_ } from "./treeFixtures";

let shown: VueWrapper | null = null;
// the tree's v-model:selected, as the view would hold it
let selected: RowKey | null = null;

afterEach(() => {
  shown?.unmount();
  shown = null;
  selected = null;
  document.body.innerHTML = "";
});

// a: LF 1 Optik, an Inhaltsbereich with two findings; its statements s1 and s2 (confirmed); its child a1 (s3);
// b: LF 2 without a title, rejected
const NODES = [
  node_("a", {
    fields: { original_title: "Optik", code: "LF 1", function: CV + "fn_area", node_type: SCHOOL + "Inhaltsbereich" },
    findings: { violation: 0, warning: 2, info: 0 },
    statements: [
      statement_("s1", { fields: { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome" } }),
      statement_("s2", { position: 2, review_status: CV + "rev_confirmed" }),
    ],
    children: [
      node_("a1", { fields: { original_title: "Licht", function: CV + "fn_unit" }, statements: [statement_("s3")] }),
    ],
  }),
  node_("b", { position: 2, fields: { original_title: null, code: "LF 2" }, review_status: CV + "rev_rejected" }),
];
const COUNTS = { nodes: {}, statements: {} };

function tree(nodes = NODES, chosen: RowKey | null = null): VueWrapper {
  selected = chosen;
  shown = mount(TreeView, {
    props: {
      rows: rowsOf(nodes),
      form: form_(),
      counts: COUNTS,
      selected: chosen,
      "onUpdate:selected": (next: RowKey | null) => {
        selected = next;
        void shown?.setProps({ selected: next });
      },
    },
    attachTo: document.body,
  });
  return shown;
}

function items(wrapper: VueWrapper): string[][] {
  return wrapper
    .findAll("[role=treeitem]")
    .map((item) => [
      item.attributes("data-key") ?? "",
      item.attributes("aria-level") ?? "",
      item.attributes("aria-expanded") ?? "-",
      item.attributes("tabindex") ?? "",
    ]);
}

function row(wrapper: VueWrapper, key: string): ReturnType<VueWrapper["get"]> {
  return wrapper.get(`[data-key="${key}"]`);
}

async function press(wrapper: VueWrapper, key: string): Promise<void> {
  await wrapper.get("[role=tree]").trigger("keydown", { key });
  await nextTick();
}

describe("a document's tree", () => {
  it("opens its top nodes: each one's statements, then its children, a level deeper, one tab stop", async () => {
    const wrapper = tree();

    expect(wrapper.get("[role=tree]").attributes("aria-label")).toBe("Knoten und Aussagen des Dokuments");
    expect(items(wrapper)).toEqual([
      ["node:a", "1", "true", "0"],
      ["statement:s1", "2", "-", "-1"],
      ["statement:s2", "2", "-", "-1"],
      ["node:a1", "2", "false", "-1"],
      ["node:b", "1", "-", "-1"],
    ]);
    expect(row(wrapper, "node:a").attributes("aria-posinset")).toBe("1");
    expect(row(wrapper, "node:a").attributes("aria-setsize")).toBe("2");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("names each row by what it is: code, title, type, status and findings; wording, kind and status", () => {
    const wrapper = tree();

    expect(row(wrapper, "node:a").text()).toContain("LF 1");
    expect(row(wrapper, "node:a").text()).toContain("Optik");
    expect(row(wrapper, "node:a").text()).toContain("Inhaltsbereich");
    expect(row(wrapper, "node:a").text()).toContain("Vorgeschlagen");
    expect(row(wrapper, "node:a").text()).toContain("2 Befunde");
    expect(row(wrapper, "node:a1").text()).toContain("Einheit"); // no type: its function
    expect(row(wrapper, "node:b").text()).toContain("ohne Titel");
    expect(row(wrapper, "node:b").text()).toContain("Verworfen");
    expect(row(wrapper, "statement:s1").text()).toContain("Sie messen.");
    expect(row(wrapper, "statement:s1").text()).toContain("Lernergebnis");
    expect(row(wrapper, "statement:s2").text()).toContain("Bestätigt");
    // a row's name is its label, not the label of the button that opens it
    const label = row(wrapper, "node:a").attributes("aria-labelledby") ?? "";
    expect(document.getElementById(label)?.textContent).toContain("Knoten");
    expect(document.getElementById(label)?.textContent).not.toContain("Zuklappen");
  });

  it("goes through its rows with the keys, opens and closes nodes, and chooses one with Enter", async () => {
    const wrapper = tree();
    (row(wrapper, "node:a").element as HTMLElement).focus();

    await press(wrapper, "ArrowDown");
    expect(document.activeElement?.getAttribute("data-key")).toBe("statement:s1");
    await press(wrapper, "End");
    await press(wrapper, "ArrowUp");
    expect(document.activeElement?.getAttribute("data-key")).toBe("node:a1");
    await press(wrapper, "ArrowRight");
    expect(row(wrapper, "node:a1").attributes("aria-expanded")).toBe("true");
    await press(wrapper, "ArrowRight");
    expect(document.activeElement?.getAttribute("data-key")).toBe("statement:s3");
    await press(wrapper, "ArrowLeft");
    await press(wrapper, "ArrowLeft");
    expect(row(wrapper, "node:a1").attributes("aria-expanded")).toBe("false");
    await press(wrapper, "Enter");

    expect(selected).toBe("node:a1");
    expect(row(wrapper, "node:a1").attributes("aria-selected")).toBe("true");
    expect(items(wrapper).filter(([, , , tabindex]) => tabindex === "0").map(([key]) => key)).toEqual(["node:a1"]);
  });

  it("chooses a row clicked, and opens or closes a node by its button without choosing it", async () => {
    const wrapper = tree();

    await row(wrapper, "statement:s2").trigger("click");
    expect(selected).toBe("statement:s2");
    await row(wrapper, "node:a1").get("button").trigger("click");

    expect(row(wrapper, "node:a1").attributes("aria-expanded")).toBe("true");
    expect(selected).toBe("statement:s2");
  });

  it("opens the path to the row chosen and puts its tab stop there", () => {
    const wrapper = tree(NODES, "statement:s3");

    expect(row(wrapper, "node:a1").attributes("aria-expanded")).toBe("true");
    expect(row(wrapper, "statement:s3").attributes("tabindex")).toBe("0");
  });

  it("shows, filtered by review status, the rows of those statuses and the nodes above, and says how many", async () => {
    const wrapper = tree();
    const status = wrapper.get("[role=status]");
    expect(status.text()).toBe("");

    await wrapper.findAll(".status-filter button")[1]?.trigger("click"); // confirmed
    expect(items(wrapper).map(([key]) => key)).toEqual(["node:a", "statement:s2"]);
    expect(status.text()).toBe("1 Zeile passt zum Filter.");

    await wrapper.findAll(".status-filter button")[2]?.trigger("click"); // and rejected
    expect(items(wrapper).map(([key]) => key)).toEqual(["node:a", "statement:s2", "node:b"]);
    expect(status.text()).toBe("2 Zeilen passen zum Filter.");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("opens the nodes above a row of the statuses chosen, though they were closed", async () => {
    const deep = statement_("deep", { review_status: CV + "rev_confirmed" });
    const wrapper = tree([node_("x", { children: [node_("x1", { statements: [deep] })] })]);
    expect(row(wrapper, "node:x1").attributes("aria-expanded")).toBe("false");

    await wrapper.findAll(".status-filter button")[1]?.trigger("click");

    expect(items(wrapper).map(([key, , open]) => [key, open])).toEqual([
      ["node:x", "true"],
      ["node:x1", "true"],
      ["statement:deep", "-"],
    ]);
  });

  it("says so where no row is of the statuses chosen", async () => {
    const wrapper = tree([node_("c")]);

    await wrapper.findAll(".status-filter button")[1]?.trigger("click");

    expect(wrapper.findAll("[role=treeitem]")).toHaveLength(0);
    expect(wrapper.get("[role=status]").text()).toBe("Keine Zeile passt zum Filter.");
  });

  it("says that it is empty where the extraction wrote no node", () => {
    const wrapper = tree([]);

    expect(wrapper.find("[role=tree]").exists()).toBe(false);
    expect(wrapper.text()).toContain("Noch keine Knoten");
  });
});
