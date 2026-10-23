"""``python -m app.vocab.load``: read the vocabularies under ONTOLOGY_DIR and load them.

Exit code 0 when the database holds the files' content afterwards (loaded now or before),
1 when the files or the database refused. Logs go to stderr.
"""

import logging
import sys

import psycopg

from app.core.logging import configure_logging
from app.core.settings import Settings
from app.vocab.loader import VocabularyError, read_vocabulary
from app.vocab.store import load_vocabulary

log = logging.getLogger("app.vocab.load")  # also when run as __main__


def main() -> int:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    try:
        vocabulary = read_vocabulary(settings.ontology_dir)
        result = load_vocabulary(settings.database_url.get_secret_value(), vocabulary)
    except (VocabularyError, OSError, psycopg.Error) as error:
        log.error("vocabulary not loaded: %s", " ".join(str(error).split()))
        return 1
    if result.changed:
        counts = (
            len(vocabulary.schemes),
            len(vocabulary.concepts),
            len(vocabulary.profiles),
            len(vocabulary.cues),
        )
        log.info(
            "loaded release %d: %d schemes, %d concepts, %d profiles, %d cues", result.release_id, *counts
        )
    else:
        log.info("release %d unchanged", result.release_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
