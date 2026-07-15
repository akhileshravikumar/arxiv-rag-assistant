import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode

import requests

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database.database import SessionLocal
from app.models.paper import Paper


ARXIV_API_URL = "https://export.arxiv.org/api/query"

NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
}

# Resolve directories relative to the repository root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
METADATA_FILE = PROCESSED_DATA_DIR / "arxiv_metadata.json"


HEADERS = {
    "User-Agent": "ArxivRAGAssistant/0.1 (contact: akhileshravikumar2@gmail.com)"
}


def normalize_text(value: str | None) -> str:
    """
    Remove excessive spaces and line breaks from arXiv text fields.
    """
    if not value:
        return ""

    return " ".join(value.split())

def parse_arxiv_published_date(published_value: str):
    """
    Convert an arXiv timestamp into a Python date.

    Example:
    2020-05-22T08:00:00Z
    becomes:
    date(2020, 5, 22)
    """
    if not published_value:
        raise ValueError("Published date is missing.")

    published_datetime = datetime.fromisoformat(
        published_value.replace("Z", "+00:00")
    )

    return published_datetime.date()


def sanitize_filename(value: str) -> str:
    """
    Convert a paper title into a filename-safe string.
    """
    cleaned = re.sub(r'[<>:"/\\|?*]', "", value)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())

    # Keep filenames at a manageable length.
    return cleaned[:120] or "untitled_paper"


def extract_arxiv_id(entry_id: str) -> str:
    """
    Extract the arXiv identifier from an entry URL.
    """
    return entry_id.rstrip("/").split("/")[-1]


def build_query_url(search_term: str, max_results: int) -> str:
    """
    Build a properly encoded arXiv API query URL.
    """
    parameters = {
        "search_query": f'all:"{search_term}"',
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    return f"{ARXIV_API_URL}?{urlencode(parameters)}"


def find_pdf_url(entry: ET.Element) -> str | None:
    """
    Locate the PDF link inside an arXiv Atom entry.
    """
    for link in entry.findall("atom:link", NAMESPACES):
        link_title = link.attrib.get("title")
        link_type = link.attrib.get("type")
        href = link.attrib.get("href")

        if link_title == "pdf" and href:
            return href

        if link_type == "application/pdf" and href:
            return href

    return None


def parse_entries(xml_content: bytes) -> list[dict]:
    """
    Convert the Atom XML response into a list of paper dictionaries.
    """
    root = ET.fromstring(xml_content)
    papers: list[dict] = []

    for entry in root.findall("atom:entry", NAMESPACES):
        entry_id = normalize_text(entry.findtext("atom:id", namespaces=NAMESPACES))
        title = normalize_text(entry.findtext("atom:title", namespaces=NAMESPACES))
        summary = normalize_text(
            entry.findtext("atom:summary", namespaces=NAMESPACES)
        )
        published = normalize_text(
            entry.findtext("atom:published", namespaces=NAMESPACES)
        )
        updated = normalize_text(
            entry.findtext("atom:updated", namespaces=NAMESPACES)
        )

        authors = []

        for author_element in entry.findall("atom:author", NAMESPACES):
            author_name = normalize_text(
                author_element.findtext("atom:name", namespaces=NAMESPACES)
            )

            if author_name:
                authors.append(author_name)

        pdf_url = find_pdf_url(entry)

        paper = {
            "arxiv_id": extract_arxiv_id(entry_id),
            "title": title,
            "authors": authors,
            "published": published,
            "updated": updated,
            "summary": summary,
            "abstract_url": entry_id,
            "pdf_url": pdf_url,
        }

        papers.append(paper)

    return papers


def search_arxiv(search_term: str, max_results: int = 5) -> list[dict]:
    """
    Search arXiv and return parsed paper metadata.
    """
    query_url = build_query_url(search_term, max_results)

    print(f"Searching arXiv for: {search_term}")
    print(f"Request URL: {query_url}")

    try:
        response = requests.get(
            query_url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

    except requests.Timeout as exc:
        raise RuntimeError("The arXiv API request timed out.") from exc

    except requests.RequestException as exc:
        raise RuntimeError(f"The arXiv API request failed: {exc}") from exc

    try:
        return parse_entries(response.content)

    except ET.ParseError as exc:
        raise RuntimeError("The arXiv API returned invalid XML.") from exc


def download_pdf(pdf_url: str, destination: Path) -> None:
    """
    Download one PDF to the requested destination.
    """
    temporary_destination = destination.with_suffix(".pdf.part")

    try:
        with requests.get(
            pdf_url,
            headers=HEADERS,
            timeout=60,
            stream=True,
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()

            if "pdf" not in content_type:
                raise RuntimeError(
                    f"Expected a PDF but received Content-Type: {content_type}"
                )

            with temporary_destination.open("wb") as pdf_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        pdf_file.write(chunk)

        temporary_destination.replace(destination)

    except requests.RequestException as exc:
        temporary_destination.unlink(missing_ok=True)
        raise RuntimeError(f"PDF download failed: {exc}") from exc

    except OSError as exc:
        temporary_destination.unlink(missing_ok=True)
        raise RuntimeError(f"Could not save PDF: {exc}") from exc


def load_existing_metadata() -> list[dict]:
    """
    Read metadata generated during an earlier run.
    """
    if not METADATA_FILE.exists():
        return []

    try:
        with METADATA_FILE.open("r", encoding="utf-8") as metadata_file:
            content = json.load(metadata_file)

        if isinstance(content, list):
            return content

        return []

    except (json.JSONDecodeError, OSError):
        print(
            "Warning: Existing metadata could not be read. "
            "A new metadata file will be created."
        )
        return []


def save_metadata(new_papers: list[dict]) -> None:
    """
    Merge new paper metadata with previously saved metadata.
    """
    existing_papers = load_existing_metadata()

    # Use arXiv ID as the deduplication key.
    papers_by_id = {
        paper["arxiv_id"]: paper
        for paper in existing_papers
        if paper.get("arxiv_id")
    }

    for paper in new_papers:
        papers_by_id[paper["arxiv_id"]] = paper

    combined_papers = list(papers_by_id.values())

    with METADATA_FILE.open("w", encoding="utf-8") as metadata_file:
        json.dump(
            combined_papers,
            metadata_file,
            indent=2,
            ensure_ascii=False,
        )


def process_papers(papers: list[dict]) -> list[dict]:
    """
    Download the PDF for each paper and add its local path to the metadata.
    """
    processed_papers: list[dict] = []

    for index, paper in enumerate(papers, start=1):
        print()
        print(f"[{index}/{len(papers)}] {paper['title']}")
        print(f"Authors: {', '.join(paper['authors'])}")
        print(f"Published: {paper['published']}")
        print(f"PDF URL: {paper['pdf_url']}")

        pdf_url = paper.get("pdf_url")

        if not pdf_url:
            print("Skipped: No PDF URL was found.")
            paper["download_status"] = "missing_pdf_url"
            processed_papers.append(paper)
            continue

        filename = (
            f"{paper['arxiv_id'].replace('/', '_')}_"
            f"{sanitize_filename(paper['title'])}.pdf"
        )

        destination = RAW_DATA_DIR / filename

        if destination.exists():
            print(f"Already downloaded: {destination.name}")
            paper["download_status"] = "already_exists"
        else:
            try:
                download_pdf(pdf_url, destination)
                print(f"Downloaded: {destination.name}")
                paper["download_status"] = "downloaded"

            except RuntimeError as exc:
                print(f"Download error: {exc}")
                paper["download_status"] = "failed"
                paper["download_error"] = str(exc)

        paper["local_pdf_path"] = str(
            destination.relative_to(PROJECT_ROOT)
        )

        processed_papers.append(paper)

        if index < len(papers):
            time.sleep(3)

    return processed_papers


def parse_arguments() -> argparse.Namespace:
    """
    Read command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Search arXiv and download research-paper PDFs."
    )

    parser.add_argument(
        "query",
        help='Search term, for example: "LLM"',
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of papers to download. Default: 5",
    )

    arguments = parser.parse_args()

    if arguments.max_results < 1 or arguments.max_results > 20:
        parser.error("--max-results must be between 1 and 20.")

    return arguments



def save_papers_to_database(papers: list[dict]) -> dict:
    """
    Insert downloaded paper metadata into PostgreSQL.

    Papers with an existing PDF URL are skipped.
    """
    db = SessionLocal()

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        for paper_data in papers:
            pdf_url = paper_data.get("pdf_url")

            if not pdf_url:
                print(
                    f"Database skipped: No PDF URL for "
                    f"{paper_data.get('title', 'Untitled paper')}"
                )
                skipped_count += 1
                continue

            existing_paper = db.scalar(
                select(Paper).where(Paper.pdf_url == pdf_url)
            )

            if existing_paper is not None:
                print(
                    f"Database skipped: Paper already exists: "
                    f"{paper_data['title']}"
                )
                skipped_count += 1
                continue

            try:
                published_date = parse_arxiv_published_date(
                    paper_data["published"]
                )

                db_paper = Paper(
                    title=paper_data["title"],
                    authors=paper_data["authors"],
                    published=published_date,
                    pdf_url=pdf_url,
                )

                db.add(db_paper)
                db.commit()
                db.refresh(db_paper)

                inserted_count += 1

                print(
                    f"Database inserted: ID {db_paper.id} - "
                    f"{db_paper.title}"
                )

            except (KeyError, TypeError, ValueError) as exc:
                db.rollback()
                failed_count += 1

                print(
                    f"Database validation error for "
                    f"{paper_data.get('title', 'Unknown paper')}: {exc}"
                )

            except IntegrityError:
                db.rollback()
                skipped_count += 1

                print(
                    f"Database skipped duplicate: "
                    f"{paper_data.get('title', 'Unknown paper')}"
                )

            except SQLAlchemyError as exc:
                db.rollback()
                failed_count += 1

                print(
                    f"Database error for "
                    f"{paper_data.get('title', 'Unknown paper')}: {exc}"
                )

    finally:
        db.close()

    return {
        "inserted": inserted_count,
        "skipped": skipped_count,
        "failed": failed_count,
    }

def main() -> int:
    """
    Run the complete search and download process.
    """
    arguments = parse_arguments()

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        papers = search_arxiv(
            search_term=arguments.query,
            max_results=arguments.max_results,
        )

        if not papers:
            print("No matching papers were found.")
            return 0

        print(f"Found {len(papers)} papers.")

        processed_papers = process_papers(papers)

        save_metadata(processed_papers)

        database_result = save_papers_to_database(
            processed_papers
        )

        successful_downloads = sum(
            paper.get("download_status")
            in {"downloaded", "already_exists"}
            for paper in processed_papers
        )

        print()
        print("Download process complete.")
        print(
            f"PDFs available: "
            f"{successful_downloads}/{len(processed_papers)}"
        )
        print(f"PDF directory: {RAW_DATA_DIR}")
        print(f"Metadata file: {METADATA_FILE}")

        print()
        print("Database result:")
        print(f"Inserted: {database_result['inserted']}")
        print(f"Skipped: {database_result['skipped']}")
        print(f"Failed: {database_result['failed']}")

        return 0

    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())