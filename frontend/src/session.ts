// Who is signed in, for the parts of the UI that differ by role. One ref beside
// the token in api/http.ts rather than a store library.
//
// A failed load leaves the session empty, so the UI shows nothing an account
// may not see; the page that loads data says what failed. Authorisation itself
// is the server's job - hiding an entry is convenience, never the guard.
import { computed, ref, type ComputedRef } from "vue";

import { getMe, getToken, type Me, type Role } from "@/api";

const current = ref<Me | null>(null);
let loading: Promise<void> | null = null;

export const session: ComputedRef<Me | null> = computed(() => current.value);

export function hasRole(role: Role): boolean {
  return current.value?.roles.includes(role) ?? false;
}

/** The account the sign-in has already checked: it need not be asked for twice. */
export function setSession(me: Me): void {
  current.value = me;
}

export function clearSession(): void {
  current.value = null;
}

/**
 * The account of the token, loaded once however many ask at the same time:
 * the shell, a guard and a page all ask on a fresh load.
 */
export function ensureSession(): Promise<void> {
  if (current.value || !getToken()) return Promise.resolve();
  loading ??= getMe()
    .then((me) => setSession(me))
    .catch(() => clearSession()) // a 401 has led to the sign-in already; anything else, the page says
    .finally(() => {
      loading = null;
    });
  return loading;
}
