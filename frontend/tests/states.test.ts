// The four states a data view has besides "all here": loading, empty, failed,
// and partly there.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";
import { t } from "@/i18n/de";

describe("the loading state", () => {
  it("says so politely, in its own words or the general ones", () => {
    const general = mount(LoadingState);
    const own = mount(LoadingState, { props: { label: "Lehrpläne werden geladen …" } });

    expect(general.attributes("role")).toBe("status");
    expect(general.text()).toBe(t("states.loading"));
    expect(own.text()).toBe("Lehrpläne werden geladen …");
  });
});

describe("the empty state", () => {
  it("says what would be here at the heading level it is given", () => {
    const wrapper = mount(EmptyState, { props: { title: "Noch nichts da", body: "Leg den ersten an.", level: 3 } });

    expect(wrapper.get("h3").text()).toBe("Noch nichts da");
    expect(wrapper.text()).toContain("Leg den ersten an.");
  });
});

describe("the error state", () => {
  it("alerts with the sentence and the reason, and offers to try again", async () => {
    const wrapper = mount(ErrorState, { props: { message: "Nicht geladen.", reason: "database away" } });

    expect(wrapper.attributes("role")).toBe("alert");
    expect(wrapper.get("q").attributes("lang")).toBe("en");
    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("retry")).toHaveLength(1);
  });
});

describe("the partial state", () => {
  it("says what is missing beside what is shown, without interrupting", () => {
    // Part of the page is there; a status, not an alert: nothing stopped working.
    const wrapper = mount(PartialState, {
      props: { notice: { text: "Ein Teil fehlt.", explanation: "Die Suche antwortet gerade nicht." } },
    });

    expect(wrapper.attributes("role")).toBe("status");
    expect(wrapper.text()).toContain("Ein Teil fehlt. Die Suche antwortet gerade nicht.");
    expect(wrapper.find("button").exists()).toBe(false);
  });

  it("is in the page before it has anything to say, so its first word is read out", () => {
    // a live region inserted together with its text is often not read
    const wrapper = mount(PartialState, { props: { notice: null, retry: true } });

    expect(wrapper.attributes("role")).toBe("status");
    expect(wrapper.text()).toBe("");
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.classes()).not.toContain("page-notice");
  });

  it("offers to fetch the rest where the page can", async () => {
    const wrapper = mount(PartialState, { props: { notice: { text: "Ein Teil fehlt." }, retry: true } });

    await wrapper.get("button").trigger("click");

    expect(wrapper.get("button").text()).toBe(t("states.retry"));
    expect(wrapper.emitted("retry")).toHaveLength(1);
  });
});
