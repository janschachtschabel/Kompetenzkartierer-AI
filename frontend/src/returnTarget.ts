/** The address parameter that says where the sign-in sends a visitor back to. */
export const RETURN_PARAM = "ziel";

/**
 * A place to go back to after signing in, or null.
 *
 * Only a path inside this app: the value comes from the address, which anybody
 * can write, and a sign-in that forwards to another site is an open redirect.
 * Browsers read both "//host" and "/\host" as another host. The sign-in itself
 * is no destination.
 */
export function returnTarget(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return null;
  // in any case, as the router matches paths
  if (/^\/anmelden(?:[/?#]|$)/i.test(value)) return null;
  return value;
}
