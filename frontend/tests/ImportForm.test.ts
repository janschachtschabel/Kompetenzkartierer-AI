import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type ImportStarted } from "@/api";
import ImportForm from "@/components/ImportForm.vue";
import { isolate } from "@/bidi";
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
    expect(wrapper.get("#import-status").text()).toBe(t("sources.import.started", { title: isolate("lehrplan") }));
    expect(wrapper.emitted("imported")?.[0]).toEqual([STARTED, "https://example.org/lehrplan.pdf"]);
    expect((wrapper.get("#import-url").element as HTMLInputElement).value).toBe("");
  });

  it("names an entry without a title by its address: its title waits for the file", async () => {
    vi.spyOn(api, "importSource").mockResolvedValue({ ...STARTED, source: { ...STARTED.source, title: "" } });
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("https://example.org/lehrplan.pdf");

    await submit(wrapper);

    expect(wrapper.get("#import-status").text()).toBe(
      t("sources.import.started", { title: isolate("https://example.org/lehrplan.pdf") }),
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

  it.each([
    ["https://example.org/mein lehrplan.pdf", "sources.import.errors.spaces"],
    ["https://example.org/a\tb.pdf", "sources.import.errors.spaces"],
    ["https://name:kennwort@example.org/a.pdf", "sources.import.errors.credentials"],
    ["https://name@example.org/a.pdf", "sources.import.errors.credentials"],
  ])("says why %s is not fetched, before sending it", async (address, key) => {
    // the server refuses these too (url_invalid); a password is not even to reach it
    const start = vi.spyOn(api, "importSource");
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue(address);

    await submit(wrapper);

    expect(start).not.toHaveBeenCalled();
    expect(wrapper.get("#import-error").text()).toContain(t(key));
  });

  it("says the server's refusal of the address at the address field", async () => {
    vi.spyOn(api, "importSource").mockRejectedValue(new ApiError("server", 422, "url_invalid", "no"));
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("https://example.org/a.pdf");

    await submit(wrapper);

    const field = wrapper.get("#import-url");
    expect(field.attributes("aria-invalid")).toBe("true");
    expect(field.attributes("aria-describedby")).toContain("import-error");
  });

  it.each(["title_invalid", "title_too_long"])("says a refusal of the title (%s) at the title field", async (code) => {
    vi.spyOn(api, "importSource").mockRejectedValue(new ApiError("server", 422, code, "no"));
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("https://example.org/a.pdf");
    await wrapper.get("#import-title").setValue("Titel");

    await submit(wrapper);

    const title = wrapper.get("#import-title");
    expect(title.attributes("aria-invalid")).toBe("true");
    expect(title.attributes("aria-describedby")).toContain("import-error");
    expect(wrapper.get("#import-url").attributes("aria-invalid")).toBeUndefined();
    expect(wrapper.get("#import-error").text()).toContain(t(`refusals.${code}`));
  });

  it("says the same refusal again, so a screen reader reads it again", async () => {
    const wrapper = mount(ImportForm);

    await submit(wrapper);
    const first = wrapper.get("#import-error").element.textContent;
    await submit(wrapper);

    expect(wrapper.get("#import-error").element.textContent).not.toBe(first);
  });

  it("sends once, however often the button is pressed while it sends", async () => {
    let finish: (started: ImportStarted) => void = () => {};
    const start = vi.spyOn(api, "importSource").mockImplementation(() => new Promise((resolve) => (finish = resolve)));
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("https://example.org/a.pdf");

    await wrapper.get("form").trigger("submit");
    await wrapper.get("form").trigger("submit");
    finish(STARTED);
    await flushPromises();

    expect(start).toHaveBeenCalledTimes(1);
  });

  it("sets a title apart from the sentence around it, whichever way it is written", async () => {
    vi.spyOn(api, "importSource").mockResolvedValue({ ...STARTED, source: { ...STARTED.source, title: "منهج" } });
    const wrapper = mount(ImportForm);
    await wrapper.get("#import-url").setValue("https://example.org/a.pdf");

    await submit(wrapper);

    expect(wrapper.get("#import-status").text()).toContain(isolate("منهج"));
  });
});
