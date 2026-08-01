"""Local-only Apache Superset configuration."""

import os
from urllib.parse import quote_plus


def required_env(name: str) -> str:
    """Read a required value without providing an insecure fallback."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


postgres_user = quote_plus(required_env("POSTGRES_USER"))
postgres_password = quote_plus(required_env("POSTGRES_PASSWORD"))
metadata_database = quote_plus(required_env("SUPERSET_METADATA_DB"))

SECRET_KEY = required_env("SUPERSET_SECRET_KEY")
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://"
    f"{postgres_user}:{postgres_password}@postgres:5432/{metadata_database}"
)

# This configuration is only served over localhost HTTP.
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = True
SQLALCHEMY_TRACK_MODIFICATIONS = False
