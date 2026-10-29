// The register's values in words: the catalogue holds a word for each value the
// backend knows (tests/registerLabels.test.ts); a value it has none for yet is
// shown as it is, rather than as an empty cell.

/** The word for `value` in `words`, or the value itself. */
export function word(words: Readonly<Record<string, string>>, value: string): string {
  return words[value] ?? value;
}

/** A concept's word by its notation - the IRI after the scheme's `prefix` - else the IRI as it is: a concept
 * the vocabulary no longer holds, or one of another scheme, is not shown as a stray notation. */
export function conceptWord(words: Readonly<Record<string, string>>, prefix: string, iri: string): string {
  const notation = iri.startsWith(prefix) ? iri.slice(prefix.length) : "";
  return Object.hasOwn(words, notation) ? words[notation] : iri;
}
