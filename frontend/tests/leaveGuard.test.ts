import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";
import { createMemoryHistory, createRouter, RouterView, type Router } from "vue-router";

import { useLeaveGuard } from "@/leaveGuard";

// a page that holds a draft, and asks about it as the guard says
const dirty = ref(false);
let guard: ReturnType<typeof useLeaveGuard> | null = null;
const Page = defineComponent({
  setup() {
    guard = useLeaveGuard(dirty);
    return () => h("p", "page");
  },
});
const Elsewhere = defineComponent({ render: () => h("p", "elsewhere") });

let shown: VueWrapper | null = null;

async function at(path: string): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/page/:id", component: Page },
      { path: "/elsewhere", component: Elsewhere },
    ],
  });
  await router.push(path);
  shown = mount(RouterView, { global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return router;
}

function unloadAsks(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

afterEach(() => {
  shown?.unmount();
  shown = null;
  guard = null;
  dirty.value = false;
});

describe("the guard of a draft", () => {
  it("lets every move pass while there is no draft", async () => {
    const router = await at("/page/1");

    await router.push("/elsewhere");

    expect(router.currentRoute.value.path).toBe("/elsewhere");
    expect(unloadAsks()).toBe(false);
  });

  it("asks before a draft goes with another path, staying where the answer is to stay", async () => {
    const router = await at("/page/1");
    dirty.value = true;

    void router.push("/page/2");
    await flushPromises();
    expect(guard?.leaving.value).toBe(true);
    guard?.answer(false);
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/page/1");

    void router.push("/elsewhere");
    await flushPromises();
    guard?.answer(true);
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/elsewhere");
  });

  it("lets a move of the query alone pass, the page's own business by default", async () => {
    const router = await at("/page/1");
    dirty.value = true;

    await router.push("/page/1?x=1");

    expect([router.currentRoute.value.fullPath, guard?.leaving.value]).toEqual(["/page/1?x=1", false]);
  });

  it("asks before the browser's back takes the draft, and stays where the answer is to stay", async () => {
    const router = await at("/page/1");
    await router.push("/page/2"); // a step back to go
    dirty.value = true;

    router.back();
    await flushPromises();
    expect(guard?.leaving.value).toBe(true);
    guard?.answer(false);
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/page/2");
  });

  it("refuses a second back while it asks, and goes where the first was to go once the draft is to go", async () => {
    const router = await at("/page/1");
    await router.push("/page/2");
    await router.push("/page/3");
    dirty.value = true;

    router.back();
    await flushPromises();
    router.back(); // a second press while the question is open
    await flushPromises();
    guard?.answer(true);
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/page/2");
    expect(router.options.history.location).toBe("/page/2");
    // followed where the back already moved the history, not pushed anew: one more back goes on back
    dirty.value = false;
    router.back();
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/page/1");
  });

  it("lets the browser ask before the tab closes while a draft is open, and no more once the page is gone", async () => {
    const router = await at("/page/1");
    dirty.value = true;
    expect(unloadAsks()).toBe(true);

    void router.push("/elsewhere");
    await flushPromises();
    guard?.answer(true);
    await flushPromises();

    expect(unloadAsks()).toBe(false); // the page unmounted took its listener along
  });
});
