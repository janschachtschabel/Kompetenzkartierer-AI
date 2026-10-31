import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type DocumentFinding, type FindingsPage, type Job } from "@/api";
import DocumentFindings from "@/components/DocumentFindings.vue";
import { findingText, focusText } from "@/findingWords";
import { t } from "@/i18n/de";

import { violations } from "./axe";

let shown: VueWrapper | null = null;

const WRONG: DocumentFinding = {
  rule: "x5.wording_not_found",
  severity: "violation",
  stage: "X5",
  focus: { kind: "statement", id: "s1", label: "Die Lernenden messen." },
  path: null,
  message: "the wording is not in the blocks its anchor names",
  message_lang: null,
  unit: null,
};
const LOST: DocumentFinding = {
  rule: "x4.unknown_block",
  severity: "warning",
  stage: "X4",
  focus: { kind: "document", id: "d1", label: null },
  path: "$.statements[0].blockIds[0]",
  message: "a block the conversion does not hold",
  message_lang: null,
  unit: "E1",
};
const ENGLISH: DocumentFinding = {
  rule: "x1.regions_differ",
  severity: "info",
  stage: "X1",
  focus: { kind: "document", id: "d1", label: null },
  path: null,
  message: "the Länder read differ from those asked",
  message_lang: null,
  unit: null,
};

function page(changes: Partial<FindingsPage> = {}): FindingsPage {
  return {
    counts: { violation: 1, warning: 1, info: 1 },
    findings: [WRONG, LOST, ENGLISH],
    truncated: false,
    repairable: [],
    ...changes,
  };
}

function job(): Job {
  return {
    id: "j9",
    kind: "extract.repair",
    status: "queued",
    progress: null,
    error_code: null,
    cancel_requested: false,
    attempts: 0,
    max_attempts: 3,
    created_at: "2026-10-25T12:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

function open(props: { own?: boolean; busy?: boolean; refresh?: number; closed?: boolean } = {}): VueWrapper {
  shown = mount(DocumentFindings, {
    props: { documentId: "d1", own: true, busy: false, refresh: 0, ...props },
    attachTo: document.body,
  });
  return shown;
}

function rows(wrapper: VueWrapper): string[][] {
  return wrapper.findAll("tbody tr").map((row) => row.findAll("td").map((cell) => cell.text()));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  document.body.innerHTML = "";
});

describe("a document's findings", () => {
  it("lists them gravest first, counted by severity, each with what it is about", async () => {
    const asked = vi.spyOn(api, "getFindings").mockResolvedValue(page({ counts: { violation: 1, warning: 2, info: 1 } }));

    const wrapper = open();
    await flushPromises();

    expect(asked).toHaveBeenCalledWith("d1");
    const counts = wrapper.findAll("[data-test=findings-counts] .status-badge");
    expect(counts.map((pill) => [pill.text(), pill.classes()])).toEqual([
      [t("documents.findings.counts.violation", { count: 1 }), ["status-badge", "error"]],
      [t("documents.findings.counts.warning", { count: 2 }), ["status-badge", "warning"]],
      [t("documents.findings.counts.info", { count: 1 }), ["status-badge", "neutral"]],
    ]);
    // scrolled on its own, by the keyboard too, named (axe in jsdom does not judge a scroll region)
    const region = wrapper.get("[role=region]");
    expect([region.attributes("tabindex"), region.attributes("aria-label")]).toEqual(["0", t("documents.findings.table")]);
    expect(rows(wrapper)).toEqual([
      [t("documents.findings.severities.violation"), findingText(WRONG).text, focusText(WRONG)],
      [t("documents.findings.severities.warning"), findingText(LOST).text, focusText(LOST)],
      [t("documents.findings.severities.info"), findingText(ENGLISH).text, focusText(ENGLISH)],
    ]);
  });

  it("counts only the severities found", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ counts: { violation: 0, warning: 1, info: 0 }, findings: [LOST] }));

    const wrapper = open();
    await flushPromises();

    expect(wrapper.findAll("[data-test=findings-counts] .status-badge").map((pill) => pill.text())).toEqual([
      t("documents.findings.counts.warning", { count: 1 }),
    ]);
  });

  it("quotes a message it has no words for as the server's English", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ findings: [ENGLISH] }));

    const wrapper = open();
    await flushPromises();

    expect(wrapper.get("tbody q").attributes("lang")).toBe("en");
    expect(wrapper.get("tbody q").text()).toBe(ENGLISH.message);
  });

  it("says how many it lists where more were found than it shows", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(
      page({ counts: { violation: 200, warning: 300, info: 100 }, findings: [WRONG, LOST], truncated: true }),
    );

    const wrapper = open();
    await flushPromises();

    expect(wrapper.get("[data-test=findings-truncated]").text()).toBe(
      t("documents.findings.truncated", { shown: 2, total: 600 }),
    );
  });

  it("says a document nothing was found on", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ counts: { violation: 0, warning: 0, info: 0 }, findings: [] }));

    const wrapper = open();
    await flushPromises();

    expect(wrapper.text()).toContain(t("documents.findings.noneTitle"));
    expect(wrapper.find("table").exists()).toBe(false);
  });

  it("shows its waiting, says a failure, and reads again when asked", async () => {
    const asked = vi
      .spyOn(api, "getFindings")
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"))
      .mockResolvedValue(page());

    const wrapper = open();
    expect(wrapper.text()).toContain(t("documents.findings.loading"));
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.findings.loadFailed"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(asked).toHaveBeenCalledTimes(2);
    expect(rows(wrapper)).toHaveLength(3);
  });

  it("keeps the list where a later reading fails, and says so beside it", async () => {
    vi.spyOn(api, "getFindings")
      .mockResolvedValueOnce(page())
      .mockRejectedValue(new ApiError("server", 503, "service_unavailable"));
    const wrapper = open();
    await flushPromises();

    await wrapper.setProps({ refresh: 1 });
    await flushPromises();

    expect(rows(wrapper)).toHaveLength(3);
    expect(wrapper.get("[role=status].page-notice").text()).toContain(t("documents.findings.loadFailed"));
  });
});

describe("a document's repair offered with its findings", () => {
  it("is offered no more once the document is frozen", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1"] }));

    const wrapper = open({ closed: true });
    await flushPromises();

    expect(wrapper.find("[data-test=repair-offer]").exists()).toBe(false);
  });

  it("is offered to its owner for the work packages the findings name, and started", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1", "E3"] }));
    const start = vi.spyOn(api, "startRepair").mockResolvedValue(job());
    const wrapper = open();
    await flushPromises();
    expect(wrapper.get("[data-test=repair-offer]").text()).toBe(t("documents.findings.repair.offer", { count: 2 }));

    await wrapper.get("[data-test=repair-start]").trigger("click");
    await flushPromises();

    expect(start).toHaveBeenCalledWith("d1");
    expect(wrapper.emitted("started")).toEqual([[job()]]);
    expect(wrapper.get("[data-test=repair-status]").text()).toBe(t("documents.findings.repair.started"));
  });

  it("takes the keyboard to the section's heading once the page hides the button for the job", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1"] }));
    vi.spyOn(api, "startRepair").mockResolvedValue(job());
    const wrapper = open();
    await flushPromises();
    const button = wrapper.get<HTMLButtonElement>("[data-test=repair-start]");
    button.element.focus();

    await button.trigger("click");
    await flushPromises();
    await wrapper.setProps({ busy: true }); // the page follows the job it started
    await flushPromises();

    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
    expect(document.activeElement).toBe(wrapper.get("#document-findings").element);
  });

  it("is not offered to another, while a job of the document waits or runs, or with nothing to repair", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1"] }));

    for (const props of [{ own: false }, { busy: true }]) {
      const wrapper = open(props);
      await flushPromises();
      expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false);
      wrapper.unmount();
    }
    vi.mocked(api.getFindings).mockResolvedValue(page());
    const nothing = open();
    await flushPromises();
    expect(nothing.find("[data-test=repair-start]").exists()).toBe(false);
    expect(nothing.find("[data-test=repair-offer]").exists()).toBe(false);
  });

  it("says that an extraction runs already where the start gave that one back", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1"] }));
    vi.spyOn(api, "startRepair").mockResolvedValue({ ...job(), kind: "extract.run", status: "running" });
    const wrapper = open();
    await flushPromises();

    await wrapper.get("[data-test=repair-start]").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-test=repair-status]").text()).toBe(t("documents.findings.repair.extractionRunning"));
    expect(wrapper.emitted("started")).toHaveLength(1); // the page follows it all the same
  });

  it("offers no repair while its findings are read again, nor beside a reading that failed", async () => {
    let reread: (value: FindingsPage) => void = () => undefined;
    vi.spyOn(api, "getFindings")
      .mockResolvedValueOnce(page({ repairable: ["E1"] }))
      .mockReturnValueOnce(new Promise<FindingsPage>((resolve) => (reread = resolve)))
      .mockRejectedValueOnce(new ApiError("server", 503, "service_unavailable"));
    const wrapper = open();
    await flushPromises();
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(true);

    await wrapper.setProps({ refresh: 1 }); // a job ended: what it found is not here yet
    await flushPromises();
    const whileRead = wrapper.find("[data-test=repair-start]").exists();
    reread(page({ repairable: ["E3"] }));
    await flushPromises();
    const afterRead = wrapper.get("[data-test=repair-offer]").text();
    await wrapper.setProps({ refresh: 2 });
    await flushPromises();

    expect(whileRead).toBe(false);
    expect(afterRead).toBe(t("documents.findings.repair.offer", { count: 1 }));
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(false); // beside the failure said
  });

  it("does not say a refusal again once the offer comes back after a job", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1"] }));
    vi.spyOn(api, "startRepair").mockRejectedValue(new ApiError("server", 429, "too_many_starts"));
    const wrapper = open();
    await flushPromises();
    await wrapper.get("[data-test=repair-start]").trigger("click");
    await flushPromises();
    expect(wrapper.find("[role=alert]").exists()).toBe(true);

    await wrapper.setProps({ busy: true });
    await wrapper.setProps({ busy: false });
    await flushPromises();

    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(true);
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
  });

  it("says a start refused in its own words, and keeps the button", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1"] }));
    vi.spyOn(api, "startRepair").mockRejectedValue(new ApiError("server", 409, "nothing_to_repair"));
    const wrapper = open();
    await flushPromises();

    await wrapper.get("[data-test=repair-start]").trigger("click");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.findings.repair.failed"));
    expect(wrapper.get("[role=alert]").text()).toContain(t("refusals.nothing_to_repair"));
    expect(wrapper.emitted("started")).toBeUndefined();
    expect(wrapper.find("[data-test=repair-start]").exists()).toBe(true);
  });

  it("has nothing axe finds", async () => {
    vi.spyOn(api, "getFindings").mockResolvedValue(page({ repairable: ["E1"] }));
    const wrapper = open();
    await flushPromises();

    expect(await violations(wrapper.html())).toEqual([]);
  });
});

describe("a document's findings whose entry is no longer the reader's", () => {
  it("say so, with no retry that could change it", async () => {
    vi.spyOn(api, "getFindings").mockRejectedValue(new ApiError("forbidden", 403, "file_hidden"));

    const wrapper = open();
    await flushPromises();

    expect(wrapper.text()).toContain(t("refusals.file_hidden"));
    expect(wrapper.findAll("button").some((button) => button.text() === t("states.retry"))).toBe(false);
  });
});
