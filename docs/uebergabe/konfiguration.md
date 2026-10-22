# Konfiguration

[Antworten für das IT-Team](anforderungen.md) · Stand M0

Der Dienst liest seine Einstellungen beim Start aus Umgebungsvariablen; API und Worker lesen
dieselben. Ein Geheimnis kann stattdessen aus der Datei kommen, die `<NAME>_FILE` nennt
(Kubernetes- oder Docker-Secret); die Datei gewinnt dann. Fehlermeldungen nennen nie einen Wert.
Ohne Vorgabe („Pflicht") startet der Dienst nicht. Eine `.env`-Datei liest er nicht.

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
| `ROOT_PATH` | Text | leer | – | Dienst |
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` | `INFO` | – | Dienst |
| `API_KEY_PEPPER` | Text, mindestens 32 Zeichen | – | ja, auch `API_KEY_PEPPER_FILE` | Dienst |
| `PUBLIC_ACCESS` | `off` \| `lookup` \| `search` | `off` | – | Dienst |
| `FORWARDED_ALLOW_IPS` | Text | `127.0.0.1,::1` | – | Dienst |
| `AUTH_FAILURE_LIMIT` | Zahl ≥ 1 | 10 | – | Dienst |
| `AUTH_FAILURE_WINDOW_S` | Zahl > 0 | 900 | – | Dienst |
| `JOB_LEASE_S` | Zahl ≥ 3, ≤ 3600 | 60 | – | Dienst |
| `JOB_POLL_S` | Zahl > 0, ≤ 60 | 1 | – | Dienst |
| `JOB_SHUTDOWN_GRACE_S` | Zahl ≥ 0, ≤ 3600 | 20 | – | Dienst |
| `ONTOLOGY_DIR` | Pfad | `ontology/` des Repositorys | – | Dienst |
| `LOG_FORMAT` | `text` \| `json` | `text` | – | Dienst |
| `STORAGE_BACKEND` | `fs` \| `s3` | `fs` | – | Dienst |
| `STORAGE_DIR` | Pfad | – | – | Dienst |
| `S3_ENDPOINT_URL` | Text | – | – | Dienst |
| `S3_BUCKET` | Text | – | – | Dienst |
| `S3_REGION` | Text | `us-east-1` | – | Dienst |
| `S3_ACCESS_KEY` | Text | – | ja, auch `S3_ACCESS_KEY_FILE` | Dienst |
| `S3_SECRET_KEY` | Text | – | ja, auch `S3_SECRET_KEY_FILE` | Dienst |
| `OPENAI_API_KEY` | Text | – | ja, auch `OPENAI_API_KEY_FILE` | Sprachmodell |
| `OPENAI_BASE_URL` | Text | `https://api.openai.com/v1` | – | Sprachmodell |
| `OPENAI_MODEL` | Text | `gpt-6-luna` | – | Sprachmodell |
| `OPENAI_REASONING_EFFORT` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` | `low` | – | Sprachmodell |
| `OPENAI_TEXT_VERBOSITY` | `low` \| `medium` \| `high` | `low` | – | Sprachmodell |
| `LLM_PROVIDER` | `openai` \| `openai-compatible` | `openai` | – | Sprachmodell |
| `LLM_CONTEXT_TOKENS` | Zahl ≥ 8000 | – | – | Sprachmodell |
<!-- settings:end -->

## Für einen Cluster

- `HOST` setzt das Image auf `0.0.0.0`; außerhalb des Images bleibt der Dienst auf Loopback.
- `STORAGE_BACKEND=s3` mit `S3_BUCKET` und, wo der Pod keine Rolle hat, `S3_ACCESS_KEY_FILE` und
  `S3_SECRET_KEY_FILE`.
- `FORWARDED_ALLOW_IPS`: die Adressen oder Netze des Ingress, nie `*` und nie ein Netz `/0`.
- `JOB_SHUTDOWN_GRACE_S` mindestens 5 s unter `terminationGracePeriodSeconds` des Workers.
- `LOG_FORMAT=json` für die zentrale Logsammlung.
