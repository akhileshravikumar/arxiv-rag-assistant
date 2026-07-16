import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from app.database.database import SessionLocal
from app.models.chunk import Chunk
from app.models.paper import Paper


PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXTRACTED_TEXT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "extracted_text"
)

CHUNKS_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "chunks"
)


def create_chunks(
    text: str,
    paper_name: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[dict]:
    """
    Divide a string into overlapping character-based chunks.
    """
    if not text.strip():
        raise ValueError("The supplied text is empty.")

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    if overlap < 0:
        raise ValueError("Overlap cannot be negative.")

    if overlap >= chunk_size:
        raise ValueError(
            "Overlap must be smaller than chunk size."
        )

    chunks: list[dict] = []

    step_size = chunk_size - overlap
    text_length = len(text)
    start = 0
    chunk_index = 0

    while start < text_length:
        end = min(
            start + chunk_size,
            text_length,
        )

        chunk_text = text[start:end].strip()
        chunk_text = " ".join(chunk_text.split())

        if chunk_text:
            chunks.append(
                {
                    "chunk_id": chunk_index,
                    "paper": paper_name,
                    "text": chunk_text,
                    "char_start": start,
                    "char_end": end,
                }
            )

            chunk_index += 1

        if end >= text_length:
            break

        start += step_size

    return chunks


def read_text_file(input_path: Path) -> str:
    """
    Read an extracted UTF-8 text file.
    """
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file does not exist: {input_path}"
        )

    if not input_path.is_file():
        raise ValueError(
            f"The input path is not a file: {input_path}"
        )

    if input_path.suffix.lower() != ".txt":
        raise ValueError(
            f"The input file must be a .txt file: {input_path.name}"
        )

    try:
        text = input_path.read_text(
            encoding="utf-8",
        )
    except UnicodeDecodeError as exc:
        raise ValueError(
            "The text file is not valid UTF-8."
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Could not read the input file: {input_path}"
        ) from exc

    if not text.strip():
        raise ValueError(
            "The input text file is empty."
        )

    return text


def save_chunks_to_json(
    chunks: list[dict],
    output_path: Path,
) -> None:

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        with output_path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                chunks,
                output_file,
                ensure_ascii=False,
                indent=2,
            )
    except OSError as exc:
        raise OSError(
            f"Could not write chunk JSON: {output_path}"
        ) from exc


def save_chunks_to_database(
    chunks: list[dict],
    paper_id: int,
    replace_existing: bool = False,
) -> dict:
    """
    Insert text chunks into PostgreSQL.
    """
    db = SessionLocal()

    try:
        paper = db.get(Paper, paper_id)

        if paper is None:
            raise ValueError(
                f"No paper exists with ID {paper_id}."
            )

        if replace_existing:
            db.execute(
                delete(Chunk).where(
                    Chunk.paper_id == paper_id
                )
            )
            db.commit()

        inserted_count = 0
        skipped_count = 0

        for chunk_data in chunks:
            existing_chunk = (
                db.query(Chunk)
                .filter(
                    Chunk.paper_id == paper_id,
                    Chunk.chunk_index
                    == chunk_data["chunk_id"],
                )
                .first()
            )

            if existing_chunk is not None:
                skipped_count += 1
                continue

            database_chunk = Chunk(
                paper_id=paper_id,
                chunk_index=chunk_data["chunk_id"],
                text=chunk_data["text"],
                char_start=chunk_data["char_start"],
                char_end=chunk_data["char_end"],
            )

            db.add(database_chunk)
            inserted_count += 1

        db.commit()

        return {
            "paper_id": paper_id,
            "paper_title": paper.title,
            "inserted": inserted_count,
            "skipped": skipped_count,
        }

    except ValueError:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        db.rollback()

        raise RuntimeError(
            f"Database insertion failed: {exc}"
        ) from exc

    finally:
        db.close()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split extracted paper text into overlapping chunks "
            "and store them in PostgreSQL."
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
        help="ID of the corresponding paper in PostgreSQL.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Maximum characters per chunk. Default: 1000",
    )

    parser.add_argument(
        "--overlap",
        type=int,
        default=200,
        help="Overlapping characters between chunks. Default: 200",
    )

    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help=(
            "Delete existing chunks for this paper before inserting "
            "the newly generated chunks."
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

    try:
        text = read_text_file(input_path)

        chunks = create_chunks(
            text=text,
            paper_name=input_path.stem,
            chunk_size=arguments.chunk_size,
            overlap=arguments.overlap,
        )

        save_chunks_to_json(
            chunks=chunks,
            output_path=output_path,
        )

        database_result = save_chunks_to_database(
            chunks=chunks,
            paper_id=arguments.paper_id,
            replace_existing=arguments.replace_existing,
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        OSError,
    ) as exc:
        print(
            f"Chunking error: {exc}",
            file=sys.stderr,
        )
        return 1

    print()
    print("Document chunking completed successfully.")
    print(f"Input file: {input_path}")
    print(f"JSON output: {output_path}")
    print(f"Text characters: {len(text)}")
    print(f"Chunk size: {arguments.chunk_size}")
    print(f"Overlap: {arguments.overlap}")
    print(
        f"Step size: "
        f"{arguments.chunk_size - arguments.overlap}"
    )
    print(f"Chunks generated: {len(chunks)}")

    print()
    print("Database result:")
    print(f"Paper ID: {database_result['paper_id']}")
    print(f"Paper title: {database_result['paper_title']}")
    print(f"Inserted: {database_result['inserted']}")
    print(f"Skipped: {database_result['skipped']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())