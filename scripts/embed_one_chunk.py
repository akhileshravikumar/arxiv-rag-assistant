from sqlalchemy import select

from app.database.database import SessionLocal
from app.models.chunk import Chunk
from app.services.embedding_service import EmbeddingService


def main() -> None:
    db = SessionLocal()

    try:
        chunk = db.scalar(
            select(Chunk).order_by(Chunk.id).limit(1)
        )

        if chunk is None:
            raise RuntimeError(
                "No chunks exist. Run the chunking pipeline first."
            )

        embedding_service = EmbeddingService()
        chunk.embedding = embedding_service.embed_text(chunk.text)

        db.commit()

        print(f"Embedded chunk ID: {chunk.id}")
        print(f"Vector dimensions: {len(chunk.embedding)}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()