import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type CurriculumDocument, type Me } from "@/api";
import RevisionNotice from "@/components/RevisionNotice.vue";
import { momentFormat, t } from "@/i18n/de";
import { refusalText } from "@/refusals";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";

import { violations } from "./axe";
import { documentOf } from "./documentFixtures";

let shown: VueWrapper | null = null;

const EDITOR: Me = { id: "a2", name: "Redakteurin", roles: ["redaktion"] };
const OWNER: Me = { id: "a1", name: "Eigentümerin", roles: ["nutzer"] };
const FROZEN = documentOf({ revision: 2, iri: "https://example.org/kk/doc/x", frozen_at: "2026-10-31T10:00:00Z" });
const COPY = documentOf({ id: "d3", revision: 3, iri: FROZEN.iri, copy_of: "d1" });

function notice(document: CurriculumDocument, me: Me = EDITOR, copied = false): VueWrapper {
  setSession(me);
  shown = mount(RevisionNotice, {
    props: { document, copied },
    global: { plugins: [router] },
    attachTo: globalThis.document.body,
  });
  return shown;
}

const copyButton = (wrapper: VueWrapper) => wrapper.get("[data-test=copy]");

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  shown?.unmount();
  shown = null;
  globalThis.document.body.innerHTML = "";
  clearSession();
});

describe("the notice of a frozen document", () => {
  it("says when it was frozen and as which revision, and offers an editor a draft copy", async () => {
    const wrapper = notice(FROZEN);

    const date = momentFormat.format(new Date(FROZEN.frozen_at as string));
    const line = t("documents.page.revision.frozen", { date, revision: 2 });
    expect(wrapper.text()).toContain(line);
    expect(wrapper.text()).toContain(t("documents.page.revision.iri", { iri: "https://example.org/kk/doc/x" }));
    // a region named by its first line: focused, it says what it is
    const root = wrapper.get(".revision-notice");
    expect(root.attributes("role")).toBe("region");
    expect(globalThis.document.getElementById(root.attributes("aria-labelledby") ?? "")?.textContent).toBe(line);
    expect(wrapper.text()).toContain(t("documents.page.revision.frozenText"));
    const button = copyButton(wrapper);
    expect(button.text()).toBe(t("documents.page.revision.copy"));
    expect(globalThis.document.getElementById(button.attributes("aria-describedby") ?? "")?.textContent).toContain(
      t("documents.page.revision.frozenText"),
    );
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("offers no copy to whom is no editor", () => {
    expect(notice(FROZEN, OWNER).find("[data-test=copy]").exists()).toBe(false);
  });

  it("opens the draft copy once it is made, its page told so", async () => {
    vi.spyOn(api, "copyDocument").mockResolvedValue(COPY);
    const push = vi.spyOn(router, "push").mockResolvedValue(undefined);
    const wrapper = notice(FROZEN);

    await copyButton(wrapper).trigger("click");
    await flushPromises();

    expect(api.copyDocument).toHaveBeenCalledWith("d1");
    expect(push).toHaveBeenCalledWith({ name: "document", params: { id: "d3" }, state: { copied: true } });
  });

  it("names the draft open already, with the way to it where the server names it", async () => {
    vi.spyOn(api, "copyDocument")
      .mockRejectedValueOnce(new ApiError("server", 409, "draft_open", "Open.", { document_id: "d9" }))
      .mockRejectedValueOnce(new ApiError("server", 409, "draft_open"));
    const wrapper = notice(FROZEN);

    await copyButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("draft_open"));
    expect(wrapper.get("[data-test=open-draft]").attributes("href")).toBe("/dokumente/d9");
    expect(await violations(wrapper.html())).toEqual([]);

    await copyButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("draft_open"));
    expect(wrapper.find("[data-test=open-draft]").exists()).toBe(false);
  });

  it("lets the way to an open draft go with the next answer", async () => {
    vi.spyOn(api, "copyDocument")
      .mockRejectedValueOnce(new ApiError("server", 409, "draft_open", "Open.", { document_id: "d9" }))
      .mockRejectedValueOnce(new ApiError("server", 409, "not_latest"));
    const wrapper = notice(FROZEN);

    await copyButton(wrapper).trigger("click");
    await flushPromises();
    await copyButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("not_latest"));
    expect(wrapper.find("[data-test=open-draft]").exists()).toBe(false);
  });

  it("says a frozen copy as frozen, not as a draft", () => {
    const wrapper = notice({ ...COPY, frozen_at: "2026-10-31T11:00:00Z" });

    expect(wrapper.find("[data-test=copy]").exists()).toBe(true);
    expect(wrapper.find("[data-test=copy-of]").exists()).toBe(false);
  });

  it("says another refusal, and has a document no longer frozen read again", async () => {
    vi.spyOn(api, "copyDocument")
      .mockRejectedValueOnce(new ApiError("server", 409, "not_latest"))
      .mockRejectedValueOnce(new ApiError("server", 409, "not_frozen"));
    const wrapper = notice(FROZEN);

    await copyButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("not_latest"));
    expect(wrapper.emitted("changed")).toBeUndefined();
    await copyButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("says another failure as one", async () => {
    vi.spyOn(api, "copyDocument").mockRejectedValue(new ApiError("network", 0));
    const wrapper = notice(FROZEN);

    await copyButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain(t("documents.page.revision.copyFailed"));
  });

  it("copies nothing more while it copies", async () => {
    const sent = vi.spyOn(api, "copyDocument").mockReturnValue(new Promise(() => {}));
    const wrapper = notice(FROZEN);

    await copyButton(wrapper).trigger("click");
    await copyButton(wrapper).trigger("click");

    expect(sent).toHaveBeenCalledTimes(1);
    expect(copyButton(wrapper).attributes("aria-disabled")).toBe("true");
  });

  it("takes the keyboard where the page sends it", () => {
    const wrapper = notice(FROZEN);

    (wrapper.vm as unknown as { focus: () => void }).focus();

    expect(globalThis.document.activeElement).toBe(wrapper.get(".revision-notice").element);
  });
});

describe("the notice of a draft copy", () => {
  it("says which revision it copies, with the way to it, and what is to do", async () => {
    const wrapper = notice(COPY);

    expect(wrapper.text()).toContain(t("documents.page.revision.draft", { revision: 2 }));
    const root = wrapper.get(".revision-notice");
    expect(globalThis.document.getElementById(root.attributes("aria-labelledby") ?? "")?.textContent).toBe(
      t("documents.page.revision.draft", { revision: 2 }),
    );
    expect(wrapper.text()).toContain(t("documents.page.revision.draftText"));
    expect(wrapper.get("[data-test=copy-of]").attributes("href")).toBe("/dokumente/d1");
    expect(wrapper.find("[data-test=copy]").exists()).toBe(false);
    expect(await violations(wrapper.html())).toEqual([]);
  });

  it("says once that it was made, where the page was opened for that", async () => {
    const wrapper = notice(COPY, EDITOR, true);
    await flushPromises();

    expect(wrapper.get("[role=status]").text()).toBe(t("documents.page.revision.copied"));
  });
});

describe("a document neither frozen nor copied", () => {
  it("has no notice", () => {
    expect(notice(documentOf()).find(".page-notice").exists()).toBe(false);
  });
});
