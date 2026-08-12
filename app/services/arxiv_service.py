import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


load_dotenv()


ARXIV_API_URL = "https://export.arxiv.org/api/query"

# The arXiv API is frequently slow under load. A single long timeout
# just holds the request open; a shorter one with a retry recovers from
# the common case of one sluggish response.
ARXIV_TIMEOUT_SECONDS = int(
    os.getenv(
        "ARXIV_TIMEOUT_SECONDS",
        "20",
    )
)

ARXIV_MAX_ATTEMPTS = int(
    os.getenv(
        "ARXIV_MAX_ATTEMPTS",
        "3",
    )
)

ARXIV_RETRY_DELAY_SECONDS = 2

NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
}

HEADERS = {
    "User-Agent": (
        "ArxivRAGAssistant/0.1 "
        "(contact: akhileshravikumar2@gmail.com)"
    )
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(value.split())


def normalize_arxiv_id(value: str) -> str:
    normalized = value.strip()

    prefixes = (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://arxiv.org/pdf/",
        "http://arxiv.org/pdf/",
    )

    for prefix in prefixes:
        normalized = normalized.removeprefix(prefix)

    normalized = normalized.removesuffix(".pdf")

    if not normalized:
        raise ValueError("A valid arXiv ID is required.")

    return normalized


def parse_arxiv_published_date(
    published_value: str,
) -> date:
    if not published_value:
        raise ValueError("Published date is missing.")

    published_datetime = datetime.fromisoformat(
        published_value.replace("Z", "+00:00")
    )

    return published_datetime.date()


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(
        r'[<>:"/\\|?*]',
        "",
        value,
    )
    cleaned = re.sub(
        r"\s+",
        "_",
        cleaned.strip(),
    )

    return cleaned[:120] or "untitled_paper"


def extract_arxiv_id(entry_id: str) -> str:
    return entry_id.rstrip("/").split("/")[-1]


def build_search_query_url(
    search_term: str,
    max_results: int,
) -> str:
    if not search_term.strip():
        raise ValueError("Search term cannot be empty.")

    if max_results < 1 or max_results > 100:
        raise ValueError(
            "max_results must be between 1 and 100."
        )

    parameters = {
        "search_query": f'all:"{search_term.strip()}"',
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    return f"{ARXIV_API_URL}?{urlencode(parameters)}"


def build_id_query_url(arxiv_id: str) -> str:
    normalized_id = normalize_arxiv_id(arxiv_id)

    parameters = {
        "id_list": normalized_id,
        "start": 0,
        "max_results": 1,
    }

    return f"{ARXIV_API_URL}?{urlencode(parameters)}"


def find_pdf_url(
    entry: ET.Element,
) -> str | None:
    for link in entry.findall(
        "atom:link",
        NAMESPACES,
    ):
        link_title = link.attrib.get("title")
        link_type = link.attrib.get("type")
        href = link.attrib.get("href")

        if link_title == "pdf" and href:
            return href

        if (
            link_type == "application/pdf"
            and href
        ):
            return href

    return None


def parse_entries(
    xml_content: bytes,
) -> list[dict]:
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise RuntimeError(
            "The arXiv API returned invalid XML."
        ) from exc

    papers: list[dict] = []

    for entry in root.findall(
        "atom:entry",
        NAMESPACES,
    ):
        entry_id = normalize_text(
            entry.findtext(
                "atom:id",
                namespaces=NAMESPACES,
            )
        )

        title = normalize_text(
            entry.findtext(
                "atom:title",
                namespaces=NAMESPACES,
            )
        )

        summary = normalize_text(
            entry.findtext(
                "atom:summary",
                namespaces=NAMESPACES,
            )
        )

        published = normalize_text(
            entry.findtext(
                "atom:published",
                namespaces=NAMESPACES,
            )
        )

        updated = normalize_text(
            entry.findtext(
                "atom:updated",
                namespaces=NAMESPACES,
            )
        )

        authors: list[str] = []

        for author_element in entry.findall(
            "atom:author",
            NAMESPACES,
        ):
            author_name = normalize_text(
                author_element.findtext(
                    "atom:name",
                    namespaces=NAMESPACES,
                )
            )

            if author_name:
                authors.append(author_name)

        pdf_url = find_pdf_url(entry)

        papers.append(
            {
                "arxiv_id": extract_arxiv_id(
                    entry_id
                ),
                "title": title,
                "authors": authors,
                "published": published,
                "updated": updated,
                "summary": summary,
                "abstract_url": entry_id,
                "pdf_url": pdf_url,
            }
        )

    return papers


def request_arxiv(
    query_url: str,
    timeout_seconds: int = ARXIV_TIMEOUT_SECONDS,
    max_attempts: int = ARXIV_MAX_ATTEMPTS,
) -> list[dict]:
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(
                query_url,
                headers=HEADERS,
                timeout=timeout_seconds,
            )
            response.raise_for_status()

            return parse_entries(response.content)

        except (
            requests.Timeout,
            requests.ConnectionError,
        ) as exc:
            last_error = exc

        except requests.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else None
            )

            # Retry only what a retry can fix.
            if status_code and status_code < 500:
                raise RuntimeError(
                    f"The arXiv API rejected the request "
                    f"(HTTP {status_code})."
                ) from exc

            last_error = exc

        except requests.RequestException as exc:
            raise RuntimeError(
                f"The arXiv API request failed: {exc}"
            ) from exc

        if attempt < max_attempts:
            time.sleep(
                ARXIV_RETRY_DELAY_SECONDS * attempt
            )

    raise RuntimeError(
        f"The arXiv API did not respond after "
        f"{max_attempts} attempts "
        f"({timeout_seconds}s each). It may be "
        f"temporarily unavailable."
    ) from last_error


def search_arxiv(
    search_term: str,
    max_results: int = 5,
) -> list[dict]:
    query_url = build_search_query_url(
        search_term=search_term,
        max_results=max_results,
    )

    return request_arxiv(query_url)


def fetch_arxiv_paper(
    arxiv_id: str,
) -> dict:
    normalized_id = normalize_arxiv_id(arxiv_id)

    papers = request_arxiv(
        build_id_query_url(normalized_id)
    )

    if not papers:
        raise RuntimeError(
            f"No arXiv paper was found for ID "
            f"{normalized_id}."
        )

    paper = papers[0]

    returned_base_id = (
        paper["arxiv_id"]
        .split("v", maxsplit=1)[0]
    )
    requested_base_id = (
        normalized_id
        .split("v", maxsplit=1)[0]
    )

    if returned_base_id != requested_base_id:
        raise RuntimeError(
            f"No exact arXiv match was found for "
            f"{normalized_id}."
        )

    return paper


def build_pdf_destination(
    paper: dict,
    raw_data_directory: Path,
) -> Path:
    filename = (
        f"{paper['arxiv_id'].replace('/', '_')}_"
        f"{sanitize_filename(paper['title'])}.pdf"
    )

    return raw_data_directory / filename


def download_pdf(
    pdf_url: str,
    destination: Path,
    timeout_seconds: int = 120,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_destination = (
        destination.with_suffix(".pdf.part")
    )

    try:
        with requests.get(
            pdf_url,
            headers=HEADERS,
            timeout=timeout_seconds,
            stream=True,
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()

            if "pdf" not in content_type:
                raise RuntimeError(
                    "Expected PDF content but received "
                    f"Content-Type: {content_type}"
                )

            with temporary_destination.open(
                "wb"
            ) as pdf_file:
                for chunk in response.iter_content(
                    chunk_size=8192
                ):
                    if chunk:
                        pdf_file.write(chunk)

        if (
            not temporary_destination.exists()
            or temporary_destination.stat().st_size == 0
        ):
            raise RuntimeError(
                "The downloaded PDF is empty."
            )

        temporary_destination.replace(
            destination
        )

    except requests.RequestException as exc:
        temporary_destination.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            f"PDF download failed: {exc}"
        ) from exc

    except OSError as exc:
        temporary_destination.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            f"Could not save PDF: {exc}"
        ) from exc


def download_arxiv_paper(
    paper: dict,
    raw_data_directory: Path,
) -> dict:
    processed_paper = dict(paper)

    pdf_url = processed_paper.get("pdf_url")

    if not pdf_url:
        processed_paper[
            "download_status"
        ] = "missing_pdf_url"

        return processed_paper

    destination = build_pdf_destination(
        paper=processed_paper,
        raw_data_directory=raw_data_directory,
    )

    if (
        destination.exists()
        and destination.stat().st_size > 0
    ):
        processed_paper[
            "download_status"
        ] = "already_exists"
    else:
        download_pdf(
            pdf_url=pdf_url,
            destination=destination,
        )

        processed_paper[
            "download_status"
        ] = "downloaded"

    processed_paper[
        "local_pdf_path"
    ] = str(destination)

    return processed_paper


def build_bibtex_entry(
    paper: dict,
) -> str:
    """
    Render one BibTeX record from stored paper metadata.
    """
    authors = paper.get("authors") or [
        "Unknown"
    ]

    arxiv_id = paper.get("arxiv_id")
    published = paper.get("published")

    year = (
        str(published)[:4]
        if published
        else "n.d."
    )

    first_author = (
        authors[0].split()[-1].lower()
        if authors
        else "unknown"
    )

    citation_key = re.sub(
        r"[^a-z0-9]",
        "",
        f"{first_author}{year}",
    ) or "paper"

    lines = [
        f"@article{{{citation_key},",
        f"  title   = {{{paper.get('title', 'Untitled')}}},",
        f"  author  = {{{' and '.join(authors)}}},",
        f"  year    = {{{year}}},",
    ]

    if arxiv_id:
        lines.append(
            f"  eprint  = {{{arxiv_id}}},"
        )
        lines.append(
            "  archivePrefix = {arXiv},"
        )
        lines.append(
            f"  url     = {{https://arxiv.org/abs/{arxiv_id}}},"
        )

    lines.append("}")

    return "\n".join(lines)