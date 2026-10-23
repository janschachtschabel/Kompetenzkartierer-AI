import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import CheckStart from "@/components/CheckStart.vue";
import JobProgress from "@/components/JobProgress.vue";
import { t } from "@/i18n/de";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";
import SourcesView from "@/views/SourcesView.vue";

import { job, page } from "./registerEntries";

let shown: VueWrapper | null = null;

function mountCheck(): VueWrapper {
  shown = mount(CheckStart, { attachTo: document.body });
  return shown;
}

async function confirm(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("[data-test=check-start]").trigger("click");
  await wrapper.get("[data-test=confirm]").trigger("click");
  await flushPromises();
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  clearSession();
});

describe("the start of the seed's check", () => {
  it("says what the check does and asks before it starts", async () => {
    const started = vi.spyOn(api, "startCheck");
    const wrapper = mountCheck();
    expect(wrapper.text()).toContain(t("sources.check.intro"));

    await wrapper.get("[data-test=check-start]").trigger("click");

    expect(wrapper.get("[role=dialog]").text()).toContain(t("sources.check.confirmTitle"));
    expect(wrapper.get("[data-test=confirm]").text()).toBe(t("sources.check.confirm"));
    expect(started).not.toHaveBeenCalled();
  });

  it("starts nothing when the question is answered no, and gives the keyboard back", async () => {
    const started = vi.spyOn(api, "startCheck");
    const wrapper = mountCheck();
    const button = wrapper.get<HTMLButtonElement>("[data-test=check-start]");
    button.element.focus();

    await button.trigger("click");
    await wrapper.get("[data-test=cancel]").trigger("click");
    await flushPromises();

    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
    expect(started).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(button.element);
  });

  it("starts the check on yes and hands its job on to follow", async () => {
    vi.spyOn(api, "startCheck").mockResolvedValue({ job_id: "j1" });
    const wrapper = mountCheck();

    await confirm(wrapper);

    expect(wrapper.emitted("started")).toEqual([["j1"]]);
    expect(wrapper.get("[data-test=check-status]").text()).toBe(t("sources.check.started"));
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
  });

  it("follows a check that waits or runs already instead of starting a second", async () => {
    const running = new ApiError("server", 409, "check_running", "A check waits or runs already.", { job_id: "j0" });
    vi.spyOn(api, "startCheck").mockRejectedValue(running);
    const wrapper = mountCheck();

    await confirm(wrapper);

    expect(wrapper.emitted("started")).toEqual([["j0"]]);
    expect(wrapper.get("[data-test=check-status]").text()).toBe(t("sources.check.running"));
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
  });

  it("says when the check did not start, and why", async () => {
    vi.spyOn(api, "startCheck").mockRejectedValue(new ApiError("server", 503, "service_unavailable"));
    const wrapper = mountCheck();

    await confirm(wrapper);

    const alert = wrapper.get("[role=alert]");
    expect(alert.text()).toContain(t("sources.check.failed"));
    expect(alert.text()).toContain(t("refusals.service_unavailable"));
    expect(wrapper.emitted("started")).toBeUndefined();
  });

  it("starts once however often it is pressed while the start is under way", async () => {
    let answer: (value: api.CheckStarted) => void = () => undefined;
    const started = vi.spyOn(api, "startCheck").mockImplementation(() => new Promise((resolve) => (answer = resolve)));
    const wrapper = mountCheck();
    await wrapper.get("[data-test=check-start]").trigger("click");
    await wrapper.get("[data-test=confirm]").trigger("click");

    const button = wrapper.get("[data-test=check-start]");
    expect(button.attributes("aria-disabled")).toBe("true");
    await button.trigger("click");
    answer({ job_id: "j1" });
    await flushPromises();

    expect(started).toHaveBeenCalledTimes(1);
    expect(wrapper.find("[role=dialog]").exists()).toBe(false);
  });
});

describe("the register page's check", () => {
  beforeEach(() => {
    vi.spyOn(api, "getInfo").mockResolvedValue({
      name: "Kompetenzkartierer-AI",
      version: "0.1.0",
      public_access: "off",
      max_upload_mb: 50,
    });
    vi.spyOn(api, "listSources").mockResolvedValue(page([]));
    vi.spyOn(api, "getJob").mockResolvedValue({ ...job("running"), kind: "source.check" });
  });

  it("is an admin's alone", async () => {
    setSession({ id: "a", name: "Lehrkraft", roles: ["nutzer", "redaktion"] });
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    expect(wrapper.findComponent(CheckStart).exists()).toBe(false);
    wrapper.unmount();

    setSession({ id: "b", name: "Admin", roles: ["admin"] });
    const admin = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();
    expect(admin.findComponent(CheckStart).exists()).toBe(true);
    admin.unmount();
  });

  it("follows the check it started among the page's jobs, once however often it is handed on", async () => {
    setSession({ id: "b", name: "Admin", roles: ["admin"] });
    const wrapper = mount(SourcesView, { global: { plugins: [router] } });
    await flushPromises();

    wrapper.findComponent(CheckStart).vm.$emit("started", "j1");
    wrapper.findComponent(CheckStart).vm.$emit("started", "j1");
    await flushPromises();

    const followed = wrapper.findAllComponents(JobProgress);
    expect(followed).toHaveLength(1);
    expect(followed[0].props()).toEqual({ jobId: "j1", label: t("sources.check.jobLabel"), quiet: false });
    wrapper.unmount();
  });
});
