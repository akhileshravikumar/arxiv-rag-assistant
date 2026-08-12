"""
Drop every application table and recreate it from the current models.

Sessions are disposable by design, so there is never anything worth
migrating. When the models change, reset rather than writing a
migration.

Usage:

    python -m scripts.reset_database
    python -m scripts.reset_database --yes     # skip confirmation
    python -m scripts.reset_database --drop-only
"""

import argparse
import sys
from urllib.parse import urlparse

from sqlalchemy import inspect, text

from app.database.database import (
    Base,
    get_engine,
    resolve_database_url,
)

# Importing the models registers them on Base.metadata, which is what
# create_all() builds from.
from app.models import (  # noqa: F401
    Chunk,
    Paper,
    ResearchSession,
)


# Includes tables from the pre-session schema so a database carried over
# from an earlier version is cleaned out completely.
APPLICATION_TABLES = [
    "chunks",
    "papers",
    "research_sessions",
    "users",
]


def describe_target() -> str:
    parsed = urlparse(
        resolve_database_url().replace(
            "postgresql+psycopg://",
            "postgresql://",
            1,
        )
    )

    database = (parsed.path or "/").lstrip("/")

    return f"{database} on {parsed.hostname}"


def confirm(target: str) -> bool:
    print(f"This will DROP every table in: {target}")
    print("All papers, chunks and sessions will be lost.")

    answer = input("Type 'reset' to continue: ").strip()

    return answer == "reset"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Drop and recreate the application schema."
        )
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )

    parser.add_argument(
        "--drop-only",
        action="store_true",
        help=(
            "Drop the tables without recreating them. "
            "The application recreates them at startup."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        target = describe_target()

    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)

        return 1

    print(f"Target: {target}\n")

    if not arguments.yes and not confirm(target):
        print("Cancelled.")

        return 1

    engine = get_engine()

    with engine.begin() as connection:
        existing = set(
            inspect(connection).get_table_names()
        )

        for table in APPLICATION_TABLES:
            if table in existing:
                connection.execute(
                    text(
                        f"DROP TABLE IF EXISTS "
                        f"{table} CASCADE"
                    )
                )

                print(f"  dropped {table}")

    if arguments.drop_only:
        print(
            "\nTables dropped. They are recreated "
            "when the application starts."
        )

        return 0

    Base.metadata.create_all(bind=engine)

    with engine.connect() as connection:
        created = sorted(
            inspect(connection).get_table_names()
        )

    print("\nRecreated:")

    for table in created:
        print(f"  {table}")

    print("\nDatabase is ready.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
