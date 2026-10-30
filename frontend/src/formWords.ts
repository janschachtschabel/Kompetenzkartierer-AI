// A document's fields in words (backend app/api/profiles.py, FormOut): a list field's value by the label the
// sector's form gives it, as the tree and its detail show it. A value the form no longer offers - retired
// from the vocabulary since it was written - stands as its IRI rather than as nothing. Read beside another
// value (a conflict, a draft kept), an empty one says so.
import type { FieldValue, FormField } from "@/api";
import { t } from "@/i18n/de";
import { sameValue } from "@/rowDraft";

/** The label of value ``iri`` of the field ``key``; the IRI itself where the form offers none. */
export function valueLabel(fields: readonly FormField[], key: string, iri: string): string {
  const field = fields.find((one) => one.key === key);
  return field?.values?.find((offered) => offered.iri === iri)?.label ?? iri;
}

/** The field's value as text: a list's values by their labels, a text itself (a text field offers no
 * values to name it by), none as nothing. */
export function valueText(fields: readonly FormField[], key: string, value: FieldValue): string {
  if (value === null) return "";
  return (Array.isArray(value) ? value : [value]).map((one) => valueLabel(fields, key, one)).join(", ");
}

/** The field's value to be read beside another: as `valueText`, an empty one as "leer". */
export function shownValue(fields: readonly FormField[], key: string, value: FieldValue | undefined): string {
  return value === undefined || sameValue(value, null) ? t("documents.tree.conflict.empty") : valueText(fields, key, value);
}
