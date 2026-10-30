import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import type { FormField } from "@/api";
import RowForm from "@/components/RowForm.vue";
import { draftOf, type Draft } from "@/rowDraft";

import { violations } from "./axe";
import { CV, SCHOOL, form_, value_ } from "./treeFixtures";

let shown: VueWrapper | null = null;
// the form's v-model, as the editor would hold it
let draft: Draft = {};

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

// a node's form whose node types hang under their functions
const FIELDS: FormField[] = form_().node.map((field) =>
  field.key === "node_type"
    ? {
        ...field,
        values: [
          value_(SCHOOL + "Inhaltsbereich", "Inhaltsbereich", { broader: [CV + "fn_area"] }),
          value_(SCHOOL + "Lernsequenz", "Lernsequenz", { broader: [CV + "fn_unit"] }),
        ],
      }
    : field,
);

function form(values: Record<string, string | null>, props: Record<string, unknown> = {}): VueWrapper {
  draft = draftOf(FIELDS, values);
  shown = mount(RowForm, {
    props: {
      fields: FIELDS,
      errors: {},
      saving: false,
      modelValue: draft,
      "onUpdate:modelValue": (next: Draft) => {
        draft = next;
        void shown?.setProps({ modelValue: next });
      },
      ...props,
    },
    attachTo: document.body,
  });
  return shown;
}

describe("a row's form", () => {
  it("shows the form's fields in its order, a list hanging under another offering the values under its choice", async () => {
    const wrapper = form({ original_title: "Optik", function: CV + "fn_unit" });

    expect(wrapper.findAll("label").map((label) => label.text())).toEqual([
      "Titel (Pflichtfeld)",
      "Funktion (Pflichtfeld)",
      "Knotentyp",
      "Code",
    ]);
    expect(wrapper.findAll("select")[1]?.findAll("option").map((option) => option.text())).toEqual([
      "keine Angabe",
      "Lernsequenz",
    ]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("gives back the draft with a field changed, the others as they were", async () => {
    const wrapper = form({ original_title: "Optik", function: CV + "fn_area", code: "1" });

    await wrapper.get("input").setValue("Licht");

    expect(draft).toEqual({ original_title: "Licht", function: CV + "fn_area", node_type: "", code: "1" });
  });

  it("asks to save by a button that names what it does, and not again while it saves", async () => {
    const wrapper = form({ original_title: "Optik" });

    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("submit")).toHaveLength(1);
    expect(wrapper.get("button[type=submit]").text()).toBe("Änderungen speichern");

    await wrapper.setProps({ saving: true });
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("button[type=submit]").attributes("aria-disabled")).toBe("true");
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("states each problem at its field, and takes the focus to a field when asked", async () => {
    const wrapper = form({ original_title: "" }, { errors: { original_title: "Dieses Feld braucht einen Wert." } });

    expect(wrapper.findAll(".field__error").map((error) => error.text())).toEqual(["Dieses Feld braucht einen Wert."]);
    expect(wrapper.get("input").attributes("aria-invalid")).toBe("true");
    (wrapper.vm as unknown as { focusField: (key: string) => void }).focusField("code");
    expect(document.activeElement).toBe(wrapper.findAll("input")[1]?.element);
    expect(await violations(wrapper.html())).toEqual([]);
  });
});
