// Where the navigation leads, and for whom. A destination without roles is for
// every account; one with roles for those holding one of them. The server
// refuses the routes' requests anyway: this only keeps the navigation honest.
import type { Role } from "@/api";
import type { IconName } from "@/icons";

export interface Destination {
  /** The route's name. */
  name: string;
  /** The catalogue key of its label. */
  label: string;
  icon: IconName;
  roles?: readonly Role[];
}

export const DESTINATIONS: readonly Destination[] = [
  { name: "start", label: "app.nav.start", icon: "map" },
  { name: "sources", label: "app.nav.sources", icon: "document" },
];

export function visibleDestinations(
  roles: readonly Role[],
  destinations: readonly Destination[] = DESTINATIONS,
): Destination[] {
  return destinations.filter((destination) => !destination.roles || destination.roles.some((role) => roles.includes(role)));
}
