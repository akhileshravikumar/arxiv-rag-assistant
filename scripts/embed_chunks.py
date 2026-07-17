import argparse
import sys
import time

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.chunk import Chunk
from app.services.embedding_service import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    EmbeddingService,
)


def count_chunks(db: Session) -> dict[str, int]:
    """
    Count total, embedded and unembedded chunks.
    """
    total_chunks = db.scalar(
        select(func.count()).select_from(Chunk)
    ) or 0

    embedded_chunks = db.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.embedding.is_not(None))
    ) or 0

    return {
        "total": total_chunks,
        "embedded": embedded_chunks,
        "missing": total_chunks - embedded_chunks,
    }


def fetch_unembedded_chunks(
    db: Session,
    database_batch_size: int,
) -> list[Chunk]:
    """
    Retrieve the next batch of chunks without embeddings.
    """
    statement = (
        select(Chunk)
        .where(Chunk.embedding.is_(None))
        .order_by(Chunk.id)
        .limit(database_batch_size)
    )

    return list(db.scalars(statement).all())


def embed_chunk_batch(
    db: Session,
    embedding_service: EmbeddingService,
    chunks: list[Chunk],
    model_batch_size: int,
) -> int:
    """
    Generate embeddings and attach each vector to its matching row.
    """
    if not chunks:
        return 0

    texts = [chunk.text for chunk in chunks]

    embeddings = embedding_service.embed_documents(
        texts=texts,
        batch_size=model_batch_size,
    )

    if len(embeddings) != len(chunks):
        raise RuntimeError(
            "The number of embeddings does not match "
            "the number of chunks."
        )

    for chunk, embedding in zip(
        chunks,
        embeddings,
        strict=True,
    ):
        if len(embedding) != EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Chunk {chunk.id} received an invalid "
                f"embedding dimension."
            )

        chunk.embedding = embedding

    db.commit()

    return len(chunks)


def embed_all_missing_chunks(
    database_batch_size: int,
    model_batch_size: int,
    max_chunks: int | None = None,
) -> dict[str, int | float]:
    """
    Embed all chunks whose embedding column is NULL.
    """
    db = SessionLocal()
    embedding_service: EmbeddingService | None = None

    embedded_during_run = 0
    batch_number = 0
    started_at = time.perf_counter()

    try:
        initial_counts = count_chunks(db)

        if initial_counts["total"] == 0:
            raise RuntimeError(
                "The chunks table is empty. "
                "Run the document chunking pipeline first."
            )

        print("Initial database state:")
        print(f"Total chunks: {initial_counts['total']}")
        print(f"Already embedded: {initial_counts['embedded']}")
        print(f"Missing embeddings: {initial_counts['missing']}")

        if initial_counts["missing"] == 0:
            print("All chunks already have embeddings.")

            return {
                "initial_missing": 0,
                "embedded": 0,
                "remaining": 0,
                "seconds": 0.0,
            }

        embedding_service = EmbeddingService()

        while True:
            if (
                max_chunks is not None
                and embedded_during_run >= max_chunks
            ):
                break

            current_batch_size = database_batch_size

            if max_chunks is not None:
                remaining_allowed = (
                    max_chunks - embedded_during_run
                )

                current_batch_size = min(
                    current_batch_size,
                    remaining_allowed,
                )

            chunks = fetch_unembedded_chunks(
                db=db,
                database_batch_size=current_batch_size,
            )

            if not chunks:
                break

            batch_number += 1

            first_chunk_id = chunks[0].id
            last_chunk_id = chunks[-1].id

            print()
            print(
                f"Batch {batch_number}: embedding "
                f"{len(chunks)} chunks "
                f"(IDs {first_chunk_id}-{last_chunk_id})"
            )

            try:
                saved_count = embed_chunk_batch(
                    db=db,
                    embedding_service=embedding_service,
                    chunks=chunks,
                    model_batch_size=model_batch_size,
                )

                embedded_during_run += saved_count

                print(
                    f"Batch {batch_number} committed. "
                    f"Total embedded this run: "
                    f"{embedded_during_run}"
                )

            except Exception:
                db.rollback()
                raise

            # Remove loaded ORM objects from the session.
            db.expire_all()

        final_counts = count_chunks(db)

        elapsed_seconds = (
            time.perf_counter() - started_at
        )

        return {
            "initial_missing": initial_counts["missing"],
            "embedded": embedded_during_run,
            "remaining": final_counts["missing"],
            "seconds": elapsed_seconds,
        }

    except SQLAlchemyError as exc:
        db.rollback()

        raise RuntimeError(
            f"Database operation failed: {exc}"
        ) from exc

    finally:
        db.close()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate embeddings for PostgreSQL chunks "
            "that do not already have vectors."
        )
    )

    parser.add_argument(
        "--database-batch-size",
        type=int,
        default=50,
        help=(
            "Chunks retrieved and committed per database batch. "
            "Default: 50"
        ),
    )

    parser.add_argument(
        "--model-batch-size",
        type=int,
        default=16,
        help=(
            "Texts processed together by the embedding model. "
            "Default: 16"
        ),
    )

    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help=(
            "Optional limit for testing. "
            "By default, all missing embeddings are generated."
        ),
    )

    arguments = parser.parse_args()

    if arguments.database_batch_size < 1:
        parser.error(
            "--database-batch-size must be at least 1."
        )

    if arguments.model_batch_size < 1:
        parser.error(
            "--model-batch-size must be at least 1."
        )

    if (
        arguments.max_chunks is not None
        and arguments.max_chunks < 1
    ):
        parser.error(
            "--max-chunks must be at least 1."
        )

    return arguments


def main() -> int:
    arguments = parse_arguments()

    print(f"Embedding model: {EMBEDDING_MODEL_NAME}")
    print(f"Embedding dimensions: {EMBEDDING_DIMENSION}")
    print(
        f"Database batch size: "
        f"{arguments.database_batch_size}"
    )
    print(
        f"Model batch size: "
        f"{arguments.model_batch_size}"
    )

    try:
        result = embed_all_missing_chunks(
            database_batch_size=(
                arguments.database_batch_size
            ),
            model_batch_size=arguments.model_batch_size,
            max_chunks=arguments.max_chunks,
        )

    except (
        RuntimeError,
        ValueError,
        MemoryError,
    ) as exc:
        print(
            f"Embedding error: {exc}",
            file=sys.stderr,
        )
        return 1

    print()
    print("Embedding process completed.")
    print(
        f"Initially missing: "
        f"{result['initial_missing']}"
    )
    print(
        f"Embedded this run: "
        f"{result['embedded']}"
    )
    print(
        f"Remaining without embeddings: "
        f"{result['remaining']}"
    )
    print(
        f"Elapsed time: "
        f"{result['seconds']:.2f} seconds"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())