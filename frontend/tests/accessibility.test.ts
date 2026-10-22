/**
 * axe over the shared building blocks. Component tests assert the ARIA somebody
 * thought to assert; this asserts the rules - a label pointing at nothing, a
 * control with no name - including what nobody remembered to check. The views
 * are in accessibility-views.test.ts.
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ConfirmDialog from "@/components/ConfirmDialog.vue";
import EmptyState from "@/components/EmptyState.vue";
import ErrorState from "@/components/ErrorState.vue";
import LoadingState from "@/components/LoadingState.vue";
import PartialState from "@/components/PartialState.vue";

import { describeViolations, violations } from "./axe";

describe("the axe harness", () => {
  it("reports a violation when there is one", async () => {
    // The guard on the negative assertions below: without it they would pass
    // just as happily if the harness checked nothing at all.
    const found = await violations('<input type="text">');

    expect(found.length).toBeGreaterThan(0);
    expect(describeViolations(found)).toContain("label");
  });
});

describe("the states", () => {
  it.each([
    ["loading", () => mount(LoadingState)],
    ["loading, quietly", () => mount(LoadingState, { props: { quiet: true } })],
    ["empty", () => mount(EmptyState, { props: { title: "Noch nichts da", body: "Leg den ersten an." } })],
    ["failed", () => mount(ErrorState, { props: { message: "Nicht geladen.", reason: "database away" } })],
    ["partly there", () => mount(PartialState, { props: { notice: { text: "Ein Teil fehlt." }, retry: true } })],
  ])("%s has no axe violations", async (_state, render) => {
    const html = render().html();
    expect(html.length, "something was rendered").toBeGreaterThan(20);

    const found = await violations(html);

    expect(found, describeViolations(found)).toEqual([]);
  });
});

describe("the confirm dialog", () => {
  it("has no axe violations", async () => {
    const wrapper = mount(ConfirmDialog, {
      props: { title: "Konto sperren?", message: "Das Konto kann sich danach nicht mehr anmelden." },
      attachTo: document.body,
    });

    const found = await violations(wrapper.html());
    wrapper.unmount();

    expect(found, describeViolations(found)).toEqual([]);
  });
});
