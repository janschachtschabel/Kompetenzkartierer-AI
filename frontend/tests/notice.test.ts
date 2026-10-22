import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import { ApiError } from "@/api";
import NoticeText from "@/components/NoticeText.vue";
import { t } from "@/i18n/de";
import { failureNotice } from "@/notice";
import { refusalText } from "@/refusals";

describe("a failure's notice", () => {
  it("says a refusal the page knows in German, without the server's English", () => {
    const error = new ApiError("forbidden", 403, "forbidden", "This needs another role.");

    expect(failureNotice(error, "Das Konto wurde nicht angelegt.")).toEqual({
      text: "Das Konto wurde nicht angelegt.",
      explanation: refusalText("forbidden"),
      failed: true,
    });
  });

  it("quotes the server's sentence as the reason for a refusal it does not know", () => {
    const error = new ApiError("server", 409, "conflict", "An account of this name exists.");

    expect(failureNotice(error, "Das Konto wurde nicht angelegt.")).toEqual({
      text: "Das Konto wurde nicht angelegt.",
      reason: "An account of this name exists.",
      failed: true,
    });
  });

  it("says how long to wait where the answer names it", () => {
    const error = new ApiError("server", 429, "too_many_requests", "Slow down.", {}, 30);

    expect(failureNotice(error).explanation).toBe(t("states.tooManyRequests", { count: 30 }));
  });

  it("lets the caller name the limit a 429 hit", () => {
    const error = new ApiError("server", 429, "too_many_requests", "Slow down.", {}, 30);

    const notice = failureNotice(error, "x", { tooManyRequests: (seconds) => `Grenze, ${String(seconds)} s` });

    expect(notice.explanation).toBe("Grenze, 30 s");
  });

  it("says that the server could not be reached", () => {
    expect(failureNotice(new ApiError("network", 0)).explanation).toBe(t("states.offline"));
  });

  it("falls back to the general sentence, and to it alone for anything else", () => {
    expect(failureNotice(new Error("boom"))).toEqual({ text: t("states.errorTitle"), failed: true });
  });
});

describe("NoticeText", () => {
  it("shows the page's words after the sentence, unquoted", () => {
    const wrapper = mount(NoticeText, { props: { notice: { text: "Satz.", explanation: "Erklärung." } } });

    expect(wrapper.text()).toBe("Satz. Erklärung.");
    expect(wrapper.find("q").exists()).toBe(false);
  });

  it("quotes the server's reason and marks it as English", () => {
    // WCAG 3.1.2: a passage in another language is marked, or a screen reader
    // reads it with German sounds.
    const wrapper = mount(NoticeText, { props: { notice: { text: "Satz.", reason: "Why." } } });

    expect(wrapper.find("q").attributes("lang")).toBe("en");
    expect(wrapper.find("q").text()).toBe("Why.");
  });

  it("renders nothing for no notice, so a live region can hold it from the start", () => {
    expect(mount(NoticeText, { props: { notice: null } }).text()).toBe("");
  });
});
