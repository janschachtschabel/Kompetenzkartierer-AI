import { focusablesIn } from "@/focusTrap";

/**
 * Keep the keyboard's place when the element that has focus is taken out of the
 * page.
 *
 * A confirmed deletion returned focus to the row's delete button, the reload
 * then removed the row, and the browser moved focus to <body>: the next Tab
 * started again at the top of the page, before the navigation (old app, audit
 * 2026-09-26, E-104). Every view that removes what was just used had the same
 * gap, so it is closed once, here: when the last focused element leaves the
 * page and nothing else took focus meanwhile, `fallback` gets it.
 *
 * Unless a modal dialog is open: then its first control does. The page behind
 * the scrim is out of reach for Escape and the dialog's Tab trap, and a share
 * taken back in the share dialog sent the keyboard there (old app, audit 2026-10-01,
 * G-44).
 *
 * A control that is disabled while it has focus loses it the same way, though
 * it stays in the page: Chromium leaves focus on <body> (old app, audit 2026-10-01,
 * 7.9-7). A control that is only busy says so with `aria-disabled` and keeps
 * focus; this catches the ones that become impossible.
 *
 * Returns the function that stops watching.
 */
export function keepFocusInPage(fallback: () => HTMLElement | null): () => void {
  let focused: Element | null = null;

  const remember = (event: FocusEvent) => {
    focused = event.target instanceof Element ? event.target : null;
  };

  const rescue = () => {
    if (!focused || (focused.isConnected && !focused.matches(":disabled"))) return;
    const active = document.activeElement;
    // <body> is where a browser leaves focus; some engines still name the
    // removed or disabled element for a moment.
    if (active && active !== document.body && active !== focused) return;
    focused = null;
    (openModalControl() ?? fallback())?.focus();
  };

  document.addEventListener("focusin", remember);
  const observer = new MutationObserver(rescue);
  // A disabled control stays in the page: only its attribute says it happened.
  observer.observe(document.body, { childList: true, subtree: true, attributeFilter: ["disabled"] });

  return () => {
    document.removeEventListener("focusin", remember);
    observer.disconnect();
  };
}

/**
 * Whether nobody holds the keyboard: it rests on <body>, or on the page's
 * main region, where a navigation puts it. A page that offers to focus
 * something once it has loaded asks this first; the person may have tabbed
 * to the search box meanwhile, and typing there was cut off when the tree
 * arrived (recheck of the round "Sichtung").
 */
export function focusIsFree(): boolean {
  const active = document.activeElement;
  return !active || active === document.body || active.id === "main";
}

/**
 * Send the keyboard to the element with this id, which the browser scrolls
 * into view; nothing happens where there is none. Not the address's fragment:
 * the router would take that for a move.
 */
export function focusById(id: string): void {
  document.getElementById(id)?.focus();
}

/** The first control of the open modal dialog -- the last one in the page, where several are. */
function openModalControl(): HTMLElement | undefined {
  const modals = document.querySelectorAll<HTMLElement>("[aria-modal='true']");
  return modals.length > 0 ? focusablesIn(modals[modals.length - 1])[0] : undefined;
}
