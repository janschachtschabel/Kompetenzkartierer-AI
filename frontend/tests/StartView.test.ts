import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { t } from "@/i18n/de";
import { router } from "@/router";
import { clearSession, setSession } from "@/session";
import { refusalText } from "@/refusals";
import StartView from "@/views/StartView.vue";

function info(publicAccess: api.Info["public_access"]): api.Info {
  return { name: "Kompetenzkartierer-AI", version: "0.1.0", public_access: publicAccess };
}

async function render() {
  const wrapper = mount(StartView, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

beforeEach(async () => {
  vi.restoreAllMocks();
  api.clearToken();
  clearSession();
  await router.push("/");
});

describe("the start page for a visitor", () => {
  it("says that nothing is open without an account, and leads to the sign-in", async () => {
    vi.spyOn(api, "getInfo").mockResolvedValue(info("off"));

    const wrapper = await render();

    expect(wrapper.get("h1").text()).toBe(t("app.title"));
    expect(wrapper.text()).toContain(t("start.visitor.off"));
    expect(wrapper.get("a[href='/anmelden']").text()).toBe(t("start.signIn"));
  });

  it.each(["lookup", "search"] as const)("says what is open where PUBLIC_ACCESS is %s", async (access) => {
    vi.spyOn(api, "getInfo").mockResolvedValue(info(access));

    const wrapper = await render();

    expect(wrapper.get(".page-notice").text()).toContain(t(`start.visitor.${access}`));
  });

  it("says that it is loading meanwhile", async () => {
    vi.spyOn(api, "getInfo").mockReturnValue(new Promise(() => undefined));

    const wrapper = await render();

    expect(wrapper.get("[role=status]").text()).toBe(t("states.loading"));
  });

  it("says when the service cannot be asked, and asks again on request", async () => {
    const asked = vi.spyOn(api, "getInfo").mockRejectedValueOnce(new api.ApiError("network", 0));
    asked.mockResolvedValueOnce(info("off"));

    const wrapper = await render();
    expect(wrapper.get("[role=alert]").text()).toContain(t("states.offline"));

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(asked).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain(t("start.visitor.off"));
  });
});

describe("the start page for an account", () => {
  it("greets it by name and asks the service nothing", async () => {
    const asked = vi.spyOn(api, "getInfo");
    setSession({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });

    const wrapper = await render();

    expect(wrapper.get("h1").text()).toBe(t("start.welcome", { name: "Lehrkraft" }));
    expect(asked).not.toHaveBeenCalled();
  });
});


describe("the start page for an account whose load fails", () => {
  beforeEach(() => {
    api.setToken("kka_token");
  });

  it("says so, with a retry - never the visitor's page", async () => {
    // the database away: /me answers 503, /info would still answer
    const info = vi.spyOn(api, "getInfo").mockResolvedValue(infoOf("lookup"));
    const me = vi.spyOn(api, "getMe").mockRejectedValueOnce(new api.ApiError("server", 503, "service_unavailable"));
    me.mockResolvedValueOnce({ id: "0190-a", name: "Lehrkraft", roles: ["nutzer"] });

    const wrapper = await render();

    expect(wrapper.get("[role=alert]").text()).toContain(refusalText("service_unavailable") ?? "");
    expect(wrapper.text()).not.toContain(t("start.visitor.lookup"));
    expect(info).not.toHaveBeenCalled();

    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();

    expect(wrapper.get("h1").text()).toBe(t("start.welcome", { name: "Lehrkraft" }));
  });

  it("shows only that it is loading while the account is asked for", async () => {
    vi.spyOn(api, "getMe").mockReturnValue(new Promise(() => undefined));
    vi.spyOn(api, "getInfo").mockResolvedValue(infoOf("lookup"));

    const wrapper = await render();

    expect(wrapper.get("[role=status]").text()).toBe(t("states.loading"));
    expect(wrapper.text()).not.toContain(t("start.about"));
    expect(wrapper.find("a[href='/anmelden']").exists()).toBe(false);
  });
});

function infoOf(publicAccess: api.Info["public_access"]): api.Info {
  return { name: "Kompetenzkartierer-AI", version: "0.1.0", public_access: publicAccess };
}
