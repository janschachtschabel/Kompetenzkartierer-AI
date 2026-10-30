import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { effectScope, nextTick, ref } from "vue";

import { useAnchorPick } from "@/anchorPick";
import AnchorPickBar from "@/components/AnchorPickBar.vue";
import BlockToggle from "@/components/BlockToggle.vue";

import { violations } from "./axe";

let shown: VueWrapper | null = null;

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("choosing an anchor's blocks", () => {
  it("takes none while none is chosen, and the blocks chosen as one anchor once they are", async () => {
    const page = ref(3);
    const scope = effectScope();
    const pick = scope.run(() => useAnchorPick([page]));
    if (!pick) throw new Error("no scope");

    expect(pick.take()).toBeNull();
    pick.toggle("p3-b2");
    pick.toggle("p3-b1");
    expect(pick.take()).toBe("blocks:p3-b1,p3-b2");
    expect(pick.picked.value.size).toBe(0);

    pick.toggle("p3-b1");
    page.value = 4;
    await nextTick();
    expect(pick.picked.value.size).toBe(0);
    scope.stop();
  });

  it("offers to take the blocks chosen only while there are some", async () => {
    shown = mount(AnchorPickBar, { props: { count: 0, page: 3 }, attachTo: document.body });

    await shown.get("[data-test=take]").trigger("click");
    expect(shown.emitted("take")).toBeUndefined();
    await shown.setProps({ count: 2 });
    await shown.get("[data-test=take]").trigger("click");
    await shown.get("[data-test=not-found]").trigger("click");

    expect(shown.emitted("take")).toEqual([[]]);
    expect(shown.emitted("notFound")).toEqual([[]]);
    expect(await violations(shown.html())).toEqual([]);
  });

  it("toggles a block by its id, its state not by colour alone", async () => {
    shown = mount(BlockToggle, { props: { id: "p3-b2", pressed: true }, attachTo: document.body });

    await shown.get("button").trigger("click");

    expect(shown.get("button").attributes()).toMatchObject({
      type: "button",
      "aria-pressed": "true",
      "aria-label": "Block p3-b2 als Fundstelle wählen",
    });
    expect(shown.find("svg").exists()).toBe(true);
    expect(shown.emitted("toggle")).toEqual([[]]);
    await shown.setProps({ pressed: false });
    expect([shown.get("button").attributes("aria-pressed"), shown.find("svg").exists()]).toEqual(["false", false]);
    expect(await violations(shown.html())).toEqual([]);
  });
});
