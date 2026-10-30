// A row of a document's tree as its form edits it (plan M1 9.8, Paket 9c2 K9/K10): each field of the form as a
// string - a text, a value's IRI - or, for a field of many, an array; none as empty. Compared as the server
// stores them: a blank text is none, any other kept as written, its edges too; a list a set. A change names
// only the fields changed, a list in the order the form lists its values. A list whose values refine another
// field's (their `broader`: a node type its function, a subkind its kind) offers those under that field's
// value chosen.
import type { EditFields, FieldValue, FormField, FormValue } from "@/api";

/** A row's values by the keys of its form's fields. */
export type Draft = Record<string, string | string[]>;

export function draftOf(fields: readonly FormField[], values: Record<string, FieldValue | undefined>): Draft {
  return Object.fromEntries(
    fields.map((field) => {
      const value = values[field.key];
      if (field.many) return [field.key, Array.isArray(value) ? [...value] : []];
      return [field.key, typeof value === "string" ? value : ""];
    }),
  );
}

function normal(value: FieldValue | undefined): string | string[] | null {
  if (Array.isArray(value)) return value.length ? [...value].sort() : null;
  return typeof value === "string" && value.trim() ? value : null;
}

export function sameValue(a: FieldValue | undefined, b: FieldValue | undefined): boolean {
  return JSON.stringify(normal(a)) === JSON.stringify(normal(b));
}

/** The fields `draft` changes from `before`, as a change sends them. */
export function changedFields(fields: readonly FormField[], before: Draft, draft: Draft): EditFields {
  const changed: EditFields = {};
  for (const field of fields) {
    const value = draft[field.key];
    if (value === undefined || sameValue(before[field.key], value)) continue;
    if (Array.isArray(value)) changed[field.key] = inFormOrder(field, value);
    else changed[field.key] = value.trim() ? value : null;
  }
  return changed;
}

// the values the form knows in its order, then any it does not know as they came
function inFormOrder(field: FormField, chosen: readonly string[]): string[] {
  const known = (field.values ?? []).map((value) => value.iri).filter((iri) => chosen.includes(iri));
  return [...known, ...chosen.filter((iri) => !known.includes(iri))];
}

/** The field whose values `field`'s values refine, where they refine any. */
export function parentField(fields: readonly FormField[], field: FormField): FormField | null {
  const broader = new Set((field.values ?? []).flatMap((value) => value.broader));
  if (!broader.size) return null;
  return fields.find((other) => other !== field && (other.values ?? []).some((value) => broader.has(value.iri))) ?? null;
}

/**
 * The values `field` offers in `draft`: under its parent's value chosen, every one while none is chosen. The
 * value it holds stays among them, though no longer under the parent's: the server says why it refuses it.
 */
export function offeredValues(fields: readonly FormField[], field: FormField, draft: Draft): FormValue[] {
  const values = field.values ?? [];
  const parent = parentField(fields, field);
  const chosen = parent ? draft[parent.key] : "";
  if (typeof chosen !== "string" || !chosen) return values;
  const held = draft[field.key];
  return values.filter((value) => value.broader.includes(chosen) || value.iri === held);
}
