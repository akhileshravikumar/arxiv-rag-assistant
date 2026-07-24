import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.paper import Paper


@dataclass(frozen=True)
class TextChunk:
    chunk_id: int
    paper: str
    text: str
    char_start: int
    char_end: int

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "paper": self.paper,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


class ChunkingService:
    def __init__(
        self,
        chunk_size: int = 1000,
        overlap: int = 200,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError(
                "Chunk size must be greater "
                "than zero."
            )

        if overlap < 0:
            raise ValueError(
                "Overlap cannot be negative."
            )

        if overlap >= chunk_size:
            raise ValueError(
                "Overlap must be smaller than "
                "chunk size."
            )

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.step_size = (
            chunk_size - overlap
        )

    def create_chunks(
        self,
        text: str,
        paper_name: str,
    ) -> list[TextChunk]:
        if not text.strip():
            raise ValueError(
                "The supplied text is empty."
            )

        if not paper_name.strip():
            raise ValueError(
                "Paper name cannot be empty."
            )

        chunks: list[TextChunk] = []

        text_length = len(text)
        start = 0
        chunk_index = 0

        while start < text_length:
            end = min(
                start + self.chunk_size,
                text_length,
            )

            chunk_text = text[start:end].strip()

            chunk_text = " ".join(
                chunk_text.split()
            )

            if chunk_text:
                chunks.append(
                    TextChunk(
                        chunk_id=chunk_index,
                        paper=paper_name,
                        text=chunk_text,
                        char_start=start,
                        char_end=end,
                    )
                )

                chunk_index += 1

            if end >= text_length:
                break

            start += self.step_size

        return chunks


def read_text_file(
    input_path: Path,
) -> str:
    resolved_path = (
        input_path.expanduser().resolve()
    )

    if not resolved_path.exists():
        raise FileNotFoundError(
            "Input file does not exist: "
            f"{resolved_path}"
        )

    if not resolved_path.is_file():
        raise ValueError(
            "The input path is not a file: "
            f"{resolved_path}"
        )

    if resolved_path.suffix.lower() != ".txt":
        raise ValueError(
            "The input file must be a .txt "
            f"file: {resolved_path.name}"
        )

    try:
        text = resolved_path.read_text(
            encoding="utf-8"
        )

    except UnicodeDecodeError as exc:
        raise ValueError(
            "The text file is not valid UTF-8."
        ) from exc

    except OSError as exc:
        raise OSError(
            "Could not read the input file: "
            f"{resolved_path}"
        ) from exc

    if not text.strip():
        raise ValueError(
            "The input text file is empty."
        )

    return text


def save_chunks_to_json(
    chunks: list[TextChunk],
    output_path: Path,
) -> Path:
    resolved_output_path = (
        output_path.expanduser().resolve()
    )

    resolved_output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = [
        chunk.to_dict()
        for chunk in chunks
    ]

    try:
        with resolved_output_path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                payload,
                output_file,
                ensure_ascii=False,
                indent=2,
            )

    except OSError as exc:
        raise OSError(
            "Could not write chunk JSON: "
            f"{resolved_output_path}"
        ) from exc

    return resolved_output_path


def save_chunks_to_database(
    db: Session,
    chunks: list[TextChunk],
    paper_id: int,
    replace_existing: bool = False,
    commit: bool = True,
) -> dict:
    paper = db.get(Paper, paper_id)

    if paper is None:
        raise ValueError(
            f"No paper exists with ID {paper_id}."
        )

    try:
        if replace_existing:
            db.execute(
                delete(Chunk).where(
                    Chunk.paper_id == paper_id
                )
            )
            db.flush()

        inserted_count = 0
        skipped_count = 0
        database_chunks: list[Chunk] = []

        for chunk_data in chunks:
            existing_chunk = db.scalar(
                select(Chunk).where(
                    Chunk.paper_id == paper_id,
                    Chunk.chunk_index
                    == chunk_data.chunk_id,
                )
            )

            if existing_chunk is not None:
                skipped_count += 1
                continue

            database_chunk = Chunk(
                paper_id=paper_id,
                chunk_index=(
                    chunk_data.chunk_id
                ),
                text=chunk_data.text,
                char_start=(
                    chunk_data.char_start
                ),
                char_end=chunk_data.char_end,
            )

            db.add(database_chunk)
            database_chunks.append(
                database_chunk
            )
            inserted_count += 1

        db.flush()

        if commit:
            db.commit()

        return {
            "paper_id": paper_id,
            "paper_title": paper.title,
            "inserted": inserted_count,
            "skipped": skipped_count,
            "database_chunks": database_chunks,
        }

    except Exception:
        if commit:
            db.rollback()

        raise