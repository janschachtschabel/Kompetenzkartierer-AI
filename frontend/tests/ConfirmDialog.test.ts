import { readFileSync } from "node:fs";
import { join } from "node:path";

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { messages } from "@/i18n/de";

function open() {
  // Attached to the document, otherwise focus() is a no-op in jsdom.
  return mount(ConfirmDialog, {
    props: { title: "Konto löschen", message: "Wirklich?" },
    attachTo: document.body,
  });
}

describe("ConfirmDialog", () => {
  it("is announced as a modal dialog named by its heading", () => {
    const wrapper = open();
    const dialog = wrapper.get("[role='dialog']");

    expect(dialog.attributes("aria-modal")).toBe("true");
    expect(dialog.attributes("aria-labelledby")).toBe("confirm-title");
    expect(wrapper.get("#confirm-title").text()).toBe("Konto löschen");

    wrapper.unmount();
  });

  it("puts focus on the harmless choice, not on the destructive one", async () => {
    const wrapper = open();
    await wrapper.vm.$nextTick();

    const focused = document.activeElement as HTMLElement;

    expect(focused.textContent?.trim()).toBe(messages.dialog.cancel);
    wrapper.unmount();
  });

  it("gives focus back to whatever opened it", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();

    const wrapper = open();
    await wrapper.vm.$nextTick();
    expect(document.activeElement).not.toBe(trigger);

    wrapper.unmount();

    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it("cancels on Escape", async () => {
    const wrapper = open();

    await wrapper.get("[role='dialog']").trigger("keydown", { key: "Escape" });

    expect(wrapper.emitted("cancel")).toHaveLength(1);
    expect(wrapper.emitted("confirm")).toBeUndefined();
    wrapper.unmount();
  });

  it("keeps Tab inside the dialog", async () => {
    const wrapper = open();
    await wrapper.vm.$nextTick();
    const buttons = wrapper.findAll("[role='dialog'] button");
    const last = buttons[buttons.length - 1];
    (last.element as HTMLElement).focus();

    await wrapper.get("[role='dialog']").trigger("keydown", { key: "Tab" });

    expect(document.activeElement).toBe(buttons[0].element);
    wrapper.unmount();
  });

  it("reports each choice exactly once", async () => {
    const wrapper = open();

    await wrapper.get("[data-test='confirm']").trigger("click");

    expect(wrapper.emitted("confirm")).toHaveLength(1);
    wrapper.unmount();
  });
});

describe("ConfirmDialog with a disabled confirm", () => {
  it("keeps Tab inside the dialog when the confirm button cannot take focus", async () => {
    const wrapper = mount(ConfirmDialog, {
      props: { title: "Frage", message: "Text", confirmDisabled: true },
      slots: { default: '<input id="inside" />' },
      attachTo: document.body,
    });
    await wrapper.vm.$nextTick();
    // Cancel is the last button that can take focus; Tab from it must land
    // on the first focusable, not leave the dialog past the disabled button.
    (wrapper.get("[data-test='cancel']").element as HTMLElement).focus();

    await wrapper.get("[role='dialog']").trigger("keydown", { key: "Tab" });

    expect((document.activeElement as HTMLElement).id).toBe("inside");
    wrapper.unmount();
  });
});

describe("ConfirmDialog for a question whose first step is a choice", () => {
  it("is described by its sentence alone, unless the question names more", () => {
    const plain = open();
    const described = mount(ConfirmDialog, {
      props: { title: "Frage", message: "Text", describedBy: "hint" },
      slots: { default: '<p id="hint">Erst wählen.</p>' },
    });

    expect(plain.get("[role='dialog']").attributes("aria-describedby")).toBe("confirm-message");
    expect(described.get("[role='dialog']").attributes("aria-describedby")).toBe("confirm-message hint");
    plain.unmount();
  });

  it("puts focus on the first choice rather than on Cancel when asked to", async () => {
    const wrapper = mount(ConfirmDialog, {
      props: { title: "Frage", message: "Text", focusFirst: true, danger: false, confirmDisabled: true },
      slots: { default: '<input id="first" type="checkbox" /><input id="second" type="checkbox" />' },
      attachTo: document.body,
    });
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();

    expect((document.activeElement as HTMLElement).id).toBe("first");
    wrapper.unmount();
  });
});

describe("ConfirmDialog on a small screen", () => {
  it("never grows past the viewport, and scrolls what does not fit", () => {
    // The batch enrichment asks with up to thirteen options; the dialog had no
    // height limit, so on a phone or at 200% zoom its buttons sat below the
    // screen with no way to reach them (old app, audit 2026-09-26, E-54). jsdom lays
    // nothing out, so the rule itself is what is checked - in the frame it sits in.
    const source = readFileSync(join(process.cwd(), "src", "components", "ModalShell.vue"), "utf8");
    const rule = /\n\.dialog \{([^}]*)\}/.exec(source)?.[1] ?? "";

    expect(rule).toMatch(/max-height:\s*calc\(100dvh/);
    expect(rule).toMatch(/overflow-y:\s*auto/);
  });
});


describe("ConfirmDialog's confirm button", () => {
  it("is the destructive one unless the question says otherwise", () => {
    // it asks before something is removed: its default word is the catalogue's "Löschen"
    const plain = open();
    const adding = mount(ConfirmDialog, { props: { title: "Frage", message: "Text", danger: false } });

    expect(plain.get("[data-test='confirm']").classes()).toEqual(expect.arrayContaining(["btn", "danger"]));
    expect(adding.get("[data-test='confirm']").classes()).toEqual(expect.arrayContaining(["btn", "primary"]));
    plain.unmount();
    adding.unmount();
  });
});

describe("ConfirmDialog in its frame", () => {
  it("cancels on Escape after a click on its text left the keyboard on the page's body", async () => {
    const wrapper = open();
    await wrapper.vm.$nextTick();
    (document.activeElement as HTMLElement | null)?.blur();

    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(wrapper.emitted("cancel")).toHaveLength(1);
    wrapper.unmount();
  });
});
