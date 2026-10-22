// A reader's text set inside a sentence of the page: a title, an address. Its
// own direction must not turn the sentence around it - an Arabic title in a
// German sentence moved the full stop to the wrong end. The isolates are what
// <bdi> is in markup, for text that is no markup: a live region's sentence, a
// status line.
const FIRST_STRONG_ISOLATE = String.fromCodePoint(0x2068);
const POP_DIRECTIONAL_ISOLATE = String.fromCodePoint(0x2069);

/** `text` set apart from the sentence it is put into. */
export function isolate(text: string): string {
  return `${FIRST_STRONG_ISOLATE}${text}${POP_DIRECTIONAL_ISOLATE}`;
}
