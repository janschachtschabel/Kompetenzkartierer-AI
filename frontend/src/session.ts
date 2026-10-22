// Who is signed in, for the parts of the UI that differ by role. Refs beside
// the token in api/http.ts rather than a store library.
//
// The state tells an account whose load failed from a visitor: "failed" keeps
// the error for the page to say, with a retry. Authorisation itself is the
// server's job - hiding an entry is convenience, never the guard.
import { computed, ref, type ComputedRef } from "vue";

import { getMe, getToken, type Me, type Role } from "@/api";

/** none: no account (a visitor, or signed out); loading; ready; failed: the token is held, its account not loaded. */
export type SessionState = "none" | "loading" | "ready" | "failed";

const current = ref<Me | null>(null);
const state = ref<SessionState>("none");
const failure = ref<unknown>(null);
// Bumped by every change of account: an answer to an older question is dropped
let generation = 0;
let loading: Promise<void> | null = null;

export const session: ComputedRef<Me | null> = computed(() => current.value);
export const sessionState: ComputedRef<SessionState> = computed(() => state.value);
export const sessionFailure: ComputedRef<unknown> = computed(() => failure.value);

export function hasRole(role: Role): boolean {
  return current.value?.roles.includes(role) ?? false;
}

/** The account the sign-in has already checked: it need not be asked for twice. */
export function setSession(me: Me): void {
  generation += 1;
  loading = null;
  current.value = me;
  state.value = "ready";
  failure.value = null;
}

export function clearSession(): void {
  generation += 1;
  loading = null;
  current.value = null;
  state.value = "none";
  failure.value = null;
}

/**
 * The account of the token, loaded once however many ask at the same time: the
 * shell, a guard and a page all ask on a fresh load. An answer that arrives
 * after the account changed - signed in as another, signed out, another token
 * held - is dropped. A 401 has led to the sign-in already (api/http.ts).
 */
export function ensureSession(): Promise<void> {
  const token = getToken();
  if (current.value || !token) return Promise.resolve();
  if (loading) return loading;
  const asked = generation;
  /**
   * Applies an answer that still belongs to the account held now. Signed in or
   * out meanwhile, it is dropped: that settled the state already. Only the token
   * changed, nobody settled it: the token held now is asked for, and those
   * waiting on this answer get that one.
   */
  const settle = (apply: () => void): Promise<void> | undefined => {
    if (generation !== asked) return;
    if (getToken() !== token) {
      clearSession();
      return ensureSession();
    }
    apply();
  };
  state.value = "loading";
  failure.value = null;
  loading = getMe().then(
    (me) => settle(() => setSession(me)),
    (error: unknown) =>
      settle(() => {
        loading = null;
        state.value = "failed";
        failure.value = error;
      }),
  );
  return loading;
}
