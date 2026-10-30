import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import ReviewToggles from "@/components/ReviewToggles.vue";
import { rowsOf, type Row } from "@/documentTree";
import { t } from "@/i18n/de";

import { violations } from "./axe";
import { CV, node_, statement_ } from "./treeFixtures";

let shown: VueWrapper | null = null;
let reviewed = vi.fn();

const ROWS = rowsOf([node_("a", { statements: [statement_("s1", { revision: 5, review_status: CV + "rev_confirmed" })] })]);
const ROW = ROWS.get("statement:s1") as Row;

function toggles(): VueWrapper {
  reviewed = vi.fn();
  shown = mount(ReviewToggles, { props: { row: ROW, documentId: "d1", onReviewed: reviewed }, attachTo: document.body });
  return shown;
}

const buttons = (wrapper: VueWrapper) => wrapper.findAll("button");
const pressed = (wrapper: VueWrapper) => buttons(wrapper).map((one) => one.attributes("aria-pressed"));
const button = (wrapper: VueWrapper, label: string) => {
  const found = buttons(wrapper).find((one) => one.text() === label);
  if (!found) throw new Error(label);
  return found;
};

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("a row's review status to choose", () => {
  it("offers the three statuses in a group named for it, the row's own pressed and ticked", async () => {
    const wrapper = toggles();

    const group = wrapper.get("[role=group]");
    expect(document.getElementById(group.attributes("aria-labelledby") ?? "")?.textContent).toBe(t("documents.tree.review.label"));
    expect(buttons(wrapper).map((one) => [one.text(), one.attributes("aria-pressed")])).toEqual([
      ["Vorgeschlagen", "false"],
      ["Bestätigt", "true"],
      ["Verworfen", "false"],
    ]);
    expect(buttons(wrapper).map((one) => one.find("svg").exists())).toEqual([false, true, false]);
    expect(buttons(wrapper).every((one) => one.attributes("type") === "button")).toBe(true);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("sets another for the row and tells how it went; the status it stands at asks nothing", async () => {
    const sent = vi.spyOn(api, "setReview").mockResolvedValue({ revisions: [{ id: "s1", revision: 6 }] });
    const wrapper = toggles();

    await button(wrapper, "Bestätigt").trigger("click");
    expect(sent).not.toHaveBeenCalled();
    await button(wrapper, "Verworfen").trigger("click");
    await flushPromises();

    expect(sent).toHaveBeenCalledWith("d1", "rejected", [{ kind: "statement", id: "s1", revision: 5 }]);
    expect(reviewed).toHaveBeenCalledWith({ outcome: "set", status: "rejected" }, "statement:s1");
  });

  it("shows the status just set pressed until the row is read again, and the row's own from then", async () => {
    const sent = vi.spyOn(api, "setReview").mockResolvedValue({ revisions: [{ id: "s1", revision: 6 }] });
    const wrapper = toggles();

    await button(wrapper, "Verworfen").trigger("click");
    await flushPromises();
    expect(pressed(wrapper)).toEqual(["false", "false", "true"]);
    await button(wrapper, "Verworfen").trigger("click"); // the status it stands at now asks nothing
    expect(sent).toHaveBeenCalledTimes(1);

    const reread = rowsOf([node_("a", { statements: [statement_("s1", { revision: 7, review_status: CV + "rev_proposed" })] })]);
    await wrapper.setProps({ row: reread.get("statement:s1") as Row });

    expect(pressed(wrapper)).toEqual(["true", "false", "false"]); // as read: another set it since
  });

  it("asks nothing more while it sets one, and tells how it went once it is gone", async () => {
    let answer: (done: { revisions: { id: string; revision: number }[] }) => void = () => undefined;
    const sent = vi.spyOn(api, "setReview").mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const wrapper = toggles();

    await button(wrapper, "Verworfen").trigger("click");
    expect(buttons(wrapper).map((one) => one.attributes("aria-disabled"))).toEqual(["true", "true", "true"]);
    await button(wrapper, "Vorgeschlagen").trigger("click");
    expect(sent).toHaveBeenCalledTimes(1);

    wrapper.unmount();
    answer({ revisions: [{ id: "s1", revision: 6 }] });
    await flushPromises();
    expect(reviewed).toHaveBeenCalledWith({ outcome: "set", status: "rejected" }, "statement:s1");
  });

  it("tells a row changed meanwhile or a tree closed, and says another failure where it was asked", async () => {
    vi.spyOn(api, "setReview")
      .mockRejectedValueOnce(new ApiError("server", 409, "stale_revision", "Changed.", { stale: [] }))
      .mockRejectedValueOnce(new ApiError("network", 0));
    const wrapper = toggles();

    await button(wrapper, "Verworfen").trigger("click");
    await flushPromises();
    expect(reviewed).toHaveBeenCalledWith({ outcome: "stale" }, "statement:s1");
    expect(pressed(wrapper)).toEqual(["false", "true", "false"]); // nothing set

    await button(wrapper, "Vorgeschlagen").trigger("click");
    await flushPromises();
    const alert = wrapper.get(".review-toggles__problem");
    expect([alert.attributes("role"), alert.text()]).toEqual(["alert", expect.stringContaining(t("documents.tree.review.failed"))]);
    expect(reviewed).toHaveBeenCalledTimes(1);
  });
});
