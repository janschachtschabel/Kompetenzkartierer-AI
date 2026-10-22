/**
 * The frame every modal of the app shares (old app, review D of the round "Sichtung",
 * finding 8): the scrim, the dialog's role and name, Tab kept inside, Escape
 * and a click on the scrim to close, and the keyboard back where it came from.
 * What goes inside, and where the keyboard starts, is the dialog's own.
 */
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";

import ModalShell from "@/components/ModalShell.vue";

import { describeViolations, violations } from "./axe";

const mounted: VueWrapper[] = [];

function mountShell(props: Record<string, unknown> = {}) {
  const wrapper = mount(ModalShell, {
    props: { labelledby: "shell-title", ...props },
    slots: {
      default: () => [
        h("h2", { id: "shell-title" }, "Teilen"),
        h("p", { id: "shell-lead" }, "Wer liest mit?"),
        h("button", { type: "button", id: "first" }, "Erster"),
        h("button", { type: "button", id: "last" }, "Letzter"),
      ],
    },
    attachTo: document.body,
  });
  mounted.push(wrapper);
  return wrapper;
}

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
  document.body.innerHTML = "";
});

describe("ModalShell", () => {
  it("is a modal dialog named by the heading it is given, described where it is told", () => {
    const wrapper = mountShell({ describedby: "shell-lead" });

    const dialog = wrapper.get("[role='dialog']");
    expect(dialog.attributes("aria-modal")).toBe("true");
    expect(dialog.attributes("aria-labelledby")).toBe("shell-title");
    expect(dialog.attributes("aria-describedby")).toBe("shell-lead");
  });

  it("carries no description it was not given", () => {
    const wrapper = mountShell();

    expect(wrapper.get("[role='dialog']").attributes("aria-describedby")).toBeUndefined();
  });

  it("asks to close on Escape and on a click on the scrim, not on one inside", async () => {
    const wrapper = mountShell();

    await wrapper.get("[role='dialog']").trigger("keydown", { key: "Escape" });
    await wrapper.get("#first").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
    // a click as the browser sends it: press, release, click, all on the scrim
    await wrapper.get(".backdrop").trigger("mousedown");
    await wrapper.get(".backdrop").trigger("mouseup");
    await wrapper.get(".backdrop").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(2);
  });

  it("asks to close on Escape where the keyboard fell out of it, onto the page", () => {
    // A control that went away took the keyboard to the page's body, and
    // Escape, heard on the dialog alone, closed nothing (old app, review A2, pre-existing).
    const wrapper = mountShell();
    (document.activeElement as HTMLElement | null)?.blur();
    expect(document.activeElement).toBe(document.body);

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("closes only the topmost of two open frames on Escape", async () => {
    const under = mountShell();
    const over = mountShell();
    (over.get("#first").element as HTMLElement).focus();

    await over.get("[role='dialog']").trigger("keydown", { key: "Escape" });

    expect(over.emitted("close")).toHaveLength(1);
    expect(under.emitted("close")).toBeUndefined();
  });

  it("leaves Escape to the frame below once the one above is gone", () => {
    const under = mountShell();
    const over = mountShell();
    over.unmount();
    mounted.splice(mounted.indexOf(over), 1);

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(under.emitted("close")).toHaveLength(1);
  });

  it("leaves Escape to a modal question of another kind asked over it", () => {
    // ConfirmDialog answers Escape itself; the frame below stays open.
    const wrapper = mountShell();
    const question = document.createElement("div");
    question.setAttribute("role", "dialog");
    question.setAttribute("aria-modal", "true");
    const cancel = document.createElement("button");
    question.append(cancel);
    document.body.append(question);
    cancel.focus();

    cancel.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(wrapper.emitted("close")).toBeUndefined();
  });

  it("keeps the frame below on the stack when one above is gone before it was mounted", async () => {
    // Unmounted within the flush that mounted it, a frame never put itself on
    // the stack; taking it off by index -1 took another frame off instead
    // (recheck of the review fixes, 2026-10-18).
    const show = ref(false);
    const closed: string[] = [];
    const Vanishing = defineComponent({
      setup() {
        show.value = false;
        return () => h("button", "x");
      },
    });
    const Host = defineComponent({
      setup() {
        return () =>
          h("div", [
            h(ModalShell, { labelledby: "below", onClose: () => closed.push("below") }, () =>
              h("button", { id: "below" }, "below"),
            ),
            show.value ? h(ModalShell, { labelledby: "above" }, () => h(Vanishing)) : null,
          ]);
      },
    });
    const wrapper = mount(Host, { attachTo: document.body });
    await flushPromises();

    show.value = true;
    await flushPromises();
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(closed).toEqual(["below"]);
    wrapper.unmount();
  });

  it("stops listening for Escape once it is gone", () => {
    const wrapper = mountShell();
    wrapper.unmount();
    mounted.splice(mounted.indexOf(wrapper), 1);

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(wrapper.emitted("close")).toBeUndefined();
  });

  it("keeps Tab inside: from the last control to the first, and Shift+Tab back", async () => {
    const wrapper = mountShell();
    const dialog = wrapper.get("[role='dialog']");

    (wrapper.get("#last").element as HTMLElement).focus();
    await dialog.trigger("keydown", { key: "Tab" });
    expect(document.activeElement?.id).toBe("first");
    await dialog.trigger("keydown", { key: "Tab", shiftKey: true });
    expect(document.activeElement?.id).toBe("last");
  });

  it("gives the keyboard back to what opened it", async () => {
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();
    const Host = defineComponent({
      setup() {
        const open = ref(true);
        return () =>
          open.value
            ? h(ModalShell, { labelledby: "t", onClose: () => (open.value = false) }, () => [
                h("h2", { id: "t" }, "Frage"),
                h("button", { type: "button", id: "inside" }, "Drinnen"),
              ])
            : h("p", "zu");
      },
    });
    const host = mount(Host, { attachTo: document.body });
    mounted.push(host);
    (host.get("#inside").element as HTMLElement).focus();

    await host.get("[role='dialog']").trigger("keydown", { key: "Escape" });

    expect(host.find("[role='dialog']").exists()).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  it("passes axe", async () => {
    const wrapper = mountShell({ describedby: "shell-lead" });

    const found = await violations(wrapper.html());
    expect(found, describeViolations(found)).toEqual([]);
  });
});


describe("a text selection that ends on the scrim", () => {
  it("closes nothing: the click lands on the scrim, the press began inside", async () => {
    // selecting a dialog's text and letting go past its edge closed it, and what was typed went
    const wrapper = mount(ModalShell, {
      props: { labelledby: "t" },
      slots: { default: '<h2 id="t">Titel</h2><p id="text">Langer Text</p>' },
      attachTo: document.body,
    });

    // as the browser sends it: the release past the edge lands on the scrim, the press did not
    await wrapper.get("#text").trigger("mousedown");
    await wrapper.get(".backdrop").trigger("mouseup");
    await wrapper.get(".backdrop").trigger("click");

    expect(wrapper.emitted("close")).toBeUndefined();
    wrapper.unmount();
  });

  it("closes nothing the other way round either: pressed on the scrim, let go inside", async () => {
    const wrapper = mount(ModalShell, {
      props: { labelledby: "t" },
      slots: { default: '<h2 id="t">Titel</h2><p id="text">Langer Text</p>' },
      attachTo: document.body,
    });

    await wrapper.get(".backdrop").trigger("mousedown");
    await wrapper.get("#text").trigger("mouseup");
    await wrapper.get(".backdrop").trigger("click");

    expect(wrapper.emitted("close")).toBeUndefined();
    wrapper.unmount();
  });
});
