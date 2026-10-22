import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type ImportStarted } from "@/api";
import ImportForm from "@/components/ImportForm.vue";
import { t } from "@/i18n/de";

const STARTED: ImportStarted = {
  source: {
    id: "s1",
    title: "lehrplan",
    provenance: "url",
    rights_status: "unklar",
    register_status: "unchecked",
    file: null,
  },
  job_id: "j1",
};

async function submit(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("form").trigger("submit");
  await flushPromises();
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("the import form", () => {
  it("starts the fetch, says so and hands on the entry with its job", async () => {
    const start = vi.spyOn(api, "importSource").mockResolvedValue(STARTED);
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("  https://example.org/lehrplan.pdf ");
    await wrapper.get("#import-title").setValue("Lehrplan");

    await submit(wrapper);

    expect(start).toHaveBeenCalledWith("https://example.org/lehrplan.pdf", "Lehrplan");
    expect(wrapper.get("#import-status").text()).toBe(t("sources.import.started", { title: "lehrplan" }));
    expect(wrapper.emitted("imported")?.[0]).toEqual([STARTED, "https://example.org/lehrplan.pdf"]);
    expect((wrapper.get("#import-url").element as HTMLInputElement).value).toBe("");
  });

  it("names an entry without a title by its address: its title waits for the file", async () => {
    vi.spyOn(api, "importSource").mockResolvedValue({ ...STARTED, source: { ...STARTED.source, title: "" } });
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("https://example.org/lehrplan.pdf");

    await submit(wrapper);

    expect(wrapper.get("#import-status").text()).toBe(
      t("sources.import.started", { title: "https://example.org/lehrplan.pdf" }),
    );
    expect(wrapper.emitted("imported")?.[0]?.[1]).toBe("https://example.org/lehrplan.pdf");
  });

  it("asks for an address before sending anything", async () => {
    const start = vi.spyOn(api, "importSource");
    const wrapper = mount(ImportForm);

    await submit(wrapper);

    expect(start).not.toHaveBeenCalled();
    expect(wrapper.get("#import-error").text()).toContain(t("sources.import.errors.missing"));
    expect(wrapper.get("#import-url").attributes("aria-describedby")).toContain("import-error");
  });

  it.each(["ftp://example.org/a.pdf", "example.org/a.pdf", "javascript:alert(1)"])(
    "says that %s is no web address, and sends nothing",
    async (address) => {
      const start = vi.spyOn(api, "importSource");
      const wrapper = mount(ImportForm);
      await wrapper.get("#import-url").setValue(address);

      await submit(wrapper);

      expect(start).not.toHaveBeenCalled();
      expect(wrapper.get("#import-error").text()).toContain(t("sources.import.errors.scheme"));
    },
  );

  it("says a refusal in its own words and keeps the address", async () => {
    vi.spyOn(api, "importSource").mockRejectedValue(
      new ApiError("server", 429, "too_many_imports", "Too many", {}, 30),
    );
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("https://example.org/a.pdf");

    await submit(wrapper);

    expect(wrapper.get("#import-error").text()).toContain(t("refusals.too_many_imports"));
    expect((wrapper.get("#import-url").element as HTMLInputElement).value).toBe("https://example.org/a.pdf");
  });
});
