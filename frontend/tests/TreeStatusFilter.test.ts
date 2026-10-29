import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import TreeStatusFilter from "@/components/TreeStatusFilter.vue";

import { violations } from "./axe";
import { CV } from "./treeFixtures";

let shown: VueWrapper | null = null;
// the filter's v-model, as the view would hold it
let model = new Set<string>();

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

const COUNTS = {
  nodes: { [CV + "rev_proposed"]: 3, [CV + "rev_confirmed"]: 1, [CV + "rev_rejected"]: 0 },
  statements: { [CV + "rev_proposed"]: 10, [CV + "rev_confirmed"]: 1, [CV + "rev_rejected"]: 0 },
};

function filter(selected: Set<string> = new Set()): VueWrapper {
  model = selected;
  shown = mount(TreeStatusFilter, {
    props: {
      counts: COUNTS,
      modelValue: selected,
      "onUpdate:modelValue": (next: Set<string>) => {
        model = next;
        void shown?.setProps({ modelValue: next });
      },
    },
    attachTo: document.body,
  });
  return shown;
}

function toggles(wrapper: VueWrapper): [string, string | undefined][] {
  return wrapper.findAll("button").map((button) => [button.text(), button.attributes("aria-pressed")]);
}

describe("the tree's filter by review status", () => {
  it("offers every status with its nodes and statements in the whole document, at nought too", async () => {
    const wrapper = filter();

    expect(wrapper.get("[role=group]").attributes("aria-label")).toBe("Nach Prüfstand filtern");
    expect(toggles(wrapper)).toEqual([
      ["Vorgeschlagen: 3 Knoten, 10 Aussagen", "false"],
      ["Bestätigt: 1 Knoten, 1 Aussage", "false"],
      ["Verworfen: 0 Knoten, 0 Aussagen", "false"],
    ]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("turns statuses on and off, several at once, and all of them off again", async () => {
    const wrapper = filter();

    await wrapper.findAll("button")[1]?.trigger("click");
    await wrapper.findAll("button")[2]?.trigger("click");

    expect(model).toEqual(new Set([CV + "rev_confirmed", CV + "rev_rejected"]));
    expect(toggles(wrapper).map(([, pressed]) => pressed)).toEqual(["false", "true", "true", undefined]);
    expect(await violations(wrapper.html())).toEqual([]);

    await wrapper.findAll("button")[1]?.trigger("click");
    expect(model).toEqual(new Set([CV + "rev_rejected"]));
    (wrapper.get("button:last-of-type").element as HTMLElement).focus();
    await wrapper.get("button:last-of-type").trigger("click");
    expect(model).toEqual(new Set());
    expect(toggles(wrapper)).toHaveLength(3); // "all" is offered only while a status is on
    await nextTick();
    expect(document.activeElement).toBe(wrapper.findAll("button")[0]?.element); // not the page's top
  });
});
