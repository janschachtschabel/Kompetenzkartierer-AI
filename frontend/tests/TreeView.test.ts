import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import TreeView from "@/components/TreeView.vue";
import { rowsOf, type RowKey } from "@/documentTree";

import { violations } from "./axe";
import { CV, SCHOOL, form_, node_, statement_, value_ } from "./treeFixtures";

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
    // a row's name says what it is first, its parts apart; the arrow is no part of it
    expect(row(wrapper, "node:a").attributes("aria-label")).toBe(
      "Knoten, LF 1, Optik, Inhaltsbereich, Vorgeschlagen, 2 Befunde",
    );
    expect(row(wrapper, "statement:s1").attributes("aria-label")).toBe("Aussage, Sie messen., Lernergebnis, Vorgeschlagen");
    expect(row(wrapper, "node:b").attributes("aria-label")).toBe("Knoten, LF 2, ohne Titel, Verworfen");
  });

  it("goes through its rows with the keys, opens and closes nodes, and chooses one with Enter", async () => {
    const wrapper = tree();
    (row(wrapper, "node:a").element as HTMLElement).focus();

    await press(wrapper, "ArrowDown");
    expect(document.activeElement?.getAttribute("data-key")).toBe("statement:s1");
    // the tab stop goes along: one row holds it
    expect(items(wrapper).filter(([, , , tabindex]) => tabindex === "0").map(([key]) => key)).toEqual(["statement:s1"]);
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
    expect(wrapper.findAll("[aria-selected]")).toHaveLength(1); // the others say nothing of it
    expect(items(wrapper).filter(([, , , tabindex]) => tabindex === "0").map(([key]) => key)).toEqual(["node:a1"]);
  });

  it("chooses a row clicked, and opens or closes a node by its arrow without choosing it", async () => {
    const wrapper = tree();

    await row(wrapper, "statement:s2").trigger("click");
    expect(selected).toBe("statement:s2");
    await row(wrapper, "node:a1").get(".tree__toggle").trigger("click");

    expect(row(wrapper, "node:a1").attributes("aria-expanded")).toBe("true");
    expect(selected).toBe("statement:s2");
  });

  it("leaves the keys at the row whose arrow was clicked; the arrow is the mouse's alone", async () => {
    const wrapper = tree();
    expect(row(wrapper, "node:a1").get(".tree__toggle").attributes("aria-hidden")).toBe("true");
    expect(row(wrapper, "node:a1").find("button").exists()).toBe(false);

    await row(wrapper, "node:a1").get(".tree__toggle").trigger("click");
    await nextTick();
    expect(document.activeElement?.getAttribute("data-key")).toBe("node:a1");
    await press(wrapper, "ArrowDown");

    expect(document.activeElement?.getAttribute("data-key")).toBe("statement:s3");
  });

  it("goes from the row a key is pressed on, and leaves keys with Alt, Ctrl or Meta to the browser", async () => {
    const wrapper = tree();
    (row(wrapper, "statement:s2").element as HTMLElement).focus();

    await row(wrapper, "statement:s2").trigger("keydown", { key: "ArrowUp" });
    await nextTick();
    expect(document.activeElement?.getAttribute("data-key")).toBe("statement:s1");

    for (const modifier of ["altKey", "ctrlKey", "metaKey"]) {
      const back = new KeyboardEvent("keydown", { key: "ArrowLeft", [modifier]: true, bubbles: true, cancelable: true });
      row(wrapper, "node:a").element.dispatchEvent(back);
      await nextTick();
      expect(back.defaultPrevented, modifier).toBe(false);
      expect(row(wrapper, "node:a").attributes("aria-expanded"), modifier).toBe("true");
    }
  });

  it("goes from the row focused though a row was chosen from without meanwhile, as by the browser's back", async () => {
    const wrapper = tree();
    (row(wrapper, "statement:s2").element as HTMLElement).focus();
    await wrapper.setProps({ selected: "node:b" });

    await row(wrapper, "statement:s2").trigger("keydown", { key: "ArrowUp" });
    await nextTick();

    expect(document.activeElement?.getAttribute("data-key")).toBe("statement:s1");
  });

  it("says the choice is the row's it moved to, the one before no longer", async () => {
    const wrapper = tree();
    await row(wrapper, "statement:s1").trigger("click");
    (row(wrapper, "statement:s1").element as HTMLElement).focus();

    await press(wrapper, "ArrowDown");
    await press(wrapper, "Enter");

    expect(selected).toBe("statement:s2");
    expect(wrapper.findAll("[aria-selected]").map((item) => item.attributes("data-key"))).toEqual(["statement:s2"]);
  });

  it("names its rows anew by another form", async () => {
    const wrapper = tree();
    const other = form_();
    other.node = other.node.map((field) =>
      field.key === "node_type"
        ? { ...field, values: [value_(SCHOOL + "Inhaltsbereich", "Inhaltsfeld", { broader: [CV + "fn_area"] })] }
        : field,
    );

    await wrapper.setProps({ form: other });

    expect(row(wrapper, "node:a").attributes("aria-label")).toContain("Inhaltsfeld");
    expect(row(wrapper, "node:a").text()).toContain("Inhaltsfeld");
  });

  it("goes to the first row with Home and chooses with Space", async () => {
    const wrapper = tree();
    (row(wrapper, "node:a1").element as HTMLElement).focus();

    await row(wrapper, "node:a1").trigger("keydown", { key: "Home" });
    await nextTick();
    expect(document.activeElement?.getAttribute("data-key")).toBe("node:a");
    await row(wrapper, "node:a").trigger("keydown", { key: " " });

    expect(selected).toBe("node:a");
  });

  it("puts the tab stop on a row chosen from without, wherever the keys were", async () => {
    const wrapper = tree();
    (row(wrapper, "statement:s2").element as HTMLElement).focus();

    await wrapper.setProps({ selected: "node:b" });

    expect(row(wrapper, "node:b").attributes("tabindex")).toBe("0");
  });

  it("keeps what is open and the filter when it is read again", async () => {
    const wrapper = tree();
    await row(wrapper, "node:a1").get(".tree__toggle").trigger("click");

    await wrapper.setProps({ rows: rowsOf(NODES) });
    expect(row(wrapper, "node:a1").attributes("aria-expanded")).toBe("true"); // no filter that would open it
    await wrapper.findAll(".status-filter button")[0]?.trigger("click"); // proposed
    await wrapper.setProps({ rows: rowsOf(NODES) });

    expect(wrapper.get(".status-filter button").attributes("aria-pressed")).toBe("true");
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

  it("gives back, with the filter off, the nodes open before it", async () => {
    const deep = statement_("deep", { review_status: CV + "rev_confirmed" });
    const wrapper = tree([node_("x", { children: [node_("x1", { statements: [deep] })] })]);

    await wrapper.findAll(".status-filter button")[1]?.trigger("click");
    expect(row(wrapper, "node:x1").attributes("aria-expanded")).toBe("true");
    await wrapper.findAll(".status-filter button")[1]?.trigger("click");

    expect(row(wrapper, "node:x1").attributes("aria-expanded")).toBe("false");
  });

  it("keeps, with the filter off, the way to a row chosen under it open", async () => {
    const deep = statement_("deep", { review_status: CV + "rev_confirmed" });
    const wrapper = tree([node_("x", { children: [node_("x1", { statements: [deep] })] })]);
    await wrapper.findAll(".status-filter button")[1]?.trigger("click"); // confirmed
    await row(wrapper, "statement:deep").trigger("click");

    await wrapper.findAll(".status-filter button")[1]?.trigger("click");

    expect(items(wrapper).map(([key]) => key)).toEqual(["node:x", "node:x1", "statement:deep"]);
    expect(row(wrapper, "statement:deep").attributes("tabindex")).toBe("0");
  });

  it("opens the way to a row of the statuses chosen that a new reading brings", async () => {
    const wrapper = tree([node_("x", { children: [node_("x1")] })]);
    await wrapper.findAll(".status-filter button")[1]?.trigger("click"); // confirmed: none yet

    const deep = statement_("deep", { review_status: CV + "rev_confirmed" });
    await wrapper.setProps({ rows: rowsOf([node_("x", { children: [node_("x1", { statements: [deep] })] })]) });

    expect(items(wrapper).map(([key]) => key)).toEqual(["node:x", "node:x1", "statement:deep"]);
  });

  it("says so where no row is of the statuses chosen, and shows no empty tree", async () => {
    const wrapper = tree([node_("c")]);

    await wrapper.findAll(".status-filter button")[1]?.trigger("click");

    expect(wrapper.find("[role=tree]").exists()).toBe(false);
    expect(wrapper.get("[role=status]").text()).toBe("Keine Zeile passt zum Filter.");
  });

  it("says that it is empty where the extraction wrote no node", () => {
    const wrapper = tree([]);

    expect(wrapper.find("[role=tree]").exists()).toBe(false);
    expect(wrapper.text()).toContain("Noch keine Knoten");
    expect(wrapper.find(".status-filter").exists()).toBe(false); // nothing to filter
  });
});
