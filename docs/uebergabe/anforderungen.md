# Antworten für das IT-Team

Stand 22.10.2026, Meilenstein M0 (Fundament). Diese Seite beantwortet die Vorgaben aus
„Übergaben an den Maschinenraum" (Team 6) Frage für Frage, in der Variante **ohne B-API**: Der
Dienst prüft eigene Zugangstokens und ruft das Sprachmodell mit einem eigenen Schlüssel. Was
noch offen ist, steht am Ende; die Antworten wachsen mit jedem Meilenstein.

Kurz: Kompetenzkartierer-AI erfasst Lehrpläne nach Curriculum-Kern 1.0, dockt sie an Kompetenz-,
Niveau- und Normdatenschemata an und bildet daraus eine Wissenslandkarte. Ein Image läuft als
API und als Worker, dazu ein Web-Image für die Oberfläche; Daten liegen in PostgreSQL und einem
S3-Objektspeicher.

## 1. API und Endpunkte

| Frage | Antwort |
|---|---|
| OpenAPI-Spec? | Ja, OpenAPI 3.1 aus dem Code (FastAPI), nie von Hand gepflegt, unter `GET /openapi.json` am öffentlichen Port. `info.title`, `info.summary` (für den Produktkatalog) und `info.description` sind gesetzt; jede Operation hat Gruppe und Kurztitel, jede Gruppe eine Beschreibung (`tests/api/test_openapi.py`) |
| Swagger UI, ReDoc? | Abgeschaltet: Beide laden Skripte und Schriften von Fremdservern in den Browser. Eine Doku-Seite nur mit eigenen Dateien kann folgen |
| Zwei Ports? | Ja. `PUBLIC_PORT` (8000) ist die API für den Ingress; `INTERNAL_PORT` (9000) liefert `/health`, `/ready` und `/metrics`. Am öffentlichen Port antworten diese Pfade mit 404, entschieden nach dem Socket, nicht nach Headern; sie stehen nicht in der Spec |
| Proben in Kubernetes? | Liveness `GET /health`, Readiness `GET /ready` (prüft die Datenbank und den Stand der Migrationen, wartet je bis 2 s auf Verbindung und Abfrage, also `timeoutSeconds` ≥ 5), beide am Port 9000 ([Helm-Beispiel](../../deploy/helm-values.example.yaml)). `HEAD /health` antwortet 405; eine Probe muss GET senden |
| Header vom Client? | `Authorization: Bearer kka_…` für alles außer `GET /api/v1/info` und dem öffentlichen Lesen, das `PUBLIC_ACCESS` freigibt. Optional `X-Request-ID`, `x-client-trace-id` und die B3-Header |
| Header zurück? | `X-Request-ID` an jeder Antwort; `WWW-Authenticate` bei 401, `Retry-After` bei 429 und 503. Dazu an jeder Antwort `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY` und `Referrer-Policy: no-referrer`; HSTS setzt der Ingress, an dem TLS endet |
| Content-Types? | `application/json`, jeder JSON-Body bis 1 MiB; `/metrics` im Textformat für Prometheus. Uploads als `multipart/form-data` (`POST /api/v1/sources`, bis `MAX_UPLOAD_MB` und 1 MiB für das Formular; ein Body über seiner Grenze wird mit 413 abgewiesen, bevor er gelesen wird). Dateiausgaben (PDF, TTL, ZIP) folgen in M1: die Abweichung, die mit T6 abzustimmen ist |
| Fehler? | Einheitlich `{"code", "message", "details"}`; Validierungsfehler nennen Feld und Art, nie die Eingabe; keine Stacktraces nach außen |
| Antwortzeiten? | Lesende Anfragen kurz; alles über 30 s läuft ab M1 als Job (`202` mit Job-ID, Stand über `GET /api/v1/jobs/{id}`): Konvertierung, Extraktion, Prüfung. Messung unter Last in M6 |

## 2. Authentifizierung (ohne B-API)

| Frage | Antwort |
|---|---|
| Wer authentifiziert? | Der Dienst selbst: Tokens, die ein Admin ausgibt, gespeichert als HMAC-SHA-256 mit dem Geheimnis `API_KEY_PEPPER`; sperrbar und widerrufbar |
| Rollen? | `admin`, `redaktion`, `nutzer`. Ohne Token nur, was `PUBLIC_ACCESS` (`off` \| `lookup` \| `search`) erlaubt, nie das Sprachmodell |
| Schutz gegen Raten? | `AUTH_FAILURE_LIMIT` Fehlversuche je Adresse (IPv6: je /64) in `AUTH_FAILURE_WINDOW_S`, danach 429; ein gültiges Token kommt immer durch. Die Client-Adresse kommt nur von Proxys aus `FORWARDED_ALLOW_IPS` |
| Schlüssel des Sprachmodells? | `OPENAI_API_KEY` als Secret (Datei über `OPENAI_API_KEY_FILE`), nur im Worker. `OPENAI_BASE_URL` erlaubt jeden OpenAI-kompatiblen Endpunkt, auch ein Gateway im Cluster; keine B-API |
| Erster Admin? | `python -m app.bootstrap NAME` einmal interaktiv (`kubectl exec -it`); das Token geht auf stdout, nie in ein Log |

## 3. Monitoring und Logging

| Frage | Antwort |
|---|---|
| Metriken? | Prometheus am internen Port, `GET /metrics`: Anfragen und Dauer je Route-Vorlage (`kka_http_requests_total`, `kka_http_request_duration_seconds`). Der Worker bedient denselben internen Port mit `/health` (Liveness) und `/metrics`: Jobs nach Art und Ausgang (`kka_jobs_total`, Ausgänge `done`, `failed`, `error`, `cancelled`, `released`, `lost`; gezählt, wie der Ausgang geschrieben wurde: `lost` auch, wenn der Handler oder das Ende den Verlust der Lease bemerkt) und ihre Dauer (`kka_job_duration_seconds`), dazu abgelaufene Leases, die ein Sweep weitergibt (`kka_job_leases_expired_total`, nach dem, was aus dem Job wurde: `queued`, `failed`, `cancelled`); er hat keinen Service, daher ein PodMonitor. LLM- und Konvertierungsmetriken folgen in M1 |
| Logs? | Eine Zeile je Ereignis auf stdout, mit `LOG_FORMAT=json` als JSON mit `time`, `level`, `logger`, `request_id`, `trace_id`, `message`; eine Zeile je Anfrage ohne Query-Werte; nie ein Geheimnis |
| Tracing? | `x-client-trace-id` und B3 (`X-B3-TraceId`, `b3`) werden übernommen, ungültige Werte verworfen. Die Trace-ID steht in jeder Logzeile der Anfrage (der Rauchtest in CI prüft es). Die Header für ausgehende Aufrufe sind vorbereitet (`outgoing_headers`), eingehängt werden sie mit den ersten ausgehenden Aufrufen in M1 (Sprachmodell, Abrufe). Ein Job trägt die Trace-ID der Anfrage, die ihn anlegte, ohne Tracing-Header (die Oberfläche sendet keinen) deren Request-ID; der Worker schreibt seine Zeilen damit |
| Alarme? | Regeln mit Tests folgen in M6 (volle Warteschlange, Lease-Verluste, Fehlerquote des Sprachmodells, Kontingente, Speicherplatz) |

## 4. Repository, Build und Versionierung

| Frage | Antwort |
|---|---|
| Repository? | github.com/janschachtschabel/Kompetenzkartierer-AI |
| Abhängigkeiten? | `backend/uv.lock` für alle Plattformen, mit Prüfsummen; das Image installiert den Export `deploy/requirements-api.txt` per `pip --require-hashes`, nur Wheels |
| Images? | `deploy/api.Dockerfile` (API und Worker, python:3.13-slim per Digest, Nutzer 10001, 244 MB) und `deploy/web.Dockerfile` (SPA hinter nginx-unprivileged per Digest, Nutzer 101, 61 MB). Kein Code-Volume, keine Daten im Image: von der Ontologie nur die Modelle, Vokabulare und Profile, die der Dienst liest. Das Web-Image nennt keinen API-Host; im Cluster routet der Ingress `/api/v1/` und `/openapi.json` zur API |
| CI? | `.github/workflows/ci.yml`: Ontologie-Prüfung, ruff, mypy, Tests mit PostgreSQL und MinIO samt Abdeckungsgrenze, Frontend-Tests und -Build, beide Images und ein Rauchtest des ganzen Dienstes in Compose (Vokabular geladen, beide Worker laufen, `/ready` je API-Replica, Trace-ID im Log). Ein grüner Lauf steht noch aus (erst nach dem ersten Push) |
| Versionen? | `app.__version__` folgt der Paketversion; Image-Tags `sha-<12 Zeichen>` je Commit und SemVer je Git-Tag sind geplant (mit der Registry) |

## 5. Deployment und Betrieb

| Frage | Antwort |
|---|---|
| Zustandslos? | Ja: kein Zustand im Prozess, der über eine Anfrage hinaus gilt. Jobs, Sperren, Zähler und Kontingente liegen in PostgreSQL, Dateien im Objektspeicher. API und Worker skalieren über Replicas |
| Warteschlange? | Eine Tabelle in PostgreSQL: Worker holen Jobs mit `FOR UPDATE SKIP LOCKED`, halten eine Lease mit Lebenszeichen, geben sie bei SIGTERM nach `JOB_SHUTDOWN_GRACE_S` zurück; ein abgestürzter Worker verliert sie nach `JOB_LEASE_S`. Faire Bedienung je Konto. Kein eigener Broker |
| Datenbank? | PostgreSQL 17 mit `vector`, `pg_trgm`, `unaccent` (anlegen durch die Migration oder vorab durch den DBA). Migrationen einmal je Release per `python -m app.db.migrate` (Helm-Hook), unter Advisory-Lock; API und Worker migrieren nie selbst, `/ready` meldet einen fehlenden Stand |
| Objektspeicher? | S3-kompatibel (`STORAGE_BACKEND=s3`), Bucket von T6; API und Worker fragen ihn beim Start ab und starten ohne ihn nicht. Rechte: `s3:ListBucket` auf den Bucket (ohne sie meldet S3 ein fehlendes Objekt als 403), `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` auf seine Objekte. Ohne Schlüssel gilt die Standardkette von boto3 (`AWS_*`-Variablen, Web-Identity/IRSA, Rolle der Instanz) |
| Volumes? | Keine in M0. Ab M3 kommen lesend eingebundene Volumes für lokale Abzüge (Wikidata, GND, ESCO) und Modelle, befüllt von Sidecars bzw. CronJobs |
| Ressourcen? | Noch nicht gemessen; das Helm-Beispiel nennt vorläufige Werte. Die Konvertierung (ab M1 eigener Worker, ein Job je Pod) braucht deutlich mehr Speicher; die Baseline unter Last kommt in M6 |
| Konfiguration? | Nur Umgebungsvariablen, Geheimnisse als Dateien (`*_FILE`); vollständige Liste in [konfiguration.md](konfiguration.md), aus dem Code erzeugt |
| Härtung? | Nicht-root, nur lesendes Wurzeldateisystem, keine Capabilities, keine neuen Privilegien, `seccomp RuntimeDefault`; in Compose so betrieben und geprüft |
| Lokal ausprobieren? | `deploy/docker-compose.yml` startet alles auf einem Rechner (README, „Compose") |

## 6. Übergabepaket

- [x] Images und Build-Dateien (`deploy/`)
- [x] Konfiguration ([konfiguration.md](konfiguration.md)), erzeugt und geprüft
- [x] Helm-Werte als Vorlage ([helm-values.example.yaml](../../deploy/helm-values.example.yaml))
- [x] Compose für den lokalen Betrieb
- [ ] CI-Lauf grün und Images in der Registry
- [ ] Alarmregeln, Ressourcen-Baseline, Lasttest (M6)
- [ ] Steckbrief für den Produktkatalog (mit dem ersten nutzbaren Stand, M1)

## 7. Kosten, Wartung und Lebenszyklus

| Frage | Antwort |
|---|---|
| Laufende Kosten? | Das Sprachmodell je Aufruf (Kontingente je Konto ab M1); sonst CPU, Speicher, PostgreSQL und Objektspeicher. Keine GPU |
| Wartung? | Abhängigkeiten über `uv.lock`, Basis-Images über ihren Digest; ein Update ist ein eigener, geprüfter Commit |
| Dritte zur Anfragezeit? | Keine in der API. Live nur in Jobs des Workers: das Sprachmodell und der Abruf von Quell-URLs, die ein Konto nennt (`source.fetch`). Abgerufen wird nur von öffentlichen Adressen (kein privates, Loopback-, Link-Local-, CGNAT-, Multicast- oder NAT64-Netz), verbunden genau zur geprüften Adresse, ohne Proxy der Umgebung; die NetworkPolicy des Workers erlaubt dafür 80/443 nach außen, nicht die Netze des Clusters. Fremddaten kommen ab M3 als lokale Abzüge |

## Offene Punkte

- Erster grüner CI-Lauf und Registry (nach dem ersten Push).
- Abstimmung der Content-Types für Uploads und Dateiausgaben (M1).
- Prüfsummen beim Objektspeicher: boto3 schickt seit 1.36 bei jedem Schreiben eine CRC32-Prüfsumme
  mit (`x-amz-checksum-crc32`, über HTTPS als `aws-chunked`), die manche S3-kompatiblen Dienste
  ablehnen. Getestet ist MinIO. Nimmt T6s Dienst sie nicht an, schalten botocores eigene Variablen
  `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` und `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required`
  sie auf „nur wo verlangt" um; der Dienst setzt keinen der beiden Werte selbst (getestet).
- Ressourcen, Alarme und Lastmessung (M6).
