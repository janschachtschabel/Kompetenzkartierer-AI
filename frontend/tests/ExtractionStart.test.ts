import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type DocumentStarted } from "@/api";
import ExtractionStart from "@/components/ExtractionStart.vue";
import { messages, t } from "@/i18n/de";
import { router } from "@/router";

import { violations } from "./axe";

let shown: VueWrapper | null = null;

function open(country: string | null = "DE-NW"): VueWrapper {
  shown = mount(ExtractionStart, {
    props: { sourceId: "s1", conversionId: "c1", country },
    global: { plugins: [router] },
    attachTo: document.body,
  });
  return shown;
}

function started(): DocumentStarted {
  return {
    document: {
      id: "d1",
      source_id: "s1",
      conversion_id: "c1",
      own: true,
      title: null,
      document_type_iri: null,
      sector: "school",
      regions: ["DE-NW"],
      created_at: "2026-10-24T12:00:00Z",
      extraction: { job_id: "j1", status: "queued" },
    },
    job: {
      id: "j1",
      kind: "extract.run",
      status: "queued",
      progress: null,
      error_code: null,
      cancel_requested: false,
      attempts: 0,
      max_attempts: 3,
      created_at: "2026-10-24T12:00:00Z",
      started_at: null,
      finished_at: null,
    },
  };
}

const checked = (wrapper: VueWrapper) =>
  wrapper.findAll<HTMLInputElement>("input[type=checkbox]").filter((box) => box.element.checked).map((box) => box.element.value);

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
});

describe("the start of an extraction from a finished conversion", () => {
  it("asks for the sector and the Länder, the entry's own already chosen", () => {
    const wrapper = open("DE-NW");

    const options = wrapper.findAll("select option").map((option) => option.text());
    expect(options).toEqual([t("documents.start.sectorChoose"), ...Object.values(messages.documents.sectors)]);
    expect(wrapper.findAll("input[type=checkbox]")).toHaveLength(Object.keys(messages.sources.countries).length);
    expect(checked(wrapper)).toEqual(["DE-NW"]);
    expect(wrapper.get("label[for=extraction-sector]").text()).toBe(t("documents.start.sector"));
  });

  it("says by the field what it lacks, and sends nothing", async () => {
    const make = vi.spyOn(api, "makeDocument");
    const wrapper = open();

    await wrapper.get("form").trigger("submit");

    const select = wrapper.get("#extraction-sector");
    expect(select.attributes("aria-invalid")).toBe("true");
    expect(wrapper.get(`#${select.attributes("aria-describedby")}`).text()).toBe(t("documents.start.sectorMissing"));
    expect(make).not.toHaveBeenCalled();
  });

  it("makes the document and goes to its page", async () => {
    const make = vi.spyOn(api, "makeDocument").mockResolvedValue(started());
    const push = vi.spyOn(router, "push").mockResolvedValue(undefined);
    const wrapper = open("DE-NW");

    await wrapper.get("#extraction-sector").setValue("school");
    await wrapper.get("input[value=DE]").setValue(true);
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(make).toHaveBeenCalledWith({
      source_id: "s1",
      conversion_id: "c1",
      sector: "school",
      regions: ["DE", "DE-NW"],
    });
    expect(push).toHaveBeenCalledWith({ name: "document", params: { id: "d1" } });
  });

  it("says a refusal in its own words and keeps what was chosen", async () => {
    vi.spyOn(api, "makeDocument").mockRejectedValue(new ApiError("server", 403, "no_budget", "No tokens left."));
    const wrapper = open("DE-NW");

    await wrapper.get("#extraction-sector").setValue("vocational");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(t("refusals.no_budget"));
    expect((wrapper.get("#extraction-sector").element as HTMLSelectElement).value).toBe("vocational");
    expect(checked(wrapper)).toEqual(["DE-NW"]);
  });

  it("has nothing axe finds, its error shown too", async () => {
    const wrapper = open();

    expect(await violations(wrapper.html())).toEqual([]);
    await wrapper.get("form").trigger("submit");
    expect(await violations(wrapper.html())).toEqual([]);
  });
});
