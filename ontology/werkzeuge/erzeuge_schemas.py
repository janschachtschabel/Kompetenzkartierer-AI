"""Generate the JSON schemas of the extraction stages from the core vocabulary.

Every enum is taken from the skos:notation values of a cv: scheme, so the
schemas cannot drift from the ontology. The schemas are strict-mode
compatible (OpenAI structured outputs): every object lists all properties as
required and forbids additional ones; optional values are nullable. Enum
nodes carry "x-cv-scheme" (and "x-cv-subset" for deliberate subsets) so that
pruefung/pruefe.py can re-check them.

The model never returns confidences, page numbers or IRIs it cannot know: it
returns block IDs from stage X0, verbatim text, and choices from lists that
the prompt numbers. Profile-specific values (node types, statement
subkinds, document types) are strings checked against the active profile.

Usage: python -I erzeuge_schemas.py <ergebnis-dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import SKOS

CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
VOCAB: Graph | None = None

# Subset for the edge decision in G1: at most ten relations the model may
# choose; official relations (recognizedFor, qualifiesFor) and structural ones
# come from rules, never from the model.
G1_RELATIONS = ["exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch",
                "buildsOn", "requires", "revisits", "concretizes", "noCorrespondence"]


def notations(scheme: str) -> list[str]:
    values = sorted({str(n) for c in VOCAB.subjects(SKOS.inScheme, CV[scheme]) for n in VOCAB.objects(c, SKOS.notation)})
    if not values:
        raise ValueError(f"scheme cv:{scheme} has no notations")
    return values


def enum(scheme: str, description: str, nullable: bool = False, subset: list[str] | None = None) -> dict:
    values = subset if subset is not None else notations(scheme)
    if subset is not None and not set(subset) <= set(notations(scheme)):
        raise ValueError(f"subset not in cv:{scheme}: {sorted(set(subset) - set(notations(scheme)))}")
    node = {"type": ["string", "null"] if nullable else "string", "enum": values + ([None] if nullable else []),
            "description": description, "x-cv-scheme": scheme}
    if subset is not None:
        node["x-cv-subset"] = True
    return node


def enum_list(scheme: str, description: str) -> dict:
    return {"type": "array", "description": description, "x-cv-scheme": scheme,
            "items": {"type": "string", "enum": notations(scheme)}}


def text(description: str, nullable: bool = False) -> dict:
    return {"type": ["string", "null"] if nullable else "string", "description": description}


def integer(description: str, nullable: bool = False) -> dict:
    return {"type": ["integer", "null"] if nullable else "integer", "description": description}


def number(description: str, nullable: bool = False) -> dict:
    return {"type": ["number", "null"] if nullable else "number", "description": description}


def strings(description: str) -> dict:
    return {"type": "array", "description": description, "items": {"type": "string"}}


def obj(description: str, **props) -> dict:
    return {"type": "object", "description": description, "additionalProperties": False,
            "required": list(props), "properties": props}


def array(description: str, item: dict) -> dict:
    return {"type": "array", "description": description, "items": item}


def schema(stage: str, title: str, description: str, root: dict) -> dict:
    root = dict(root)
    root.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
                 "$id": f"https://w3id.org/wlo/curriculum/schema/{stage}", "title": title})
    root["description"] = description
    return root


BLOCKS = "Block-IDs aus Stufe X0 (Muster p<Seite>-b<Block>), in Lesereihenfolge. Nie Seitenzahlen erfinden."


def x1() -> dict:
    applicability = obj(
        "Geltung der Spezifikation; nur Angaben, die das Dokument macht.",
        sector=enum("EducationSectors", "Bildungsbereich der Spezifikation."),
        formality=enum("Formalities", "formal, nicht formal oder informell.", nullable=True),
        timeKind=enum("TimeKinds", "Art der Zeitangabe (Alter, Jahrgang, Ausbildungsjahr …).", nullable=True),
        timeText=text("Zeitangabe im Wortlaut („Klassen 5/6“, „0 bis 10 Jahre“).", nullable=True),
        levelText=text("Niveau- oder Abschlussangabe im Wortlaut („Mittlerer Schulabschluss“, „B1“).", nullable=True),
        institutionText=text("Schulart, Einrichtungsart, Hochschul- oder Lernort im Wortlaut.", nullable=True),
        targetGroupText=text("Zielgruppe im Wortlaut.", nullable=True),
        evidenceBlockIds=strings(BLOCKS),
    )
    return schema("x1-dokumentprofil", "X1 Dokumentprofil",
                  "Stufe X1: Metadaten, Spezifikationen (Geltungseinheiten) und dokumenteigene Begriffe aus Titelei, "
                  "Inhaltsverzeichnis und Vorwortanfang. Ein Aufruf je Dokument.",
                  obj("Dokumentprofil",
                      document=obj("Dokument (Fassung)",
                                   title=text("Titel wörtlich."),
                                   documentType=text("Knotentyp-ID eines Dokumenttyps aus der Liste im Prompt (aktives Profil)."),
                                   legalForm=enum("LegalForms", "Rechtsform; unknown, wenn nicht genannt."),
                                   documentBinding=enum("DocumentBindings", "Verbindlichkeit des Dokuments; unknown, wenn nicht genannt."),
                                   lifecycle=enum("Lifecycles", "Lebenszyklus; Anhörungsfassung = consultation."),
                                   educationSectors=enum_list("EducationSectors", "Alle Bildungsbereiche, für die das Dokument Spezifikationen enthält."),
                                   regions=strings("Länder als ISO-3166-2-Code (DE-NW); DE für länderübergreifend."),
                                   issuerText=text("Herausgeber im Wortlaut.", nullable=True),
                                   issuedText=text("Datum der Ausgabe/des Beschlusses im Wortlaut.", nullable=True),
                                   validFromText=text("Inkrafttreten im Wortlaut.", nullable=True),
                                   editionText=text("Fassungs- oder Versionsangabe im Wortlaut.", nullable=True),
                                   evidenceBlockIds=strings(BLOCKS)),
                      specifications=array("Geltungseinheiten des Dokuments (Curricula, Rahmen, Qualifikations- oder Prüfungsspezifikationen).",
                                           obj("Spezifikation",
                                               key=text("Laufende Kennung S1, S2 …"),
                                               kind={"type": "string", "enum": ["curriculum", "competencyFramework",
                                                                                "qualificationSpecification", "assessmentSpecification"],
                                                     "description": "Untertyp der Spezifikation (Kernklassen)."},
                                               title=text("Bezeichnung wörtlich (Fach, Beruf, Studiengang, Kurs)."),
                                               fieldText=text("Fach/Feld im Wortlaut.", nullable=True),
                                               applicability=applicability,
                                               variants=array("Varianten (Fachrichtung, Schwerpunkt, Wahlqualifikation, Teilcurriculum …).",
                                                              obj("Variante",
                                                                  key=text("Kennung V1, V2 …"),
                                                                  label=text("Bezeichnung wörtlich."),
                                                                  variantKind=enum("VariantKinds", "Art der Variante."))))),
                      termMappings=array("Dokumenteigene Bezeichnungen, die auf Knotentypen oder Aussage-Unterarten des Profils zeigen.",
                                         obj("Termzuordnung",
                                             documentTerm=text("Bezeichnung wie im Dokument."),
                                             mapsTo=text("ID aus der Liste im Prompt."),
                                             evidenceBlockId=text("Block, in dem der Begriff erklärt oder benutzt wird."))),
                      newTerms=array("Gliederungsbegriffe ohne Treffer im Profil – gehen in die Prüfliste für das Lexikon.",
                                     obj("Neuer Begriff",
                                         documentTerm=text("Bezeichnung wie im Dokument."),
                                         suggestedFunction=enum("NodeFunctions", "Vorgeschlagene Kernfunktion."),
                                         evidenceBlockId=text("Block mit dem ersten Vorkommen."))),
                      ))


def x1_gliederung() -> dict:
    return schema("x1-gliederung", "X1 Gerüst typisieren",
                  "Stufe X1, zweiter Aufruf: nur für Überschriften, die Muster und Lexikon nicht typisieren konnten. Das Gerüst "
                  "selbst baut die Pipeline deterministisch aus Inhaltsverzeichnis, Layout und Lexikon.",
                  obj("Typisierung",
                      headings=array("Je unklare Überschrift eine Entscheidung.",
                                     obj("Überschrift",
                                         headingId=text("ID der Überschrift aus der Liste im Prompt."),
                                         nodeType=text("Knotentyp-ID aus der Liste oder null, wenn keiner passt.", nullable=True),
                                         nodeFunction=enum("NodeFunctions", "Kernfunktion."),
                                         appliesTo=strings("Kennungen der Spezifikationen (S1 …), für die der Abschnitt gilt; leer = erbt."),
                                         scopeShare=enum("ScopeShares", "Gemeinsam, spezifisch, ergänzend oder alternativ.", nullable=True)))))


def statement(description: str) -> dict:
    return obj(description,
               blockIds=strings(BLOCKS),
               verbatim=text("Wortlaut der Aussage, wörtlich und vollständig, ohne gemeinsamen Einleitungssatz."),
               leadIn=text("Gemeinsamer Einleitungssatz („Die Schülerinnen und Schüler …“), sonst null.", nullable=True),
               statementKind=enum("StatementKinds", "Aussageart nach Funktion, nicht nach Wort; im Zweifel unclassified."),
               statementSubkind=text("Aussage-Unterart-ID aus der Liste im Prompt oder null.", nullable=True),
               addressee=enum("Addressees", "An wen sich die Aussage richtet."),
               obligation=enum("Obligations", "Verbindlichkeit nur, wenn sie an dieser Aussage steht; sonst null (wird vererbt).", nullable=True),
               layoutMarkers=enum_list("LayoutMarkers", "Satz- und Layoutsignale am Wortlaut (fett, kursiv, Klammer …)."),
               codeText=text("Nummer oder Kennung wie im Dokument („(3)“, „a)“, „QA2“).", nullable=True),
               levelText=text("Niveauangabe im Wortlaut an dieser Aussage („G/M/E“, „A1“, „Niveau D“).", nullable=True),
               timeText=text("Zeitangabe im Wortlaut an dieser Aussage.", nullable=True),
               contextText=text("Ausdrücklich genannte Situation, Lebensbereich oder Lernort.", nullable=True),
               crossCuttingMarkers=strings("Querschnittsmarker roh („L BNE“, „[MD3]“, „⇒ Medienbildung“)."),
               referenceMarker=text("Verweis roh („P 2.1“, „➔ GE, Kl. 8/9, LB 2“).", nullable=True),
               exampleText=text("Beispielteil („z. B. …“) wörtlich.", nullable=True),
               purposeText=text("Handlungsziel („Möchte …“) wörtlich.", nullable=True),
               targetsContent={"type": "array", "items": {"type": "integer"},
                               "description": "Indizes (0-basiert) der Inhaltsaussagen derselben Antwort, auf die diese Aussage zeigt."})


def x3() -> dict:
    return schema("x3-rahmenteile", "X3 Rahmenteile",
                  "Stufe X3: einmal je Dokument die Rahmenteile lesen – Kompetenzmodell, Niveaumodell, Operatorenliste, "
                  "Querschnittslegende, Regeln, Bildungsziele und Aufträge. Die Ergebnisse werden Auswahllisten für X4.",
                  obj("Rahmenteile",
                      competencyModels=array("Vom Dokument erklärte Kompetenzmodelle.",
                                             obj("Kompetenzmodell",
                                                 title=text("Bezeichnung wörtlich."),
                                                 dimensions=array("Dimensionen in Dokumentreihenfolge.",
                                                                  obj("Dimension",
                                                                      code=text("Kürzel, falls vorhanden.", nullable=True),
                                                                      label=text("Bezeichnung wörtlich."),
                                                                      parentLabel=text("Übergeordnete Dimension oder null.", nullable=True))),
                                                 evidenceBlockIds=strings(BLOCKS))),
                      levelModels=array("Vom Dokument erklärte Niveau- oder Stufenmodelle.",
                                        obj("Niveaumodell",
                                            title=text("Bezeichnung wörtlich."),
                                            levelDimension=enum("LevelDimensions", "Was die Stufen messen."),
                                            competenceDimension=text("Kompetenzbereich, für den die Stufen gelten („Lesen“, „Hörverstehen“), wörtlich; null, wenn sie für alle Bereiche gelten.", nullable=True),
                                            levels=array("Stufen von der niedrigsten zur höchsten Leistung oder Anforderung (bei Noten von 6 nach 1).",
                                                         obj("Stufe", code=text("Kürzel."), label=text("Bezeichnung wörtlich."))),
                                            defaultRelation=enum("LevelRelations", "Wie das Dokument Aussagen den Stufen zuordnet.", nullable=True),
                                            evidenceBlockIds=strings(BLOCKS))),
                      operators=array("Operatorenliste des Dokuments.",
                                      obj("Operator",
                                          lemma=text("Operator in Grundform; trennbare Verben als „wählen … aus“."),
                                          definition=text("Erklärung wörtlich.", nullable=True),
                                          taskDemandText=text("Anforderungsbereich laut Liste im Wortlaut.", nullable=True),
                                          evidenceBlockId=text("Block der Zeile."))),
                      crossCuttingLegend=array("Legende der Querschnittsmarker.",
                                               obj("Marker",
                                                   marker=text("Marker wie im Dokument („L BNE“, „[MD3]“)."),
                                                   label=text("Erklärung wörtlich."),
                                                   evidenceBlockId=text("Block der Legende."))),
                      rules=array("Regeln (Wahl, Voraussetzung, Abschluss, Anrechnung, Fortschritt) im Wortlaut mit geparsten Werten.",
                                  obj("Regel",
                                      blockIds=strings(BLOCKS),
                                      verbatim=text("Wortlaut der Regel."),
                                      ruleKind={"type": "string", "enum": ["selection", "prerequisite", "completion", "recognition", "progression"],
                                                "description": "Regelart (Kernklassen)."},
                                      minCount=integer("Mindestzahl der Optionen.", nullable=True),
                                      maxCount=integer("Höchstzahl der Optionen.", nullable=True),
                                      minAmount=number("Mindestumfang.", nullable=True),
                                      maxAmount=number("Höchstumfang.", nullable=True),
                                      amountUnit=enum("WorkloadUnits", "Einheit des Umfangs.", nullable=True),
                                      requirementKind=enum("RequirementKinds", "Art der Voraussetzung.", nullable=True),
                                      maxShare=number("Höchstanteil der Anrechnung (0–1).", nullable=True),
                                      optionTexts=strings("Optionen wie im Dokument (Titel oder Kennungen)."))),
                      statements=array("Bildungsziele, Aufträge und Grundsätze der Rahmenteile.", statement("Aussage eines Rahmenteils")),
                      checkedAbsent=enum_list("DockingPoints", "Andockpunkte, die das Dokument nachweislich nicht angibt (z. B. kein Niveaumodell).")))


def x4() -> dict:
    return schema("x4-aussagen", "X4 Aussagen einer Einheit",
                  "Stufe X4: ein Aufruf je Einheit (Seitenbereich aus dem Skelett) – alle Aussagen im Wortlaut als Blätter. "
                  "Die Wortlautprüfung (X5) gleicht verbatim gegen die Blöcke ab.",
                  obj("Aussagen",
                      unitKey=text("Kennung der Einheit aus dem Skelett."),
                      statements=array("Aussagen in Dokumentreihenfolge; ein Spiegelstrich, eine Tabellenzeile oder ein Satz je Aussage nach der Segmentierungsregel des Knotentyps.",
                                       statement("Aussage")),
                      checkedAbsent=enum_list("DockingPoints", "Andockpunkte, die in dieser Einheit nachweislich fehlen.")))


def n1() -> dict:
    return schema("n1-zerlegung", "N1 Zerlegung",
                  "Stufe N1: Lernergebnisse, Bildungsziele und Standards in Handlung × Gegenstand × Bedingung zerlegen. "
                  "Mehrere Operatoren = mehrere Zerlegungen. Alle Teile stehen wörtlich in der Aussage (Rückprobe).",
                  obj("Zerlegungen",
                      decompositions=array("Zerlegungen.",
                                           obj("Zerlegung",
                                               statementId=text("ID der Aussage aus dem Prompt."),
                                               actionText=text("Handlung wörtlich; trennbare Verben als „wählen … aus“."),
                                               operatorLemma=text("Operator-Lemma aus der Liste im Prompt oder null.", nullable=True),
                                               objectText=text("Gegenstand wörtlich."),
                                               conditionText=text("Bedingung oder Kontext wörtlich.", nullable=True),
                                               qualityCriterion=text("Qualitätskriterium wörtlich („sachgerecht“).", nullable=True),
                                               developmentQualifier=text("Entwicklungs- oder Fortschrittssignal wörtlich („zunehmend selbstständig“).", nullable=True),
                                               autonomy=enum("Autonomies", "Selbstständigkeit nur, wenn im Wortlaut ausgedrückt.", nullable=True),
                                               knowledgeType=enum("KnowledgeTypes", "Wissensart nur bei Wissensaussagen.", nullable=True),
                                               competenceDimension=text("Dimension aus dem Kompetenzmodell des Dokuments (Liste im Prompt) oder null.", nullable=True)))))


def g1() -> dict:
    return schema("g1-kanten", "G1 Kantenentscheidung",
                  "Stufe G1: für jede Quelle aus höchstens 40 nummerierten Kandidaten (Retrieval + Rerank) die passende "
                  "Relation wählen. Konfidenz berechnet die Pipeline; das Modell begründet mit einem Zitat.",
                  obj("Kanten",
                      decisions=array("Je Quelle eine oder mehrere Entscheidungen.",
                                      obj("Entscheidung",
                                          sourceId=text("ID der Quelle aus dem Prompt."),
                                          candidate=integer("Nummer des Kandidaten oder null, wenn keiner passt.", nullable=True),
                                          relation=enum("AlignmentRelations", "Relation der Quelle zum Kandidaten.", subset=G1_RELATIONS),
                                          rationale=text("Kurze Begründung mit dem entscheidenden Wortlaut aus Quelle oder Kandidat.")))))


def main() -> None:
    global VOCAB
    ergebnis = Path(sys.argv[1])
    VOCAB = Graph()
    VOCAB.parse(ergebnis / "ontologie" / "cur-vokabular.ttl")
    out = ergebnis / "schemas"
    out.mkdir(exist_ok=True)
    for build in (x1, x1_gliederung, x3, x4, n1, g1):
        sch = build()
        name = sch["$id"].rsplit("/", 1)[-1]
        (out / f"{name}.schema.json").write_bytes((json.dumps(sch, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"wrote schemas/{name}.schema.json")


if __name__ == "__main__":
    main()
