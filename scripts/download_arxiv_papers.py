import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import (
    IntegrityError,
    SQLAlchemyError,
)

from app.database.database import SessionLocal
from app.models.paper import Paper
from app.services.arxiv_service import (
    parse_arxiv_published_date,
    process_papers,
    save_metadata,
    search_arxiv,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
)

METADATA_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "arxiv_metadata.json"
)


def save_papers_to_database(
    papers: list[dict],
) -> dict:
    db = SessionLocal()

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        for paper_data in papers:
            pdf_url = paper_data.get(
                "pdf_url"
            )

            if not pdf_url:
                print(
                    "Database skipped: "
                    "No PDF URL for "
                    f"{paper_data.get('title', 'Untitled paper')}"
                )

                skipped_count += 1
                continue

            existing_paper = db.scalar(
                select(Paper).where(
                    Paper.pdf_url == pdf_url
                )
            )

            if existing_paper is not None:
                print(
                    "Database skipped: "
                    "Paper already exists: "
                    f"{paper_data['title']}"
                )

                skipped_count += 1
                continue

            try:
                database_paper = Paper(
                    title=paper_data["title"],
                    authors=paper_data[
                        "authors"
                    ],
                    published=(
                        parse_arxiv_published_date(
                            paper_data[
                                "published"
                            ]
                        )
                    ),
                    pdf_url=pdf_url,
                )

                db.add(database_paper)
                db.commit()
                db.refresh(database_paper)

                inserted_count += 1

                print(
                    "Database inserted: "
                    f"ID {database_paper.id} - "
                    f"{database_paper.title}"
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                db.rollback()
                failed_count += 1

                print(
                    "Database validation error "
                    f"for {paper_data.get('title', 'Unknown paper')}: "
                    f"{exc}"
                )

            except IntegrityError:
                db.rollback()
                skipped_count += 1

                print(
                    "Database duplicate skipped: "
                    f"{paper_data.get('title', 'Unknown paper')}"
                )

            except SQLAlchemyError as exc:
                db.rollback()
                failed_count += 1

                print(
                    "Database error for "
                    f"{paper_data.get('title', 'Unknown paper')}: "
                    f"{exc}"
                )

    finally:
        db.close()

    return {
        "inserted": inserted_count,
        "skipped": skipped_count,
        "failed": failed_count,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search arXiv, download PDFs, save "
            "metadata, and insert paper records."
        )
    )

    parser.add_argument(
        "query",
        help='Search term, for example: "LLM"',
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help=(
            "Maximum papers to retrieve. "
            "Default: 5"
        ),
    )

    arguments = parser.parse_args()

    if (
        arguments.max_results < 1
        or arguments.max_results > 20
    ):
        parser.error(
            "--max-results must be between "
            "1 and 20."
        )

    return arguments


def main() -> int:
    arguments = parse_arguments()

    RAW_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    METADATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        print(
            f"Searching arXiv for: "
            f"{arguments.query}"
        )

        papers = search_arxiv(
            search_term=arguments.query,
            max_results=arguments.max_results,
        )

        if not papers:
            print("No matching papers were found.")
            return 0

        print(f"Found {len(papers)} papers.")

        processed_papers = process_papers(
            papers=papers,
            raw_data_directory=RAW_DATA_DIR,
            delay_seconds=3,
        )

        for index, paper in enumerate(
            processed_papers,
            start=1,
        ):
            print()
            print(
                f"[{index}/{len(processed_papers)}] "
                f"{paper['title']}"
            )
            print(
                "Status: "
                f"{paper.get('download_status')}"
            )
            print(
                "PDF: "
                f"{paper.get('local_pdf_path', 'Unavailable')}"
            )

            if paper.get("download_error"):
                print(
                    "Error: "
                    f"{paper['download_error']}"
                )

        save_metadata(
            new_papers=processed_papers,
            metadata_file=METADATA_FILE,
        )

        database_result = (
            save_papers_to_database(
                processed_papers
            )
        )

        successful_downloads = sum(
            paper.get("download_status")
            in {
                "downloaded",
                "already_exists",
            }
            for paper in processed_papers
        )

        print()
        print("Download process complete.")
        print(
            "PDFs available: "
            f"{successful_downloads}/"
            f"{len(processed_papers)}"
        )
        print(
            f"PDF directory: {RAW_DATA_DIR}"
        )
        print(
            f"Metadata file: {METADATA_FILE}"
        )

        print()
        print("Database result:")
        print(
            f"Inserted: "
            f"{database_result['inserted']}"
        )
        print(
            f"Skipped: "
            f"{database_result['skipped']}"
        )
        print(
            f"Failed: "
            f"{database_result['failed']}"
        )

        return 0

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())