import { describe, expect, it } from "vitest";

import { t } from "@/i18n/de";
import { DESTINATIONS, type Destination, visibleDestinations } from "@/navigation";
import { router } from "@/router";

const TABLE: readonly Destination[] = [
  { name: "start", label: "app.nav.start", icon: "map" },
  { name: "konten", label: "app.nav.start", icon: "map", roles: ["admin"] },
  { name: "redaktion", label: "app.nav.start", icon: "map", roles: ["admin", "redaktion"] },
];

describe("the navigation", () => {
  it("shows a destination for everyone signed in to every account", () => {
    expect(visibleDestinations(["nutzer"], TABLE).map(({ name }) => name)).toEqual(["start"]);
  });

  it("shows a destination to the roles it names, and to no other", () => {
    expect(visibleDestinations(["redaktion"], TABLE).map(({ name }) => name)).toEqual(["start", "redaktion"]);
    expect(visibleDestinations(["admin"], TABLE).map(({ name }) => name)).toEqual(["start", "konten", "redaktion"]);
  });

  it("names every destination of the app in the catalogue", () => {
    for (const destination of DESTINATIONS) expect(t(destination.label)).not.toBe(destination.label);
  });

  it("leads only to pages the router has", () => {
    for (const destination of DESTINATIONS) expect(router.hasRoute(destination.name)).toBe(true);
  });
});
