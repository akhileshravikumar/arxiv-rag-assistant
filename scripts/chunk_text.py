import argparse
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.database.database import SessionLocal
from app.services.chunking_service import (
    ChunkingService,
    read_text_file,
    save_chunks_to_database,
    save_chunks_to_json,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CHUNKS_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "chunks"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split extracted paper text into "
            "overlapping chunks and store them "
            "in PostgreSQL."
        )
    )

    parser.add_argument(
        "input_path",
        help="Path to an extracted .txt paper.",
    )

    parser.add_argument(
        "--paper-id",
        type=int,
        required=True,
        help=(
            "ID of the corresponding paper "
            "in PostgreSQL."
        ),
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help=(
            "Maximum characters per chunk. "
            "Default: 1000"
        ),
    )

    parser.add_argument(
        "--overlap",
        type=int,
        default=200,
        help=(
            "Overlapping characters between "
            "chunks. Default: 200"
        ),
    )

    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help=(
            "Delete existing chunks for the "
            "paper before inserting new chunks."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    input_path = Path(
        arguments.input_path
    ).expanduser().resolve()

    output_path = (
        CHUNKS_DIR
        / f"{input_path.stem}_chunks.json"
    )

    db = SessionLocal()

    try:
        text = read_text_file(input_path)

        chunking_service = ChunkingService(
            chunk_size=arguments.chunk_size,
            overlap=arguments.overlap,
        )

        chunks = (
            chunking_service.create_chunks(
                text=text,
                paper_name=input_path.stem,
            )
        )

        saved_json_path = (
            save_chunks_to_json(
                chunks=chunks,
                output_path=output_path,
            )
        )

        database_result = (
            save_chunks_to_database(
                db=db,
                chunks=chunks,
                paper_id=arguments.paper_id,
                replace_existing=(
                    arguments.replace_existing
                ),
                commit=True,
            )
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        OSError,
        SQLAlchemyError,
    ) as exc:
        db.rollback()

        print(
            f"Chunking error: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        db.close()

    print()
    print(
        "Document chunking completed "
        "successfully."
    )
    print(f"Input file: {input_path}")
    print(f"JSON output: {saved_json_path}")
    print(f"Text characters: {len(text)}")
    print(
        f"Chunk size: "
        f"{arguments.chunk_size}"
    )
    print(f"Overlap: {arguments.overlap}")
    print(
        "Step size: "
        f"{arguments.chunk_size - arguments.overlap}"
    )
    print(
        f"Chunks generated: {len(chunks)}"
    )

    print()
    print("Database result:")
    print(
        f"Paper ID: "
        f"{database_result['paper_id']}"
    )
    print(
        "Paper title: "
        f"{database_result['paper_title']}"
    )
    print(
        f"Inserted: "
        f"{database_result['inserted']}"
    )
    print(
        f"Skipped: "
        f"{database_result['skipped']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())