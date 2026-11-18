"""Adapt the DB endpoint for Compose without replacing existing credentials."""

import os

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def database_url(environment):
    try:
        url = make_url(environment["DATABASE_URL"])
        if url.drivername not in ("postgresql", "postgresql+asyncpg"):
            raise ValueError("Unsupported database driver")
        port = int(environment.get("DATABASE_PORT_OVERRIDE", "5432"))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid database port")
        return url.set(
            drivername="postgresql+asyncpg",
            host=environment["DATABASE_HOST_OVERRIDE"],
            port=port,
        ).render_as_string(hide_password=False)
    except (KeyError, ValueError, TypeError, ArgumentError):
        # Do not include the URL or SQLAlchemy's parsing exception in logs.
        raise ValueError(
            "Invalid DATABASE_URL or Docker database endpoint; restore the original private database configuration"
        ) from None


if __name__ == "__main__":
    try:
        print(database_url(os.environ))
    except ValueError as error:
        raise SystemExit(str(error)) from None
