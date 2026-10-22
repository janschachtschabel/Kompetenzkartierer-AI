// The register's values in words: the catalogue holds a word for each value the
// backend knows (tests/registerLabels.test.ts); a value it has none for yet is
// shown as it is, rather than as an empty cell.

/** The word for `value` in `words`, or the value itself. */
export function word(words: Readonly<Record<string, string>>, value: string): string {
  return words[value] ?? value;
}
