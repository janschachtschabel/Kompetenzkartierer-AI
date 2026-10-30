// What the panel of a document's tree is headed (plan M1 9.8, Paket 9c2b L4): the row chosen - a node by its
// code and title, as the tree names it -, or a row being added and where it goes, at the top or under the node
// chosen.
import type { Row } from "@/documentTree";
import { t } from "@/i18n/de";
import type { CreateTarget } from "@/rowCreate";

function nodeName(row: Row | null): string {
  if (row?.kind !== "node") return t("documents.tree.untitled");
  const { code, original_title: title } = row.node.fields;
  return [code, title].filter((part) => typeof part === "string" && part).join(" ") || t("documents.tree.untitled");
}

export function panelHeading(row: Row | null, creating: CreateTarget | null): string {
  if (creating?.kind === "statement") return t("documents.tree.create.headingStatement", { name: nodeName(row) });
  if (creating) {
    return creating.parent === null
      ? t("documents.tree.create.headingTop")
      : t("documents.tree.create.headingChild", { name: nodeName(row) });
  }
  if (!row) return t("documents.tree.detail.heading");
  if (row.kind === "statement") return t("documents.tree.detail.statement");
  return t("documents.tree.detail.node", { name: nodeName(row) });
}
