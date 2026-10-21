"""Port the HCO v1.0 lexicon into the curriculum-core lexicon model.

Reads hochschule/hco-lexicon.ttl (396 skos-xl entries on 60 HCO classes,
properties and concepts) and writes profile/hochschule-lexikon.ttl: one
cur:LexicalCue per entry, attached to hs:Terminology.

Decisions applied while porting (see konzept.md, section "Hochschule"):
- HCO targets map to node types, statement subkinds, core classes, core or
  hs: properties and vocabulary values (TARGETS);
- label contexts become scopes: country -> cur:scopeRegion, institution type
  -> cur:scopeInstitutionType, discipline culture -> cur:scopeSubject (ISCED-F),
  qualification type -> hs:scopeQualification;
- evidence E -> verified true; strength derived from role and evidence
  (HCO has no strengths): pref/alt 0.8, cue/negative 0.7, homonym 0.5,
  +0.1 for amtlich belegte Wortlaute;
- errors of the source are corrected (HCO report H.9).

Usage: python -I portiere_hochschul_lexikon.py <hco-lexicon.ttl> <ergebnis-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import RDF, XSD, Graph, Literal, Namespace
from rdflib.namespace import PROV

HCO = Namespace("https://w3id.org/hco/")
SKOSXL = Namespace("http://www.w3.org/2008/05/skos-xl#")

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
HS = Namespace("https://w3id.org/wlo/curriculum/profile/higher-education#")
LAND = Namespace("https://w3id.org/wlo/curriculum/region/")
FLD = Namespace("https://w3id.org/wlo/curriculum/field/")

TARGETS = {
    "AdmissionRequirement": [CUR.PrerequisiteRule, HS["rk-zugang"]],
    "Annex": [HS.annexOf],
    "ArtisticComponent": [HS.KuenstlerischesHauptfach],
    "Assessment": [CUR.Assessment],
    "ComponentGroup": [HS.Wahlpflichtkatalog],
    "ComponentUse": [CUR.Placement],
    "ContentStatement": [HS.Inhalt],
    "CourseUnit": [HS.Lehrveranstaltung],
    "CurriculumPlan": [CUR.Curriculum],
    "ExternalComponentReference": [HS.Verweis],
    "LearningOutcomeStatement": [HS.Modulziel],
    "Module": [HS.Modul],
    "ParticipationRequirement": [CUR.PrerequisiteRule],
    "Placement": [HS.Praxisphase],
    "PrerequisiteRule": [CUR.PrerequisiteRule],
    "ProgrammeArea": [HS.Studienbereich],
    "ProgrammeQualificationGoal": [HS.Studiengangsziel],
    "ProgrammeVersion": [CUR.edition],
    "ProgressionRule": [CUR.ProgressionRule],
    "ProjectComponent": [HS.Projektmodul],
    "RecognitionRule": [CUR.RecognitionRule],
    "ScopeAssignment": [CUR.appliesTo],
    "SelectionRule": [CUR.SelectionRule],
    "Specialisation": [HS.Schwerpunkt],
    "StudyPhase": [HS.Studienabschnitt],
    "StudyProgramme": [CUR.Programme],
    "TeachingLearningActivity": [HS.teachingFormat],
    "Thesis": [HS.Abschlussarbeit],
    "Workload": [CUR.workload],
    "amends": [CUR.amends],
    "appliesToCohort": [CUR.appliesToCohort],
    "componentCode": [CUR.code],
    "componentType": [HS.componentType],
    "creditAwardCondition": [HS.creditAwardCondition],
    "dt_AdmissionRegulation": [HS["dt-Zugangsordnung"]],
    "dt_CombinedStudyExaminationRegulation": [HS["dt-SPO"]],
    "dt_ExaminationRegulation": [HS["dt-Pruefungsordnung"]],
    "dt_GeneralExaminationRegulation": [HS["dt-RahmenPO"]],
    "dt_ModuleCatalogue": [HS["dt-Modulhandbuch"]],
    "dt_PlacementRegulation": [HS["dt-Praxisordnung"]],
    "dt_StateExaminationRegulation": [HS["dt-Staatsexamen"]],
    "dt_TeacherTrainingRegulation": [HS["dt-Lehramt"]],
    "durationSemesters": [HS.durationSemesters],
    "ectsCredits": [CV.unit_ectsCredit],
    "ectsRequired": [CUR.minAmount],
    "gradeWeight": [CUR.gradeWeight],
    "gradingScheme": [CUR.graded, HS.gradingText],
    "inheritsFrom": [CUR.inheritsFrom],
    "instructionLanguage": [HS.instructionLanguage],
    "ns_binding": [CV.bind_binding],
    "ns_bindingAnnex": [CV.bind_binding, HS.annexOf],
    "ns_informative": [CV.bind_informative],
    "obligation": [CUR.obligation],
    "offerFrequency": [HS.offerFrequency],
    "recommendedSemester": [CV.time_semester],
    "responsiblePerson": [HS["if-person"]],
    "standardDurationSemesters": [HS.standardDurationSemesters],
    "studyMode": [HS.studyMode],
    "totalCredits": [CUR.totalWorkload],
    "usabilityText": [HS.usabilityText],
}
ALTERNATIVES = {  # hco:alsoPointsTo targets
    "pr_major": HS["pr-kernfach"], "tf_lab": HS["tf-labor"], "sws": HS.sws,
    "dt_ModuleCatalogue": HS["dt-Modulhandbuch"], "usabilityText": HS.usabilityText,
    "ContentStatement": HS.Inhalt, "CourseUnit": HS.Lehrveranstaltung, "Assessment": CUR.Assessment,
    "componentType": HS.componentType, "ComponentGroup": HS.Wahlpflichtkatalog,
}
CONTEXTS = {
    "it_University": (CUR.scopeInstitutionType, HS["it-uni"]),
    "it_UAS": (CUR.scopeInstitutionType, HS["it-haw"]),
    "it_ArtMusic": (CUR.scopeInstitutionType, HS["it-kunst"]),
    "it_DualUniversity": (CUR.scopeInstitutionType, HS["it-dual"]),
    "it_UniversityOfEducation": (CUR.scopeInstitutionType, HS["it-ph"]),
    "fk_Medicine": (CUR.scopeSubject, FLD["0912"]),
    "fk_Law": (CUR.scopeSubject, FLD["0421"]),
    "fk_TeacherEducation": (CUR.scopeSubject, FLD["011"]),
    "fk_ArtsMusic": (CUR.scopeSubject, FLD["021"]),
    "fk_Engineering": (CUR.scopeSubject, FLD["07"]),
    "fk_Business": (CUR.scopeSubject, FLD["041"]),
    "fk_Humanities": (CUR.scopeSubject, FLD["02"]),
    "fk_Science": (CUR.scopeSubject, FLD["05"]),
    "ql_LegacyDiploma": (HS.scopeQualification, HS["qt-diplom"]),
    "ql_StateExamination": (HS.scopeQualification, HS["qt-staatsexamen"]),
}
ROLES = {"role_pref": CV.role_pref, "role_alt": CV.role_alt, "role_cue": CV.role_cue,
         "role_negative": CV.role_negative, "role_homonym": CV.role_homonym}
BASE_STRENGTH = {CV.role_pref: 0.8, CV.role_alt: 0.8, CV.role_cue: 0.7, CV.role_negative: 0.7, CV.role_homonym: 0.5}

# Corrections from the HCO report H.9, keyed by the source entry's local name.
RETARGET = {"gradingScheme--alt--gewichtung-der-note": [CUR.gradeWeight]}
REROLE = {
    "ContentStatement--alt--gliederung": (CV.role_cue, None),
    "LearningOutcomeStatement--alt--kompetenzen": (CV.role_cue, None),
    "Specialisation--alt--fachrichtung": (CV.role_homonym,
        "In der Berufsbildung Variante eines Ausbildungsberufs (Profil beruf:); an Hochschulen Schwerpunkt."),
    "creditAwardCondition--alt--leistungsnachweis": (CV.role_homonym,
        "Als Feld = Voraussetzung für die LP-Vergabe; als Prüfung selbst = cur:Assessment."),
    "CurriculumPlan--cue--curriculum": (CV.role_homonym,
        "Als Überschrift einer Ordnung („§ 5 Curriculum“) = Studienstruktur; im Fließtext ohne Signalwert."),
}
DROP = {"ProgrammeArea--pref--studienbereich"}  # duplicate of the homonym entry for the same target


def port(src: Graph) -> Graph:
    out = Graph()
    for prefix, ns in [("cur", CUR), ("cv", CV), ("hs", HS), ("land", LAND), ("fld", FLD), ("prov", PROV), ("xsd", XSD)]:
        out.bind(prefix, ns)
    owner = {entry: target for target, entry in src.subject_objects(HCO.hasLexicalEntry)}
    for entry in sorted(src.subjects(RDF.type, HCO.LexicalEntry)):
        local = str(entry).rsplit("/", 1)[-1]
        if local in DROP:
            continue
        target_name = str(owner[entry]).rsplit("/", 1)[-1]
        cue = HS["lex-" + local.replace("--", "-")]
        form = src.value(entry, SKOSXL.literalForm)
        role = ROLES[str(src.value(entry, HCO.labelRole)).rsplit("/", 1)[-1]]
        hint = None
        if local in REROLE:
            role, hint = REROLE[local]
        verified = str(src.value(entry, HCO.evidenceStatus)).endswith("ev_E")
        out.add((cue, RDF.type, CUR.LexicalCue))
        out.add((cue, CUR.surfaceForm, Literal(str(form))))
        out.add((cue, CUR.cueRole, role))
        out.add((cue, CUR.cueKind, CV.ck_term))
        out.add((cue, PROV.wasDerivedFrom, entry))
        for t in RETARGET.get(local, TARGETS[target_name]):
            out.add((cue, CUR.mapsTo, t))
        for alt in src.objects(entry, HCO.alsoPointsTo):
            out.add((cue, CUR.alsoMapsTo, ALTERNATIVES[str(alt).rsplit("/", 1)[-1]]))
        for ctx in src.objects(entry, HCO.labelContext):
            name = str(ctx).rsplit("/", 1)[-1]
            if name.startswith("de_"):
                out.add((cue, CUR.scopeRegion, LAND["DE-" + name[3:]]))
            else:
                prop, value = CONTEXTS[name]
                out.add((cue, prop, value))
        if getattr(form, "language", None) == "en":
            out.add((cue, CUR.recognitionHint, Literal("Englischsprachige Fassung oder Modulhandbuch.", lang="de")))
        for note in src.objects(entry, HCO.entryNote):
            out.add((cue, CUR.recognitionHint, note))
        if hint:
            out.add((cue, CUR.recognitionHint, Literal(hint, lang="de")))
        strength = BASE_STRENGTH[role] + (0.1 if verified else 0.0)
        out.add((cue, CUR.strength, Literal(f"{strength:.1f}", datatype=XSD.decimal)))
        out.add((cue, CUR.verified, Literal(verified)))
        out.add((HS.Terminology, CUR.hasCue, cue))
    return out


HEADER = """# =============================================================================
# GENERIERT von werkzeuge/portiere_hochschul_lexikon.py aus
# hochschule/hco-lexicon.ttl (HCO v1.0, 396 Einträge).
# Nicht von Hand ändern: Quelle oder Skript anpassen und neu erzeugen.
# Feldlexikon des Modulsteckbriefs; Korrekturen laut HCO-Bericht H.9.
# =============================================================================
"""


def main() -> None:
    src_path, ergebnis = Path(sys.argv[1]), Path(sys.argv[2])
    src = Graph()
    src.parse(src_path)
    out = port(src)
    target = ergebnis / "profile" / "hochschule-lexikon.ttl"
    target.write_bytes((HEADER + out.serialize(format="turtle")).replace("\r\n", "\n").encode("utf-8"))
    print(f"{len(set(out.subjects(RDF.type, CUR.LexicalCue)))} cues -> {target}")


if __name__ == "__main__":
    main()
