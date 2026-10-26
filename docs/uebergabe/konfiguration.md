# Konfiguration

[Antworten für das IT-Team](anforderungen.md) · Stand M1 (Paket 1)

Der Dienst liest seine Einstellungen beim Start aus Umgebungsvariablen; API und Worker lesen
dieselben. Ein Geheimnis kann stattdessen aus der Datei kommen, die `<NAME>_FILE` nennt
(Kubernetes- oder Docker-Secret); die Datei gewinnt dann. Fehlermeldungen nennen nie einen Wert.
Ohne Vorgabe („Pflicht") startet der Dienst nicht; „Pflicht bei …" und „Pflicht für …" gelten
nur unter dieser Bedingung bzw. für diesen Teil. Ein Muster ist ein regulärer Ausdruck, dem der
ganze Wert genügen muss; die Endpunkte (`S3_ENDPOINT_URL`, `OPENAI_BASE_URL`) nehmen zudem keinen
Nutzer, keine Query und kein Fragment an. Eine `.env`-Datei liest er nicht.

Was jede Einstellung bewirkt, steht im [README](../../README.md), Abschnitt „Betrieb". Die
Tabelle unten ist aus dem Code erzeugt (`python -m app.core.config_doc` im Ordner `backend/`);
ein Test schlägt an, wenn sie veraltet.

<!-- settings:start (python -m app.core.config_doc) -->
| Variable | Werte | Vorgabe | Geheim | Teil |
|---|---|---|---|---|
| `DATABASE_URL` | Text | Pflicht | ja, auch `DATABASE_URL_FILE` | Dienst |
| `DB_POOL_MIN_SIZE` | Zahl ≥ 0 | 1 | – | Dienst |
| `DB_POOL_MAX_SIZE` | Zahl ≥ 1 | 10 | – | Dienst |
| `DB_POOL_TIMEOUT_S` | Zahl > 0, ≤ 60 | 5 | – | Dienst |
| `HOST` | Text | `127.0.0.1` | – | Dienst |
| `PUBLIC_PORT` | Zahl ≥ 1, ≤ 65535 | 8000 | – | Dienst |
| `INTERNAL_PORT` | Zahl ≥ 1, ≤ 65535 | 9000 | – | Dienst |
| `ROOT_PATH` | Text nach Muster `^(/[A-Za-z0-9._~-]+)*$` | leer | – | Dienst |
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` | `INFO` | – | Dienst |
| `API_KEY_PEPPER` | Text, mindestens 32 Zeichen | –; Pflicht für die API und `app.bootstrap` | ja, auch `API_KEY_PEPPER_FILE` | Dienst |
| `PUBLIC_ACCESS` | `off` \| `lookup` \| `search` | `off` | – | Dienst |
| `FORWARDED_ALLOW_IPS` | Text | `127.0.0.1,::1` | – | Dienst |
| `AUTH_FAILURE_LIMIT` | Zahl ≥ 1 | 10 | – | Dienst |
| `AUTH_FAILURE_WINDOW_S` | Zahl > 0 | 900 | – | Dienst |
| `JOB_LEASE_S` | Zahl ≥ 3, ≤ 3600 | 60 | – | Dienst |
| `JOB_POLL_S` | Zahl > 0, ≤ 60 | 1 | – | Dienst |
| `JOB_SHUTDOWN_GRACE_S` | Zahl ≥ 0, ≤ 3600 | 20 | – | Dienst |
| `MAX_UPLOAD_MB` | Zahl ≥ 1, ≤ 500 | 50 | – | Dienst |
| `UPLOADS_PER_MINUTE` | Zahl ≥ 1 | 20 | – | Dienst |
| `THIRD_PARTY_MARKDOWN` | `hidden` \| `accounts` \| `public` | `hidden` | – | Dienst |
| `URL_IMPORTS_PER_MINUTE` | Zahl ≥ 1 | 20 | – | Dienst |
| `CONVERSIONS_PER_MINUTE` | Zahl ≥ 1 | 20 | – | Dienst |
| `MAX_JOBS_IN_FLIGHT` | Zahl ≥ 1, ≤ 1000 | 20 | – | Dienst |
| `MODEL_STARTS_PER_MINUTE` | Zahl ≥ 1 | 10 | – | Dienst |
| `EXTRACT_CONCURRENCY` | Zahl ≥ 1, ≤ 16 | 4 | – | Dienst |
| `SHACL_TIMEOUT_S` | Zahl ≥ 10, ≤ 1800 | 300 | – | Dienst |
| `FETCH_USER_AGENT` | Text nach Muster `^[A-Za-z0-9._-]+(/[!-~]+)?( [ -~]*[!-~])?$`, höchstens 200 Zeichen | `Kompetenzkartierer-AI (+https://github.com/janschachtschabel/Kompetenzkartierer-AI)` | – | Dienst |
| `CHECK_HOST_INTERVAL_S` | Zahl ≥ 0.5, ≤ 60 | 2 | – | Dienst |
| `MAX_PDF_PAGES` | Zahl ≥ 1, ≤ 5000 | 800 | – | Dienst |
| `CONVERT_TIMEOUT_S` | Zahl ≥ 1, ≤ 7200 | 900 | – | Dienst |
| `WORKER_KINDS` | Text nach Muster `^([a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*(,[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*)*)?$` | leer | – | Dienst |
| `ONTOLOGY_DIR` | Pfad | `ontology/` des Repositorys | – | Dienst |
| `LOG_FORMAT` | `text` \| `json` | `text` | – | Dienst |
| `STORAGE_BACKEND` | `fs` \| `s3` | `fs` | – | Dienst |
| `STORAGE_DIR` | Pfad | –; Pflicht bei `STORAGE_BACKEND=fs` | – | Dienst |
| `S3_ENDPOINT_URL` | Text nach Muster `^https?://[^\s/]+(/\S*)?$` | – | – | Dienst |
| `S3_BUCKET` | Text nach Muster `^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$` | –; Pflicht bei `STORAGE_BACKEND=s3` | – | Dienst |
| `S3_REGION` | Text nach Muster `^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$` | `us-east-1` | – | Dienst |
| `S3_ACCESS_KEY` | Text | –; nur zusammen mit `S3_SECRET_KEY` | ja, auch `S3_ACCESS_KEY_FILE` | Dienst |
| `S3_SECRET_KEY` | Text | –; nur zusammen mit `S3_ACCESS_KEY` | ja, auch `S3_SECRET_KEY_FILE` | Dienst |
| `OPENAI_API_KEY` | Text | – | ja, auch `OPENAI_API_KEY_FILE` | Sprachmodell |
| `OPENAI_BASE_URL` | Text nach Muster `^https?://[^\s/]+(/\S*)?$` | `https://api.openai.com/v1` | – | Sprachmodell |
| `OPENAI_MODEL` | Text | `gpt-6-luna` | – | Sprachmodell |
| `OPENAI_REASONING_EFFORT` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` | `low` | – | Sprachmodell |
| `OPENAI_TEXT_VERBOSITY` | `low` \| `medium` \| `high` | `low` | – | Sprachmodell |
| `LLM_PROVIDER` | `openai` \| `openai-compatible` | `openai` | – | Sprachmodell |
| `LLM_CONTEXT_TOKENS` | Zahl ≥ 8000 | – | – | Sprachmodell |
| `LLM_MAX_OUTPUT_TOKENS` | Zahl ≥ 1000, ≤ 1000000 | 16000 | – | Sprachmodell |
<!-- settings:end -->

## Auf einem Rechner

- `INTERNAL_PORT` gilt für API und Worker: Beide bedienen dort `/health` und `/metrics`. Läuft
  ein Worker neben der API auf demselben Rechner, braucht er ein eigenes `INTERNAL_PORT` (etwa
  `9001`); sonst startet der zweite Prozess nicht, oder beide teilen sich den Port still
  (Windows). Im Cluster und in Compose hat jeder Pod bzw. Container seinen eigenen.

## Für einen Cluster

- `HOST` setzt das Image auf `0.0.0.0`; außerhalb des Images bleibt der Dienst auf Loopback.
- `STORAGE_BACKEND=s3` mit `S3_BUCKET`; für einen eigenen S3-Dienst dazu `S3_ENDPOINT_URL` und
  `S3_REGION`. Ein leerer oder fehlender `S3_ENDPOINT_URL` heißt AWS selbst; ohne `S3_REGION` gilt
  `us-east-1` (leer wird es abgewiesen). Der Bucket muss bestehen: API und Worker öffnen den
  Speicher beim Start und fragen ihn dabei ab; ohne Bucket (bzw. ohne `STORAGE_DIR`) starten sie
  nicht.
- `WORKER_KINDS` beschränkt einen Worker auf Job-Arten (kommagetrennt), etwa eigene Pods für die
  Konvertierung mit einem Job je Pod; leer nimmt er alle, die er kennt. Eine Art ohne Handler
  beendet den Start mit Code 1.
- Schlüssel: `S3_ACCESS_KEY_FILE` und `S3_SECRET_KEY_FILE`, beide oder keiner. Ohne sie nimmt
  boto3 seine Standardkette (`AWS_*`-Variablen, Web-Identity/IRSA, die Rolle der Instanz). Wohin
  der Dienst geht, sagt nur `S3_ENDPOINT_URL`: `AWS_ENDPOINT_URL` und ein `endpoint_url` in
  `~/.aws/config` übergeht er. Profile und Anmeldedaten von boto3 gelten weiter.
- Rechte der Rolle: `s3:ListBucket` auf den Bucket (ohne sie antwortet S3 auf ein fehlendes
  Objekt mit 403 statt 404), `s3:GetObject`, `s3:PutObject` und `s3:DeleteObject` auf seine Objekte.
- `FORWARDED_ALLOW_IPS`: die Adressen oder Netze des Ingress, nie `*` und nie ein Netz `/0`.
- Uploads: Das Formular eines Uploads liegt ab 1 MiB als temporäre Datei in `/tmp` (bzw.
  `TMPDIR`), bis zu `MAX_UPLOAD_MB` + 1 MiB; danach hält die API die Datei einmal im
  Arbeitsspeicher, solange sie sie prüft und ablegt. Je gleichzeitigem Upload braucht eine
  API-Replica also bis zu `MAX_UPLOAD_MB` + 1 MiB in `/tmp` und rund `MAX_UPLOAD_MB` mehr
  Arbeitsspeicher (bei 50 MB und vier Uploads zugleich rund 204 MiB `/tmp` und 200 MiB RAM).
  Eine Grenze für gleichzeitige Uploads je Replica gibt es nicht; `UPLOADS_PER_MINUTE` zählt je
  Konto.
- Konvertierung: Der Worker legt die Datei für die Dauer der Umwandlung in `/tmp` ab (bis
  `MAX_UPLOAD_MB`) und hält sie einmal im Arbeitsspeicher; der Kindprozess, der sie umwandelt,
  braucht je nach PDF ein Vielfaches davon (gemessen wird in M6). Unter Linux nimmt der Kernel
  bei Speichermangel zuerst ihn (`oom_score_adj` 1000), nicht den Worker; die Konvertierung
  endet dann mit `died`.
- Prüfung (X5): Gegen die SHACL-Formen prüft ein Kindprozess des Workers, mit derselben Regel für
  Speichermangel; seinen Speicherbedarf misst M6. Gemessen (CPU, ohne Last): rund 2 s für ein
  Dokument mit 100 Knoten und Aussagen (mit Fundstellen 200 Zeilen), 9 s mit 400, 43 s mit 1.200
  (300 Knoten, 900 Aussagen); `SHACL_TIMEOUT_S` (Standard 300 s) begrenzt ihn, danach bleibt das
  Tor mit dem Befund `x5.shacl_timeout` zu. Ein neuer Start der Extraktion prüft ein Dokument,
  dessen X5 fertig ist, nicht erneut: Eine höhere Frist gilt für Dokumente, deren X5 noch aussteht,
  und für die Prüfung nach einer Reparatur (`extract.repair`) oder einer Bearbeitung
  (`extract.check`). Der Befund `x5.shacl_timeout` allein
  ist kein Anlass für eine Reparatur. Stirbt der Kindprozess oder bricht er ab, scheitert
  der Lauf X5 (`ShaclCrashed`), und der Job wird bis zu seiner Versuchsgrenze wiederholt.
- `JOB_SHUTDOWN_GRACE_S` mindestens 5 s unter `terminationGracePeriodSeconds` des Workers.
- `LOG_FORMAT=json` für die zentrale Logsammlung.
