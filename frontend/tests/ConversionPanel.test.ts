import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import ConversionPanel from "@/components/ConversionPanel.vue";
import { findingText } from "@/conversionWords";
import { t } from "@/i18n/de";
import { router } from "@/router";

import { conversion } from "./conversions";
import { deferred, job } from "./registerEntries";

const PDF = "application/pdf";
let shown: VueWrapper | null = null;

async function open(mime = PDF): Promise<VueWrapper> {
  shown = mount(ConversionPanel, { props: { sourceId: "s1", mime }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

const startButton = (wrapper: VueWrapper) => wrapper.get("[data-test=conversion-start]");
const status = (wrapper: VueWrapper) => wrapper.get("[data-test=conversion-status]");
const pending = conversion({ status: "pending", pages: null, printed_pages: null, finished_at: null, engine_version: null });

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getConversion").mockRejectedValue(new ApiError("server", 404, "no_conversion"));
});

afterEach(() => {
  vi.useRealTimers();
  shown?.unmount();
  shown = null;
});

describe("an entry's conversion", () => {
  it("says it loads, then that the file is not converted yet, with the way to convert it", async () => {
    shown = mount(ConversionPanel, { props: { sourceId: "s1", mime: PDF }, global: { plugins: [router] } });
    expect(shown.text()).toContain(t("states.loading"));
    await flushPromises();

    expect(shown.get("h2").text()).toBe(t("conversions.heading"));
    expect(shown.text()).toContain(t("conversions.intro"));
    expect(startButton(shown).text()).toBe(t("conversions.start"));
    // a region there from the start, so the first word it gets is read out
    expect(status(shown).attributes("role")).toBe("status");
    expect(status(shown).text()).toBe("");
  });

  it("starts the conversion, follows its job and shows it done once the job has ended", async () => {
    // the job's first question is a second away; flushPromises runs on setImmediate, left real
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    vi.spyOn(api, "askConversion").mockResolvedValue(pending);
    vi.spyOn(api, "getJob").mockResolvedValue({ ...job("done"), kind: "source.convert" });
    const wrapper = await open();
    vi.mocked(api.getConversion).mockResolvedValue(conversion());

    const button = startButton(wrapper);
    (button.element as HTMLButtonElement).focus();
    await button.trigger("click");
    await flushPromises();

    expect(api.askConversion).toHaveBeenCalledWith("s1");
    expect(wrapper.text()).toContain(t("conversions.jobLabel"));
    expect(status(wrapper).text()).toBe(t("conversions.started"));
    // the button went with the state it belonged to: the keyboard is at the section's heading
    expect(document.activeElement).toBe(wrapper.get("h2").element);

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(api.getConversion).toHaveBeenCalledTimes(2);
    expect(status(wrapper).text()).toBe(t("conversions.done", { pages: 3 }));
    expect(wrapper.get("a[href='/quellen/s1/bloecke']").text()).toBe(t("conversions.showBlocks"));
  });

  it("follows a conversion that runs already, as it found it", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    vi.mocked(api.getConversion).mockResolvedValue(pending);
    vi.spyOn(api, "getJob").mockResolvedValue({
      ...job("running"),
      kind: "source.convert",
      progress: { code: "converting", params: {} },
    });
    const wrapper = await open();

    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.text()).toContain(t("jobs.progress.converting"));
    expect(wrapper.find("[data-test=conversion-start]").exists()).toBe(false);
  });

  it("asks about no file but a PDF, and says so", async () => {
    const wrapper = await open("text/html");

    expect(wrapper.text()).toContain(t("refusals.not_pdf"));
    expect(wrapper.find("button").exists()).toBe(false);
    expect(api.getConversion).not.toHaveBeenCalled();
  });

  it("says a file for the editors alone is theirs, without a start", async () => {
    vi.mocked(api.getConversion).mockRejectedValue(new ApiError("forbidden", 403, "file_hidden"));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("refusals.file_hidden"));
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
  });

  it("shows a conversion done: its pages, its tool, what it found, and the way to its blocks", async () => {
    const symbol = { code: "unmapped_symbol", params: { codepoint: "U+F0B7", count: 3, pages: [1] } };
    vi.mocked(api.getConversion).mockResolvedValue(conversion({ findings: [symbol] }));
    const wrapper = await open();

    const facts = wrapper.get("dl").text();
    expect(facts).toContain(t("conversions.facts.pages"));
    expect(facts).toContain("3");
    expect(facts).toContain("pdfplumber 0.11.10");
    expect(facts).toContain("23.10.2026");
    expect(wrapper.get("[data-test=findings]").text()).toBe(findingText(symbol));
    expect(wrapper.find("a[href='/quellen/s1/bloecke']").exists()).toBe(true);
    // a state found, not an event: nothing to announce
    expect(status(wrapper).text()).toBe("");
  });

  it("says when the conversion found nothing remarkable", async () => {
    vi.mocked(api.getConversion).mockResolvedValue(conversion());
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("conversions.noFindings"));
    expect(wrapper.find("[data-test=findings]").exists()).toBe(false);
  });

  it("says why a conversion failed, and starts it again on request", async () => {
    vi.mocked(api.getConversion).mockResolvedValue(conversion({ status: "failed", error_code: "needs_ocr", pages: null }));
    vi.spyOn(api, "askConversion").mockResolvedValue(pending);
    vi.spyOn(api, "getJob").mockResolvedValue({ ...job("running"), kind: "source.convert" });
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("conversions.failed"));
    expect(wrapper.text()).toContain(t("jobs.failures.needs_ocr"));
    const again = startButton(wrapper);
    expect(again.text()).toBe(t("states.retry"));

    await again.trigger("click");
    await flushPromises();

    expect(api.askConversion).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).not.toContain(t("jobs.failures.needs_ocr"));
    expect(wrapper.text()).toContain(t("conversions.jobLabel"));
  });

  it("says a conversion whose job was cancelled was stopped", async () => {
    vi.mocked(api.getConversion).mockResolvedValue(conversion({ status: "failed", error_code: "cancelled", pages: null }));
    const wrapper = await open();

    expect(wrapper.text()).toContain(t("conversions.cancelled"));
  });

  it("says the job's end in the status, a failure with its reason", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    vi.mocked(api.getConversion)
      .mockResolvedValueOnce(pending)
      .mockResolvedValue(conversion({ status: "failed", error_code: "too_many_pages", pages: null }));
    vi.spyOn(api, "getJob").mockResolvedValue({ ...job("failed"), kind: "source.convert", error_code: "too_many_pages" });
    const wrapper = await open();

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(status(wrapper).text()).toBe(`${t("conversions.failed")} ${t("jobs.failures.too_many_pages")}`);
    expect(wrapper.find("[data-test=conversion-start]").exists()).toBe(true);
  });

  it("says the job's end once: in the section's words, not the job's as well", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const reloaded = deferred<api.Conversion>();
    vi.mocked(api.getConversion).mockResolvedValueOnce(pending).mockReturnValue(reloaded.promise);
    vi.spyOn(api, "getJob").mockResolvedValue({ ...job("done"), kind: "source.convert" });
    const wrapper = await open();

    await vi.advanceTimersByTimeAsync(1000);
    // the job has ended, the section reloads: whatever is said meanwhile is heard as well
    const meanwhile = wrapper.findAll("[role=status]").map((region) => region.text()).filter(Boolean);
    reloaded.resolve(conversion());
    await flushPromises();

    expect(meanwhile).toEqual([]);
    expect(status(wrapper).text()).toBe(t("conversions.done", { pages: 3 }));
  });

  it.each([
    // another account's job, an editor's start: the job answers 404 to this reader (app/api/jobs.py)
    ["a job it may not follow", { job_id: "j9" }],
    ["no job named", { job_id: null }],
  ])("follows a conversion by its own state where it has %s, until it is done", async (_case, named) => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    vi.mocked(api.getConversion)
      .mockResolvedValueOnce({ ...pending, ...named })
      .mockResolvedValueOnce({ ...pending, ...named })
      .mockResolvedValue(conversion());
    vi.spyOn(api, "getJob").mockRejectedValue(new ApiError("server", 404, "not_found"));
    const wrapper = await open();

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();
    expect(wrapper.text()).toContain(t("conversions.following"));
    expect(wrapper.text()).not.toContain(t("jobs.goneReasons.not_found"));

    await vi.advanceTimersByTimeAsync(2000);
    await flushPromises();
    await vi.advanceTimersByTimeAsync(4000);
    await flushPromises();

    expect(status(wrapper).text()).toBe(t("conversions.done", { pages: 3 }));
    expect(wrapper.text()).toContain(t("conversions.showBlocks"));
  });

  it("stops asking once it is gone from the page", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    vi.mocked(api.getConversion).mockResolvedValue({ ...pending, job_id: null });
    const wrapper = await open();
    const asked = vi.mocked(api.getConversion).mock.calls.length;

    wrapper.unmount();
    shown = null;
    await vi.advanceTimersByTimeAsync(30_000);

    expect(api.getConversion).toHaveBeenCalledTimes(asked);
  });

  it("says a refused start beside the button, which stays", async () => {
    vi.spyOn(api, "askConversion").mockRejectedValue(new ApiError("server", 422, "not_pdf"));
    const wrapper = await open();

    await startButton(wrapper).trigger("click");
    await flushPromises();

    const refusal = wrapper.get("[role=alert]");
    expect(refusal.text()).toContain(t("conversions.startFailed"));
    expect(refusal.text()).toContain(t("refusals.not_pdf"));
    expect(wrapper.find("[data-test=conversion-start]").exists()).toBe(true);
  });

  it("starts once however often it is pressed while it starts, and says it is busy", async () => {
    const answer = deferred<api.Conversion>();
    vi.spyOn(api, "askConversion").mockReturnValue(answer.promise);
    const wrapper = await open();

    await startButton(wrapper).trigger("click");
    await startButton(wrapper).trigger("click");

    expect(startButton(wrapper).attributes("aria-disabled")).toBe("true");
    expect(startButton(wrapper).attributes("disabled")).toBeUndefined();
    expect(api.askConversion).toHaveBeenCalledTimes(1);
    answer.resolve(conversion());
    await flushPromises();
  });

  it("says when its state did not load, and loads it again on request", async () => {
    vi.mocked(api.getConversion)
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue(conversion());
    const wrapper = await open();
    expect(wrapper.get("[role=alert]").text()).toContain(t("conversions.loadFailed"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain(t("conversions.showBlocks"));
  });
});
