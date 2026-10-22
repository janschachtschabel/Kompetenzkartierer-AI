const FOCUSABLE = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

/** What can take focus inside `container`, in order: a disabled control cannot. */
export function focusablesIn(container: HTMLElement | null): HTMLElement[] {
  return Array.from(container?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
    (element) => !(element as HTMLButtonElement).disabled,
  );
}

/**
 * Keep Tab inside a modal: from its last control back to the first, and
 * Shift+Tab the other way round.
 *
 * One copy for every dialog. There were two, and the share dialog's counted a
 * disabled submit as the last stop, so Tab from the control before it walked
 * out of the modal into the page behind (old app, audit 2026-09-26, E-47).
 *
 * What precedes the first control counts as the start: a heading that takes
 * focus by script, once the share dialog has no share left to take back (old app, audit
 * 2026-10-01, G-44), is no stop of its own and led Shift+Tab out.
 */
export function trapTab(event: KeyboardEvent, container: HTMLElement | null): void {
  if (event.key !== "Tab") return;
  const focusable = focusablesIn(container);
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;
  const atStart =
    active === first || (!!active && !!(first.compareDocumentPosition(active) & Node.DOCUMENT_POSITION_PRECEDING));

  if (event.shiftKey && atStart) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
