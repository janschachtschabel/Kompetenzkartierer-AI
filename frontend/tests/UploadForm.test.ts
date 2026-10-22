import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type SourceOut } from "@/api";
import UploadForm from "@/components/UploadForm.vue";
import { t } from "@/i18n/de";

const MIB = 2 ** 20;

function stored(title: string): SourceOut {
  return {
    id: "s1",
    title,
    provenance: "upload",
    rights_status: "unklar",
    register_status: "acquired",
    file: { name: "lehrplan.pdf", mime: "application/pdf", size: 8 },
  };
}

function pdf(size?: number): File {
  const file = new File(["%PDF-1.7"], "lehrplan.pdf", { type: "application/pdf" });
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
}

async function choose(wrapper: VueWrapper, file: File): Promise<void> {
  const input = wrapper.get("input[type=file]");
  Object.defineProperty(input.element, "files", { value: [file], configurable: true });
  await input.trigger("change");
}

async function submit(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("form").trigger("submit");
  await flushPromises();
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("the upload form", () => {
  it("sends the chosen file with its title, says so and hands the entry on", async () => {
    const upload = vi.spyOn(api, "uploadSource").mockResolvedValue(stored("Lehrplan Physik"));
    const wrapper = mount(UploadForm, { props: { maxUploadMb: 50 } });
    const file = pdf();
    await choose(wrapper, file);
    await wrapper.get("#upload-title").setValue("Lehrplan Physik");

    await submit(wrapper);

    expect(upload).toHaveBeenCalledWith(file, "Lehrplan Physik");
    expect(wrapper.get("#upload-status").text()).toBe(t("sources.upload.done", { title: "Lehrplan Physik" }));
    expect(wrapper.emitted("uploaded")?.[0]).toEqual([stored("Lehrplan Physik")]);
    // ready for the next one
    expect((wrapper.get("#upload-title").element as HTMLInputElement).value).toBe("");
  });

  it("names the limit beside the file field", () => {
    const wrapper = mount(UploadForm, { props: { maxUploadMb: 50 } });

    expect(wrapper.get("#upload-file-hint").text()).toContain("50 MB");
  });

  it("asks for a file before sending anything, at the file field", async () => {
    const upload = vi.spyOn(api, "uploadSource");
    const wrapper = mount(UploadForm, { props: { maxUploadMb: 50 } });

    await submit(wrapper);

    expect(upload).not.toHaveBeenCalled();
    expect(wrapper.get("#upload-error").text()).toContain(t("sources.upload.errors.missing"));
    const input = wrapper.get("#upload-file");
    expect(input.attributes("aria-invalid")).toBe("true");
    expect(input.attributes("aria-describedby")).toContain("upload-error");
  });

  it("refuses a file over the limit before sending its megabytes", async () => {
    const upload = vi.spyOn(api, "uploadSource");
    const wrapper = mount(UploadForm, { props: { maxUploadMb: 50 } });
    await choose(wrapper, pdf(50 * MIB + 1));

    await submit(wrapper);

    expect(upload).not.toHaveBeenCalled();
    expect(wrapper.get("#upload-error").text()).toContain(t("sources.upload.errors.tooLarge", { limit: 50 }));
  });

  it("sends any file where the limit is not known: the server decides", async () => {
    const upload = vi.spyOn(api, "uploadSource").mockResolvedValue(stored("lehrplan"));
    const wrapper = mount(UploadForm);
    await choose(wrapper, pdf(500 * MIB));

    await submit(wrapper);

    expect(upload).toHaveBeenCalled();
    expect(wrapper.get("#upload-file-hint").text()).not.toContain("MB");
  });

  it("says a refusal in its own words, at the field it is about, and keeps what was typed", async () => {
    vi.spyOn(api, "uploadSource").mockRejectedValue(new ApiError("server", 422, "title_too_long", "too long"));
    const wrapper = mount(UploadForm, { props: { maxUploadMb: 50 } });
    await choose(wrapper, pdf());
    await wrapper.get("#upload-title").setValue("Ein Titel");

    await submit(wrapper);

    expect(wrapper.get("#upload-error").text()).toContain(t("refusals.title_too_long"));
    expect(wrapper.get("#upload-title").attributes("aria-invalid")).toBe("true");
    expect(wrapper.get("#upload-file").attributes("aria-invalid")).toBeUndefined();
    expect((wrapper.get("#upload-title").element as HTMLInputElement).value).toBe("Ein Titel");
  });

  it("says a body cut at the server's limit as a file too large", async () => {
    vi.spyOn(api, "uploadSource").mockRejectedValue(new ApiError("server", 413, "content_too_large"));
    const wrapper = mount(UploadForm, { props: { maxUploadMb: 50 } });
    await choose(wrapper, pdf());

    await submit(wrapper);

    expect(wrapper.get("#upload-error").text()).toContain(t("sources.upload.errors.tooLarge", { limit: 50 }));
  });

  it("sends once, however often the button is pressed while it sends", async () => {
    let finish: (source: SourceOut) => void = () => {};
    const upload = vi
      .spyOn(api, "uploadSource")
      .mockImplementation(() => new Promise((resolve) => (finish = resolve)));
    const wrapper = mount(UploadForm, { props: { maxUploadMb: 50 } });
    await choose(wrapper, pdf());

    await wrapper.get("form").trigger("submit");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("#upload-status").text()).toBe(t("sources.upload.busy"));
    expect(wrapper.get("button[type=submit]").attributes("aria-disabled")).toBe("true");
    finish(stored("lehrplan"));
    await flushPromises();

    expect(upload).toHaveBeenCalledTimes(1);
  });
});
