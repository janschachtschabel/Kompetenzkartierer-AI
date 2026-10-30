import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import type { FormField } from "@/api";
import FormFieldInput from "@/components/FormFieldInput.vue";

import { violations } from "./axe";
import { CV, form_ } from "./treeFixtures";

let shown: VueWrapper | null = null;
// the field's v-model, as the form would hold it
let model: string | string[] = "";

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

function field(key: string): FormField {
  const found = [...form_().node, ...form_().statement].find((item) => item.key === key);
  if (!found) throw new Error(key);
  return found;
}

function input(of: FormField, value: string | string[], error: string | null = null): VueWrapper {
  model = value;
  shown = mount(FormFieldInput, {
    props: {
      field: of,
      values: of.values ?? [],
      error,
      modelValue: value,
      "onUpdate:modelValue": (next: string | string[]) => {
        model = next;
        void shown?.setProps({ modelValue: next });
      },
    },
    attachTo: document.body,
  });
  return shown;
}

describe("a field of a row's form", () => {
  it("edits a text in a box as long as the form allows, its label saying it is required", async () => {
    const wrapper = input(field("original_title"), "Optik");
    const box = wrapper.get("input");

    expect(wrapper.get("label").text()).toBe("Titel (Pflichtfeld)");
    expect(wrapper.get("label").attributes("for")).toBe(box.attributes("id"));
    expect(box.attributes("maxlength")).toBe("2000");
    await box.setValue("Licht");
    expect(model).toBe("Licht");
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("edits a long text in a text area, an optional field's label saying nothing more", () => {
    const wrapper = input({ ...field("levelText"), kind: "longtext" }, "Stufe 2");

    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("Stufe 2");
    expect(wrapper.get("label").text()).toBe("Niveau im Wortlaut");
  });

  it("chooses one value from a list by its label, an optional list offering none", async () => {
    const wrapper = input(field("node_type"), "");
    const options = wrapper.findAll("option").map((option) => [option.attributes("value"), option.text()]);

    expect(options).toEqual([
      ["", "keine Angabe"],
      ["https://w3id.org/wlo/curriculum/profile/school#Inhaltsbereich", "Inhaltsbereich"],
    ]);
    await wrapper.get("select").setValue("https://w3id.org/wlo/curriculum/profile/school#Inhaltsbereich");
    expect(model).toBe("https://w3id.org/wlo/curriculum/profile/school#Inhaltsbereich");
    expect(wrapper.findAll("option")[0]?.text()).toBe("keine Angabe"); // chosen, it can be cleared again
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("asks a required list to be chosen while it is empty, and offers no empty choice once one is", () => {
    expect(input(field("function"), "").findAll("option")[0]?.text()).toBe("Bitte wählen");
    shown?.unmount();

    expect(input(field("function"), CV + "fn_area").findAll("option").map((option) => option.text())).toEqual([
      "Bereich",
      "Einheit",
    ]);
  });

  it("keeps a value the form does not know as a choice of its own, so that saving does not drop it", () => {
    const wrapper = input(field("function"), "urn:retired");

    expect(wrapper.findAll("option").at(-1)?.text()).toBe("unbekannt: urn:retired");
    expect((wrapper.get("select").element as HTMLSelectElement).value).toBe("urn:retired");
  });

  it("chooses several values of a list by boxes in a group named by the field", async () => {
    const wrapper = input(field("addressees"), [CV + "addr_learner", "urn:retired"]);

    expect(wrapper.get("fieldset legend").text()).toBe("Adressaten (Pflichtfeld)");
    expect(wrapper.findAll("input[type=checkbox]").map((box) => (box.element as HTMLInputElement).checked)).toEqual([
      true,
      false,
      true,
    ]);
    expect(wrapper.findAll("fieldset label").map((label) => label.text())).toEqual([
      "Lernende",
      "Lehrkräfte",
      "unbekannt: urn:retired",
    ]);
    await wrapper.findAll("input[type=checkbox]")[1]?.setValue(true);
    expect(model).toEqual([CV + "addr_learner", "urn:retired", CV + "addr_educator"]);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("says a problem at its field, tied to the control, not by colour alone", () => {
    const wrapper = input(field("original_title"), "", "Dieses Feld braucht einen Wert.");
    const error = wrapper.get(".field__error");

    expect(error.text()).toBe("Dieses Feld braucht einen Wert.");
    expect(error.find("svg").exists()).toBe(true);
    expect(wrapper.get("input").attributes("aria-invalid")).toBe("true");
    expect(wrapper.get("input").attributes("aria-describedby")).toBe(error.attributes("id"));
  });

  it("ties a problem of a list of many to its group", async () => {
    const wrapper = input(field("addressees"), [], "Dieses Feld braucht einen Wert.");

    expect(wrapper.get("fieldset").attributes("aria-describedby")).toBe(wrapper.get(".field__error").attributes("id"));
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("takes the focus when asked, at its control or its group's first box", () => {
    const text = input(field("original_title"), "");
    (text.vm as unknown as { focus: () => void }).focus();
    expect(document.activeElement).toBe(text.get("input").element);
    shown?.unmount();

    const boxes = input(field("addressees"), []);
    (boxes.vm as unknown as { focus: () => void }).focus();
    expect(document.activeElement).toBe(boxes.get("input[type=checkbox]").element);
  });
});
