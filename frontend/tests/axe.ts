/**
 * Running axe over a mounted component.
 *
 * axe-core directly rather than a wrapper: `vitest-axe` has sat at 0.1.0 with an
 * unreleased 1.0 for years, and the whole of it is the twenty lines below.
 *
 * What this adds to the ARIA assertions the component tests already make: those
 * check the attributes somebody thought to check. axe checks the rules -- a
 * label pointing at no element, a heading level skipped, a control with no
 * accessible name -- including the ones nobody remembered.
 *
 * What it does not add: axe finds roughly a third of what a real audit finds. It
 * cannot tell whether an alt text is *right*, whether the focus order makes
 * sense, or whether the wording means anything. Keyboard walks and a screen
 * reader stay necessary.
 */
import axe, { type Result, type RunOptions } from "axe-core";

/**
 * The accessibility violations axe finds in `html`.
 *
 * jsdom computes no layout, so the rules that need geometry -- contrast, target
 * size -- cannot run here and are disabled rather than left to report nothing:
 * a rule that silently never fires reads as coverage. Both are checked against
 * the real browser instead (tests/contrast.test.ts, and the measurements in the
 * audit).
 */
export async function violations(html: string, options: RunOptions = {}): Promise<Result[]> {
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  try {
    const result = await axe.run(host, {
      rules: {
        "color-contrast": { enabled: false },
        "target-size": { enabled: false },
      },
      ...options,
    });
    return result.violations;
  } finally {
    host.remove();
  }
}

/** A one-line summary per violation, so a failure names what to fix. */
export function describeViolations(found: Result[]): string {
  return found.map((v) => `${v.id}: ${v.help} (${v.nodes.length}x)`).join("\n");
}
