# The API and the worker: one image, two commands (python -m app.serve, python -m app.jobs.worker).
# Build from the repository root: docker build -f deploy/api.Dockerfile .
#
# Bases are pinned by digest: a build tomorrow gives the same image, and a Debian or CPython
# security fix arrives as a new digest someone chooses to take. python:3.13-slim (Debian trixie).
FROM python:3.13-slim@sha256:27b7c9d4f13ca20bb1170148f02095d50a5dfce1f7f2dabf5ca273727e43b7ea AS build
# The runtime packages of uv.lock, exported with their hashes (a test keeps the export equal to the
# lock): pip checks every file against its hash, takes wheels only, so nothing compiles here, and
# installs nothing the export does not name. No uv in the image: pip comes with the base.
COPY deploy/requirements-api.txt /tmp/requirements-api.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check \
       --require-hashes --no-deps --only-binary=:all: -r /tmp/requirements-api.txt

FROM python:3.13-slim@sha256:27b7c9d4f13ca20bb1170148f02095d50a5dfce1f7f2dabf5ca273727e43b7ea AS runtime
# Code and ontology belong to root: the service reads them, it cannot change them. It writes
# nothing to the image; objects go to the object store, rows to PostgreSQL. With a read-only root
# file system (Compose, Helm) only /tmp stays writable.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin kka
COPY --from=build /opt/venv /opt/venv
# The repository's layout: settings find ontology/ two folders above app/ by default; ONTOLOGY_DIR
# says it as well, for whoever reads the environment. Of ontology/ only what the service reads
# (MODEL_DIRS in app/vocab/loader.py), not the research notes, examples and tools beside it.
COPY backend/app /srv/backend/app
COPY ontology/ontologie /srv/ontology/ontologie
COPY ontology/vokabulare /srv/ontology/vokabulare
COPY ontology/profile /srv/ontology/profile
# The published seed of the source register (python -m app.sources.seed), 2 MB
COPY data/seed /srv/data/seed
RUN python -m compileall -q /srv/backend/app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    ONTOLOGY_DIR=/srv/ontology
WORKDIR /srv/backend
USER 10001
# 8000 the public API, 9000 the internal port: /health, /ready, /metrics
EXPOSE 8000 9000
# A GET: /health answers HEAD with 405, and wget --spider sends HEAD. The worker answers
# /health on the same internal port, so the check serves both commands.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request; port = int(os.environ.get('INTERNAL_PORT') or 9000); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3).status == 200 else 1)"]
CMD ["python", "-m", "app.serve"]
