import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import AnchorDraftList from "@/components/AnchorDraftList.vue";
import { t } from "@/i18n/de";

import { violations } from "./axe";

let shown: VueWrapper | null = null;

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

function list(codes: string[], error: string | null = null): VueWrapper {
  shown = mount(AnchorDraftList, { props: { codes, error }, attachTo: document.body });
  return shown;
}

function removers(wrapper: VueWrapper) {
  return wrapper.findAll("li button");
}

describe("the anchors of a statement's draft", () => {
  it("says each in words, with a button to remove it that names which", async () => {
    const wrapper = list(["blocks:p5-b2,p5-b3", "page:7"]);

    expect(wrapper.get("h3").text()).toBe(t("documents.tree.anchors.draftHeading"));
    expect(wrapper.findAll("li span").map((item) => item.text())).toEqual(["Seite 5: 2 Blöcke (p5-b2, p5-b3)", "Auf Seite 7 nicht gefunden"]);
    expect(removers(wrapper).map((button) => button.text())).toEqual(["Entfernen", "Entfernen"]);
    const described = removers(wrapper).map((button) => {
      const id = button.attributes("aria-describedby") ?? "";
      return document.getElementById(id)?.textContent?.trim();
    });
    expect(described).toEqual(["Seite 5: 2 Blöcke (p5-b2, p5-b3)", "Auf Seite 7 nicht gefunden"]);
    expect(removers(wrapper).every((button) => button.attributes("type") === "button")).toBe(true);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("asks for an anchor to be removed, the keyboard going on to the one in its place", async () => {
    const wrapper = list(["blocks:p5-b2", "page:7", "page:8"]);

    await removers(wrapper)[1]?.trigger("click");
    expect(wrapper.emitted("remove")).toEqual([["page:7"]]);
    await wrapper.setProps({ codes: ["blocks:p5-b2", "page:8"] });
    await nextTick();
    expect(document.activeElement).toBe(removers(wrapper)[1]?.element);

    // the last one: to the one before
    await removers(wrapper)[1]?.trigger("click");
    await wrapper.setProps({ codes: ["blocks:p5-b2"] });
    await nextTick();
    expect(document.activeElement).toBe(removers(wrapper)[0]?.element);

    // none left: to the list
    await removers(wrapper)[0]?.trigger("click");
    await wrapper.setProps({ codes: [] });
    await nextTick();
    expect(document.activeElement).toBe(wrapper.get("section").element);
  });

  it("leaves the keyboard where it is when an anchor comes from elsewhere", async () => {
    const outside = document.createElement("button");
    document.body.append(outside);
    outside.focus();
    const wrapper = list(["page:7"]);

    await wrapper.setProps({ codes: ["page:7", "blocks:p5-b2"] });
    await nextTick();

    expect(document.activeElement).toBe(outside);
  });

  it("tells two anchors of as many blocks on one page apart, by their blocks", () => {
    const wrapper = list(["blocks:p5-b2", "blocks:p5-b7"]);

    expect(wrapper.findAll("li span").map((item) => item.text())).toEqual(["Seite 5: 1 Block (p5-b2)", "Seite 5: 1 Block (p5-b7)"]);
  });

  it("says how to choose one where there is none", async () => {
    const wrapper = list([]);

    expect(wrapper.find("ul").exists()).toBe(false);
    expect(wrapper.text()).toContain(t("documents.tree.anchors.draftNone"));
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("states a problem of the anchors under them, the list described by it", async () => {
    const wrapper = list(["blocks:p5-b2"], "Ein Block, den die Umwandlung nicht hat.");

    const error = wrapper.get(".field__error");
    expect(error.text()).toBe("Ein Block, den die Umwandlung nicht hat.");
    expect(error.find("svg").exists()).toBe(true); // not by colour alone
    expect(wrapper.get("section").attributes("aria-describedby")).toBe(error.attributes("id"));
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("takes the keyboard when asked, and is described by nothing without a problem", () => {
    const wrapper = list(["page:7"]);

    (wrapper.vm as unknown as { focus: () => void }).focus();

    expect(document.activeElement).toBe(wrapper.get("section").element);
    expect(wrapper.get("section").attributes("aria-describedby")).toBeUndefined();
  });
});
