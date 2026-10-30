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

  it("lead to the first page too, where a table begins there, by naming it", async () => {
    // an address without its page is the first one on the blocks' page, the first anchor's on the tree's
    await router.push({ name: "conversion", params: { id: "s1" }, query: { zeile: "node:a", seite: "3" } });
    shown = mount(BlockList, {
      props: { blocks: [], continued: [{ ...RUNNING_ON, id: "p1-b4", page: 1 }], page: 3 },
      global: { plugins: [router] },
      attachTo: document.body,
    });

    const href = shown.get(".block a").attributes("href") ?? "";
    expect(href).toContain("seite=1");
    expect(href).not.toContain("seite=3");
  });

  it("lead to the page a table begins on, keeping the rest of the address", async () => {
    const wrapper = await list();

    const href = wrapper.get(".block a").attributes("href") ?? "";
    expect(href).toContain("seite=2");
    expect(href).toContain("zeile=node");
  });
});

describe("a page's blocks to choose an anchor from", () => {
  async function choosing(picked: ReadonlySet<string> = new Set()): Promise<VueWrapper> {
    await router.push({ name: "conversion", params: { id: "s1" } });
    shown = mount(BlockList, {
      props: {
        blocks: [block("p3-b1", "Erster"), block("p3-b2", "Zweiter")],
        continued: [RUNNING_ON],
        page: 3,
        picking: true,
        picked,
      },
      global: { plugins: [router] },
      attachTo: document.body,
    });
    return shown;
  }

  function toggles(wrapper: VueWrapper) {
    return wrapper.findAll(".block button");
  }

  it("offer each block, a table run on too, as a toggle named by its id, and say which are chosen", async () => {
    const wrapper = await choosing(new Set(["p2-b2", "p3-b2"]));

    expect(toggles(wrapper).map((button) => button.attributes("aria-label"))).toEqual([
      "Block p2-b2 als Fundstelle wählen",
      "Block p3-b1 als Fundstelle wählen",
      "Block p3-b2 als Fundstelle wählen",
    ]);
    expect(toggles(wrapper).map((button) => button.attributes("aria-pressed"))).toEqual(["true", "false", "true"]);
    // the visible words are in the name, the state not by colour alone
    expect(toggles(wrapper).map((button) => button.text())).toEqual(Array(3).fill("Als Fundstelle wählen"));
    expect(toggles(wrapper).map((button) => button.find("svg").exists())).toEqual([true, false, true]);
    expect(wrapper.findAll(".block").map((item) => item.classes("block--picked"))).toEqual([true, false, true]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("ask for a block to be chosen or let go by its id", async () => {
    const wrapper = await choosing();

    await toggles(wrapper)[2]?.trigger("click");
    await toggles(wrapper)[0]?.trigger("click");

    expect(wrapper.emitted("toggle")).toEqual([["p3-b2"], ["p2-b2"]]);
  });

  it("offer none while no anchor is chosen", async () => {
    const wrapper = await list();

    expect(toggles(wrapper)).toHaveLength(0);
  });
});
