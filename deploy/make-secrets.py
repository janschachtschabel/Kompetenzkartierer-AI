"""Write the secrets of the local Compose setup into deploy/secrets/, one file each.

    python deploy/make-secrets.py

A file that exists is kept: run it again and nothing changes, so a database made with one
password keeps working. The files are random, never committed (.gitignore), and readable by
every user of this machine: Compose hands them to the containers as bind mounts, and the
containers run as other users (postgres, 10001, 65532) than the one who made them. That is
for a developer's machine; a cluster takes its secrets from Kubernetes (helm-values.example).
"""

import secrets
import stat
import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parent / "secrets"


def values() -> dict[str, str]:
    """The secrets, made fresh; database_url is derived from db_password when both are new."""
    password = secrets.token_urlsafe(24)
    return {
        "db_password": password,
        "database_url": f"postgresql://kka:{password}@postgres:5432/kka",
        "api_key_pepper": secrets.token_urlsafe(48),
        "s3_access_key": "kka-" + secrets.token_hex(8),
        "s3_secret_key": secrets.token_urlsafe(32),
    }


def main() -> int:
    FOLDER.mkdir(exist_ok=True)
    fresh = values()
    if (FOLDER / "db_password").exists() != (FOLDER / "database_url").exists():
        print("db_password and database_url must be made together; remove both or neither", file=sys.stderr)
        return 1
    for name, value in fresh.items():
        path = FOLDER / name
        if path.exists():
            print(f"kept    {name}")
            continue
        path.write_text(value, encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        print(f"written {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
