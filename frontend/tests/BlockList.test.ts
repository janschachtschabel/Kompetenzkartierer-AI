import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setToken } from "@/api";
import BlockList from "@/components/BlockList.vue";
import { router } from "@/router";

import { violations } from "./axe";
import { block, cell } from "./conversions";

let shown: VueWrapper | null = null;

beforeEach(() => {
  setToken("kka_token"); // the pages are an account's
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

const RUNNING_ON = { id: "p2-b2", page: 2, cells: [cell("T1:r3c1", "Modellieren", { page: 3 })] };

async function list(cited?: ReadonlySet<string>): Promise<VueWrapper> {
  // a page that keeps more in its address than the page of the source - the tree, the row chosen
  await router.push({ name: "conversion", params: { id: "s1" }, query: { zeile: "node:a", seite: "3" } });
  shown = mount(BlockList, {
    props: { blocks: [block("p3-b1", "Erster"), block("p3-b2", "Zweiter")], continued: [RUNNING_ON], page: 3, cited },
    global: { plugins: [router] },
    attachTo: document.body,
  });
  return shown;
}

describe("a page's blocks", () => {
  it("mark the blocks a row's anchors name by a word as well as by its edge", async () => {
    const wrapper = await list(new Set(["p3-b2", "p2-b2"]));

    const items = wrapper.findAll(".block");
    expect(items.map((item) => item.classes("block--cited"))).toEqual([true, false, true]);
    expect(items.map((item) => item.find(".block__cited").exists() && item.get(".block__cited").text())).toEqual([
      "Beleg",
      false,
      "Beleg",
    ]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("mark none where no row is chosen", async () => {
    const wrapper = await list();

    expect(wrapper.findAll(".block--cited")).toHaveLength(0);
  });

  it("lead to the page a table begins on, keeping the rest of the address", async () => {
    const wrapper = await list();

    const href = wrapper.get(".block a").attributes("href") ?? "";
    expect(href).toContain("seite=2");
    expect(href).toContain("zeile=node");
  });
});
