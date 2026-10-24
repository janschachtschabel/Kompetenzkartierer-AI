import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument } from "@/api";
import SourceDocuments from "@/components/SourceDocuments.vue";
import { t } from "@/i18n/de";
import { router } from "@/router";

import { violations } from "./axe";

let shown: VueWrapper | null = null;

function made(id: string, changes: Partial<CurriculumDocument> = {}): CurriculumDocument {
  return {
    id,
    source_id: "s1",
    conversion_id: "c1",
    own: true,
    title: null,
    document_type_iri: null,
    sector: "school",
    regions: ["DE-NW"],
    created_at: "2026-10-24T10:00:00Z",
    extraction: null,
    ...changes,
  };
}

async function open(): Promise<VueWrapper> {
  shown = mount(SourceDocuments, { props: { sourceId: "s1" }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return shown;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
});

describe("the documents of a register entry", () => {
  it("lists the entry's documents as the server gives them, each with its extraction", async () => {
    const list = vi.spyOn(api, "listDocuments").mockResolvedValue([
      made("d2", { title: "Kernlehrplan Physik", extraction: { job_id: "j2", status: "running" } }),
      made("d1"),
    ]);

    const wrapper = await open();

    expect(list).toHaveBeenCalledWith("s1");
    const links = wrapper.findAll("li a");
    expect(links.map((link) => [link.text(), link.attributes("href")])).toEqual([
      ["Kernlehrplan Physik", "/dokumente/d2"],
      [t("documents.untitled"), "/dokumente/d1"],
    ]);
    expect(wrapper.findAll("li")[0].text()).toContain(t("documents.page.lastStatus", { status: t("jobs.status.running") }));
    expect(wrapper.findAll("li")[1].text()).toContain(t("documents.page.none"));
  });

  it("says when the entry has none yet", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);

    expect((await open()).text()).toContain(t("documents.list.empty"));
  });

  it("says when they did not load, and asks again", async () => {
    vi.spyOn(api, "listDocuments")
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue([made("d1")]);
    const wrapper = await open();
    expect(wrapper.text()).toContain(t("documents.list.loadFailed"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(wrapper.findAll("li")).toHaveLength(1);
  });

  it("has nothing axe finds", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([made("d1")]);

    expect(await violations((await open()).html())).toEqual([]);
  });
});
