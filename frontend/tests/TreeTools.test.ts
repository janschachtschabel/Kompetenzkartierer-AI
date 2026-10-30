import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, CHECK_KIND, type Job, type Tree } from "@/api";
import JobProgress from "@/components/JobProgress.vue";
import TreeTools from "@/components/TreeTools.vue";
import { t } from "@/i18n/de";
import { refusalText } from "@/refusals";

import { violations } from "./axe";
import { job } from "./registerEntries";
import { tree_ } from "./treeFixtures";

let shown: VueWrapper | null = null;

const check = (status: Job["status"]): Job => ({ ...job(status), kind: CHECK_KIND });
const CLOSED: Partial<Tree> = { editable: false, reviewable: false, closed: "job_open" };

function tools(changes: Partial<Tree> = {}): VueWrapper {
  shown = mount(TreeTools, { props: { tree: tree_([], changes), documentId: "d1" }, attachTo: document.body });
  return shown;
}

const names = (wrapper: VueWrapper) => wrapper.findAll("button").map((one) => one.text());
const button = (wrapper: VueWrapper, label: string) => {
  const found = wrapper.findAll("button").find((one) => one.text() === label);
  if (!found) throw new Error(label);
  return found;
};
const checkButton = (wrapper: VueWrapper) => button(wrapper, t("documents.tree.check.button"));

// the check started, the tree read again as the page does: closed while its job is open
async function start(wrapper: VueWrapper): Promise<void> {
  const pressed = checkButton(wrapper);
  (pressed.element as HTMLElement).focus();
  await pressed.trigger("click");
  await flushPromises();
  await wrapper.setProps({ tree: tree_([], CLOSED) });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("the tree's tools", () => {
  it("offer the owner to add a node at the top and to check the tree again", async () => {
    const wrapper = tools();

    expect(names(wrapper)).toEqual([t("documents.tree.create.node"), t("documents.tree.check.button")]);
    await button(wrapper, t("documents.tree.create.node")).trigger("click");

    expect(wrapper.emitted("create-top")).toHaveLength(1);
    vi.useRealTimers(); // axe waits on timers of its own
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("offer nothing where the tree is closed", () => {
    expect(names(tools(CLOSED))).toEqual([]);
  });

  it("start the check, have the tree read again and follow its job, named as a check", async () => {
    const started = vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockResolvedValue(check("running"));
    const wrapper = tools();

    await start(wrapper);

    expect(started).toHaveBeenCalledWith("d1");
    expect(wrapper.emitted("changed")).toHaveLength(1);
    const progress = wrapper.getComponent(JobProgress);
    expect(progress.props()).toMatchObject({ jobId: "j1", label: t("documents.page.checkLabel") });
    await vi.advanceTimersByTimeAsync(1000);
    expect(progress.get(".status-badge").text()).toBe(t("jobs.status.running"));
  });

  it("name a job the start met by its kind: an extraction waiting is no check", async () => {
    const extracting: Job = { ...check("running"), kind: "extract.run" };
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(extracting);
    vi.spyOn(api, "getJob").mockResolvedValue(extracting);
    const wrapper = tools();

    await start(wrapper);

    expect(wrapper.getComponent(JobProgress).props("label")).toBe(t("documents.page.jobLabel"));
  });

  it("keep the check's button while its job waits or runs, busy, the keyboard on it: a press starts nothing", async () => {
    const started = vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockResolvedValue(check("running"));
    const wrapper = tools();

    await start(wrapper);
    await vi.advanceTimersByTimeAsync(1000);
    await checkButton(wrapper).trigger("click");
    await flushPromises();

    expect(names(wrapper)).toEqual([t("documents.tree.check.button"), t("jobs.cancel.button")]);
    expect(checkButton(wrapper).attributes("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(checkButton(wrapper).element);
    expect(started).toHaveBeenCalledTimes(1);
  });

  it("start nothing more while the start is on its way", async () => {
    const started = vi.spyOn(api, "startDocumentCheck").mockReturnValue(new Promise(() => {}));
    const wrapper = tools();

    await checkButton(wrapper).trigger("click");
    await checkButton(wrapper).trigger("click");

    expect(checkButton(wrapper).attributes("aria-disabled")).toBe("true");
    expect(started).toHaveBeenCalledTimes(1);
  });

  it("have the tree read again once the check has ended, and offer it again beside how it ended", async () => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockResolvedValue(check("done"));
    const wrapper = tools();

    await start(wrapper);
    await vi.advanceTimersByTimeAsync(1000);
    expect(wrapper.emitted("changed")).toHaveLength(2);
    // ended, the tree not yet read again - or its reading failed: the button stays, a press starts the check again
    expect(checkButton(wrapper).attributes("aria-disabled")).toBeUndefined();
    expect(document.activeElement).toBe(checkButton(wrapper).element);
    await wrapper.setProps({ tree: tree_([]) });

    expect(wrapper.getComponent(JobProgress).get(".status-badge").text()).toBe(t("jobs.status.done"));
    expect(checkButton(wrapper).attributes("aria-disabled")).toBeUndefined();
    expect(document.activeElement).toBe(checkButton(wrapper).element);
  });

  it("let the button go with a reading after the end that finds the tree closed", async () => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockResolvedValue(check("done"));
    const wrapper = tools();
    await start(wrapper);
    await vi.advanceTimersByTimeAsync(1000);

    await wrapper.setProps({ tree: tree_([], { ...CLOSED, closed: "frozen" }) });

    expect(names(wrapper)).toEqual([]);
  });

  it("say where the check runs when its job is the owner's alone, the keyboard to reading the tree again", async () => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));
    const wrapper = tools();

    await start(wrapper);
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(wrapper.findComponent(JobProgress).exists()).toBe(false);
    expect(wrapper.text()).toContain(t("documents.tree.check.lost"));
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.tree.check.lost"));
    expect(names(wrapper)).toEqual([t("documents.tree.check.readAgain")]);
    expect(document.activeElement).toBe(button(wrapper, t("documents.tree.check.readAgain")).element);
    await button(wrapper, t("documents.tree.check.readAgain")).trigger("click");
    expect(wrapper.emitted("changed")).toHaveLength(2);
    // after the click: Vue drops an event older than its handler, and the real clock is behind the faked one
    vi.useRealTimers(); // axe waits on timers of its own
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("leave another reason the job is gone for the job's own words", async () => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("forbidden", 403, "forbidden"));
    const wrapper = tools();

    await start(wrapper);
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(wrapper.getComponent(JobProgress).text()).toContain(t("jobs.goneReasons.forbidden"));
    expect(wrapper.text()).not.toContain(t("documents.tree.check.lost"));
    // the button kept, no longer busy, until the tree is read again: the keyboard is not left on nothing
    expect(checkButton(wrapper).attributes("aria-disabled")).toBeUndefined();
    expect(document.activeElement).toBe(checkButton(wrapper).element);
  });

  it("let the note go once the tree is read open again, the keyboard back on the check", async () => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));
    const wrapper = tools();
    await start(wrapper);
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    await button(wrapper, t("documents.tree.check.readAgain")).trigger("click");
    await wrapper.setProps({ tree: tree_([], CLOSED) }); // read again, the check still running
    expect(wrapper.text()).toContain(t("documents.tree.check.lost"));
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.tree.check.running"));
    const said = wrapper.get("[role=status]").element.textContent;
    await wrapper.setProps({ tree: tree_([], CLOSED) }); // a reading not asked for: nothing said anew
    expect(wrapper.get("[role=status]").element.textContent).toBe(said);
    await wrapper.setProps({ tree: tree_([]) });
    await flushPromises();

    expect(wrapper.text()).not.toContain(t("documents.tree.check.lost"));
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.tree.check.done"));
    expect(document.activeElement).toBe(checkButton(wrapper).element);
  });

  it("let the note go with a reading that finds the check done, though none found it running", async () => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));
    const wrapper = tools();
    await checkButton(wrapper).trigger("click"); // the reading after the start failed: the tree stays as it was
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();
    expect(wrapper.find(".tree-tools__note").exists()).toBe(true);

    await wrapper.setProps({ tree: tree_([]) });

    expect(wrapper.find(".tree-tools__note").exists()).toBe(false);
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.tree.check.done"));
  });

  it("keep the note where the tree, read again after the job was gone, is closed by it", async () => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));
    const wrapper = tools();
    await checkButton(wrapper).trigger("click"); // the tree not yet read again
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    await wrapper.setProps({ tree: tree_([], CLOSED) });

    expect(wrapper.text()).toContain(t("documents.tree.check.lost"));
    // the start's own reading, not one the note asked for: the note is not overtaken
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.tree.check.lost"));
  });

  it.each([
    ["closed for another reason", { editable: false, reviewable: false, closed: "frozen" as const }],
    ["open", {}],
  ])("let the note go with a reading that finds the tree %s: no job closes it", async (_how, changes) => {
    vi.spyOn(api, "startDocumentCheck").mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "no_job"));
    const wrapper = tools();
    await start(wrapper);
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    await wrapper.setProps({ tree: tree_([], changes) });

    expect(wrapper.find(".tree-tools__note").exists()).toBe(false);
    expect(wrapper.get("[role=status]").text()).toBe(t("documents.tree.check.done"));
  });

  it("follow a check started anew in place of the note, and keep the note through a refusal", async () => {
    vi.spyOn(api, "startDocumentCheck")
      .mockResolvedValueOnce(check("queued"))
      .mockRejectedValueOnce(new ApiError("server", 409, "job_open"))
      .mockResolvedValue({ ...check("queued"), id: "j2" });
    vi.spyOn(api, "getJob").mockRejectedValueOnce(new ApiError("server", 404, "no_job")).mockResolvedValue(check("running"));
    const wrapper = tools();
    await checkButton(wrapper).trigger("click"); // the tree still read open: the check offered again
    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    await checkButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain(t("documents.tree.check.lost"));
    await checkButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.text()).not.toContain(t("documents.tree.check.lost"));
    expect(wrapper.getComponent(JobProgress).props("jobId")).toBe("j2");
  });

  it.each(["not_checked", "frozen", "job_open", "file_hidden"])(
    "say the refusal %s at the button and have nothing read again",
    async (code) => {
      vi.spyOn(api, "startDocumentCheck").mockRejectedValue(new ApiError("server", 409, code));
      const wrapper = tools();

      await checkButton(wrapper).trigger("click");
      await flushPromises();

      expect(wrapper.get("[role=alert]").text()).toContain(refusalText(code));
      expect(wrapper.emitted("changed")).toBeUndefined();
      expect(wrapper.findComponent(JobProgress).exists()).toBe(false);
      expect(checkButton(wrapper).attributes("aria-disabled")).toBeUndefined();
    },
  );

  it("say another failure as one, and let it go with the next press", async () => {
    vi.spyOn(api, "startDocumentCheck")
      .mockRejectedValueOnce(new ApiError("network", 0))
      .mockResolvedValue(check("queued"));
    vi.spyOn(api, "getJob").mockResolvedValue(check("running"));
    const wrapper = tools();

    await checkButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.tree.check.failed"));
    vi.useRealTimers(); // axe waits on timers of its own
    expect(await violations(wrapper.html())).toEqual([]);
    await checkButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.find("[role=alert]").exists()).toBe(false);
  });
});
